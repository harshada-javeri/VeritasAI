# VeritasAI — Project State

*Single source of truth for resuming development in a fresh Claude Code session.*
*Last updated: 2026-06-23 · HEAD: `ba0fa30` · Branch: `main` (pushed to origin).*

---

## Repository Overview

### Purpose

An **AI-native data quality platform** for a news-events intelligence feed. It validates
~620K JSON:API news-event records using a layered strategy:

> **Rules gate. LLMs judge. Humans backstop. Everything is logged, versioned, and measured.**

Deterministic rules do the cheap, exact work on 100% of records; LLM judges do the semantic
work only on what rules can't settle; a budget-throttled pipeline ties it together; everything
is evaluated, persisted, and observable.

### Architecture

Layered, each layer depending only on lower ones (DI throughout; every boundary strongly typed):

```
ingest → rules (gate) → pipeline (routing → escalation → remediation → finalize)
                              │            │
                          judges ── llm_gateway (pin/route/retry/cost/budget)
                              │            │
                       prompt_registry   monitoring (metrics/logging/alerts)
                              │
                            store (SQLAlchemy)        evals (replay-backed)
```

- **Deliverable mode:** assessment-grade but production-shaped (interfaces, config, DI, strict
  typing) so it promotes without a rewrite.
- **Stack:** Python 3.12, Pydantic v2, SQLAlchemy 2.0 (async), `uv`, MyPy strict, Ruff.
- **LLM access:** vendor-agnostic; develop/test against `ReplayJudge` (no live calls).

### Major design decisions

- **Single `Verdict` currency** for both rules and LLM judges → uniform storage/routing/trace.
- **Tolerant parser, validating rules:** the parser never rejects content problems; rules flag them.
- **Pinned model IDs** (never `*-latest`); structured output only (no prose parsing).
- **Optional, no-op-by-default seams** for storage and monitoring → the pipeline is independent
  of both and stays runnable in-memory.
- **Replay-everywhere:** evals and pipeline tests run offline and deterministically.

---

## Current Status — all phases 0–6 complete, committed, pushed

### Phase 0 — Ingestion & profiling foundation · `ad77442`
- **Deliverables:** `config.py` (env-driven settings, `DATASET_ROOT`→`./datasets` fallback,
  pinned models, thresholds, budget); `domain/models.py` (`ResolvedEvent`, `Verdict`, `Company`,
  `Article`, `ParseError`); `ingest/` (configurable recursive discovery + tolerant streaming
  JSON:API parser); `scripts/profile_dataset.py`.
- **Decisions:** streaming line-by-line (never load 2.3 GB); structural errors → `ParseError`,
  content issues preserved for rules; dataset git-ignored.

### Phase 1 — Deterministic rules engine · `5a80b09`
- **Deliverables:** `rules/` (8 rules: `event_id_uuid`, `confidence_in_range`,
  `confidence_floor`, `category_known`, `date_sanity`, `referential_integrity`,
  `conditional_completeness`, `exact_duplicate`); `RuleRegistry`/`RuleEngine`/`RuleReport`;
  rule metrics hook; `docs/data-quality-findings.md`.
- **Decisions:** rollup precedence (any FAIL→quarantine, any UNCERTAIN→review, else clean);
  rules pure + `now` injected; per-category conditional-completeness severity map.

### Phase 2 — LLM gateway, prompt registry, judges · `cc7da04`
- **Deliverables:** `llm_gateway/` (errors, types, pricing, budget, retry, providers, gateway);
  `prompt_registry/` (YAML specs + 3 prompts); `judges/` (`LLMJudge` Protocol, `JudgeOutput`,
  `BaseLLMJudge`, `AnthropicJudge`, `GeminiJudge`, `ReplayJudge`); `docs/phase2-llm-architecture.md`.
- **Decisions:** vendor specifics isolated in provider clients behind a `Transport` Protocol;
  hand-written flat JSON schema (Gemini rejects `$ref`/`additionalProperties`); confirmed
  Anthropic pricing; async tests via `asyncio.run` (no pytest-asyncio).

### Phase 3 — Evaluation framework · `f59c4dd`
- **Deliverables:** `evals/` (datasets, metrics, runner, report, CLI `make eval`); 3 labeled
  datasets with recorded predictions; `docs/evaluation-strategy.md`.
- **Decisions:** dataset version ⟂ prompt version; macro-averaged P/R/F1 over present classes +
  accuracy; regression = any tracked metric drop > threshold → non-zero exit; **ReplayJudge only**.
- **Caught a packaging bug:** the Phase-0 `datasets/` ignore matched the packaged eval fixtures;
  fixed to anchored `/datasets/` + a `!src/veritas/evals/datasets/**` negation.

### Phase 4 — Pipeline orchestration & escalation · `9492fb4`
- **Deliverables:** `pipeline/` (`contracts.py`, `routing.py`, `escalation.py`, `remediation.py`,
  `runner.py`); `docs/pipeline-design.md` + `docs/phase4-pipeline-review.md`.
