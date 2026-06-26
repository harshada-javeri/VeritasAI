# Firmable Submission Audit — VeritasAI

**Auditor role:** Principal Engineer / Technical Reviewer
**Date:** 2026-06-24 · **Branch:** `main` · **HEAD:** `e1c616f` (Phase 7 complete)
**Scope:** compliance of the delivered repository against the Firmable assessment requirements

---

## Part A — GitHub Repository Requirements

### A1 — Code

#### EDA (Exploratory Data Analysis)

| | |
|---|---|
| **Status** | 🟡 Partial |
| **Evidence** | `scripts/profile_dataset.py` — a runnable dataset profiler (streaming JSON:API discovery + field statistics); `docs/data-quality-findings.md` — a detailed written EDA report (620,785 records, 29 categories, duplicate analysis, confidence distribution, conditional-field profiling). |
| **Gap** | No notebook (`.ipynb`) or interactive EDA artifact. The profiler is a CLI script; findings live in a Markdown doc. Most assessments expect a Jupyter notebook with rendered outputs, plots, and inline commentary — that artifact is absent. |
| **Recommended fix** | Convert `scripts/profile_dataset.py` into an `eda/eda_news_events.ipynb` with rendered cell outputs (bar charts of category distribution, confidence histogram, null-rate table). Re-use the numbers already documented in `docs/data-quality-findings.md`. |
| **Estimated effort** | 2–3 hours |

---

#### Rule-based checks

| | |
|---|---|
| **Status** | ✅ Complete |
| **Evidence** | `src/veritas/rules/checks.py` — 8 rules: `event_id_uuid`, `confidence_in_range`, `confidence_floor`, `category_known`, `date_sanity`, `referential_integrity`, `conditional_completeness`, `exact_duplicate`; `src/veritas/rules/engine.py`, `registry.py`, `base.py`; `tests/test_rules.py`; documented in `docs/data-quality-findings.md`. |
| **Gap** | None. |

---

#### LLM checks

| | |
|---|---|
| **Status** | ✅ Complete |
| **Evidence** | 3 checks: `semantic_accuracy` (Haiku), `source_credibility` (Haiku + Sonnet escalation), `entity_resolution` (Sonnet). Prompts in `src/veritas/prompt_registry/prompts/*.yaml`. Judges in `src/veritas/judges/`. Structured output (forced tool-use on Anthropic; `responseSchema` on Gemini). `tests/test_judges.py`, `tests/test_prompt_registry.py`. |
| **Gap** | None. |

---

#### Agentic pipeline

| | |
|---|---|
| **Status** | ✅ Complete |
| **Evidence** | `src/veritas/pipeline/` — `contracts.py`, `routing.py`, `escalation.py`, `remediation.py`, `runner.py`. Full ingest → rules → escalation → remediation → finalize → store + observe loop. `tests/test_pipeline.py`. Documented in `docs/pipeline-design.md` and `docs/phase4-pipeline-review.md`. |
| **Gap** | None. |

---

#### Eval harness

| | |
|---|---|
| **Status** | ✅ Complete |
| **Evidence** | `src/veritas/evals/` — `dataset.py`, `metrics.py`, `runner.py`, `report.py`, `cli.py`, `__main__.py`. `Makefile` target `make eval`. Labeled datasets + recorded predictions present (see A2). `tests/test_evals.py`. Documented in `docs/evaluation-strategy.md`. |
| **Gap** | None. |

---

#### Monitoring scripts

| | |
|---|---|
| **Status** | 🟡 Partial |
| **Evidence** | `src/veritas/monitoring/` — `sinks.py`, `events.py`, `logging.py`, `otel.py`, `alerts.py` — a fully-wired observability *library* with structured JSON logging, metrics sinks, and an `AlertEvaluator` for 5 alert kinds. `tests/test_monitoring.py`. Documented in `docs/observability.md`. `scripts/profile_dataset.py` for dataset-level inspection. |
| **Gap** | The monitoring package is a *library*, not a *script*. There is no standalone `scripts/monitor.py` or `scripts/run_alerts.py` that an operator runs on a schedule. Alert logic is computed (`AlertEvaluator`) but never *delivered* anywhere. `scripts/` has only `profile_dataset.py`, `dashboard_render_check.py`, and `capture_dashboard_screenshots.sh`. |
| **Recommended fix** | Add `scripts/monitor.py`: wire an `InMemoryMetricsSink` over a Postgres/SQLite snapshot, call `AlertEvaluator.evaluate()`, print or write the result. 1-page script; existing logic already handles it. |
| **Estimated effort** | 1–2 hours |

