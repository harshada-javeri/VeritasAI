# Design Review — Decision Intelligence Console
## Adversarial review of `dashboard-product-spec.md`

**Review panel:** VP Engineering · Head of Data Quality · Staff Product Designer · Principal Data Visualization Engineer
**Date:** 2026-06-23 · **Subject:** `docs/dashboard-product-spec.md` v1.0
**Posture:** Brutally critical. The spec is well-written; that is exactly why it needs a hard review, because polish hides assumptions.

---

## 0. The verdict before the details

The spec is a beautiful design for a platform that **does not yet emit the data it depends on.** Read it twice and a pattern emerges: roughly **40% of the widgets assume a time-series history, a human-review system, and a downstream-lineage graph that the codebase does not have.** It is a spec for VeritasAI *as it will exist in a year*, presented as if it ships on today's tables.

That is the headline finding, and it recurs in every workspace. Three load-bearing fictions:

1. **"Trends over 30 days."** `MetricsSnapshot` is **in-memory and ephemeral** (`InMemoryMetricsSink`); there is no metrics-history table. Every sparkline, every "vs. 7-day median," every burn-down line needs a time-series store that does not exist. The only durable time signal is `trace_logs.created_at` and `quality_verdicts.ts`. **Most trends in this spec are currently unbuildable.**
2. **"Impact score = f(downstream consumers, …)."** There is **no consumer or lineage graph anywhere in the platform.** "Downstream consumers" is invented data. The entire impact-ranking premise — the spec's proudest principle — rests on a field nothing produces.
3. **"Human Review Operations."** There is **no review system**: no queue table, no reviewer identity, no assignment/claim/lock, no SLA config, no persistence of human decisions. The remediation layer is proposal-only with `auto_applicable` hard-wired to `False` and **no accept/reject store.** This workspace specs a product that hasn't been built at any layer.

None of this makes the design bad. It makes it a **roadmap dressed as a spec**, and it must be honest about which widgets are "today" vs. "needs a new data contract first." The spec's own principle — *"honest about gaps … marks signals as upcoming rather than faking it"* — is violated by the spec itself everywhere except one flagged circuit-breaker.

Now, per workspace.

---

## 1. Trust Center

**1. What is excellent.**
The decomposed-score / "why it changed" strip is the single best idea in the document. A VP-facing trust verdict that names its top drivers is genuinely decision-grade, and choosing a confidence *distribution* over an average is the correct call given the known bimodal 0.0 spike — a mean would lie. This top band, alone, would justify the project.

**2. What is confusing.**
- **Two composite scores with overlapping inputs.** "Data Quality Score" (clean-rate + high-conf-pass + integrity) and "Dataset Health Score" (parse + integrity + dupes + schema) **both include integrity.** A VP will ask "why are there two numbers and which one gates my release?" The spec never says which score is authoritative. Pick one headline number; demote the other to a driver.
- **The ridgeline.** A confidence ridgeline is data-viz catnip and **executive poison** — you cannot read a value off it, and the VP audience this band targets will not parse a stacked density plot. The Principal Viz reviewer flags this: ridgelines impress designers and confuse executives. A simple current-vs-baseline histogram with the 0.0-mass called out as a number does the job.

**3. What is unnecessary.**
The 0–100 composite weighting is asserted with no justification. A weighted blend of three rates is a **made-up index**; its absolute value ("82") means nothing and its movements are only as trustworthy as weights nobody has validated. Either ground the weights in something (cost of each failure mode) or drop the composite and show the three real rates. A precise-looking fabricated index is worse than three honest percentages.

**4. What is missing.**
- **The release-gate workflow.** The VP's actual job here is go/no-go. There is no threshold, no "data is below the ship line," no way to *record* a go/no-go decision or annotate "we shipped despite the amber." The workspace shows trust but does not operationalize the decision it exists for.
- **Cold-start / empty state.** At launch there is no baseline and no history. Every delta and trend is blank. The spec has no design for day one, which is the day it will first be demoed.
- **Per-shard truth.** The driver strip says "shard 14" but the score is global. There's no shard scorecard, yet the data is multi-shard and quality is known to vary by shard.