- **Decisions:** FAIL→quarantine (no spend), REVIEW→escalate, CLEAN→deterministic 20% sample;
  escalate **only the uncertain check** (Haiku→Sonnet); remediation **proposal-only**; bounded
  async windowed pool + shared `BudgetGuard`, no scheduler; rule-REVIEW persists even when LLM passes.

### Phase 5 — Storage layer · `d7f276a`
- **Deliverables:** `store/` (`base`, `models`, `database`, `repositories`, `sinks`); Alembic
  scaffolding (no migration workflow); `docs/storage-design.md`.
- **Decisions:** async SQLAlchemy 2.0, SQLite default, Postgres = URL change; idempotency key
  `(event_id, check_name, prompt_version, model)` with **`""` not NULL** for rule keys; portable
  select-then-upsert; `events_clean` upsert, `trace_logs` append-only; needs `sqlalchemy[asyncio]`
  (greenlet); two Phase-4 contracts changed (async `on_outcome`, `EventOutcome.snapshot`).

### Phase 6 — Monitoring & observability · `ba0fa30`
- **Deliverables:** `monitoring/` (`events`, `sinks`, `logging`, `otel`, `alerts`);
  `docs/observability.md`.
- **Decisions:** `MetricsSink` (+Null/InMemory) and `MetricsRuleSink` adapter; `PipelineLogger`
  (JSON only); `OpenTelemetryMetricsSink` (optional, lazy importlib, graceful fallback);
  `AlertEvaluator` for 5 alert kinds; monitoring depends only on `domain`+`rules.metrics` to
  avoid cycles; all integrations are additive optional kwargs (no contract change).

*(Also `dc680bf` — chore: ignore `.DS_Store`.)*

---

## Current Metrics

| Gate | Status |
|---|---|
| Tests | **130 passed** |
| MyPy | **strict — clean (67 source files)** |
| Ruff | **clean** |

Commands: `uv run pytest`, `uv run mypy`, `uv run ruff check .`, `make eval`.

---

## Repository Structure

```
veritas-ai/
├─ src/veritas/
│  ├─ config.py                # pydantic-settings: models, thresholds, budget, eval, pipeline
│  ├─ domain/models.py         # ResolvedEvent, Verdict, Company, Article, ParseError, enums
│  ├─ ingest/                  # discovery.py, parser.py (tolerant streaming JSON:API)
│  ├─ rules/                   # base, checks (8 rules), engine, registry, metrics
│  ├─ llm_gateway/             # errors, types, pricing, budget, retry, providers, gateway
│  ├─ prompt_registry/         # spec, registry, prompts/*.yaml (3 checks)
│  ├─ judges/                  # protocol, schema, base, anthropic, gemini, replay
│  ├─ evals/                   # dataset, metrics, runner, report, cli + datasets/*
│  ├─ pipeline/                # contracts, routing, escalation, remediation, runner
│  ├─ store/                   # base, models, database, repositories, sinks
│  └─ monitoring/              # events, sinks, logging, otel, alerts
├─ tests/                      # 10 test modules (one per package) + fixtures/
├─ docs/                       # findings, design & strategy docs, PROJECT_STATE.md (this file)
├─ alembic/ + alembic.ini      # migration scaffolding (not wired)
├─ scripts/profile_dataset.py
├─ datasets/                   # 2.3 GB feed, git-ignored (runtime-discovered)
├─ Makefile                    # eval / test / lint / typecheck / check
└─ pyproject.toml, uv.lock
```

---

## Important Design Decisions

- **Duplicate ID handling:** the feed has **7,875 duplicate event IDs** (README claimed 0); all
  are benign exact re-emissions (96% cross-shard). `exact_duplicate` rule = global, `event_id`-keyed,
  first-wins → repeats quarantined with no LLM spend. Storage idempotency reinforces it.
- **`amount` vs `amount_normalized`:** `amount` is **free text** (`"$1m"`, `"$6 million"`);
  `amount_normalized` is the **numeric** field. The conditional-completeness rule reads
  `amount_normalized` (an early profiler reading of "0.8% present" was a coercion artifact).
- **Escalation strategy:** per-check tiered — run cheap (Haiku) judge; if `uncertain` and an
  escalation judge exists, re-run **only that check** on Sonnet (authoritative). Never re-evaluate
  the whole event.
- **Budget guard strategy:** one shared `BudgetGuard` per run; `ensure_available()` before each
  call, `record(cost)` after; on exhaustion the router degrades (remaining → REVIEW), never crashes;
  run cost reconciles with `BudgetGuard.spent`.
- **Idempotency strategy:** canonical key `(event_id, check_name, prompt_version, model)`; rule
  keys store `""` not NULL so the unique constraint dedupes them; re-running the pipeline overwrites
  (replay-safe, no double-bill). Routing sample is a deterministic hash of `event_id`.
