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
$EDITOR config.yaml           # set your authors, keywords, categories
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
  keep_days: 7                # delete digests older than N days (omit to keep all)

http:
  user_agent: "arxiv-digest/0.1 (you@example.com)"
  min_interval_seconds: 3     # arXiv asks for ≤ 1 request / 3 seconds
  timeout_seconds: 20

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

arxiv-digest schedule install [--config PATH]
    Register a weekday run with the OS scheduler at config.schedule.{hour,minute}.
    Each config file gets its own job, so several can be scheduled at once.
arxiv-digest schedule uninstall [--config PATH]
    Remove that config's scheduled run.
arxiv-digest schedule status
    List every installed scheduled run and the config it uses.
```

`run` also takes `--notify/--no-notify` to override `config.notify.enabled`.
All commands accept `--config PATH` if you want to keep configs elsewhere.

## Scheduling

### Locally (built-in, macOS)

Set a time and (optionally) a desktop notification in your config:

```yaml
schedule:
  enabled: true
  hour: 21        # 24-hour local time
  minute: 30
notify:
  enabled: true
  open_on_click: true   # click the banner to open the digest folder
```

then install the job:

```bash
arxiv-digest schedule install
```

This registers a launchd LaunchAgent that runs `arxiv-digest run` every weekday
(Mon–Fri) at the configured time and shows a banner with the match count. Change the time by
editing the config and re-running `install`; remove it with
`arxiv-digest schedule uninstall`. To schedule more than one config, run
`install --config other.yaml` for each; every config gets its own job
(`com.arxiv-digest.daily.<name>`) and log (`arxiv-digest-<name>.log`), so they
don't replace each other. The notification uses
[`terminal-notifier`](https://github.com/julienXX/terminal-notifier) if
installed (clickable), otherwise falls back to `osascript`.

> **Platform support:** the built-in scheduler is macOS-only for now; Linux
> (systemd) and Windows (Task Scheduler) backends are planned. `notify` and the
> scheduler no-op / error clearly on unsupported platforms.

### Locally (cron, any OS)

arXiv announces around **20:00 US Eastern** on weekdays, so schedule any
time after that. A minimal crontab entry:

```cron
30 21 * * 1-5  cd /path/to/arXiv_search && .venv/bin/arxiv-digest run >> digest.log 2>&1
```

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
