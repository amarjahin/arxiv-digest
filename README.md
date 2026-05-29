# arxiv-digest

A small Python CLI that fetches today's arXiv submissions for one or more
categories, filters them by configured authors and keywords, and writes a
dated Markdown digest.

Source of truth for "today" is arXiv's official per-category RSS feed
(`https://rss.arxiv.org/rss/<category>`), so it matches what's on the
`/list/<category>/new` page exactly (and correctly skips weekends/holidays).

## Install

Requires Python 3.11+.

```bash
git clone <this-repo>
cd arXiv_search
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

This puts an `arxiv-digest` command on your `PATH` (inside the venv).

## Quick start

```bash
arxiv-digest init             # writes ./config.yaml from the example
$EDITOR config.yaml           # set your authors, keywords, categories, email
arxiv-digest validate-config  # confirm the YAML parses
arxiv-digest run              # writes digests/YYYY-MM-DD.md
```

`arxiv-digest run --dry-run` fetches and filters without writing the file —
useful for tuning your filters.

## Configuring filters

`config.yaml` controls everything. The relevant fields:

```yaml
categories:                   # arXiv category slugs — one feed per entry
  - hep-th
  - cond-mat.str-el

authors:                      # bare string OR {surname, given} dict
  - "Edward Witten"           # matches "Edward Witten", "E. Witten",
                              # "Witten, Edward"
  - "Maldacena"               # surname-only — any first name
  - surname: "Polchinski"     # explicit dict form when you want to
    given: "Joseph"           # require a specific given name

keywords:
  any_of:                     # substring match against title + abstract
    - "holography"
    - "black hole entropy"

exclude:
  authors: []                 # same shape as `authors`
  keywords: []                # same shape as `keywords.any_of`

output:
  dir: "./digests"
  include_abstract: true
  group_by: category          # category | author | none
  random_count: 0             # extra random picks from unmatched papers

http:
  user_agent: "arxiv-digest/0.1 (you@example.com)"
  min_interval_seconds: 3     # arXiv asks for ≤ 1 request / 3 seconds
  timeout_seconds: 20

email:
  enabled: false              # set true (or use `--email`) to send via SMTP
  to: ["you@example.com"]
  from_addr: "you@example.com"
  subject: "arXiv digest — {date}"
  host: "smtp.gmail.com"
  port: 587
  username: "you@example.com"
  password_env: "ARXIV_DIGEST_SMTP_PASSWORD"   # read at send time
  attach_file: true

include_replacements: false   # also surface papers arXiv replaced today
```

A paper appears in the digest if it matches **any** configured author
**or** keyword (and is not hit by an `exclude` rule). With both `authors`
and `keywords.any_of` empty, every paper in the listed categories goes
through.

### Author matching, briefly

Names are NFKD-folded (so `Martín` matches `Martin`) and surnames must
appear as **whole tokens** (so `Lee` does not match `Leeson`). When a
given name is supplied, it must find a prefix-compatible match in the
paper's author tokens — so configuring `Edward Witten` matches both
`Edward Witten` and `E. Witten`, but not `Edmund Witten`.

## Commands

```
arxiv-digest run [--config PATH] [--dry-run]
    Fetch each configured category, dedupe, filter, write the digest.

arxiv-digest validate-config [--config PATH]
    Load the config, print the fully-resolved values. Exit non-zero on error.

arxiv-digest init [--config PATH] [--force]
    Copy the bundled example config to PATH (default ./config.yaml).
```

All commands accept `--config PATH` if you want to keep configs elsewhere.

## Scheduling

### Locally (cron / launchd)

arXiv announces around **20:00 US Eastern** on weekdays, so schedule any
time after that. A minimal crontab entry:

```cron
30 21 * * 1-5  cd /path/to/arXiv_search && .venv/bin/arxiv-digest run >> digest.log 2>&1
```

### Daily email via GitHub Actions

`.github/workflows/digest.yml` runs the digest on a cron and emails it to
you. Setup, once per repo:

1. **Gmail app password** — enable 2FA on your Google account, then create
   an app password at https://myaccount.google.com/apppasswords.
2. **Repo secrets** (Settings → Secrets and variables → Actions → New
   repository secret):
   - `ARXIV_DIGEST_SMTP_PASSWORD` — the 16-char app password.
   - `ARXIV_DIGEST_CONFIG` — paste the full contents of your local
     `config.yaml`. `config.yaml` itself is gitignored; the workflow
     writes this secret to disk before running.
3. **First run** — Actions tab → "Daily arXiv digest" → "Run workflow"
   to verify before waiting for the next cron tick.

To change a setting (new keyword, different recipient, etc.), edit the
`ARXIV_DIGEST_CONFIG` secret in the GitHub UI. The default cron is
`0 13 * * 1-5` (09:00 ET weekdays) — adjust in the workflow file.

## Output

One file per run: `digests/YYYY-MM-DD_<category>.md` (the first
category in `config.yaml` is used in the filename). Header shows the categories
queried and the match count; each entry has the title (linked to the abs
page), arXiv id, authors (with the matched config name called out),
matched keywords, cross-list categories, and the abstract as a
blockquote.

## Development

```bash
pytest                  # unit tests; skips the live-network marker by default
pytest -m live          # opt-in: hit the real arXiv API
ruff check .            # lint
```

The package layout is `src/arxiv_digest/`. See `plan.md` for the design
notes and the deferred-feature list.
