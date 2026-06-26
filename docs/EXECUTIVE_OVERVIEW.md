# VeritasAI — Executive Overview

*A five-minute read for a VP Engineering, CDO, or technical reviewer.*
*Last updated: 2026-06-24 · Branch `main` (pushed to origin).*

> **One line:** VeritasAI is an AI-native data-quality platform for a news-event intelligence feed —
> **rules gate, LLMs judge, humans backstop, and everything is logged, versioned, and measured.**

---

## Problem

A news-event intelligence feed delivers ~620K JSON:API records — "Company A acquires Company B,"
"Company C hires an executive," "Company D launches a product" — extracted from news articles. Other
teams consume these events *as truth*. The data has real, measurable quality problems:

- **Mislabeled events** — the text describes a partnership but it's tagged as an acquisition.
- **Wrong entities** — the law firm is recorded as the defendant; the subject and object are swapped.
- **Low-signal sources** — PR puffery and syndicated reprints masquerading as genuine news.
- **Stale events** — a 2014 event resurfacing as if it happened this week.
- **Structural defects** — broken references, impossible dates, malformed IDs, duplicates.

A wrong "this event is good" doesn't stay contained — it flows downstream into other teams'
decisions, where it's expensive to trace back and corrosive to trust in the entire feed. The
business needs quality that is **trustworthy, attributable, and defensible**, not just "mostly right."

---

## Why Existing Solutions Fail

- **Pure rules engines** catch structural defects (bad dates, broken references, malformed IDs) but
  are blind to *meaning*. No regex can tell you whether a summary actually describes the category
  it's labeled with, or whether a source is genuine news versus a press release.
- **Pure LLM approaches** are expensive, slow, and unmeasured. Running a model on 100% of 620K
  records burns budget on questions a `$0` rule could have answered, and a "loose prompt" with no
  eval harness is a judge nobody has checked — confidently wrong on the cases that matter most.
- **Black-box scoring** ("data quality is 94%") is a vanity metric. It tells an operator the weather,
  not where the leak is — *which source* started degrading, *when*, and *why*.

VeritasAI's answer is the **split**: *reach for a rule first; reach for an LLM only when the question
is semantic, contextual, or fuzzy — and when you do, measure the judge before you trust it.* Rules do
the cheap, exact, deterministic work on everything; LLMs do the judgment work only on what rules can't
settle; humans own the genuinely ambiguous tail; and every decision is traced, versioned, and costed.

---

## Architecture

Layered, each layer depending only on lower ones — dependency injection throughout, every boundary
strongly typed and expressed as a Protocol:

```
ingest → rules (gate) → pipeline (routing → escalation → remediation → finalize)
                              │            │
                          judges ── llm_gateway (pin/route/retry/cost/budget)
                              │            │
                       prompt_registry   monitoring (metrics/logging/alerts)
                              │
                            store (SQLAlchemy)        evals (replay-backed)
```

The flow end to end:

```
JSONL feed → INGEST → RULE TRIAGE → LLM ESCALATION → REMEDIATE → STORE + OBSERVE → DASHBOARD
             (parse)  (free, 100%)  (only on doubt)  (propose)   (trace every call)  (read-only)
```

- **Rules = the gate.** Run first, on everything, free. Hard fail → quarantine, no LLM spend.
- **LLMs = the judge.** Run only on what rules can't settle. Cheap model (Haiku) first; escalate the
  *uncertain* check only to the stronger model (Sonnet).
- **Humans = the backstop.** Ambiguous and low-confidence cases route to a human review queue.
- **Everything is logged.** One trace row per call: prompt version, model, tokens, cost, latency,
  verdict — append-only and attributable.

**Stack:** Python 3.12, Pydantic v2, async SQLAlchemy 2.0, `uv`, MyPy strict, Ruff. Vendor-agnostic
LLM access; develops and tests entirely offline against a `ReplayJudge` (zero live spend).

---

## Key Design Decisions

- **Single `Verdict` currency** for both rules and LLM judges → uniform storage, routing, and tracing.
- **Tolerant parser, validating rules** — the parser never rejects content problems; rules flag them.
- **Pinned model IDs** (never `*-latest`) and **structured output only** (no fragile prose parsing).
- **Tiered escalation** — cheap judge first; escalate *only the uncertain check* to the stronger model,
  never re-evaluate the whole event. This is the primary cost lever.
- **Fail-safe routing** — every ambiguity or error biases toward human REVIEW, never toward silently
  passing bad data. The system errs toward a person, which is the correct bias for data quality.
- **Remediation is proposal-only** — the system suggests a fix and explains its reasoning; a human
  approves. It never silently rewrites data.
- **Cost is a designed concern** — a `BudgetGuard` gates every call; cost is computed per call from a
  pinned pricing table; the budget degrades gracefully (remaining work → REVIEW) rather than crashing.
- **Idempotency keyed on `(event_id, check_name, prompt_version, model)`** — re-runs overwrite cleanly
  and never double-write.
- **Optional, no-op-by-default seams** for storage and monitoring — the pipeline runs fully in-memory
  without either, and they attach as injected seams without changing any contract.
- **Replay everywhere** — evals and pipeline tests run offline and deterministically, for $0.

---

## Production Readiness Findings

An independent review board (Principal Engineer, Staff AI Platform Engineer, SRE, Security) assessed
the repository. The honest verdict:

> **A 9/10 design wearing a 3/10 production surface — and it knows it.**

This is a **production-shaped reference implementation**, exactly as scoped: senior-grade boundaries,
reproducibility, and cost discipline, built offline by design. It would *promote* to production along
a clear path without an architectural rewrite — but that promotion work is real.

