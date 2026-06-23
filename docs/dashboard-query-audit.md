# Dashboard V1 — Production Query Audit

**Status:** Pre-build query review for Phase 7 · **Date:** 2026-06-23
**Authors:** Staff Data Visualization Engineer · Database/Platform Reviewer
**Inputs:** `dashboard-v1-scope.md` (the buildable widget list), `dashboard-implementation-plan.md` (repository methods, §4 performance, §4.2 index set).
**Method:** Every read-only repository method proposed for V1 is audited against the **three existing tables** at three population sizes. Sizes assume the documented fan-out: ~1 event → multiple verdicts (8 rules + sampled LLM checks) + multiple trace rows. So **"10M events" ≈ 80–120M verdict rows** — verdict-table cardinality is always the binding constraint, not event count.

---

## 0. The tables and their indexes (the ground truth this audit reasons over)

| Table | Rows at 10M events | Indexes that exist **today** |
|---|---|---|
| `events_clean` (`EV`) | ~10M | PK `event_id`; index `status` |
| `quality_verdicts` (`QV`) | **~80–120M** | index `event_id`; UNIQUE `(event_id, check_name, prompt_version, model)` |
| `trace_logs` (`TR`) | ~30–60M (append-only) | index `event_id` |

**Indexes the plan adds in §4.2 (assumed present for the "with index" verdicts below):**
`QV(check_type, check_name, verdict)` · `QV(created_at)` (BRIN on PG) · `QV(model)` partial · `QV(prompt_version)` partial · `QV(check_name) INCLUDE(confidence)` (PG covering) · `EV(category)` · `TR(created_at)` · `TR(stage)`.

**Classification key**
- 🟢 **Safe at 1M rows** — interactive (<1s) with or without the new index.
- 🟡 **Safe at 10M rows** — interactive **only with the §4.2 index** and a bounded range; degrades past that.
- 🟠 **Requires aggregation table** — full-population scan; a daily/run rollup is needed before ~5M verdicts.
- 🔴 **Requires pre-computation** — cannot be answered interactively at scale from raw rows at all (distinct-heavy / self-join); must be materialized by the pipeline.

The classification is set by behaviour **at 10M events / ~100M verdicts**, which is the question asked.

---

## 1. Verdict-table aggregations (`quality_verdicts` — the hot table)

These dominate the audit because `QV` is the largest table and nearly every workspace reads it.

### `VerdictRepository.count_by_check(check_name, verdict)`
1. **SQL** — `SELECT COUNT(*) FROM QV WHERE check_name=? AND verdict=?`
2. **Complexity** — O(matching rows) with index; O(n) scan without. Single scalar out.
3. **Indexes** — `QV(check_type, check_name, verdict)` makes it an index-only count.
4. **SQLite** — no covering-index count; still walks the index entries. Acceptable; one B-tree range.
5. **PostgreSQL** — index-only scan, visibility-map dependent; very fast post-`VACUUM`.
6. **Caching** — TTL 60s; cheap to recompute.
7. **Materialization** — none needed.
8. **Class:** 🟡 **Safe at 10M** (with index). Without the composite index it is a 100M-row scan → 🟠.

### `VerdictRepository.failure_breakdown()` / `rule_breakdown()`
1. **SQL** — `SELECT check_name, verdict, COUNT(*) FROM QV [WHERE check_type='rule'] GROUP BY check_name, verdict`
2. **Complexity** — O(n) over the full table; tiny output (8 checks × 3 verdicts ≈ 24 groups).
3. **Indexes** — `QV(check_type, check_name, verdict)` → **index-only grouped aggregate** (never touches the heap).
4. **SQLite** — even index-only, it walks **every** index entry (~100M). Seconds-to-tens-of-seconds at 10M events. **Not interactive at scale on SQLite.**
5. **PostgreSQL** — index-only scan + hash/group aggregate; parallelizable; tolerable at 10M events, painful at 100M+.
6. **Caching** — TTL 120s.
7. **Materialization** — **yes, beyond ~5M verdicts.** This is the archetypal "tiny output, full scan" query — perfect for a daily rollup (`rule × verdict × day → count`).
8. **Class:** 🟠 **Requires aggregation table** at 10M events. 🟢 at 1M.

