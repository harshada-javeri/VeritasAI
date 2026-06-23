# VeritasAI — Observability (Phase 6)

*Metrics, structured logging, an optional OpenTelemetry adapter, and alerts —
wired into the existing pipeline without changing any public contract.*
*Date: 2026-06-23.*

Observability is **opt-in and dependency-light**. The `monitoring` package depends only
on `domain` + `rules.metrics`, so the gateway, runner, and repositories can emit into it
with no import cycle. Every integration point is an **additive optional argument** with a
no-op default — existing call sites and Protocol method signatures are unchanged.

## 1. Components

| Component | Role |
|---|---|
| `MetricsSink` (Protocol) | `on_rule` / `on_llm` / `on_provider_call` / `on_outcome` |
| `NullMetricsSink` | no-op default (observability off) |
| `InMemoryMetricsSink` | in-process counters + `snapshot() -> MetricsSnapshot` |
| `MetricsRuleSink` | adapts the Phase-1 `RuleMetricsSink` → unified `MetricsSink` (zero RuleEngine change) |
| `OpenTelemetryMetricsSink` | optional OTel adapter; **graceful fallback** to no-op when OTel absent |
| `PipelineLogger` | structured **JSON-only** event logging |
| `AlertPolicy` / `AlertEvaluator` | threshold policy + evaluation over a snapshot |

## 2. Tracked fields

Per the spec, metric events carry: `rule_name`, `verdict`, `severity`, `latency_ms`,
`tokens` (`input_tokens`/`output_tokens`), `cost_usd`, `prompt_version`, `model`. These live
on `RuleExecution` (rule_name/verdict/severity/latency_ms) and `LLMExecution`
(check_name/model/prompt_version/verdict/latency_ms/tokens/cost_usd).

## 3. Integration points (additive, no contract change)

| Surface | What it emits | How |
|---|---|---|
| **RuleEngine** | `on_rule` per rule | `RuleEngine(rules, metrics=MetricsRuleSink(sink))` — the Phase-1 metrics seam |
| **LLMGateway** | `on_provider_call` (provider, ok, error_type) | new optional `metrics=` kwarg; records success/failure around the retried call |
| **PipelineRunner** | `on_llm` per verdict + `on_outcome` per event + JSON log | new optional `metrics=` / `logger=` kwargs |
| **Repositories** | structured persistence logs (`verdicts_upserted`, `event_upserted`, `trace_appended`) | new optional `logger=` kwarg |

Gateway/repositories import monitoring under `TYPE_CHECKING` only (annotations) with `None`
defaults, so they stay decoupled at runtime.

## 4. Metrics catalog

| Metric | Source | Meaning |
|---|---|---|
| `rule_executions`, `rule_failures` | `on_rule` | deterministic-rule volume and hard-fails |
| `llm_executions` | `on_llm` | judge calls that produced a verdict |
| `input_tokens`, `output_tokens`, `cost_usd` | `on_llm` | token + cost accounting (reconciles with `BudgetGuard.spent`) |
| `escalations` | `on_outcome` | events routed to LLM judges (action ESCALATE) |
| `clean`, `review`, `quarantine`, `outcomes` | `on_outcome` | final-status distribution |
| `provider_calls`, `provider_failures` | `on_provider_call` | gateway transport health per provider |
| derived: `review_rate`, `quarantine_rate`, `provider_failure_rate` | `MetricsSnapshot` | rate views for alerting |

OTel metric names (when the adapter is active): `veritas.rule.executions`,
`veritas.llm.executions`, `veritas.llm.cost_usd`, `veritas.provider.calls`,
`veritas.events.outcomes`, each with attributes (rule/verdict/model/provider/status).

## 5. Alert catalog

| Alert | Severity | Fires when |
|---|---|---|
| `budget_exceeded` | error | `budget.spent >= budget.limit` |
| `evaluation_regression` | error | any tracked eval metric regressed (from Phase 3) |
| `review_rate_spike` | warning | `outcomes ≥ min_samples` and `review_rate > review_rate_max` (0.50) |
| `quarantine_rate_spike` | warning | `outcomes ≥ min_samples` and `quarantine_rate > quarantine_rate_max` (0.40) |
| `provider_failure_spike` | error | `provider_calls ≥ min_samples` and `provider_failure_rate > provider_failure_rate_max` (0.20) |

Rate alerts are **suppressed below `min_samples` (20)** to avoid noise on tiny windows.
`AlertEvaluator.evaluate(snapshot, *, budget=BudgetStatus(...), regressed_metrics=[...])`
takes monitoring-local inputs — the caller adapts a `BudgetGuard` and an eval
`RegressionReport` into them, keeping monitoring free of those dependencies.

## 6. Structured logging

`PipelineLogger.log(event, **fields)` emits one JSON object per call (sorted keys,
`default=str`). `emit` is injectable (tests capture lines; default → stdlib logger) and
`clock` is injectable (deterministic `ts`, omitted when no clock). Events today:
`event_finalized` (runner), `verdicts_upserted` / `event_upserted` / `trace_appended`
(repositories).

## 7. OpenTelemetry: optional with graceful fallback

`OpenTelemetryMetricsSink` imports OTel **lazily via `importlib`** (so MyPy never needs the
stubs and nothing breaks when it is absent). If OTel is not installed the sink reports
`available is False` and every method no-ops; `OpenTelemetryMetricsSink.try_create()` returns
a `NullMetricsSink` instead. **OpenTelemetry is not a project dependency** — installing it is
the only thing needed to light up real export.

## 8. Future architecture (Grafana / OpenTelemetry)

```
VeritasAI pipeline
  ├─ MetricsSink ── OpenTelemetryMetricsSink ──▶ OTLP exporter ──▶ OTel Collector
  │                                                                   ├──▶ Prometheus ──▶ Grafana dashboards
  │                                                                   └──▶ (traces) Tempo/Jaeger
  └─ PipelineLogger (JSON) ───────────────────────────────────────▶ Loki / stdout ──▶ Grafana logs
                                                                       AlertEvaluator ──▶ Alertmanager / PagerDuty / Slack
```

- **Metrics**: swap `NullMetricsSink` → `OpenTelemetryMetricsSink.try_create()`; the OTel
  Collector scrapes/receives and forwards to Prometheus; Grafana renders the metrics catalog
  (DQ trend rule-vs-LLM, cost/latency, review-queue size — README §9 tiles).
- **Logs**: `PipelineLogger`'s JSON lines ship to Loki/stdout; Grafana correlates by
  `event_id`.
- **Alerts**: run `AlertEvaluator` on a schedule (or on a rolling snapshot) and route alerts to
  Alertmanager → Slack/PagerDuty — the same surfaces README §8 calls for (rule-fail spike → Slack,
  regression → page, review backlog → tile).
- **Traces** (later): the deferred `Tracer` span seam becomes OTel spans across ingest → rules →
  escalation → finalize.

Nothing above is wired yet; the seams (no-op sinks, structured logger, alert evaluator) are in
place so enabling a backend is configuration, not a rewrite.

## 9. Tests (`tests/test_monitoring.py`)

In-memory accumulation; null-sink inertness; the rule-metric adapter; structured-JSON logging;
the OTel graceful fallback; each alert kind (budget, regression, review/quarantine/provider
spikes) plus min-samples suppression and the healthy-silent case; gateway provider
success/failure recording; and a full pipeline run asserting rule/LLM/outcome metrics and the
`event_finalized` log — then feeding the resulting snapshot through the `AlertEvaluator`.
