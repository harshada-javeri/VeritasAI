"""Builds the AI Judge Performance view-model from the OFFLINE eval harness.

Every metric carries its ``n`` and an always-on small-sample warning at fixture
size. The live verdict-mix tile is descriptive only (no ground truth on live
traffic).
"""

from __future__ import annotations

from veritas.dashboard.repositories.eval_repository import EvalRepository
from veritas.dashboard.repositories.verdict_repository import VerdictRepository
from veritas.dashboard.services import formatting as fmt
from veritas.dashboard.viewmodels.common import Bucket, SeriesPoint
from veritas.dashboard.viewmodels.judge import (
    CheckMixVM,
    CheckScoreVM,
    ClassScoreVM,
    JudgePerformanceVM,
    MismatchVM,
    PromptCompareVM,
)
from veritas.evals import ComparisonResult, EvalResult

_SMALL_SAMPLE = 100
_MAX_FAILURES = 10
_DATA_NOTE = (
    "Offline eval over packaged fixtures — descriptive, not live accuracy. "
    "Sample sizes are small; treat every score with its n."
)


class JudgeService:
    def __init__(self, evals: EvalRepository, verdicts: VerdictRepository) -> None:
        self._evals = evals
        self._verdicts = verdicts

    def build(self) -> JudgePerformanceVM:
        datasets = self._evals.datasets()
        if not datasets:
            return JudgePerformanceVM(is_empty=True, data_note=_DATA_NOTE)

        results: list[EvalResult] = []
        for dataset in datasets:
            versions = self._evals.prompt_versions(dataset)
            if not versions:
                continue
            results.append(self._evals.scorecard(dataset, max(versions)))

        scorecards = tuple(self._scorecard(r) for r in results)
        worst = self._worst_failures(results)
        comparison = self._comparison(datasets)
        live_mix = self._live_mix()

        return JudgePerformanceVM(
            is_empty=False,
            available_datasets=tuple(datasets),
            scorecards=scorecards,
            comparison=comparison,
            worst_failures=worst,
            live_verdict_mix=live_mix,
            data_note=_DATA_NOTE,
        )

    @staticmethod
    def _scorecard(result: EvalResult) -> CheckScoreVM:
        metrics = result.metrics
        return CheckScoreVM(
            dataset=result.dataset,
            check_name=result.check_name,
            prompt_version=result.prompt_version,
            n=metrics.n,
            accuracy=metrics.accuracy,
            macro_precision=metrics.macro_precision,
            macro_recall=metrics.macro_recall,
            macro_f1=metrics.macro_f1,
            sample_warning=metrics.n < _SMALL_SAMPLE,
            per_class=tuple(
                ClassScoreVM(
                    label=c.label,
                    precision=c.precision,
                    recall=c.recall,
                    f1=c.f1,
                    support=c.support,
                )
                for c in metrics.per_class
            ),
        )

    @staticmethod
    def _worst_failures(results: list[EvalResult]) -> tuple[MismatchVM, ...]:
        mismatches = [m for r in results for m in r.mismatches]
        mismatches.sort(
            key=lambda m: m.confidence if m.confidence is not None else 0.0, reverse=True
        )
        return tuple(
            MismatchVM(
                event_id=m.event_id,
                category=m.category,
                gold=m.gold.value,
                predicted=m.predicted.value,
                confidence_display=(fmt.pct(m.confidence) if m.confidence is not None else "—"),
                reason=m.reason,
            )
            for m in mismatches[:_MAX_FAILURES]
        )

    def _comparison(self, datasets: list[str]) -> PromptCompareVM | None:
        for dataset in datasets:
            versions = self._evals.prompt_versions(dataset)
            if len(versions) >= 2:
                baseline, candidate = versions[-2], versions[-1]
                return self._compare(self._evals.compare(dataset, baseline, candidate))
        return None

    @staticmethod
    def _compare(result: ComparisonResult) -> PromptCompareVM:
        regression = result.regression
        if regression.regressed:
            recommendation = f"HOLD — regression on {sorted(regression.regressed_metrics)}"
        else:
            recommendation = (
                f"Safe to promote — no tracked metric dropped beyond {regression.threshold:.2f}"
            )
        return PromptCompareVM(
            dataset=result.dataset,
            baseline_version=result.baseline.prompt_version,
            candidate_version=result.candidate.prompt_version,
            regressed=regression.regressed,
            regressed_metrics=tuple(regression.regressed_metrics),
            drops=tuple(
                SeriesPoint(label=metric, value=drop) for metric, drop in regression.drops.items()
            ),
            threshold=regression.threshold,
            recommendation=recommendation,
        )

    def _live_mix(self) -> tuple[CheckMixVM, ...]:
        rows = self._verdicts.llm_verdict_mix()
        by_check: dict[str, list[tuple[str, int]]] = {}
        for row in rows:
            by_check.setdefault(row.check_name, []).append((row.verdict, row.count))
        mix: list[CheckMixVM] = []
        for check_name, pairs in sorted(by_check.items()):
            total = sum(count for _, count in pairs) or 1
            mix.append(
                CheckMixVM(
                    check_name=check_name,
                    buckets=tuple(
                        Bucket(label=verdict, count=count, rate=count / total)
                        for verdict, count in sorted(pairs)
                    ),
                )
            )
        return tuple(mix)
