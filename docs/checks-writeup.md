# VeritasAI — Quality Checks, End to End

*Every quality decision in the platform, in one document. For each check: the business problem,*
*why it is a rule or an LLM, the prompt and rubric, the model choice, measured results, failure modes,*
*and what to improve next.*
*Date: 2026-06-24 · Eval figures from `make eval` (see [eval-results.md](eval-results.md)).*

The organizing decision is the **split**: *reach for a rule first; reach for an LLM only when the
question is semantic, contextual, or fuzzy.* Rules run on 100% of records at zero token cost and gate
the budget; LLM judges run only on what rules can't settle. This document covers both halves — the 8
deterministic rules in brief, then the 3 LLM checks in depth.

---

## Part 1 — Deterministic rules (the gate)

These run first, on every record, for free. A hard fail quarantines the record before any model is
called. Each rule exists because the data demanded it (see [data-quality-findings.md](data-quality-findings.md)
for the empirical numbers behind each one).

| Rule | Business problem | Why a rule (not an LLM) | Logic |
|---|---|---|---|
| `event_id_uuid` | Malformed IDs break joins and dedup | Pure format check | `event_id` is a valid UUID |
| `confidence_in_range` | Out-of-range scores corrupt downstream filters | Range check | `confidence ∈ [0,1]` |
| `confidence_floor` | The feed has a ~29K spike of `confidence=0.0` noise | Threshold | `confidence < 0.15` → quarantine |
| `category_known` | Novel/typo categories pollute the taxonomy | Set membership | `category ∈` known set, else review |
| `date_sanity` | Stale 2010 events resurface as "new" | Range + comparison | `found_at ≤ now`, not pre-2000, ≈ article date |
| `referential_integrity` | Dangling `company`/`source` refs break lineage | Join/resolve | every relationship id resolves to an included entity |
| `conditional_completeness` | Category-required fields missing (e.g. `amount` on financing) | Conditional presence | per-category required-field map on `amount_normalized` etc. |
| `exact_duplicate` | The feed carries 7,875 duplicate IDs (96% cross-shard) | Hash/identity | global `event_id`-keyed, first-wins → repeats quarantined, no LLM spend |

**Why these are rules:** every one is answerable by a regex, a range, a set-membership test, or a
join. None requires reading prose. They are exact, free, and run at full throughput — the README's
heuristic: *if you can write it as a regex, a range, a set, or a join, it's a rule.*

**Rollup precedence:** any rule FAIL → quarantine; any rule UNCERTAIN/REVIEW → review; else continue
to the LLM stage. A rule REVIEW persists even if a later LLM check passes — rule uncertainty is a
separate dimension and is never silently overridden.

---

## Part 2 — LLM checks (the judges)

Three checks, each a *versioned prompt + a strict output schema + an eval set*. All emit the same
`judge_output` shape (`verdict` / `confidence` / `reason` / `evidence_span`) via forced structured
output, so storage and tracing stay uniform and parsing never breaks.

---

### Check A — Semantic accuracy

**Business problem.** Does the event's `category` label actually match what the text says? A summary
that describes a lawsuit but is tagged `launches` is a silent data defect that flows downstream as
truth. This is the highest-volume quality question in the feed.

**Why an LLM, not a rule.** Answering it requires *reading meaning* — "does this prose describe a
launch?" — which no regex or set-membership test can do. It is the canonical semantic check.

**Prompt** (`semantic_accuracy.v1`, system + template, verbatim):
```
system: You validate whether a news event's CATEGORY label matches its text.
  Decide using only the provided fields. Rubric:
    - pass: the text clearly describes an event of the labelled category.
    - fail: the text describes a different event type, or no event at all.
    - uncertain: the text is ambiguous, truncated, or insufficient to decide.
  Set evidence_span to the shortest phrase from the text that drove your decision.
  Return only the structured verdict.
template: CATEGORY: $category / SUMMARY: $summary / SENTENCE: $article_sentence
```

**Rubric.** Three classes — `pass` (text clearly matches the category), `fail` (text describes a
different event or none), `uncertain` (ambiguous/truncated). The `evidence_span` requirement forces the
judge to ground its verdict in a specific phrase, which both improves quality and makes the verdict
auditable.

