# arXiv Daily Digest — Build Plan

A Python CLI that fetches **today's arXiv submissions** for one or more
sub-arXiv categories, filters them by a configurable list of authors (and
optional keyword rules), and writes a dated **Markdown** digest file.

---

## 1. Scope & decisions (locked)

| Decision | Choice |
|---|---|
| Interface | CLI script driven by a YAML config file |
| Output | Markdown digest file, one per run (e.g. `digests/2026-05-25.md`) |
| "Today" definition | arXiv's official daily listing (the `/new` announcement) |
| Language | Python 3.11+ |

Non-goals for v1: web UI, email delivery, JSON output, full-text search,
citation graph. These are noted in §10 as future work.

---

## 2. Data source

arXiv publishes a **daily "new submissions" listing** per category. The
cleanest machine-readable form is the per-category RSS feed:

```
http://export.arxiv.org/rss/<category>     e.g.  hep-th, cs.LG, math.AG
```

Each feed item contains: arXiv id, title, authors, abstract, primary
category, and a link to the abs page. The feed regenerates each
announcement day, so consuming it once per day = "today's submissions"
exactly as arXiv defines it (correctly skipping weekends/holidays).

**Fallback / enrichment**: for fields the RSS feed truncates (full author
list, comments, cross-list categories), look the paper up via the Atom
API by id: `http://export.arxiv.org/api/query?id_list=<id>`. Do this only
when needed (a paper survives the filter) to stay polite to arXiv.

**Rate-limit etiquette**: arXiv asks for ≤ 1 request / 3 seconds and a
descriptive `User-Agent`. Build a small `requests.Session` wrapper that
enforces this.

---

## 3. Project layout

```
arXiv_search/
├── plan.md                  # this file
├── pyproject.toml           # deps + console_scripts entry point
├── README.md
├── config.example.yaml      # template config the user copies
├── src/
│   └── arxiv_digest/
│       ├── __init__.py
│       ├── cli.py           # argparse / click entry point
│       ├── config.py        # load + validate YAML
│       ├── fetch.py         # RSS fetch, Atom enrich, rate-limit
│       ├── filter.py        # author + keyword matching
│       ├── render.py        # Markdown rendering
│       └── models.py        # Paper dataclass
├── tests/
│   ├── fixtures/            # sample RSS + Atom XML for offline tests
│   ├── test_filter.py
│   ├── test_render.py
│   └── test_fetch.py        # uses responses/vcr, no live calls
└── digests/                 # output directory (gitignored)
```

---

## 4. Dependencies

Minimal, well-known libraries:

- `feedparser` — parse the RSS feed.
- `httpx` (or `requests`) — HTTP with timeouts.
- `pydantic` v2 — config schema + validation with good error messages.
- `pyyaml` — load YAML config.
- `click` — CLI (nicer than argparse for subcommands + help text).
- `rich` — optional, for a pretty terminal summary on top of the file output.
- Dev: `pytest`, `responses` or `pytest-httpx` for HTTP mocking, `ruff`, `mypy`.

Manage with `uv` or `pip` + `pyproject.toml`. Pin in a `uv.lock` /
`requirements.lock`.

---

## 5. Config file format

`config.yaml` — single source of truth for filters. Example:

```yaml
categories:
  - hep-th
  - cond-mat.str-el

authors:
  # Match is case-insensitive, accent-folded, and matches "last, first"
  # or "first last". Substring match on the surname is the default.
  - "Edward Witten"
  - "Maldacena"
  - surname: "Polchinski"      # explicit form
    given: "Joseph"            # optional, narrows match

keywords:                       # optional, OR'd with author hits
  any_of:
    - "holography"
    - "black hole entropy"

exclude:
  authors: []
  keywords: []

output:
  dir: "./digests"
  format: markdown              # only "markdown" in v1
  include_abstract: true
  group_by: category            # category | author | none

http:
  user_agent: "arxiv-digest/0.1 (you@example.com)"
  min_interval_seconds: 3
  timeout_seconds: 20
```

Validate with a Pydantic model so typos in keys fail loudly.

---

## 6. Core flow

```
cli.main()
  ├── load config.yaml         (config.py)
  ├── for each category:
  │     fetch RSS              (fetch.py — rate-limited)
  │     parse into Paper[]     (models.py)
  ├── dedupe by arxiv_id       (cross-listings repeat across categories)
  ├── apply filters            (filter.py)
  │     - author match (normalized, see §7)
  │     - keyword match on title + abstract
  │     - exclude rules
  ├── enrich survivors via Atom API for full author list (fetch.py)
  ├── render Markdown          (render.py)
  └── write digests/YYYY-MM-DD.md, print path to stdout
```