**Strengths the board called out:** clean hexagonal layering ("no-op by absence" seams), determinism
as architecture (replay, deterministic sampling, idempotent writes, pinned models), engineered cost
control, and uncompromising hygiene. It *fails safe* toward human review, and it *documents its own
deferrals* honestly.

**Gaps that stand between it and a live launch (all scoped out by design):**

- The **live path has never run** — every test is offline; auth, rate limits, and real latency are
  unvalidated.
- **State is in-process** — the budget guard and dedup set live in one process's heap; no horizontal
  scale-out story yet.
- **Replay re-spends** — idempotency is enforced at the DB write, not before the model call.
- **No operational plane** — no CI/CD, container, health checks, alert *delivery*, or real telemetry
  export (the alert logic exists; nothing routes it anywhere yet).
- **Security is the weakest domain** — secrets handling, prompt-injection hardening, and PII/retention
  controls are unaddressed, as expected for an offline build.

None of these are surprises; the build contract scoped them out. They are the roadmap, not rot.

---

## Stakeholder Feedback Incorporated

Firmable's review gave three priorities, and each one **validated a decision already in the build**:

1. **Precision matters more than coverage.** → Confirmed by the fail-safe-to-REVIEW routing and
   proposal-only remediation: the system never auto-closes on uncertainty. We now optimize and gate
   on **precision** explicitly, and monitor recall for erosion rather than maximizing it.
2. **Humans must own ambiguous decisions.** → Confirmed by the founding "humans backstop" principle.
   The "uncertain" band is reframed as the product's center of gravity — a context-rich handoff to a
   named owner, not an error state to automate away.
3. **Source-level drift analysis beats aggregate quality trends.** → Confirmed by the existing source
   lineage (`most_relevant_source` → article domain) and the source-credibility judge. We're promoting
   *source* from an input field to the **primary axis** of quality, cost, and drift analysis.

Net: no architectural change required — the feedback sharpens priorities and sets the Phase 8 agenda.
(Full analysis in [STAKEHOLDER_FEEDBACK_INTEGRATION.md](STAKEHOLDER_FEEDBACK_INTEGRATION.md).)

---

## Current Status

**All phases 0–7 complete, committed, and pushed to `main`.**

| Phase | Delivered |
|---|---|
| **0 — Foundations** | Config (pinned models, thresholds, budget), domain models, tolerant streaming JSON:API parser |
| **1 — Rules engine** | 8 deterministic rules, registry/engine/report, rollup precedence |
| **2 — LLM gateway & judges** | Vendor-agnostic gateway (pin/route/retry/cost/budget), prompt registry, 3 judges + ReplayJudge |
| **3 — Evaluation framework** | Offline eval harness (`make eval`), labeled datasets, P/R/F1 + regression gate |
| **4 — Pipeline orchestration** | Routing, tiered escalation, proposal-only remediation, budget-guarded async runner |
| **5 — Storage layer** | Async SQLAlchemy 2.0, SQLite-default/Postgres-ready, idempotent upserts, append-only trace |
| **6 — Monitoring** | Metrics sinks, JSON logging, optional OpenTelemetry, AlertEvaluator (5 alert kinds) |
| **7 — Dashboard** | Read-only Streamlit Decision Intelligence Console — 7 workspaces over the storage layer |

**Repository metrics (current gates):**

| Gate | Status |
|---|---|
| Tests | **157 passed** (130 pipeline + 27 dashboard) |
| MyPy | **strict — clean (115 source files)** |
| Ruff | **clean** |
| Eval harness | `make eval` exits 0 |

The Phase 7 console ships 7 workspaces — Trust Center, Cost & Efficiency, Data Quality Intelligence,
Human Review, Platform Health, AI Judge Performance, and an Event Detail drill-down — with strict
layering (repository → service → view-model → component → page) and every workspace verified to render
headlessly.

---

## Future Roadmap

Phase 8 turns Firmable's feedback into the next build: **Source Intelligence & Root-Cause.**

### Source intelligence
Promote *source* (publisher domain / vendor) from an input field to a first-class entity. Aggregate
verdicts, cost, and outcomes **by source** so the system answers directly: which sources originate the
most events, what are their per-check pass/fail rates, and how much review load and spend each one
generates. This is the lineage layer the V1 console explicitly deferred — read-and-aggregate work over
data already persisted. It feeds a transparent, explainable **per-vendor quality score** (same
philosophy as the trust index — a weighted roll-up that shows its formula, never a black-box number)
and **source-level drift detection**: the canary discipline extended from model/prompt drift to
*source* drift, so an alert names the source and the moment — "vendor X's credibility fell starting
June 18" — not just "quality dropped."

### Human review workflow
Evolve the review queue from a read-only list into a **diagnosis-and-ownership surface**. Surface the
highest-leverage ambiguous items first, carry full context (evidence span, judge reasoning, source
credibility, lineage), and make every ambiguous decision have a *named owner* of record. Chain it to
the drill-down spine so an operator goes symptom → contributing events → event detail → owned decision
without manual spelunking. This is the direct build-out of "humans own ambiguity, with context."

### Metrics history
Build the durable time-series layer the V1 console only approximates today (it works off `created_at`
on current rows). A `quality_metrics_daily`-style rollup turns "quality this moment" into "quality over
time, attributable by source and check" — pre-aggregated so dashboards never scan raw rows, and the
foundation that makes drift detection and trend analysis cheap and fast at feed scale.

*Beyond Phase 8, the production-readiness roadmap remains: prove the live path, externalize state to*
*Postgres/Redis, close the replay-respend gap, deliver alerts and telemetry, and harden security.*
