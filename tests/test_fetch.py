"""Tests for fetch.py against a saved RSS fixture (no network)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from arxiv_digest.fetch import parse_rss

FIXTURE = Path(__file__).parent / "fixtures" / "sample_hep-th.xml"


def test_parses_expected_number_of_entries():
    papers = parse_rss(FIXTURE.read_bytes(), "hep-th")
    # The saved feed had 48 entries when captured. If the fixture changes, update this.
    assert len(papers) == 48


def test_first_paper_fields():
    papers = parse_rss(FIXTURE.read_bytes(), "hep-th")
    p = papers[0]
    assert p.arxiv_id == "2605.22912"
    assert p.version == 1
    assert p.title.startswith("Sharpening the Supersymmetric")
    assert "Matthew Reece" in p.authors
    assert p.primary_category == "hep-th"
    assert p.submitted_date == date(2026, 5, 25)
    assert p.abs_url == "https://arxiv.org/abs/2605.22912"
    assert p.pdf_url == "https://arxiv.org/pdf/2605.22912"
    assert not p.is_replacement
    assert p.abstract.startswith("The Axion Weak Gravity Conjecture")


def test_replacements_are_flagged():
    papers = parse_rss(FIXTURE.read_bytes(), "hep-th")
    replacements = [p for p in papers if p.is_replacement]
    # The captured fixture has 12 replacements; if the fixture changes update both.
    assert len(replacements) == 12


def test_abstract_prefix_stripped():
    papers = parse_rss(FIXTURE.read_bytes(), "hep-th")
    for p in papers:
        assert not p.abstract.startswith("arXiv:")
        assert not p.abstract.lower().startswith("abstract:")


def test_authors_are_split_not_one_concatenated_string():
    papers = parse_rss(FIXTURE.read_bytes(), "hep-th")
    # Find a paper with multiple authors and confirm we split them.
    multi = next((p for p in papers if len(p.authors) >= 3), None)
    assert multi is not None, "fixture should contain at least one multi-author paper"
    for name in multi.authors:
        assert "," not in name
