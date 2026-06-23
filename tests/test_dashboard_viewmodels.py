"""View-model contract tests: frozen, extra-forbid, and helper behaviour."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from veritas.dashboard.viewmodels.common import (
    Band,
    DistributionBin,
    DistributionVM,
    MetricVM,
    Sparkline,
)
from veritas.dashboard.viewmodels.cost import BudgetVM


def test_viewmodels_are_frozen() -> None:
    metric = MetricVM(label="x", value=1.0, display="1")
    with pytest.raises(ValidationError):
        metric.value = 2.0  # type: ignore[misc]


def test_viewmodels_forbid_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Band(severity="trusted", reason="ok", unexpected=1)  # type: ignore[call-arg]


def test_severity_is_constrained() -> None:
    with pytest.raises(ValidationError):
        Band(severity="purple", reason="nope")  # type: ignore[arg-type]


def test_sparkline_empty() -> None:
    assert Sparkline().is_empty
    assert not Sparkline(points=(1.0, 2.0), labels=("a", "b")).is_empty


def test_distribution_empty() -> None:
    assert DistributionVM(label="d").is_empty
    populated = DistributionVM(
        label="d", bins=(DistributionBin(lower=0.0, upper=0.1, count=3),), total=3
    )
    assert not populated.is_empty


def test_budget_vm_round_trips() -> None:
    band = Band(severity="caution", reason="80%")
    budget = BudgetVM(spent_usd=80.0, limit_usd=100.0, consumed_pct=0.8, display="…", band=band)
    assert budget.band.severity == "caution"
    assert budget.model_dump()["consumed_pct"] == 0.8