### `VerdictRepository.rule_timeseries(bucket)` / `timeseries_by_check(...)`
1. **SQL** — `SELECT check_name, date_trunc(?,created_at) b, verdict, COUNT(*) FROM QV WHERE check_type='rule' [AND created_at >= ?] GROUP BY check_name, b, verdict ORDER BY b`
2. **Complexity** — O(rows in range). Bounded time window is the saving grace.
3. **Indexes** — `QV(created_at)` for the range; composite for the grouping.
4. **SQLite** — no `date_trunc` → emulate with `strftime` (kills index usability on the expression unless bucketed in the service). **Recommended: fetch range rows, bucket in the service.** Range filter still uses the `created_at` index.
5. **PostgreSQL** — **BRIN on `created_at`** makes the range scan cheap because inserts are time-ordered ≈ physical-ordered. This is the high-leverage index.
6. **Caching** — TTL 300s (trends move slowly).
7. **Materialization** — a per-day rollup makes this trivial; until then, a bounded window (e.g. last 30 buckets) keeps it 🟡.
8. **Class:** 🟡 **Safe at 10M** with a bounded range + `created_at` index. Unbounded ("all time") → 🟠.

### `VerdictRepository.confidence_histogram([by_check], bins)`
1. **SQL (PG)** — `SELECT [check_name,] width_bucket(confidence,0,1,?) g, COUNT(*) FROM QV WHERE check_type='llm' AND confidence IS NOT NULL GROUP BY [check_name,] g`
2. **Complexity** — O(LLM rows). LLM verdicts are a **fraction** of `QV` (rules emit no confidence-bearing LLM rows) — smaller working set than rule queries.
3. **Indexes** — `QV(check_name) INCLUDE(confidence)` (PG covering) avoids heap fetches; partial `WHERE check_type='llm'` shrinks it.
4. **SQLite** — no `width_bucket`. Return `CAST(confidence*bins AS INT)` grouped counts via integer arithmetic, or fetch confidences in range and bin in the service. Index does not cover the expression; relies on the partial set being small.
5. **PostgreSQL** — covering index → index-only; fast.
6. **Caching** — TTL 120s.
7. **Materialization** — only if LLM verdict volume itself reaches tens of millions; lower priority than rule rollups.
8. **Class:** 🟡 **Safe at 10M** (LLM subset is smaller). 🟢 at 1M.

### `VerdictRepository.llm_verdict_mix()`
1. **SQL** — `SELECT check_name, verdict, COUNT(*) FROM QV WHERE check_type='llm' GROUP BY check_name, verdict`
2. **Complexity** — O(LLM rows); tiny output.
3–7. Same profile as `rule_breakdown` but on the smaller LLM subset; composite index serves it; rollup-friendly.
8. **Class:** 🟠 at 10M events (still a full subset scan), 🟢 at 1M.

### `VerdictRepository.latency_percentiles_by_model()` / `latency_timeseries(bucket)`
1. **SQL (PG)** — `SELECT model, percentile_cont(ARRAY[0.5,0.9,0.99]) WITHIN GROUP (ORDER BY latency_ms) FROM QV WHERE check_type='llm' AND latency_ms IS NOT NULL GROUP BY model`
2. **Complexity** — `percentile_cont` **materializes and sorts** each group → O(m log m) per model, memory-heavy. The most compute-intensive aggregate in the set.
3. **Indexes** — partial `QV(model) WHERE check_type='llm'`; `created_at` for the timeseries variant.
4. **SQLite** — **no `percentile_cont` at all.** Must pull `latency_ms` values (LLM subset) and compute percentiles in the service — pulling tens of millions of values to Python is infeasible at scale. SQLite path is dev-only; at scale this query is Postgres-only or rollup-only.
5. **PostgreSQL** — works, but the sort spills to disk at high cardinality. **Per-model + time-bucketed** keeps each sort on a partition. Consider `percentile_disc` or a t-digest extension for cheaper approximate percentiles at 100M.
6. **Caching** — TTL 120s.
7. **Materialization** — **strongly recommended**: precompute per-model/day p50/p90/p99 in a rollup; percentiles are the worst thing to compute live.
8. **Class:** 🟠 **Requires aggregation table** at 10M events (and 🔴 on SQLite — not computable there at scale).

