# VeritasAI
AI-Native Data Quality Platform for News Event Intelligence using Rules, LLM Evaluation, and Agentic Remediation.

> **In one line:** Rules gate, LLMs judge, humans backstop — and every decision is logged, versioned,
> costed, and measured. Validates ~620K news-event records that downstream teams consume as truth.

**Status:** Phases 0–7 complete · **157 tests passing** · MyPy strict clean (116 files) · Ruff clean · eval gate green.

---

# Quickstart (for reviewers)

Goal: a working system in **under five minutes**, **zero API keys, zero spend**. Everything below
runs fully offline against replay fixtures and a deterministic synthetic demo database.

**Prerequisites:** Python 3.12 and [`uv`](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`).

```bash
# 1. Clone & install (uv creates the venv and resolves the lockfile)
git clone <repo-url> veritas-ai && cd veritas-ai
uv sync

# 2. (Optional) configure — only needed to point at the real feed or live models.
#    Every gate, eval, and the demo dashboard below run WITHOUT this step.
cp .env.example .env        # then set DATASET_ROOT if you have the feed

# 3. Verify the build is green (Ruff + MyPy strict + 157 tests)
make check

# 4. Run the evaluation harness (replay-only, $0) — precision/recall/F1 + regression gate
make eval                   # exits non-zero if a tracked metric regressed

# 5. See the dashboard with data — seed a deterministic synthetic demo DB, then launch
uv run python scripts/seed_demo_db.py
DATABASE_URL="sqlite+aiosqlite:///./veritas-demo.db" \
    uv run streamlit run src/veritas/dashboard/app.py
```

**What you should see**

| Step | Expected result |
|---|---|
| `make check` | `All checks passed!` · `Success: no issues found in 115 source files` · `157 passed` |
| `make eval` | Per-check P/R/F1 table, worst-failure dump, and `no regression` → exit `0` |
| dashboard | All 7 workspaces populated (≈168 demo events) at <http://localhost:8501> |

**Reproduce the committed results:** the numbers in [docs/eval-results.md](docs/eval-results.md) come
straight from `make eval` over the replay fixtures in `src/veritas/evals/datasets/` — re-run it and you
get the same figures (replay is deterministic). The demo DB is also deterministic (fixed RNG seed), so
the dashboard looks identical on every machine.

> **Running against the real feed / live models** is optional and not needed to review the system.
> Point `DATASET_ROOT` at the JSONL feed and drive `PipelineRunner` over it (the storage sinks write
> `./veritas.db`; see [docs/pipeline-design.md](docs/pipeline-design.md)) to populate the dashboard from
> real records; live LLM judges additionally require an Anthropic API key. The default `ReplayJudge`
> path — which everything above uses — needs neither a feed nor a key.

---

# Architecture Overview

Layered, each layer depending only on lower ones — dependency injection throughout, every boundary a
typed Protocol:

```
ingest → rules (gate) → pipeline (routing → escalation → remediation → finalize)
                              │            │
                          judges ── llm_gateway (pin/route/retry/cost/budget)
                              │            │
                       prompt_registry   monitoring (metrics/logging/alerts)
                              │
                            store (SQLAlchemy)        evals (replay-backed)
```

A record's path: **ingest** (tolerant JSON:API parse) → **rule triage** (free, on 100% of records;
hard fail → quarantine, no spend) → **LLM escalation** (only what rules can't settle; cheap judge
first, escalate the *uncertain* check to the stronger model) → **remediation** (proposal-only) →
**store + observe** (every call traced) → **dashboard** (read-only). Stack: Python 3.12, Pydantic v2,
async SQLAlchemy 2.0, `uv`, MyPy strict, Ruff. Develops and tests fully offline against a `ReplayJudge`
(zero live spend).

# Design Principles

- **Reach for a rule first.** Reach for an LLM only when the question is semantic, contextual, or
  fuzzy — and when you do, measure the judge before you trust it.
- **Single `Verdict` currency** for rules and LLM judges → uniform storage, routing, and tracing.
- **Tolerant parser, validating rules** — the parser never rejects content problems; rules flag them.
- **Pinned model IDs** (never `*-latest`) and **structured output only** — reproducible, parseable.
- **Tiered escalation** — escalate only the uncertain check, never the whole event. The cost lever.
- **Fail-safe routing** — every ambiguity or error biases toward human REVIEW, never silent pass.
- **Remediation is proposal-only** — the system suggests and explains; a human approves.
- **Optional, no-op-by-default seams** — the pipeline runs in-memory without storage or monitoring.
- **Replay everywhere** — evals and pipeline tests run offline and deterministically, for $0.

# Production Readiness Review

An independent board (Principal Engineer, Staff AI Platform Engineer, SRE, Security) assessed the repo.
Verdict: **a 9/10 design wearing a 3/10 production surface — and it knows it.** This is a
production-shaped reference implementation that would *promote* to production without an architectural
rewrite; the remaining work is operational, not structural.

- **Strengths:** clean hexagonal layering, determinism as architecture (replay, idempotent writes,
  pinned models), engineered cost control, uncompromising hygiene, fails safe toward human review.
- **Scoped-out gaps (the roadmap):** the live path has never run; state is in-process; replay
  re-spends; no operational plane (CI/CD, alert delivery, telemetry export); security hardening
  (secrets, prompt injection, PII/retention) is unaddressed.

Full detail: [docs/PRODUCTION_READINESS_REVIEW.md](docs/PRODUCTION_READINESS_REVIEW.md).

# Dashboard

A read-only **Decision Intelligence Console** (Streamlit) over the storage layer, with strict layering
(repository → service → view-model → component → page) and no business logic in the UI. Seven
workspaces: **Trust Center** (transparent quality index — shows the formula, not a magic number),
**Cost & Efficiency**, **Data Quality Intelligence**, **Human Review** (the ambiguous-decision queue
with judge reasoning + evidence), **Platform Health**, **AI Judge Performance** (eval scorecards with
honest small-sample warnings), and an **Event Detail** drill-down — every aggregate links down to a
single event's full verdict stack, trace, and cost. Run: `uv run streamlit run src/veritas/dashboard/app.py`.

To see it populated with no API keys or feed, seed the deterministic demo database first
(`uv run python scripts/seed_demo_db.py`, then set `DATABASE_URL` per the [Quickstart](#quickstart-for-reviewers)).
A per-workspace description, example insights, and a one-command capture process live in
[screenshots/README.md](screenshots/README.md) — screenshots are produced locally and not committed
(no fabricated images).

# Stakeholder Feedback Incorporated

Firmable's review gave three priorities — each **validated a decision already in the build**:

1. **Precision > coverage** → confirmed by fail-safe-to-REVIEW routing and proposal-only remediation;
   we now optimize and gate on **precision** explicitly.
2. **Humans own ambiguous decisions** → confirmed by the founding "humans backstop" principle; the
   review queue is the product's center of gravity, not a fallback.
3. **Source-level drift > aggregate trends** → confirmed by existing source lineage and the
   source-credibility judge; *source* is being promoted to the primary axis of analysis.

Full analysis: [docs/STAKEHOLDER_FEEDBACK_INTEGRATION.md](docs/STAKEHOLDER_FEEDBACK_INTEGRATION.md).

# Roadmap

**Phase 8 — Source Intelligence & Root-Cause** (direct from the feedback above):

- **Source intelligence** — aggregate verdicts, cost, and outcomes *by source/vendor/domain*; a
  transparent per-vendor quality score.
- **Source-level drift detection** — extend the canary discipline from model/prompt drift to *source*
  drift; alerts name the source and the moment ("vendor X degraded starting June 18").
- **Human review workflow** — evolve the queue into a diagnosis-and-ownership surface; every ambiguous
  decision gets a named owner and full context.
- **Metrics history** — a durable daily rollup so quality becomes attributable over time, by source.

Beyond Phase 8: prove the live path, externalize state (Postgres/Redis), close the replay-respend gap,
deliver alerts/telemetry, harden security. See [docs/EXECUTIVE_OVERVIEW.md](docs/EXECUTIVE_OVERVIEW.md).

# How this was built

A first-person account of the architecture approach, the phased build process, the AI tooling used
(Claude Code), which decisions were human-owned vs. AI-assisted, the hardest problems, and what I'd
change: [docs/HOW_I_BUILT_THIS.md](docs/HOW_I_BUILT_THIS.md).

---

# AI-Native Data Quality System — News Events Dataset

**Technical design & build guide** *(full reference below)*
*Author: Senior AI/ML Engineer · Audience: data team, reviewer*

---

## 1. TL;DR — what we're building

A data quality system where **rules do the cheap, deterministic work** and **LLMs do the judgement work** (semantic accuracy, entity resolution, source credibility, freshness). Every LLM call is a *measured, versioned, traced* component — not a loose prompt. The whole thing runs as an agentic pipeline: ingest → rule triage → LLM escalation → remediation proposal → human review queue, with full observability and a cost ceiling.

The guiding rule, in one line:

> **Reach for a rule first. Reach for an LLM only when the question is semantic, contextual, or fuzzy — and when you do, measure the judge before you trust it.**

```
                    ┌─────────────────────────────────────────────────────┐
   JSONL feed  ──▶  │  INGEST  →  RULE TRIAGE  →  LLM ESCALATION  →  REMEDIATE │
  (310K recs)       └────┬───────────┬───────────────┬────────────────┬──────┘
                         │           │               │                │
                         ▼           ▼               ▼                ▼
                     raw store   hard fails      LLM verdicts     fix proposals
                                 (deterministic)  (judged + scored) (auto / human)
                         │           │               │                │
                         └───────────┴───────┬───────┴────────────────┘
                                             ▼
                          TRACE LOG (every call: prompt v, model, cost, latency, decision)
                                             ▼
                          STORAGE  →  DASHBOARD  →  HUMAN REVIEW QUEUE
```

---

## 2. The data (what's actually in it)

Each line is a JSON:API document:

```
{
  "data": [ { news_event } ],     # the event
  "included": [ {company}, {company}, {news_article} ]   # linked entities
}
```

A `news_event` has:

| Part | Key fields | Notes |
|---|---|---|
| `attributes` | `summary`, `category`, `confidence`, `found_at`, `article_sentence`, `human_approved`, `location`/`location_data`, `amount` | 29 keys; most are **category-specific** |
| `relationships` | `company1` (subject), `company2` (object), `most_relevant_source` (article) | company1 present ~97%, company2 ~35%, source ~100% |
| `included` | `company` (domain, name, ticker), `news_article` (title, body, url, published_at) | the evidence the LLM reads |

**What profiling told us (real numbers from the feed):**

- **310,710 records**, 12 files, ~1.2 GB total.
- **~40+ categories.** Top: `launches`, `partners_with`, `hires`, `recognized_as`, `receives_award`, `acquires`, `receives_financing`.
- **`confidence` ranges 0.0–1.0, mean 0.64**, with a distinct spike at **0.0** — these are almost always noise (e.g. `conf=0.0 partners_with: "Windsor partners with The Canadian Mental Health Association"`).
- **Event dates span 2010–2025** → stale events resurfacing as "new" is a real failure mode.
- **Sparse fields are conditional, not broken:** `amount` is ~95% null because it only applies to financing/acquisition events. `headcount` only to hiring events. *Do not flag these as missing-data errors blindly* — flag them only when the category implies they should be present.
- **0 duplicate event IDs**, but **one article often produces many events** (~5% of source IDs map to 2+ events). That's where dedup and entity-resolution edge cases live.

---

## 3. Rules first, LLM where rules fail (the split)

This is the most important design decision and the thing the reviewer is testing for.

### Solve with deterministic rules (cheap, exact, $0)

| Check | Logic |
|---|---|
| Schema / type validity | `id` is UUID; `confidence` ∈ [0,1]; required keys present |
| Category enum | `category` ∈ known set; flag novel values for review |
| Date sanity | `found_at` ≤ now; not before 2000; `found_at` ≈ article `published_at` |
| Referential integrity | every `relationships` id resolves to an `included` entity |
| Conditional completeness | if `category ∈ {receives_financing, acquires}` → `amount` should be non-null; if `hires` → `job_title`/`headcount` expected |
| Exact duplicates | same `(company1, category, found_at, summary)` hash |
| Confidence floor | `confidence < 0.15` → auto-quarantine (rule, not LLM) |

Rules catch a large fraction of bad records at **zero token cost** and at full throughput. Run them on **100% of records, always.**

### Solve with LLMs (semantic, contextual, fuzzy)

| Check | Why a rule can't do it |
|---|---|
| **Semantic accuracy** — does the summary/sentence actually describe the labelled `category`? | Requires reading meaning, not matching strings |
| **Entity resolution validation** — is `company1` plausibly the event's subject given the text? | Needs judgement about who-did-what-to-whom |
| **Source credibility & relevance** — real news vs. PR puffery vs. syndicated reprint vs. duplicate coverage | Genre/intent classification |
| **Contextual freshness** — is this genuinely new, or a historical event re-surfaced? | Needs to reason about the article's own time references |
| **Geographic/market validity** *(optional)* — does the event apply to the claimed market? | Inference from text + location_data |

**Heuristic for the split:** *If you can write the check as a regex, a range, a set-membership, or a join — it's a rule. If answering it requires reading and understanding prose — it's an LLM check.*

---

## 4. The LLM checks (design)

Each check is a **versioned prompt + a strict output schema + an eval set**. Same pattern for all three.

**Common output schema (structured JSON, every check returns this):**

```json
{
  "check": "semantic_accuracy",
  "verdict": "pass | fail | uncertain",
  "confidence": 0.0,
  "reason": "one-sentence justification",
  "evidence_span": "the text that drove the decision"
}
```

### Check A — Semantic accuracy (the workhorse)

- **Input:** `category`, `summary`, `article_sentence` (not the full body — keeps it cheap).
- **Prompt skeleton:**
  ```
  You are validating whether a news event's CATEGORY label matches its text.
  CATEGORY: {category}
  SUMMARY: {summary}
  SENTENCE: {article_sentence}
  Rubric:
    - pass: the text clearly describes a "{category}" event.
    - fail: the text describes a different event type, or no event.
    - uncertain: text is ambiguous or truncated.
  Return ONLY the JSON schema. No prose.
  ```
- **Model:** **Haiku** — high-volume, narrow classification. Cheap and fast.

### Check B — Source credibility & relevance

- **Input:** article `title`, first ~600 tokens of `body`, `url` domain.
- **Goal:** classify `{genuine_news, press_release, marketing, syndicated_reprint, low_signal}`.
- **Model:** **Haiku** for the bulk; **Sonnet** only for the `uncertain` band.

### Check C — Entity resolution validation

- **Input:** `summary`, `article_sentence`, `company1.name`/`domain`, `company2.name`/`domain`.
- **Goal:** confirm the linked company is plausibly the event subject (catches the "law firm vs. defendant" swap, wrong-company merges).
- **Model:** **Sonnet** — this is the nuanced one; entity errors are expensive downstream.

### Model-choice principle

> **Haiku for cheap classification at volume. Sonnet for nuanced judgement and the `uncertain` escalation band. A frontier model only for a tiny hard-case tier you sample into the eval set.** Never run the expensive model on traffic the cheap model already answers confidently.

### Measuring the judge (non-negotiable)

For each check: **≥30 hand-labelled examples** with ground truth → measure **precision / recall / accuracy**. We care less about the absolute number than about *knowing where the judge is weak*. Pull the 5–10 worst failures and write down **why** it got them wrong (truncated sentence? category genuinely ambiguous? rare event type?). That failure note is the most valuable artifact in the whole submission.

---

## 5. Reusable skills

A **skill** is a markdown spec any agent (Claude Code, Cursor, API) can load to run a defined task. We ship at least one:

**`skills/news-events-quality-check/SKILL.md`** describes:
- **When to trigger:** a new/changed `news_event` record needs validation.
- **Inputs:** the event JSON + its `included` entities.
- **Outputs:** the per-check JSON verdicts + an overall `pass/fail/review` rollup.
- **Dependencies:** which prompt versions and eval sets it uses.
- **How to interpret:** verdict precedence (any hard rule fail → fail; LLM fail with conf>0.7 → fail; uncertain → review queue).
- **Worked example:** one record in, the verdict JSON out.

**Bonus `skills/news-events-remediation/SKILL.md`**: takes a flagged record and *proposes* a fix — corrected category, suggested merge target, or "reject with reason" — and always explains its reasoning. It **proposes, never silently writes.**

Skills make the workflow portable and versioned: the same capability runs in a notebook, in CI, or inside an agent loop without rewriting anything.

---

## 6. Agentic remediation pipeline

A single loop ties it together. A Python script/notebook demonstrating this end-to-end is sufficient for the assessment; the same shape scales to production (Section 11).

```
for each record in batch:
  1. INGEST       parse JSON:API, resolve included entities → flat record
  2. RULE TRIAGE  run all deterministic checks
                    ├─ hard fail        → quarantine, log, done (no LLM spend)
                    └─ pass / ambiguous → continue
  3. ESCALATE     run LLM checks (Haiku); route `uncertain` → Sonnet
  4. DIAGNOSE     if any fail → remediation skill proposes:
                    corrected value | suggested merge | suggested rejection
  5. LOG          append a trace row: input, prompt_version, model,
                    output, latency_ms, cost_usd, decision
  6. ROUTE        auto-fix (high conf, low risk) | human review queue (else)
```

**Where each actor belongs:**
- **Rules** = the gate. Run first, on everything, free.
- **LLMs** = the judge. Run only on what rules can't settle.
- **Humans** = the backstop. Review `uncertain`, low-confidence remediations, and a continuous random sample of "auto-passed" records to catch silent drift.

---

## 7. Evals & observability

This is what separates AI-*native* from AI-*assisted*.

**Eval harness** — one command (`make eval`, i.e. `uv run python -m veritas.evals`) that:
- re-runs every LLM check against its labelled set,
- reports precision/recall/accuracy per check,
- diffs against the previous prompt version (regression gate),
- exits non-zero if any metric drops beyond a threshold → wire into CI.

**Prompt versioning** — prompts live as versioned YAML files in `src/veritas/prompt_registry/prompts/` (e.g. `semantic_accuracy.v1.yaml`), each with a `version:` header. Every trace row records which version produced it, so v1-vs-v2 comparison is a `GROUP BY prompt_version` over the trace log.

**Tracing schema** (one row per LLM call — JSONL or SQLite):

```
record_id | check | prompt_version | model | input_tokens | output_tokens |
latency_ms | cost_usd | verdict | confidence | reason | ts
```

**Failure analysis** — every eval run dumps the worst N misclassifications with their inputs so you can read *why*. Most "LLM is wrong" cases are really *ambiguous ground truth* or *truncated input* — and that tells you to fix the data or the prompt, not the model.

---

## 8. Monitoring & cost (with the math)

**What runs where:**
- **Every record:** all rules (free) + Check A semantic accuracy (Haiku, cheap).
- **Sampled (e.g. 5–10%):** the heavier checks (entity resolution / source credibility) + a random audit of auto-passed records.
- **Scheduled (nightly/weekly):** full-feed drift report, dashboard refresh, eval re-run.

**Detecting prompt drift / model regression** (the `claude-sonnet-latest` problem): **pin model versions in config**, and run the eval set on a fixed schedule (e.g. daily) as a *canary*. If accuracy on the frozen labelled set moves without a prompt change, the model changed underneath you — alert. Never silently float to `-latest` in production.

**Cost ceiling — the math** (illustrative rates; verify current pricing):

```
input ≈ 400 tok/record, output ≈ 90 tok/record (per check)

Full one-time backfill, 1 Haiku check on all 310,710 records   ≈  $211
Full backfill, 3 Haiku checks                                  ≈  $634   (~457M tokens)
Triaged: escalate ~15% to Sonnet                               ≈  +$119
─────────────────────────────────────────────────────────────────────────
One full historical pass, fully triaged                        ≈  ~$300–650
Ongoing (e.g. 10K new records/day, 1 Haiku check)              ≈  ~$7/day
```

The lever that keeps cost down is the **triage gate**: rules and the confidence floor remove a chunk of records before any token is spent, and only the `uncertain` band reaches the expensive model. Set a hard monthly budget; the trace log's `cost_usd` column makes the burn rate a single query.

**Alerting surface:** hard rule-fail spikes → Slack; eval/canary regression → ticket + page on-call; review-queue backlog growth → dashboard tile.

---

## 9. Storage & reporting

**Minimal schema (rules and LLM verdicts side by side):**

```sql
CREATE TABLE events_clean (        -- cleaned, validated records
  event_id        UUID PRIMARY KEY,
  category        TEXT,
  summary         TEXT,
  found_at        TIMESTAMPTZ,
  company1_id     UUID,
  confidence      NUMERIC,
  status          TEXT             -- clean | quarantined | review
);

CREATE TABLE quality_verdicts (    -- one row per check per record
  event_id        UUID,
  check_name      TEXT,
  check_type      TEXT,            -- 'rule' | 'llm'
  verdict         TEXT,            -- pass | fail | uncertain
  confidence      NUMERIC,
  reason          TEXT,
  prompt_version  TEXT,            -- null for rules
  model           TEXT,
  cost_usd        NUMERIC,
  latency_ms      INT,
  ts              TIMESTAMPTZ
);

CREATE TABLE quality_metrics_daily ( -- pre-aggregated for the dashboard
  day             DATE,
  check_name      TEXT,
  check_type      TEXT,
  pass_rate       NUMERIC,
  fail_rate       NUMERIC,
  avg_cost_usd    NUMERIC,
  avg_latency_ms  INT
);
```

**Dashboard** (Streamlit or a static HTML report is fine) with four tiles:
1. **DQ trend over time**, split **rule vs. LLM**.
2. **Top failing reasons** surfaced by the LLM judges (group by `reason`).
3. **Cost & latency** of LLM checks over time.
4. **Human-review backlog** size and age.

---

## 10. How to build it end-to-end (production-grade, scalable)

Phased so each phase ships something usable.

**Phase 0 — Foundations (day 1)**
- Repo layout *(as built)*: `src/veritas/{ingest,rules,judges,prompt_registry,llm_gateway,evals,pipeline,store,monitoring,dashboard}/` with `scripts/`, `skills/`, `tests/`, `docs/`, and `datasets/` at the root. (The original sketch used top-level `eda/`/`sql/`; those were folded into `scripts/profile_dataset.py` and the SQLAlchemy models in `store/`.)
- A flat parser: JSON:API line → clean record + resolved entities. Stream line-by-line (never load 100 MB into memory).
- Config file pinning **exact model IDs**, thresholds, and the cost budget.

**Phase 1 — Rules + profiling (day 1–2)**
- Implement the deterministic checks from Section 3. They're fast, free, and catch the bulk.
- Light EDA report (the numbers in Section 2). Establishes the rule-vs-LLM split with evidence.

**Phase 2 — LLM checks + evals (day 2–4)**
- Build the three checks (Section 4) with strict JSON schemas and **structured output / tool-use** so parsing never breaks.
- Hand-label ≥30 examples per check. Build the one-command eval harness. **Do not ship a check until its judge is measured.**

**Phase 3 — Skills + pipeline (day 4–5)**
- Write `SKILL.md` for quality-check (+ remediation bonus).
- Wire the agentic loop (Section 6) with the triage gate and the trace logger.

**Phase 4 — Storage, monitoring, dashboard (day 5–7)**
- Apply the DDL; load verdicts.
- Monitoring script: canary eval on schedule, drift alert, budget guard.
- Dashboard tiles. Optional ≤5-min Loom of the loop running end-to-end.

**Scaling from 310K → 100M+ records:**
- **Throughput:** the per-record loop is embarrassingly parallel. Shard by file/date; run as a queue of batch jobs (Temporal / Celery / a managed batch service). Use the **Anthropic Batch API** for the historical backfill — it's roughly half the cost and built for exactly this.
- **Idempotency:** key every verdict on `(event_id, check_name, prompt_version)` so re-runs overwrite cleanly and a crash never double-bills.
- **Backpressure & cost:** the rule gate + confidence floor are your throttle. Cap LLM concurrency; the trace log's `cost_usd` is your live budget meter with a hard stop.
- **Storage:** verdicts table is append-only and time-partitioned (partition by day); aggregate into the daily metrics table so dashboards never scan raw rows.
- **Drift defence:** pinned model versions + scheduled canary eval on a frozen labelled set is the single most important production safeguard.
- **Human loop:** route only `uncertain` + low-confidence remediations + a small random audit sample to people — that keeps reviewer load roughly constant as volume grows.

---

## 11. Known weaknesses (honest hand-off notes)

- **Ground-truth ceiling:** 30 labels/check is enough to *direct* the judge, not to certify it. Production needs a few hundred, ideally with two labellers and an agreement score.
- **LLM-as-judge bias:** the judge can be confidently wrong on rare categories with thin training signal (e.g. `identified_as_competitor_of`). Sample those into evals deliberately.
- **Freshness check is the hardest:** "is this stale?" depends on the article's *own* time language, which is easy to misread. Treat its verdicts as `review`, not `auto-fail`, until measured.
- **Entity resolution at scale** needs a real candidate-generation step (blocking on domain/ticker) before the LLM validates — the LLM should confirm, not search.

---

## 12. The one principle to remember

**Rules gate. LLMs judge. Humans backstop. Everything is logged, versioned, and measured.** If a teammate reads only this line, they can rebuild the system correctly.

