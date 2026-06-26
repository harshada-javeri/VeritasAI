"""View-models for the Data Quality Intelligence workspace."""

from __future__ import annotations

from veritas.dashboard.viewmodels.common import VM, Bucket, DistributionVM, Sparkline


class RuleStatVM(VM):
    check_name: str
    total: int
    fail: int
    review: int
    fail_rate: float
    fail_rate_display: str
    baseline_rate: float | None
    spark: Sparkline


class CategoryFailureVM(VM):
    category: str | None
    check_name: str
    count: int


class SourceRowVM(VM):
    """One source/vendor row — populated only when source metadata is ingested."""

    source: str
    trust_display: str
    failure_rate_display: str
    trend: str
    top_failing_rule: str


class SourceDriftVM(VM):
    """Source Drift Intelligence — the stakeholder's #1 operational signal.

    ``available`` is False in V1 because ``events_clean`` carries no source/vendor
    column; the card then states exactly what unlocks and the single condition that
    turns it on. No fabricated numbers are ever shown.
    """

    available: bool = False
    headline: str = ""
    unlocks: tuple[str, ...] = ()
    activation_note: str = ""
    rows: tuple[SourceRowVM, ...] = ()


class QualityIntelligenceVM(VM):
    is_empty: bool
    rule_stats: tuple[RuleStatVM, ...] = ()
    categories: tuple[Bucket, ...] = ()
    failures_by_category: tuple[CategoryFailureVM, ...] = ()
    confidence_by_check: tuple[DistributionVM, ...] = ()
    source_drift: SourceDriftVM = SourceDriftVM()
