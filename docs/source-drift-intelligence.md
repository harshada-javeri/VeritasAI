# VeritasAI — Source Drift Intelligence (Phase 8 Proposal)

*The natural Phase 8 evolution: promote **source** from an input field to the primary axis of quality,*
*cost, and drift analysis — so the platform answers "which feed is degrading, and when," not just*
*"what is the aggregate quality today."*
*Date: 2026-06-24 · Status: proposal · Origin: Firmable stakeholder feedback.*

> **Stakeholder mandate (Suresh / Firmable):** precision over coverage; humans own ambiguous
> decisions; **the most valuable insight is source-level drift and vendor degradation detection** —
> aggregate quality metrics are less useful than knowing *which source/feed is degrading.* This
> document turns that mandate into a buildable phase. Full feedback analysis:
> [STAKEHOLDER_FEEDBACK_INTEGRATION.md](STAKEHOLDER_FEEDBACK_INTEGRATION.md).

---

## 1. Why this, why now

An org-wide "data quality is 94%" number is the weather report: it tells you something is off but not
where the leak is. Quality problems are never uniform — they concentrate in *one* syndication farm,
*one* PR-wire vendor, *one* domain that changed its formatting last Tuesday. The actionable unit is the
**source**: the publisher domain / vendor behind each event.

The platform already carries the lineage to do this and simply hasn't aggregated on it yet:

- Every event resolves a `most_relevant_source` → a `news_article` with a `url`/domain
  (`docs/data-quality-findings.md`: source present on 100% of events).
- **Source credibility is already a first-class judge** (Check B) — its per-event verdict *is* a
  source-quality signal waiting to be grouped by source.
- `quality_verdicts` persists `confidence`, `cost_usd`, `latency_ms`, `prompt_version`, `model`, `ts`
  per check per event; `trace_logs` is append-only lineage. Phase 8 is an **aggregation-and-detection
  layer over data already produced**, not a new collection system.

This is the same "promotes without rewrite" discipline as the rest of the platform: the contracts hold;
we add a source dimension and a detector.

---

## 2. Vendor-level quality scoring

A transparent, explainable score per vendor/source — same philosophy as the dashboard's Trust Center
index: **show the formula, never a magic number.**

**Definition (proposed, all components already measured):**
```
VendorQuality(source) = weighted blend of, over events from that source in the window:
    credibility_pass_rate   (Check B pass rate)            weight 0.35
    semantic_accuracy_rate  (Check A pass rate)            weight 0.25
    integrity_pass_rate     (referential_integrity pass)   weight 0.15
    originality_rate        (1 − duplicate/reprint rate)   weight 0.15
    freshness_rate          (date_sanity pass)             weight 0.10
```
Every component is a rate already computed per event; the score is a documented weighted sum with the
component breakdown shown inline, so a vendor's score always carries *why*.

**Precision-first weighting (per the mandate):** the score weights **confident failures** heavily and
treats the ambiguous tail separately. A vendor is not "bad" because it produces hard cases that route to
human review; it is "bad" because it produces *confident defects*. So `fail` verdicts at confidence ≥
0.80 drive the score; `uncertain`/low-confidence verdicts are reported as a separate "review load"
metric, not folded into the quality number. This prevents penalizing a source for honest ambiguity and
keeps the score aligned with the precision-over-coverage value.

**Output:** a ranked vendor table (worst-first), each row decomposed into its component rates, each
linking down to the contributing events — the existing drill-down spine.

---

## 3. Source-level trust scoring

Vendor quality is *historical*; source **trust** is the *forward-looking* operating decision: how much
should the pipeline believe this source right now?

- **Trust tier** (derived from VendorQuality + recency + volume): `trusted` / `watch` / `throttle` /
  `quarantine-on-ingest`. A `trusted` source's clean events can use a lighter sampling rate; a
  `throttle` source's events get a higher LLM-escalation rate; a `quarantine-on-ingest` source is held
  for review before spend.
- **Confidence re-weighting:** a source's trust tier becomes a prior on `confidence_floor` — events
  from a `watch` source clear the floor at a higher bar. This is a config-level lever, not new model
  work, and it directly serves precision (be stricter on sources with a track record of defects).

Trust is **transparent and reversible**: a tier is always shown with the score and window that produced
it, and a source climbs back to `trusted` as its recent quality recovers.