**5. Would this be used daily?**
**No — and that's fine.** A VP checks trust before a release or in an incident, not daily. Designing the top band for a weekly/triggered visit (and making it deep-linkable into Slack) matters more than daily density. The spec over-invests in operator density on a page whose owner visits rarely.

---

## 2. AI Judge Performance

**1. What is excellent.**
Sorting judges by F1 *ascending* (worst on top) is the right operational instinct. The prompt-version diverging-bar comparison maps cleanly onto the existing `compare_prompts`/`detect_regression` eval code, so it is buildable and decision-grade. "Confidently wrong, sorted by confidence-of-the-wrong-answer" is a sharp, correct prioritization.

**2. What is confusing.**
The page conflates **two incompatible data sources** without saying so: the **labeled eval datasets** (offline, fixed, tiny) and the **live verdict stream** (unlabeled, large). Accuracy/P/R/F1 can *only* come from the labeled set; "failure clusters" over live traffic have **no ground truth** to define a "failure." The spec slides between them as if they're one feed. An operator will not know whether "Recall 0.71" describes 10 fixture examples or 600K live events. These must be visually segregated and labeled with their `n`.

**3. What is unnecessary.**
The **confusion-shift heatmap**. The eval datasets are **~10–12 examples each.** A confusion matrix on n=12 is mostly empty cells and single-count noise; a "shift heatmap" between two such matrices is **statistical theater** — it will show dramatic-looking migrations that are one example moving. This is the canonical "impressive but not actionable" widget. Cut it until eval sets are 100×.

