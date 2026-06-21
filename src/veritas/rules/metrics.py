"""Rule metrics hook — interface only.

A lightweight, dependency-free seam for observing rule execution. The engine
emits one :class:`RuleMetric` per produced verdict through a
:class:`RuleMetricsSink`; the default :class:`NullMetricsSink` does nothing.

Deliberately decoupled: this module imports no telemetry backend (no
OpenTelemetry, no Prometheus). A real sink — OTel exporter, StatsD, a DB writer —
is supplied later by implementing the Protocol, with zero change to the engine.
``RuleMetric`` is a frozen ``slots`` dataclass, not a Pydantic model, because it
is emitted on a hot path (one per rule per record, millions of times).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from veritas.domain.models import VerdictStatus


class MetricSeverity(StrEnum):
    """Severity ladder derived from the verdict, for alerting/routing."""

    INFO = "info"  # pass
    WARNING = "warning"  # uncertain -> review
    ERROR = "error"  # fail -> quarantine


_SEVERITY_BY_VERDICT: dict[VerdictStatus, MetricSeverity] = {
    VerdictStatus.PASS: MetricSeverity.INFO,
    VerdictStatus.UNCERTAIN: MetricSeverity.WARNING,
    VerdictStatus.FAIL: MetricSeverity.ERROR,
}


def severity_for(verdict: VerdictStatus) -> MetricSeverity:
    """Map a verdict status to its metric severity."""
    return _SEVERITY_BY_VERDICT[verdict]


@dataclass(frozen=True, slots=True)
class RuleMetric:
    """A single rule-execution measurement."""

    rule_name: str
    verdict: VerdictStatus
    severity: MetricSeverity
    latency_ms: float


@runtime_checkable
class RuleMetricsSink(Protocol):
    """Where rule metrics go. Implement this to wire in a real backend."""

    def record(self, metric: RuleMetric) -> None: ...


class NullMetricsSink:
    """Default no-op sink: keeps the engine fully decoupled from any backend."""

    def record(self, metric: RuleMetric) -> None:
        return None
