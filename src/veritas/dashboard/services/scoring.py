"""Composite-index definition and severity bands — one source of truth.

The Data Quality Index is a *transparent* weighted blend of three observable
rates, not a magic number: every component (rate, weight, contribution) is shown
in the view-model. Weights live here so Trust Center and any future consumer
agree on what "quality" means. Range is 0-100.
"""

from __future__ import annotations

from dataclasses import dataclass

from veritas.dashboard.viewmodels.common import Severity

# Known empirical rule baselines (from docs/data-quality-findings.md), drawn as
# static reference bands — constants, not history.
RULE_BASELINES: dict[str, float] = {
    "confidence_floor": 0.097,
    "referential_integrity": 0.024,
}

# Index weights (sum to 1.0). Documented and overridable; never hidden.
INDEX_WEIGHTS: dict[str, float] = {
    "clean_rate": 0.5,
    "integrity_pass_rate": 0.3,
    "duplicate_ok_rate": 0.2,
}


@dataclass(frozen=True, slots=True)
class IndexComponent:
    name: str
    rate: float
    weight: float

    @property
    def contribution(self) -> float:
        return self.rate * self.weight * 100.0


@dataclass(frozen=True, slots=True)
class IndexResult:
    value: float
    components: tuple[IndexComponent, ...]


def compute_index(
    *, clean_rate: float, integrity_pass_rate: float, duplicate_ok_rate: float
) -> IndexResult:
    """0-100 transparent composite. Each rate is in [0, 1]."""
    components = (
        IndexComponent("clean_rate", clean_rate, INDEX_WEIGHTS["clean_rate"]),
        IndexComponent(
            "integrity_pass_rate", integrity_pass_rate, INDEX_WEIGHTS["integrity_pass_rate"]
        ),
        IndexComponent(
            "duplicate_ok_rate", duplicate_ok_rate, INDEX_WEIGHTS["duplicate_ok_rate"]
        ),
    )
    value = sum(component.contribution for component in components)
    return IndexResult(value=value, components=components)


def band_for_index(value: float) -> Severity:
    if value >= 90.0:
        return "trusted"
    if value >= 75.0:
        return "caution"
    return "blocked"


def band_for_budget(consumed_pct: float) -> Severity:
    if consumed_pct >= 1.0:
        return "blocked"
    if consumed_pct >= 0.8:
        return "caution"
    return "trusted"


def band_for_status(status: str) -> Severity:
    mapping: dict[str, Severity] = {
        "clean": "trusted",
        "review": "caution",
        "quarantine": "blocked",
        "quarantined": "blocked",
    }
    return mapping.get(status.lower(), "caution")