`Paper` dataclass fields: `arxiv_id`, `version`, `title`, `authors`
(list[str]), `abstract`, `primary_category`, `categories`,
`submitted_date`, `abs_url`, `pdf_url`, `matched_authors`,
`matched_keywords`.

---

## 7. Author matching — the tricky part

Naive substring matching produces both false positives ("Lee" matches
half of arXiv) and false negatives (accents, initials, "J. Maldacena"
vs "Juan Maldacena"). Strategy:

1. **Normalize** both sides: lowercase, NFKD-decompose, strip combining
   marks, collapse whitespace, drop punctuation. ("Martín Pérez" →
   "martin perez").
2. **Surname-anchored match**: split the configured name into surname +
   optional given. Require the surname to appear as a whole token in
   the paper's author string.
3. If `given` is provided, require it to appear too, allowing initial
   match (`"Joseph"` matches `"J."` and `"J. M."`).
4. Record which configured author triggered the hit on the `Paper` for
   the renderer to show.

Unit-test this module heavily — it's where bugs will hide. Fixtures
should include diacritics, hyphenated surnames, "Last, First"
ordering, and Chinese/Japanese name romanizations.

---

## 8. Markdown output

One file per run at `digests/YYYY-MM-DD.md`. Example shape:

```markdown
# arXiv digest — 2026-05-25

_Categories: hep-th, cond-mat.str-el • 3 matches out of 187 new submissions_

## hep-th

### [Holographic complexity in de Sitter space](https://arxiv.org/abs/2505.12345)
**arXiv:2505.12345** • Submitted 2026-05-24
**Authors:** Juan Maldacena, A. N. Other  ← _matched: Maldacena_
**Matched keywords:** holography

> Abstract paragraph here…

---
```

Group by `output.group_by`. Always include arxiv id, abs link, authors
(bold the matched ones), and submission date. If
`include_abstract: false`, omit the blockquote.

Print the resulting file path to stdout on completion so the user (or a
cron job) can `open` it.

---

## 9. CLI surface

```
arxiv-digest run [--config PATH] [--date YYYY-MM-DD] [--dry-run]
arxiv-digest validate-config [--config PATH]
arxiv-digest init               # writes config.example.yaml to ./config.yaml
```

- `--date` overrides "today" — useful for re-running yesterday.
  (Implementation note: RSS is always "latest"; for historical replays
  query the Atom API with a `submittedDate` range instead. Document
  this caveat.)
- `--dry-run` fetches and filters but doesn't write the file.

---

## 10. Edge cases & gotchas to handle explicitly

- **No new submissions today** (e.g. weekends): write a digest stating
  so rather than erroring.
- **Cross-listings**: a paper can appear in multiple category feeds.
  Dedupe by `arxiv_id` before filtering.
- **Updated (replaced) papers vs new**: the RSS feed mixes both. Tag
  each item; default to new-only, expose a `include_replacements` config
  flag.
- **arXiv API outages**: catch network errors, log, exit non-zero so
  cron jobs surface it.
- **Author name collisions**: surface this — if a config name matches
  >N papers in a day, warn that the filter may be too loose.
- **Time zone**: arXiv announcements are on US Eastern. Use the feed's
  own date, don't compute "today" from local clock.

---

## 11. Testing strategy

- Unit tests for `filter.py` with name-normalization fixtures.
- Snapshot test for `render.py` against a tiny fixed `Paper[]`.
- `fetch.py` tested with recorded RSS XML (no live network in CI).
- One opt-in integration test (`pytest -m live`) that hits arXiv for
  smoke verification; skipped by default.

---

## 12. Milestones

1. **Skeleton** — pyproject, package layout, empty modules, CI lint.
2. **Fetch + parse** — pull one category's RSS into `Paper[]`; print to stdout.
3. **Filter** — author matcher with tests; keyword matcher.
4. **Render** — Markdown writer; end-to-end happy path.
5. **Config + CLI polish** — YAML schema, `init` / `validate-config` commands, error messages.
6. **Hardening** — rate limiting, retries, edge cases from §10.
7. **README** — install, configure, schedule via `cron`/`launchd`.

Each milestone is independently shippable and testable.

---

## 13. Future extensions (out of scope for v1)

- Email / Slack delivery.
- Web UI showing a rolling N-day window.
- Persistent SQLite store so the digest can diff against "what you've
  already seen".
- LLM-based relevance ranking on top of keyword filtering.
- Citation / co-author network features.