---

### A2 — Directories

#### `skills/` directory

| | |
|---|---|
| **Status** | ❌ Missing |
| **Evidence** | `find . -name "SKILL.md" -o -name "skills/"` → nothing found. The README §5 describes skills and even names the paths (`skills/news-events-quality-check/SKILL.md`, `skills/news-events-remediation/SKILL.md`), but neither directory nor files were created. |
| **Gap** | This is an explicit Firmable deliverable: a `SKILL.md` that can be loaded by any agent to run the quality-check workflow. It is the highest-visibility missing artifact in the whole submission. |
| **Recommended fix** | Create `skills/news-events-quality-check/SKILL.md` following the README §5 spec: when to trigger, inputs (event JSON + included entities), outputs (per-check JSON verdicts + overall rollup), dependencies (prompt versions, eval sets), interpretation guide (verdict precedence), and one worked example. Add the bonus `skills/news-events-remediation/SKILL.md`. |
| **Estimated effort** | 2–3 hours |

---

#### `prompts/` directory

| | |
|---|---|
| **Status** | 🟡 Partial |
| **Evidence** | Versioned prompt YAML files exist at `src/veritas/prompt_registry/prompts/semantic_accuracy.v1.yaml`, `source_credibility.v1.yaml`, `entity_resolution.v1.yaml`. Each contains `name`, `version`, `owner`, `model`, `schema`, `description`, `system`, and `template`. |
| **Gap** | Prompts live inside the source package (`src/veritas/prompt_registry/prompts/`) rather than in a top-level `prompts/` directory. The README §5 says "prompts live as files in `prompts/`" — the expected convention. While the content is correct, the location diverges from the stated design and from what a reviewer expecting to find `prompts/*.yaml` at the root would see. |
| **Recommended fix** | Either (a) create a top-level `prompts/` symlink or copy, or (b) update the README architecture section to reflect the actual `src/veritas/prompt_registry/prompts/` path. Option (b) is lower-risk; option (a) makes the repo immediately readable against the spec. |
| **Estimated effort** | 30 minutes |

---

#### `evals/` directory + versioned content

| | |
|---|---|
| **Status** | ✅ Complete |
| **Evidence** | `src/veritas/evals/datasets/` holds three dataset directories, one per check: `semantic_accuracy_v1/`, `entity_resolution_v1/`, `source_credibility_v1/`. Each has `dataset.jsonl` (labeled gold examples: `{event, label, note}`) and `predictions/` with one or more recorded prediction JSON files (semantic accuracy has both `v1.json` and `v2.json`). |
| **Gap** | Dataset sizes are seed-sized: 12 / 10 / 10 examples respectively. The README explicitly warns "≥30 hand-labelled examples per check" for production. This is a documented known gap, not a surprise. |

---

#### Versioned prompts

| | |
|---|---|
| **Status** | ✅ Complete |
| **Evidence** | All three prompts are in YAML format with explicit `name:`, `version:` (`v1`), `owner:`, `model:` (pinned, never `-latest`), `system:`, and `template:` fields. A second prompt version (`semantic_accuracy.v2`) is implied by the `v2.json` prediction file, though the prompt YAML itself is v1-only. |
| **Gap** | Minor: no `semantic_accuracy.v2.yaml` for the v2 predictions. A reviewer can infer v2 exists from the prediction file but cannot read the prompt changes. |
| **Recommended fix** | Add `semantic_accuracy.v2.yaml` or a `CHANGELOG` note in the v1 YAML recording what changed for v2. |
| **Estimated effort** | 30 minutes |

---

#### Labeled eval datasets

| | |
|---|---|
| **Status** | 🟡 Partial |
| **Evidence** | Three datasets present with correct schema (`event`, `label`, `note`). Content is real and non-trivial (genuine event examples with varied labels). |
| **Gap** | Sizes are 10–12 per check; the documented production requirement is ≥30. This is explicitly noted as a known gap (`docs/PROJECT_STATE.md` §"Known Technical Debt"). The README itself states "≥30 hand-labelled examples" as the standard. The submission as-is falls short of its own stated bar. |
| **Recommended fix** | Expand each dataset to ≥30 examples covering edge cases (truncated sentences, rare categories, ambiguous cases). |
| **Estimated effort** | 4–6 hours per check (human labeling work) |

