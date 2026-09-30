"""Render filtered Papers as a Markdown digest."""

from __future__ import annotations

import re
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from typing import Literal

from .models import Paper

GroupBy = Literal["category", "author", "none", "priority"]


def render_markdown(
    papers: list[Paper],
    *,
    categories: list[str],
    total_seen: int,
    run_date: date,
    include_abstract: bool = True,
    group_by: GroupBy = "category",
    keyword_priority: list[str] | None = None,
    random_papers: list[Paper] | None = None,
) -> str:
    """Build the digest as one Markdown string."""
    buf = StringIO()
    _write_header(buf, run_date, categories, matches=len(papers), total=total_seen)

    if not papers:
        buf.write("_No matching submissions today._\n")
    else:
        if group_by == "category":
            grouped = _group_by_category(papers)
        elif group_by == "author":
            grouped = _group_by_matched_author(papers)
        elif group_by == "priority":
            grouped = _group_by_priority(papers, keyword_priority or [])
        else:
            grouped = [("", papers)]

        for heading, group_papers in grouped:
            if heading:
                buf.write(f"## {heading} ({len(group_papers)})\n\n")
            for paper in group_papers:
                _write_paper(buf, paper, include_abstract=include_abstract)

    if random_papers:
        buf.write(f"## Random picks ({len(random_papers)})\n\n")
        for paper in random_papers:
            _write_paper(buf, paper, include_abstract=include_abstract)

    return buf.getvalue()


def write_digest(
    content: str,
    output_dir: Path,
    run_date: date,
    primary_category: str,
) -> Path:
    """Write the digest to `<output_dir>/<YYYY-MM-DD>_<category>.md`."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{run_date.isoformat()}_{primary_category}.md"
    path.write_text(content, encoding="utf-8")
    return path


# Matches only files `write_digest` produces, so pruning never touches
# anything else a user keeps in the output dir.
_DIGEST_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_.+\.md$")


def prune_digests(output_dir: Path, today: date, keep_days: int) -> list[Path]:
    """Delete digests whose filename date is more than `keep_days` before
    `today`. Returns the removed paths."""
    if not output_dir.is_dir():
        return []
    cutoff = today - timedelta(days=keep_days)
    removed: list[Path] = []
    for path in sorted(output_dir.iterdir()):
        m = _DIGEST_NAME_RE.match(path.name)
        if not m or not path.is_file():
            continue
        try:
            file_date = date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if file_date < cutoff:
            path.unlink()
            removed.append(path)
    return removed


# ---- internals ----

def _write_header(
    buf: StringIO, run_date: date, categories: list[str], matches: int, total: int
) -> None:
    buf.write(f"# arXiv digest — {run_date.isoformat()}\n\n")
    cat_list = ", ".join(categories) if categories else "(none)"
    buf.write(
        f"_Categories: {cat_list} • {matches} match"
        f"{'es' if matches != 1 else ''} out of {total} new submission"
        f"{'s' if total != 1 else ''}._\n\n"
    )


def _write_paper(buf: StringIO, paper: Paper, *, include_abstract: bool) -> None:
    buf.write(f"### [{paper.title}]({paper.abs_url})\n")
    buf.write(
        f"**arXiv:{paper.arxiv_id}** • Submitted {paper.submitted_date.isoformat()}"
    )
    if paper.is_replacement:
        buf.write(" • _replacement_")
    buf.write("\n")

    authors_str = ", ".join(paper.authors) if paper.authors else "(no authors listed)"
    buf.write(f"**Authors:** {authors_str}")
    if paper.matched_authors:
        buf.write(f"  ← _matched: {', '.join(paper.matched_authors)}_")
    buf.write("\n")

    if paper.matched_keywords:
        buf.write(f"**Matched keywords:** {', '.join(paper.matched_keywords)}\n")

    if paper.categories and len(paper.categories) > 1:
        buf.write(f"**Categories:** {', '.join(paper.categories)}\n")

    if include_abstract and paper.abstract:
        buf.write("\n")
        for line in paper.abstract.splitlines() or [paper.abstract]:
            buf.write(f"> {line}\n")

    buf.write("\n---\n\n")


def _group_by_category(papers: list[Paper]) -> list[tuple[str, list[Paper]]]:
    buckets: dict[str, list[Paper]] = {}
    for p in papers:
        buckets.setdefault(p.primary_category, []).append(p)
    return sorted(buckets.items())


def _group_by_matched_author(papers: list[Paper]) -> list[tuple[str, list[Paper]]]:
    buckets: dict[str, list[Paper]] = {}
    untagged: list[Paper] = []
    for p in papers:
        if not p.matched_authors:
            untagged.append(p)
            continue
        for author in p.matched_authors:
            buckets.setdefault(author, []).append(p)
    grouped = sorted(buckets.items())
    if untagged:
        grouped.append(("Other matches", untagged))
    return grouped


def _group_by_priority(
    papers: list[Paper], keyword_priority: list[str]
) -> list[tuple[str, list[Paper]]]:
    """Author matches first, then one section per keyword in config order.
    Each paper goes in exactly one bucket — author > keyword, and among
    keywords the earliest-listed wins."""
    author_bucket: list[Paper] = []
    keyword_buckets: dict[str, list[Paper]] = {kw: [] for kw in keyword_priority}
    untagged: list[Paper] = []
    for p in papers:
        if p.matched_authors:
            author_bucket.append(p)
            continue
        placed = False
        for kw in keyword_priority:
            if kw in p.matched_keywords:
                keyword_buckets[kw].append(p)
                placed = True
                break
        if not placed:
            untagged.append(p)

    grouped: list[tuple[str, list[Paper]]] = []
    if author_bucket:
        grouped.append(("Author matches", author_bucket))
    for kw in keyword_priority:
        if keyword_buckets[kw]:
            grouped.append((f"Keyword: {kw}", keyword_buckets[kw]))
    if untagged:
        grouped.append(("Other", untagged))
    return grouped
