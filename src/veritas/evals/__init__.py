"""Evaluation framework: measure judges against versioned labeled sets.

Replay-only (``ReplayJudge``) — evaluations never call a live model. Metrics are
precision / recall / F1 (macro) + accuracy; comparing two prompt versions yields
a regression report that fails the eval when a tracked metric drops too far.
"""

from veritas.evals.dataset import (
    EvalDataset,
    EvalExample,
    available_prompt_versions,
    build_replay_judge,
    check_name_for,
    list_datasets,
    load_dataset,
    load_predictions,
)
from veritas.evals.metrics import ClassMetrics, Metrics, score
from veritas.evals.runner import (
    ComparisonResult,
    EvalResult,
    Mismatch,
    RegressionReport,
    compare_prompts,
    detect_regression,
    evaluate_dataset,
    run_dataset,
)

__all__ = [
    "ClassMetrics",
    "ComparisonResult",
    "EvalDataset",
    "EvalExample",
    "EvalResult",
    "Metrics",
    "Mismatch",
    "RegressionReport",
    "available_prompt_versions",
    "build_replay_judge",
    "check_name_for",
    "compare_prompts",
    "detect_regression",
    "evaluate_dataset",
    "list_datasets",
    "load_dataset",
    "load_predictions",
    "run_dataset",
    "score",
]