### `VerdictRepository.list_by_status(status, limit, offset, order_by)` — review/quarantine viewer
1. **SQL (default sort)** — `SELECT … FROM EV WHERE status=? ORDER BY updated_at LIMIT ? OFFSET ?`
   **SQL (sort by judge confidence)** — `SELECT e.* , q.min_conf FROM EV e JOIN (SELECT event_id, MIN(confidence) min_conf FROM QV WHERE check_type='llm' GROUP BY event_id) q ON q.event_id=e.event_id WHERE e.status=? ORDER BY q.min_conf LIMIT ? OFFSET ?`
2. **Complexity** — status filter uses `EV(status)` index (cheap). **The confidence sort is the problem**: the subquery aggregates the whole LLM subset of `QV` (~per-event MIN over 100M rows) before the join — full aggregation regardless of `LIMIT`.
3. **Indexes** — `EV(status)`; the confidence subquery wants a `QV(event_id, confidence) WHERE check_type='llm'` covering index.
4. **SQLite** — large `OFFSET` paginates by walking skipped rows (O(offset)); use keyset pagination. The confidence subquery is a full GROUP BY → slow.
5. **PostgreSQL** — same; the per-event aggregate doesn't benefit from `LIMIT` because it must rank all candidates first.
6. **Caching** — short TTL or none (it's a worklist); cache the count separately.
7. **Materialization** — the confidence sort wants a **per-event summary** (one row per event: status, min LLM confidence, category) — i.e. exactly the `events_clean`-enrichment that belongs in a rollup / the future review-work store.
8. **Class:** default sort 🟢/🟡 (indexed + keyset). **Confidence sort 🔴 at 10M** — pre-compute a per-event confidence summary. (This is why the scope doc made the review workspace a minimal *viewer*.)

---

## 2. Cost aggregations (`CostRepository` — all over `quality_verdicts`)

### `CostRepository.total_cost()` / `token_totals()`
1. **SQL** — `SELECT SUM(cost_usd) FROM QV` ( / `SUM(input_tokens), SUM(output_tokens)`)
2. **Complexity** — O(n) full-table sum; one scalar.
3. **Indexes** — none help a global `SUM` over all rows; it must read every row's value.
4. **SQLite** — full scan of 100M rows for a sum → **seconds**. Acceptable only behind caching.
5. **PostgreSQL** — parallel seq-scan sum; faster but still full-table.
6. **Caching** — TTL 60s (this is the budget number — shortest TTL + poll on the cost page).
7. **Materialization** — **yes**: running cost total is the canonical rollup metric (incremental sum per run/day).
8. **Class:** 🟠 **Requires aggregation table** at 10M events. 🟢 at 1M.

### `CostRepository.cost_by_check()` / `cost_per_verdict_by_model()` / `cost_by_prompt_version()`
1. **SQL** — `SELECT <dim>, SUM(cost_usd)[, AVG, COUNT] FROM QV [WHERE …] GROUP BY <dim>`
2. **Complexity** — O(n) full scan; tiny output (handful of models/checks/versions).
3. **Indexes** — partial `QV(model)` / `QV(prompt_version)`; composite for check. But a `SUM` aggregate still reads every qualifying row's `cost_usd` (not in most indexes) → heap fetches unless a covering `(dim) INCLUDE (cost_usd)` index exists.
4. **SQLite** — full scan + group; no covering-include → reads heap. Slow at scale.
5. **PostgreSQL** — add `INCLUDE (cost_usd, input_tokens)` to make these index-only; otherwise heap-bound.
6. **Caching** — TTL 120s.
7. **Materialization** — **yes**, same daily rollup as costs (`dim × day → sum/count`).
8. **Class:** 🟠 **Requires aggregation table** at 10M events. 🟢 at 1M.

### `CostRepository.cost_per_1k_events()`
1. **SQL (naïve)** — `SELECT SUM(cost_usd)/NULLIF(COUNT(DISTINCT event_id),0)*1000 FROM QV`
2. **Complexity** — `COUNT(DISTINCT event_id)` over 100M rows = a **large distinct sort/hash** (~10M distinct keys). Expensive and memory-heavy.
3. **Indexes** — none make `COUNT(DISTINCT)` cheap on the big table.
4. **SQLite** — distinct over 100M rows → heavy temp B-tree; **avoid entirely.**
5. **PostgreSQL** — hash-distinct spills at this cardinality.
6. **Caching** — TTL 120s.
7. **Materialization / fix** — **do not `COUNT(DISTINCT)` on `QV`.** Take the event count from `EV.count()` (cheap, one row per event) and divide `total_cost()` by it. With that rewrite it collapses to two cheap scalars.
8. **Class:** naïve form 🔴; **rewritten form 🟠** (inherits `total_cost`'s scan), 🟢 at 1M.

### `CostRepository.escalation_rate()` — **flagged in the plan as the worst V1 query**
1. **SQL** — needs "per event, did both a cheap-tier and an escalation-tier LLM verdict exist?":
   `SELECT COUNT(*) FILTER (WHERE tiers>1)::float / COUNT(*) FROM (SELECT event_id, COUNT(DISTINCT model) tiers FROM QV WHERE check_type='llm' GROUP BY event_id) t`
2. **Complexity** — `GROUP BY event_id` over the LLM subset (~tens of millions) producing ~millions of groups, **then** `COUNT(DISTINCT model)` within each. Both group-cardinality-high and distinct-within-group. **The single most expensive query in V1.**
3. **Indexes** — `QV(event_id, model) WHERE check_type='llm'` helps the grouping but cannot remove it.
4. **SQLite** — group over millions of keys + per-group distinct → far past interactive; effectively unusable at scale.
5. **PostgreSQL** — large `GroupAggregate`; spills; slow even parallelized.
6. **Caching** — TTL 120s, but recompute cost is the problem, not staleness.
7. **Materialization** — **mandatory at scale**: escalation must be counted **at write time** (the pipeline already knows when it escalates — `EscalationResult.escalated_checks`) and rolled up. Reconstructing it post-hoc from `QV` is the wrong place to compute it.
8. **Class:** 🔴 **Requires pre-computation.** Ship it behind a flag at V1 (per the plan), enable via rollup.

---

## 3. Event-table aggregations (`events_clean`)

### `EventRepository.count_by_status()`
1. **SQL** — `SELECT status, COUNT(*) FROM EV GROUP BY status`
2. **Complexity** — O(EV rows) but `EV` is 10× smaller than `QV`, and `status` is indexed.
3. **Indexes** — `EV(status)` → index-only grouped count (3–4 groups).
4. **SQLite** — walks the `status` index; fast (10M index entries, few groups).
5. **PostgreSQL** — index-only scan; very fast.
6. **Caching** — TTL 60s.
7. **Materialization** — not needed at 10M; optional at 100M+ events.
8. **Class:** 🟢 **Safe at 1M**, 🟡 **Safe at 10M** comfortably (smaller table + indexed).

### `EventRepository.count_by_category()`
1. **SQL** — `SELECT category, COUNT(*) FROM EV GROUP BY category`
2. **Complexity** — O(EV rows); 29 groups out.
3. **Indexes** — `EV(category)` → index-only.
4. **SQLite** — index walk; fine.
5. **PostgreSQL** — index-only; fine.
6. **Caching** — TTL 300s (category mix is stable).
7. **Materialization** — optional past 100M events.
8. **Class:** 🟡 **Safe at 10M** with `EV(category)`.

### `EventRepository.list_by_status(...)` — see §1 (joins `QV` for the confidence sort)
Default sort is an `EV(status)` index scan + keyset pagination → 🟢/🟡. The confidence sort is the 🔴 case analysed in §1.

---

## 4. Join queries

### `VerdictRepository.failures_by_category()` — `QV ⋈ EV`
1. **SQL** — `SELECT e.category, q.check_name, COUNT(*) FROM QV q JOIN EV e ON e.event_id=q.event_id WHERE q.check_type='rule' AND q.verdict='fail' GROUP BY e.category, q.check_name`
2. **Complexity** — join of (filtered) `QV` against 10M `EV`. The **filter must apply before the join**: rule-fails are a minority of `QV`, so push `check_type='rule' AND verdict='fail'` first, then join the surviving rows to `EV` by PK.
3. **Indexes** — `QV(check_type, check_name, verdict)` to produce the filtered set cheaply; `EV` PK for the join probe; `EV(category)` for the group.
4. **SQLite** — nested-loop join driven by the filtered `QV` set against the `EV` PK; tolerable **if** the filter is selective, bad if rule-fail rate is high.
5. **PostgreSQL** — planner picks hash-join; ensure the filtered side is the build side. Watch work_mem.
6. **Caching** — TTL 300s.
7. **Materialization** — **yes** at scale: `category × check × day → fail count` is a natural rollup that removes the join entirely.
8. **Class:** 🟠 **Requires aggregation table** at 10M events; 🟢 at 1M.

---

## 5. Trace-table aggregations (`trace_logs`)

### `TraceRepository.throughput(bucket)`
1. **SQL** — `SELECT date_trunc(?,created_at) b, COUNT(*) FROM TR [WHERE created_at>=?] GROUP BY b ORDER BY b`
2. **Complexity** — O(rows in range); append-only table.
3. **Indexes** — `TR(created_at)` (BRIN on PG — append-only is the ideal BRIN case).
4. **SQLite** — emulate `date_trunc` via `strftime`/service-side bucketing; range filter uses the index.
5. **PostgreSQL** — BRIN range scan; excellent.
6. **Caching** — TTL 120s.
7. **Materialization** — per-bucket rollup at very high volume; bounded range keeps it fine.
8. **Class:** 🟡 **Safe at 10M** with a bounded range.

### `TraceRepository.count_by_stage()`
1. **SQL** — `SELECT stage, COUNT(*) FROM TR GROUP BY stage`
2. **Complexity** — O(TR rows); few stage groups.
3. **Indexes** — `TR(stage)` → index-only.
4. **SQLite** — index walk over 30–60M entries; seconds. Cache it.
5. **PostgreSQL** — index-only; fine.
6. **Caching** — TTL 300s.
7. **Materialization** — optional at scale.
8. **Class:** 🟠 at 10M events (full index walk, no range), 🟢 at 1M.

### `*.count()` (storage size — existing methods)
`SELECT COUNT(*)` per table. PG keeps cheap estimates (`reltuples`) — prefer the catalog estimate for the size widget over an exact `COUNT(*)` of 100M rows. SQLite must scan. **Class:** 🟡 (use PG `reltuples` / cache aggressively).

---

## 6. Drill-down queries (`Event Detail`) — bounded by design

| Method | SQL | Class |
|---|---|---|
| `EventRepository.get(event_id)` | `SELECT … FROM EV WHERE event_id=?` (PK lookup) | 🟢 at any size |
| `VerdictRepository.list_for_event(event_id)` | `SELECT … FROM QV WHERE event_id=? ORDER BY id` (uses `QV(event_id)` index) | 🟢 at any size |
| `TraceRepository.list_for_event(event_id)` | `SELECT … FROM TR WHERE event_id=? ORDER BY id` (uses `TR(event_id)` index) | 🟢 at any size |

All three are **single-event, index-driven, bounded-result** — they do not degrade with table size. This is why Event Detail is the safest workspace and the recommended first build. Caching: none/short (on-demand per event).

---

## 7. Offline eval queries (`EvalRepository`) — not against the DB

`scorecard` / `compare` / `worst_failures` wrap the in-package `evals/` harness over **~10–12-example fixtures**. Cost is independent of DB size; the constraint is statistical (small-`n` badge), not performance. **Class:** 🟢 always. Cache keyed on dataset/prompt version; recompute on-demand.

---

## 8. Findings

### Worst query
**`CostRepository.escalation_rate()` — 🔴.** A `GROUP BY event_id` over the LLM verdict subset (~tens of millions of groups) with a `COUNT(DISTINCT model)` *inside* each group. It is the only V1 query that is both high-group-cardinality **and** distinct-within-group, it benefits least from any index, and it is uncomputable interactively on SQLite at scale. The correct home for this metric is **write-time counting in the pipeline** (which already has `EscalationResult.escalated_checks`), not post-hoc reconstruction. Ship behind a flag; enable via rollup.

Runner-up: **`cost_per_1k_events()` naïve `COUNT(DISTINCT event_id)`** — fixed for free by dividing `total_cost()` by `EV.count()` instead.

### Most expensive dashboard page
**Cost & Efficiency.** It issues the largest cluster of full-`QV`-scan aggregates in one page load — `total_cost`, `cost_by_check`, `cost_per_verdict_by_model`, `cost_by_prompt_version`, `cost_timeseries`, `token_totals`, **and** `escalation_rate` — almost all 🟠/🔴, all over the 100M-row table. Without rollups it is the page that will first feel slow and the one whose numbers a poll-refresh will most expensively recompute. (Runner-up: **Data Quality Intelligence**, which adds the `QV ⋈ EV` join and the rule timeseries.)

### First scalability bottleneck
**`quality_verdicts` full-table `GROUP BY` aggregation, crossing ~5M verdict rows (≈500K events).** Before that, ad-hoc queries + the §4.2 indexes are interactive. After it, the tiny-output/full-scan cost and rule/breakdown queries cross the 1-second interactive budget on SQLite first, then on Postgres. **This is the trigger to land the `metrics_history` rollup contract** (`dashboard-v1-scope.md` §4 / `dashboard-implementation-plan.md` §4.5). The dashboard's view-model contract is unchanged by that switch — only the repository's backing query moves from raw `QV` to the rollup table.

---

## 9. Classification summary

| Method | 1M | 10M events (~100M QV) | At-scale requirement |
|---|---|---|---|
| `EventRepository.get` / `list_for_event` (QV/TR) | 🟢 | 🟢 | none (index-bound single event) |
| `EventRepository.count_by_status` | 🟢 | 🟡 | indexed; fine |
| `EventRepository.count_by_category` | 🟢 | 🟡 | `EV(category)` |
| `*.count()` (storage size) | 🟢 | 🟡 | use PG `reltuples`; cache |
| `VerdictRepository.count_by_check` | 🟢 | 🟡 | composite index |
| `VerdictRepository.confidence_histogram[_by_check]` | 🟢 | 🟡 | LLM subset + covering index |
| `VerdictRepository.*_timeseries` (bounded range) | 🟢 | 🟡 | `created_at` index (BRIN) |
| `TraceRepository.throughput` (bounded) | 🟢 | 🟡 | `TR(created_at)` |
| `VerdictRepository.failure_breakdown` / `rule_breakdown` | 🟢 | 🟠 | rule×verdict×day rollup |
| `VerdictRepository.llm_verdict_mix` | 🟢 | 🟠 | rollup |
| `VerdictRepository.latency_percentiles*` | 🟢 | 🟠 (🔴 SQLite) | per-model/day percentile rollup |
| `TraceRepository.count_by_stage` | 🟢 | 🟠 | rollup (optional) |
| `CostRepository.total_cost` / `token_totals` | 🟢 | 🟠 | running-sum rollup |
| `CostRepository.cost_by_*` (check/model/prompt) | 🟢 | 🟠 | dim×day cost rollup |
| `VerdictRepository.failures_by_category` (join) | 🟢 | 🟠 | category×check×day rollup |
| `CostRepository.cost_per_1k_events` (rewritten) | 🟢 | 🟠 | inherits total_cost rollup |
| `list_by_status` — **confidence sort** | 🟡 | 🔴 | per-event summary / review store |
| `CostRepository.escalation_rate` | 🟡 | 🔴 | **write-time count in pipeline** |
| `cost_per_1k_events` (naïve `COUNT(DISTINCT)`) | 🟡 | 🔴 | rewrite (don't COUNT DISTINCT on QV) |
| `EvalRepository.*` (offline) | 🟢 | 🟢 | none (DB-independent) |

**Read of the table:** at the **real dataset (~620K events)** everything is 🟢/🟡 — V1 ships and is fast. At **10M events** the verdict-table aggregates become 🟠 and three queries become 🔴. The single intervention that resolves the entire 🟠 column is the **daily/run rollup table**; the 🔴 rows additionally need either a rewrite (cost-per-1k), a write-time counter (escalation), or a per-event summary (confidence-sorted review list). None of these change the dashboard's UI or view-model contracts.

---

*End of query audit. No code, no commits.*
