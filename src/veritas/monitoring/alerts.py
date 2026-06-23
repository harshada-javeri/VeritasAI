"""Alert policy and evaluation.

Operates on a ``MetricsSnapshot`` plus small monitoring-local inputs (a
``BudgetStatus`` and a list of regressed metric names) rather than importing
``llm_gateway`` or ``evals`` — keeping monitoring dependency-light and cycle-free.
The caller adapts a ``BudgetGuard`` / eval ``RegressionReport`` into these inputs.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from veritas.monitoring.events import MetricsSnapshot
from veritas.rules.metrics import MetricSeverity


class AlertKind(StrEnum):
    BUDGET_EXCEEDED = "budget_exceeded"
    EVALUATION_REGRESSION = "evaluation_regression"
    REVIEW_RATE_SPIKE = "review_rate_spike"
    QUARANTINE_RATE_SPIKE = "quarantine_rate_spike"
    PROVIDER_FAILURE_SPIKE = "provider_failure_spike"


class BudgetStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    spent: float
    limit: float


class Alert(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: AlertKind
    severity: MetricSeverity
    message: str
    value: float | None = None
    threshold: float | None = None


class AlertPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_samples: int = 20  # below this, rate-based alerts are suppressed (noise)
    review_rate_max: float = 0.50
    quarantine_rate_max: float = 0.40
    provider_failure_rate_max: float = 0.20


class AlertEvaluator:
    def __init__(self, policy: AlertPolicy | None = None) -> None:
        self._policy = policy if policy is not None else AlertPolicy()

    def evaluate(
        self,
        snapshot: MetricsSnapshot,
        *,
        budget: BudgetStatus | None = None,
        regressed_metrics: Sequence[str] = (),
    ) -> list[Alert]:
        alerts: list[Alert] = []
        policy = self._policy

        if budget is not None and budget.spent >= budget.limit:
            alerts.append(
                Alert(
                    kind=AlertKind.BUDGET_EXCEEDED,
                    severity=MetricSeverity.ERROR,
                    message=f"budget exhausted: spent ${budget.spent:.4f} of ${budget.limit:.2f}",
                    value=budget.spent,
                    threshold=budget.limit,
                )
            )

        if regressed_metrics:
            alerts.append(
                Alert(
                    kind=AlertKind.EVALUATION_REGRESSION,
                    severity=MetricSeverity.ERROR,
                    message=f"eval regression on metrics: {sorted(regressed_metrics)}",
                )
            )

        if snapshot.outcomes >= policy.min_samples:
            if snapshot.review_rate > policy.review_rate_max:
                alerts.append(
                    Alert(
                        kind=AlertKind.REVIEW_RATE_SPIKE,
                        severity=MetricSeverity.WARNING,
                        message=f"review rate {snapshot.review_rate:.2f} exceeds "
                        f"{policy.review_rate_max:.2f}",
                        value=snapshot.review_rate,
                        threshold=policy.review_rate_max,
                    )
                )
            if snapshot.quarantine_rate > policy.quarantine_rate_max:
                alerts.append(
                    Alert(
                        kind=AlertKind.QUARANTINE_RATE_SPIKE,
                        severity=MetricSeverity.WARNING,
                        message=f"quarantine rate {snapshot.quarantine_rate:.2f} exceeds "
                        f"{policy.quarantine_rate_max:.2f}",
                        value=snapshot.quarantine_rate,
                        threshold=policy.quarantine_rate_max,
                    )
                )

        if (
            snapshot.provider_calls >= policy.min_samples
            and snapshot.provider_failure_rate > policy.provider_failure_rate_max
        ):
            alerts.append(
                Alert(
                    kind=AlertKind.PROVIDER_FAILURE_SPIKE,
                    severity=MetricSeverity.ERROR,
                    message=f"provider failure rate {snapshot.provider_failure_rate:.2f} exceeds "
                    f"{policy.provider_failure_rate_max:.2f}",
                    value=snapshot.provider_failure_rate,
                    threshold=policy.provider_failure_rate_max,
                )
            )

        return alerts
