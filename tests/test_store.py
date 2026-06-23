"""Tests for the storage layer: repositories, idempotency, SQLite integration."""

from __future__ import annotations

import asyncio
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
from veritas.llm_gateway.budget import BudgetGuard
from veritas.pipeline import (
    CheckJudges,
    DefaultRoutingPolicy,
    EventOutcome,
    EventSnapshot,
    FinalStatus,
    HeuristicRemediator,
    PipelineRunner,
    TieredEscalationRouter,
)
from veritas.rules.registry import default_context, default_registry
from veritas.store import (
    Database,
    EventRepository,
    RepositoryTraceSink,
    RepositoryVerdictSink,
    TraceRepository,
    VerdictRepository,
)

NOW = datetime(2026, 6, 22, tzinfo=UTC)
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
CLEAN_UUID = "11111111-1111-1111-1111-111111111111"


def _verdict(
    event_id: str,
    check: str,
    status: VerdictStatus,
    *,
    pv: str | None = None,
    model: str | None = None,
    check_type: CheckType = CheckType.LLM,
    confidence: float = 0.9,
) -> Verdict:
    return Verdict(
        event_id=event_id,
        check_name=check,
        check_type=check_type,
        status=status,
        confidence=confidence,
        reason="recorded",
        prompt_version=pv,
        model=model,
        cost_usd=0.0,
        ts=NOW,
    )


def _clean_event(event_id: str) -> ResolvedEvent:
    return ResolvedEvent(
        event_id=event_id,
        category="launches",
        confidence=0.8,
        found_at=datetime(2024, 1, 1, tzinfo=UTC),
        summary="Acme launches Widget",
        article_sentence="Acme launched Widget.",
        attributes={"product": "Widget"},
        company1_id="c1",
        company1=Company(id="c1", name="Acme"),
        company2_id="c2",
        source_article_id="a1",
        source_article=Article(id="a1"),
    )


# --- verdict repository --------------------------------------------------- #


def test_verdict_insert_and_list() -> None:
    async def scenario() -> list[Verdict]:
        db = Database.in_memory()
        await db.create_all()
        repo = VerdictRepository(db.sessionmaker)
        await repo.upsert_verdicts(
            [_verdict("e1", "semantic_accuracy", VerdictStatus.PASS, pv="v1", model=HAIKU)]
        )
        rows = await repo.list_for_event("e1")
        await db.dispose()
        return rows

    rows = asyncio.run(scenario())
    assert len(rows) == 1
    assert rows[0].status is VerdictStatus.PASS
    assert rows[0].prompt_version == "v1"
    assert rows[0].model == HAIKU


def test_verdict_upsert_is_idempotent() -> None:
    async def scenario() -> tuple[int, VerdictStatus]:
        db = Database.in_memory()
        await db.create_all()
        repo = VerdictRepository(db.sessionmaker)
        await repo.upsert_verdicts(
            [_verdict("e1", "semantic_accuracy", VerdictStatus.PASS, pv="v1", model=HAIKU)]
        )
        # same idempotency key, different status -> updates in place, no new row
        await repo.upsert_verdicts(
            [_verdict("e1", "semantic_accuracy", VerdictStatus.FAIL, pv="v1", model=HAIKU)]
        )
        rows = await repo.list_for_event("e1")
        await db.dispose()
        return len(rows), rows[0].status

    count, status = asyncio.run(scenario())
    assert count == 1
    assert status is VerdictStatus.FAIL


def test_rule_verdict_idempotent_with_absent_prompt_and_model() -> None:
    # prompt_version/model are None for rules -> stored as "" so the unique
    # constraint still dedupes (SQL NULLs would be treated as distinct).
    async def scenario() -> int:
        db = Database.in_memory()
        await db.create_all()
        repo = VerdictRepository(db.sessionmaker)
        rule = _verdict("e1", "confidence_floor", VerdictStatus.FAIL, check_type=CheckType.RULE)
        await repo.upsert_verdicts([rule])
        await repo.upsert_verdicts([rule])
        rows = await repo.list_for_event("e1")
        await db.dispose()
        return len(rows)

    assert asyncio.run(scenario()) == 1


def test_distinct_models_are_distinct_rows() -> None:
    async def scenario() -> int:
        db = Database.in_memory()
        await db.create_all()
        repo = VerdictRepository(db.sessionmaker)
        await repo.upsert_verdicts(
            [
                _verdict("e1", "semantic_accuracy", VerdictStatus.UNCERTAIN, pv="v1", model=HAIKU),
                _verdict("e1", "semantic_accuracy", VerdictStatus.FAIL, pv="v1", model=SONNET),
            ]
        )
        rows = await repo.list_for_event("e1")
        await db.dispose()
        return len(rows)

    assert asyncio.run(scenario()) == 2


