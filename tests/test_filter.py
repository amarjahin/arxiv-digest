"""Unit tests for filter.py — the highest-bug-risk module per the plan."""

from __future__ import annotations

from datetime import date

import pytest

from arxiv_digest.filter import (
    AuthorPattern,
    FilterConfig,
    _normalize_tokens,
    dedupe,
    filter_papers,
)
from arxiv_digest.models import Paper


def _paper(arxiv_id: str = "2501.00001", **overrides) -> Paper:
    defaults = dict(
        arxiv_id=arxiv_id,
        version=1,
        title="Title",
        authors=["Alice Smith"],
        abstract="Abstract about quantum gravity.",
        primary_category="hep-th",
        categories=["hep-th"],
        submitted_date=date(2026, 5, 25),
        abs_url=f"https://arxiv.org/abs/{arxiv_id}",
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
    )
    defaults.update(overrides)
    return Paper(**defaults)


class TestNormalize:
    def test_accent_fold(self):
        assert _normalize_tokens("Martín Pérez") == ["martin", "perez"]

    def test_strip_punctuation_but_keep_hyphen(self):
        assert _normalize_tokens("Smith-Jones, A.") == ["smith-jones", "a"]

    def test_collapses_whitespace(self):
        assert _normalize_tokens("  Foo   Bar  ") == ["foo", "bar"]


class TestAuthorPatternMatch:
    @pytest.mark.parametrize("cfg,author,expected", [
        ("Edward Witten", "Edward Witten", True),
        ("Edward Witten", "E. Witten", True),
        ("Edward Witten", "Witten, Edward", True),
        ("Edward Witten", "Edmund Witten", False),
        ("Witten", "E. Witten", True),
        ("Witten", "J. Wittenberg", False),       # surname is a token boundary
        ("Maldacena", "J. Maldacena", True),
        ("Martín Pérez", "Martin Perez", True),
        ("Martin Perez", "Martín Pérez", True),
        ("Lee", "Sam Leeson", False),             # whole-token requirement
        ("Smith-Jones", "A. Smith-Jones", True),
        ("Smith-Jones", "A. Smith", False),       # hyphen joins tokens
    ])
    def test_string_form(self, cfg, author, expected):
        pat = AuthorPattern.from_config(cfg)
        assert pat.matches(author) is expected

    def test_dict_form_with_given_filters(self):
        pat = AuthorPattern.from_config({"surname": "Polchinski", "given": "Joseph"})
        assert pat.matches("J. Polchinski") is True
        assert pat.matches("Joseph Polchinski") is True
        assert pat.matches("A. Polchinski") is False

    def test_dict_form_without_given(self):
        pat = AuthorPattern.from_config({"surname": "Polchinski"})
        assert pat.matches("A. Polchinski") is True

    def test_invalid_inputs(self):
        with pytest.raises(ValueError):
            AuthorPattern.from_config("")
        with pytest.raises(ValueError):
            AuthorPattern.from_config({"given": "Joseph"})  # missing surname
        with pytest.raises(ValueError):
            AuthorPattern.from_config({"surname": "Van Der Berg"})  # surname must be 1 token


class TestFilterPapers:
    def test_no_filters_lets_everything_through(self):
        papers = [_paper("2501.00001"), _paper("2501.00002")]
        out = filter_papers(papers, FilterConfig.from_raw())
        assert len(out) == 2

    def test_author_inclusion(self):
        papers = [
            _paper("2501.00001", authors=["Alice Smith"]),
            _paper("2501.00002", authors=["Bob Jones"]),
        ]
        out = filter_papers(papers, FilterConfig.from_raw(authors=["Smith"]))
        assert [p.arxiv_id for p in out] == ["2501.00001"]
        assert out[0].matched_authors == ["Smith"]

    def test_keyword_inclusion_normalizes(self):
        papers = [
            _paper("2501.00001", abstract="Discusses BLACK HOLES at length"),
            _paper("2501.00002", abstract="About cold atoms"),
        ]
        out = filter_papers(papers, FilterConfig.from_raw(keywords_any_of=["black hole"]))
        assert [p.arxiv_id for p in out] == ["2501.00001"]
        assert out[0].matched_keywords == ["black hole"]

    def test_inclusion_is_OR(self):
        papers = [
            _paper("2501.00001", authors=["Smith"], abstract="cold atoms"),
            _paper("2501.00002", authors=["Jones"], abstract="black hole"),
            _paper("2501.00003", authors=["Jones"], abstract="cold atoms"),
        ]
        out = filter_papers(
            papers, FilterConfig.from_raw(authors=["Smith"], keywords_any_of=["black hole"])
        )
        assert {p.arxiv_id for p in out} == {"2501.00001", "2501.00002"}

    def test_exclude_overrides_inclusion(self):
        papers = [_paper(authors=["Alice Smith"], abstract="quantum gravity")]
        out = filter_papers(
            papers,
            FilterConfig.from_raw(authors=["Smith"], exclude_keywords=["quantum gravity"]),
        )
        assert out == []

    def test_replacements_dropped_by_default(self):
        papers = [
            _paper("2501.00001", is_replacement=False),
            _paper("2501.00002", is_replacement=True),
        ]
        out = filter_papers(papers, FilterConfig.from_raw())
        assert [p.arxiv_id for p in out] == ["2501.00001"]

    def test_replacements_kept_when_enabled(self):
        papers = [_paper("2501.00002", is_replacement=True)]
        out = filter_papers(papers, FilterConfig.from_raw(include_replacements=True))
        assert len(out) == 1


class TestDedupe:
    def test_drops_repeated_arxiv_ids_preserving_order(self):
        a = _paper("2501.00001", primary_category="hep-th")
        b = _paper("2501.00001", primary_category="quant-ph")  # cross-listed dup
        c = _paper("2501.00002")
        out = dedupe([a, b, c])
        assert [p.arxiv_id for p in out] == ["2501.00001", "2501.00002"]
        assert out[0].primary_category == "hep-th"  # first wins
