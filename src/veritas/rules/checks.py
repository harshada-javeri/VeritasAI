"""The deterministic rule set.

Each rule is grounded in a measured number from ``docs/data-quality-findings.md``;
the comment on each says which observation justifies it. Rules are intentionally
small and single-purpose so the registry composes them and the dashboard can
report a pass-rate per check.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from veritas.domain.models import ResolvedEvent, Verdict, VerdictStatus
from veritas.rules.base import ExpectedField, RuleContext, rule_verdict

PASS = VerdictStatus.PASS
FAIL = VerdictStatus.FAIL
UNCERTAIN = VerdictStatus.UNCERTAIN

# The 29 categories actually observed in the feed (findings §2). Anything outside
# this set is a genuine novelty and is routed to review rather than hard-failed.
KNOWN_CATEGORIES: frozenset[str] = frozenset(
    {
        "launches",
        "partners_with",
        "hires",
        "invests_into",
        "recognized_as",
        "is_developing",
        "receives_award",
        "acquires",
        "invests_into_assets",
        "has_issues_with",
        "attends_event",
        "leaves",
        "receives_financing",
        "signs_new_client",
        "expands_facilities",
        "sells_assets_to",
        "opens_new_location",
        "promotes",
        "retires_from",
        "increases_headcount_by",
        "expands_offices_to",
        "identified_as_competitor_of",
        "integrates_with",
        "closes_offices_in",
        "expands_offices_in",
        "files_suit_against",
        "decreases_headcount_by",
        "goes_public",
        "merges_with",
    }
)

# Per-category expected fields (findings §4). Severity reflects how often the
# field is genuinely present: near-100% -> FAIL when absent; partial -> review.
# The money signal is ``amount_normalized`` (numeric), NOT ``amount`` (free text).
CONDITIONAL_FIELDS: dict[str, tuple[ExpectedField, ...]] = {
    "receives_financing": (
        ExpectedField("amount_normalized", FAIL),  # present 100%
        ExpectedField("financing_type", UNCERTAIN),  # present 80.9%
    ),
    "launches": (ExpectedField("product", FAIL),),  # present 100%
    "is_developing": (ExpectedField("product", FAIL),),  # present 100%
    "receives_award": (ExpectedField("award", FAIL),),  # present 100%
    "recognized_as": (ExpectedField("recognition", FAIL),),  # present 100%
    "hires": (ExpectedField("job_title", FAIL),),  # present 85.8%
    "acquires": (ExpectedField("amount_normalized", UNCERTAIN),),  # present 26.9%
    "invests_into": (ExpectedField("amount_normalized", UNCERTAIN),),  # present 53.5%
}


def _is_blank(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _as_utc(value: datetime) -> datetime:
    """Normalize naive datetimes (e.g. date-only ``found_at``) to UTC for comparison."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class EventIdUuidRule:
    """`event_id` must be a UUID (README §3 schema validity)."""

    name = "event_id_uuid"

    def evaluate(self, event: ResolvedEvent, ctx: RuleContext) -> Verdict | None:
        try:
            uuid.UUID(event.event_id)
        except (ValueError, AttributeError, TypeError):
            return rule_verdict(
                event_id=event.event_id,
                check_name=self.name,
                status=FAIL,
                reason=f"event_id is not a valid UUID: {event.event_id!r}",
                now=ctx.now,
            )
        return rule_verdict(
            event_id=event.event_id,
            check_name=self.name,
            status=PASS,
            reason="event_id is a valid UUID",
            now=ctx.now,
        )


class ConfidenceRangeRule:
    """`confidence` must be present and within [0, 1]. (0.0 is valid here.)"""

    name = "confidence_in_range"

    def evaluate(self, event: ResolvedEvent, ctx: RuleContext) -> Verdict | None:
        if event.confidence is None:
            raw = event.attributes.get("confidence")
            detail = f" (raw={raw!r})" if raw is not None else ""
            return rule_verdict(
                event_id=event.event_id,
                check_name=self.name,
                status=FAIL,
                reason=f"confidence is missing or unparseable{detail}",
                now=ctx.now,
            )
        if not 0.0 <= event.confidence <= 1.0:
            return rule_verdict(
                event_id=event.event_id,
                check_name=self.name,
                status=FAIL,
                reason=f"confidence {event.confidence} outside [0, 1]",
                now=ctx.now,
            )
        return rule_verdict(
            event_id=event.event_id,
            check_name=self.name,
            status=PASS,
            reason="confidence within [0, 1]",
            now=ctx.now,
        )


class CategoryKnownRule:
    """`category` must be in the observed set; novel values route to review."""

    name = "category_known"

    def evaluate(self, event: ResolvedEvent, ctx: RuleContext) -> Verdict | None:
        if not event.category:
            return rule_verdict(
                event_id=event.event_id,
                check_name=self.name,
                status=FAIL,
                reason="category is missing",
                now=ctx.now,
            )
        if event.category not in ctx.known_categories:
            return rule_verdict(
                event_id=event.event_id,
                check_name=self.name,
                status=UNCERTAIN,
                reason=f"novel category {event.category!r} not in known set",
                now=ctx.now,
            )
        return rule_verdict(
            event_id=event.event_id,
            check_name=self.name,
            status=PASS,
            reason=f"category {event.category!r} is known",
            now=ctx.now,
        )


