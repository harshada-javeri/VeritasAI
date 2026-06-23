"""Tests for the evaluation framework: metrics, datasets, runner, regression, CLI."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from veritas.domain.models import CheckType, ResolvedEvent, Verdict, VerdictStatus
from veritas.evals import (
    EvalDataset,
    EvalExample,
    available_prompt_versions,
    detect_regression,
    evaluate_dataset,
    list_datasets,
    load_dataset,
    run_dataset,
    score,
)
from veritas.evals.cli import main as eval_main
from veritas.evals.runner import compare_prompts
from veritas.judges.replay import ReplayJudge

PASS = VerdictStatus.PASS
FAIL = VerdictStatus.FAIL
UNCERTAIN = VerdictStatus.UNCERTAIN
NOW = datetime(2026, 6, 22, tzinfo=UTC)


# --- metrics -------------------------------------------------------------- #


def test_score_perfect() -> None:
    pairs = [(PASS, PASS), (FAIL, FAIL), (UNCERTAIN, UNCERTAIN)]
    metrics = score(pairs)
    assert metrics.accuracy == 1.0
    assert metrics.macro_f1 == 1.0


def test_score_binary_precision_recall() -> None:
    # gold: 2 fail, 2 pass. Predicted: one false-positive fail, one missed fail.
    pairs = [(FAIL, FAIL), (FAIL, PASS), (PASS, FAIL), (PASS, PASS)]
    metrics = score(pairs)
    assert metrics.accuracy == 0.5
    fail_metrics = next(c for c in metrics.per_class if c.label == "fail")
    assert fail_metrics.precision == pytest.approx(0.5)  # 1 tp / (1 tp + 1 fp)
    assert fail_metrics.recall == pytest.approx(0.5)  # 1 tp / (1 tp + 1 fn)


def test_macro_ignores_absent_classes() -> None:
    # No 'uncertain' in gold -> it must not drag the macro average to 0.
    pairs = [(PASS, PASS), (FAIL, FAIL)]
    metrics = score(pairs)
    assert metrics.macro_f1 == 1.0


# --- datasets ------------------------------------------------------------- #


def test_shipped_datasets_present() -> None:
    names = list_datasets()
    assert {"semantic_accuracy_v1", "entity_resolution_v1", "source_credibility_v1"} <= set(names)


def test_load_dataset_and_check_name() -> None:
    dataset = load_dataset("semantic_accuracy_v1")
    assert dataset.check_name == "semantic_accuracy"
    assert len(dataset.examples) == 12
    assert all(isinstance(example.event, ResolvedEvent) for example in dataset.examples)


def test_semantic_accuracy_has_two_prompt_versions() -> None:
    assert available_prompt_versions("semantic_accuracy_v1") == ["v1", "v2"]


# --- runner --------------------------------------------------------------- #


def test_run_dataset_scores_against_gold() -> None:
    result = asyncio.run(run_dataset("semantic_accuracy_v1", "v1"))
    assert result.metrics.n == 12
    # v1 has two seeded errors -> 10/12 correct.
    assert result.metrics.accuracy == pytest.approx(10 / 12)
    assert len(result.mismatches) == 2
    # worst-first ordering by confidence
    confidences = [m.confidence or 0.0 for m in result.mismatches]
    assert confidences == sorted(confidences, reverse=True)


def test_v2_improves_over_v1_no_regression() -> None:
    comparison = asyncio.run(compare_prompts("semantic_accuracy_v1", "v1", "v2", 0.05))
    assert comparison.candidate.metrics.accuracy >= comparison.baseline.metrics.accuracy
    assert comparison.regression.regressed is False


# --- regression detection ------------------------------------------------- #


def test_detect_regression_fires_on_drop() -> None:
    baseline = score([(PASS, PASS), (FAIL, FAIL), (PASS, PASS), (FAIL, FAIL)])
    candidate = score([(PASS, PASS), (FAIL, PASS), (PASS, PASS), (FAIL, PASS)])  # misses both fails
    report = detect_regression(baseline, candidate, 0.05)
    assert report.regressed is True
    assert "accuracy" in report.regressed_metrics


def test_detect_regression_silent_within_threshold() -> None:
    metrics = score([(PASS, PASS), (FAIL, FAIL)])
    report = detect_regression(metrics, metrics, 0.05)
    assert report.regressed is False
    assert report.regressed_metrics == []


# --- in-memory end to end ------------------------------------------------- #


def _event(event_id: str) -> ResolvedEvent:
    return ResolvedEvent(event_id=event_id, category="launches", summary="s", article_sentence="x")


def _verdict(event_id: str, status: VerdictStatus) -> Verdict:
    return Verdict(
        event_id=event_id,
        check_name="semantic_accuracy",
        check_type=CheckType.LLM,
        status=status,
        confidence=0.8,
        reason="recorded",
        ts=NOW,
    )


def test_evaluate_dataset_with_in_memory_replay() -> None:
    dataset = EvalDataset(
        name="tmp_v1",
        check_name="semantic_accuracy",
        examples=[
            EvalExample(event=_event("a"), label=PASS),
            EvalExample(event=_event("b"), label=FAIL),
        ],
    )
    judge = ReplayJudge(
        "semantic_accuracy",
        {"a": _verdict("a", PASS), "b": _verdict("b", PASS)},  # 'b' wrong
    )
    result = asyncio.run(evaluate_dataset(dataset, judge, "v1"))
    assert result.metrics.accuracy == 0.5
    assert [m.event_id for m in result.mismatches] == ["b"]


# --- CLI ------------------------------------------------------------------ #


def test_cli_runs_all_datasets_and_succeeds(capsys: pytest.CaptureFixture[str]) -> None:
    code = eval_main([])
    out = capsys.readouterr().out
    assert code == 0  # seeded data has no regression
    assert "semantic_accuracy_v1" in out
    assert "worst failures" in out
    assert "regression" in out  # comparison shown for the 2-version dataset


def test_cli_compare_flags_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    argv = ["--dataset", "semantic_accuracy_v1", "--compare"]
    argv += ["--baseline", "v1", "--candidate", "v2"]
    code = eval_main(argv)
    assert code == 0
    assert "vs v2" in capsys.readouterr().out
