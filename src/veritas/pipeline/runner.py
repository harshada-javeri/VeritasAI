"""PipelineRunner: composes the lifecycle with bounded async concurrency.

Dataset → Parser → RuleEngine → RoutingDecision → EscalationRouter → LLMJudge →
RemediationProposal → Final Verdict. All collaborators are injected (DI), so the
same runner serves live judges and ReplayJudges (offline/deterministic). The
shared BudgetGuard is the only throttle — there is no scheduler.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from typing import TYPE_CHECKING

from veritas.domain.models import ParseError, ResolvedEvent, Verdict, VerdictStatus
from veritas.llm_gateway.budget import BudgetGuard
from veritas.monitoring.events import LLMExecution, OutcomeRecorded

if TYPE_CHECKING:
    from veritas.monitoring.logging import PipelineLogger
    from veritas.monitoring.sinks import MetricsSink
from veritas.pipeline.contracts import (
    EscalationRouter,
    EventOutcome,
    EventSnapshot,
    FinalStatus,
    RemediationProposal,
    Remediator,
    RouteAction,
    RoutingPolicy,
    VerdictSink,
)
from veritas.pipeline.contracts import (
    PipelineTraceSink as TraceSink,
)
from veritas.rules.base import RecordStatus, RuleContext
from veritas.rules.engine import RuleEngine, RuleReport

RecordOrError = ResolvedEvent | ParseError


def parse_error_outcome(error: ParseError) -> EventOutcome:
    """A structural parse failure terminates as QUARANTINED (no rules, no LLM)."""
    event_id = f"{error.source_file}:{error.source_line}"
    return EventOutcome(
        event_id=event_id,
        final_status=FinalStatus.QUARANTINED,
        parse_error=error,
        error=f"parse failure ({error.error_type}): {error.reason}",
    )


class PipelineRunner:
    def __init__(
        self,
        *,
        rule_engine: RuleEngine,
        rule_context: RuleContext,
        routing_policy: RoutingPolicy,
        escalation_router: EscalationRouter,
        remediator: Remediator,
        budget: BudgetGuard,
        llm_fail_min_confidence: float = 0.70,
        max_concurrency: int = 8,
        verdict_sink: VerdictSink | None = None,
        trace_sink: TraceSink | None = None,
        metrics: MetricsSink | None = None,
        logger: PipelineLogger | None = None,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        self._rule_engine = rule_engine
        self._ctx = rule_context
        self._policy = routing_policy
        self._router = escalation_router
        self._remediator = remediator
        self._budget = budget
        self._fail_conf = llm_fail_min_confidence
        self._max_concurrency = max_concurrency
        self._verdict_sink = verdict_sink
        self._trace_sink = trace_sink
        self._metrics = metrics
        self._logger = logger

    # --- single event ----------------------------------------------------- #

    async def run_event(self, event: ResolvedEvent) -> EventOutcome:
        report = self._rule_engine.evaluate(event, self._ctx)
        decision = self._policy.decide(event, report)

        llm_verdicts: list[Verdict] = []
        cost = 0.0
        budget_exhausted = False
        error: str | None = None

        if decision.action is RouteAction.ESCALATE:
            try:
                result = await self._router.route(event, decision)
                llm_verdicts = result.verdicts
                cost = result.cost_usd
                budget_exhausted = result.budget_exhausted
            except Exception as exc:
                error = f"escalation failed: {exc}"

        final_status = self._finalize(report, llm_verdicts, budget_exhausted, error)
        remediation = await self._maybe_remediate(event, report, llm_verdicts)

        outcome = EventOutcome(
            event_id=event.event_id,
            final_status=final_status,
            snapshot=EventSnapshot(
                event_id=event.event_id,
                category=event.category,
                summary=event.summary,
                found_at=event.found_at,
                company1_id=event.company1_id,
                company2_id=event.company2_id,
            ),
            rule_report=report,
            llm_verdicts=llm_verdicts,
            routing=decision,
            remediation=remediation,
            total_cost_usd=cost,
            prompt_versions={
                v.check_name: v.prompt_version for v in llm_verdicts if v.prompt_version
            },
            error=error,
        )
        await self._emit(outcome, report, llm_verdicts)
        self._observe(outcome)
        return outcome

    def _observe(self, outcome: EventOutcome) -> None:
        if self._metrics is not None:
            for verdict in outcome.llm_verdicts:
                self._metrics.on_llm(LLMExecution.from_verdict(verdict))
            escalated = (
                outcome.routing is not None and outcome.routing.action is RouteAction.ESCALATE
            )
            self._metrics.on_outcome(
                OutcomeRecorded(
                    event_id=outcome.event_id,
                    final_status=outcome.final_status.value,
                    escalated=escalated,
                    cost_usd=outcome.total_cost_usd,
                )
            )
        if self._logger is not None:
            self._logger.log(
                "event_finalized",
                event_id=outcome.event_id,
                status=outcome.final_status.value,
                cost_usd=outcome.total_cost_usd,
                llm_checks=len(outcome.llm_verdicts),
            )

    def _finalize(
        self,
        report: RuleReport,
        llm_verdicts: list[Verdict],
        budget_exhausted: bool,
        error: str | None,
    ) -> FinalStatus:
        if report.status is RecordStatus.QUARANTINED:
            return FinalStatus.QUARANTINED
        high_conf_fail = any(
            v.status is VerdictStatus.FAIL and (v.confidence or 0.0) >= self._fail_conf
            for v in llm_verdicts
        )
        if high_conf_fail:
            return FinalStatus.QUARANTINED
        if report.status is RecordStatus.REVIEW or budget_exhausted or error is not None:
            return FinalStatus.REVIEW
        if any(v.status is not VerdictStatus.PASS for v in llm_verdicts):
            return FinalStatus.REVIEW
        return FinalStatus.CLEAN

    async def _maybe_remediate(
        self, event: ResolvedEvent, report: RuleReport, llm_verdicts: list[Verdict]
    ) -> RemediationProposal | None:
        all_verdicts = [*report.verdicts, *llm_verdicts]
        if any(v.status is VerdictStatus.FAIL for v in all_verdicts):
            return await self._remediator.propose(event, all_verdicts)
        return None

    async def _emit(
        self, outcome: EventOutcome, report: RuleReport, llm_verdicts: list[Verdict]
    ) -> None:
        if self._verdict_sink is not None:
            await self._verdict_sink.upsert_verdicts([*report.verdicts, *llm_verdicts])
        if self._trace_sink is not None:
            await self._trace_sink.on_outcome(outcome)

    # --- stream with bounded concurrency ---------------------------------- #

    async def _dispatch(self, item: RecordOrError) -> EventOutcome:
        if isinstance(item, ParseError):
            outcome = parse_error_outcome(item)
            if self._trace_sink is not None:
                await self._trace_sink.on_outcome(outcome)
            self._observe(outcome)
            return outcome
        return await self.run_event(item)

    async def run(self, items: Iterable[RecordOrError]) -> AsyncIterator[EventOutcome]:
        """Process a stream with at most ``max_concurrency`` events in flight.

        Outcomes are yielded in completion order (events are independent). The
        window bounds both concurrency and the number of live tasks.
        """
        iterator = iter(items)
        pending: set[asyncio.Task[EventOutcome]] = set()

        def fill() -> None:
            while len(pending) < self._max_concurrency:
                try:
                    item = next(iterator)
                except StopIteration:
                    return
                pending.add(asyncio.create_task(self._dispatch(item)))

        fill()
        while pending:
            done, still_pending = await asyncio.wait(
                pending, return_when=asyncio.FIRST_COMPLETED
            )
            pending = still_pending
            for task in done:
                yield task.result()
            fill()
