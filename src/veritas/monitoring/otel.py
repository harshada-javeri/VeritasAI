"""OpenTelemetry metrics adapter — optional, with graceful fallback.

OpenTelemetry is NOT a dependency of VeritasAI. This sink imports it lazily via
``importlib`` (so MyPy never needs the stubs and nothing breaks when it is
absent). If OTel is unavailable the sink is inert (every method no-ops);
``try_create`` returns a ``NullMetricsSink`` instead, so callers get a working
``MetricsSink`` either way.
"""

from __future__ import annotations

import importlib
from typing import Any

from veritas.monitoring.events import LLMExecution, OutcomeRecorded, ProviderCall, RuleExecution
from veritas.monitoring.sinks import MetricsSink, NullMetricsSink


class OpenTelemetryMetricsSink:
    """Implements ``MetricsSink`` against an OTel meter, if one is available."""

    def __init__(self, meter: Any | None = None) -> None:
        if meter is None:
            try:
                otel_metrics = importlib.import_module("opentelemetry.metrics")
                meter = otel_metrics.get_meter("veritas")
            except ImportError:
                meter = None
        self._meter = meter
        self._counters: dict[str, Any] = {}

    @property
    def available(self) -> bool:
        return self._meter is not None

    def _counter(self, name: str) -> Any:
        assert self._meter is not None  # callers guard on availability first
        if name not in self._counters:
            self._counters[name] = self._meter.create_counter(name)
        return self._counters[name]

    def on_rule(self, event: RuleExecution) -> None:
        if self._meter is None:
            return
        self._counter("veritas.rule.executions").add(
            1, {"rule": event.rule_name, "verdict": event.verdict.value}
        )

    def on_llm(self, event: LLMExecution) -> None:
        if self._meter is None:
            return
        self._counter("veritas.llm.executions").add(
            1, {"model": event.model or "", "verdict": event.verdict.value}
        )
        if event.cost_usd:
            self._counter("veritas.llm.cost_usd").add(event.cost_usd, {"model": event.model or ""})

    def on_provider_call(self, event: ProviderCall) -> None:
        if self._meter is None:
            return
        self._counter("veritas.provider.calls").add(
            1, {"provider": event.provider, "ok": str(event.ok).lower()}
        )

    def on_outcome(self, event: OutcomeRecorded) -> None:
        if self._meter is None:
            return
        self._counter("veritas.events.outcomes").add(1, {"status": event.final_status})

    @classmethod
    def try_create(cls) -> MetricsSink:
        """Return an OTel sink if OpenTelemetry is installed, else a no-op sink."""
        sink = cls()
        return sink if sink.available else NullMetricsSink()