---

#### Eval results

| | |
|---|---|
| **Status** | 🟡 Partial |
| **Evidence** | Prediction files (`predictions/v1.json`, `v2.json`) are present and contain recorded verdicts with full provenance (event_id, verdict, confidence, reason, prompt_version, model, tokens, cost, latency). Running `make eval` generates a live report. |
| **Gap** | There is no *committed, human-readable eval results artifact* — no `eval_results.md`, `eval_report.json`, or rendered report in the repo. A reviewer must run `make eval` locally to see the numbers; the metrics are not visible in the repo without tooling. The `docs/evaluation-strategy.md` explains the methodology but does not show actual scores. |
| **Recommended fix** | Run `make eval`, capture the output (precision/recall/F1 per check + worst failures), and commit it as `docs/eval-results.md`. This is the "most valuable artifact in the whole submission" per the README and it is not visible. |
| **Estimated effort** | 1 hour |

---

### A3 — Storage: DDL scripts or reproducible schema

| | |
|---|---|
| **Status** | ✅ Complete (satisfies requirement) |
| **Evidence** | `src/veritas/store/models.py` — three SQLAlchemy 2.0 ORM models: `EventCleanRow`, `QualityVerdictRow`, `TraceLogRow`, with `__tablename__`, full `Mapped[...]` column annotations, and indexes. `src/veritas/store/base.py` — `Base.metadata.create_all(engine)` call used in tests and the dashboard render check. Alembic scaffolding in `alembic/env.py`. `docs/storage-design.md` — full schema in Mermaid ER diagram plus explicit DDL-equivalent table specs. |
| **Gap** | No standalone `.sql` DDL file. Alembic is scaffolded but has no migration versions. In practice, `Base.metadata.create_all()` produces the same DDL — the ORM *is* the authoritative schema and it can reproduce DDL. This satisfies the requirement but an explicit `sql/schema.sql` (auto-generated via `Base.metadata.create_all()` + `CreateTable`) would make the schema immediately readable without a Python environment. |
| **Recommended fix** | Add `sql/schema.sql` by running `from sqlalchemy.schema import CreateTable; print(CreateTable(T))` for each model. One-liner; makes the schema self-evident. |
| **Estimated effort** | 30 minutes |

---

### A4 — README: setup, run, reproduction instructions

| | |
|---|---|
| **Status** | 🟡 Partial |
| **Evidence** | README has: `.env.example` with `DATASET_ROOT` instructions; `Makefile` with `eval / test / lint / typecheck / check`; the Phase 7 dashboard run command (`uv run streamlit run src/veritas/dashboard/app.py`); extensive design documentation. |
| **Gap** | There is **no dedicated "Getting Started" / "Setup" section** that a new reviewer can follow step-by-step: no `git clone`, no `uv sync` or `pip install` instruction, no `cp .env.example .env` instruction, no "run the pipeline against sample data" example command, no expected output. A reviewer who is not already deep in the codebase cannot immediately reproduce the pipeline from the README alone. The README's §10 "How to build" is a *design* walkthrough, not a *quickstart*. |
| **Recommended fix** | Add a `## Quickstart` section (5–8 lines) at the top of the README: `git clone`, `uv sync`, `cp .env.example .env` + DATASET_ROOT note, `make check` to verify gates, `make eval` for the harness, `uv run streamlit run ...` for the dashboard. |
| **Estimated effort** | 30 minutes |

---

## Part B — Notion Deliverable Requirements

### B1 — Part 1: Solution summary and architecture overview

| | |
|---|---|
| **Status** | ✅ Complete |
| **Evidence** | `README.md` §1 (TL;DR), the newly added `# Architecture Overview` and `# Design Principles` sections; `docs/EXECUTIVE_OVERVIEW.md` (full five-minute overview); `docs/architecture-review.md` (C4 diagrams, sequence diagrams, data contracts, deployment topology). |
| **Gap** | None — this is arguably the best-covered section of the submission. |

---

#### Rule-vs-LLM split decision and rationale

| | |
|---|---|
| **Status** | ✅ Complete |
| **Evidence** | `README.md` §3 ("Rules first, LLM where rules fail") — explicit split table with rationale per check. `docs/data-quality-findings.md` — empirical numbers that *justify* each rule. `docs/phase2-llm-architecture.md` — the LLM-side rationale. `docs/EXECUTIVE_OVERVIEW.md` §"Why Existing Solutions Fail". |
| **Gap** | None. |

