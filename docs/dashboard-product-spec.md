# VeritasAI — Decision Intelligence Console
## Product Specification

**Authoring team:** VP Product · Principal Product Designer · Staff Data Visualization Engineer · AI Platform Architect
**Status:** Spec for build · **Version:** 1.0 · **Date:** 2026-06-23
**Codename:** *Veritas Console*

> This is not a dashboard. It is a **decision instrument**. Every surface exists to move a specific person from *uncertainty* to *a defensible decision* in under a minute. If a widget does not change what someone does next, it is cut.

---

# 1. Product Vision

### The problem
VeritasAI already produces the truth — rule verdicts, LLM judgments, costs, traces, eval scores. But truth sitting in `quality_verdicts` and `trace_logs` is not a decision. Today a VP Engineering cannot answer "can I ship on today's data?" without a SQL console and twenty minutes. That latency *is* the product gap.

### The thesis
> **Decision Intelligence, not Business Intelligence.** A BI dashboard answers "what happened." A decision console answers "what should I do, and why, right now." The difference is that every number carries its *cause* and its *consequence* inline — a score is never shown without the drivers that moved it and the action it implies.

### What we are building
A **dark-mode, desktop-first, information-dense console** of six purpose-built workspaces, each owned by a persona and anchored to one decision. It looks and behaves like the operational consoles shipped by Datadog (signal density, time-anchored everything), Stripe (executive legibility over financial truth), Snowflake/Databricks (lineage you can drill into), and Palantir (the object-centric "investigate this entity" workflow). It is explicitly *not* a chart gallery.

### Three non-negotiable product principles
1. **Every score is decomposed.** No metric appears without a "why" — the top contributing drivers, ranked by their delta contribution. A Data Quality Score that drops 4 points must say *which rule, which category, which shard* caused it.
2. **Severity over recency.** Queues and lists rank by **blast radius** (events affected × downstream consumers × confidence), never by timestamp. The most expensive problem is always at the top.
3. **The number links to the row.** Every aggregate is a drill-down entry point. A cost figure links to the verdicts that incurred it; a failure rate links to the failing events. There are no dead-end numbers.

### What success looks like
A stakeholder opens their workspace and, **within 60 seconds, without clicking into a query**, knows: whether to trust today's data, what is broken, what needs a human, what is expensive, and what is degrading — *and* has a one-click path to the underlying evidence.

---

# 2. User Personas

| Persona | Lands on | The one question they open the console to answer | Decision they make |
|---|---|---|---|
| **VP Engineering** | Trust Center | "Can I ship product on today's data?" | Go / no-go on releases gated by data quality. |
| **Head of Data Quality** | Data Quality Intelligence | "Is quality improving, and what's drifting?" | Where to invest rule/prompt effort this week. |
| **Director, AI Platform** | AI Judge Performance | "Are the judges accurate, and is the new prompt better?" | Promote / roll back a prompt version. |
| **Operations Lead** | Cost & Efficiency + Platform Health | "Are we on budget and is the platform healthy?" | Throttle escalation, raise budget, page on-call. |
| **Human Review Team** | Human Review Operations | "What's the highest-impact thing in my queue?" | Which event to adjudicate next. |

### Persona design tensions (resolved)
- **Executive vs. Operator.** The same workspace serves both via **progressive disclosure**: the top band is executive-legible (one verdict, one trend, one driver); everything below is operator-dense (distributions, ranked tables, drill-downs). Executives never scroll; operators always do.
- **Trust vs. Curiosity.** Trust personas (VP Eng) need a single defensible verdict. Investigative personas (Data Quality, AI Platform) need to roam. We give the former a **headline verdict object** and the latter a **drill-down spine** from that same object.

---

# 3. Information Architecture

### Global frame
Every workspace shares one chrome so the console reads as a single instrument:

