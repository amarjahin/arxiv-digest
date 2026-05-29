"""Author + keyword filtering for fetched Papers.

A paper survives the filter if it matches at least one author OR keyword
inclusion rule AND matches no exclusion rule. If no inclusion rules are
configured at all, every paper survives (useful for "just give me everything
in hep-th today").

The non-trivial bit is author matching — see AuthorPattern below.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from .models import Paper

# Anything that isn't a letter, digit, hyphen, or whitespace becomes a space
# before tokenizing. Hyphens are kept so "Smith-Jones" stays one token.
_PUNCT_RE = re.compile(r"[^\w\s\-]", flags=re.UNICODE)


def _normalize_tokens(value: str) -> list[str]:
    """Lower-case, accent-fold, and split a name or phrase into tokens.

    >>> _normalize_tokens("Martín Pérez")
    ['martin', 'perez']
    >>> _normalize_tokens("Witten, E.")
    ['witten', 'e']
    """
    # NFKD splits accented chars into base + combining mark; we then drop the
    # combining marks (category Mn = Mark, nonspacing).
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = _PUNCT_RE.sub(" ", stripped).lower()
    return cleaned.split()


def _normalize_phrase(value: str) -> str:
    """Same normalization as _normalize_tokens but rejoined as a single string,
    used for substring matching against title + abstract."""
    return " ".join(_normalize_tokens(value))


@dataclass
class AuthorPattern:
    """A configured author filter, normalized for matching.

    `surname` is required (the anchor token). `given_tokens` may be empty
    (match any first name) or one+ tokens that must each find a
    prefix-compatible author token.
    """

    surname: str                  # normalized, single token
    given_tokens: list[str]       # normalized, may be empty
    display: str                  # original spelling, for output

    @classmethod
    def from_config(cls, value: str | dict[str, Any]) -> AuthorPattern:
        if isinstance(value, str):
            tokens = _normalize_tokens(value)
            if not tokens:
                raise ValueError(f"empty author filter: {value!r}")
            # Last token = surname, rest = given. Single-token configs
            # become surname-only filters.
            surname = tokens[-1]
            given = tokens[:-1]
            return cls(surname=surname, given_tokens=given, display=value.strip())

        # dict form: {surname: ..., given: ...}
        if not isinstance(value, dict) or "surname" not in value:
            raise ValueError(f"author filter must be a string or a dict with 'surname': {value!r}")
        surname_tokens = _normalize_tokens(str(value["surname"]))
        if len(surname_tokens) != 1:
            raise ValueError(f"surname must normalize to one token, got {surname_tokens!r}")
        given_raw = value.get("given") or ""
        given_tokens = _normalize_tokens(str(given_raw))
        display = f"{given_raw} {value['surname']}".strip() if given_raw else str(value["surname"])
        return cls(surname=surname_tokens[0], given_tokens=given_tokens, display=display)

    def matches(self, author_name: str) -> bool:
        author_tokens = _normalize_tokens(author_name)
        if self.surname not in author_tokens:
            return False
        if not self.given_tokens:
            return True
        # Each configured given token must match SOME author token (other
        # than the surname slot) via prefix compatibility.
        non_surname = [t for t in author_tokens if t != self.surname]
        for needed in self.given_tokens:
            if not any(_prefix_compatible(needed, candidate) for candidate in non_surname):
                return False
        return True


def _prefix_compatible(a: str, b: str) -> bool:
    """True if either token is a prefix of the other. Empty strings never match."""
    if not a or not b:
        return False
    return a.startswith(b) or b.startswith(a)


@dataclass
class FilterConfig:
    """Parsed inclusion/exclusion rules, ready to apply."""

    authors: list[AuthorPattern] = field(default_factory=list)
    keywords_any_of: list[str] = field(default_factory=list)        # normalized phrases
    exclude_authors: list[AuthorPattern] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)       # normalized phrases
    include_replacements: bool = False

    @property
    def has_inclusions(self) -> bool:
        return bool(self.authors or self.keywords_any_of)

    @classmethod
    def from_raw(
        cls,
        authors: list[Any] | None = None,
        keywords_any_of: list[str] | None = None,
        exclude_authors: list[Any] | None = None,
        exclude_keywords: list[str] | None = None,
        include_replacements: bool = False,
    ) -> FilterConfig:
        return cls(
            authors=[AuthorPattern.from_config(a) for a in (authors or [])],
            keywords_any_of=[_normalize_phrase(k) for k in (keywords_any_of or []) if k.strip()],
            exclude_authors=[AuthorPattern.from_config(a) for a in (exclude_authors or [])],
            exclude_keywords=[_normalize_phrase(k) for k in (exclude_keywords or []) if k.strip()],
            include_replacements=include_replacements,
        )


def filter_papers(papers: list[Paper], filters: FilterConfig) -> list[Paper]:
    """Return papers that pass the filter, with `matched_*` fields populated."""
    survivors: list[Paper] = []
    for paper in papers:
        if paper.is_replacement and not filters.include_replacements:
            continue

        matched_authors = _match_authors(paper, filters.authors)
        matched_keywords = _match_keywords(paper, filters.keywords_any_of)

        # Inclusion check: with no rules, everything is in; with rules, need
        # at least one author OR keyword hit.
        if filters.has_inclusions and not (matched_authors or matched_keywords):
            continue

        # Exclusion check: any exclude_authors hit OR any exclude_keywords hit
        # drops the paper.
        if _match_authors(paper, filters.exclude_authors):
            continue
        if _match_keywords(paper, filters.exclude_keywords):
            continue

        paper.matched_authors = [pat.display for pat in matched_authors]
        paper.matched_keywords = matched_keywords
        survivors.append(paper)
    return survivors


def _match_authors(paper: Paper, patterns: list[AuthorPattern]) -> list[AuthorPattern]:
    hits: list[AuthorPattern] = []
    for pat in patterns:
        if any(pat.matches(name) for name in paper.authors):
            hits.append(pat)
    return hits


def _match_keywords(paper: Paper, normalized_keywords: list[str]) -> list[str]:
    if not normalized_keywords:
        return []
    haystack = _normalize_phrase(f"{paper.title} {paper.abstract}")
    return [kw for kw in normalized_keywords if kw in haystack]


def dedupe(papers: list[Paper]) -> list[Paper]:
    """Drop duplicates by arxiv_id (papers can be cross-listed into multiple
    categories and thus appear in multiple feeds)."""
    seen: set[str] = set()
    out: list[Paper] = []
    for p in papers:
        if p.arxiv_id in seen:
            continue
        seen.add(p.arxiv_id)
        out.append(p)
    return out
