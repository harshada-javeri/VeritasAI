"""Typed metric events and the aggregate snapshot.

Monitoring depends only on leaf modules (``domain``, ``rules.metrics``) so it can be
imported by the gateway, runner, and repositories without import cycles. In
particular ``OutcomeRecorded.final_status`` is a plain ``str`` (the FinalStatus
value) rather than importing the pipeline enum.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from veritas.domain.models import Verdict, VerdictStatus
from veritas.rules.metrics import MetricSeverity

_FROZEN = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())


class RuleExecution(BaseModel):
    model_config = _FROZEN

    rule_name: str
    verdict: VerdictStatus
    severity: MetricSeverity
    latency_ms: float


class LLMExecution(BaseModel):
    model_config = _FROZEN

    check_name: str
    model: str | None
    prompt_version: str | None
    verdict: VerdictStatus
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None

    @classmethod
    def from_verdict(cls, verdict: Verdict) -> LLMExecution:
        return cls(
            check_name=verdict.check_name,
            model=verdict.model,
            prompt_version=verdict.prompt_version,
            verdict=verdict.status,
            latency_ms=verdict.latency_ms,
            input_tokens=verdict.input_tokens,
            output_tokens=verdict.output_tokens,
            cost_usd=verdict.cost_usd,
        )


class ProviderCall(BaseModel):
    model_config = _FROZEN

    provider: str
    model: str
    ok: bool
    error_type: str | None = None


class OutcomeRecorded(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    final_status: str  # FinalStatus value ("clean" | "quarantined" | "review")
    escalated: bool
    cost_usd: float


class MetricsSnapshot(BaseModel):
    """A point-in-time aggregate, suitable for alerting and dashboards."""

    model_config = ConfigDict(extra="forbid")

    rule_executions: int = 0
    rule_failures: int = 0
    llm_executions: int = 0
    escalations: int = 0
    outcomes: int = 0
    clean: int = 0
    review: int = 0
    quarantine: int = 0
    provider_calls: int = 0
    provider_failures: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def review_rate(self) -> float:
        return self.review / self.outcomes if self.outcomes else 0.0

    @property
    def quarantine_rate(self) -> float:
        return self.quarantine / self.outcomes if self.outcomes else 0.0

    @property
    def provider_failure_rate(self) -> float:
        return self.provider_failures / self.provider_calls if self.provider_calls else 0.0
