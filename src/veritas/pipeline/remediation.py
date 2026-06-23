"""Heuristic remediation: deterministic, proposal-only.

Maps the dominant failing check to a proposed fix. No LLM call and no
auto-apply (decision 5) — the proposal is an audit artifact for a later, separate
apply step. A future LLM-backed remediator can implement the same ``Remediator``
protocol as a drop-in.
"""

from __future__ import annotations

from collections.abc import Sequence

from veritas.domain.models import ResolvedEvent, Verdict, VerdictStatus
from veritas.pipeline.contracts import RemediationAction, RemediationProposal

PROPOSER = "heuristic-remediator@v1"

# Failing check -> proposed remediation. Rule failures and LLM failures both map here.
_ACTION_BY_CHECK: dict[str, RemediationAction] = {
    "semantic_accuracy": RemediationAction.CORRECT_CATEGORY,
    "entity_resolution": RemediationAction.SUGGEST_MERGE,
    "source_credibility": RemediationAction.REJECT,
    "conditional_completeness": RemediationAction.CORRECT_FIELD,
    "category_known": RemediationAction.CORRECT_CATEGORY,
    "exact_duplicate": RemediationAction.REJECT,
    "confidence_floor": RemediationAction.REJECT,
    "referential_integrity": RemediationAction.SUGGEST_MERGE,
}


class HeuristicRemediator:
    """Implements ``Remediator``."""

    async def propose(
        self, event: ResolvedEvent, verdicts: Sequence[Verdict]
    ) -> RemediationProposal:
        fails = [v for v in verdicts if v.status is VerdictStatus.FAIL]
        if not fails:
            return RemediationProposal(
                event_id=event.event_id,
                action=RemediationAction.NONE,
                reason="no failing checks; nothing to remediate",
                proposer=PROPOSER,
            )

        # Drive off the most confident failure (None confidence -> treat as low).
        driver = max(fails, key=lambda v: v.confidence if v.confidence is not None else 0.0)
        action = _ACTION_BY_CHECK.get(driver.check_name, RemediationAction.REJECT)

        target_field: str | None = None
        proposed_value: str | None = None
        merge_target_id: str | None = None
        if action is RemediationAction.CORRECT_CATEGORY:
            target_field = "category"
        elif action is RemediationAction.CORRECT_FIELD:
            target_field = "attributes"
        elif action is RemediationAction.SUGGEST_MERGE:
            merge_target_id = event.company2_id

        return RemediationProposal(
            event_id=event.event_id,
            action=action,
            reason=f"{driver.check_name} failed: {driver.reason}",
            target_field=target_field,
            proposed_value=proposed_value,
            merge_target_id=merge_target_id,
            confidence=driver.confidence,
            proposer=PROPOSER,
            prompt_version=driver.prompt_version,
            auto_applicable=False,
        )
