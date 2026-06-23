# Dashboard V1 — Buildable Scope

**Status:** Approved scope for Phase 7 · **Date:** 2026-06-23
**Authors:** AI Platform Architect · Staff Data Visualization Engineer (with VP Eng / Head of DQ sign-off from the design review)
**Companion docs:** `dashboard-product-spec.md` (the full vision), `dashboard-design-review.md` (the critique that produced this gate).

> **The gate.** A widget is **V1** only if every pixel it renders can be computed from data that exists in the database **today**, via a read-only query over an existing table. Everything else is **V2**, and §3 says exactly which missing capability it is waiting on. No widget appears in V1 without all four of: (1) data source, (2) repository method, (3) backing table, (4) refresh strategy.

---

## 1. What actually exists today (the only inputs V1 may use)

### 1.1 Durable tables (SQLAlchemy store)

| Table | Columns V1 can read | Durability note |
|---|---|---|
| `events_clean` | `event_id` (PK), `category`, `summary`, `found_at`, `company1_id`, `company2_id`, `status`, `updated_at` | **`updated_at` mutates on re-run** (upsert overwrites). Safe for *current-state* snapshots; **unsafe as a time axis.** No `created_at`. Raw event confidence is **not stored here.** |
| `quality_verdicts` | `id`, `event_id`, `check_name`, `check_type` (`rule`/`llm`), `prompt_version`, `model`, `verdict`, `confidence`, `reason`, `evidence_span`, `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`, `ts`, `created_at` | **`created_at` is first-write-wins and stable across re-runs** → a reliable processing-time axis. This is the richest V1 source. |
| `trace_logs` | `id`, `event_id`, `trace_id`, `stage`, `payload_hash`, `created_at` | **Append-only.** `created_at` is a reliable processing-time axis for throughput. Stores a *hash*, not payload or timings. |

### 1.2 Offline / on-demand assets (not in the DB)
- **Eval framework** (`evals/`): per-class Precision/Recall/F1 + macro + accuracy (`score()`), `compare_prompts`, `detect_regression`. Runs against **packaged fixtures of ~10–12 examples each** — on-demand, not from the DB. Small-`n` caveat is mandatory wherever it surfaces.
- **Config** (`Settings`): `cost.monthly_budget_usd`, pinned model IDs, `pipeline.clean_sample_rate`, eval `regression_threshold`, alert thresholds. Static, read once.
- **Pricing table**: USD/MTok per pinned model. Static.

### 1.3 Explicitly NOT available today (forces V2 — see §3)
- ❌ **No metrics-history table.** `MetricsSnapshot` (`review_rate`/`quarantine_rate`/`provider_failure_rate`) is **in-memory and ephemeral** — gone when the process exits.
- ❌ **No provider-call records.** `ProviderCall` ok/fail events go only to the ephemeral metrics sink. **Provider success/failure is in no table.**
- ❌ **No alert records.** Alerts are computed in-process and never persisted or routed.
- ❌ **No human-review system.** No queue table, reviewer identity, assignment, SLA, or captured human decision.
- ❌ **No lineage / downstream-consumer graph.** "Impact" has no backing field.
- ❌ **No remediation-decision store.** Proposals are transient, `auto_applicable=False`, never persisted.
- ❌ **No durable per-event finalized-at.** `events_clean.updated_at` mutates, so **status-rate *trends* are not reconstructable**; only the current status *snapshot* is.

### 1.4 Repository policy for V1
V1 **may add new read-only methods** to a `dashboard/repositories/` layer (per `dashboard-product-spec.md` §6). These are `SELECT`-only aggregations over the three existing tables. V1 **may NOT** add tables, columns, write paths, or new pipeline emissions — those are V2 data contracts (§4). New method names below are proposals for that read layer; where an existing store method suffices it is named directly.

### 1.5 Global refresh model
The database mutates **only during/after a batch pipeline run** — there is no live ingestion service. Therefore the V1 refresh vocabulary is:
- **On-load + manual refresh** — default for current-state snapshots.
- **Poll (15 s)** — optional, only meaningful *while a run is in progress*; same query, repeated.
- **On-demand (recompute)** — eval widgets; runs the harness, cached until inputs change.
- **On-demand per `event_id`** — drill-down detail.

There is no sub-second "live" tile in V1, because there is no live data source. Claiming one would be dishonest.

---

