"""Unit tests for the deterministic rule set, engine, and registry."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from veritas.config import Thresholds
from veritas.domain.models import Article, Company, ResolvedEvent, VerdictStatus
from veritas.rules.base import RecordStatus, RuleContext
from veritas.rules.checks import (
    CONDITIONAL_FIELDS,
    KNOWN_CATEGORIES,
    CategoryKnownRule,
    ConditionalCompletenessRule,
    ConfidenceFloorRule,
    ConfidenceRangeRule,
    DateSanityRule,
    EventIdUuidRule,
    ExactDuplicateRule,
    ReferentialIntegrityRule,
)
from veritas.rules.engine import RuleEngine
from veritas.rules.metrics import (
    MetricSeverity,
    NullMetricsSink,
    RuleMetric,
    RuleMetricsSink,
    severity_for,
)
from veritas.rules.registry import default_context, default_registry

NOW = datetime(2026, 6, 22, tzinfo=UTC)
VALID_UUID = "11111111-1111-1111-1111-111111111111"


def make_ctx(**overrides: Any) -> RuleContext:
    base = {
        "now": NOW,
        "thresholds": Thresholds(),
        "known_categories": KNOWN_CATEGORIES,
        "conditional_fields": CONDITIONAL_FIELDS,
    }
    base.update(overrides)
    return RuleContext(**base)  # type: ignore[arg-type]


def make_event(**overrides: Any) -> ResolvedEvent:
    """A baseline event that passes every rule; override one field per test."""
    attributes = overrides.pop("attributes", {"product": "Widget", "confidence": 0.8})
    fields: dict[str, Any] = {
        "event_id": VALID_UUID,
        "category": "launches",
        "confidence": 0.8,
        "found_at": datetime(2024, 1, 1, tzinfo=UTC),
        "attributes": attributes,
        "company1_id": "c1",
        "company1": Company(id="c1", name="Acme"),
        "source_article_id": "a1",
        "source_article": Article(id="a1"),
    }
    fields.update(overrides)
    return ResolvedEvent(**fields)


# --- event_id_uuid -------------------------------------------------------- #


def test_event_id_uuid_pass() -> None:
    verdict = EventIdUuidRule().evaluate(make_event(), make_ctx())
    assert verdict is not None and verdict.status is VerdictStatus.PASS


def test_event_id_uuid_fail() -> None:
    verdict = EventIdUuidRule().evaluate(make_event(event_id="not-a-uuid"), make_ctx())
    assert verdict is not None and verdict.status is VerdictStatus.FAIL


# --- confidence_in_range -------------------------------------------------- #


def test_confidence_missing_fails() -> None:
    event = make_event(confidence=None, attributes={"confidence": "high", "product": "W"})
    verdict = ConfidenceRangeRule().evaluate(event, make_ctx())
    assert verdict is not None and verdict.status is VerdictStatus.FAIL
    assert "high" in verdict.reason  # raw value surfaced


def test_confidence_out_of_range_fails() -> None:
    verdict = ConfidenceRangeRule().evaluate(make_event(confidence=1.5), make_ctx())
    assert verdict is not None and verdict.status is VerdictStatus.FAIL


def test_confidence_zero_is_in_range() -> None:
    verdict = ConfidenceRangeRule().evaluate(make_event(confidence=0.0), make_ctx())
    assert verdict is not None and verdict.status is VerdictStatus.PASS


# --- confidence_floor ----------------------------------------------------- #


def test_confidence_floor_quarantines_zero() -> None:
    verdict = ConfidenceFloorRule().evaluate(make_event(confidence=0.0), make_ctx())
    assert verdict is not None and verdict.status is VerdictStatus.FAIL


def test_confidence_floor_passes_above_threshold() -> None:
    verdict = ConfidenceFloorRule().evaluate(make_event(confidence=0.2), make_ctx())
    assert verdict is not None and verdict.status is VerdictStatus.PASS


def test_confidence_floor_abstains_when_missing() -> None:
    event = make_event(confidence=None, attributes={"product": "W"})
    assert ConfidenceFloorRule().evaluate(event, make_ctx()) is None


# --- category_known ------------------------------------------------------- #


def test_category_known_passes() -> None:
    verdict = CategoryKnownRule().evaluate(make_event(category="acquires"), make_ctx())
    assert verdict is not None and verdict.status is VerdictStatus.PASS


def test_category_novel_routes_to_review() -> None:
    verdict = CategoryKnownRule().evaluate(make_event(category="frobnicates"), make_ctx())
    assert verdict is not None and verdict.status is VerdictStatus.UNCERTAIN


def test_category_missing_fails() -> None:
    verdict = CategoryKnownRule().evaluate(make_event(category=None), make_ctx())
    assert verdict is not None and verdict.status is VerdictStatus.FAIL


# --- date_sanity ---------------------------------------------------------- #


def test_date_future_fails() -> None:
    future = datetime(2030, 1, 1, tzinfo=UTC)
    verdict = DateSanityRule().evaluate(make_event(found_at=future), make_ctx())
    assert verdict is not None and verdict.status is VerdictStatus.FAIL


def test_date_too_old_fails() -> None:
    old = datetime(1990, 1, 1, tzinfo=UTC)
    verdict = DateSanityRule().evaluate(make_event(found_at=old), make_ctx())
    assert verdict is not None and verdict.status is VerdictStatus.FAIL


def test_date_naive_is_handled() -> None:
    naive = datetime(2024, 5, 5)  # date-only style, no tzinfo
    verdict = DateSanityRule().evaluate(make_event(found_at=naive), make_ctx())
    assert verdict is not None and verdict.status is VerdictStatus.PASS


def test_date_missing_fails() -> None:
    verdict = DateSanityRule().evaluate(make_event(found_at=None), make_ctx())
    assert verdict is not None and verdict.status is VerdictStatus.FAIL


# --- referential_integrity ------------------------------------------------ #


def test_dangling_reference_fails() -> None:
    event = make_event(unresolved_references=["cmissing"])
    verdict = ReferentialIntegrityRule().evaluate(event, make_ctx())
    assert verdict is not None and verdict.status is VerdictStatus.FAIL


def test_missing_company1_routes_to_review() -> None:
    event = make_event(company1_id=None, company1=None)
    verdict = ReferentialIntegrityRule().evaluate(event, make_ctx())
    assert verdict is not None and verdict.status is VerdictStatus.UNCERTAIN


def test_all_relationships_resolve_passes() -> None:
    verdict = ReferentialIntegrityRule().evaluate(make_event(), make_ctx())
    assert verdict is not None and verdict.status is VerdictStatus.PASS


# --- conditional_completeness --------------------------------------------- #


def test_completeness_not_applicable_returns_none() -> None:
    # partners_with has no conditionally-required field.
    event = make_event(category="partners_with", attributes={})
    assert ConditionalCompletenessRule().evaluate(event, make_ctx()) is None


def test_financing_missing_amount_normalized_fails() -> None:
    event = make_event(category="receives_financing", attributes={"financing_type": "series_a"})
    verdict = ConditionalCompletenessRule().evaluate(event, make_ctx())
    assert verdict is not None and verdict.status is VerdictStatus.FAIL
    assert "amount_normalized" in verdict.reason


def test_financing_present_passes() -> None:
    event = make_event(
        category="receives_financing",
        attributes={"amount_normalized": 1_000_000, "financing_type": "series_a"},
    )
    verdict = ConditionalCompletenessRule().evaluate(event, make_ctx())
    assert verdict is not None and verdict.status is VerdictStatus.PASS


def test_acquires_missing_amount_is_review_not_fail() -> None:
    # acquires legitimately lacks amount_normalized ~73% of the time -> review.
    event = make_event(category="acquires", attributes={})
    verdict = ConditionalCompletenessRule().evaluate(event, make_ctx())
    assert verdict is not None and verdict.status is VerdictStatus.UNCERTAIN


# --- exact_duplicate (stateful) ------------------------------------------- #


def test_duplicate_first_passes_second_fails() -> None:
    rule = ExactDuplicateRule()
    ctx = make_ctx()
    first = rule.evaluate(make_event(), ctx)
    second = rule.evaluate(make_event(), ctx)
    assert first is not None and first.status is VerdictStatus.PASS
    assert second is not None and second.status is VerdictStatus.FAIL


# --- engine + registry ---------------------------------------------------- #


def test_default_registry_has_all_rules() -> None:
    registry = default_registry()
    names = {rule.name for rule in registry.rules()}
    assert names == {
        "event_id_uuid",
        "confidence_in_range",
        "confidence_floor",
        "category_known",
        "date_sanity",
        "referential_integrity",
        "conditional_completeness",
        "exact_duplicate",
    }


def test_duplicate_registration_raises() -> None:
    registry = default_registry()
    try:
        registry.register(EventIdUuidRule())
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ValueError on duplicate registration")


def test_engine_clean_event() -> None:
    engine = default_registry().build_engine()
    report = engine.evaluate(make_event(), default_context(NOW))
    assert report.status is RecordStatus.CLEAN
    assert all(v.status is VerdictStatus.PASS for v in report.verdicts)


def test_engine_quarantines_on_any_fail() -> None:
    engine = default_registry().build_engine()
    report = engine.evaluate(make_event(confidence=0.0), default_context(NOW))
    assert report.status is RecordStatus.QUARANTINED


def test_engine_reviews_on_uncertain_only() -> None:
    engine = default_registry().build_engine()
    event = make_event(category="frobnicates")  # novel -> uncertain, nothing fails
    report = engine.evaluate(event, default_context(NOW))
    assert report.status is RecordStatus.REVIEW


def test_engine_verdicts_are_all_rule_type() -> None:
    engine = default_registry().build_engine()
    report = engine.evaluate(make_event(), default_context(NOW))
    assert all(v.check_type.value == "rule" for v in report.verdicts)
    assert all(v.prompt_version is None and v.model is None for v in report.verdicts)


# --- metrics hook --------------------------------------------------------- #


class _CapturingSink:
    """Test double implementing the RuleMetricsSink Protocol."""

    def __init__(self) -> None:
        self.metrics: list[RuleMetric] = []

    def record(self, metric: RuleMetric) -> None:
        self.metrics.append(metric)


def test_severity_for_maps_each_verdict() -> None:
    assert severity_for(VerdictStatus.PASS) is MetricSeverity.INFO
    assert severity_for(VerdictStatus.UNCERTAIN) is MetricSeverity.WARNING
    assert severity_for(VerdictStatus.FAIL) is MetricSeverity.ERROR


def test_capturing_sink_satisfies_protocol() -> None:
    assert isinstance(_CapturingSink(), RuleMetricsSink)
    assert isinstance(NullMetricsSink(), RuleMetricsSink)


def test_metrics_emitted_once_per_verdict() -> None:
    sink = _CapturingSink()
    engine = RuleEngine(default_registry().rules(), metrics=sink)
    report = engine.evaluate(make_event(), default_context(NOW))
    assert len(sink.metrics) == len(report.verdicts)
    # Clean event -> every produced verdict is a pass -> INFO severity.
    assert all(m.severity is MetricSeverity.INFO for m in sink.metrics)
    assert all(m.latency_ms >= 0.0 for m in sink.metrics)
    assert {m.rule_name for m in sink.metrics} >= {"event_id_uuid", "confidence_floor"}


def test_metrics_severity_reflects_failure() -> None:
    sink = _CapturingSink()
    engine = RuleEngine(default_registry().rules(), metrics=sink)
    engine.evaluate(make_event(confidence=0.0), default_context(NOW))
    by_rule = {m.rule_name: m.severity for m in sink.metrics}
    assert by_rule["confidence_floor"] is MetricSeverity.ERROR


def test_default_engine_uses_null_sink_without_error() -> None:
    # build_engine() supplies no sink; evaluation must still succeed.
    report = default_registry().build_engine().evaluate(make_event(), default_context(NOW))
    assert report.status is RecordStatus.CLEAN
