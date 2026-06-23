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


class QualityIntelligenceVM(VM):
    is_empty: bool
    rule_stats: tuple[RuleStatVM, ...] = ()
    categories: tuple[Bucket, ...] = ()
    failures_by_category: tuple[CategoryFailureVM, ...] = ()
    confidence_by_check: tuple[DistributionVM, ...] = ()
