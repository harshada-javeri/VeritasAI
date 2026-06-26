# VeritasAI — Evaluation Results

*An engineering review of judge quality, not a benchmark table. What the judges get right,*
*where they fail, why, and what thresholds the failures imply.*
*Generated from `make eval` (replay-backed, deterministic, zero spend) · HEAD `e1c616f` · 2026-06-24.*

> **Reproduce:** `make eval` (= `uv run python -m veritas.evals`). Every number below is copied
> verbatim from that command's output. The harness scores recorded predictions through `ReplayJudge`,
> so results are identical on any machine with no API key and no network.

---

## 1. Headline

| Check | Model | n | Accuracy | Macro P | Macro R | Macro F1 |
|---|---|---:|---:|---:|---:|---:|
| **semantic_accuracy** (v2) | Haiku | 12 | **0.917** | 0.600 | 0.667 | **0.630** |
| **entity_resolution** (v1) | Sonnet | 10 | 0.800 | 0.593 | 0.500 | 0.514 |
| **source_credibility** (v1) | Haiku→Sonnet | 10 | 0.800 | 0.571 | 0.583 | 0.563 |

**Read this correctly.** These are **seed-sized** label sets (10–12 examples/check). They are large
enough to *direct* the judges — to find blind spots and set thresholds — and far too small to
*certify* them. The README sets the production bar at ≥30/check with two labelers; we are below it
deliberately and say so. Treat the macro F1 figures as directional, and the **per-class and
failure-mode findings below as the real signal** — they hold regardless of n.

The single most important pattern is visible in every check at once: **the `uncertain` class scores
F1 = 0.000 across all three.** That is not three coincidences; it is one systematic finding (§4).

---

## 2. Per-class breakdown

Labels are three classes (`pass` / `fail` / `uncertain`); metrics are one-vs-rest, macro-averaged
over classes present in the gold set. The per-class view is where a judge's weakness actually shows.

### semantic_accuracy @ v2 (acc 0.917, n=12)
| Class | P | R | F1 | support |
|---|---:|---:|---:|---:|
| pass | 1.000 | 1.000 | 1.000 | 7 |
| fail | 0.800 | 1.000 | 0.889 | 4 |
| uncertain | 0.000 | 0.000 | 0.000 | 1 |

Strong on the decisive classes — perfect on `pass`, perfect recall on `fail`. The only `fail`
imprecision (P=0.80) and the entire macro gap come from the single `uncertain` example it misread.

### entity_resolution @ v1 (acc 0.800, n=10)
| Class | P | R | F1 | support |
|---|---:|---:|---:|---:|
| pass | 0.778 | 1.000 | 0.875 | 7 |
| fail | 1.000 | 0.500 | 0.667 | 2 |
| uncertain | 0.000 | 0.000 | 0.000 | 1 |

The weakest judge by F1 — and the failure mode is the dangerous direction: **`fail` recall = 0.50.**
It catches only half the wrong-entity cases, and when it misses it says `pass` (§3). For a check whose
whole job is catching the law-firm-vs-defendant swap, missed `fail`s are the costly error.

### source_credibility @ v1 (acc 0.800, n=10)
| Class | P | R | F1 | support |
|---|---:|---:|---:|---:|
| pass | 0.714 | 1.000 | 0.833 | 5 |
| fail | 1.000 | 0.750 | 0.857 | 4 |
| uncertain | 0.000 | 0.000 | 0.000 | 1 |

Balanced. `fail` precision is perfect (every "this is PR/reprint" call was correct); `fail` recall
0.75 means one promotional source slipped through as `pass` (§3). `pass` precision 0.714 is the cost
of that miss plus the uncertain misread.

---

## 3. Worst failures — root-cause analysis

The harness dumps every misclassification with the input that produced it. There are **5 total**
across all three checks. Each is analyzed for *why*, because the why is what tells you whether to fix
the data, the prompt, or the threshold.

