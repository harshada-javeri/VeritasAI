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
    DecisionVM,
    EventDetailVM,
    EventHeaderVM,
    TraceRowVM,
    VerdictRowVM,
)

# Worst-wins precedence used to find the verdict that decided the final state.
_PRECEDENCE = {"fail": 2, "uncertain": 1, "review": 1, "pass": 0}


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
            decision=self._decision(header_dto.status, verdict_dtos),
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

    def _decision(self, status: str, verdicts: list[VerdictDTO]) -> DecisionVM:
        rules = [v for v in verdicts if v.check_type == "rule"]
        llms = [v for v in verdicts if v.check_type == "llm"]
        escalated = bool(llms)
        worst_rule = self._worst(rules)
        worst_llm = self._worst(llms)

        # The verdict that decided the outcome: the worst across the whole stack.
        key = self._worst(verdicts)
        if key is not None and key.status == "fail":
            rationale = (
                f"Quarantined by rule `{key.check_name}` — {key.reason}. "
                f"No LLM spend (the triage gate stops here)."
            )
        elif key is not None and key.status in {"uncertain", "review"}:
            owner = "LLM judge" if key.check_type == "llm" else "rule"
            rationale = (
                f"Routed to human review: {owner} `{key.check_name}` was uncertain"
                f"{f' ({fmt.pct(key.confidence)})' if key.confidence is not None else ''} — "
                f"a person owns this call."
            )
        else:
            rationale = "Clean: every rule and judge passed; safe to consume downstream."

        return DecisionVM(
            final_status=status,
            band=Band(severity=band_for_status(status), reason=f"event is {status}"),
            rationale=rationale,
            escalated=escalated,
            escalated_display=(
                "Yes — escalated to LLM judges" if escalated else "No — settled by rules at $0"
            ),
            rule_outcome=self._outcome_label(worst_rule, none="no rule verdicts"),
            llm_outcome=self._outcome_label(worst_llm, none="not escalated"),
            key_check=key.check_name if key else "—",
            key_confidence=(
                fmt.pct(key.confidence) if key and key.confidence is not None else "—"
            ),
            key_model=(key.model or "—") if key else "—",
            key_prompt_version=(key.prompt_version or "—") if key else "—",
            key_cost=(fmt.money(key.cost_usd) if key and key.cost_usd is not None else "—"),
            key_latency=fmt.latency_ms(key.latency_ms) if key else "—",
        )

    @staticmethod
    def _worst(verdicts: list[VerdictDTO]) -> VerdictDTO | None:
        return max(verdicts, key=lambda v: _PRECEDENCE.get(v.status, 0), default=None)

    @staticmethod
    def _outcome_label(v: VerdictDTO | None, *, none: str) -> str:
        if v is None:
            return none
        return f"{v.status} · {v.check_name}"

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
