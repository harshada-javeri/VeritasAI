"""Deterministic rules engine: the free, exact gate that runs on 100% of records."""

from veritas.rules.base import (
    ExpectedField,
    RecordStatus,
    Rule,
    RuleContext,
    rollup_status,
    rule_verdict,
)
from veritas.rules.engine import RuleEngine, RuleReport
from veritas.rules.metrics import (
    MetricSeverity,
    NullMetricsSink,
    RuleMetric,
    RuleMetricsSink,
    severity_for,
)
from veritas.rules.registry import RuleRegistry, default_context, default_registry

__all__ = [
    "ExpectedField",
    "MetricSeverity",
    "NullMetricsSink",
    "RecordStatus",
    "Rule",
    "RuleContext",
    "RuleEngine",
    "RuleMetric",
    "RuleMetricsSink",
    "RuleRegistry",
    "RuleReport",
    "default_context",
    "default_registry",
    "rollup_status",
    "rule_verdict",
    "severity_for",
]
