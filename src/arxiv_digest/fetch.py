"""Fetch arXiv per-category RSS feeds and parse them into Paper objects.

The RSS feed (https://rss.arxiv.org/rss/<category>) is the source of truth for
arXiv's daily announcement listing — it's what populates the /list/<cat>/new
page. We parse it offline (via feedparser) so this module has no network logic
beyond the thin `ArxivClient` HTTP wrapper.
"""

from __future__ import annotations

import re
import time
from datetime import date
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import httpx

from .models import Paper

# guid format: "oai:arXiv.org:2605.22912v1"
_GUID_RE = re.compile(r"oai:arXiv\.org:(?P<id>\S+?)v(?P<version>\d+)$")

# Strip the boilerplate prefix arXiv prepends to every <description>:
#   "arXiv:2605.22912v1 Announce Type: new \nAbstract: <real abstract>"
_SUMMARY_PREFIX_RE = re.compile(
    r"^arXiv:\S+\s+Announce\s+Type:\s+\S+\s+Abstract:\s+", re.IGNORECASE
)

RSS_URL_TEMPLATE = "https://rss.arxiv.org/rss/{category}"


class ArxivClient:
    """HTTP client that enforces arXiv's politeness policy (~1 request / 3s)
    and sets a descriptive User-Agent.

    Used as a context manager so the underlying httpx.Client gets closed:
        with ArxivClient(user_agent="...") as c:
            resp = c.get(url)
    """

    def __init__(
        self,
        user_agent: str,
        min_interval_seconds: float = 3.0,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout_seconds,
            follow_redirects=True,
        )
        self._min_interval = min_interval_seconds
        self._last_request_monotonic: float = 0.0

    def get(self, url: str) -> httpx.Response:
        elapsed = time.monotonic() - self._last_request_monotonic
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        resp = self._client.get(url)
        self._last_request_monotonic = time.monotonic()
        resp.raise_for_status()
        return resp

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ArxivClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def parse_rss(content: bytes, requested_category: str) -> list[Paper]:
    """Parse one category's RSS bytes into Paper objects.

    `requested_category` is used only as a fallback when an entry is missing
    its <category> element — the RSS we requested defines what category we
    asked for.
    """
    feed = feedparser.parse(content)
    papers: list[Paper] = []
    for entry in feed.entries:
        paper = _entry_to_paper(entry, requested_category)
        if paper is not None:
            papers.append(paper)
    return papers


def _entry_to_paper(entry: Any, requested_category: str) -> Paper | None:
    guid = entry.get("id", "")
    m = _GUID_RE.search(guid)
    if not m:
        return None  # silently drop malformed entries
    arxiv_id = m.group("id")
    version = int(m.group("version"))

    abstract = _SUMMARY_PREFIX_RE.sub("", entry.get("summary", "")).strip()

    # arXiv puts all authors into one comma-separated dc:creator string.
    # feedparser exposes that whole string as entry.author.
    author_str = entry.get("author") or ""
    authors = [a.strip() for a in author_str.split(",") if a.strip()]

    tags = entry.get("tags") or []
    categories = [t.get("term") for t in tags if t.get("term")]
    primary_category = categories[0] if categories else requested_category

    # Use the original RFC 2822 timezone (arXiv stamps these in US Eastern) so
    # we don't accidentally roll over a date when feedparser shifts to UTC.
    submitted = _parse_pub_date(entry.get("published", ""))

    announce_type = (entry.get("arxiv_announce_type") or "new").lower()

    abs_url = entry.get("link") or f"https://arxiv.org/abs/{arxiv_id}"
    pdf_url = abs_url.replace("/abs/", "/pdf/")

    return Paper(
        arxiv_id=arxiv_id,
        version=version,
        title=entry.get("title", "").strip(),
        authors=authors,
        abstract=abstract,
        primary_category=primary_category,
        categories=categories or [requested_category],
        submitted_date=submitted,
        abs_url=abs_url,
        pdf_url=pdf_url,
        is_replacement=(announce_type == "replace"),
    )


def _parse_pub_date(value: str) -> date:
    if not value:
        return date.today()
    try:
        return parsedate_to_datetime(value).date()
    except (TypeError, ValueError):
        return date.today()


def fetch_category(client: ArxivClient, category: str) -> list[Paper]:
    """Fetch and parse one category's daily listing."""
    resp = client.get(RSS_URL_TEMPLATE.format(category=category))
    return parse_rss(resp.content, requested_category=category)
