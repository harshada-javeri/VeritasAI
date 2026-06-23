"""Builds the Event Detail view-model from the three single-event reads."""

from __future__ import annotations

from veritas.dashboard.repositories.event_repository import EventRepository
from veritas.dashboard.repositories.rows import VerdictDTO
from veritas.dashboard.repositories.trace_repository import TraceRepository
from veritas.dashboard.repositories.verdict_repository import VerdictRepository
from veritas.dashboard.services import formatting as fmt
from veritas.dashboard.services.scoring import band_for_status
from veritas.dashboard.viewmodels.common import Band, MoneyVM
from veritas.dashboard.viewmodels.event_detail import (
    EventDetailVM,
    EventHeaderVM,
    TraceRowVM,
    VerdictRowVM,
)


class EventService:
    def __init__(
        self,
        events: EventRepository,
        verdicts: VerdictRepository,
        traces: TraceRepository,
    ) -> None:
        self._events = events
        self._verdicts = verdicts
        self._traces = traces

    def build(self, event_id: str) -> EventDetailVM:
        header_dto = self._events.get_header(event_id)
        if header_dto is None:
            return EventDetailVM(event_id=event_id, found=False)

        verdict_dtos = self._verdicts.list_for_event(event_id)
        trace_dtos = self._traces.list_for_event(event_id)
        total_cost = sum(v.cost_usd or 0.0 for v in verdict_dtos)

        header = EventHeaderVM(
            event_id=header_dto.event_id,
            category=header_dto.category,
            summary=header_dto.summary,
            found_at_display=fmt.dt(header_dto.found_at),
            company1_id=header_dto.company1_id,
            company2_id=header_dto.company2_id,
            status=header_dto.status,
            status_band=Band(
                severity=band_for_status(header_dto.status),
                reason=f"event is {header_dto.status}",
            ),
        )
        return EventDetailVM(
            event_id=event_id,
            found=True,
            header=header,
            verdicts=tuple(self._verdict_row(v) for v in verdict_dtos),
            trace=tuple(
                TraceRowVM(
                    stage=t.stage,
                    trace_id=t.trace_id,
                    payload_hash=t.payload_hash,
                    created_at_display=fmt.dt(t.created_at),
                )
                for t in trace_dtos
            ),
            cost_summary=MoneyVM(value_usd=total_cost, display=fmt.money(total_cost)),
        )

    @staticmethod
    def _verdict_row(v: VerdictDTO) -> VerdictRowVM:
        tokens_display = (
            f"{v.input_tokens}/{v.output_tokens}"
            if v.input_tokens is not None and v.output_tokens is not None
            else "—"
        )
        return VerdictRowVM(
            check_name=v.check_name,
            check_type=v.check_type,
            status=v.status,
            confidence_display=(fmt.pct(v.confidence) if v.confidence is not None else "—"),
            reason=v.reason,
            evidence_span=v.evidence_span,
            prompt_version=v.prompt_version or "—",
            model=v.model or "—",
            cost_display=(fmt.money(v.cost_usd) if v.cost_usd is not None else "—"),
            tokens_display=tokens_display,
            latency_display=fmt.latency_ms(v.latency_ms),
            ts_display=fmt.dt(v.ts),
            is_fail=v.status == "fail",
            is_uncertain=v.status == "uncertain",
        )
