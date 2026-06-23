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


class EventDetailVM(VM):
    event_id: str
    found: bool
    header: EventHeaderVM | None = None
    verdicts: tuple[VerdictRowVM, ...] = ()
    trace: tuple[TraceRowVM, ...] = ()
    cost_summary: MoneyVM | None = None