---

### B2 — Part 2: Per-check writeup (prompt, rubric, eval results, model choice)

| | |
|---|---|
| **Status** | 🟡 Partial |
| **Evidence** | **Prompts:** All three prompt YAMLs contain `system` (rubric), `template`, `model`, and `description`. **Model choice rationale:** `README.md` §4 and `docs/phase2-llm-architecture.md` §4 explain Haiku vs. Sonnet selection per check. **Eval framework:** `docs/evaluation-strategy.md` describes methodology. **Predictions:** recorded in `predictions/*.json`. |
| **Gap** | **No consolidated per-check writeup document.** The information is scattered across the prompt YAML, the phase-2 architecture doc, and the evaluation-strategy doc. A Notion reviewer expecting "one section per check with prompt, rubric, eval numbers, and model choice in one place" must assemble it from multiple files. Critically: **no committed eval metrics output** (precision, recall, F1) is visible anywhere in the repo without running `make eval`. The "why it matters" failure analysis ("here are the 5 worst misclassifications and why") is described as methodology but never shown as an artifact. |
| **Recommended fix** | Create `docs/checks-writeup.md` with one section per check: (1) what it tests and why LLM not rules, (2) prompt (verbatim), (3) rubric, (4) model choice and rationale, (5) eval results (actual P/R/F1 numbers from `make eval`), (6) worst failures with analysis. |
| **Estimated effort** | 3–4 hours |

---

### B3 — Part 3: Skill design and example invocation

| | |
|---|---|
| **Status** | ❌ Missing |
| **Evidence** | `skills/` directory does not exist. `SKILL.md` does not exist. `README.md` §5 describes the skill design intent in detail (when to trigger, inputs, outputs, dependencies, interpretation, worked example) but the actual deliverable files are absent. |
| **Gap** | This is the most concrete, Firmable-specific requirement gap. A "skill" in Firmable's assessment framing is a runnable, portable specification that any agent can load — and it is explicitly called for in the README's own design section. Its absence is immediately visible. |
| **Recommended fix** | See A2 `skills/` above. Create `skills/news-events-quality-check/SKILL.md` based exactly on the README §5 spec. It needs no code — only the Markdown spec with a worked JSON example. |
| **Estimated effort** | 2–3 hours |

---

### B4 — Part 4: Agentic pipeline walkthrough

| | |
|---|---|
| **Status** | ✅ Complete |
| **Evidence** | `docs/pipeline-design.md` — full implementation walkthrough (routing decisions, escalation logic, finalize rollup, budget integration, failure handling). `docs/phase4-pipeline-review.md` — design-review companion. `README.md` §6 — the agentic pipeline loop in pseudocode. `docs/DEMO_SCRIPT.md` — a presenter walkthrough of the pipeline end-to-end. |
| **Gap** | None for written documentation. The gap relative to the original README vision is that there is no notebook or Loom-style demonstration of the pipeline running. "Optional ≤5-min Loom" was scoped optional in the README. |

---

### B5 — Part 5: Eval, tracing, and failure analysis findings

| | |
|---|---|
| **Status** | 🟡 Partial |
| **Evidence** | `docs/evaluation-strategy.md` — full methodology (metrics, dataset versioning, regression gate, worst-failure dump, the "uncertain class scores 0" observation). `src/veritas/evals/datasets/*/predictions/` — recorded predictions. `src/veritas/store/models.py` — `trace_logs` schema. `docs/storage-design.md` — trace-log design. |
| **Gap** | **No committed failure-analysis artifact.** The evaluation-strategy doc describes *how* to read failures, and the worst-failures methodology is built into the CLI — but no output artifact (a table of actual misclassified examples with "why it was wrong" notes) is committed to the repo. The README explicitly says "that failure note is the most valuable artifact in the whole submission" — and it is missing. |
| **Recommended fix** | Run `make eval`, capture worst failures, write 2–3 sentences per failure explaining the likely root cause (ambiguous label, truncated sentence, rare category). Commit as part of `docs/eval-results.md` or `docs/checks-writeup.md`. |
| **Estimated effort** | 1–2 hours |

---

### B6 — Part 6: Monitoring plan and cost math

