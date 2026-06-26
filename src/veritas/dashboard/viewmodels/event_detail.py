"""View-models for the Event Detail drill-down (the object spine)."""

from __future__ import annotations

from veritas.dashboard.viewmodels.common import VM, Band, MoneyVM


class VerdictRowVM(VM):
    check_name: str
    check_type: str
    status: str
    confidence_display: str
    reason: str
    evidence_span: str | None
    prompt_version: str
    model: str
    cost_display: str
    tokens_display: str
    latency_display: str
    ts_display: str
    is_fail: bool
    is_uncertain: bool


class TraceRowVM(VM):
    stage: str
    trace_id: str
    payload_hash: str
    created_at_display: str


class EventHeaderVM(VM):
    event_id: str
    category: str | None
    summary: str | None
    found_at_display: str
    company1_id: str | None
    company2_id: str | None
    status: str
    status_band: Band


class DecisionVM(VM):
    """Why this event reached its final state — the debugging focal point.

    Everything here is derived from the verdict stack; it makes the routing
    decision obvious without forcing the reader to reconstruct it row by row.
    """

    final_status: str
    band: Band
    rationale: str
    escalated: bool
    escalated_display: str
    rule_outcome: str
    llm_outcome: str
    key_check: str
    key_confidence: str
    key_model: str
    key_prompt_version: str
    key_cost: str
    key_latency: str


class EventDetailVM(VM):
    event_id: str
    found: bool
    header: EventHeaderVM | None = None
    decision: DecisionVM | None = None
    verdicts: tuple[VerdictRowVM, ...] = ()
    trace: tuple[TraceRowVM, ...] = ()
    cost_summary: MoneyVM | None = None
