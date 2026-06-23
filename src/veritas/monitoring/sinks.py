"""Metrics sinks: the protocol plus null and in-memory implementations.

``MetricsRuleSink`` bridges the existing rules-layer ``RuleMetricsSink`` (Phase 1)
to this unified sink, so the RuleEngine integrates with no contract change — it
already accepts a ``RuleMetricsSink``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from veritas.domain.models import VerdictStatus
from veritas.monitoring.events import (
    LLMExecution,
    MetricsSnapshot,
    OutcomeRecorded,
    ProviderCall,
    RuleExecution,
)
from veritas.rules.metrics import RuleMetric

# FinalStatus values, kept as literals to avoid importing the pipeline package.
_QUARANTINED = "quarantined"
_REVIEW = "review"
_CLEAN = "clean"


@runtime_checkable
class MetricsSink(Protocol):
    """Receives typed metric events. All methods are cheap and fire-and-forget."""

    def on_rule(self, event: RuleExecution) -> None: ...
    def on_llm(self, event: LLMExecution) -> None: ...
    def on_provider_call(self, event: ProviderCall) -> None: ...
    def on_outcome(self, event: OutcomeRecorded) -> None: ...


class NullMetricsSink:
    """Default no-op sink — keeps observability fully optional."""

    def on_rule(self, event: RuleExecution) -> None:
        return None

    def on_llm(self, event: LLMExecution) -> None:
        return None

    def on_provider_call(self, event: ProviderCall) -> None:
        return None

    def on_outcome(self, event: OutcomeRecorded) -> None:
        return None


class InMemoryMetricsSink:
    """Accumulates counters for tests and a live in-process dashboard."""

    def __init__(self) -> None:
        self.rule_executions = 0
        self.rule_failures = 0
        self.llm_executions = 0
        self.escalations = 0
        self.outcomes = 0
        self.clean = 0
        self.review = 0
        self.quarantine = 0
        self.provider_calls = 0
        self.provider_failures = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0

    def on_rule(self, event: RuleExecution) -> None:
        self.rule_executions += 1
        if event.verdict is VerdictStatus.FAIL:
            self.rule_failures += 1

    def on_llm(self, event: LLMExecution) -> None:
        self.llm_executions += 1
        self.input_tokens += event.input_tokens or 0
        self.output_tokens += event.output_tokens or 0
        self.cost_usd += event.cost_usd or 0.0

    def on_provider_call(self, event: ProviderCall) -> None:
        self.provider_calls += 1
        if not event.ok:
            self.provider_failures += 1

    def on_outcome(self, event: OutcomeRecorded) -> None:
        self.outcomes += 1
        if event.escalated:
            self.escalations += 1
        if event.final_status == _QUARANTINED:
            self.quarantine += 1
        elif event.final_status == _REVIEW:
            self.review += 1
        elif event.final_status == _CLEAN:
            self.clean += 1

    def snapshot(self) -> MetricsSnapshot:
        return MetricsSnapshot(
            rule_executions=self.rule_executions,
            rule_failures=self.rule_failures,
            llm_executions=self.llm_executions,
            escalations=self.escalations,
            outcomes=self.outcomes,
            clean=self.clean,
            review=self.review,
            quarantine=self.quarantine,
            provider_calls=self.provider_calls,
            provider_failures=self.provider_failures,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cost_usd=self.cost_usd,
        )


class MetricsRuleSink:
    """Adapts the rules-layer ``RuleMetricsSink`` to a unified ``MetricsSink``."""

    def __init__(self, sink: MetricsSink) -> None:
        self._sink = sink

    def record(self, metric: RuleMetric) -> None:
        self._sink.on_rule(
            RuleExecution(
                rule_name=metric.rule_name,
                verdict=metric.verdict,
                severity=metric.severity,
                latency_ms=metric.latency_ms,
            )
        )
