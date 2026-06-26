---
name: news-events-quality-check
version: 1.0.0
owner: data-quality-team
status: stable
summary: Validate a single news-event record (or a batch) with the rules-gate → LLM-judge → human-backstop strategy and return per-check verdicts plus a defensible rollup.
depends_on:
  rules: veritas.rules (8 deterministic checks)
  prompts:
    - semantic_accuracy.v1   (model: claude-haiku-4-5-20251001)
    - source_credibility.v1  (model: claude-haiku-4-5-20251001 → escalate claude-sonnet-4-6)
    - entity_resolution.v1   (model: claude-sonnet-4-6)
  eval_sets:
    - semantic_accuracy_v1
    - source_credibility_v1
    - entity_resolution_v1
  output_schema: judge_output (verdict / confidence / reason / evidence_span)
---

# Skill — News-Events Quality Check

Validate a news-event record and return a defensible quality decision. This is the
operational entry point to VeritasAI's core loop: **rules gate, LLMs judge, humans
backstop — every decision logged, versioned, costed, and measured.**

The skill is renderer-agnostic: the same specification runs in a notebook, in CI, or
inside an agent loop. It produces *data* (per-check verdicts + a rollup), never side
effects — it proposes nothing and writes nothing. Acting on the result (quarantine,
escalate, queue for review) is the caller's decision, governed by the interpretation
guide below.

---

## When to trigger

Run this skill whenever a `news_event` record needs a quality decision:

- **On ingest** — a new event arrives from the feed and must be validated before it is
  trusted downstream.
- **On change** — an existing event's `category`, `summary`, `article_sentence`, or its
  linked entities (`company1`, `company2`, `most_relevant_source`) changed.
- **On reprocess** — a prompt or rule version was upgraded and you are re-judging
  affected events. (The verdict idempotency key `(event_id, check_name, prompt_version,
  model)` makes re-runs safe: same inputs overwrite cleanly, never double-count.)
- **On audit** — a random sample of already-passed events, to catch silent drift.

Do **not** trigger it on a record that only failed a structural rule and was already
quarantined — the rules gate short-circuits LLM spend, and so should you.

---

## Inputs

A single resolved event (or an array of them for batch mode):

```json
{
  "event": {
    "event_id": "uuid",
    "category": "launches",
    "summary": "Acme launches CloudWidget",
    "article_sentence": "Acme today launched CloudWidget.",
    "found_at": "2025-03-04T10:00:00Z",
    "confidence": 0.82
  },
  "included": {
    "company1": { "name": "Acme", "domain": "acme.com" },
    "company2": null,
    "most_relevant_source": {
      "url_domain": "techcrunch.com",
      "title": "Acme ships CloudWidget",
      "body_excerpt": "Independent reporting on the launch ..."
    }
  }
}
```

- **Required:** `event.event_id`, `event.category`, `event.summary`.
- **Used by LLM checks when present:** `article_sentence` (semantic accuracy, entity
  resolution); `company1`/`company2` name+domain (entity resolution); source
  `url_domain`/`title`/`body_excerpt` (source credibility).
- **Tolerant by design:** missing optional fields downgrade an LLM check to `uncertain`
  (→ review), never a crash. The parser never rejects content problems; the rules flag them.

---

## Outputs

Per-check verdicts (uniform `Verdict` shape for both rules and LLM judges) plus an
overall rollup:

```json
{
  "event_id": "uuid",
  "rollup": "review",
  "rule_verdicts": [
    {"check_name": "referential_integrity", "check_type": "rule", "status": "pass", "confidence": null, "reason": "all relationship ids resolve", "evidence_span": null},
    {"check_name": "confidence_floor", "check_type": "rule", "status": "pass", "confidence": null, "reason": "0.82 ≥ 0.15", "evidence_span": null}
  ],
  "llm_verdicts": [
    {"check_name": "semantic_accuracy", "check_type": "llm", "status": "pass", "confidence": 0.93, "reason": "text describes a launch", "evidence_span": "today launched CloudWidget", "prompt_version": "v1", "model": "claude-haiku-4-5-20251001"},
    {"check_name": "source_credibility", "check_type": "llm", "status": "uncertain", "confidence": 0.49, "reason": "domain ambiguous", "evidence_span": "techcrunch.com", "prompt_version": "v1", "model": "claude-haiku-4-5-20251001"}
  ],
  "cost_usd": 0.00072,
  "rollup_reason": "source_credibility uncertain → human review"
}
```

`rollup` is one of `clean | quarantined | review`. Every LLM verdict carries its
`prompt_version` and `model` so the decision is always attributable to an exact judge.

---

## Dependencies