---

## 4. Drift detection

The core deliverable, and the direct extension of a discipline the platform already has. Today drift
defense is **model/prompt drift** — pinned model IDs + a scheduled canary eval on a frozen labeled set
(README §8). Phase 8 adds **source drift**: detect when a *source's* quality distribution shifts over
time.

**Mechanism (mirrors the canary + the existing alert engine):**
- Maintain a per-source rolling baseline (trailing median ± MAD) for each component rate
  (credibility, semantic, integrity, originality, freshness) and for verdict-confidence distribution.
- On each scheduled run, compare the current window to the baseline; flag a source whose rate moves
  beyond a `k·MAD` band, with the existing `min_samples` noise-suppression (the alert engine's pattern,
  so single-event blips don't fire).
- **The alert is source-attributed and time-stamped** — the whole point of the mandate: not "quality
  dropped" but *"`techcrunch-syndicate.example` credibility pass-rate fell from 0.96 to 0.70 starting
  2026-06-18, n=412."*

**Detector types:**
- **Rate drift** — a component rate degrading (the common case: a vendor's credibility falling).
- **Distribution drift** — a source's confidence histogram shifting (e.g. mass moving toward the
  uncertain band, an early warning before pass-rate moves).
- **Volume drift** — a source's event volume spiking or collapsing (a reprint farm flooding, or a feed
  going dark).
- **Mix drift** — a source's category mix shifting away from its baseline.

---

## 5. Escalation triggers

Drift findings must *do something*, on the same fail-safe principle as the pipeline (bias toward a
human, never toward silent acceptance):

| Trigger | Condition | Action |
|---|---|---|
| **Soft drift** | one component beyond 2·MAD, `min_samples` met | Move source to `watch`; raise its escalation sample rate; surface in the anomaly feed. |
| **Hard drift** | credibility/semantic pass-rate beyond 3·MAD, sustained 2 windows | Move source to `throttle`; fire a source-drift alert (new `AlertEvaluator` kind); open a root-cause workflow (§7). |
| **Collapse** | pass-rate below an absolute floor, or volume spike with degraded quality | Move source to `quarantine-on-ingest`; page the Ops Lead; hold the source's backlog for review. |
| **Recovery** | rates back within baseline for N windows | Auto-promote the tier back up; clear the alert; record the episode in source history. |

These are **proposals to operators by default** (precision-first, human-owned) — the tier change for a
`throttle`/`quarantine` decision surfaces as an accept/confirm action, not a silent automatic
re-routing, until a source has enough history to automate safely.

---

## 6. Feed degradation detection

A "feed" is a collection of sources (a vendor that supplies many domains, or a shard). Feed-level
degradation is the aggregate-with-attribution view the mandate asks for: roll source drift *up* to the
feed, but keep the *down*-attribution one click away.

- **Feed health = distribution of its sources' trust tiers**, not an average rate. A feed with 95%
  trusted sources and one collapsing source is healthier than a feed uniformly mediocre — and the
  collapsing source is the actionable item, which an average would bury.
- **Degradation signal:** a feed degrades when its mass of `watch`/`throttle` sources grows, or when a
  high-volume source within it drifts. The signal names the *responsible sources*, ranked by blast
  radius (events × downstream consumers × confidence) — never a bare feed-level percentage.
- This directly answers Suresh's framing: *aggregate metrics are less useful than knowing which feed is
  degrading* — so feed health is always presented as "which sources, how much, since when," not "94%."

---

## 7. Root-cause workflow

Tie detection to a human-owned resolution, reusing the existing drill-down spine end to end:

```
Source-drift alert            (which source, which component, how much, since when)
   ↓ drill
Contributing events           (the failing verdicts driving the drop, worst-first by confidence×volume)
   ↓ drill
Event Detail                  (full verdict stack, judge reasoning, evidence_span, trace lineage, cost)
   ↓ decide
Decision of record            (a named human: throttle / re-weight / quarantine backlog / accept;
                               or fix upstream with the vendor)
```

Every step already exists in the platform as a primitive — the alert engine's shape, the
`quality_verdicts` provenance, the dashboard's Event Detail object view. Phase 8 wires them into a
*named workflow* with the source as the entry point. The human owns the resolution (the second
stakeholder mandate); the system's job is to make the path from symptom to cause to decision a few
clicks, with full evidence at each step.

