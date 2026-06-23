"""Strongly-typed contracts for the pipeline lifecycle.

Every stage consumes and returns one of these typed objects — no bare dicts cross
a boundary. ``RemediationProposal`` is proposal-only by design (decision 5): the
pipeline never auto-applies a change, so there is no auto-apply terminal status;
``final_status`` is one of CLEAN / QUARANTINED / REVIEW with a proposal attached
whenever a check failed.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from veritas.domain.models import ParseError, ResolvedEvent, Verdict
from veritas.rules.engine import RuleReport


class RouteAction(StrEnum):
    QUARANTINE = "quarantine"  # terminal, no LLM spend
    ESCALATE = "escalate"  # run the selected LLM checks
    ACCEPT = "accept"  # terminal clean, LLM skipped (not sampled)


class FinalStatus(StrEnum):
    CLEAN = "clean"
    QUARANTINED = "quarantined"
    REVIEW = "review"


class RemediationAction(StrEnum):
    NONE = "none"
    CORRECT_CATEGORY = "correct_category"
    CORRECT_FIELD = "correct_field"
    SUGGEST_MERGE = "suggest_merge"
    REJECT = "reject"


class RoutingDecision(BaseModel):
    """What the triage gate decided for one event."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    action: RouteAction
    checks: tuple[str, ...] = ()  # LLM check names to run when action == ESCALATE
    reason: str
    sampled: bool = False


class EscalationResult(BaseModel):
    """Outcome of running the escalation band for one event."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    verdicts: list[Verdict]  # one authoritative LLM verdict per check that ran
    escalated_checks: tuple[str, ...] = ()  # checks escalated cheap-tier -> expensive-tier
    cost_usd: float = 0.0  # includes intermediate (escalated-away) calls
    budget_exhausted: bool = False


class RemediationProposal(BaseModel):
    """A proposed fix. Never applied automatically (decision 5)."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    action: RemediationAction
    reason: str
    target_field: str | None = None
    proposed_value: str | None = None
    merge_target_id: str | None = None
    confidence: float | None = None
    proposer: str
    prompt_version: str | None = None
    auto_applicable: bool = False  # informational only; pipeline never acts on it


class EventOutcome(BaseModel):
    """The Final Verdict: the complete record of what happened to one event."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    final_status: FinalStatus
    rule_report: RuleReport | None = None
    llm_verdicts: list[Verdict] = Field(default_factory=list)
    routing: RoutingDecision | None = None
    remediation: RemediationProposal | None = None
    total_cost_usd: float = 0.0
    prompt_versions: dict[str, str] = Field(default_factory=dict)  # check -> prompt_version
    parse_error: ParseError | None = None
    error: str | None = None  # set when a stage failed (routes to REVIEW)


# --------------------------------------------------------------------------- #
# Component protocols
# --------------------------------------------------------------------------- #


@runtime_checkable
class RoutingPolicy(Protocol):
    """Pure: derives a routing decision from the rule report. No I/O."""

    def decide(self, event: ResolvedEvent, report: RuleReport) -> RoutingDecision: ...


@runtime_checkable
class EscalationRouter(Protocol):
    """Runs the decision's checks via injected judges, escalating only the
    uncertain check, gated by the shared BudgetGuard."""

    async def route(self, event: ResolvedEvent, decision: RoutingDecision) -> EscalationResult: ...


@runtime_checkable
class Remediator(Protocol):
    """Proposes a fix for a flagged event. Never applies it."""

    async def propose(
        self, event: ResolvedEvent, verdicts: Sequence[Verdict]
    ) -> RemediationProposal: ...


@runtime_checkable
class VerdictSink(Protocol):
    """Future storage seam (Phase 5). Upsert keyed by (event_id, check, prompt_version)."""

    async def upsert_verdicts(self, verdicts: Sequence[Verdict]) -> None: ...


@runtime_checkable
class PipelineTraceSink(Protocol):
    """Future monitoring seam (Phase 5). One trace row per finalized event."""

    def on_outcome(self, outcome: EventOutcome) -> None: ...
