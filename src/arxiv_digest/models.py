"""Internal data model for one arXiv paper as it flows through the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Paper:
    """One arXiv submission. Constructed by `fetch`, annotated by `filter`,
    consumed by `render`."""

    arxiv_id: str                          # e.g. "2505.12345" (no version suffix)
    version: int                           # 1 for brand-new submissions
    title: str
    authors: list[str]                     # in arXiv's listed order
    abstract: str
    primary_category: str                  # e.g. "hep-th"
    categories: list[str]                  # primary + cross-lists
    submitted_date: date                   # the announcement date
    abs_url: str                           # https://arxiv.org/abs/<id>
    pdf_url: str                           # https://arxiv.org/pdf/<id>

    # Filter annotations — empty until filter.py runs.
    matched_authors: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)

    # Whether arXiv flagged this entry as a replacement vs a new submission.
    is_replacement: bool = False

    @property
    def id_with_version(self) -> str:
        return f"{self.arxiv_id}v{self.version}"
