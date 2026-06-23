# Dashboard V1 — Implementation Plan

**Status:** Build-ready architecture for Phase 7 · **Date:** 2026-06-23
**Authors:** AI Platform Architect · Staff Data Visualization Engineer
**Inputs:** `dashboard-product-spec.md` (vision), `dashboard-design-review.md` (critique), `dashboard-v1-scope.md` (the buildable line — this plan implements *only* that scope).
**Stack:** Streamlit · SQLAlchemy 2.0 · the existing VeritasAI `store/` layer (three tables: `events_clean`, `quality_verdicts`, `trace_logs`).

---

## 0. The one architectural decision to make first: sync vs. async

The existing store is **async** (`AsyncSession`, `aiosqlite`/`asyncpg`, `async_sessionmaker`). **Streamlit is synchronous** and re-executes the whole script top-to-bottom on every interaction. Bridging these per-rerun with `asyncio.run()` means standing up and tearing down an event loop on every widget click — fragile, and a known source of "event loop is closed" / "attached to a different loop" failures.

**Decision: the dashboard gets its own dedicated, read-only, *synchronous* SQLAlchemy engine.**

- Same database URL as the pipeline (read the same `veritas.db` / Postgres), but a **separate sync engine** (`create_engine` + `sessionmaker`, `sqlite`/`psycopg` driver — not `aiosqlite`/`asyncpg`).
- Created **once** via `@st.cache_resource` (engine + sessionmaker live for the server's lifetime, never per rerun).
- **Read-only by construction**: the dashboard layer has no write methods, no `upsert`, no `begin()` transactions — only `SELECT`. It never contends with the pipeline's writes.
- The async store stays exactly as-is for the pipeline. The dashboard does **not** import the pipeline's async repositories; it has its own sync read repositories against the same tables (same models, sync session).

This avoids the async/Streamlit impedance mismatch entirely, keeps the read path simple, and means the dashboard cannot corrupt pipeline state. It is the single most important call in this plan.

> The existing `EventRepository.get` / `list_for_event` methods are async and used by the pipeline. Event Detail in V1 re-implements those reads on the **sync** session (trivial, single-row/single-event `SELECT`s). We reuse the **ORM models** (`EventCleanRow`, `QualityVerdictRow`, `TraceLogRow`), not the async repository classes.

---

## 1. Repository Architecture

```text
dashboard/
  app.py            # Composition root. Owns: the @st.cache_resource sync engine,
                    # global session_state (time scope, baseline, run/shard filter),
                    # left-rail nav, the global severity banner. Wires repos->services
                    # ->pages via DI. NO queries, NO viz, NO business math here.

  pages/            # UI ONLY — one module per V1 workspace. Each page: reads the
                    # global scope from session_state, calls ONE service method to
                    # get a fully-built view-model, hands it to components. NO SQL,
                    # NO aggregation, NO thresholds, NO formatting.
    trust_center.py
    cost_efficiency.py
    quality_intelligence.py
    judge_performance.py
    platform_health.py
    review_viewer.py
    event_detail.py            # the drill-down object view (modal/panel)

  components/        # Presentational widgets. Pure functions: view-model -> Streamlit
                    # render. Stateless. NO data access, NO business logic, NO math
                    # beyond what a chart library does internally.
    decomposed_score.py        # number + sparkline + component breakdown strip
    ranked_table.py            # sortable table w/ inline sparklines + signed deltas
    distribution.py            # histogram / percentile fan (st altair/plotly wrapper)
    sparkline.py
    trend_indicator.py         # signed delta + arrow vs. an explicit baseline
    diverging_bars.py          # prompt-version / component deltas
    cost_waterfall.py
    severity_banner.py
    small_multiples.py         # grid of sparklines (rule trends, confidence-by-check)
    drilldown_panel.py         # renders an EventDetailVM

  viewmodels/        # The repo<->UI contract. Immutable, typed Pydantic models.
                    # Display-ready: pre-computed deltas, pre-ranked lists,
                    # pre-formatted units. A page consumes ONLY these. §5 defines them.
    trust.py
    cost.py
    judge.py
    platform.py
    quality.py
    review.py
    event_detail.py
    common.py                  # Sparkline, Delta, Bucket, MetricBand shared types

  services/          # BUSINESS LOGIC. Composition, derived metrics, percentile math,
                    # escalation-rate derivation, index formulas + weights, ordering,
                    # unit formatting. Consumes repositories, returns view-models.
                    # Knows NOTHING about Streamlit or SQL.
    trust_service.py
    cost_service.py
    quality_service.py
    judge_service.py           # bridges the OFFLINE eval harness, not the DB
    platform_service.py
    review_service.py
    event_service.py
    scoring.py                 # single source of index formulas + weights
    formatting.py              # USD, %, token, latency, count formatters

  repositories/      # DATA ACCESS ONLY — the only place SQL/ORM lives. Sync,
                    # read-only SELECTs over the three existing tables. Returns
                    # typed row DTOs (frozen dataclasses), NEVER view-models,
                    # NEVER business aggregates beyond GROUP-BY rollups.
    base.py                    # session-per-call context mgr over the cached engine
    event_repository.py
    verdict_repository.py
    trace_repository.py
    cost_repository.py         # cost/token aggregates over quality_verdicts
    eval_repository.py         # wraps the offline evals/ harness (no DB)
```

### Responsibility boundaries (the contract, enforced by import rules)

| Layer | May import | May NOT do | Output |
|---|---|---|---|
| `pages/` | `viewmodels`, `components`, a service interface | SQL, aggregation, thresholds, formatting, branching on raw numbers | rendered Streamlit |
| `components/` | `viewmodels`, a chart lib | data access, business math, thresholds | rendered widget |
| `services/` | `repositories`, `viewmodels`, `scoring`, `formatting` | SQL, Streamlit, rendering | a view-model |
| `repositories/` | `store.models`, sync session | business logic, view-models, formatting | typed row DTOs |
| `viewmodels/` | pydantic only | everything else | data classes |

**Two hard rules, mechanically checkable:** (1) `import streamlit` appears only in `pages/`, `components/`, and `app.py` — never in `services/` or `repositories/`. (2) `select(`/`text(`/ORM query appears only in `repositories/`. A lint rule or a simple import-graph test enforces both.

---

## 2. Data Flow

```text
Repository            Service                 ViewModel            Component        Page
──────────            ───────                 ─────────            ─────────        ────
SELECT … GROUP BY  →  compose/derive/      →  immutable,       →  pure render   →  layout +
returns row DTOs      rank/format/weight      display-ready       of the VM        scope read
(no logic)            (all the logic)         (no logic)          (no logic)       (no logic)
```

- A page reads the **global scope** (time range, baseline, shard filter) from `session_state` and calls exactly **one** service method, e.g. `cost_service.build(scope) -> CostEfficiencyVM`.
- The service calls one or more repository methods (cached — §3), runs all derivation (percentiles, escalation rate, index weighting, delta-vs-baseline, unit formatting), and returns a single fully-built view-model.
- The page passes view-model sub-objects to components. Components only render.
- **No SQL in pages. No business logic in components.** A page that does arithmetic, or a component that queries, is a review-blocking defect.

Drill-down follows the same flow: a component emits an `event_id` (via a Streamlit callback into `session_state`); `event_detail.py` calls `event_service.build(event_id) -> EventDetailVM` and renders `drilldown_panel`.

---

## 3. Query Strategy (per V1 widget)

**Caching model.** All repository reads are wrapped in `@st.cache_data(ttl=…)`, keyed on `(method, scope params, data_version)`. `data_version` is a coarse cache-buster (e.g. `max(created_at)` across `quality_verdicts` + `trace_logs`, fetched by one cheap query) so the cache auto-invalidates when a pipeline run writes new rows, and the **manual "Refresh" button** calls `st.cache_data.clear()`. The engine itself is `@st.cache_resource` (never re-created).

**Refresh model** (from the scope doc): `on-load + manual` default; `poll 15s` only while a run is active (a checkbox that sets a short TTL); `on-demand` for eval; `on-demand per event` for drill-down.

Legend: tables — `EV`=`events_clean`, `QV`=`quality_verdicts`, `TR`=`trace_logs`.

### Trust Center

| Widget | Repository method | SQL shape | Cache TTL | Refresh |
|---|---|---|---|---|
| Status composition | `EventRepository.count_by_status()` | `SELECT status, COUNT(*) FROM EV GROUP BY status` | 60s | load/manual/poll |
| Duplicate snapshot | `VerdictRepository.count_by_check('exact_duplicate','fail')` | `SELECT COUNT(*) FROM QV WHERE check_name=? AND verdict=?` | 60s | load/manual |
| Duplicate trend | `VerdictRepository.timeseries_by_check('exact_duplicate','fail',bucket)` | `SELECT date_trunc(bucket,created_at) b, COUNT(*) FROM QV WHERE check_name=? AND verdict=? GROUP BY b ORDER BY b` | 300s | load/manual |
| Integrity snapshot/trend | `VerdictRepository.count_by_check` / `…timeseries_by_check('referential_integrity',…)` | as above | 300s | load/manual |
| Judge-confidence distribution | `VerdictRepository.confidence_histogram(check_type='llm',bins)` | `SELECT width_bucket(confidence,0,1,bins) g, COUNT(*) FROM QV WHERE check_type='llm' AND confidence IS NOT NULL GROUP BY g` | 120s | load/manual |
| Static driver breakdown | `VerdictRepository.failure_breakdown()` | `SELECT check_name, verdict, COUNT(*) FROM QV GROUP BY check_name, verdict` | 120s | load/manual |

### Cost & Efficiency

| Widget | Repository method | SQL shape | Cache TTL | Refresh |
|---|---|---|---|---|
| Total spend vs budget | `CostRepository.total_cost()` | `SELECT COALESCE(SUM(cost_usd),0) FROM QV` (+ limit from `Settings`) | 60s | load/manual/poll |
| Cost per verdict by model | `CostRepository.cost_per_verdict_by_model()` | `SELECT model, COUNT(*), SUM(cost_usd), AVG(cost_usd) FROM QV WHERE check_type='llm' GROUP BY model` | 120s | load/manual |
| Cost per 1k events | `CostRepository.cost_per_1k_events()` | `SELECT SUM(cost_usd)/NULLIF(COUNT(DISTINCT event_id),0)*1000 FROM QV` | 120s | load/manual |
| Cost by check | `CostRepository.cost_by_check()` | `SELECT check_name, SUM(cost_usd) FROM QV GROUP BY check_name` | 120s | load/manual |
| Cost by prompt version | `CostRepository.cost_by_prompt_version()` | `SELECT prompt_version, SUM(cost_usd), SUM(input_tokens), COUNT(*) FROM QV WHERE prompt_version<>'' GROUP BY prompt_version` | 120s | load/manual |
| Spend trend | `CostRepository.cost_timeseries(bucket)` | `SELECT date_trunc(bucket,created_at) b, SUM(cost_usd) FROM QV GROUP BY b ORDER BY b` | 300s | load/manual |
| Escalation rate | `CostRepository.escalation_rate()` | two-pass / subquery: events with an escalation-tier `model` verdict ÷ events with any `check_type='llm'` verdict (see §4.3) | 120s | load/manual |
| Token totals | `CostRepository.token_totals()` | `SELECT SUM(input_tokens), SUM(output_tokens) FROM QV` | 120s | load/manual |

### Data Quality Intelligence

| Widget | Repository method | SQL shape | Cache TTL | Refresh |
|---|---|---|---|---|
| Rule-failure breakdown | `VerdictRepository.rule_breakdown()` | `SELECT check_name, verdict, COUNT(*) FROM QV WHERE check_type='rule' GROUP BY check_name, verdict` | 120s | load/manual |
| Rule-failure trends | `VerdictRepository.rule_timeseries(bucket)` | `SELECT check_name, date_trunc(bucket,created_at) b, verdict, COUNT(*) FROM QV WHERE check_type='rule' GROUP BY check_name, b, verdict` | 300s | load/manual |
| Category composition | `EventRepository.count_by_category()` | `SELECT category, COUNT(*) FROM EV GROUP BY category` | 300s | load/manual |
| Failures by category | `VerdictRepository.failures_by_category()` | `SELECT e.category, q.check_name, COUNT(*) FROM QV q JOIN EV e ON e.event_id=q.event_id WHERE q.check_type='rule' AND q.verdict='fail' GROUP BY e.category, q.check_name` | 300s | load/manual |
| Confidence-by-check | `VerdictRepository.confidence_histogram_by_check(bins)` | histogram, `GROUP BY check_name, bucket` | 120s | load/manual |

### AI Judge Performance (offline eval path — no DB except the live mix tile)

| Widget | Repository method | "Query" shape | Cache | Refresh |
|---|---|---|---|---|
| Per-check P/R/F1 (+`n`) | `EvalRepository.scorecard(dataset)` | wraps `evals.evaluate_dataset` over packaged fixtures | `@st.cache_data` keyed on dataset version | on-demand recompute |
| Prompt comparison | `EvalRepository.compare(dataset,vA,vB)` | wraps `evals.compare_prompts`/`detect_regression` | keyed on (dataset, versions) | on-demand |
| Worst failures | `EvalRepository.worst_failures(dataset,k)` | `Mismatch` list, confidently-wrong first | keyed on dataset | on-demand |
| Live verdict mix | `VerdictRepository.llm_verdict_mix()` | `SELECT check_name, verdict, COUNT(*) FROM QV WHERE check_type='llm' GROUP BY check_name, verdict` | 120s | load/manual |

### Platform Health

| Widget | Repository method | SQL shape | Cache | Refresh |
|---|---|---|---|---|
| LLM latency percentiles | `VerdictRepository.latency_percentiles_by_model()` | `SELECT model, percentile_cont(0.5/0.9/0.99) WITHIN GROUP (ORDER BY latency_ms) FROM QV WHERE check_type='llm' AND latency_ms IS NOT NULL GROUP BY model` (SQLite: approx in service — §4.4) | 120s | load/manual |
| Latency trend | `VerdictRepository.latency_timeseries(bucket)` | percentiles per `date_trunc(bucket,created_at)` | 300s | load/manual |
| Throughput | `TraceRepository.throughput(bucket)` | `SELECT date_trunc(bucket,created_at) b, COUNT(*) FROM TR GROUP BY b ORDER BY b` | 120s | load/manual/poll |
| Storage size | `*.count()` (exist) | `SELECT COUNT(*)` ×3 | 300s | load/manual |
| Stage volume | `TraceRepository.count_by_stage()` | `SELECT stage, COUNT(*) FROM TR GROUP BY stage` | 300s | load/manual |

### Event Detail (drill-down — single event, cheap)

| Widget | Repository method | SQL shape | Cache | Refresh |
|---|---|---|---|---|
| Event header | `EventRepository.get(event_id)` | `SELECT … FROM EV WHERE event_id=?` (PK) | none / short | on-demand per event |
| Verdict stack | `VerdictRepository.list_for_event(event_id)` | `SELECT … FROM QV WHERE event_id=? ORDER BY id` | none / short | on-demand per event |
| Trace timeline | `TraceRepository.list_for_event(event_id)` | `SELECT … FROM TR WHERE event_id=? ORDER BY id` | none / short | on-demand per event |

---

## 4. Performance Review (10M events / 100M verdicts)

### 4.1 The brutal truth about the current indexes
Today only three indexes exist: `EV.event_id` (PK), `EV.status`, `QV.event_id`, `TR.event_id`, plus the `QV` unique constraint `(event_id, check_name, prompt_version, model)`. **Every aggregation in §3 groups by columns that are NOT indexed** — `check_name`, `check_type`, `model`, `prompt_version`, `verdict`, `created_at`, `category`. At 100M verdicts, each such `GROUP BY` is a **full-table scan + hash aggregate over 100M rows** — multi-second to minutes, on every page load. **This is the dashboard's defining performance problem.**

### 4.2 Required indexes (additive — no schema/contract change, allowed in V1)
These are the minimum to make V1 queries survive into the low-millions. They cover the GROUP BY / filter columns:

| Index | Serves |
|---|---|
| `QV(check_type, check_name, verdict)` | rule/llm breakdowns, verdict mix, driver breakdown |
| `QV(created_at)` (BRIN on Postgres; b-tree on SQLite) | all verdict time-series, cost trend, latency trend |
| `QV(model)` partial `WHERE check_type='llm'` | cost-by-model, latency-by-model |
| `QV(prompt_version)` partial `WHERE prompt_version<>''` | cost-by-prompt-version |
| `QV(check_name) INCLUDE (confidence)` (covering, PG) | confidence histograms without heap fetch |
| `EV(category)` | category composition |
| `TR(created_at)`, `TR(stage)` | throughput, stage volume |

`created_at` as **BRIN** on Postgres is the high-leverage one: append-only insert order ≈ physical order, so a BRIN index makes time-range scans cheap at 100M rows for a fraction of a b-tree's size.

### 4.3 Expensive queries, ranked (and the fix)
1. **`escalation_rate()`** — needs "per event, did a cheap-tier AND escalation-tier verdict exist?" That's a self-join or `GROUP BY event_id HAVING COUNT(DISTINCT model)>1` over `QV` — **the single most expensive V1 query** (groups 100M rows by 10M keys). Fix: compute it from the *cheaper* aggregate `cost_by_prompt_version`/per-model counts where possible, or accept it as a **rollup-only** metric (§4.5).
2. **`failures_by_category()`** — a `QV ⋈ EV` join of 100M × 10M. Fix: index both join keys (`QV.event_id` exists; ensure `EV.event_id` PK is used), and push the `verdict='fail' AND check_type='rule'` filter *before* the join. Still rollup-bound at 100M.
3. **`cost_per_1k_events()`** — `COUNT(DISTINCT event_id)` over 100M rows is a large distinct-sort. Fix: maintain event count separately (`EV.count()` is cheap) and divide; never `COUNT(DISTINCT)` on the big table.
4. **Latency percentiles** — `percentile_cont` over 100M rows materializes a sort. Fix: per-model + time-bucketed so each percentile runs on a partition, not the whole table.
5. **All time-series** — fine *with* the `created_at` index and a bounded time range; catastrophic without one.

### 4.4 SQLite vs. Postgres reality
The dev DB is SQLite, which has **no `percentile_cont`, no `width_bucket`, no `date_trunc`**. Two consequences the implementer must plan for:
- **Histograms & percentiles**: on SQLite, the repository returns *raw values or pre-bucketed counts via integer arithmetic* (`CAST(confidence*bins AS INT)`), and the **service** computes percentiles/bins. On Postgres, push it into SQL. The repository method signature is the same; the SQL differs by dialect. Keep dialect branches inside `repositories/` only.
- **`date_trunc`**: emulate on SQLite with `strftime`. Same containment rule.

This is why aggregation logic that *can't* be expressed portably in SQL lives in the **service**, fed by the repository's raw/bucketed rows — not in the page.

### 4.5 Aggregation strategy at scale — the honest ceiling
**Ad-hoc `GROUP BY`-on-every-page-load does not scale to 100M verdicts, even with perfect indexes** — an index helps a filtered/ranged scan, but a full-population rollup (e.g. "cost by check across all time") still touches every row. The V1 dashboard is therefore **correct and fast at the real dataset size (≈620K events, single-digit-millions of verdicts)** and **degrades predictably beyond that.**

The scale fix is exactly the **`metrics_history` / rollup data contract from `dashboard-v1-scope.md` §4** — pre-aggregated daily/run-level rollups (cost, counts, latency percentiles, rule rates) written by the pipeline, so the dashboard reads thousands of rollup rows instead of 100M raw rows. That is a **V2 data contract**, not a V1 dashboard feature. V1 ships ad-hoc queries + the indexes above; V1.5 adds rollups when verdict volume crosses ~5M. This plan names the ceiling rather than pretending the queries scale.

---

## 5. Dashboard Contracts (strongly-typed view models)

All view models are **frozen Pydantic models** (`model_config = ConfigDict(frozen=True, extra='forbid')`), **display-ready** (deltas pre-computed, lists pre-ranked, units pre-formatted as strings where they're shown). Shared atoms live in `viewmodels/common.py`:

- **`Sparkline`** — `points: tuple[float, ...]`, `buckets: tuple[str, ...]`.
- **`Delta`** — `value: float`, `direction: Literal['up','down','flat']`, `vs_baseline: str` (label), `is_improvement: bool` (semantic, not directional — a *down* cost is good).
- **`Bucket`** — `label: str`, `count: int`, `rate: float`.
- **`Band`** — `severity: Literal['trusted','caution','blocked']`, `reason: str`.

### TrustCenterVM (`viewmodels/trust.py`)
| Field | Type | Source / note |
|---|---|---|
| `status_composition` | `tuple[Bucket, ...]` | clean/review/quarantine counts + rates (`EV.status`) |
| `data_quality_index` | `IndexVM \| None` | `None` if weights not committed; else value + `components: tuple[ComponentVM,...]` (each component's name, rate, weight, contribution) — the transparent index |
| `duplicate` | `MetricVM` | snapshot value + `Sparkline` + `Delta` |
| `integrity` | `MetricVM` | snapshot + sparkline + delta |
| `judge_confidence_dist` | `DistributionVM` | bins + counts (LLM verdict confidence) |
| `driver_breakdown` | `tuple[DriverVM, ...]` | static "which check drives current failures", ranked by count |
| `banner` | `Band` | worst-of severity for the workspace |

`IndexVM` = `{ value: float, components: tuple[ComponentVM,...], formula_label: str }`. `MetricVM` = `{ label, value, unit, spark: Sparkline, delta: Delta }`.

### CostEfficiencyVM (`viewmodels/cost.py`)
| Field | Type | Note |
|---|---|---|
| `total_spend` | `MoneyVM` | `value_usd: float`, `formatted: str` |
| `budget` | `BudgetVM` | `spent_usd`, `limit_usd`, `consumed_pct`, `band: Band` (no forecast in V1) |
| `cost_per_1k_events` | `MoneyVM` + `Delta` | headline unit metric |
| `cost_per_verdict` | `tuple[ModelCostVM, ...]` | per model: count, sum, avg |
| `cost_by_check` | `tuple[Bucket, ...]` | rules show $0 |
| `cost_by_prompt_version` | `tuple[PromptCostVM, ...]` | sum, avg input tokens, count — the regression detector |
| `spend_trend` | `Sparkline` | cost over `created_at` buckets |
| `escalation_rate` | `RateVM` | value + `Delta`; flagged `rollup_pending` at scale |
| `tokens` | `TokenVM` | input/output totals + per-verdict |
| `efficiency_statement` | `str` | the one-sentence exec takeaway (rules cleared X% at $0 …) — **no fabricated hours-saved** |

### JudgePerformanceVM (`viewmodels/judge.py`)
| Field | Type | Note |
|---|---|---|
| `scorecards` | `tuple[CheckScoreVM, ...]` | per check: `precision`, `recall`, `f1`, `accuracy`, `n: int`, `sample_warning: bool` (**always True at fixture n**) — sorted by `f1` ascending |
| `comparison` | `PromptCompareVM \| None` | per-class signed deltas, `regressed: bool`, `regression_threshold: float`, `recommendation: str` |
| `worst_failures` | `tuple[MismatchVM, ...]` | true vs predicted, confidence-of-wrong, exemplar `event_id` |
| `live_verdict_mix` | `tuple[CheckMixVM, ...]` | descriptive pass/fail/uncertain per check — labeled **not accuracy** |
| `data_note` | `str` | mandatory "offline eval, n=… — descriptive only" banner text |

### PlatformHealthVM (`viewmodels/platform.py`)
| Field | Type | Note |
|---|---|---|
| `latency` | `tuple[LatencyVM, ...]` | per model: `p50`, `p90`, `p99` (ms) — **LLM only**, labeled |
| `latency_trend` | `tuple[Sparkline, ...]` | p90 over time per model |
| `throughput` | `Sparkline` | trace emissions per bucket — labeled per-run, not real-time |
| `storage` | `tuple[TableSizeVM, ...]` | per table row counts (current; no growth trend in V1) |
| `stage_volume` | `tuple[Bucket, ...]` | trace emissions per stage |
| `unavailable_note` | `str` | explicit: provider failures / alerts / per-stage latency are V2 |

### EventDetailVM (`viewmodels/event_detail.py`)
| Field | Type | Note |
|---|---|---|
| `header` | `EventHeaderVM` | `event_id`, `category`, `summary`, `found_at`, `company1_id`, `company2_id`, `status` (`EV`) |
| `verdicts` | `tuple[VerdictRowVM, ...]` | full stack: `check_name`, `check_type`, `status`, `confidence`, `reason`, `evidence_span`, `prompt_version`, `model`, `cost_usd`, `input/output_tokens`, `latency_ms`, `ts` |
| `trace` | `tuple[TraceRowVM, ...]` | `stage`, `trace_id`, `payload_hash`, `created_at` (append order) |
| `cost_summary` | `MoneyVM` | sum of verdict costs for this event |

The **row DTOs** returned by repositories are *separate*, leaner frozen dataclasses (e.g. `VerdictRow`) — repositories never construct view-models. The service maps row DTOs → view-models.

---

## 6. Risk Review

### 6.1 N+1 risks
- **Highest risk — review viewer sorted by judge confidence.** Sorting the review list by judge uncertainty must NOT loop `list_for_event` per row. **Fix:** one set-based `EV ⋈ QV` query with the confidence aggregate computed in SQL, paginated. Per-row enrichment is banned in list views.
- **Event Detail is safe** — it's a single event, three single-event queries. Bounded by design.
- **Small-multiples (rule trends, confidence-by-check)** must come from **one** grouped query returning all series, not one query per rule/check. The repository returns the long-format rows; the service pivots.

### 6.2 Streamlit state risks
- **Engine re-creation per rerun** → connection storms / leaked pools. **Fix:** `@st.cache_resource` for engine+sessionmaker; never create in a page.
- **Top-to-bottom re-execution** re-runs every query on every interaction. **Fix:** `@st.cache_data` on all reads (§3); the global scope lives in `session_state` so a filter change re-runs queries *once*, with new cache keys.
- **Widget key collisions across workspaces** (Streamlit keys are global) → cross-page state bleed. **Fix:** namespace every widget `key` by workspace (`cost::model_filter`).
- **Drill-down navigation** via `session_state['selected_event']` + `st.rerun()`; must clear on workspace switch to avoid a stale event panel.
- **Sessions are per-user-session, server is multi-session** → `cache_resource` engine is shared across users (fine, read-only); `session_state` is per user (correct for filters). Don't put data in `session_state`.

### 6.3 Caching risks
- **Stale-during-run**: a long pipeline run writes rows the dashboard caches over. **Fix:** the `data_version` cache key (`max(created_at)`) auto-busts; the poll mode shortens TTL; manual refresh clears. Document that without refresh, numbers are as-of last cache fill.
- **Over-caching the budget/spend number** can show a stale "under budget" during an active burn. **Fix:** shortest TTL (60s) + poll on the cost page specifically.
- **Cache key explosion**: caching on a free-form custom time range produces unbounded keys. **Fix:** snap custom ranges to day boundaries; cap `maxsize`.
- **Caching view-models vs. rows**: cache at the **repository read** boundary (raw rows), not the assembled view-model, so the same rows serve multiple widgets and services stay cheap to recompute. (View-model assembly is microseconds; row fetch is the cost.)

### 6.4 Scalability risks
- **The §4.5 ceiling** is the headline: ad-hoc `GROUP BY` is fine to single-digit-million verdicts, then needs rollups. **Mitigation:** ship indexes now; gate a rollup contract at ~5M verdicts; the dashboard reads rollups without UI change because the view-model contract is identical.
- **SQLite single-writer + dashboard reads during a run**: a read can block on a write lock. **Fix:** open the dashboard connection in WAL/read-only mode; on Postgres this is a non-issue.
- **`COUNT(DISTINCT event_id)` and self-join escalation rate** are the two queries that fall over first — both flagged `rollup_pending` and computed cheaply (or deferred) until rollups exist.
- **Unbounded result sets** (e.g. a category breakdown returning 29 rows is fine; a raw event list is not) — every list method is `LIMIT/OFFSET` paginated; no method returns an unbounded row set to the service.

---

## 7. Build Order

Sequenced by **dependency → buildability → value**, so each step is demoable and de-risks the next.

1. **Foundation** *(unblocks everything)* — `app.py` composition root; the `@st.cache_resource` **sync read engine**; `repositories/base.py` (session-per-call); `viewmodels/common.py` atoms; the `@st.cache_data` + `data_version` caching harness; the import-rule lint test (streamlit-only-in-UI, SQL-only-in-repos). Add the **§4.2 indexes** as an Alembic migration up front.
2. **Event Detail** *(proves the spine, lowest risk)* — repositories reuse the existing read shapes (`get`/`list_for_event`); `event_service`; `drilldown_panel`. Ship the object view first because every later widget links to it, and it validates the whole repo→service→VM→component→page flow on trivial queries.
3. **Cost & Efficiency** *(highest executive value, pure single-table aggregation)* — `cost_repository`, `cost_service`, the cost components, `cost_efficiency.py`. Defer `escalation_rate` behind a flag (it's the one expensive query). This is the workspace that justifies the project; build it early.
4. **Data Quality Intelligence** *(strongest data fit)* — rule breakdowns/trends, category composition, failures-by-category, confidence-by-check. Reuses cost-era components (`ranked_table`, `small_multiples`, `distribution`).
5. **Trust Center** *(composes prior data)* — status composition + duplicate/integrity trends (already built in 3–4) + the **transparent index** in `scoring.py`. Build after DQ because it reuses those repository methods and the index needs agreed weights.
6. **Platform Health** *(needs dialect-aware percentile/latency work)* — latency percentiles (SQLite-vs-PG branch), throughput, storage size, stage volume. Lands the `unavailable_note` for the V2 cuts.
7. **AI Judge Performance** *(separate offline path)* — `eval_repository` wrapping the `evals/` harness, the mandatory small-`n` badge, prompt comparison, live verdict mix. Last among full workspaces because it's an independent integration (not DB aggregation) and the smallest daily-use payoff.
8. **Review viewer** *(read-only, explicitly minimal)* — `list_by_status` paginated, sort by real fields only, links to Event Detail. Built last and kept deliberately small: it is a **viewer**, and the real review *system* is the V2 contract.

**Cross-cutting, threaded through 2–8:** the component library grows as workspaces need it (don't pre-build all of `components/`); the severity banner + left-rail pips wire in once the first two workspaces expose a `Band`.

---

## 8. Definition of done for V1

- All §3 widgets render from the three existing tables (+ offline eval) via read-only sync repositories; **zero SQL outside `repositories/`, zero business logic in `components/`, zero `import streamlit` in `services/`/`repositories/`** (enforced by the §7.1 lint test).
- The §4.2 indexes are migrated; every query meets an interactive latency budget (<1s) **at the real dataset size**, and the §4.5 scale ceiling + rollup plan is documented in-repo.
- Every aggregate links to a complete **Event Detail**; no dead-end numbers.
- Every offline-eval metric shows its `n` and the small-sample badge; every V2-cut surface shows an explicit "unavailable in V1 — needs <contract>" note.

---

*End of implementation plan. No code, no commits.*