| # | Check | Event | Gold | Pred | Conf | The input | Root cause |
|---|---|---|---|---|---:|---|---|
| 1 | entity_resolution | `er-05` | fail | pass | 0.66 | "Advisor BankCo on Stark-Wayne deal" → BankCo is `company1` | **Advisor-vs-principal confusion.** BankCo *advised* the deal; it is not the acquirer. The judge treated "mentioned in an M&A sentence" as "is the subject." This is the exact entity-swap class the check exists to catch — and it missed it at moderate confidence. |
| 2 | entity_resolution | `er-09` | uncertain | pass | 0.52 | "Trade group names Soylent leader" → Soylent named | **Ambiguous subject read as clear.** Whether Soylent is the event subject or just named is genuinely unclear; the gold label is `uncertain`. The judge forced a `pass` at barely-above-coinflip confidence (0.52). |
| 3 | semantic_accuracy | `sa-12` | uncertain | fail | 0.40 | "Report mentions Acme in passing" (category: launches) | **Insufficient-evidence read as a defect.** There isn't enough text to confirm *or* deny a launch — gold is `uncertain`. The judge over-committed to `fail`, but at low confidence (0.40), which is the saving grace (§4). |
| 4 | source_credibility | `sc-06` | fail | pass | 0.61 | "Company blog: We welcome our new CTO" | **Company-authored content read as news.** A company blog post is first-party PR, not independent reporting — gold is `fail`. The judge accepted it as genuine at moderate confidence. |
| 5 | source_credibility | `sc-10` | uncertain | pass | 0.49 | "Unclear blogspot post on Foo-Bar" | **Low-signal source forced to a verdict.** A vague blogspot post has too little signal to credit — gold is `uncertain`. The judge guessed `pass` at sub-0.5 confidence. |

