"""Core domain models.

Design stance: ``ResolvedEvent`` is a *faithful, tolerant* flattening of a
JSON:API ``news_event`` and its linked entities — not a validated/clean record.
Content-level problems (out-of-range confidence, implausible dates, unknown
categories) are deliberately **not** rejected here; the raw value is coerced
where possible and the original is always preserved in ``attributes`` so the
deterministic rules (Phase 1) can flag them. Only *structural* failures —
unparseable JSON, a missing ``data`` envelope, an event with no ``id`` — are
surfaced as ``ParseError`` by the parser, because such a record cannot be keyed
or reasoned about at all.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --------------------------------------------------------------------------- #
# Lenient coercion helpers
#
# These never raise: a value that cannot be coerced becomes ``None``. The raw,
# uncoerced value still lives in ``ResolvedEvent.attributes`` for the rules.
# --------------------------------------------------------------------------- #


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().lstrip("$").replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _to_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            # Python 3.11+ handles trailing 'Z' and offsets; date-only is ok too.
            return datetime.fromisoformat(text)
        except ValueError:
            return None
    return None


def _to_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return None


# --------------------------------------------------------------------------- #
# Linked entities (resolved from the JSON:API ``included`` array)
# --------------------------------------------------------------------------- #


class Company(BaseModel):
    """A company entity linked from ``relationships`` and resolved via ``included``."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str | None = None
    domain: str | None = None
    ticker: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    """Full original ``attributes`` block, preserved verbatim."""


class Article(BaseModel):
    """A news article entity — the evidence the LLM judges read."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str | None = None
    body: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("published_at", mode="before")
    @classmethod
    def _coerce_published_at(cls, value: Any) -> datetime | None:
        return _to_datetime(value)


# --------------------------------------------------------------------------- #
# The flattened event
# --------------------------------------------------------------------------- #


class ResolvedEvent(BaseModel):
    """A ``news_event`` flattened with its linked entities resolved.

    Promoted top-level fields are the cross-category attributes the pipeline
    routes on; ``attributes`` retains the complete, raw attribute map (including
    category-specific keys such as ``headcount``/``job_title``/``location_data``
    and the *uncoerced* originals of the promoted fields).
    """

    model_config = ConfigDict(extra="forbid")

    # Identity
    event_id: str
    type: str = "news_event"

    # Promoted, cross-category attributes (tolerantly coerced; may be None).
    category: str | None = None
    summary: str | None = None
    article_sentence: str | None = None
    confidence: float | None = None
    found_at: datetime | None = None
    human_approved: bool | None = None
    amount: float | None = None

    # Source of truth: the full original ``attributes`` block.
    attributes: dict[str, Any] = Field(default_factory=dict)

    # Relationship target ids (present even when the entity did not resolve, so
    # the referential-integrity rule can distinguish "absent" from "dangling").
    company1_id: str | None = None
    company2_id: str | None = None
    source_article_id: str | None = None

    # Resolved entities (None if the id was absent or did not resolve).
    company1: Company | None = None
    company2: Company | None = None
    source_article: Article | None = None

    unresolved_references: list[str] = Field(default_factory=list)
    """Relationship ids that were declared but had no matching ``included`` entity."""

    # Provenance for tracing / idempotency.
    source_file: str | None = None
    source_line: int | None = None

    @field_validator("confidence", "amount", mode="before")
    @classmethod
    def _coerce_floats(cls, value: Any) -> float | None:
        return _to_float(value)

    @field_validator("found_at", mode="before")
    @classmethod
    def _coerce_found_at(cls, value: Any) -> datetime | None:
        return _to_datetime(value)

    @field_validator("human_approved", mode="before")
    @classmethod
    def _coerce_human_approved(cls, value: Any) -> bool | None:
        return _to_bool(value)


# --------------------------------------------------------------------------- #
# Verdicts — the single currency for both rules and LLM judges
# --------------------------------------------------------------------------- #


class CheckType(StrEnum):
    RULE = "rule"
    LLM = "llm"


class VerdictStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNCERTAIN = "uncertain"


class Verdict(BaseModel):
    """One check's outcome for one event.

    Rules and LLM judges emit the *same* type so storage, routing, and the trace
    log are uniform. LLM-only fields (``prompt_version``, ``model``, token/cost)
    are ``None`` for rule verdicts.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str
    check_name: str
    check_type: CheckType
    status: VerdictStatus
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] | None = None
    reason: str
    evidence_span: str | None = None

    # LLM provenance (null for rules).
    prompt_version: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None

    ts: datetime


# --------------------------------------------------------------------------- #
# Parse failures — structural problems that prevent building a ResolvedEvent
# --------------------------------------------------------------------------- #


class ParseError(BaseModel):
    """A line that could not be turned into one or more ``ResolvedEvent``s."""

    model_config = ConfigDict(extra="forbid")

    source_file: str | None
    source_line: int | None
    error_type: Literal["json_decode", "malformed_record"]
    reason: str
    excerpt: str | None = None