| Stage | Component | Version pin |
|---|---|---|
| Rules gate | `veritas.rules` — 8 deterministic checks | code-versioned |
| Check A — semantic accuracy | `semantic_accuracy.v1` | `claude-haiku-4-5-20251001` |
| Check B — source credibility | `source_credibility.v1` | `claude-haiku-4-5-20251001`, escalate `claude-sonnet-4-6` |
| Check C — entity resolution | `entity_resolution.v1` | `claude-sonnet-4-6` |
| Output contract | `judge_output` schema | `verdict / confidence / reason / evidence_span` |
| Measured by | eval sets `*_v1` | see [docs/eval-results.md](../../docs/eval-results.md) |

Model IDs are **pinned, never `-latest`** — a floating model silently changes verdicts.
Offline/dev runs use `ReplayJudge` (recorded verdicts, zero spend, deterministic).

---

## Interpretation guide (verdict precedence)

Apply in order; the first matching rule wins. This mirrors the pipeline's
`_finalize` rollup so the skill and the pipeline never disagree.

1. **Parse error** → `quarantined`. The record is structurally unusable; no checks run.
2. **Any rule hard-fail** (e.g. `referential_integrity`, `exact_duplicate`,
   `confidence_floor`, `event_id_uuid`) → `quarantined`. **No LLM is called** — the gate
   protects the budget.
3. **Any LLM `fail` with `confidence ≥ 0.70`** → `quarantined` (a confident defect), with
   a remediation proposal attached (see the remediation skill).
4. **Any rule `review`, OR budget exhausted, OR a stage error** → `review`.
5. **Any LLM verdict that is not `pass`** (an `uncertain`, or a low-confidence `fail`)
   → `review`. *This is where humans own the ambiguous tail — by design, not by accident.*
6. **Otherwise** → `clean`.

The bias is deliberate and one-directional: **toward human review, never toward silently
passing bad data.** A precise "this is a problem" signal matters more than catching every
edge — an over-flag costs a reviewer a minute; a missed defect ships downstream as truth.

---

## Example invocation

**As an agent skill / library call (offline, replay):**

```text
load skill: news-events-quality-check
input: { event: {...}, included: {...} }
→ runs rules gate; escalates only checks the rules can't settle;
  returns per-check verdicts + rollup
```

**In the pipeline (the same logic, batched and budget-guarded):**

```bash
# Validates a stream of events with the full rules → escalate → finalize loop.
uv run python -m veritas.pipeline --input datasets/  # (driven from config; ReplayJudge offline)
```

**Measure the judges before trusting them:**

```bash
make eval     # per-check precision/recall/F1 + regression gate; exits non-zero on regression
```

---

## Example output (a record that routes to review)

Input: `{ event: { event_id: "sc-10", category: "partners_with", summary: "Unclear
blogspot post on Foo-Bar" }, included: { most_relevant_source: { url_domain:
"foo-bar.blogspot.com" } } }`

```json
{
  "event_id": "sc-10",
  "rollup": "review",
  "rule_verdicts": [{"check_name": "category_known", "check_type": "rule", "status": "pass", "reason": "partners_with is a known category"}],
  "llm_verdicts": [
    {"check_name": "source_credibility", "check_type": "llm", "status": "uncertain", "confidence": 0.49, "reason": "low-signal blog source; cannot confirm original reporting", "evidence_span": "blogspot.com", "prompt_version": "v1", "model": "claude-haiku-4-5-20251001"}
  ],
  "cost_usd": 0.00031,
  "rollup_reason": "source_credibility uncertain (conf 0.49 < 0.70) → human review (precedence rule 5)"
}
```

The judge was honestly uncertain on a low-signal source, so the event becomes a human
decision rather than a guessed pass — exactly the intended behavior.

---

## Versioning strategy

- **Skill version** (`1.0.0`, semantic) — bump **major** on an output-shape or
  precedence-semantics change (breaks callers), **minor** on an added check or field
  (backward-compatible), **patch** on doc/clarity fixes.
- **Prompt versions** are independent and pinned per check (`semantic_accuracy.v1`, …). A
  prompt change is a new version file with its own recorded eval predictions; the eval
  harness regression-gates v(N) against v(N-1) before promotion. Every verdict records the
  `prompt_version` that produced it, so a verdict is reproducible and a prompt change is a
  `GROUP BY prompt_version` away from a before/after comparison.
- **Eval-set versions** are independent of prompt versions: hold the labeled set fixed and
  vary the prompt to compare; bump the eval-set version only when you add or relabel
  examples. See [docs/evaluation-strategy.md](../../docs/evaluation-strategy.md).
- **Model pins** live in config. Never float to `-latest`; a model change under a fixed
  prompt is detected by the scheduled canary eval on the frozen labeled set.

Related: [news-events-remediation](../news-events-remediation/SKILL.md) — proposes a fix
for a record this skill flagged.