| | |
|---|---|
| **Status** | ✅ Complete |
| **Evidence** | `docs/observability.md` — full monitoring catalog (metrics, sinks, alert kinds, OTel adapter). `README.md` §8 — explicit cost math table (Haiku/Sonnet pricing, full-backfill estimate, ongoing per-day estimate). `src/veritas/llm_gateway/pricing.py` — pinned prices in code. `src/veritas/llm_gateway/budget.py` — `BudgetGuard` implementation. `docs/PRODUCTION_READINESS_REVIEW.md` §6 — cost driver ranking. |
| **Gap** | Minor: the Gemini pricing in `pricing.py` is flagged "illustrative — verify before use." Alert *delivery* is unimplemented (computed but routed nowhere). Both are documented honestly. |

---

### B7 — Part 7: Dashboard screenshots and example insights

| | |
|---|---|
| **Status** | 🟡 Partial |
| **Evidence** | `src/veritas/dashboard/` — a complete 7-workspace Streamlit Decision Intelligence Console. `scripts/dashboard_render_check.py` — headless verification (all 7 workspaces render clean via `AppTest`). `scripts/capture_dashboard_screenshots.sh` — Playwright-based screenshot capture script. `docs/DEMO_SCRIPT.md` §7 — describes each workspace and what it shows. |
| **Gap** | **No actual PNG screenshots are committed to the repo.** The capture script is provided but requires Playwright/Chromium. A reviewer opening the repository sees no visual evidence of the dashboard without running it locally. Screenshots are the most immediately impactful presentation artifact and they are absent. |
| **Recommended fix** | Run `scripts/capture_dashboard_screenshots.sh` locally (or run `uv run playwright install chromium && bash scripts/capture_dashboard_screenshots.sh`) and commit the resulting `screenshots/01-trust-center.png` through `07-event-detail.png`. Add `![Trust Center](screenshots/01-trust-center.png)` inline in the `# Dashboard` section of the README. |
| **Estimated effort** | 1 hour |

---

### B8 — Part 8: "How you build" reflection

| | |
|---|---|
| **Status** | ❌ Missing |
| **Evidence** | No dedicated reflection document exists. `docs/PROJECT_STATE.md` has engineering notes and known trade-offs. `docs/PRODUCTION_READINESS_REVIEW.md` §13 ("What Would Impress a Hiring Manager") comes closest. `docs/STAKEHOLDER_FEEDBACK_INTEGRATION.md` and `docs/WEEKEND_SUBMISSION_NOTE.md` describe process. |
| **Gap** | No document explicitly addresses: what tools were used (Claude Code, ChatGPT, Cursor, other IDEs), how the agentic tools contributed vs. human judgment, what was hard, what you would do differently, what this build taught you. This is a high-signal deliverable for Firmable specifically — it tests self-awareness and engineering philosophy, not just code. |
| **Recommended fix** | Create `docs/HOW_I_BUILT_THIS.md` covering: (1) tooling used and how, (2) what the multi-phase build process looked like, (3) the one most important design decision and why, (4) what you would do differently, (5) what surprised you about the data. 400–600 words, first-person, honest. |
| **Estimated effort** | 1–2 hours |

---

### B9 — Tools Used documentation

| | |
|---|---|
| **Status** | ❌ Missing |
| **Evidence** | No document inventories the tools used during the build. The README does not mention Claude Code, ChatGPT, Cursor, or any agentic tools by name. |
| **Gap** | Firmable explicitly asks for documentation of which AI/agentic tools were used. This transparency is part of the assessment — they are evaluating the candidate's ability to use AI tools productively and reflectively, not penalizing it. The absence of this section reads as an oversight, not discretion. |
| **Recommended fix** | Include a "Tools used" section in `docs/HOW_I_BUILT_THIS.md` (above). List: Claude Code (architecture + implementation), specific IDE, any ChatGPT or Cursor usage, and 1–2 sentences on how each was used and what value it added vs. where human judgment was essential. |
| **Estimated effort** | Covered by B8 above — 30 minutes extra |

---

## Submission Readiness Score

| Category | Weight | Score | Weighted |
|---|---|---|---|
| Code completeness (EDA, rules, LLM, pipeline, evals, monitoring) | 20% | 80 | 16 |
| Directory structure (`skills/`, `prompts/`, `evals/`) | 15% | 55 | 8 |
| Eval artifacts (labeled data, predictions, committed results) | 15% | 55 | 8 |
| Storage (schema reproducible, DDL readable) | 10% | 85 | 9 |
| README (architecture, setup, run, reproduction) | 10% | 65 | 7 |
| Notion deliverables (Parts 1–8) | 25% | 60 | 15 |
| Tools reflection | 5% | 0 | 0 |
| **Total** | **100%** | | **63 / 100** |

