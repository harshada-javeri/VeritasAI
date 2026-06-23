"""Default routing policy: the triage gate.

Pure and deterministic. Rule FAIL -> quarantine (no LLM). Rule REVIEW -> escalate.
Rule CLEAN -> sample a configurable fraction into semantic review; the rest are
accepted without LLM spend. Sampling is a stable hash of ``event_id`` (not random)
so the decision is idempotent across re-runs.
"""

from __future__ import annotations

import hashlib

from veritas.domain.models import ResolvedEvent
from veritas.pipeline.contracts import RouteAction, RoutingDecision
from veritas.rules.base import RecordStatus
from veritas.rules.engine import RuleReport

_HASH_MAX = 0xFFFFFFFF


class DefaultRoutingPolicy:
    """Implements ``RoutingPolicy``."""

    def __init__(
        self,
        *,
        clean_sample_rate: float = 0.20,
        clean_checks: tuple[str, ...] = ("semantic_accuracy",),
        review_checks: tuple[str, ...] = ("semantic_accuracy",),
    ) -> None:
        if not 0.0 <= clean_sample_rate <= 1.0:
            raise ValueError("clean_sample_rate must be in [0, 1]")
        self._rate = clean_sample_rate
        self._clean_checks = clean_checks
        self._review_checks = review_checks

    def _sampled_in(self, event_id: str) -> bool:
        if self._rate <= 0.0:
            return False
        if self._rate >= 1.0:
            return True
        digest = hashlib.sha256(event_id.encode("utf-8")).hexdigest()[:8]
        return int(digest, 16) / _HASH_MAX < self._rate

    def decide(self, event: ResolvedEvent, report: RuleReport) -> RoutingDecision:
        if report.status is RecordStatus.QUARANTINED:
            return RoutingDecision(
                event_id=event.event_id,
                action=RouteAction.QUARANTINE,
                reason="hard rule failure; quarantined with no LLM spend",
            )
        if report.status is RecordStatus.REVIEW:
            return RoutingDecision(
                event_id=event.event_id,
                action=RouteAction.ESCALATE,
                checks=self._review_checks,
                reason="rule uncertainty; escalating to LLM judges",
            )
        # RecordStatus.CLEAN
        if self._sampled_in(event.event_id):
            pct = round(self._rate * 100)
            return RoutingDecision(
                event_id=event.event_id,
                action=RouteAction.ESCALATE,
                checks=self._clean_checks,
                sampled=True,
                reason=f"rule-clean; sampled for semantic review (~{pct}%)",
            )
        return RoutingDecision(
            event_id=event.event_id,
            action=RouteAction.ACCEPT,
            reason="rule-clean; not sampled for LLM review",
        )