## 2. V1 — Build Now

Organized by the spec's six workspaces, but reduced to only what the data supports. Workspaces that collapse to little (Human Review Ops) say so plainly.

### 2.1 Trust Center *(reduced — snapshot-first)*

| Widget | 1. Data source | 2. Repository method | 3. Backing table | 4. Refresh |
|---|---|---|---|---|
| **Current status composition** (clean / review / quarantine counts + %) | `events_clean.status` grouped | `EventRepository.count_by_status()` *(new)* | `events_clean` | On-load + manual; poll 15s during run |
| **Duplicate snapshot** (count + rate of duplicate-flagged events) | `quality_verdicts` where `check_name='exact_duplicate'` and `verdict='fail'` | `VerdictRepository.count_by_check(check_name, verdict)` *(new)* | `quality_verdicts` | On-load + manual |
| **Duplicate trend** | same, bucketed by `created_at` (day/run) | `VerdictRepository.timeseries_by_check(check_name, verdict, bucket)` *(new)* | `quality_verdicts` | On-load + manual |
| **Integrity snapshot + trend** | `quality_verdicts` where `check_name='referential_integrity'`, current + bucketed by `created_at` | `VerdictRepository.count_by_check` / `…timeseries_by_check` *(new)* | `quality_verdicts` | On-load + manual |
| **Judge-confidence distribution** (histogram of LLM verdict confidence) | `quality_verdicts.confidence` where `check_type='llm'` | `VerdictRepository.confidence_histogram(check_type, bins)` *(new)* | `quality_verdicts` | On-load + manual |
| **Static driver breakdown** (which checks contribute the most current failures — the honest, *non-temporal* "why") | `quality_verdicts` grouped by `check_name`, `verdict` | `VerdictRepository.failure_breakdown()` *(new)* | `quality_verdicts` | On-load + manual |

**Cut to V2 / changed from spec:**
- The **0–100 composite Trust/Health scores** ship in V1 **only as transparent, defined indices** with the formula and weights shown inline (e.g. `clean_rate`, `integrity_pass_rate`, `duplicate_rate` displayed as their own numbers and a labeled blend) — *not* as an opaque magic number. If product won't commit to defensible weights, ship the three component rates and **no composite.**
- **Raw-data "Confidence Trend"** → **V2**: raw `event.confidence` is **not persisted** to `events_clean`. Only *judge* confidence is available (shown above). This is a real data gap, not a design choice.
- **"Why score changed" temporal decomposition** → **V2** (needs metrics history / durable finalized-at). V1 ships the *static* breakdown only.

### 2.2 Data Quality Intelligence *(the strongest V1 workspace)*

| Widget | 1. Data source | 2. Repository method | 3. Backing table | 4. Refresh |
|---|---|---|---|---|
| **Rule-failure breakdown** (the 8 rules, count + rate per rule, current) | `quality_verdicts` where `check_type='rule'`, grouped by `check_name`, `verdict` | `VerdictRepository.rule_breakdown()` *(new)* | `quality_verdicts` | On-load + manual |
| **Rule-failure trends** (per-rule sparklines over time) | same, bucketed by `created_at` | `VerdictRepository.rule_timeseries(bucket)` *(new)* | `quality_verdicts` | On-load + manual |
| **Category composition** (event mix across 29 categories, current) | `events_clean.category` grouped | `EventRepository.count_by_category()` *(new)* | `events_clean` | On-load + manual |
| **Failure rate by category** (which categories fail which rules) | join `quality_verdicts` (rule fails) → `events_clean.category` on `event_id` | `VerdictRepository.failures_by_category()` *(new)* | `quality_verdicts` ⋈ `events_clean` | On-load + manual |
| **Confidence distribution by check** (small-multiples) | `quality_verdicts.confidence` grouped by `check_name` | `VerdictRepository.confidence_histogram_by_check(bins)` *(new)* | `quality_verdicts` | On-load + manual |

**Cut to V2:**
- **Automatic anomaly feed** → **V2** (needs persisted baselines/metrics history; per the review, also a false-positive risk at rule×shard×category cardinality). V1 may draw **fixed known baselines** (floor-fail ~9.7%, ref-integrity ~2.4%) as static reference bands — those are constants, not history.
- **Category/confidence *drift* vs. baseline-over-time** → **V2** (needs a stored baseline). V1 shows current distributions only.

