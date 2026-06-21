"""The rule engine: run a set of rules over one event and roll up the result."""

from __future__ import annotations

import time
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from veritas.domain.models import ResolvedEvent, Verdict
from veritas.rules.base import RecordStatus, Rule, RuleContext, rollup_status
from veritas.rules.metrics import (
    NullMetricsSink,
    RuleMetric,
    RuleMetricsSink,
    severity_for,
)


class RuleReport(BaseModel):
    """All rule verdicts for one event plus the record-level rollup."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    status: RecordStatus
    verdicts: list[Verdict]


class RuleEngine:
    """Runs an ordered set of rules. Stateless except for any state a rule owns
    (e.g. the duplicate rule's seen-set), so one engine instance is one run."""

    def __init__(
        self,
        rules: Sequence[Rule],
        metrics: RuleMetricsSink | None = None,
    ) -> None:
        self._rules: tuple[Rule, ...] = tuple(rules)
        # Depends only on the Protocol; defaults to the no-op sink.
        self._metrics: RuleMetricsSink = metrics if metrics is not None else NullMetricsSink()

    @property
    def rules(self) -> tuple[Rule, ...]:
        return self._rules

    def evaluate(self, event: ResolvedEvent, ctx: RuleContext) -> RuleReport:
        verdicts: list[Verdict] = []
        for rule in self._rules:
            start = time.perf_counter()
            verdict = rule.evaluate(event, ctx)
            latency_ms = (time.perf_counter() - start) * 1000.0
            if verdict is not None:
                verdicts.append(verdict)
                self._metrics.record(
                    RuleMetric(
                        rule_name=rule.name,
                        verdict=verdict.status,
                        severity=severity_for(verdict.status),
                        latency_ms=latency_ms,
                    )
                )
        return RuleReport(
            event_id=event.event_id,
            status=rollup_status(verdicts),
            verdicts=verdicts,
        )
