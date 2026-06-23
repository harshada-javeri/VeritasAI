"""Tiered escalation: run the cheap judge per check, escalate only the uncertain one.

For each check in the routing decision: run the primary (cheap-tier) judge; if it
returns ``uncertain`` and an escalation (expensive-tier) judge is configured for that
check, re-run *only that check* on the expensive tier and treat its verdict as
authoritative. The whole event is never re-evaluated (decision 4). The shared
``BudgetGuard`` is checked before every call so the router degrades gracefully when
the budget is exhausted rather than crashing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from veritas.config import Settings, get_settings
from veritas.domain.models import ResolvedEvent, VerdictStatus
from veritas.judges.anthropic import AnthropicJudge
from veritas.judges.protocol import LLMJudge
from veritas.llm_gateway.budget import BudgetGuard
from veritas.llm_gateway.errors import BudgetExceededError
from veritas.llm_gateway.types import Completer
from veritas.pipeline.contracts import EscalationResult, RoutingDecision
from veritas.prompt_registry.registry import PromptRegistry


@dataclass(frozen=True, slots=True)
class CheckJudges:
    """The judge tiers for one check: a cheap primary and an optional escalation."""

    primary: LLMJudge
    escalation: LLMJudge | None = None


class TieredEscalationRouter:
    """Implements ``EscalationRouter``."""

    def __init__(self, judges: Mapping[str, CheckJudges], budget: BudgetGuard) -> None:
        self._judges = dict(judges)
        self._budget = budget

    async def route(self, event: ResolvedEvent, decision: RoutingDecision) -> EscalationResult:
        verdicts = []
        escalated: list[str] = []
        cost = 0.0
        exhausted = False

        for check in decision.checks:
            pair = self._judges.get(check)
            if pair is None:
                continue  # no judge configured for this check; skip (fewer verdicts)
            try:
                self._budget.ensure_available()
            except BudgetExceededError:
                exhausted = True
                break

            primary = await pair.primary.evaluate(event)
            cost += primary.cost_usd or 0.0
            authoritative = primary

            if primary.status is VerdictStatus.UNCERTAIN and pair.escalation is not None:
                try:
                    self._budget.ensure_available()
                except BudgetExceededError:
                    exhausted = True
                    verdicts.append(primary)  # keep the cheap verdict we did get
                    break
                escalated_verdict = await pair.escalation.evaluate(event)
                cost += escalated_verdict.cost_usd or 0.0
                authoritative = escalated_verdict
                escalated.append(check)

            verdicts.append(authoritative)

        return EscalationResult(
            event_id=event.event_id,
            verdicts=verdicts,
            escalated_checks=tuple(escalated),
            cost_usd=cost,
            budget_exhausted=exhausted,
        )


def build_default_escalation_router(
    *,
    gateway: Completer,
    registry: PromptRegistry,
    budget: BudgetGuard,
    settings: Settings | None = None,
) -> TieredEscalationRouter:
    """Wire the standard checks: Haiku primary + Sonnet escalation for the
    cheap-tier checks; Sonnet-only for entity resolution (already top tier)."""
    resolved = settings if settings is not None else get_settings()
    sonnet = resolved.models.sonnet

    def judge(check: str, prompt: str, model: str | None) -> AnthropicJudge:
        return AnthropicJudge(
            gateway=gateway,
            registry=registry,
            check_name=check,
            prompt_name=prompt,
            model=model,
        )

    judges = {
        "semantic_accuracy": CheckJudges(
            primary=judge("semantic_accuracy", "semantic_accuracy", None),  # spec pins Haiku
            escalation=judge("semantic_accuracy", "semantic_accuracy", sonnet),
        ),
        "source_credibility": CheckJudges(
            primary=judge("source_credibility", "source_credibility", None),
            escalation=judge("source_credibility", "source_credibility", sonnet),
        ),
        "entity_resolution": CheckJudges(
            primary=judge("entity_resolution", "entity_resolution", None),  # spec pins Sonnet
            escalation=None,
        ),
    }
    return TieredEscalationRouter(judges, budget)