- **Global time scope** (top-left): a single time-range control (`Today` default, `7d`, `30d`, `Custom`, plus a `Live` toggle). It governs *every* widget on the page — there are no per-widget time pickers. A **comparison baseline** (`vs. prior period`, `vs. 7-day median`) is selectable beside it and drives every delta and trend indicator on screen.
- **Run/shard scope** (top-center): filter to a pipeline run, a source shard, or a category. The feed is multi-shard (24 files); scoping to a shard is a first-class operation, not a buried filter.
- **Global severity banner** (top, full-width, conditional): if any **launch-blocking** condition is true right now (budget exhausted, provider failure spike, quarantine spike), a single dark-red band states it in plain language with a deep link. It is the only color-saturated element on an otherwise restrained canvas — alarm is rare, so it reads.
- **Left rail**: the six workspaces, each with a **state pip** (green / amber / red, derived from that workspace's worst live signal) so the navigation itself is a status board. You can triage which workspace needs you before entering it.
- **The object spine**: the recurring drill-down target across the whole console is the **Event** (`event_id`) and the **Check** (`check_name × prompt_version × model`). Clicking any aggregate anywhere opens the relevant **Event Detail** or **Check Detail** panel — the Palantir-style object view that unifies rule verdicts, LLM verdicts, trace, cost, and remediation for that object.

### The six workspaces (decision map)

| # | Workspace | Owner | Console question answered |
|---|---|---|---|
| 1 | **Trust Center** | VP Eng | *Can we trust today's data?* |
| 2 | **AI Judge Performance** | AI Platform | *Where is AI failing?* / *Is quality improving (judge side)?* |
| 3 | **Cost & Efficiency** | Ops Lead | *What is costing money?* |
| 4 | **Human Review Operations** | Review Team | *What requires human intervention?* |
| 5 | **Data Quality Intelligence** | Head of DQ | *Is quality improving (data side)?* |
| 6 | **Platform Health** | Ops Lead | *Is the platform healthy?* |

Data lineage note (so this is buildable, not aspirational): every widget below is sourced from artifacts that **already exist** — `events_clean`, `quality_verdicts` (with `check_type`, `prompt_version`, `model`, `confidence`, `cost_usd`, `input/output_tokens`, `latency_ms`, `ts`), `trace_logs` (append-only, `stage`, `payload_hash`), the monitoring `MetricsSnapshot` (`review_rate`, `quarantine_rate`, `provider_failure_rate`), the eval framework's per-class P/R/F1, the rule metrics sink, and the `BudgetGuard` meter. The spec introduces **no new data the platform does not produce.**

---

## Workspace 1 — Trust Center
**Owner:** VP Engineering · **Question:** *Can we trust today's data?*

The answer must be a single, defensible verdict, decomposed into causes. This is the only workspace an executive may ever see, so its top band is the whole product in miniature.

### Top band — the Trust Verdict (executive, no scroll)
- **Data Quality Score** — a 0–100 composite (derived: weighted blend of clean-rate, high-confidence-pass rate, and integrity pass rate). Rendered as a **large numeral with a 30-day sparkline and a signed delta vs. baseline**, not a gauge, not a donut. The numeral's only color states a band (trusted / caution / blocked).
- **Dataset Health Score** — a structural-integrity composite (parse success, referential integrity, duplicate rate, schema conformance). Same treatment.
- **The "Why" strip (mandatory).** Directly beneath the two scores, a horizontal **driver-contribution bar**: the ranked list of what moved the score since baseline — e.g. *"−3.1: `confidence_floor` failures up in `launches` shard 14"*, *"+0.8: duplicate rate recovered."* This is the feature that makes it a decision instrument. Each driver is a drill-down link to the underlying events.

### Mid band — the trends (operator-legible)
- **Duplicate Trend** — sparkline of duplicate-ID rate over time with the absolute count; the dataset is known to carry ~7,875 cross-shard dupes, so this is load-bearing, not cosmetic. Annotated with shard boundaries.
- **Integrity Trend** — referential-integrity pass rate (dangling `company1`/`company2`/source references) over time.
- **Confidence Trend** — a **confidence distribution ridgeline** (small-multiple of the confidence histogram per period), *not* a single average line. The known 0.0-confidence spike (~29K events) must be visible as a left-edge mass, because an average would hide it. This is the deliberate choice of a distribution view over a KPI.

### Drill-down
Any driver, any trend point → **Event list filtered to that cause** → **Event Detail**. The VP can go from "score dropped 3 points" to "these 2,140 events in shard 14 failed the confidence floor" in two clicks.

### Why-it-changed engine (cross-cutting)
Every score on this page is backed by a **contribution decomposition**: `Δscore = Σ (Δrate_componentᵢ × weightᵢ)`, ranked by absolute contribution. The console always shows the top 3 contributors and the residual. This is computed in a service, never in the page (see §6).

---

## Workspace 2 — AI Judge Performance
**Owner:** Director, AI Platform · **Question:** *Where is AI failing?*

Built for root-cause analysis, not vanity accuracy. Anchored on the eval framework's labeled datasets (semantic_accuracy, entity_resolution, source_credibility) and the live verdict stream.

### Top band — judge scorecard, per check
A **ranked table** (not cards) with one row per check (`semantic_accuracy`, `entity_resolution`, `source_credibility`), columns: **Accuracy · Precision · Recall · F1 · n · escalation rate · mean confidence**, each with an inline sparkline and a delta vs. the prior eval. Rows sort by **F1 ascending** — the worst judge is on top. This is the "where is AI failing" answer in one glance.

### Prompt version comparison (promote/rollback decision)
- A **side-by-side diff view** of two prompt versions (e.g. `semantic_accuracy.v1` vs `v2`) showing per-class P/R/F1 deltas as a **signed horizontal bar set** (improvement right, regression left), with the regression threshold (0.05) drawn as a guide line. This is the eval framework's `compare_prompts` / `detect_regression`, surfaced visually.
- A **confusion shift heatmap**: which true-class→predicted-class cells changed between versions. Heatmap, not table, because the eye finds the migrated mass instantly.
- A single **Promote / Hold** affordance with the regression verdict stated in words ("v2 improves macro-F1 by +0.04; no class regressed beyond threshold — safe to promote").

### Failure clusters (the root-cause core)
- A **failure cluster table**: misjudgments grouped by shared signal (category, source domain, confidence band, escalation outcome), ranked by **cluster size × cost**. Each cluster row expands to the **worst N exemplars** (the eval `Mismatch` list, sorted by confidence-of-the-wrong-answer descending — a confidently wrong judge is the most dangerous).
- A **disagreement matrix**: where primary (Haiku) and escalation (Sonnet) judges disagreed, and who the human ultimately sided with — the truest signal of judge quality.

### Drill-down
Cluster → exemplar event → **Event Detail** showing the full prompt version, the verdict, the rationale, the token/cost, and the trace. Root cause is always reachable from the aggregate.

---

## Workspace 3 — Cost & Efficiency
**Owner:** Operations Lead · **Designed to impress executives.** · **Question:** *What is costing money?*

This is the workspace shown in the board deck. It must read like a **Stripe financial console**: unit economics first, dramatic and honest.

### Top band — unit economics (executive)
- **Cost per 1,000 events** — the headline unit metric, large numeral, 30-day trend, delta vs. baseline. This is the number a CFO understands.
- **Cost per verdict** — secondary unit metric, split by check and by tier (Haiku vs. Sonnet) in a small stacked bar so the escalation premium is visible.
- **Human-review hours saved** — the ROI hero number: `(auto-cleared events) × (avg manual review minutes)`, expressed as FTE-equivalents. This is the line that justifies the platform's existence and belongs at the top.
- **Budget burn** — a **burn-down/burn-rate pace line**, not a gauge: actual spend vs. the linear budget pace for the month, with a projected month-end landing point and the date the budget is forecast to exhaust at current rate. (Sourced from `BudgetGuard.spent` / `limit` plus the cost time-series.)

### Mid band — where the money goes (cost attribution)
- **Cost waterfall by stage/tier**: rules ($0, the saver) → Haiku primary → Sonnet escalation → human review (modeled). A waterfall makes the escalation premium and the human-cost tail unmistakable.
- **Escalation rate** trend with a cost-overlay: every point on the escalation curve carries its marginal Sonnet cost, so the operator sees the *price* of uncertainty, not just its rate.
- **Cost-per-category ranked table**: which event categories consume the most judgment spend (launches/partners_with dominate volume) — the targeting list for prompt/rule optimization.

### The efficiency story
A single sentence, computed and shown: *"This month, rules auto-cleared 82% of events at $0; LLM judgment cost $X; escalation added $Y; we avoided ≈Z human-review hours — net cost per trusted record: $N."* That sentence is the executive takeaway.

### Drill-down
Any cost figure → the contributing verdicts (`quality_verdicts.cost_usd`, tokens, model) → Event Detail. No cost number is a dead end.

---

## Workspace 4 — Human Review Operations
**Owner:** Human Review Team · **Question:** *What requires human intervention?*

Ranked by **impact, never timestamp.** This is the team's working surface for the entire shift.

### The two queues (impact-ranked)
- **Review Queue** (events in REVIEW): ranked by an **impact score** = `f(downstream consumers, category volume, confidence-of-uncertainty, age-weighting)`. The most consequential ambiguous event is always row one. Columns: impact, category, why-it's-here (the triggering check), judge disagreement flag, age, SLA state.
- **Quarantine Queue** (events QUARANTINED): same impact ranking, with the failing rule/judge and confidence inline. Quarantine is more severe than review, so it gets the more alarming visual weight.

### SLA aging — as risk, not as a clock
- An **SLA aging heatmap**: rows = impact bands, columns = age buckets, cell intensity = count. The dangerous cell (high-impact × old) is visually loud. This replaces a naive "oldest first" list — a low-impact item aging is fine; a high-impact item aging is an incident.
- A breach-risk band states, in words, *"3 high-impact items will breach SLA within 2 hours."*

### Remediation proposals (decision accelerators)
- A **proposals table**: the `HeuristicRemediator` outputs (always proposal-only, never auto-applied) presented as **accept / reject / edit** decisions, ranked by impact and by proposal confidence. Each proposal shows the before→after diff and the rule/judge evidence that motivated it.
- Reviewer throughput and backlog-growth indicators (intake rate vs. clearance rate) so the team and the Ops Lead can see if the queue is winning or losing.

### Drill-down
Every queue row → **Event Detail** with the full verdict stack, trace, prompt versions, and the remediation proposal — everything needed to adjudicate without leaving the panel.

---

## Workspace 5 — Data Quality Intelligence
**Owner:** Head of Data Quality · **Question:** *Is quality improving, and what's drifting?*
**Mandate:** highlight unusual behavior **automatically** — the operator should not have to hunt for the anomaly.

### Rule failure trends
- A **rule-failure small-multiples grid**: one sparkline per rule (the 8 deterministic checks — `confidence_floor`, `referential_integrity`, `conditional_completeness`, etc.), each with its current rate and delta. The grid is sorted by **delta magnitude**, so whichever rule is moving most is top-left. Known baselines (floor-fail ~9.7%, ref-integrity review ~2.4%) are drawn as reference bands so "normal" is visible.

### Emerging anomalies (automatic)
- An **anomaly feed**: the console runs change-detection (rate vs. trailing median ± MAD bands; the alert engine's `min_samples` suppression applies) and surfaces *"this just started behaving unusually"* as a ranked feed — e.g. *"`conditional_completeness` failures in `receives_financing` jumped 3.2σ in shard 19."* Each item links to the events. The operator reads the feed; they do not build the query.

### Category drift & confidence drift
- **Category drift**: a **drift ribbon** showing the category mix this period vs. baseline, with the largest movers called out (the dataset is 29 categories, launches 32% / partners_with 20% / hires 10.5% at baseline — drift from that mix is the signal).
- **Confidence drift**: a **distribution-shift view** (current confidence histogram overlaid on baseline, with the population-shift statistic). Again a distribution, never a single moving average — because the platform's known pathology is a bimodal confidence spike that a mean would erase.

### Drill-down
Anomaly or drift mover → filtered event list → Event Detail. The investigative spine is the same object model as everywhere else.

---

## Workspace 6 — Platform Health
**Owner:** Operations Lead · **Question:** *Is the platform healthy?*

A Datadog-grade operational surface over the pipeline's own telemetry. Time-anchored, signal-dense.

### Throughput & latency
- **Throughput**: events finalized per minute (from `OutcomeRecorded` stream / trace timestamps), with a stacked breakdown by final status (clean / review / quarantine). A backlog indicator if intake outpaces finalize.
- **Latency**: a **latency distribution band** (p50/p90/p99 over time as a percentile fan), split by stage where the trace allows (rules vs. LLM call) and by model. p99, not mean — the tail is the operational truth. Sourced from `quality_verdicts.latency_ms` and the gateway's measured `latency_ms`.

### Provider failures
- **Provider failure rate** trend (from `MetricsSnapshot.provider_failure_rate` / `ProviderCall` ok-fail), split by provider (anthropic / gemini) and error type, with the alert threshold (0.20, `min_samples=20`) drawn in. Retry/transient-vs-permanent breakdown so the operator distinguishes a blip from an outage. (Honest gap noted for build: a circuit-breaker state indicator is a *future* signal — flagged, not faked.)

### Alert history
- An **alert timeline** (swimlane by alert kind: `budget_exceeded`, `evaluation_regression`, `review_rate_spike`, `quarantine_rate_spike`, `provider_failure_spike`), showing fired/cleared spans and current state. This is the operational memory the alert engine currently lacks a home for.

### Storage growth
- **Storage growth** trends per table (`events_clean`, `quality_verdicts`, `trace_logs` — the append-only trace is the fastest grower), with row-count and on-disk size, and a projected fill line. Surfaces the retention conversation before it becomes an incident.

### Drill-down
Latency outlier or provider-failure spike → the affected verdicts/traces → Event Detail / Check Detail.

---

# 4. Visual Design System

### Philosophy
**Restraint is the brand.** This console looks expensive because it is quiet. Color is a *scarce* signal reserved for severity; the default canvas is monochrome data on a dark ground. If everything is colored, nothing is urgent.

### Forbidden (per mandate, and on principle)
- ✗ Pie / donut charts — they encode poorly and read as consumer-grade.
- ✗ Rainbow / categorical-rainbow palettes — they imply meaning that isn't there.
- ✗ Decorative charts, 3D, gradients-for-flair, animated counters.
- ✗ Generic KPI card grids — replaced by **decomposed scores** (a number is never shown without its drivers).

### Preferred vocabulary
| Pattern | Used for | Why |
|---|---|---|
| **Heatmaps** | SLA aging, confusion shift, anomaly intensity | The eye finds the hot cell faster than it reads a table. |
| **Distribution / ridgeline / percentile-fan** | Confidence, latency, drift | The platform's pathologies are bimodal/tail effects a mean would hide. |
| **Sparklines** | Every score and rate | Trend-in-context at a glance, zero chrome. |
| **Ranked tables** | Queues, clusters, judges, cost-by-category | Decisions are made on ordered lists, not on shapes. |
| **Trend indicators** | Every metric | Signed delta + direction arrow vs. an explicit baseline. |
| **Signed bar (diverging)** | Prompt-version deltas, drivers | Improvement/regression as left/right is instantly legible. |
| **Waterfall** | Cost attribution by stage/tier | Makes the escalation premium and human-cost tail unmistakable. |
| **Drill-down spine** | Everywhere | Every aggregate links to its rows; no dead-end numbers. |

### Color semantics (the entire palette)
- **Neutral ground**: near-black background, two-step elevated surfaces, off-white primary text, muted gray secondary text. This carries ~90% of the pixels.
- **Severity scale (the only saturated hues)**: a single 3-step ramp — *trusted* (calm teal/green), *caution* (amber), *blocked/breach* (red). Used only for state, never for category encoding.
- **Data ink**: one accent for the primary series, neutral grays for comparison/baseline series. Sequential (single-hue) ramps for heatmaps; diverging (two-hue) only for signed/delta data.
- **Accessibility**: severity never relies on hue alone — pair with icon/shape and label; target WCAG AA contrast on the dark ground; colorblind-safe ramps (no red/green-only distinctions).

### Typography & numerics
- Tabular (monospaced) figures for every number so columns align and deltas are scannable.
- A clear type scale: hero numerals for executive band, dense regular weight for operator tables.
- Units and baselines are always labeled inline ("$ / 1k events · vs. 7-day median").

### Motion
- Effectively none. Transitions are functional (drill-down panel slide), sub-200ms, and never decorative. Live tiles update without animated counting.

---

# 5. UX Principles

1. **Dark mode first.** The console is designed on a dark ground; a light theme is a later port, not the source of truth. Operators run this on wall displays and for long shifts — dark reduces fatigue and makes the rare severity color pop.
2. **Desktop-first, density-first.** Optimized for wide (≥1440px) displays and multi-monitor operations rooms. No mobile compromise dilutes the layout. Information density is a feature: an operator should see a workspace's full state without scrolling the top band.
3. **Progressive disclosure for two audiences.** Top band = executive (one verdict, one trend, one driver, no scroll). Below = operator (distributions, ranked tables, drill-downs). The same page serves the VP and the analyst.
4. **Every number is a door.** Aggregates link to their rows; rows link to the Event/Check object. The drill-down spine is consistent across all six workspaces.
5. **Severity over recency, always.** Queues, feeds, and lists rank by impact/blast-radius. Time is a column, not the sort key.
6. **Cause is co-located with effect.** A score and its drivers, a rate and its anomaly, a cost and its attribution — shown together, never on separate pages.
7. **Honest about gaps.** Where a signal is not yet produced by the platform (e.g. circuit-breaker state), the console marks it as upcoming rather than faking it. Trust is the product.
8. **One global time scope.** The whole page reasons about one time range and one baseline; no per-widget time controls to reconcile.

---

# 6. Dashboard Architecture

Strict three-layer separation. **No SQL in the UI. No business logic in pages.** Pages render view-models; they never compute and never query.

```text
dashboard/
  pages/            # UI ONLY. One module per workspace. Renders a ready-made
                    # view-model. No SQL, no math, no thresholds, no business rules.
    trust_center.py
    judge_performance.py
    cost_efficiency.py
    review_operations.py
    quality_intelligence.py
    platform_health.py

  components/        # Reusable presentational widgets. Pure render functions of
                    # typed inputs -> visual. Stateless, framework-thin.
    decomposed_score.py     # score + sparkline + driver-contribution strip
    ranked_table.py         # impact-sorted table with inline sparklines/deltas
    heatmap.py              # sequential/diverging heatmap (SLA, confusion, anomaly)
    distribution.py         # histogram / ridgeline / percentile-fan
    sparkline.py
    trend_indicator.py      # signed delta + arrow vs. baseline
    diverging_bars.py       # prompt-version / driver deltas
    cost_waterfall.py
    severity_banner.py
    drilldown_panel.py      # Event Detail / Check Detail object view

  viewmodels/        # The contract between logic and UI. Immutable, typed
                    # (Pydantic) DTOs. Pre-formatted, display-ready, zero logic.
                    # A page consumes ONLY these; it cannot reach past them.
    trust.py        # TrustVerdictVM, ScoreDriverVM, ConfidenceDistributionVM ...
    judge.py        # JudgeScorecardVM, PromptCompareVM, FailureClusterVM ...
    cost.py         # UnitEconomicsVM, CostWaterfallVM, BudgetBurnVM ...
    review.py       # ReviewQueueVM, SLAHeatmapVM, RemediationProposalVM ...
    quality.py      # RuleTrendVM, AnomalyVM, DriftVM ...
    platform.py     # ThroughputVM, LatencyDistributionVM, AlertTimelineVM ...

  services/          # BUSINESS LOGIC. All computation lives here: score
                    # composition, the why-it-changed decomposition, impact
                    # ranking, anomaly detection, drift stats, cost/ROI math,
                    # SLA risk, budget projection. Consumes repositories,
                    # produces view-models. Knows nothing about rendering.
    trust_service.py            # composite scores + contribution decomposition
    judge_service.py            # P/R/F1, prompt compare, failure clustering
    cost_service.py             # unit economics, attribution, burn projection, ROI
    review_service.py           # impact ranking, SLA risk, proposal ordering
    quality_service.py          # rule trends, anomaly (median±MAD), drift stats
    platform_service.py         # throughput, latency percentiles, alert state
    scoring.py                  # shared score definitions & weights (single source)
    impact.py                   # shared blast-radius / impact-score definition

  repositories/      # DATA ACCESS ONLY. The only place SQL / ORM lives. Reads
                    # events_clean, quality_verdicts, trace_logs, metrics
                    # snapshots, eval results. Returns typed records, NEVER
                    # view-models and NEVER business aggregates beyond what the
                    # store can express. Reuses the existing SQLAlchemy session.
    event_repository.py
    verdict_repository.py        # wraps the existing store VerdictRepository
    trace_repository.py
    metrics_repository.py        # MetricsSnapshot history
    eval_repository.py           # eval P/R/F1 + comparison results
    cost_repository.py           # cost/token aggregates over quality_verdicts

  app.py             # Composition root: wires repositories -> services ->
                    # pages, owns the global time/scope/baseline state and the
                    # left-rail navigation. Dependency injection only; no logic.
```

### Layer contract (enforced, not aspirational)
- **`pages/` → may import only `viewmodels/` and `components/`.** A page receives a view-model from a service (wired in `app.py`) and renders it. A page that contains an arithmetic operation, a threshold, or a query is a bug.
- **`services/` → consume `repositories/`, return `viewmodels/`.** All thresholds, weights, score formulas, ranking, anomaly/drift math, and projections live here, in one place (`scoring.py`/`impact.py` hold the shared definitions so Trust Center and Data Quality agree on what "clean" means).
- **`repositories/` → the only SQL.** They return typed row records. They reuse the platform's existing async SQLAlchemy session and the store's repositories — the console is a **read-mostly consumer** of the same database, not a fork of it.
- **`viewmodels/` → immutable, display-ready DTOs.** Pre-formatted strings, pre-computed deltas, pre-ranked lists. The boundary that makes the UI swappable (Streamlit today, a real SPA later) without touching logic.

### Why this survives a frontend swap
The build contract deferred a real SPA; today's renderer may be Streamlit. Because pages depend only on view-models, **replacing the renderer touches `pages/` + `components/` and nothing else.** Services and repositories — where the value is — are framework-agnostic. This is the same "promotes without rewrite" discipline as the core platform.

---

# 7. Success Criteria

### The 60-second test (the acceptance bar)
A stakeholder, opening their workspace cold, answers **without running a query**:

| Question | Where it's answered | Time budget |
|---|---|---|
| **Can I trust today's data?** | Trust Center top band — Trust Verdict + driver strip | < 10s |
| **What is broken?** | Left-rail state pips + global severity banner → worst workspace | < 15s |
| **What needs review?** | Human Review Operations — impact-ranked top row | < 10s |
| **What is expensive?** | Cost & Efficiency — cost-per-1k + budget burn pace | < 10s |
| **What is degrading?** | Data Quality Intelligence anomaly feed + Platform Health trends | < 15s |

**Pass condition:** all five answerable in ≤ 60s total, and each answer carries a one-click path to its evidence.

### Quantitative product KPIs
- **Time-to-decision:** median < 60s for the five questions above (instrumented via interaction analytics).
- **Drill-through rate:** > 40% of sessions reach an Event/Check Detail — proof the numbers are doors, not dead ends.
- **Zero-SQL operation:** 100% of the five core questions answerable without the SQL console (the original product gap, closed).
- **Alert actionability:** every fired alert in the timeline has a console destination that explains and localizes it.
- **Executive legibility:** a non-technical exec correctly states the trust verdict and the budget pace in a 5-minute unguided test.

### Qualitative bar
It should feel like an instrument a Datadog/Stripe/Palantir team shipped: quiet, dense, fast, and *trustworthy* — where every number is decomposed into its cause and connected to its consequence, and where the rarest thing on the screen is a saturated color, because that means something is actually wrong.

---

*End of specification. No implementation, no Streamlit code, no commits — this document defines what to build and why, not how to code it.*
