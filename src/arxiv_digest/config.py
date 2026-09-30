"""YAML config loading and validation.

We use pydantic so unknown keys / wrong types fail loudly with line-precise
errors, instead of silently being ignored (the common cost of plain dataclass
loaders).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .filter import FilterConfig


class AuthorEntry(BaseModel):
    """The dict form of an author filter: `{surname: ..., given: ...}`."""
    model_config = ConfigDict(extra="forbid")
    surname: str
    given: str | None = None


# An author in the config is either a bare string ("Edward Witten") or the
# dict form. Pydantic discriminates by type.
AuthorFilter = Union[str, AuthorEntry]


class Keywords(BaseModel):
    model_config = ConfigDict(extra="forbid")
    any_of: list[str] = Field(default_factory=list)


class Exclude(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authors: list[AuthorFilter] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dir: Path = Path("./digests")
    format: Literal["markdown"] = "markdown"
    include_abstract: bool = True
    group_by: Literal["category", "author", "none", "priority"] = "category"
    random_count: int = Field(default=0, ge=0)
    keep_days: int | None = Field(default=None, ge=1)   # prune older digests; None = keep all


class Http(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_agent: str = "arxiv-digest/0.1 (please set contact email)"
    min_interval_seconds: float = 3.0
    timeout_seconds: float = 20.0


class Email(BaseModel):
    """SMTP delivery settings. Password is never stored here — it's read at
    send time from the env var named in `password_env`."""

    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    to: list[str] = Field(default_factory=list)
    from_addr: str | None = None        # defaults to `username` if unset
    subject: str = "arXiv digest — {date}"   # `{date}` is substituted at send time
    host: str = "smtp.gmail.com"
    port: int = 587
    username: str = ""                  # SMTP login (usually your Gmail address)
    password_env: str = "ARXIV_DIGEST_SMTP_PASSWORD"
    attach_file: bool = True            # attach the .md file alongside the body


class Schedule(BaseModel):
    """Daily run time for `arxiv-digest schedule install` (local clock)."""

    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    hour: int = Field(default=8, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)


class Notify(BaseModel):
    """Desktop notification shown at the end of a run."""

    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    open_on_click: bool = True   # clicking the banner opens the digest folder


class Config(BaseModel):
    """Top-level config. `extra='forbid'` so a typo in a key fails fast."""

    model_config = ConfigDict(extra="forbid")

    categories: list[str]
    authors: list[AuthorFilter] = Field(default_factory=list)
    keywords: Keywords = Field(default_factory=Keywords)
    exclude: Exclude = Field(default_factory=Exclude)
    output: Output = Field(default_factory=Output)
    http: Http = Field(default_factory=Http)
    email: Email = Field(default_factory=Email)
    schedule: Schedule = Field(default_factory=Schedule)
    notify: Notify = Field(default_factory=Notify)
    include_replacements: bool = False

    @field_validator("categories")
    @classmethod
    def _categories_nonempty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("at least one category is required")
        return v

    def to_filter_config(self) -> FilterConfig:
        """Convert the validated config into the runtime FilterConfig that
        `filter.filter_papers` consumes."""
        return FilterConfig.from_raw(
            authors=[_unwrap_author(a) for a in self.authors],
            keywords_any_of=self.keywords.any_of,
            exclude_authors=[_unwrap_author(a) for a in self.exclude.authors],
            exclude_keywords=self.exclude.keywords,
            include_replacements=self.include_replacements,
        )


def _unwrap_author(a: AuthorFilter) -> str | dict[str, str]:
    """Convert pydantic model back to the dict form AuthorPattern expects."""
    if isinstance(a, AuthorEntry):
        d: dict[str, str] = {"surname": a.surname}
        if a.given is not None:
            d["given"] = a.given
        return d
    return a


class ConfigError(Exception):
    """Raised with a user-friendly message when the config can't be loaded."""


def load_config(path: Path) -> Config:
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {path}: {e}") from e
    if raw is None:
        raise ConfigError(f"Config file {path} is empty")
    if not isinstance(raw, dict):
        raise ConfigError(f"Config file {path} must contain a YAML mapping at the top level")
    try:
        return Config.model_validate(raw)
    except ValidationError as e:
        raise ConfigError(f"Config validation failed for {path}:\n{e}") from e
