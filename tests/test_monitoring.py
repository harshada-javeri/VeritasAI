"""Tests for monitoring: metrics sinks, logging, OTel fallback, alerts, integration."""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime

from veritas.domain.models import (
    Article,
    CheckType,
    Company,
    ResolvedEvent,
    Verdict,
    VerdictStatus,
)
from veritas.judges.replay import ReplayJudge
from veritas.llm_gateway import (
    BudgetGuard,
    LLMGateway,
    LLMRequest,
    PriceRate,
    PricingTable,
    ProviderResult,
)
from veritas.llm_gateway.errors import PermanentLLMError
from veritas.monitoring import (
    Alert,
    AlertEvaluator,
    AlertKind,
    AlertPolicy,
    BudgetStatus,
    InMemoryMetricsSink,
    LLMExecution,
    MetricsRuleSink,
    MetricsSink,
    MetricsSnapshot,
    NullMetricsSink,
    OpenTelemetryMetricsSink,
    OutcomeRecorded,
    PipelineLogger,
    ProviderCall,
    RuleExecution,
)
from veritas.pipeline import (
    CheckJudges,
    DefaultRoutingPolicy,
    HeuristicRemediator,
    PipelineRunner,
    TieredEscalationRouter,
)
from veritas.rules.engine import RuleEngine
from veritas.rules.metrics import MetricSeverity, RuleMetric
from veritas.rules.registry import default_context, default_registry

NOW = datetime(2026, 6, 22, tzinfo=UTC)
HAIKU = "claude-haiku-4-5-20251001"
CLEAN_UUID = "11111111-1111-1111-1111-111111111111"


def _rule(
    verdict: VerdictStatus = VerdictStatus.PASS,
    severity: MetricSeverity = MetricSeverity.INFO,
) -> RuleExecution:
    return RuleExecution(rule_name="r", verdict=verdict, severity=severity, latency_ms=0.0)


def _outcome(status: str, *, escalated: bool = False) -> OutcomeRecorded:
    return OutcomeRecorded(event_id="e", final_status=status, escalated=escalated, cost_usd=0.0)


# --- in-memory metrics sink ---------------------------------------------- #


def test_in_memory_sink_accumulates() -> None:
    sink = InMemoryMetricsSink()
    sink.on_rule(_rule(VerdictStatus.FAIL, MetricSeverity.ERROR))
    sink.on_llm(
        LLMExecution(
            check_name="semantic_accuracy",
            model=HAIKU,
            prompt_version="v1",
            verdict=VerdictStatus.PASS,
            latency_ms=42,
            input_tokens=100,
            output_tokens=20,
            cost_usd=0.001,
        )
    )
    sink.on_provider_call(ProviderCall(provider="anthropic", model=HAIKU, ok=False, error_type="X"))
    sink.on_outcome(_outcome("review", escalated=True))
    snap = sink.snapshot()
    assert snap.rule_executions == 1 and snap.rule_failures == 1
    assert snap.llm_executions == 1 and snap.input_tokens == 100 and snap.cost_usd == 0.001
    assert snap.provider_calls == 1 and snap.provider_failures == 1
    assert snap.outcomes == 1 and snap.review == 1 and snap.escalations == 1


def test_null_sink_is_inert() -> None:
    sink = NullMetricsSink()
    sink.on_rule(_rule())
    sink.on_outcome(_outcome("clean"))
    assert isinstance(sink, MetricsSink)


def test_metrics_rule_sink_adapts_rule_metric() -> None:
    sink = InMemoryMetricsSink()
    adapter = MetricsRuleSink(sink)
    adapter.record(
        RuleMetric(
            rule_name="confidence_floor",
            verdict=VerdictStatus.FAIL,
            severity=MetricSeverity.ERROR,
            latency_ms=0.05,
        )
    )
    assert sink.snapshot().rule_executions == 1
    assert sink.snapshot().rule_failures == 1


# --- structured logging --------------------------------------------------- #


def test_pipeline_logger_emits_structured_json() -> None:
    lines: list[str] = []
    logger = PipelineLogger(emit=lines.append, clock=lambda: "2026-06-22T00:00:00Z")
    logger.log("event_finalized", event_id="e1", status="clean", cost_usd=0.0)
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event"] == "event_finalized"
    assert payload["event_id"] == "e1"
    assert payload["status"] == "clean"
    assert payload["ts"] == "2026-06-22T00:00:00Z"


# --- OpenTelemetry fallback ----------------------------------------------- #


def test_otel_sink_falls_back_gracefully() -> None:
    # OpenTelemetry is not installed -> the sink is inert and try_create yields a no-op.
    sink = OpenTelemetryMetricsSink()
    assert sink.available is False
    # calling methods must not raise even when unavailable
    sink.on_outcome(_outcome("clean"))
    assert isinstance(OpenTelemetryMetricsSink.try_create(), MetricsSink)


# --- alerts --------------------------------------------------------------- #


def test_alert_budget_exceeded() -> None:
    budget = BudgetStatus(spent=10.0, limit=10.0)
    alerts = AlertEvaluator().evaluate(MetricsSnapshot(), budget=budget)
    assert [a.kind for a in alerts] == [AlertKind.BUDGET_EXCEEDED]


def test_alert_evaluation_regression() -> None:
    alerts = AlertEvaluator().evaluate(MetricsSnapshot(), regressed_metrics=["accuracy"])
    assert any(a.kind is AlertKind.EVALUATION_REGRESSION for a in alerts)


