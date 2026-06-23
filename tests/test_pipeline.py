"""Tests for the pipeline: routing, tiered escalation, remediation, runner finalize."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import UTC, datetime

from veritas.domain.models import (
    Article,
    CheckType,
    Company,
    ParseError,
    ResolvedEvent,
    Verdict,
    VerdictStatus,
)
from veritas.judges.replay import ReplayJudge
from veritas.llm_gateway.budget import BudgetGuard
from veritas.pipeline import (
    CheckJudges,
    DefaultRoutingPolicy,
    EscalationResult,
    EventOutcome,
    FinalStatus,
    HeuristicRemediator,
    PipelineRunner,
    RemediationAction,
    RouteAction,
    TieredEscalationRouter,
)
from veritas.rules.base import RuleContext
from veritas.rules.engine import RuleEngine
from veritas.rules.registry import default_context, default_registry

NOW = datetime(2026, 6, 22, tzinfo=UTC)
CLEAN_ID = "11111111-1111-1111-1111-111111111111"
QUARANTINE_ID = "22222222-2222-2222-2222-222222222222"
REVIEW_ID = "33333333-3333-3333-3333-333333333333"


def ctx() -> RuleContext:
    return default_context(NOW)


def engine() -> RuleEngine:
    return default_registry().build_engine()


def _event(event_id: str, *, category: str = "launches", confidence: float = 0.8) -> ResolvedEvent:
    return ResolvedEvent(
        event_id=event_id,
        category=category,
        confidence=confidence,
        found_at=datetime(2024, 1, 1, tzinfo=UTC),
        article_sentence="Acme launched Widget.",
        summary="Acme launches Widget",
        attributes={"product": "Widget"},
        company1_id="c1",
        company1=Company(id="c1", name="Acme"),
        company2_id="c2",
        source_article_id="a1",
        source_article=Article(id="a1", title="t", body="b", url="https://x.example/y"),
    )


def clean_event() -> ResolvedEvent:
    return _event(CLEAN_ID)


def quarantine_event() -> ResolvedEvent:
    return _event(QUARANTINE_ID, confidence=0.0)  # confidence_floor -> QUARANTINED


def review_event() -> ResolvedEvent:
    return _event(REVIEW_ID, category="frobnicates")  # novel category -> REVIEW


def _llm_verdict(event_id: str, status: VerdictStatus, conf: float, *, model: str) -> Verdict:
    return Verdict(
        event_id=event_id,
        check_name="semantic_accuracy",
        check_type=CheckType.LLM,
        status=status,
        confidence=conf,
        reason="recorded",
        prompt_version="v1",
        model=model,
        cost_usd=0.0,
        ts=NOW,
    )


HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"


def _recordings(
    event_id: str, status: VerdictStatus, conf: float, model: str
) -> dict[str, Verdict]:
    return {event_id: _llm_verdict(event_id, status, conf, model=model)}


# --- routing policy ------------------------------------------------------- #


def test_quarantine_routes_to_quarantine() -> None:
    report = engine().evaluate(quarantine_event(), ctx())
    decision = DefaultRoutingPolicy().decide(quarantine_event(), report)
    assert decision.action is RouteAction.QUARANTINE
    assert decision.checks == ()


def test_review_routes_to_escalate() -> None:
    report = engine().evaluate(review_event(), ctx())
    decision = DefaultRoutingPolicy().decide(review_event(), report)
    assert decision.action is RouteAction.ESCALATE
    assert decision.checks == ("semantic_accuracy",)


def test_clean_not_sampled_is_accepted() -> None:
    report = engine().evaluate(clean_event(), ctx())
    decision = DefaultRoutingPolicy(clean_sample_rate=0.0).decide(clean_event(), report)
    assert decision.action is RouteAction.ACCEPT


def test_clean_sampled_is_escalated() -> None:
    report = engine().evaluate(clean_event(), ctx())
    decision = DefaultRoutingPolicy(clean_sample_rate=1.0).decide(clean_event(), report)
    assert decision.action is RouteAction.ESCALATE
    assert decision.sampled is True


def test_sampling_is_deterministic() -> None:
    policy = DefaultRoutingPolicy(clean_sample_rate=0.5)
    report = engine().evaluate(clean_event(), ctx())
    first = policy.decide(clean_event(), report).action
    second = policy.decide(clean_event(), report).action
    assert first is second


# --- escalation router ---------------------------------------------------- #


def _route(
    judges: dict[str, CheckJudges], budget: BudgetGuard, event: ResolvedEvent
) -> EscalationResult:
    router = TieredEscalationRouter(judges, budget)
    decision = DefaultRoutingPolicy(clean_sample_rate=1.0).decide(
        event, engine().evaluate(event, ctx())
    )
    return asyncio.run(router.route(event, decision))


def test_uncertain_primary_escalates_to_secondary() -> None:
    event = review_event()
    judges = {
        "semantic_accuracy": CheckJudges(
            primary=ReplayJudge(
                "semantic_accuracy",
                _recordings(event.event_id, VerdictStatus.UNCERTAIN, 0.5, HAIKU),
            ),
            escalation=ReplayJudge(
                "semantic_accuracy",
                _recordings(event.event_id, VerdictStatus.FAIL, 0.88, SONNET),
            ),
        )
    }
    result = _route(judges, BudgetGuard(100.0), event)
    assert result.escalated_checks == ("semantic_accuracy",)
    assert len(result.verdicts) == 1
    assert result.verdicts[0].status is VerdictStatus.FAIL
    assert result.verdicts[0].model == SONNET  # authoritative = escalated tier


def test_confident_primary_does_not_escalate() -> None:
    event = review_event()
    judges = {
        "semantic_accuracy": CheckJudges(
            primary=ReplayJudge(
                "semantic_accuracy",
                _recordings(event.event_id, VerdictStatus.PASS, 0.95, HAIKU),
            ),
            escalation=ReplayJudge("semantic_accuracy", {}),  # would KeyError if called
        )
    }
    result = _route(judges, BudgetGuard(100.0), event)
    assert result.escalated_checks == ()
    assert result.verdicts[0].model == HAIKU


def test_exhausted_budget_degrades() -> None:
    event = review_event()
    budget = BudgetGuard(1.0)
    budget.record(1.0)  # exhaust
    judges = {
        "semantic_accuracy": CheckJudges(
            primary=ReplayJudge("semantic_accuracy", {}),  # never reached
        )
    }
    result = _route(judges, budget, event)
    assert result.budget_exhausted is True
    assert result.verdicts == []


# --- remediation ---------------------------------------------------------- #


def test_remediation_proposes_for_semantic_fail() -> None:
    verdicts = [_llm_verdict(CLEAN_ID, VerdictStatus.FAIL, 0.9, model=SONNET)]
    proposal = asyncio.run(HeuristicRemediator().propose(clean_event(), verdicts))
    assert proposal.action is RemediationAction.CORRECT_CATEGORY
    assert proposal.target_field == "category"
    assert proposal.auto_applicable is False


def test_remediation_none_when_no_failures() -> None:
    verdicts = [_llm_verdict(CLEAN_ID, VerdictStatus.PASS, 0.9, model=HAIKU)]
    proposal = asyncio.run(HeuristicRemediator().propose(clean_event(), verdicts))
    assert proposal.action is RemediationAction.NONE


# --- runner end to end ---------------------------------------------------- #


def _runner(
    judges: dict[str, CheckJudges],
    *,
    sample_rate: float,
    budget: BudgetGuard | None = None,
) -> PipelineRunner:
    guard = budget if budget is not None else BudgetGuard(100.0)
    return PipelineRunner(
        rule_engine=engine(),
        rule_context=ctx(),
        routing_policy=DefaultRoutingPolicy(clean_sample_rate=sample_rate),
        escalation_router=TieredEscalationRouter(judges, guard),
        remediator=HeuristicRemediator(),
        budget=guard,
        llm_fail_min_confidence=0.70,
        max_concurrency=4,
    )


def _judges_for(event_id: str, status: VerdictStatus, conf: float) -> dict[str, CheckJudges]:
    return {
        "semantic_accuracy": CheckJudges(
            primary=ReplayJudge(
                "semantic_accuracy", {event_id: _llm_verdict(event_id, status, conf, model=HAIKU)}
            )
        )
    }


def test_runner_clean_pass() -> None:
    judges = _judges_for(CLEAN_ID, VerdictStatus.PASS, 0.95)
    outcome = asyncio.run(_runner(judges, sample_rate=1.0).run_event(clean_event()))
    assert outcome.final_status is FinalStatus.CLEAN
    assert len(outcome.llm_verdicts) == 1
    assert outcome.prompt_versions == {"semantic_accuracy": "v1"}
    assert outcome.remediation is None


def test_runner_high_conf_fail_quarantines_with_proposal() -> None:
    judges = _judges_for(CLEAN_ID, VerdictStatus.FAIL, 0.9)
    outcome = asyncio.run(_runner(judges, sample_rate=1.0).run_event(clean_event()))
    assert outcome.final_status is FinalStatus.QUARANTINED
    assert outcome.remediation is not None
    assert outcome.remediation.action is RemediationAction.CORRECT_CATEGORY


def test_runner_rule_quarantine_skips_llm() -> None:
    outcome = asyncio.run(_runner({}, sample_rate=1.0).run_event(quarantine_event()))
    assert outcome.final_status is FinalStatus.QUARANTINED
    assert outcome.llm_verdicts == []
    assert outcome.total_cost_usd == 0.0
    assert outcome.routing is not None and outcome.routing.action is RouteAction.QUARANTINE
    assert outcome.remediation is not None  # rule failure -> proposal


def test_runner_rule_review_persists_despite_llm_pass() -> None:
    judges = _judges_for(REVIEW_ID, VerdictStatus.PASS, 0.95)
    outcome = asyncio.run(_runner(judges, sample_rate=1.0).run_event(review_event()))
    assert outcome.final_status is FinalStatus.REVIEW  # rule uncertainty is not overridden


def test_runner_accept_path_no_llm() -> None:
    outcome = asyncio.run(_runner({}, sample_rate=0.0).run_event(clean_event()))
    assert outcome.final_status is FinalStatus.CLEAN
    assert outcome.routing is not None and outcome.routing.action is RouteAction.ACCEPT
    assert outcome.llm_verdicts == []


def test_runner_budget_exhausted_routes_to_review() -> None:
    budget = BudgetGuard(1.0)
    budget.record(1.0)
    judges = _judges_for(CLEAN_ID, VerdictStatus.PASS, 0.95)
    outcome = asyncio.run(
        _runner(judges, sample_rate=1.0, budget=budget).run_event(clean_event())
    )
    assert outcome.final_status is FinalStatus.REVIEW


async def _collect(
    runner: PipelineRunner, items: Iterable[ResolvedEvent | ParseError]
) -> list[EventOutcome]:
    return [outcome async for outcome in runner.run(items)]


def test_runner_stream_bounded_concurrency() -> None:
    ids = [f"{i:08d}-1111-1111-1111-111111111111" for i in range(7)]
    events: list[ResolvedEvent | ParseError] = [_event(i, confidence=0.8) for i in ids]
    judges = {
        "semantic_accuracy": CheckJudges(
            primary=ReplayJudge(
                "semantic_accuracy",
                {i: _llm_verdict(i, VerdictStatus.PASS, 0.95, model=HAIKU) for i in ids},
            )
        )
    }
    runner = _runner(judges, sample_rate=1.0)
    outcomes = asyncio.run(_collect(runner, events))
    assert len(outcomes) == 7
    assert {o.event_id for o in outcomes} == set(ids)
    assert all(o.final_status is FinalStatus.CLEAN for o in outcomes)


def test_runner_handles_parse_error_in_stream() -> None:
    err = ParseError(
        source_file="f.jsonl", source_line=9, error_type="json_decode", reason="bad", excerpt="{"
    )
    runner = _runner({}, sample_rate=0.0)
    outcomes = asyncio.run(_collect(runner, [err]))
    assert len(outcomes) == 1
    assert outcomes[0].final_status is FinalStatus.QUARANTINED
    assert outcomes[0].parse_error is not None
