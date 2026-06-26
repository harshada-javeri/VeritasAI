# Stakeholder Feedback Integration — Firmable

*How Firmable's product feedback maps onto VeritasAI's existing architecture, what it validates,*
*and where it points the next phase.*

**Date:** 2026-06-24 · **Source:** Firmable stakeholder review · **Status:** direction-setting (no code changes in this document)

---

## Feedback Summary

Firmable gave three pieces of feedback, in priority order:

1. **Precision matters more than coverage.** A wrong "this event is good" is far more expensive than
   a missed flag. Firmable would rather we surface fewer issues with high confidence than chase
   exhaustive recall and erode trust in the verdict. The product's credibility lives in being *right
   when it speaks*, not in speaking about everything.

2. **Humans must own ambiguous decisions.** When an event is genuinely uncertain, the system must
   not silently auto-resolve it. A named human is the decision-maker of record for the ambiguous
   tail; the machine's job is to *triage to that human with context*, not to guess on their behalf.

3. **Source-level drift analysis is more valuable than aggregate quality trends.** A single org-wide
   "data quality is 94%" number hides the thing operators actually act on: *which source/vendor/domain
   started producing worse data, and when.* Quality is most useful when it is attributable to a
   source, not averaged across all of them.

The throughline: **Firmable values trustworthy, attributable, human-owned judgment over broad,
aggregate automation.** That is the same value system VeritasAI was built on — the feedback sharpens
priorities rather than redirecting them.

---

## Impact on Product Direction

### Why precision > recall for this problem

The cost asymmetry is structural, not stylistic. VeritasAI's verdicts gate a downstream
intelligence feed that other teams *consume as truth*. The two ways to be wrong are not equal:

- **A false "pass" (missed defect)** flows downstream as a clean record. A consumer acts on a
  mislabeled acquisition or a wrong company-subject, and the error is now in *their* decisions —
  discovered late, expensive to trace back, and corrosive to trust in the whole feed.
- **A false "fail" (over-flag)** costs reviewer minutes and is caught immediately at the review
  queue. It is annoying, it is bounded, and it never leaves the building.

When the downstream cost of a missed defect dwarfs the cost of an extra review, the correct operating
point is **high precision on the "this is a problem" signal**, accepting lower recall. Concretely,
this means the bar to *auto-resolve* (auto-pass or auto-fix) should be high and the bar to *escalate
to a human* should be low. A judge that is "probably right" is not allowed to close a decision; it is
allowed to ask a person.

This also reframes how we measure the judges. The eval harness already reports precision, recall, and
F1 per check — but Firmable's feedback tells us **precision is the metric we optimize and gate on**,
and recall is the metric we *monitor for erosion* rather than maximize. A prompt change that raises
recall while dropping precision is a regression for this product, even if F1 improves.

### Why human-in-the-loop is a product requirement (not a fallback)

In many systems, human review is the thing you build to cover for an imperfect model — a temporary
crutch you hope to automate away. Firmable's second point inverts that: **human ownership of the
ambiguous tail is the product, not the scaffolding.** The value VeritasAI sells is *defensible
decisions*, and a decision is only defensible if someone is accountable for it when it was genuinely
a judgment call.

This has three consequences for direction:

- **The "uncertain" band is a feature surface, not an error state.** It is where the product earns
  its keep. The work is to make that handoff *excellent* — give the reviewer the evidence, the
  judge's reasoning, the source, and the lineage — not to shrink the band toward zero at the cost of
  precision.
- **Auto-resolution must stay conservative by design.** Anything the system closes without a human
  must clear a high-confidence, low-risk bar; everything else routes to a person. We never trade
  away human ownership of ambiguity to hit an automation rate.
- **Reviewer experience becomes a first-class product concern.** If humans own the hard decisions,
  their throughput, context, and queue health are core metrics — not operational afterthoughts.

### Why source-level traceability matters

Aggregate quality is a *vanity metric* for an operator: it tells you the weather, not where the leak
is. Firmable's third point says the actionable unit of analysis is **the source** — the publisher
domain, the vendor, the article origin behind each event.

This matters because data quality problems are almost never uniform. They are *concentrated*: one
syndicated-reprint farm, one PR-wire vendor, one domain that changed its formatting last Tuesday.
An org-wide trend line that dips from 94% to 91% tells you something is wrong; a source-attributed
view tells you *vendor X's semantic-accuracy pass rate fell from 96% to 70% starting June 18*, which
is a thing you can act on — throttle the source, re-weight its confidence, open a vendor conversation,
or quarantine its backlog.

The dataset already carries the lineage to do this. Every event resolves a
`most_relevant_source` → a `news_article` with a `url` and domain, and source credibility is one of
the three LLM checks we designed (Check B: genuine news vs. press release vs. syndicated reprint vs.
low-signal). The feedback tells us to **promote source from an input feature to a primary axis of
analysis** — to slice quality, cost, and drift *by source*, and to make "which source is degrading"
a question the system answers directly rather than one an operator reconstructs by hand.

