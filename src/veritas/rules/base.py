"""Rule engine primitives: the Rule contract, evaluation context, verdict
generation, and the record-level rollup.

A rule is a *pure, deterministic* check over a single :class:`ResolvedEvent`.
It returns a :class:`Verdict` (``pass``/``fail``/``uncertain``) or ``None`` when
the rule does not apply to that event. Rules cost nothing and run on 100% of
records — they are the gate before any LLM spend.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from veritas.config import Thresholds
from veritas.domain.models import CheckType, ResolvedEvent, Verdict, VerdictStatus


class RecordStatus(StrEnum):
    """Record-level rollup of all rule verdicts (mirrors ``events_clean.status``)."""

    CLEAN = "clean"
    QUARANTINED = "quarantined"
    REVIEW = "review"


@dataclass(frozen=True)
class ExpectedField:
    """A category-conditional field and the severity if it is absent."""

    field: str
    severity: VerdictStatus  # FAIL (genuine defect) or UNCERTAIN (route to review)


@dataclass(frozen=True)
class RuleContext:
    """Immutable configuration handed to every rule on each evaluation.

    ``now`` is injected (never read from the clock inside a rule) so date logic
    is deterministic and testable.
    """

    now: datetime
    thresholds: Thresholds
    known_categories: frozenset[str]
    conditional_fields: dict[str, tuple[ExpectedField, ...]]


@runtime_checkable
class Rule(Protocol):
    """Structural contract for a deterministic rule."""

    name: str

    def evaluate(self, event: ResolvedEvent, ctx: RuleContext) -> Verdict | None:
        """Return a verdict, or ``None`` if the rule does not apply to ``event``."""
        ...


def rule_verdict(
    *,
    event_id: str,
    check_name: str,
    status: VerdictStatus,
    reason: str,
    now: datetime,
    confidence: float | None = 1.0,
    evidence_span: str | None = None,
) -> Verdict:
    """Build a rule verdict. Rules are deterministic, so confidence defaults to 1.0."""
    return Verdict(
        event_id=event_id,
        check_name=check_name,
        check_type=CheckType.RULE,
        status=status,
        confidence=confidence,
        reason=reason,
        evidence_span=evidence_span,
        ts=now,
    )


def rollup_status(verdicts: list[Verdict]) -> RecordStatus:
    """Collapse per-check verdicts into a record status (fail > uncertain > pass)."""
    has_fail = any(v.status is VerdictStatus.FAIL for v in verdicts)
    if has_fail:
        return RecordStatus.QUARANTINED
    has_uncertain = any(v.status is VerdictStatus.UNCERTAIN for v in verdicts)
    if has_uncertain:
        return RecordStatus.REVIEW
    return RecordStatus.CLEAN
