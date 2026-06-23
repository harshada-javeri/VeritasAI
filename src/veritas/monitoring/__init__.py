"""Monitoring & observability: metrics, structured logging, OTel adapter, alerts.

Dependency-light by design (only ``domain`` + ``rules.metrics``) so the gateway,
runner, and repositories can emit without import cycles.
"""

from veritas.monitoring.alerts import (
    Alert,
    AlertEvaluator,
    AlertKind,
    AlertPolicy,
    BudgetStatus,
)
from veritas.monitoring.events import (
    LLMExecution,
    MetricsSnapshot,
    OutcomeRecorded,
    ProviderCall,
    RuleExecution,
)
from veritas.monitoring.logging import PipelineLogger
from veritas.monitoring.otel import OpenTelemetryMetricsSink
from veritas.monitoring.sinks import (
    InMemoryMetricsSink,
    MetricsRuleSink,
    MetricsSink,
    NullMetricsSink,
)

__all__ = [
    "Alert",
    "AlertEvaluator",
    "AlertKind",
    "AlertPolicy",
    "BudgetStatus",
    "InMemoryMetricsSink",
    "LLMExecution",
    "MetricsRuleSink",
    "MetricsSink",
    "MetricsSnapshot",
    "NullMetricsSink",
    "OpenTelemetryMetricsSink",
    "OutcomeRecorded",
    "PipelineLogger",
    "ProviderCall",
    "RuleExecution",
]
