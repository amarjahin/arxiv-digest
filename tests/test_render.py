"""Tests for render.py — verify Markdown shape and grouping."""

from __future__ import annotations

from datetime import date

from arxiv_digest.models import Paper
from arxiv_digest.render import render_markdown


def _paper(**kw) -> Paper:
    defaults = dict(
        arxiv_id="2501.00001",
        version=1,
        title="Quantum Gravity Notes",
        authors=["Alice Smith", "Bob Jones"],
        abstract="A short abstract.",
        primary_category="hep-th",
        categories=["hep-th"],
        submitted_date=date(2026, 5, 25),
        abs_url="https://arxiv.org/abs/2501.00001",
        pdf_url="https://arxiv.org/pdf/2501.00001",
    )
    defaults.update(kw)
    return Paper(**defaults)


def test_empty_match_message():
    md = render_markdown(
        [], categories=["hep-th"], total_seen=10, run_date=date(2026, 5, 25)
    )
    assert "No matching submissions today" in md
    assert "0 matches out of 10" in md


def test_singular_plural_in_header():
    md = render_markdown(
        [_paper()], categories=["hep-th"], total_seen=1, run_date=date(2026, 5, 25)
    )
    assert "1 match out of 1 new submission." in md


def test_paper_block_has_link_id_and_authors():
    p = _paper(matched_authors=["Smith"], matched_keywords=["quantum"])
    md = render_markdown(
        [p], categories=["hep-th"], total_seen=1, run_date=date(2026, 5, 25)
    )
    assert "### [Quantum Gravity Notes](https://arxiv.org/abs/2501.00001)" in md
    assert "**arXiv:2501.00001**" in md
    assert "**Authors:** Alice Smith, Bob Jones" in md
    assert "_matched: Smith_" in md
    assert "**Matched keywords:** quantum" in md
    assert "> A short abstract." in md


def test_group_by_category_orders_headings():
    p1 = _paper(arxiv_id="2501.00001", primary_category="hep-th")
    p2 = _paper(arxiv_id="2501.00002", primary_category="cond-mat.str-el")
    md = render_markdown(
        [p1, p2],
        categories=["hep-th", "cond-mat.str-el"],
        total_seen=2,
        run_date=date(2026, 5, 25),
        group_by="category",
    )
    # alphabetical: cond-mat.str-el before hep-th
    assert md.index("## cond-mat.str-el") < md.index("## hep-th")


def test_group_by_none_omits_category_headings():
    p = _paper()
    md = render_markdown(
        [p],
        categories=["hep-th"],
        total_seen=1,
        run_date=date(2026, 5, 25),
        group_by="none",
    )
    assert "## hep-th" not in md
    assert "### [Quantum Gravity Notes]" in md


def test_replacement_marker():
    p = _paper(is_replacement=True)
    md = render_markdown(
        [p], categories=["hep-th"], total_seen=1, run_date=date(2026, 5, 25)
    )
    assert "_replacement_" in md


def test_omit_abstract_when_flag_off():
    md = render_markdown(
        [_paper()],
        categories=["hep-th"],
        total_seen=1,
        run_date=date(2026, 5, 25),
        include_abstract=False,
    )
    assert "> A short abstract." not in md


def test_prune_digests_removes_only_old_digest_files(tmp_path):
    from arxiv_digest.render import prune_digests

    today = date(2026, 9, 30)
    old = tmp_path / "2026-09-22_hep-th.md"          # 8 days old
    boundary = tmp_path / "2026-09-23_hep-th.md"     # exactly 7 days — kept
    recent = tmp_path / "2026-09-29_hep-th.md"
    unrelated = tmp_path / "notes.md"
    old_non_md = tmp_path / "2020-01-01_hep-th.txt"
    for p in (old, boundary, recent, unrelated, old_non_md):
        p.write_text("x")

    removed = prune_digests(tmp_path, today, keep_days=7)

    assert removed == [old]
    assert not old.exists()
    assert boundary.exists() and recent.exists()
    assert unrelated.exists() and old_non_md.exists()


def test_prune_digests_missing_dir_is_noop(tmp_path):
    from arxiv_digest.render import prune_digests

    assert prune_digests(tmp_path / "nope", date(2026, 9, 30), keep_days=7) == []
