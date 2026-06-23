# VeritasAI — Pipeline Design (Phase 4, as built)

*Implementation companion to [phase4-pipeline-review.md](phase4-pipeline-review.md). Reflects
the approved architecture decisions and what shipped in `src/veritas/pipeline/`.*
*Date: 2026-06-23.*

The pipeline orchestrates the components from Phases 0–3 into one lifecycle. It adds **no new
judgement** — it routes, escalates, proposes, and rolls up, with the `BudgetGuard` as the only
throttle. Everything is replay-backed and deterministic for tests.

```
Dataset → Parser → RuleEngine → RoutingDecision → EscalationRouter → LLMJudge → RemediationProposal → EventOutcome
```

## Approved decisions, as implemented

| # | Decision | Where |
|---|---|---|
| 1 | Rules **FAIL → QUARANTINE**, no LLM spend | `DefaultRoutingPolicy` → `RouteAction.QUARANTINE`; runner skips the router |
| 2 | Rules **REVIEW → escalate** to LLM | policy → `ESCALATE` with `escalation_checks` |
| 3 | Rules **CLEAN → 20% sampling** (configurable) | `DefaultRoutingPolicy(clean_sample_rate=…)`; `ACCEPT` otherwise |
| 4 | **Escalate only the uncertain check** | `TieredEscalationRouter`: per-check Haiku→Sonnet, never re-runs the event |
| 5 | **Proposal only**, never auto-apply | `HeuristicRemediator` → `RemediationProposal(auto_applicable=False)` |
| 6 | **Bounded async**, configurable, shared budget, no scheduler | `PipelineRunner.run` windowed pool + shared `BudgetGuard` |

**Note vs the design review:** the doc anticipated an `AUTO_REMEDIABLE` terminal state. Decision 5
(never auto-apply) makes that misleading, so `FinalStatus` is just `CLEAN / QUARANTINED / REVIEW`,
with a `RemediationProposal` *attached* whenever any check failed.

## Sampling is deterministic, not random

`clean_sample_rate` selects events by a stable hash of `event_id`
(`sha256(event_id)[:8] / 0xFFFFFFFF < rate`). The same event always lands the same way, so the
20% sample is **idempotent across re-runs** — a precondition for resumability and for the storage
upsert (Phase 5). No `random` anywhere.

## Tiered escalation (decision 4)

`TieredEscalationRouter` holds, per check, a `CheckJudges(primary, escalation)`. For each check in
the decision: run `primary` (cheap tier, e.g. Haiku); if it returns `uncertain` *and* an escalation
judge exists, re-run **only that check** on the expensive tier (Sonnet) and treat that verdict as
authoritative. `EscalationResult.escalated_checks` records which escalated; `cost_usd` includes the
intermediate (escalated-away) call even though only the authoritative verdict is kept. Any judge
implementing the `LLMJudge` protocol slots in — so `ReplayJudge` makes the whole router offline.

## Finalize rollup (`PipelineRunner._finalize`)

Mirrors README §5 precedence, and **respects rule uncertainty even when the LLM passes**:

1. `parse_error` → `QUARANTINED`.
2. rule `QUARANTINED` → `QUARANTINED` (no LLM ran).
3. any LLM `FAIL` with `confidence ≥ llm_fail_min_confidence` → `QUARANTINED` (+ proposal).
4. rule `REVIEW`, or `budget_exhausted`, or a stage `error` → `REVIEW`.
5. any LLM non-`PASS` (uncertain / low-conf fail) → `REVIEW`.
6. otherwise → `CLEAN`.

So a rule-`REVIEW` event whose semantic judge passes still finalizes as `REVIEW` — the rule's
uncertainty is a different dimension and is not silently overridden.

## Budget integration & failure handling

- One shared `BudgetGuard`. The router calls `ensure_available()` before every judge call; on
  `BudgetExceededError` it stops, sets `budget_exhausted=True`, and returns partial results →
  the runner finalizes those events to `REVIEW`. The run **completes and degrades**, never crashes.
- The runner wraps escalation per event (`try/except`): one bad event sets `error` and routes to
  `REVIEW` rather than killing the stream.
- `ParseError`s in the input stream become `QUARANTINED` outcomes (structural).

## Concurrency (decision 6)

`PipelineRunner.run(items)` is a windowed async pool: it keeps at most `max_concurrency` tasks in
flight (bounding both concurrency *and* live task count), yielding outcomes in completion order
(events are independent). No external scheduler; the `BudgetGuard` is the cost throttle.

## Contracts (all strongly typed — `pipeline/contracts.py`)

`RoutingDecision`, `EscalationResult`, `RemediationProposal`, `EventOutcome` (Pydantic, `extra=forbid`)
and the `RoutingPolicy` / `EscalationRouter` / `Remediator` / `VerdictSink` / `PipelineTraceSink`
Protocols. Every stage consumes and returns these or earlier-phase types (`ResolvedEvent`,
`RuleReport`, `Verdict`). `PipelineRunner` takes all collaborators by injection.

## Integrations wired

- **RuleEngine** ([rules/](../src/veritas/rules/)) — the gate; `RuleReport.status` drives routing.
- **LLMJudge** ([judges/](../src/veritas/judges/)) — primary/escalation judges; `ReplayJudge` for offline runs.
- **PromptRegistry** ([prompt_registry/](../src/veritas/prompt_registry/)) — `build_default_escalation_router`
  constructs `AnthropicJudge`s from the registry (semantic/source on Haiku+Sonnet, entity on Sonnet).
- **BudgetGuard** ([llm_gateway/](../src/veritas/llm_gateway/)) — shared throttle across the run.

## Deferred (seams defined, not built)

`VerdictSink` (storage upsert by `(event_id, check, prompt_version)`) and `PipelineTraceSink`
(one trace row per outcome) are optional injected Protocols with no-op-by-absence behavior — the
runner calls them only when provided. Storage, monitoring, and the dashboard land in Phase 5+ with
no rework to the runner.

## Test coverage (`tests/test_pipeline.py`)

Routing (quarantine/review/accept/escalate + deterministic sampling), tiered escalation
(uncertain→escalate, confident→no escalation, budget-exhausted degrade), remediation
(proposal for fail, none otherwise), and runner end-to-end (clean-pass, high-conf-fail→quarantine
+proposal, rule-quarantine skips LLM, rule-review persists despite LLM pass, accept path,
budget-exhausted→review, bounded-concurrency stream, parse-error handling). All replay-backed.
