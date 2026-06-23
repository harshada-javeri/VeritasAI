"""Typed row DTOs returned by repositories.

Frozen dataclasses, not ORM rows and not view-models. They carry exactly the
columns a GROUP-BY/lookup produces; services map them into view-models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class StatusCount:
    status: str
    count: int


@dataclass(frozen=True, slots=True)
class CheckVerdictCount:
    check_name: str
    verdict: str
    count: int


@dataclass(frozen=True, slots=True)
class CategoryCount:
    category: str | None
    count: int


@dataclass(frozen=True, slots=True)
class CategoryCheckCount:
    category: str | None
    check_name: str
    count: int


@dataclass(frozen=True, slots=True)
class DayCount:
    day: str
    count: int


@dataclass(frozen=True, slots=True)
class CheckDayVerdictCount:
    check_name: str
    day: str
    verdict: str
    count: int


@dataclass(frozen=True, slots=True)
class HistogramBin:
    """Bucket index 0..10 (10 == confidence exactly 1.0; merged into 9 by the service)."""

    bucket: int
    count: int


@dataclass(frozen=True, slots=True)
class CheckHistogramBin:
    check_name: str
    bucket: int
    count: int


@dataclass(frozen=True, slots=True)
class StageCount:
    stage: str
    count: int


# --- cost ----------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ModelCost:
    model: str
    count: int
    total_cost: float
    avg_cost: float


@dataclass(frozen=True, slots=True)
class CheckCost:
    check_name: str
    total_cost: float


@dataclass(frozen=True, slots=True)
class PromptCost:
    prompt_version: str
    total_cost: float
    total_input_tokens: int
    count: int


@dataclass(frozen=True, slots=True)
class DayCost:
    day: str
    total_cost: float


@dataclass(frozen=True, slots=True)
class TokenTotals:
    input_tokens: int
    output_tokens: int


# --- latency -------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ModelLatencies:
    """Raw latencies per model; the service computes percentiles (portable)."""

    model: str
    values: tuple[int, ...]


# --- event detail --------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class EventHeaderDTO:
    event_id: str
    category: str | None
    summary: str | None
    found_at: datetime | None
    company1_id: str | None
    company2_id: str | None
    status: str


@dataclass(frozen=True, slots=True)
class VerdictDTO:
    check_name: str
    check_type: str
    status: str
    confidence: float | None
    reason: str
    evidence_span: str | None
    prompt_version: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    latency_ms: int | None
    ts: datetime


@dataclass(frozen=True, slots=True)
class TraceDTO:
    stage: str
    trace_id: str
    payload_hash: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class StatusListItem:
    """A row of the review/quarantine viewer (status filter + optional confidence sort)."""

    event_id: str
    category: str | None
    summary: str | None
    found_at: datetime | None
    status: str
    min_llm_confidence: float | None