---

## Changes to Dashboard Strategy

The Phase 7 console was built as a read-only Decision Intelligence Console over the existing storage
layer. Firmable's feedback validates most of its structure and redirects the emphasis of a few views.

### Views validated by the feedback

These are doing exactly what Firmable values and should be kept and deepened:

- **Trust Center.** Its premise — surface a transparent, attributable trust posture rather than a
  single opaque score — is precisely the "precision and defensibility over a vanity number" instinct.
  The transparent, weighted data-quality index (it shows the formula, not a magic number) is the
  right shape. Validated.
- **Human Review (the read-only review viewer).** Firmable's "humans own ambiguous decisions" makes
  this the *center of gravity* of the product, not a side panel. The view that surfaces the review
  queue with the judge's reasoning and evidence is validated and should grow (see below).
- **AI Judge Performance.** Built around offline eval scorecards with an always-on small-sample
  warning. Firmable's precision-first stance makes this view *more* important: it is where we prove
  the judges are precise enough to be trusted to auto-resolve. The honesty about small `n` is exactly
  right. Validated — with a shift toward foregrounding **precision** as the headline metric.
- **Event Detail (the drill-down spine).** Every aggregate links down to a single event's full
  verdict stack, trace, and cost. This *is* defensibility made navigable — the ability to answer
  "why did we decide this?" for any record. Strongly validated.
- **Cost & Efficiency.** Still valid as the cost-discipline story; lightly affected (see below — it
  should gain a per-source/per-review cost attribution).

### Views that should evolve

- **Data Quality Intelligence — evolve from aggregate to source-attributed.** This is the most direct
  consequence of feedback #3. Today the view reports quality *by check and by category* (worst-first
  by fail rate). It should add **source/vendor/domain as a first-class slice**: pass and fail rates
  *per source*, ranked worst-first, so the question "which source is hurting us" is answered on the
  page. The aggregate trend stays available but stops being the headline.
- **Trust Center — make drivers source-aware.** The index already exposes its component drivers;
  those drivers should be attributable to the sources moving them, so "trust dipped" comes with
  "because these two sources degraded," not just "because integrity fell."
- **Human Review — evolve toward ownership and routing, not just viewing.** The current view is
  read-only by V1 scope. Firmable's #2 elevates it: the eventual target is a view that supports
  *ownership* (who owns this decision), surfaces the *highest-leverage* ambiguous items first, and
  carries enough context (evidence span, judge reasoning, source credibility, lineage) that the human
  can decide quickly and defensibly. V1's honest caveat — that *impact ranking requires V2 lineage* —
  is exactly the gap Phase 8 fills.
- **AI Judge Performance — lead with precision, segment by source.** Reframe the scorecard so
  **precision is the primary number** and recall is shown as a monitored secondary. Add per-source
  segmentation so we can see *where* a judge is weak (e.g. a judge that is precise on genuine news but
  unreliable on a particular syndication source).

### What the feedback explicitly does *not* ask for

It does not ask for more breadth or more aggregate dashboards. The instinct to add "total events
processed" hero numbers or org-wide trend walls runs *against* this feedback. The console should get
**deeper and more attributable**, not broader.

---

## Phase 8 Direction

Phase 8 becomes **Source Intelligence & Root-Cause** — the phase that turns "source" from an input
field into the primary lens for quality, and turns the review queue from a list into an
ownership-and-diagnosis workflow. Four workstreams, in dependency order:

### 1. Source intelligence

Build the source as a first-class entity. Every event already resolves to a `news_article` with a
`url`/domain and a `most_relevant_source` relationship; Phase 8 aggregates verdicts, cost, and
outcomes **by source**, so the system can answer, for any publisher domain or vendor:

- What volume of events do they originate, and in which categories?
- What are their per-check pass / fail / uncertain rates (especially source-credibility and
  semantic-accuracy)?
- How much human-review load and LLM spend do they generate per clean event delivered?

This is the lineage layer the V1 console explicitly deferred ("impact ranking requires V2"). It is
read-and-aggregate work over data we already persist — no new mandatory dependency, consistent with
the storage-repository pattern.

### 2. Vendor quality scoring

On top of source aggregation, compute a **transparent per-vendor quality score** — the same design
philosophy as the Trust Center index: a weighted, *explainable* roll-up (credibility pass rate,
semantic-accuracy pass rate, duplicate/reprint rate, freshness), never an opaque number. The score's
job is to rank vendors so operators can act: prioritize, throttle, re-weight confidence on ingest, or
open a vendor conversation. Because precision is the product value, the score should weight
**confident defects** heavily and treat the ambiguous tail as a separate, human-owned signal — a
vendor isn't "bad" because it produces hard cases; it's "bad" because it produces confident failures.

### 3. Source-level drift detection

