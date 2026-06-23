"""Service-layer tests: repositories -> view-models, including derivation logic."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from veritas.config import Settings
from veritas.dashboard.repositories import (
    CostRepository,
    EvalRepository,
    EventRepository,
    TraceRepository,
    VerdictRepository,
)
from veritas.dashboard.services import (
    CostService,
    EventService,
    JudgeService,
    PlatformService,
    QualityService,
    ReviewService,
    TrustService,
)


def test_trust_service(read_sm: sessionmaker[Session]) -> None:
    vm = TrustService(EventRepository(read_sm), VerdictRepository(read_sm)).build()
    assert not vm.is_empty
    assert {b.label for b in vm.status_composition} == {"clean", "review", "quarantine"}
    assert vm.duplicate.value == 1.0
    assert vm.data_quality_index is not None
    # integrity pass rate = 2/3; clean rate = 0.5; dup-ok = 1 - 1/4
    clean = next(c for c in vm.data_quality_index.components if c.name == "clean_rate")
    assert clean.rate == pytest.approx(0.5)
    assert any(d.check_name == "confidence_floor" for d in vm.drivers)


def test_trust_service_empty(empty_sm: sessionmaker[Session]) -> None:
    vm = TrustService(EventRepository(empty_sm), VerdictRepository(empty_sm)).build()
    assert vm.is_empty
    assert vm.data_quality_index is None


def test_cost_service(read_sm: sessionmaker[Session]) -> None:
    svc = CostService(CostRepository(read_sm), EventRepository(read_sm), Settings())
    vm = svc.build()
    assert not vm.is_empty
    assert vm.total_spend.value_usd == pytest.approx(0.013)
    assert vm.escalation_rate.value == pytest.approx(1 / 3)
    assert vm.budget.consumed_pct == pytest.approx(0.013 / 500.0)
    assert any(c.is_zero for c in vm.cost_by_check)  # rule checks cost $0


def test_cost_service_empty(empty_sm: sessionmaker[Session]) -> None:
    svc = CostService(CostRepository(empty_sm), EventRepository(empty_sm), Settings())
    assert svc.build().is_empty


def test_quality_service(read_sm: sessionmaker[Session]) -> None:
    vm = QualityService(VerdictRepository(read_sm), EventRepository(read_sm)).build()
    assert not vm.is_empty
    rates = {r.check_name: r.fail_rate for r in vm.rule_stats}
    assert rates["exact_duplicate"] == pytest.approx(1.0)
    assert rates["confidence_floor"] == pytest.approx(0.5)
    # worst-first ordering
    assert vm.rule_stats[0].fail_rate >= vm.rule_stats[-1].fail_rate
    assert any(b.label == "launches" for b in vm.categories)


def test_platform_service(read_sm: sessionmaker[Session]) -> None:
    vm = PlatformService(
        VerdictRepository(read_sm), TraceRepository(read_sm), EventRepository(read_sm)
    ).build()
    assert not vm.is_empty
    sizes = {t.table: t.rows for t in vm.storage}
    assert sizes == {"events_clean": 4, "quality_verdicts": 10, "trace_logs": 5}
    haiku = next(m for m in vm.latency if m.model == "claude-haiku-4-5-20251001")
    assert haiku.p50_ms > 0


def test_review_service(read_sm: sessionmaker[Session]) -> None:
    vm = ReviewService(EventRepository(read_sm)).build("review", order_by="confidence")
    assert not vm.is_empty
    assert [i.event_id for i in vm.items] == ["e2"]
    assert "Impact ranking" in vm.sort_note


def test_event_service(read_sm: sessionmaker[Session]) -> None:
    svc = EventService(
        EventRepository(read_sm), VerdictRepository(read_sm), TraceRepository(read_sm)
    )
    found = svc.build("e2")
    assert found.found
    assert found.header is not None
    assert len(found.verdicts) == 3
    assert found.cost_summary is not None
    assert found.cost_summary.value_usd == pytest.approx(0.011)

    missing = svc.build("nope")
    assert not missing.found
    assert missing.header is None


def test_judge_service_offline(read_sm: sessionmaker[Session]) -> None:
    vm = JudgeService(EvalRepository(Settings()), VerdictRepository(read_sm)).build()
    assert not vm.is_empty
    assert vm.scorecards
    assert all(s.sample_warning for s in vm.scorecards)  # fixtures are tiny
    assert vm.comparison is not None  # semantic_accuracy ships v1 + v2
    assert any(mix.check_name == "semantic_accuracy" for mix in vm.live_verdict_mix)
