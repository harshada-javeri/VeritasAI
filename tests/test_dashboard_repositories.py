"""Repository-layer tests: SQL reads against the seeded in-memory database."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from veritas.dashboard.repositories import (
    CostRepository,
    EventRepository,
    MetaRepository,
    TraceRepository,
    VerdictRepository,
    to_sync_url,
)


def test_to_sync_url_converts_async_drivers() -> None:
    assert to_sync_url("sqlite+aiosqlite:///./veritas.db") == "sqlite:///./veritas.db"
    assert to_sync_url("postgresql+asyncpg://h/db") == "postgresql+psycopg://h/db"
    assert to_sync_url("sqlite:///./x.db") == "sqlite:///./x.db"


def test_event_counts(read_sm: sessionmaker[Session]) -> None:
    repo = EventRepository(read_sm)
    assert repo.count() == 4
    by_status = {r.status: r.count for r in repo.count_by_status()}
    assert by_status == {"clean": 2, "review": 1, "quarantine": 1}
    by_category = {r.category: r.count for r in repo.count_by_category()}
    assert by_category["launches"] == 2


def test_event_header_and_listing(read_sm: sessionmaker[Session]) -> None:
    repo = EventRepository(read_sm)
    assert repo.get_header("missing") is None
    header = repo.get_header("e1")
    assert header is not None and header.status == "clean"

    review = repo.list_by_status("review", order_by="confidence")
    assert [item.event_id for item in review] == ["e2"]
    assert review[0].min_llm_confidence == pytest.approx(0.5)


def test_verdict_reads(read_sm: sessionmaker[Session]) -> None:
    repo = VerdictRepository(read_sm)
    assert repo.count() == 10
    assert repo.count_by_check("exact_duplicate", "fail") == 1

    rule = {(r.check_name, r.verdict): r.count for r in repo.rule_breakdown()}
    assert rule[("confidence_floor", "fail")] == 1
    assert rule[("referential_integrity", "pass")] == 2

    dup_trend = repo.timeseries_by_check("exact_duplicate", "fail")
    assert sum(d.count for d in dup_trend) == 1

    hist = repo.confidence_histogram("llm")
    assert sum(b.count for b in hist) == 4  # four LLM verdicts carry confidence

    fails = {(c.category, c.check_name): c.count for c in repo.failures_by_category()}
    assert fails[("hires", "confidence_floor")] == 1
    assert fails[("hires", "exact_duplicate")] == 1

    latency = {m.model: len(m.values) for m in repo.latency_by_model()}
    assert latency["claude-haiku-4-5-20251001"] == 3
    assert latency["claude-sonnet-4-6"] == 1

    for_e2 = repo.list_for_event("e2")
    assert len(for_e2) == 3


def test_cost_reads(read_sm: sessionmaker[Session]) -> None:
    repo = CostRepository(read_sm)
    assert repo.total_cost() == pytest.approx(0.013)

    tokens = repo.token_totals()
    assert tokens.input_tokens == 1600
    assert tokens.output_tokens == 240

    by_model = {m.model: m.total_cost for m in repo.cost_per_verdict_by_model()}
    assert by_model["claude-haiku-4-5-20251001"] == pytest.approx(0.003)
    assert by_model["claude-sonnet-4-6"] == pytest.approx(0.01)

    by_check = {c.check_name: c.total_cost for c in repo.cost_by_check()}
    assert by_check["semantic_accuracy"] == pytest.approx(0.013)

    by_prompt = {p.prompt_version: p for p in repo.cost_by_prompt_version()}
    assert by_prompt["v1"].count == 4
    assert by_prompt["v1"].total_input_tokens == 1600

    trend = {d.day: d.total_cost for d in repo.cost_timeseries()}
    assert sum(trend.values()) == pytest.approx(0.013)

    escalated, llm_events = repo.escalation_event_counts({"claude-sonnet-4-6"})
    assert escalated == 1
    assert llm_events == 3


def test_trace_reads(read_sm: sessionmaker[Session]) -> None:
    repo = TraceRepository(read_sm)
    assert repo.count() == 5
    assert sum(d.count for d in repo.throughput()) == 5
    stages = {s.stage: s.count for s in repo.count_by_stage()}
    assert stages["rules"] == 3
    assert len(repo.list_for_event("e1")) == 2


def test_meta_data_version(read_sm: sessionmaker[Session], empty_sm: sessionmaker[Session]) -> None:
    assert MetaRepository(read_sm).data_version() != "empty"
    assert MetaRepository(empty_sm).data_version() == "empty"