> The score reflects genuine engineering depth (the code, architecture, pipeline, storage, monitoring,
> and dashboard are all high quality) against the missing *presentation* and *deliverable* artifacts
> that Firmable explicitly requires. The gap is not engineering skill — it is assembly.

---

## Top 10 Missing Items (ranked by visibility and assessment impact)

| # | Item | Impact | Effort |
|---|---|---|---|
| 1 | **`skills/` directory + `SKILL.md`** — the most explicit named deliverable in the README's own design spec. Its absence is immediately visible to any reviewer who reads §5. | Very high | 2–3 hrs |
| 2 | **Dashboard screenshots committed to the repo** — a visual artifact that communicates the full Phase 7 build in 7 images. Currently requires running the app locally to see anything. | Very high | 1 hr |
| 3 | **`docs/HOW_I_BUILT_THIS.md` + tools used** — the "Part 8 reflection" requirement. High signal for Firmable specifically; absence reads as an oversight. | High | 1–2 hrs |
| 4 | **Committed eval results** (`docs/eval-results.md`) — actual P/R/F1 numbers and worst-failure analysis. The README calls this "the most valuable artifact in the whole submission" and it is not visible without running `make eval`. | High | 1 hr |
| 5 | **README Quickstart section** — 5–8 lines for a new reviewer to clone, install, verify, and run. Currently absent despite `.env.example` and Makefile existing. | High | 30 min |
| 6 | **`docs/checks-writeup.md`** — consolidated per-check document (prompt + rubric + eval numbers + model rationale + failure analysis) in one place, as Notion Part 2 requires. | Medium-high | 3–4 hrs |
| 7 | **EDA notebook** — an `eda/eda_news_events.ipynb` with rendered outputs and plots. The `data-quality-findings.md` content exists; it needs a visual notebook home. | Medium | 2–3 hrs |
| 8 | **`sql/schema.sql`** — an explicit, human-readable DDL file. The ORM covers this functionally but the file makes the schema scannable without a Python environment. | Medium | 30 min |
| 9 | **`monitoring/` standalone script** — a `scripts/monitor.py` that an operator runs to evaluate alerts against a live DB snapshot, making "monitoring" a script not just a library. | Medium | 1–2 hrs |
| 10 | **Eval dataset expansion** — grow each labeled dataset to ≥30 examples (from 10–12 today), meeting the standard the README itself sets. Requires human labeling time. | Medium | 4–6 hrs each |

---

## Fastest Path to 100% Compliance

The engineering is done. The gap is entirely in **presentation and documentation** artifacts.
Estimated total: **one focused day (6–8 hours).**

### Hour 1 — Quick wins (zero code, immediate visibility)
1. Add `## Quickstart` to README (30 min).
2. Add `sql/schema.sql` (30 min).

### Hours 2–3 — Skills (highest-priority named deliverable)
3. Create `skills/news-events-quality-check/SKILL.md` per README §5 spec.
4. Create `skills/news-events-remediation/SKILL.md`.

### Hour 4 — Eval results + failure analysis (the "most valuable artifact")
5. Run `make eval`. Capture output.
6. Create `docs/eval-results.md` with P/R/F1 per check + 5 worst failures per check with root-cause notes.

### Hours 5–6 — Checks writeup + screenshots
7. Create `docs/checks-writeup.md` consolidating prompt / rubric / eval numbers / model rationale per check (draw from prompt YAMLs + phase2 doc + eval-results).
8. Run `scripts/capture_dashboard_screenshots.sh` (install Playwright if needed) → commit 7 PNGs → add to README.

### Hour 7 — Reflection + tools (high-signal for Firmable)
9. Write `docs/HOW_I_BUILT_THIS.md` — how it was built, tools used, what was hard, what you'd change.

### Hour 8 — EDA notebook
10. Convert `scripts/profile_dataset.py` findings into `eda/eda_news_events.ipynb`. Use the numbers from `docs/data-quality-findings.md`. Add a distribution chart, confidence histogram, and category table.

**Optional (lower priority):** add `scripts/monitor.py`; expand eval datasets to ≥30 examples; add `semantic_accuracy.v2.yaml`; clarify prompts path in README.

After these steps, the repository's engineering quality and its presentation will be commensurate —
every section a Firmable reviewer opens will have a visible, readable artifact to match the
code behind it.
