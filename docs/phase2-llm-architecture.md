# VeritasAI — Phase 2: LLM Architecture & Judges

*The AI evaluation layer: vendor-agnostic, cost-aware, fully testable, replayable without API calls.*
*Date: 2026-06-22.*

This is the layer that does the **judgement work** rules can't: semantic accuracy,
source credibility, entity resolution. It sits behind the rules gate (Phase 1) and
escalates only what rules can't settle.

---

## 1. Layering

```
            judges/                         the "what to ask"
  ┌───────────────────────────────┐
  │ LLMJudge (Protocol)            │  async evaluate(event) -> Verdict   (only)
  │  ├─ ReplayJudge   (fixtures)   │  no network, used by evals + dev
  │  ├─ AnthropicJudge ┐ provider- │
  │  └─ GeminiJudge    ┘ bound     │  share BaseLLMJudge: event→prompt→Verdict
  └───────────────┬───────────────┘
                  │ LLMRequest / LLMResponse   (vendor-neutral currency)
  ┌───────────────▼───────────────┐         ┌──────────────────────────────┐
  │ llm_gateway/                   │ uses    │ prompt_registry/             │
  │  LLMGateway.complete():        │◀────────│  PromptSpec (name/version/   │
  │   pin → route → retry →        │         │   owner/model/schema/        │
  │   account cost → budget guard  │         │   system/template)           │
  │  └─ ProviderClient (per vendor)│         │  PromptRegistry (YAML dir)   │
  │      └─ Transport (HTTP seam)  │         └──────────────────────────────┘
  └────────────────────────────────┘
```

**Boundary discipline:** the only vendor-specific code is in the gateway's provider
clients. Judges, prompts, and the `Verdict` they emit are vendor-neutral — switching a
check from Claude to Gemini is a model-id change, nothing else.

---

## 2. Design goals → how they're met

| Goal | Mechanism |
|---|---|
| **Vendor agnostic** | `LLMGateway.complete(LLMRequest) -> LLMResponse` is provider-neutral; `provider_for_model` routes by id prefix to `AnthropicClient` / `GeminiClient`. Adding a vendor = one client + a pin. |
| **Cost aware** | `PricingTable` (USD/MTok per pinned model) → cost on every `LLMResponse`; `BudgetGuard` meters cumulative spend and refuses calls once the ceiling is hit. |
| **Fully testable** | The HTTP boundary is the `Transport` Protocol. Tests inject a fake returning canned provider bodies, exercising real request-building and response-parsing with **zero network and zero keys**. 77 tests, MyPy-strict, Ruff-clean. |
| **Replayable without API calls** | `ReplayJudge` returns recorded `Verdict`s keyed by `event_id` — the basis for reproducible evals (Phase 3) and free local development. |

---

## 3. Structured output — only JSON, never parsed prose

Both providers are forced to emit one fixed shape, [`JUDGE_OUTPUT_SCHEMA`](../src/veritas/judges/schema.py)
(`verdict` / `confidence` / `reason` / `evidence_span`), validated into `JudgeOutput`:

- **Anthropic** — Messages API with a single **forced tool** (`tool_choice: {type: tool}`);
  the tool's `input_schema` *is* our schema, and the structured output is the `tool_use.input`
  dict (no text parsing, ever).
- **Gemini** — `generateContent` with `responseMimeType: application/json` + a `responseSchema`.
  Gemini rejects `additionalProperties`/`title`/`$ref`, so the client sanitizes the schema first
  — which is exactly why the schema is a hand-written flat dict, not a Pydantic-derived one
  (Pydantic would emit `$defs`/`$ref` for the enum).

`confidence` is clamped into `[0, 1]` so a mildly out-of-range model value degrades to a valid
verdict rather than raising.

## 4. Request lifecycle (`LLMGateway.complete`)

1. **Pin check** — model must be in the allowlist, else `ModelNotPinnedError`. No silent `-latest`.
2. **Route** — by id prefix to the provider client.
3. **Retry** — `with_retry` retries `TransientLLMError` (429/5xx/network) with exponential backoff;
   `PermanentLLMError` (4xx, malformed response) is not retried. `sleep` is injectable → deterministic tests.
4. **Account** — cost = `PricingTable.cost(model, in, out)`; latency from an injectable clock.
5. **Budget** — `ensure_available()` before, `record(cost)` after; the meter is the throttle.
6. Return `LLMResponse` (content + model + provider + tokens + cost + latency).

The judge maps that into a `Verdict` with `check_type=LLM`, `prompt_version`, `model`, tokens, cost,
and latency — the same `Verdict` type rules emit, so storage and the trace log stay uniform.

## 5. Prompt registry

Three shipped prompts (one YAML each, under `prompt_registry/prompts/`), tracking the five required
fields plus `system`/`template`:

| Prompt | Model (pinned) | Check |
|---|---|---|
| `semantic_accuracy` | `claude-haiku-4-5-20251001` | category vs text (the workhorse) |
| `source_credibility` | `claude-haiku-4-5-20251001` | genuine news vs PR/marketing/reprint |
| `entity_resolution` | `claude-sonnet-4-6` | is company1 plausibly the subject |

This realizes the README's model-choice principle: **Haiku for cheap classification at volume,
Sonnet for the nuanced check.** Rendering uses `string.Template` (`$placeholder`) so JSON braces
in a prompt never collide with formatting.

## 6. Pricing (confirmed Anthropic rates; Gemini illustrative)

| Model | Input $/MTok | Output $/MTok |
|---|---:|---:|
| `claude-haiku-4-5` | 1.00 | 5.00 |
| `claude-sonnet-4-6` | 3.00 | 15.00 |
| `gemini-2.5-flash` | 0.30 | 2.50 *(verify before a real run)* |

## 7. Out of scope (Phase 2 boundary)

No storage layer (judges return `Verdict`s; persistence is later). No eval harness, no agentic
pipeline wiring, no live API keys exercised in tests. `build_gateway(...)` wires a real
`HttpxTransport`-backed gateway from settings + keys when a live run is wanted.

## 8. Known sharp edges

- **`build_gateway` HTTP path is not unit-tested** (it would require network); the request/response
  logic it depends on *is* fully tested via the fake transport. The thin httpx wrapper is the only
  unverified line.
- **Gemini schema sanitizer is allow-by-prune** — it strips known-unsupported keys; a future schema
  using an unsupported construct Gemini *also* rejects would need a new prune rule.
- **`entity_resolution` should confirm, not search** (README §11): candidate generation by
  domain/ticker belongs before this judge at scale — the judge validates a proposed link.
