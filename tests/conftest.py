"""Shared fixtures for the dashboard test suite.

Builds a synchronous in-memory SQLite database (shared connection via
``StaticPool``), creates the existing schema, and seeds a small, deterministic
fixture exercising every dashboard query path.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from veritas.store.base import Base
from veritas.store.models import EventCleanRow, QualityVerdictRow, TraceLogRow

DAY1 = datetime(2026, 6, 22, 9, 0, tzinfo=UTC)
DAY2 = datetime(2026, 6, 23, 9, 0, tzinfo=UTC)


def _rule(event_id: str, check_name: str, verdict: str, ts: datetime) -> QualityVerdictRow:
    return QualityVerdictRow(
        event_id=event_id,
        check_name=check_name,
        check_type="rule",
        prompt_version="",
        model="",
        verdict=verdict,
        confidence=None,
        reason=f"{check_name} -> {verdict}",
        evidence_span=None,
        input_tokens=None,
        output_tokens=None,
        cost_usd=None,
        latency_ms=None,
        ts=ts,
        created_at=ts,
    )


def _llm(
    event_id: str,
    verdict: str,
    *,
    model: str,
    confidence: float,
    cost: float,
    latency: int,
    ts: datetime,
    prompt_version: str = "v1",
) -> QualityVerdictRow:
    return QualityVerdictRow(
        event_id=event_id,
        check_name="semantic_accuracy",
        check_type="llm",
        prompt_version=prompt_version,
        model=model,
        verdict=verdict,
        confidence=confidence,
        reason=f"semantic_accuracy -> {verdict}",
        evidence_span="evidence",
        input_tokens=400,
        output_tokens=60,
        cost_usd=cost,
        latency_ms=latency,
        ts=ts,
        created_at=ts,
    )


def _seed(session: Session) -> None:
    events = [
        EventCleanRow(
            event_id="e1", category="launches", summary="A launches B",
            found_at=DAY1, company1_id="c1", company2_id="c2", status="clean", updated_at=DAY1,
        ),
        EventCleanRow(
            event_id="e2", category="partners_with", summary="A partners with C",
            found_at=DAY1, company1_id="c1", company2_id=None, status="review", updated_at=DAY2,
        ),
        EventCleanRow(
            event_id="e3", category="hires", summary="A hires D",
            found_at=DAY2, company1_id="c1", company2_id=None, status="quarantine", updated_at=DAY2,
        ),
        EventCleanRow(
            event_id="e4", category="launches", summary="E launches F",
            found_at=DAY2, company1_id="c5", company2_id="c6", status="clean", updated_at=DAY2,
        ),
    ]
    haiku = "claude-haiku-4-5-20251001"
    sonnet = "claude-sonnet-4-6"
    verdicts = [
        _rule("e1", "confidence_floor", "pass", DAY1),
        _rule("e1", "referential_integrity", "pass", DAY1),
        _llm("e1", "pass", model=haiku, confidence=0.9, cost=0.001, latency=800, ts=DAY1),
        _rule("e2", "referential_integrity", "review", DAY1),
        _llm("e2", "uncertain", model=haiku, confidence=0.5, cost=0.001, latency=900, ts=DAY1),
        _llm("e2", "pass", model=sonnet, confidence=0.8, cost=0.01, latency=1500, ts=DAY2),
        _rule("e3", "confidence_floor", "fail", DAY2),
        _rule("e3", "exact_duplicate", "fail", DAY2),
        _rule("e4", "referential_integrity", "pass", DAY2),
        _llm("e4", "pass", model=haiku, confidence=0.95, cost=0.001, latency=700, ts=DAY2),
    ]
    traces = [
        TraceLogRow(
            event_id="e1", trace_id="t1", stage="rules", payload_hash="h1", created_at=DAY1
        ),
        TraceLogRow(
            event_id="e1", trace_id="t1", stage="finalize", payload_hash="h2", created_at=DAY1
        ),
        TraceLogRow(
            event_id="e2", trace_id="t2", stage="rules", payload_hash="h3", created_at=DAY1
        ),
        TraceLogRow(
            event_id="e2", trace_id="t2", stage="escalate", payload_hash="h4", created_at=DAY2
        ),
        TraceLogRow(
            event_id="e3", trace_id="t3", stage="rules", payload_hash="h5", created_at=DAY2
        ),
    ]
    session.add_all([*events, *verdicts, *traces])
    session.commit()


@pytest.fixture
def read_engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as session:
        _seed(session)
    yield engine
    engine.dispose()


@pytest.fixture
def read_sm(read_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(read_engine, expire_on_commit=False)


@pytest.fixture
def empty_sm() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()
