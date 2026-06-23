"""View-models for the AI Judge Performance workspace (offline eval)."""

from __future__ import annotations

from veritas.dashboard.viewmodels.common import VM, Bucket, SeriesPoint


class ClassScoreVM(VM):
    label: str
    precision: float
    recall: float
    f1: float
    support: int


class CheckScoreVM(VM):
    dataset: str
    check_name: str
    prompt_version: str
    n: int
    accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    sample_warning: bool
    per_class: tuple[ClassScoreVM, ...] = ()


class MismatchVM(VM):
    event_id: str
    category: str | None
    gold: str
    predicted: str
    confidence_display: str
    reason: str


class PromptCompareVM(VM):
    dataset: str
    baseline_version: str
    candidate_version: str
    regressed: bool
    regressed_metrics: tuple[str, ...]
    drops: tuple[SeriesPoint, ...]
    threshold: float
    recommendation: str


class CheckMixVM(VM):
    check_name: str
    buckets: tuple[Bucket, ...] = ()


class JudgePerformanceVM(VM):
    is_empty: bool
    available_datasets: tuple[str, ...] = ()
    scorecards: tuple[CheckScoreVM, ...] = ()
    comparison: PromptCompareVM | None = None
    worst_failures: tuple[MismatchVM, ...] = ()
    live_verdict_mix: tuple[CheckMixVM, ...] = ()
    data_note: str