def test_alert_review_and_quarantine_spikes() -> None:
    snap = MetricsSnapshot(outcomes=100, review=60, quarantine=50)
    kinds = {a.kind for a in AlertEvaluator().evaluate(snap)}
    assert AlertKind.REVIEW_RATE_SPIKE in kinds
    assert AlertKind.QUARANTINE_RATE_SPIKE in kinds


def test_alert_provider_failure_spike() -> None:
    snap = MetricsSnapshot(provider_calls=50, provider_failures=20)
    kinds = {a.kind for a in AlertEvaluator().evaluate(snap)}
    assert AlertKind.PROVIDER_FAILURE_SPIKE in kinds


def test_alert_suppressed_below_min_samples() -> None:
    # 100% review but only 3 samples -> below min_samples, no rate alert
    snap = MetricsSnapshot(outcomes=3, review=3)
    assert AlertEvaluator(AlertPolicy(min_samples=20)).evaluate(snap) == []


def test_alert_healthy_is_silent() -> None:
    snap = MetricsSnapshot(outcomes=100, clean=95, review=3, quarantine=2)
    assert AlertEvaluator().evaluate(snap) == []


# --- gateway provider metrics --------------------------------------------- #


class _FakeClient:
    provider = "anthropic"

    def __init__(self, *, fail: bool) -> None:
        self._fail = fail

    async def complete(self, request: LLMRequest) -> ProviderResult:
        if self._fail:
            raise PermanentLLMError("boom")
        return ProviderResult(
            content={"verdict": "pass"}, model=request.model, input_tokens=1, output_tokens=1
        )


def _req() -> LLMRequest:
    return LLMRequest(model=HAIKU, prompt="hi", response_schema={"type": "object"})


def test_gateway_records_provider_success_and_failure() -> None:
    pricing = PricingTable({HAIKU: PriceRate(1.0, 5.0)})

    async def scenario() -> tuple[int, int]:
        ok_sink = InMemoryMetricsSink()
        gw_ok = LLMGateway(
            {"anthropic": _FakeClient(fail=False)},
            pinned_models={HAIKU},
            budget=BudgetGuard(100.0),
            pricing=pricing,
            metrics=ok_sink,
        )
        await gw_ok.complete(_req())

        fail_sink = InMemoryMetricsSink()
        gw_fail = LLMGateway(
            {"anthropic": _FakeClient(fail=True)},
            pinned_models={HAIKU},
            budget=BudgetGuard(100.0),
            pricing=pricing,
            metrics=fail_sink,
        )
        with contextlib.suppress(PermanentLLMError):
            await gw_fail.complete(_req())
        return ok_sink.provider_failures, fail_sink.provider_failures

    ok_failures, fail_failures = asyncio.run(scenario())
    assert ok_failures == 0
    assert fail_failures == 1


# --- full pipeline observability integration ------------------------------ #


def _clean_event() -> ResolvedEvent:
    return ResolvedEvent(
        event_id=CLEAN_UUID,
        category="launches",
        confidence=0.8,
        found_at=datetime(2024, 1, 1, tzinfo=UTC),
        summary="Acme launches Widget",
        article_sentence="Acme launched Widget.",
        attributes={"product": "Widget"},
        company1_id="c1",
        company1=Company(id="c1", name="Acme"),
        source_article_id="a1",
        source_article=Article(id="a1"),
    )


def test_pipeline_emits_metrics_and_logs() -> None:
    sink = InMemoryMetricsSink()
    lines: list[str] = []
    logger = PipelineLogger(emit=lines.append)
    recorded = Verdict(
        event_id=CLEAN_UUID,
        check_name="semantic_accuracy",
        check_type=CheckType.LLM,
        status=VerdictStatus.PASS,
        confidence=0.95,
        reason="ok",
        prompt_version="v1",
        model=HAIKU,
        cost_usd=0.0,
        ts=NOW,
    )
    judges = {
        "semantic_accuracy": CheckJudges(
            primary=ReplayJudge("semantic_accuracy", {CLEAN_UUID: recorded})
        )
    }
    budget = BudgetGuard(100.0)
    runner = PipelineRunner(
        rule_engine=RuleEngine(default_registry().rules(), metrics=MetricsRuleSink(sink)),
        rule_context=default_context(NOW),
        routing_policy=DefaultRoutingPolicy(clean_sample_rate=1.0),
        escalation_router=TieredEscalationRouter(judges, budget),
        remediator=HeuristicRemediator(),
        budget=budget,
        metrics=sink,
        logger=logger,
    )
    asyncio.run(runner.run_event(_clean_event()))

    snap = sink.snapshot()
    assert snap.rule_executions == 8  # all eight deterministic rules emitted
    assert snap.llm_executions == 1
    assert snap.outcomes == 1 and snap.clean == 1 and snap.escalations == 1
    events = [json.loads(line) for line in lines]
    finalized = [e for e in events if e["event"] == "event_finalized"]
    assert len(finalized) == 1 and finalized[0]["status"] == "clean"


def test_alert_evaluator_consumes_pipeline_snapshot() -> None:
    # Drive a snapshot through the pipeline, then alert on it end to end.
    sink = InMemoryMetricsSink()
    for _ in range(30):
        sink.on_outcome(_outcome("quarantined"))
    alerts: list[Alert] = AlertEvaluator().evaluate(sink.snapshot())
    assert any(a.kind is AlertKind.QUARANTINE_RATE_SPIKE for a in alerts)