# --- event repository ----------------------------------------------------- #


def test_event_upsert_and_status_update() -> None:
    async def scenario() -> tuple[str, str]:
        db = Database.in_memory()
        await db.create_all()
        repo = EventRepository(db.sessionmaker)
        await repo.upsert(event_id="e1", status="review", category="launches", summary="s")
        first = await repo.get("e1")
        await repo.upsert(event_id="e1", status="clean", category="launches", summary="s")
        second = await repo.get("e1")
        count = await repo.count()
        await db.dispose()
        assert first is not None and second is not None and count == 1
        return first.status, second.status

    first_status, second_status = asyncio.run(scenario())
    assert first_status == "review"
    assert second_status == "clean"


# --- trace repository ----------------------------------------------------- #


def test_trace_append_is_appendable() -> None:
    async def scenario() -> int:
        db = Database.in_memory()
        await db.create_all()
        repo = TraceRepository(db.sessionmaker)
        await repo.append(event_id="e1", trace_id="t1", stage="finalized", payload_hash="h1")
        await repo.append(event_id="e1", trace_id="t1", stage="finalized", payload_hash="h2")
        rows = await repo.list_for_event("e1")
        await db.dispose()
        return len(rows)

    assert asyncio.run(scenario()) == 2


# --- sinks ---------------------------------------------------------------- #


def test_repository_sinks_persist_outcome() -> None:
    async def scenario() -> tuple[str | None, int, int]:
        db = Database.in_memory()
        await db.create_all()
        sm = db.sessionmaker
        verdict_sink = RepositoryVerdictSink(VerdictRepository(sm))
        trace_sink = RepositoryTraceSink(TraceRepository(sm), EventRepository(sm))

        await verdict_sink.upsert_verdicts(
            [_verdict("e1", "semantic_accuracy", VerdictStatus.FAIL, pv="v1", model=HAIKU)]
        )
        outcome = EventOutcome(
            event_id="e1",
            final_status=FinalStatus.QUARANTINED,
            snapshot=EventSnapshot(event_id="e1", category="launches", summary="s"),
        )
        await trace_sink.on_outcome(outcome)

        event_row = await EventRepository(sm).get("e1")
        traces = await TraceRepository(sm).list_for_event("e1")
        verdicts = await VerdictRepository(sm).list_for_event("e1")
        await db.dispose()
        status = event_row.status if event_row is not None else None
        return status, len(traces), len(verdicts)

    status, n_traces, n_verdicts = asyncio.run(scenario())
    assert status == "quarantined"
    assert n_traces == 1
    assert n_verdicts == 1


# --- pipeline integration + replay-safety --------------------------------- #


def test_pipeline_persists_and_is_replay_safe() -> None:
    async def scenario() -> tuple[FinalStatus, tuple[int, int, int], tuple[int, int, int]]:
        db = Database.in_memory()
        await db.create_all()
        sm = db.sessionmaker
        verdicts = VerdictRepository(sm)
        events = EventRepository(sm)
        traces = TraceRepository(sm)
        event = _clean_event(CLEAN_UUID)

        async def run_once() -> list[EventOutcome]:
            recorded = _verdict(
                CLEAN_UUID, "semantic_accuracy", VerdictStatus.PASS, pv="v1", model=HAIKU
            )
            judges = {
                "semantic_accuracy": CheckJudges(
                    primary=ReplayJudge("semantic_accuracy", {CLEAN_UUID: recorded})
                )
            }
            budget = BudgetGuard(100.0)
            runner = PipelineRunner(
                rule_engine=default_registry().build_engine(),
                rule_context=default_context(NOW),
                routing_policy=DefaultRoutingPolicy(clean_sample_rate=1.0),
                escalation_router=TieredEscalationRouter(judges, budget),
                remediator=HeuristicRemediator(),
                budget=budget,
                verdict_sink=RepositoryVerdictSink(verdicts),
                trace_sink=RepositoryTraceSink(traces, events),
            )
            return [outcome async for outcome in runner.run([event])]

        out1 = await run_once()
        counts1 = (await verdicts.count(), await events.count(), await traces.count())
        await run_once()  # replay
        counts2 = (await verdicts.count(), await events.count(), await traces.count())
        await db.dispose()
        return out1[0].final_status, counts1, counts2

    final_status, counts1, counts2 = asyncio.run(scenario())
    assert final_status is FinalStatus.CLEAN
    # verdicts + events are idempotent across the replay; trace_logs is append-only.
    assert counts1[0] > 0 and counts2[0] == counts1[0]  # verdicts stable
    assert counts1[1] == 1 and counts2[1] == 1  # one events_clean row
    assert counts1[2] == 1 and counts2[2] == 2  # trace appended each run