This is the direct build-out of feedback #3 and the natural extension of the canary/regression
discipline already in the system. Today drift defense is **model/prompt drift** on a frozen labeled
set (pinned models + scheduled canary eval). Phase 8 adds **source drift**: detect when a *source's*
quality distribution shifts over time — vendor X's credibility pass rate falling week-over-week,
a domain's semantic-accuracy collapsing after a site redesign, a reprint farm's duplicate rate
spiking. The mechanism mirrors the canary: a per-source baseline, a scheduled comparison, and an
alert when a source moves beyond threshold. Critically, this is **source-attributed**, so the alert
names the source and the moment — not "quality dropped" but "this source started degrading on this
date." This plugs straight into the existing `AlertEvaluator` shape (a new alert kind), reusing the
`min_samples` noise-suppression already in place.

### 4. Root-cause workflows

Tie it together with the human at the center (feedback #2). When a source-drift alert fires or a
vendor score drops, the operator needs to go from *symptom* to *cause* to *decision* without manual
spelunking. The root-cause workflow chains the drill-down spine that already exists:

- **Alert / score drop** (which source, when, how much) →
- **Contributing events** (the failing verdicts driving the drop, worst-first) →
- **Event Detail** (the full verdict stack, judge reasoning, evidence span, trace lineage for any
  one event) →
- **Decision of record** (a named human owns the resolution: throttle the source, re-weight,
  quarantine the backlog, or accept).

This is the review viewer evolving from a queue into a *diagnosis-and-ownership* surface — exactly
the "humans own ambiguity, with context" requirement. The append-only `trace_logs` and full verdict
provenance (`prompt_version`, `model`, cost, latency, timestamps) already provide the lineage; Phase 8
makes it walkable from a source-level symptom down to an owned decision.

---

## Design Decisions Confirmed

Firmable's feedback is, gratifyingly, a validation of choices VeritasAI already made. Connecting each
piece of feedback to the existing decision it confirms:

| Feedback | Existing VeritasAI decision it confirms |
|---|---|
| **Precision > coverage** | **The system fails safe toward REVIEW.** Every ambiguity and error biases to human review, never to silently passing bad data (parse failure → quarantine; budget exhaustion → REVIEW; any error → REVIEW; any non-pass LLM verdict → REVIEW). This *is* a precision-first posture: we don't auto-close on uncertainty. |
| **Precision > coverage** | **Conservative auto-resolution thresholds.** Verdict precedence requires high-confidence LLM fails to auto-fail and keeps remediation **proposal-only** (the `HeuristicRemediator` proposes, never silently writes). The machine doesn't get to be confidently wrong in production. |
| **Precision > coverage** | **The eval harness measures the judge before we trust it** (≥30 labeled examples/check, P/R/F1, regression gate). Firmable just tells us *which* metric to gate on: precision. |
| **Precision > coverage** | **Tiered escalation (Haiku → Sonnet on `uncertain`).** We spend more to get a *more precise* verdict exactly on the hard cases, rather than accepting the cheap judge's uncertain answer. |
| **Humans own ambiguity** | **"Humans = the backstop" was a founding principle** ("Rules gate. LLMs judge. Humans backstop."). The review queue, not auto-fix, is the destination for `uncertain` and low-confidence remediations. |
| **Humans own ambiguity** | **Remediation is proposal-only by design** — the system never silently writes a fix; a human approves. Ownership of the resolution stays human. |
| **Humans own ambiguity** | **REVIEW status is a persisted, first-class outcome** in `events_clean` — ambiguous decisions are routed and tracked, not swallowed. The Phase 7 Human Review view already makes that queue inspectable. |
| **Source-level traceability** | **Source credibility is already one of the three LLM checks** (Check B: genuine news / press release / syndicated reprint / low-signal). We always treated source quality as a judgment worth making. |
| **Source-level traceability** | **The data model carries full source lineage** — `most_relevant_source` → `news_article` (url, domain, published_at) is resolved on every event. The attribution Firmable wants is already in the persisted data. |
| **Source-level traceability** | **Append-only `trace_logs` + full verdict provenance** give per-event lineage (`prompt_version`, `model`, cost, latency, ts). Source-level drift analysis is an *aggregation* over lineage we already keep. |
| **Source-level traceability** | **The drill-down spine** (every aggregate links to Event Detail) is the navigational pattern root-cause workflows extend — from a source-level symptom down to a single event's full story. |
| **Source-level traceability** | **The canary/regression discipline** (pinned models + scheduled eval on a frozen set + `AlertEvaluator` with `min_samples`) is the exact mechanism source-drift detection reuses — a new alert kind, not a new system. |

**Net read:** none of the three pieces of feedback require an architectural change. Each one confirms
a decision already in the build and tells us where to *deepen* it. Precision-first is already encoded
in the fail-safe routing and proposal-only remediation; human ownership is the founding "humans
backstop" principle made into a product centerpiece; source-level analysis is an aggregation and a new
alert kind over lineage the system already persists. Firmable validated the bones — Phase 8 builds the
source-intelligence and root-cause layer the V1 console explicitly left for V2.
