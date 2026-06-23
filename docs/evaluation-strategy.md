# VeritasAI — Evaluation Strategy

*How we measure a judge before we trust it. Reviewer-facing.*
*Date: 2026-06-23.*

The principle from the README: **measure the judge before you trust it.** A judge
that isn't measured is a loose prompt. This framework turns each LLM check into a
*measured, versioned, regression-gated* component — and it does so **without ever
calling a live model**, so evaluations are reproducible, deterministic, and free.

Run it: `make eval` (→ `python -m veritas.evals`).

---

## 1. Two independent version axes

| Axis | Example | What it pins | Changes when… |
|---|---|---|---|
| **Dataset version** | `semantic_accuracy_v1` | the labeled ground-truth set | you add/relabel examples |
| **Prompt version** | `v1`, `v2` | which recorded predictions you score | you edit the prompt |

They are orthogonal: **hold the dataset fixed and vary the prompt** to compare versions
or detect drift. A dataset directory holds the gold labels plus one recorded prediction
set per prompt version:

```
src/veritas/evals/datasets/semantic_accuracy_v1/
  dataset.jsonl              # gold: {event, label, note} per line
  predictions/
    v1.json                  # recorded Verdicts from prompt v1
    v2.json                  # recorded Verdicts from prompt v2
```

Predictions are replayed through `ReplayJudge` — **no API key, no network, no spend.**
This is the same `ReplayJudge` the pipeline will use, so what we measure is exactly what
runs.

## 2. Metrics

Labels are three classes — `pass` / `fail` / `uncertain` — so the binary metrics are
computed **one-vs-rest per class** and **macro-averaged**:

- For class *c*: `precision = TP / (TP+FP)`, `recall = TP / (TP+FN)`, `F1 = 2PR/(P+R)`.
- **Macro** = the mean of each metric over the classes that **appear in the gold labels**.
  An absent class (support 0) is excluded so it can't drag the average to zero.
- **Accuracy** = exact-match fraction over all examples.
- **Zero-division → 0.0** by convention (e.g. a class the model never predicts).

The CLI prints the macro headline *and* the per-class breakdown, because the per-class
view is where a judge's weakness shows — e.g. in the shipped seed data the `uncertain`
class scores 0 (the recorded judge never confidently picks it), which is exactly the kind
of blind spot the README warns about and the per-class table surfaces.

Why macro (not "fail" as a single positive class)? Data quality cares about *both* catching
bad records (`fail` recall) and not over-flagging good ones (`fail` precision), and
`uncertain` is a real routing outcome. Macro keeps all three honest in one number while the
per-class rows preserve the detail.

## 3. Worst failures

Every prediction that disagrees with gold is collected and **sorted by the judge's own
confidence, descending** — the most *confident mistakes* are the most important to read,
because they're where the judge is reliably wrong rather than appropriately unsure. Each
line shows the event, gold vs predicted, confidence, and the judge's stated reason, so the
reviewer can write down *why* (truncated text? genuinely ambiguous? rare category?) — the
single most valuable artifact per the README.

## 4. Regression detection

Comparing two prompt versions yields a regression report over the **tracked metrics**
(`accuracy`, `macro_precision`, `macro_recall`, `macro_f1`). For each:

```
drop = baseline_metric - candidate_metric
regressed if  drop > threshold     (threshold from config: evals.regression_threshold, default 0.05)
```

If **any** tracked metric regresses, `make eval` prints `EVAL FAILED` and **exits non-zero** —
so it drops straight into CI as a gate that blocks a prompt change that quietly makes a judge
worse. (A negative drop = improvement and is reported as a positive delta.)

This is also the **model-drift canary**: pin the model, freeze the labeled set, and run the
same eval on a schedule. If metrics move without a prompt change, the model changed underneath
you.

## 5. `make eval` output anatomy

For each dataset:
- a **comparison block** when ≥2 prompt versions exist (or `--compare`): baseline vs candidate
  headline + regression report;
- a **result block**: macro + per-class metrics and the worst failures.

Useful flags: `--dataset NAME` (repeatable), `--prompt-version V` (score one version),
`--baseline V --candidate V` (explicit comparison), `--threshold F`, `--top N`, `--json PATH`.

## 6. Honest limitations

- **Seed-sized sets.** The shipped sets are ~10–12 examples per check — enough to exercise the
  metrics and *direct* a judge, **not** to certify one. Production needs ≥30 per check (README
  §11), ideally two labelers with an agreement score.
- **`uncertain` is thin.** One example per set; its per-class metrics are noisy by construction.
  Rare/ambiguous categories should be deliberately oversampled into the labeled set.
- **Predictions are recorded, not live.** That's the point (reproducibility, $0), but it means a
  prediction set must be regenerated when a prompt genuinely changes — the recording is the
  contract being tested, captured once from a real run.
- **Macro over present classes** is a deliberate choice; switch to a fixed positive class if a
  specific check cares only about catching `fail`.