### 2.3 Cost & Efficiency *(fully buildable — and the executive win)*

| Widget | 1. Data source | 2. Repository method | 3. Backing table | 4. Refresh |
|---|---|---|---|---|
| **Total spend + budget consumed** (Σ `cost_usd` vs configured monthly budget) | Σ `quality_verdicts.cost_usd`; limit from `Settings.cost.monthly_budget_usd` | `CostRepository.total_cost()` *(new)* + config | `quality_verdicts` | On-load + manual; poll 15s during run |
| **Cost per verdict** (mean, and by tier/model) | `quality_verdicts.cost_usd` grouped by `model` | `CostRepository.cost_per_verdict_by_model()` *(new)* | `quality_verdicts` | On-load + manual |
| **Cost per 1,000 events** (Σ cost / distinct `event_id` × 1000) | `quality_verdicts` agg | `CostRepository.cost_per_1k_events()` *(new)* | `quality_verdicts` | On-load + manual |
| **Cost by check** | `cost_usd` grouped by `check_name` (rules = $0) | `CostRepository.cost_by_check()` *(new)* | `quality_verdicts` | On-load + manual |
| **Cost by prompt version** (catches verbose-prompt cost regressions) | `cost_usd`, `input_tokens` grouped by `prompt_version` | `CostRepository.cost_by_prompt_version()` *(new)* | `quality_verdicts` | On-load + manual |
| **Spend trend** (cost over time) | `cost_usd` bucketed by `created_at` | `CostRepository.cost_timeseries(bucket)` *(new)* | `quality_verdicts` | On-load + manual |
| **Escalation rate** (events with an escalation-tier model verdict ÷ events with any LLM verdict) | `quality_verdicts` model-tier presence per `event_id` | `CostRepository.escalation_rate()` *(new)* | `quality_verdicts` | On-load + manual |
| **Token economics** (input/output token totals & per-verdict) | Σ `input_tokens`, `output_tokens` | `CostRepository.token_totals()` *(new)* | `quality_verdicts` | On-load + manual |

**Cut to V2:**
- **"Human-review hours saved"** → **V2** (and demoted): it requires human-review volume + a measured per-review time. Both are V2. Per the review, this was the worst vanity metric — it does **not** ship in V1.
- **Live budget meter from `BudgetGuard`** → not needed: the in-process guard isn't visible to the dashboard process. V1 **reconstructs spend from `Σ cost_usd`**, which is strictly better (durable). The guard stays a runtime throttle, not a dashboard source.
- **Budget *projection*/burn-down with forecast** → V1 ships **consumed-vs-limit** (real). A *forecast line* is V2 (needs a trustworthy time series + traffic model).

### 2.4 AI Judge Performance *(offline eval only — with mandatory small-n honesty)*

| Widget | 1. Data source | 2. Repository method | 3. Backing table | 4. Refresh |
|---|---|---|---|---|
| **Per-check P/R/F1 + accuracy** (with `n` and a "small sample" badge) | eval `score()` over packaged fixtures | `EvalRepository.scorecard(dataset)` *(new; wraps `evaluate_dataset`)* | none (packaged fixtures) | On-demand (recompute); cached per dataset version |
| **Prompt-version comparison** (v1 vs v2 deltas + regression flag) | eval `compare_prompts` / `detect_regression` | `EvalRepository.compare(dataset, vA, vB)` *(new)* | none (fixtures) | On-demand; cached per (dataset, versions) |
| **Worst-failure exemplars** (the `Mismatch` list, confidently-wrong first) | eval runner `Mismatch` output | `EvalRepository.worst_failures(dataset, k)` *(new)* | none (fixtures) | On-demand |
| **Live judge verdict distribution** (pass/fail/uncertain mix per check — *unlabeled*, descriptive only) | `quality_verdicts` where `check_type='llm'` grouped by `check_name`, `verdict` | `VerdictRepository.llm_verdict_mix()` *(new)* | `quality_verdicts` | On-load + manual |

**Mandatory V1 constraints on this workspace:**
- Every eval metric **must render its `n` and an explicit "n too small to trust" state** when `n < 100`. With fixtures at ~10–12, that badge is **always on** in V1. Non-negotiable per the review.
- **Confusion-shift heatmap** → **V2** (meaningless at n≈12).
- **"Human sided with" disagreement matrix** → **V2** (needs captured human decisions).
- The live verdict-mix tile is labeled **descriptive, not accuracy** — there is no ground truth on live traffic.