- **Storage strategy:** async SQLAlchemy 2.0, SQLite-default/Postgres-ready (URL-only switch);
  storage-pure repositories (domain types), sinks bridge pipeline `EventOutcome` → repos;
  `events_clean` (current state) + `quality_verdicts` (append, time-partition in PG) + `trace_logs`
  (append-only audit). Pipeline depends on it only via optional sinks.
- **Monitoring strategy:** opt-in `MetricsSink`/`PipelineLogger`/`AlertEvaluator`, no-op by default;
  monitoring is dependency-light (domain + rules.metrics) to avoid cycles; OpenTelemetry is optional
  with graceful fallback (not a dependency); integrations are additive (no contract change).

---

## Known Technical Debt (intentionally deferred)

- **Alembic migrations:** scaffolding only; no version files / CI workflow (SQLite uses `create_all`).
- **`build_gateway` HTTP path** (httpx transport) is real but not unit-tested (no network in tests);
  request/response parsing *is* tested via a fake transport.
- **Eval label sets are seed-sized** (~10–12/check); production needs ≥30/check with two labelers.
- **Gemini schema sanitizer** is allow-by-prune; a new unsupported construct would need a new rule.
- **`quality_metrics_daily` rollup** (README §9) not built; dashboards would aggregate raw rows today.
- **OpenTelemetry / Grafana / Alertmanager wiring** not built — seams exist (no-op sinks, JSON logs,
  `AlertEvaluator`); enabling is configuration.
- **Tracing spans** (`Tracer` span seam) deferred.
- **LLM-backed remediator:** only the deterministic `HeuristicRemediator` ships; an LLM remediator
  can implement the same `Remediator` protocol.
- **Entity resolution** needs a candidate-generation/blocking step before the judge at scale.
- **Concurrency**: the runner materializes one task per in-flight item (bounded by `max_concurrency`);
  a true streaming windowed source would be needed for unbounded feeds.

---

## Next Phase — Phase 7: Dashboard

### Dashboard requirements
A reviewer-facing view over persisted data (`events_clean`, `quality_verdicts`, `trace_logs`) and a
live `MetricsSnapshot`, with at minimum the README §9 tiles:
1. **DQ trend over time**, split rule vs. LLM.
2. **Top failing reasons** surfaced by the judges (group by `reason`).
3. **Cost & latency** of LLM checks over time.
4. **Human-review backlog** size and age (count of `review` status).
Plus a **live alerts panel** driven by `AlertEvaluator`.

### Architecture requirements
- Read-only over the storage repositories (add read/aggregate query methods; do not bypass them).
- Streamlit **or** a static HTML report is acceptable (assessment scope); keep it a thin view —
  no business logic in the dashboard.
- Reuse `InMemoryMetricsSink.snapshot()` / `AlertEvaluator` for the live panels; reuse the eval
  harness output for the regression/quality view.
- No new mandatory dependencies in the core package; the dashboard may have its own optional extra.

### Reviewer goals
- Show the rules-vs-LLM split and the cost story at a glance.
- Make the review queue and the worst LLM failures (with reasons) inspectable.
- Demonstrate the canary/regression and alerting surfaces end to end.

---

## Restart Instructions (for a new Claude Code session)

1. **Read this file first**, then `README.md` (full design) and `docs/data-quality-findings.md`
   (the empirical numbers every rule is grounded in).
2. **Working agreement:** generate only the files for the current phase, no placeholders/toy code,
   run `ruff` + `mypy --strict` + `pytest` before finishing, **stop for review between phases**,
   and **do not add a `Co-Authored-By` trailer** to commits (repo preference).
3. **Verify the baseline:** `uv sync` then `uv run ruff check . && uv run mypy && uv run pytest`
   (expect 130 passing, clean) and `make eval` (expect exit 0).
4. **Dataset** is git-ignored under `datasets/` (or `DATASET_ROOT`); it is discovered at runtime.
   Tests/evals never need it (they use fixtures + ReplayJudge).
5. **Mental model:** `ingest → rules gate → pipeline (route/escalate/remediate/finalize) → store +
   monitoring`, with `evals` measuring judges offline. Lower layers never import higher ones; new
   cross-cutting features attach as **optional, no-op-by-default** injected seams.
6. **Conventions:** all domain models Pydantic v2; one `Verdict` type; pinned model IDs; structured
   output only; deterministic/injected clocks and sampling for replay-safety.
7. **Next work is Phase 7 (Dashboard)** — see above. Confirm scope with the user, then build the
   read/aggregate query methods on the repositories before the view.
8. **Git:** branch is `main`, pushed to `origin`. Identity `harshada-javeri <harshada.javeri@gmail.com>`.
   Per-phase commits follow `feat(phaseN): …`; commit and push only when the user asks.
