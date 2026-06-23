"""Text rendering of eval results, worst failures, and regression reports."""

from __future__ import annotations

from veritas.evals.metrics import Metrics
from veritas.evals.runner import ComparisonResult, EvalResult, RegressionReport


def _metrics_line(metrics: Metrics) -> str:
    return (
        f"acc={metrics.accuracy:.3f}  "
        f"P={metrics.macro_precision:.3f}  "
        f"R={metrics.macro_recall:.3f}  "
        f"F1={metrics.macro_f1:.3f}  (n={metrics.n})"
    )


def format_result(result: EvalResult, *, top: int = 5) -> str:
    lines = [
        f"## {result.dataset}  [{result.check_name} @ prompt {result.prompt_version}]",
        f"  macro: {_metrics_line(result.metrics)}",
        "  per-class:",
    ]
    for cls in result.metrics.per_class:
        lines.append(
            f"    {cls.label:<10} P={cls.precision:.3f} R={cls.recall:.3f} "
            f"F1={cls.f1:.3f} support={cls.support}"
        )
    shown = min(top, len(result.mismatches))
    lines.append(f"  worst failures ({shown} of {len(result.mismatches)}):")
    if not result.mismatches:
        lines.append("    (none — all predictions matched gold)")
    for mismatch in result.mismatches[:top]:
        conf = f"{mismatch.confidence:.2f}" if mismatch.confidence is not None else "n/a"
        lines.append(
            f"    [{mismatch.event_id}] gold={mismatch.gold.value} "
            f"pred={mismatch.predicted.value} conf={conf}"
        )
        lines.append(f"        {mismatch.summary or ''!r} -> {mismatch.reason}")
    return "\n".join(lines)


def format_regression(report: RegressionReport) -> str:
    status = "REGRESSION" if report.regressed else "OK"
    lines = [f"  regression (threshold {report.threshold:.3f}): {status}"]
    for metric, drop in report.drops.items():
        flag = "  <== drop exceeds threshold" if metric in report.regressed_metrics else ""
        # Positive drop = got worse; negative = improved.
        lines.append(f"    {metric:<16} delta={-drop:+.3f}{flag}")
    return "\n".join(lines)


def format_comparison(comparison: ComparisonResult, *, top: int = 5) -> str:
    return "\n".join(
        [
            f"## {comparison.dataset}: prompt {comparison.baseline.prompt_version} "
            f"vs {comparison.candidate.prompt_version}",
            f"  baseline  ({comparison.baseline.prompt_version}): "
            f"{_metrics_line(comparison.baseline.metrics)}",
            f"  candidate ({comparison.candidate.prompt_version}): "
            f"{_metrics_line(comparison.candidate.metrics)}",
            format_regression(comparison.regression),
            "",
            format_result(comparison.candidate, top=top),
        ]
    )