### 2.5 Platform Health *(reduced to processing telemetry that's actually stored)*

| Widget | 1. Data source | 2. Repository method | 3. Backing table | 4. Refresh |
|---|---|---|---|---|
| **LLM latency distribution** (p50/p90/p99, by model — *LLM only*) | `quality_verdicts.latency_ms` where `check_type='llm'` | `VerdictRepository.latency_percentiles_by_model()` *(new)* | `quality_verdicts` | On-load + manual |
| **Latency trend** | `latency_ms` percentiles bucketed by `created_at` | `VerdictRepository.latency_timeseries(bucket)` *(new)* | `quality_verdicts` | On-load + manual |
| **Processing throughput** (events/verdicts/traces per time bucket — *per run/day, not real-time*) | `trace_logs.created_at` (or `quality_verdicts.created_at`) bucketed | `TraceRepository.throughput(bucket)` *(new)* | `trace_logs` | On-load + manual; poll 15s during run |
| **Current storage size** (row counts per table) | `count()` per table | `EventRepository.count`, `VerdictRepository.count`, `TraceRepository.count` *(exist)* | all three | On-load + manual |
| **Stage volume** (trace emissions per `stage`) | `trace_logs` grouped by `stage` | `TraceRepository.count_by_stage()` *(new)* | `trace_logs` | On-load + manual |

**Cut to V2:**
- **Provider failure rate / breakdown** → **V2**: provider ok/fail is **in no table** (ephemeral sink only). This is the most important honest cut here.
- **Per-stage latency split (rules vs. LLM)** → **V2**: rule latency is **not recorded**; only LLM `latency_ms` exists. V1 says "LLM latency" and means it.
- **Alert history / timeline** → **V2** (alerts not persisted).
- **Storage *growth* trend** → **V2** (needs historical counts). V1 shows current size only.
- **Live "events per minute"** → out: no live service. V1 shows per-run throughput.

### 2.6 Human Review Operations *(V1 = read-only triage list; the *system* is V2)*

The full operational workspace (queues, assignment, SLA, decisions, proposals) is **V2** — none of its backend exists. V1 ships only what the data permits: a **read-only, sortable list of events currently in non-clean states**, for visibility, with full drill-down. It is a *viewer*, not a *workflow*.

| Widget | 1. Data source | 2. Repository method | 3. Backing table | 4. Refresh |
|---|---|---|---|---|
| **Review list** (events where `status='review'`) | `events_clean` filtered by status | `EventRepository.list_by_status('review', limit, offset)` *(new)* | `events_clean` | On-load + manual |
| **Quarantine list** (events where `status='quarantine'`) | `events_clean` filtered by status | `EventRepository.list_by_status('quarantine', …)` *(new)* | `events_clean` | On-load + manual |
| **List ordering** | sort by available fields only: `category`, `updated_at`, or **judge-uncertainty confidence** (joined from verdicts) | `EventRepository.list_by_status(..., order_by)` *(new)* | `events_clean` (⋈ `quality_verdicts` for confidence sort) | On-load + manual |

**Hard constraints:**
- **No "impact" sort** — there is no impact data. V1 sorts by real fields (category, age, judge confidence) and **says so**. No phantom ranking.
- **No claim / assign / lock / accept / reject / bulk action** — all V2 (no decision store).
- **Remediation proposals** are **not** shown in V1: they are transient and unpersisted. Showing a proposal a user cannot act on or that won't survive a refresh is the kind of dead-end the review condemned.

### 2.7 Cross-cutting — the drill-down spine *(fully buildable today)*

The Palantir-style **Event Detail** object view is the one piece of the original vision that ships **whole** in V1, because its repository methods **already exist**:

| Widget | 1. Data source | 2. Repository method | 3. Backing table | 4. Refresh |
|---|---|---|---|---|
| **Event header** | `events_clean` row | `EventRepository.get(event_id)` *(exists)* | `events_clean` | On-demand per event |
| **Verdict stack** (all rule + LLM verdicts for the event, with prompt_version, model, confidence, cost, tokens, latency) | `quality_verdicts` for the event | `VerdictRepository.list_for_event(event_id)` *(exists)* | `quality_verdicts` | On-demand per event |
| **Trace timeline** (append-only stage emissions) | `trace_logs` for the event | `TraceRepository.list_for_event(event_id)` *(exists)* | `trace_logs` | On-demand per event |