**The pattern across all five:** four of the five errors are the judge **collapsing a genuinely-hard
case into a confident-enough class instead of saying `uncertain`** (#2, #3, #5 are uncertain→something;
#1, #4 are confident misreads of subtle distinctions). The judges are good at clear cases and
systematically over-decisive on ambiguous ones.

---

## 4. The `uncertain` blind spot (the load-bearing finding)

`uncertain` scores **F1 = 0.000 in all three checks.** Every check has exactly one `uncertain` gold
example, and **no check ever correctly produces `uncertain`** — the recorded judges always pick `pass`
or `fail` instead.

This matters more than any macro number, because `uncertain` is not a nuisance class — **it is the
routing signal that sends an event to a human.** A judge that never says `uncertain` is a judge that
never *asks for help*, which is precisely the behavior a precision-first, human-in-the-loop system
must not have. The errors confirm it: the misread `uncertain` cases (#2, #3, #5) were forced into a
confident class instead of being escalated to review.

Two non-obvious mitigations fall out of the data, and both are *already in the architecture* rather
than requiring a model fix:

1. **The confidence values are honest even when the class is wrong.** The forced-decision errors
   landed at 0.52, 0.40, 0.49, 0.61, 0.66 — clustered right where a calibrated judge *should* be
   unsure. The model "knows" it is guessing; it just isn't allowed to express it as a class. A
   **confidence-band → review** rule recovers most of these without touching the prompt (§5).
2. **The pipeline's fail-safe rollup already routes low-confidence non-passes to review.** Precedence
   rule 5 (any LLM non-`pass`, or a `fail` below the high-confidence bar) → REVIEW. So even a judge
   that under-produces `uncertain` is backstopped by the routing layer — the system fails toward a
   human, not toward a silent pass.

The labeling action item is also clear: with one `uncertain` example per check, this class is
**unmeasurable**. Expanding the eval sets must prioritize `uncertain` examples specifically.

---

## 5. Confidence calibration & recommended escalation thresholds

Reading the confidence of the *wrong* answers against the confidence of the *right* ones gives a
practical operating point, even at this n.

- **Correct `pass`/`fail` verdicts** in the recorded sets sit at **0.9** (e.g. `sa-01` pass @ 0.9).
- **Every one of the 5 errors** sits in **[0.40, 0.66]** — the judges are not confidently wrong; they
  are *unconfidently wrong*. There are no high-confidence errors in the data.

This is the most useful calibration result available: **a confidence floor cleanly separates the
errors from the correct decisions here.** Recommended thresholds, consistent with the pipeline's
existing `llm_fail_min_confidence`:

| Band | Verdict confidence | Action | Why |
|---|---|---|---|
| **High** | ≥ 0.80 | Honor the verdict (auto-pass / auto-quarantine on `fail`) | All correct verdicts live here; no errors observed in this band. |
| **Mid** | 0.50 – 0.80 | Route to **review** regardless of class | Captures errors #1 (0.66), #4 (0.61), #2 (0.52). The judge is deciding on signal it isn't sure of. |
| **Low** | < 0.50 | Route to **review** (and prefer `uncertain` semantics) | Captures errors #3 (0.40), #5 (0.49). At sub-coinflip confidence, a class label is noise. |

A floor at **0.80 for auto-actioning** and **review below it** would have caught **all 5 errors** in
this dataset, at the cost of reviewing some correct mid-confidence verdicts — the right trade for a
precision-first system where a missed defect is far more expensive than an extra review. This is a
*recommendation to validate at ≥30 examples*, not a tuned production constant; the n is too small to
fix the exact number, but the *shape* (errors live below 0.7, correct verdicts at 0.9) is unambiguous.

---

## 6. Prompt comparison & regression gate (semantic_accuracy v1 → v2)

The harness compares two prompt versions on the *same* frozen gold set and gates promotion on
regression. Actual output:

| Metric | v1 (baseline) | v2 (candidate) | Δ | Threshold | Verdict |
|---|---:|---:|---:|---:|---|
| accuracy | 0.833 | 0.917 | **+0.083** | 0.050 | improved |
| macro_precision | 0.593 | 0.600 | +0.007 | 0.050 | flat |
| macro_recall | 0.583 | 0.667 | **+0.083** | 0.050 | improved |
| macro_f1 | 0.577 | 0.630 | **+0.052** | 0.050 | improved |

**Gate result: `OK` — safe to promote.** No tracked metric regressed beyond the 0.05 threshold; three
of four improved, the fourth held. v2's gain came from fixing `fail` recall (it now catches all four
mislabeled-category cases) without sacrificing `pass` precision (still 1.000). This is exactly the
promote/rollback decision the gate exists to make — and it is the mechanism that lets a prompt evolve
without silently getting worse. (`make eval` exits non-zero if any metric had dropped past threshold,
so this gate runs in CI, not just by eye.)

---

## 7. What these results justify

1. **Promote `semantic_accuracy` v2.** The gate is green and the improvement is real and balanced.
2. **Adopt a confidence-floor → review rule** at ~0.80 for auto-actioning. The data shows a clean
   separation; the routing layer already supports it (`llm_fail_min_confidence`).
3. **Treat `entity_resolution` as the highest-risk judge.** Its `fail` recall (0.50) means it misses
   half of wrong-entity cases — and the entity-swap error (`er-05`) is a costly downstream defect.
   Prioritize its eval expansion and consider always-escalating its `uncertain`/mid-confidence band to
   Sonnet (it already runs on Sonnet, so the next lever is a candidate-generation/blocking step before
   the judge, per the README's known weakness on entity resolution at scale).
4. **Expand every eval set to ≥30, front-loading `uncertain` examples.** The `uncertain` class is
   currently unmeasurable (n=1 each) and is the most important class for a human-in-the-loop system.
5. **Keep the regression gate in CI.** It already caught nothing-bad here (v2 is clean), which is the
   point — it is the guardrail that makes prompt iteration safe.

---

*All figures reproducible via `make eval`. Methodology — metric definitions, the two independent
version axes, and why macro-averaging — is documented in [evaluation-strategy.md](evaluation-strategy.md).*