**Model choice.** **Haiku** (`claude-haiku-4-5-20251001`). High-volume, narrow classification — exactly
Haiku's strength. It runs on every escalated event and on the CLEAN sample, so cost discipline here
dominates the bill; using Sonnet would roughly triple per-call cost for a task Haiku does well.

**Evaluation (v2, n=12):** accuracy **0.917**, macro F1 **0.630**. Per-class: `pass` F1 **1.000**,
`fail` F1 **0.889**, `uncertain` F1 0.000. v2 was promoted over v1 by the regression gate (+0.083
accuracy, +0.052 macro-F1, nothing regressed). It is the strongest of the three judges on the decisive
classes.

**Failure modes.** One error in 12: `sa-12` ("Report mentions Acme in passing", gold `uncertain`) was
called `fail` at confidence 0.40 — an insufficient-evidence case over-committed to a defect verdict.
The judge is decisive and accurate on clear cases; its weakness is forcing genuinely-ambiguous text
into a confident class instead of `uncertain`.

**Future improvements.** (1) Expand the eval set to ≥30 with more `uncertain` and truncated-sentence
examples — the class is currently unmeasurable at n=1. (2) Add a confidence-floor → review rule (~0.80)
so low-confidence calls like `sa-12` route to a human regardless of class. (3) Sample rare categories
(the long tail beyond launches/partners_with/hires) into the eval set deliberately.

---

### Check B — Source credibility

**Business problem.** Is the source genuine, original news reporting — or a press release, marketing
content, or a syndicated reprint? Low-signal sources inflate the feed with PR puffery dressed as
events. This is also the check that Firmable's stakeholder feedback elevates: source quality is the
unit operators most want attributed (see [source-drift-intelligence.md](source-drift-intelligence.md)).

**Why an LLM, not a rule.** This is genre/intent classification from text — distinguishing a
TechCrunch report from a PRNewswire release from a company blog. A domain allowlist is a crude proxy at
best (PR and reprints appear on reputable domains); the judgment needs to read the article.

**Prompt** (`source_credibility.v1`, verbatim):
```
system: You assess whether a news article is a credible, original news report about a
  real event, as opposed to a press release, marketing content, or a syndicated
  reprint. Decide using the title, body excerpt, and source domain. Rubric:
    - pass: reads as genuine, original news reporting.
    - fail: reads as a press release, marketing/promotional content, or a reprint.
    - uncertain: not enough signal to tell.
  Set evidence_span to the phrase or cue that drove your decision.
  Return only the structured verdict.
template: SOURCE_DOMAIN: $url_domain / TITLE: $article_title / BODY_EXCERPT: $article_body
```

**Rubric.** `pass` (genuine original reporting), `fail` (PR / marketing / reprint), `uncertain` (too
little signal). It reads three inputs — domain, title, and a body excerpt (first ~600 tokens, not the
full body, to keep it cheap).

**Model choice.** **Haiku for the bulk, escalate the `uncertain` band to Sonnet**
(`claude-sonnet-4-6`). The tiered design spends the stronger model only where the cheap one is unsure —
the platform's primary cost lever.

**Evaluation (v1, n=10):** accuracy **0.800**, macro F1 **0.563**. Per-class: `fail` precision
**1.000** (every "this is PR/reprint" call was correct — the safe direction), `fail` recall 0.750,
`pass` F1 0.833, `uncertain` 0.000. Balanced, with the conservative bias you want: it rarely
false-accuses a source.

**Failure modes.** Two errors. `sc-06` ("Company blog: We welcome our new CTO", gold `fail`) was
accepted as `pass` at 0.61 — company-authored content read as independent news, the most important
miss for this check. `sc-10` ("Unclear blogspot post", gold `uncertain`) was forced to `pass` at 0.49.
Both are the same shape: a marginal source credited too generously.

**Future improvements.** (1) Add domain-class features (known-wire vs. known-PR-distributor vs.
self-published) as prompt hints — cheap signal the model currently has to infer. (2) Expand eval to
≥30 with more company-blog and sponsored-content negatives (the `sc-06` class). (3) This check is the
natural backbone of Phase 8 vendor-quality scoring — its per-source pass rate *is* a vendor trust
signal.

---

### Check C — Entity resolution