class ConfidenceFloorRule:
    """`confidence` below the floor (default 0.15) is auto-quarantined (findings §3).

    ~10.7% of the feed clears this floor deterministically, avoiding LLM spend on
    the 0.0 "no real signal" spike.
    """

    name = "confidence_floor"

    def evaluate(self, event: ResolvedEvent, ctx: RuleContext) -> Verdict | None:
        if event.confidence is None:
            return None  # ConfidenceRangeRule owns the missing/unparseable case
        floor = ctx.thresholds.confidence_floor
        if event.confidence < floor:
            return rule_verdict(
                event_id=event.event_id,
                check_name=self.name,
                status=FAIL,
                reason=f"confidence {event.confidence} below floor {floor}",
                now=ctx.now,
            )
        return rule_verdict(
            event_id=event.event_id,
            check_name=self.name,
            status=PASS,
            reason=f"confidence {event.confidence} at or above floor {floor}",
            now=ctx.now,
        )


class DateSanityRule:
    """`found_at` must exist, not be in the future, and not predate ``min_event_year``."""

    name = "date_sanity"

    def evaluate(self, event: ResolvedEvent, ctx: RuleContext) -> Verdict | None:
        if event.found_at is None:
            raw = event.attributes.get("found_at")
            detail = f" (raw={raw!r})" if raw is not None else ""
            return rule_verdict(
                event_id=event.event_id,
                check_name=self.name,
                status=FAIL,
                reason=f"found_at is missing or unparseable{detail}",
                now=ctx.now,
            )
        found_at = _as_utc(event.found_at)
        if found_at > _as_utc(ctx.now):
            return rule_verdict(
                event_id=event.event_id,
                check_name=self.name,
                status=FAIL,
                reason=f"found_at {event.found_at.isoformat()} is in the future",
                now=ctx.now,
            )
        if event.found_at.year < ctx.thresholds.min_event_year:
            return rule_verdict(
                event_id=event.event_id,
                check_name=self.name,
                status=FAIL,
                reason=(
                    f"found_at year {event.found_at.year} predates "
                    f"min_event_year {ctx.thresholds.min_event_year}"
                ),
                now=ctx.now,
            )
        return rule_verdict(
            event_id=event.event_id,
            check_name=self.name,
            status=PASS,
            reason="found_at is within the plausible range",
            now=ctx.now,
        )


class ReferentialIntegrityRule:
    """Relationship ids must resolve; the event subject (company1) and source should exist."""

    name = "referential_integrity"

    def evaluate(self, event: ResolvedEvent, ctx: RuleContext) -> Verdict | None:
        if event.unresolved_references:
            return rule_verdict(
                event_id=event.event_id,
                check_name=self.name,
                status=FAIL,
                reason=f"dangling relationship references: {event.unresolved_references}",
                now=ctx.now,
            )
        missing: list[str] = []
        if event.company1_id is None:
            missing.append("company1")
        if event.source_article_id is None:
            missing.append("most_relevant_source")
        if missing:
            return rule_verdict(
                event_id=event.event_id,
                check_name=self.name,
                status=UNCERTAIN,
                reason=f"expected relationship(s) absent: {missing}",
                now=ctx.now,
            )
        return rule_verdict(
            event_id=event.event_id,
            check_name=self.name,
            status=PASS,
            reason="all relationships resolve",
            now=ctx.now,
        )


class ConditionalCompletenessRule:
    """Category-conditional field presence (findings §4). Severity is per category."""

    name = "conditional_completeness"

    def evaluate(self, event: ResolvedEvent, ctx: RuleContext) -> Verdict | None:
        expected = ctx.conditional_fields.get(event.category or "")
        if not expected:
            return None  # category has no conditionally-required field
        missing: list[str] = []
        worst = PASS
        for spec in expected:
            if _is_blank(event.attributes.get(spec.field)):
                missing.append(spec.field)
                if spec.severity is FAIL:
                    worst = FAIL
                elif worst is not FAIL:
                    worst = UNCERTAIN
        if not missing:
            return rule_verdict(
                event_id=event.event_id,
                check_name=self.name,
                status=PASS,
                reason=f"category {event.category!r}: expected fields present",
                now=ctx.now,
            )
        return rule_verdict(
            event_id=event.event_id,
            check_name=self.name,
            status=worst,
            reason=f"category {event.category!r}: expected field(s) absent: {missing}",
            now=ctx.now,
        )


class ExactDuplicateRule:
    """Flag repeat ``event_id``s within a run (findings §1: 7,875 benign repeats).

    Stateful: first occurrence passes; later ones fail. The seen-set is global to
    the run (duplicates span shards), so reuse one instance across the stream and
    create a fresh one per independent run.
    """

    name = "exact_duplicate"

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def evaluate(self, event: ResolvedEvent, ctx: RuleContext) -> Verdict | None:
        if event.event_id in self._seen:
            return rule_verdict(
                event_id=event.event_id,
                check_name=self.name,
                status=FAIL,
                reason="duplicate event_id (already seen earlier in this run)",
                now=ctx.now,
            )
        self._seen.add(event.event_id)
        return rule_verdict(
            event_id=event.event_id,
            check_name=self.name,
            status=PASS,
            reason="first occurrence of event_id",
            now=ctx.now,
        )