This makes the V1 promise real: **every aggregate above links to a complete, evidence-grade event view** — no dead-end numbers — using methods that already ship.

---

## 3. V2 — Future Roadmap (blocked on a missing capability)

Each item names the **single capability** it waits on. Nothing here is a design problem; it is a **data-contract** problem.

### 3.1 Requires *historical metrics storage* (a persisted time-series of snapshots/rates)
- Status-rate **trends** (review-rate, quarantine-rate, clean-rate over time).
- "Why the trust score changed" **temporal** decomposition.
- Budget **burn-down forecast** with projected exhaust date.
- **Storage-growth** trend and fill projection.
- Drift-vs-baseline views (category drift, confidence drift) needing a stored baseline.
- The **anomaly feed** (needs trailing-window baselines).

### 3.2 Requires a *human-review workflow system* (queue + identity + SLA)
- Assignable, lockable **review/quarantine queues**.
- **SLA** definition, aging-as-risk heatmap, breach prediction.
- Reviewer **throughput / backlog** (intake vs. clearance).
- **Bulk actions** on queue items.

### 3.3 Requires a *lineage / consumer graph* + an *impact model*
- **Impact-ranked** queues and lists (`f(downstream consumers, …)`).
- Blast-radius scoring anywhere it appears.
- Source-level root-cause linkage for drift.

### 3.4 Requires *decision capture* (persisting human adjudications & remediation outcomes)
- **"Human sided with"** disagreement matrix (Judge Performance).
- Accept / reject / edit of **remediation proposals**, with audit.
- Judge-vs-human ongoing evaluation on live traffic.
- **Human-review hours saved** (needs review volume + measured per-review time).

### 3.5 Requires *provider telemetry persistence* (`ProviderCall` written to a table)
- **Provider failure rate / breakdown** by provider and error type.
- **Per-stage latency** split (also needs rule-stage timing emission).
- Retry / transient-vs-permanent analytics.

### 3.6 Requires *alert routing + persistence*
- **Alert history / timeline** swimlane.
- Alert **acknowledgement**, on-call assignment, routing to Slack/PagerDuty.

### 3.7 Requires richer *eval datasets* (n ≥ ~100/check)
- Trustworthy P/R/F1 **without** the permanent small-`n` badge.
- **Confusion-shift heatmaps** between prompt versions.

---

## 4. The four data contracts that unlock V2

To convert the roadmap into buildable work, Phase 8+ should land these — in priority order, because each unblocks the most-wanted V2 workspace:

1. **`metrics_history` table** (periodic persisted `MetricsSnapshot` + a durable per-event `finalized_at`). Unlocks §3.1 — the largest set of widgets, and the trends executives expect.
2. **A review-work store** (`review_items` with identity, assignment, SLA, status) **+ a `human_decisions` table**. Unlocks §3.2 and §3.4 together — the only *daily* workspace and the judge-feedback loop in one stroke.
3. **`provider_calls` table** (persist `ProviderCall` ok/fail/latency/error_type) **+ rule-stage timing**. Unlocks §3.5 — real Platform Health.
4. **An `alerts` table + a routing sink.** Unlocks §3.6 — turns computed alerts into incident response.

(Lineage/impact, §3.3, is deliberately last: it is the largest new subsystem and the least essential to a credible launch.)

---

## 5. V1 acceptance summary

**V1 ships:** a Cost & Efficiency workspace (near-complete), a Data Quality Intelligence workspace (strong), a Trust Center (snapshot-first, honest composites), an offline AI Judge Performance scorecard (small-`n`-flagged), a reduced Platform Health (LLM latency + throughput + storage size), a read-only review/quarantine **viewer**, and a complete **Event Detail drill-down** — all from three existing tables plus the offline eval harness, via read-only repository methods and an on-load/poll/on-demand refresh model.

**V1 explicitly does not ship:** any time-series that depends on the ephemeral metrics sink, provider-failure analytics, alert history, impact ranking, the human-review *workflow*, remediation decisions, or any composite/ROI number whose inputs aren't in the database. Each is in §3 with the one capability it needs.

This is the buildable line. Everything above it is honest; everything below it has a named unlock.

---

*End of scope. No code, no implementation, no commits.*
