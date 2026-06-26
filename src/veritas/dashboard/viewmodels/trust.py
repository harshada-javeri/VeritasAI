"""View-models for the Trust Center workspace."""

from __future__ import annotations

from veritas.dashboard.viewmodels.common import VM, Band, Bucket, DistributionVM, MetricVM


class ComponentVM(VM):
    """One transparent input to the composite index, with its weighted contribution."""

    name: str
    rate: float
    weight: float
    contribution: float
    display: str


class IndexVM(VM):
    value: float
    display: str
    components: tuple[ComponentVM, ...]
    formula_label: str
    band: Band


class DriverVM(VM):
    check_name: str
    verdict: str
    count: int
    share: float


class TrustCenterVM(VM):
    is_empty: bool
    status_composition: tuple[Bucket, ...] = ()
    data_quality_index: IndexVM | None = None
    duplicate: MetricVM
    integrity: MetricVM
    judge_confidence: DistributionVM
    drivers: tuple[DriverVM, ...] = ()
    banner: Band
    headline: str = ""  # one-line plain-English explanation under the hero score