---

## 8. Dashboard design

A new **Source Intelligence** workspace, plus targeted additions to existing ones, consistent with the
console's design system (decomposed scores, ranked tables, distributions, severity-only color,
drill-down spine — see [dashboard-product-spec.md](dashboard-product-spec.md)).

**New workspace — Source Intelligence** (owner: Head of Data Quality / Ops Lead):
- **Top band (executive):** count of sources by trust tier; the single worst-degrading source named,
  with its drift magnitude and start date; a feed-health strip decomposed by responsible sources.
- **Vendor quality table (ranked, worst-first):** one row per source — VendorQuality score decomposed
  into its component rates, trust tier, event volume, review-load, drift flag. Sorts by drift magnitude
  so the mover is on top (severity over recency).
- **Drift feed (automatic):** source-attributed, time-stamped drift events as a ranked feed —
  *"this source just started behaving unusually"* — each linking to contributing events. The operator
  reads the feed; they do not build the query.
- **Source detail (object view):** a single source's quality trend (per component), its confidence
  distribution vs. baseline (distribution view, not a mean line), its trust-tier history, and its
  contributing events — the Palantir-style drill target, now keyed on source as well as event/check.

**Additions to existing workspaces:**
- **Data Quality Intelligence:** add source as a slice on the rule-failure grid and a source-drift lane
  in the anomaly feed.
- **Trust Center:** make the "why" driver strip source-aware ("trust dipped −3.1: source X credibility
  fell"), so the executive verdict names the responsible source.
- **Cost & Efficiency:** add cost-per-clean-event *by source*, exposing vendors that are expensive to
  validate per trusted record delivered.

---

## 9. Future data contracts required

Phase 8 is mostly aggregation over existing data, but three additive contracts make it first-class.
All are additive — no existing schema changes, consistent with the platform's no-contract-break rule.

1. **A durable source dimension.** Today source domain lives inside the resolved event and the trace,
   not as a queryable column on `quality_verdicts`/`events_clean`. Add `source_domain` (and a stable
   `source_id`) to the persisted event projection so quality/cost can `GROUP BY source` without
   re-parsing. *Additive column; backfillable from the trace.*
2. **A `quality_metrics_by_source_daily` rollup** (the source-attributed sibling of the README §9
   `quality_metrics_daily` that is currently unbuilt). Pre-aggregated per (source, check, day): pass/
   fail/uncertain rates, mean confidence, cost, volume — so drift detection and the dashboard never
   scan raw verdict rows at feed scale. *Append-only, time-partitioned, the same pattern as the
   existing verdict store.*
3. **A `source_drift` alert kind + a source-trust state table.** Extend `AlertEvaluator` with a
   source-drift alert (same `AlertPolicy`/`min_samples` machinery), and persist the per-source trust
   tier + its history so tiers are durable across runs and the recovery logic has a baseline. *New
   enum value + one small table; no change to existing alert kinds.*

**Explicitly out of scope for Phase 8** (honest boundaries, per the platform's "honest about gaps"
principle): downstream-consumer lineage (true blast-radius impact ranking needs consumer graphs the
platform doesn't yet have — V1 already states "impact ranking requires V2"); automated vendor
offboarding (Phase 8 proposes, humans decide); and cross-vendor entity linkage. These are named so the
phase doesn't quietly imply capabilities it won't ship.

---

## 10. Phasing within Phase 8 (dependency order)

1. **Source dimension + backfill** (contract 1) — nothing aggregates by source without it.
2. **`quality_metrics_by_source_daily` rollup** (contract 2) — the queryable substrate.
3. **VendorQuality + trust scoring** (§2, §3) — read-and-aggregate over the rollup; transparent formula.
4. **Drift detection + `source_drift` alert** (§4, contract 3) — reuses the canary/alert pattern.
5. **Escalation triggers + trust-tier wiring** (§5) — config levers on the existing routing policy.
6. **Source Intelligence dashboard workspace + root-cause workflow** (§7, §8) — surfaces it all.

Each step ships something usable and reuses an existing platform primitive. The result: VeritasAI stops
reporting *what* the aggregate quality is and starts answering *which source is degrading, by how much,
since when, and what to do about it* — which is exactly what the stakeholder asked for.
