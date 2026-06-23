"""Run a judge over a labeled dataset, score it, and compare prompt versions.

Everything here is replay-backed (``ReplayJudge``); no live model is ever called.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from veritas.domain.models import VerdictStatus
from veritas.evals.dataset import EvalDataset, build_replay_judge, load_dataset
from veritas.evals.metrics import Metrics, score
from veritas.judges.protocol import LLMJudge


class Mismatch(BaseModel):
    """A prediction that disagreed with the gold label."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    category: str | None
    summary: str | None
    gold: VerdictStatus
    predicted: VerdictStatus
    confidence: float | None
    reason: str


class EvalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: str
    check_name: str
    prompt_version: str
    metrics: Metrics
    mismatches: list[Mismatch]  # sorted worst-first (highest-confidence errors)


class RegressionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threshold: float
    drops: dict[str, float]  # baseline - candidate, per tracked metric
    regressed: bool
    regressed_metrics: list[str]


class ComparisonResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: str
    baseline: EvalResult
    candidate: EvalResult
    regression: RegressionReport


async def evaluate_dataset(
    dataset: EvalDataset, judge: LLMJudge, prompt_version: str
) -> EvalResult:
    pairs: list[tuple[VerdictStatus, VerdictStatus]] = []
    mismatches: list[Mismatch] = []
    for example in dataset.examples:
        verdict = await judge.evaluate(example.event)
        pairs.append((example.label, verdict.status))
        if verdict.status != example.label:
            mismatches.append(
                Mismatch(
                    event_id=example.event.event_id,
                    category=example.event.category,
                    summary=example.event.summary,
                    gold=example.label,
                    predicted=verdict.status,
                    confidence=verdict.confidence,
                    reason=verdict.reason,
                )
            )
    # Worst first: most confident mistakes are the most important to read.
    mismatches.sort(key=lambda m: m.confidence if m.confidence is not None else 0.0, reverse=True)
    return EvalResult(
        dataset=dataset.name,
        check_name=dataset.check_name,
        prompt_version=prompt_version,
        metrics=score(pairs),
        mismatches=mismatches,
    )


async def run_dataset(name: str, prompt_version: str) -> EvalResult:
    """Load a dataset by name and evaluate the recorded predictions for a prompt version."""
    dataset = load_dataset(name)
    judge = build_replay_judge(name, prompt_version)
    return await evaluate_dataset(dataset, judge, prompt_version)


def detect_regression(
    baseline: Metrics, candidate: Metrics, threshold: float
) -> RegressionReport:
    base = baseline.tracked()
    cand = candidate.tracked()
    drops = {metric: base[metric] - cand[metric] for metric in base}
    regressed_metrics = [metric for metric, drop in drops.items() if drop > threshold]
    return RegressionReport(
        threshold=threshold,
        drops=drops,
        regressed=bool(regressed_metrics),
        regressed_metrics=regressed_metrics,
    )


async def compare_prompts(
    name: str, baseline_version: str, candidate_version: str, threshold: float
) -> ComparisonResult:
    baseline = await run_dataset(name, baseline_version)
    candidate = await run_dataset(name, candidate_version)
    regression = detect_regression(baseline.metrics, candidate.metrics, threshold)
    return ComparisonResult(
        dataset=name, baseline=baseline, candidate=candidate, regression=regression
    )