**4. What is missing.**
- **Confidence intervals / sample-size honesty.** P/R/F1 on tiny n must show error bars or an explicit "n too small to trust" state. Presenting F1=0.83 from 12 examples as a precise number is the most dangerous lie in the whole console — it will drive prompt promote/rollback decisions off noise.
- **The human-label feedback loop.** The "disagreement matrix — who the human sided with" requires captured human adjudications. **Nothing captures them** (see Workspace 4). So the truest judge-quality signal in the spec depends on a workflow that doesn't exist. This is a circular dependency the spec never acknowledges.
- **Drift of the live judge vs. its own past.** With no eval label on live data, the only honest live signal is *distributional* (is the judge's pass-rate/confidence drifting?) — and that's not specced here; it's half-buried in Workspace 5.

**5. Would this be used daily?**
**No.** This is a **pre-promotion** tool, used when someone ships a prompt — episodic, maybe weekly. The "Promote / Hold" button also implies this read-mostly console can deploy a prompt version; that's **scope creep into deployment control** the platform has no machinery for (no rollback, per the production review). Show the recommendation; don't pretend the button ships it.

---

## 3. Cost & Efficiency

**1. What is excellent.**
Unit economics first (cost per 1k events, cost per verdict) is exactly the Stripe-grade framing executives respond to. The cost waterfall by tier is a genuinely good way to show the escalation premium, and it maps to real `quality_verdicts.cost_usd`/`model` data. Budget burn as a *pace line with a projected exhaust date* beats a gauge.

**2. What is confusing.**
The waterfall mixes **real money and fabricated money in one chart.** "rules ($0) → Haiku → Sonnet → **human review (modeled)**." The first three are measured `cost_usd`; the fourth is an assumed `hours × rate` with no basis. Putting a guessed number in the same visual grammar as metered spend will get someone to quote the total in a board meeting as if it's all real. **Separate measured cost from modeled cost, visually and verbally.**

**3. What is unnecessary — and this is the big one.**
**"Human-review hours saved" as the ROI hero number is a vanity metric.** It is computed as `auto-cleared events × assumed-minutes-per-review`. The assumed minutes is a constant nobody has measured; the "auto-cleared" baseline assumes every event would otherwise have been human-reviewed, which is false. It is the textbook "impressive but not actionable" figure: it cannot go down, it drives no decision, and it inflates with volume regardless of quality. The spec literally calls it "the line that justifies the platform's existence" — that's the tell. **Demote it, footnote the assumptions, or cut it.** A CFO who discovers the assumption will distrust the entire workspace.

**4. What is missing.**
- **Cost anomaly / spike attribution.** The actionable cost question is "why did spend jump *yesterday*?" — a sudden escalation-rate change, a prompt that got more verbose, a retry storm. There's no cost-spike detector, only smooth trends. Smooth trends are not where money leaks.
- **Per-prompt-version token cost.** A new prompt that doubles input tokens is the most common silent cost regression. Cost should be attributable to `prompt_version` (the data exists), and it isn't.
- **Forecast confidence.** The burn projection is a single line; a linear extrapolation of LLM spend is wrong on day one of a traffic change. No band, no scenario.

**5. Would this be used daily?**
**By the Ops Lead, weekly; by executives, monthly.** Not a daily surface — which means the daily-cost-leak detection (the missing piece above) is *more* important than the executive band, because nobody's watching the slow trends in real time anyway.

---

## 4. Human Review Operations

**1. What is excellent.**
The *intent* — rank by impact, SLA-as-risk-heatmap not a clock, proposals as accept/reject decisions — is the correct mental model for a review console. If the underlying system existed, this is how it should be shaped. The "high-impact × old" hot cell is the right thing to make loud.

**2. What is confusing.**
The **impact score is undefined and undefinable on current data.** `f(downstream consumers, category volume, confidence-of-uncertainty, age)` — *downstream consumers do not exist as data.* So the headline sort key of the team's primary daily surface is **built on a phantom field.** Worse, it's opaque: a reviewer cannot tell *why* item A outranks item B, which kills trust in the queue order. Either define impact from fields that exist (category volume + confidence + age) and show the formula, or don't claim impact ranking.

**3. What is unnecessary.**
Reviewer **throughput/backlog charts on this page.** That's a *manager's* view (Ops Lead), not a reviewer's. The person adjudicating an event does not need an intake-vs-clearance line in their face; it's clutter on a working surface. Move it to Platform Health or a team-lead view.

**4. What is missing — and this is structurally fatal.**
This workspace specs the **UI for a backend that does not exist.** Concretely absent, at *every* layer:
- **No queue persistence.** "REVIEW" is a transient `final_status` on an outcome, not a durable, assignable work item.
- **No reviewer identity, assignment, claim, or lock.** Two reviewers will open the same event. There is no "assigned to me."
- **No capture of the human decision.** When a reviewer adjudicates, *nothing records it* — which also breaks Workspace 2's disagreement matrix and any future judge-vs-human eval. This is the most important missing thing in the entire console.
- **No SLA definition.** "SLA aging" needs an SLA. None is configured anywhere.
- **No bulk actions.** "Accept 50 low-risk proposals" is the #1 reviewer-throughput feature and is absent.
- **No remediation persistence.** Proposals are `auto_applicable=False` with no store for accept/reject, no write-back path, no audit.

You cannot ship a review *dashboard* before the review *system*. This workspace is a roadmap item mislabeled as a design.

**5. Would this be used daily?**
**This is the ONLY genuinely daily workspace in the console** — and it is the most fictional. That inversion is the single biggest risk in the spec: the most-used surface depends on the most missing infrastructure. Priorities are upside-down.

---

## 5. Data Quality Intelligence

**1. What is excellent.**
The rule-failure small-multiples sorted by delta magnitude is a strong, honest pattern, and it maps to the real rule-metrics sink. Drawing known baselines (floor-fail ~9.7%, ref-integrity ~2.4%) as reference bands so "normal" is visible is exactly right — most anomaly tools fail by not showing normal.

**2. What is confusing.**
"Category drift ribbon" and "confidence-drift distribution-shift view" overlap conceptually with the Trust Center's confidence trend and with Workspace 2's live drift. **Three workspaces touch confidence drift** with three different visuals. The Head of DQ and the VP will see different-looking confidence widgets and ask which is right. Pick one canonical confidence-drift view and link to it.

**3. What is unnecessary / actively risky.**
The **automatic anomaly feed at the specced cardinality is an alert-fatigue generator.** "rule × shard × category" change detection = 8 rules × 24 shards × 29 categories ≈ **5,500 cells**, each with median±MAD bands. Even with `min_samples=20` suppression, this produces either a firehose of single-event "anomalies" or — once suppression kicks in on low-volume cells — mostly silence punctuated by noise. Statistical anomaly detection on sparse, multi-dimensional count data is **notoriously a false-positive machine.** The spec presents it as a clean "read the feed, don't build the query" feature; in practice the Head of DQ will mute it in a week. Either drastically reduce dimensionality (rule-level only, with category as a drill-down) or don't promise automatic anomalies.

**4. What is missing.**
- **The action.** An anomaly feed that detects "conditional_completeness jumped in receives_financing" leads to... what? There's no workflow to open a rule ticket, suppress a known-benign drift, or mark "investigating." Detection without a response loop is just more numbers.
- **Root-cause linkage to source.** Drift in a category is often one bad source/shard. The spec links to "filtered events" but not to the *source* dimension, which is where DQ actually intervenes.

**5. Would this be used daily?**
**By the Head of DQ, yes-ish** — but only if the anomaly feed earns trust. A noisy feed gets abandoned, and then the whole workspace goes unvisited. Its daily-use viability is entirely contingent on solving the false-positive problem the spec hand-waves.

---

## 6. Platform Health

**1. What is excellent.**
Percentile-fan latency (p50/p90/p99) instead of a mean is the correct, Datadog-grade choice — the tail is the operational truth. The alert-timeline swimlane is a real gap-filler: the alert engine currently has nowhere to live, and this gives it an operational memory. Storage-growth-with-projection surfaces the retention conversation early. This is the most production-credible workspace in the spec.

**2. What is confusing.**
"Latency split by stage (rules vs. LLM)" — **the trace does not store per-stage timings.** `trace_logs` holds a `payload_hash`, not durations; only the gateway's per-verdict `latency_ms` exists. So the rules-vs-LLM latency split is **not computable** from current data. The spec asserts a breakdown the schema can't support, and an operator debugging latency will trust a split that's actually just LLM latency relabeled.

**3. What is unnecessary.**
Throughput "events per minute" as a live tile is low-value for a system the production review established is a **batch pipeline with no service, no live ingestion, and no scheduler.** There is no steady-state throughput to monitor — there are batch runs. A live EPM tile implies a streaming system that doesn't exist. Show per-run throughput, not a real-time rate.

**4. What is missing.**
- **The metrics-history substrate.** Same root problem as everywhere: `MetricsSnapshot` is in-memory. Provider-failure trends, latency-over-time, and the alert timeline all need a persisted telemetry store. Platform Health is the workspace that *most* needs the thing the platform most lacks.
- **Alert acknowledgement / on-call routing.** The timeline shows alerts but offers no ack, no "who's on it," no routing. The production review already flagged that alerts are computed but delivered nowhere; the dashboard *displays* them but still doesn't *route* them. Showing an unrouted alert is not incident response.
- **Run/job status.** For a batch system the #1 health question is "did last night's run finish, and did it error?" There's no run-status surface at all.

**5. Would this be used daily?**
**Only during incidents and after batch runs.** For a non-service batch system there's no 24/7 thing to watch. The spec designs a real-time NOC for a system that runs in bursts.

---

## 7. Cross-cutting risks

### 7.1 Information overload
- **Six dense workspaces is a lot of console** for a 5-person audience where 4 of them visit episodically. The spec's "information density is a feature" mantra is right for the *operator* (one person, one workspace) and wrong as a global default — it pushes density onto executive surfaces that should be sparse.
- **Per-page small-multiples + heatmaps + ridgelines + ranked tables stacked together** (esp. Trust Center and Data Quality Intelligence) will exceed the "executive reads the top band in 10s" promise. The top band competes with a wall of operator viz directly beneath it. Progressive disclosure is *claimed* but the layout co-locates exec and operator content on one scroll — they need a harder visual or interaction boundary (collapse operator detail by default).

### 7.2 Visual clutter
- **Three redundant status systems**: the global severity banner, the left-rail state pips, *and* per-workspace severity. Three places encoding "is this bad" will disagree at the edges (banner says red, pip says amber) and erode trust. Collapse to one source of truth.
- **Ridgelines and stacked bars** violate the spec's own restraint ethos. Ridgelines (Trust Center) are unreadable for values; the "small stacked bar" for cost-per-verdict-by-tier (Workspace 3) makes segment comparison hard — the exact failure mode the spec criticizes pie charts for. The design system preaches discipline the workspaces don't always keep.
- **Tabular-figures everywhere + sparklines in every table cell + deltas + reference bands** is a lot of ink per row. Ranked tables with 8 columns each carrying a sparkline become unreadable past ~7 rows.

### 7.3 Impressive-but-not-actionable metrics (the vanity list)
1. **Human-review hours saved** — assumption-driven, monotonic, drives no decision. The worst offender.
2. **The 0–100 composite scores** — fabricated indices with unvalidated weights; movement is uninterpretable in absolute terms.
3. **P/R/F1 on n≈12** — precise-looking, statistically meaningless without intervals.
4. **Confusion-shift heatmap** — dramatic on tiny n, signal-free.
5. **Live "events per minute"** — a streaming metric for a batch system.
6. **Drill-through rate > 40% as a success KPI** — a vanity *product* metric; high drill-through can mean the aggregates failed to answer the question, not that they succeeded. Don't optimize it.

### 7.4 Missing operational workflows (across the whole console)
- **No human-decision capture** — breaks the review loop AND judge evaluation. #1 gap.
- **No assignment/claim/lock/bulk-action** in queues.
- **No alert acknowledgement, routing, or on-call** anywhere.
- **No annotations / incident notes / "investigating" states** — detection never closes into response.
- **No saved views / saved filters / shareable deep links** for recurring use.
- **No scheduled export / emailed exec digest** — executives won't log in daily; the console has no push.
- **No access control / PII redaction by role** — event summaries and article text (plaintext, per the production review) are shown to all five personas with no field-level gating. The Review Team needs full text; does the VP? This is a governance hole.
- **No cold-start / empty-state design** — day-one demo is all blank trends.
- **No run/job status** for the batch pipeline that is the actual unit of work.

---

## 8. Summary scorecard

| Workspace | Excellent | Fatal/structural flaw | Daily use? |
|---|---|---|---|
| **Trust Center** | Decomposed "why-it-changed" verdict | Two overlapping composites; fabricated index weights; needs metrics history | Weekly/triggered |
| **AI Judge Performance** | Worst-first F1 ranking; prompt diff | P/R/F1 on n≈12 with no intervals; depends on uncaptured human labels | Episodic |
| **Cost & Efficiency** | Unit economics + burn pace | Vanity "hours saved"; measured & modeled cost mixed in one chart | Weekly/monthly |
| **Human Review Ops** | Correct impact/SLA mental model | **Entire backend (queue, identity, decision capture, SLA) does not exist** | **Daily — and most fictional** |
| **Data Quality Intelligence** | Rule small-multiples + baseline bands | Anomaly feed is a false-positive machine at specced cardinality | Daily *if* feed earns trust |
| **Platform Health** | Percentile-fan latency; alert timeline | Per-stage latency not in schema; metrics history absent; batch ≠ NOC | Incident-only |

### The three things to fix before this spec is buildable
1. **Build the data substrate first.** A persisted metrics/time-series store and an actual human-review system (queue + identity + decision capture) are *prerequisites*, not details. Re-label every widget as "ships today on current tables" vs. "needs new data contract X." Honesty the spec demands of itself.
2. **Define `impact` from fields that exist** and show the formula, or stop claiming impact ranking. A phantom sort key on the primary daily surface is the most damaging single flaw.
3. **Purge the vanity metrics** — hours-saved, fabricated composites, n≈12 F1 without intervals, confusion-shift heatmap. They're the parts most likely to be quoted and least likely to be true, and they'll poison trust in the honest 80% of the console.

**Bottom line:** the *design language* is excellent and the *decision-instrument philosophy* is right. But the spec writes checks the platform's data can't cash, and its most-used workspace is its least-built. It is a strong v2 design and a misleading v1 plan. Sequence it behind the data contracts, and it becomes the real thing.

---

*End of design review. No code, no implementation, no commits.*
