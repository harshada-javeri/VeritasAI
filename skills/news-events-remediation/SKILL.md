---
name: news-events-remediation
version: 1.0.0
owner: data-quality-team
status: stable
summary: Take a flagged news-event record and its verdicts, and PROPOSE a fix (corrected category, suggested merge, field correction, or reject-with-reason) with an explained rationale. Proposes only — never writes.
depends_on:
  upstream_skill: news-events-quality-check (supplies the verdicts this skill reasons over)
  proposer: heuristic-remediator@v1 (veritas.pipeline.remediation)
  contract: RemediationProposal (veritas.pipeline.contracts)
---

# Skill — News-Events Remediation

Take a record that the [quality-check skill](../news-events-quality-check/SKILL.md) flagged
(`quarantined` or `review`) and propose a concrete fix, with the reasoning that motivates
it. This skill **proposes, never silently writes** — its output is a decision *accelerator*
for a human, not an autonomous mutation. The pipeline attaches the proposal to the event
outcome and routes it to the review queue; a person accepts, edits, or rejects it.

This boundary is a product requirement, not a limitation: humans own the resolution of
ambiguous and failed records. The skill makes that ownership *fast* by pre-computing the
most likely correct action and showing its evidence.

---

## When to trigger

Run this skill on a record that has **at least one failing verdict** — i.e. the
quality-check rollup is `quarantined` or `review` and the cause is a `fail` (not merely an
`uncertain`). Specifically:

- After `news-events-quality-check` returns a non-clean rollup driven by a failed rule or
  a failed LLM judge.
- During remediation-queue processing, to populate the accept/reject/edit proposal a
  reviewer will act on.

Do **not** trigger it when there are no failing checks (nothing to remediate — the skill
returns `action: none`), or to "auto-fix" records without a human in the loop. The output
is `auto_applicable: false` by contract; treat any future `true` as advisory only.

---

## Inputs

The flagged event plus the verdicts the quality-check skill produced:

```json
{
  "event": {
    "event_id": "uuid",
    "category": "launches",
    "summary": "Umbrella sues Hooli",
    "company2_id": "comp-hooli"
  },
  "verdicts": [
    {"check_name": "semantic_accuracy", "check_type": "llm", "status": "fail", "confidence": 0.91, "reason": "text describes a lawsuit, not a launch", "prompt_version": "v1", "model": "claude-haiku-4-5-20251001"}
  ]
}
```

- **Required:** `event.event_id`, and at least one `verdict` (rule or LLM).
- **Used to shape the proposal:** `event.category`, `event.company2_id` (merge target),
  and the failing verdict's `check_name`, `confidence`, `reason`, `prompt_version`.

---

## Outputs

A single `RemediationProposal`:

```json
{
  "event_id": "uuid",
  "action": "correct_category",
  "reason": "semantic_accuracy failed: text describes a lawsuit, not a launch",
  "target_field": "category",
  "proposed_value": null,
  "merge_target_id": null,
  "confidence": 0.91,
  "proposer": "heuristic-remediator@v1",
  "prompt_version": "v1",
  "auto_applicable": false
}
```

The proposal is **driven by the most confident failure** (a confidently-wrong signal is the
most actionable). `auto_applicable` is always `false` — informational only; the pipeline
never acts on it.

---

## Dependencies

| Concern | Component |
|---|---|
| Verdicts in | `news-events-quality-check` skill output |
| Proposer | `heuristic-remediator@v1` (`veritas.pipeline.remediation`) |
| Output contract | `RemediationProposal` (`veritas.pipeline.contracts`) |
| Action vocabulary | `RemediationAction`: `none / correct_category / correct_field / suggest_merge / reject` |

The shipped proposer is **deterministic and explainable** (no LLM call, no guessing). An
LLM-backed remediator can implement the same `Remediator` protocol later without changing
this skill's contract.

---

## Interpretation guide (failing check → proposed action)

The proposer maps the dominant failing check to an action. The mapping is intentionally
conservative — each action is a *suggestion with evidence*, not an instruction:

| Failing check | Proposed action | Meaning for the reviewer |
|---|---|---|
| `semantic_accuracy` | `correct_category` | The label likely doesn't match the text — pick the right category. |
| `category_known` | `correct_category` | The category is not in the known set — map it to a valid one. |
| `entity_resolution` | `suggest_merge` | The linked company may be wrong — consider merging to `company2`. |
| `referential_integrity` | `suggest_merge` | A relationship id is dangling — resolve or merge the entity. |
| `conditional_completeness` | `correct_field` | A category-required field is missing — fill `attributes`. |
| `source_credibility` | `reject` | Source reads as PR/marketing/reprint — reject with reason. |
| `exact_duplicate` | `reject` | A repeat of an already-seen event — reject as duplicate. |
| `confidence_floor` | `reject` | Confidence below floor — reject as noise. |
| *(no failing check)* | `none` | Nothing to remediate. |

The reviewer always sees the **`reason`** (the failing check's own rationale) and the
**`confidence`**, so they accept/edit/reject on evidence, not on the action label alone.

---

## Example invocation

```text
load skill: news-events-remediation
input: { event: {...}, verdicts: [ ...from quality-check... ] }
→ returns one RemediationProposal (proposal-only; auto_applicable=false)
```

In the pipeline this runs automatically after any check fails; the proposal is attached to
the `EventOutcome` and surfaced in the dashboard's Human Review workspace as an
accept / reject / edit decision.

---

## Example output (a mislabeled-category fix)

Input: event `sa-06` (`category: launches`, summary `"Umbrella sues Hooli"`) with a
high-confidence `semantic_accuracy` failure.

```json
{
  "event_id": "sa-06",
  "action": "correct_category",
  "reason": "semantic_accuracy failed: text describes a lawsuit, not a launch",
  "target_field": "category",
  "proposed_value": null,
  "merge_target_id": null,
  "confidence": 0.91,
  "proposer": "heuristic-remediator@v1",
  "prompt_version": "v1",
  "auto_applicable": false
}
```

The proposer correctly identifies the category as the field to fix and surfaces *why* (the
judge's own reason) — but leaves the corrected value to the human, because choosing the
right replacement category is a judgment call, and judgment calls are owned by people.

---

## Versioning strategy

- **Skill version** (`1.0.0`, semantic) — major on a contract change to
  `RemediationProposal` or the action vocabulary; minor on a new mapped check or action;
  patch on doc fixes.
- **Proposer version** is pinned in the output (`proposer: "heuristic-remediator@v1"`), so
  every proposal is attributable to the exact logic that produced it. Swapping in an
  LLM-backed proposer bumps the proposer id (e.g. `llm-remediator@v1`) and records its
  `prompt_version`, without changing this skill's input/output contract.
- **The proposal carries the originating `prompt_version`** of the failing judge, so a fix
  is traceable back to the precise judge and prompt that flagged it.

Related: [news-events-quality-check](../news-events-quality-check/SKILL.md) — produces the
verdicts this skill remediates.