**Business problem.** Is the linked `company1` plausibly the *subject* of the event — the actor the
category applies to — rather than merely mentioned? This catches the expensive "law-firm-vs-defendant"
swap and wrong-company merges. Entity errors are the costliest downstream because they corrupt the
who-did-what graph.

**Why an LLM, not a rule.** This needs judgment about who-did-what-to-whom in prose — a referential
reasoning task. The rule layer's `referential_integrity` only checks that the id *resolves*; whether
the resolved entity is the right *subject* is semantic.

**Prompt** (`entity_resolution.v1`, verbatim):
```
system: You verify whether the linked company is plausibly the SUBJECT of the event
  described in the text (the actor the category applies to), not merely mentioned.
  Decide using the summary, sentence, and the linked company name/domain. Rubric:
    - pass: the linked company is plausibly the event subject.
    - fail: the linked company is the wrong entity (e.g. mentioned but not the subject).
    - uncertain: the text does not make the subject clear.
  Set evidence_span to the phrase that identifies the true subject.
  Return only the structured verdict.
template: SUMMARY: $summary / SENTENCE: $article_sentence /
  LINKED_COMPANY1: $company1_name ($company1_domain) / OTHER_COMPANY2: $company2_name
```

**Rubric.** `pass` (linked company is plausibly the subject), `fail` (wrong entity — mentioned but not
the subject), `uncertain` (subject unclear).

**Model choice.** **Sonnet** (`claude-sonnet-4-6`) — the nuanced one, run at the stronger tier because
entity errors are expensive and the reasoning (subject vs. advisor vs. mention) is subtle.

**Evaluation (v1, n=10):** accuracy **0.800**, but the **weakest by macro F1 (0.514)** — and the
failure mode is the dangerous direction. Per-class: `pass` F1 0.875, `fail` **precision 1.000 but
recall 0.500**, `uncertain` 0.000. It catches only half of wrong-entity cases.

**Failure modes.** Two errors, both `fail`/`uncertain` → `pass`. `er-05` ("Advisor BankCo on
Stark-Wayne deal", gold `fail`): BankCo *advised* the deal but is linked as `company1`; the judge read
"mentioned in an M&A sentence" as "is the subject" (conf 0.66). `er-09` ("Trade group names Soylent
leader", gold `uncertain`): forced to `pass` at 0.52. The advisor-vs-principal distinction is the exact
swap this check exists to catch, and it missed it.

**Future improvements.** (1) **Highest-priority eval expansion** — `fail` recall 0.50 is the riskiest
single metric in the suite; needs ≥30 examples weighted toward advisor/intermediary/mentioned-only
negatives. (2) Add a candidate-generation/blocking step (domain/ticker match) *before* the judge so the
LLM *confirms* a subject rather than *searches* for one — the README's documented scaling fix for
entity resolution. (3) Always route this check's mid-confidence band to review given the recall risk.

---

## Part 3 — Cross-cutting findings

- **All three judges under-produce `uncertain`** (F1 0.000 across the board). For a precision-first,
  human-in-the-loop system this is the most important finding: a judge that never says "I'm not sure"
  never asks for a human. It is mitigated architecturally — the pipeline's fail-safe rollup routes
  low-confidence non-passes to review anyway — but it must be fixed at the eval/label level (every
  eval set has only one `uncertain` example today).
- **Confidence is honest even when the class is wrong.** All 5 errors across all checks landed in
  [0.40, 0.66]; all correct verdicts sit at 0.9. A confidence floor near 0.80 cleanly separates them —
  the basis for the recommended escalation thresholds in [eval-results.md](eval-results.md) §5.
- **The model split is validated by cost and risk, not preference.** Haiku handles the high-volume
  semantic and bulk-credibility work; Sonnet takes the nuanced entity check and the uncertain
  escalation band. Cheap where volume dominates, strong where errors are expensive.
- **Seed-sized eval sets are a known, stated limitation.** 10–12/check directs the judges but does not
  certify them; production needs ≥30/check with two labelers and an agreement score. This is tracked
  debt, not a hidden gap.

*The methodology behind every number here — metric definitions, version axes, the regression gate — is
in [evaluation-strategy.md](evaluation-strategy.md); the raw results are in [eval-results.md](eval-results.md).*
