# How I Built This

*A first-person, honest account of building VeritasAI — the approach, the process, the tools, what
was hard, and what I'd change. Written for the Firmable reviewer.*

---

## Architecture approach

I started from one principle and let it dictate everything: **rules gate, LLMs judge, humans backstop —
and every decision is logged, versioned, costed, and measured.** That sentence is the whole system; the
code is just its faithful expansion.

Concretely that meant:

- **A single `Verdict` currency.** Rules and LLM judges both emit `pass | fail | uncertain` with
  confidence, reason, and evidence. One currency means one storage schema, one routing policy, one
  tracing format. This was the highest-leverage decision in the build — it collapsed what could have
  been two parallel subsystems into one.
- **Hexagonal layering with typed Protocol seams.** `ingest → rules → pipeline → (judges → llm_gateway)
  → store / monitoring → dashboard`, each layer depending only on lower ones, every boundary a Pydantic
  model or a `Protocol`. Storage and monitoring are *optional, no-op-by-absence* — the pipeline runs
  in-memory with neither.
- **Determinism as architecture.** Pinned model IDs (never `*-latest`), structured output via forced
  tool-use (never text parsing), idempotent verdict writes keyed on
  `(event_id, check_name, prompt_version, model)`, and a `ReplayJudge` so the entire system —
  evals, pipeline tests, the dashboard demo — runs offline, deterministically, for \$0.

The deliverable target was deliberate: **assessment-now, production-shaped.** Not a full FastAPI service,
but interfaces + config + dependency injection throughout, so it would *promote* to production without an
architectural rewrite. An [independent review board](PRODUCTION_READINESS_REVIEW.md) called it "a 9/10
design wearing a 3/10 production surface — and it knows it." That self-awareness was the goal.

## Build process

I built in **strict phases, stopping for review between each one**, with a written design review *before*
any code in a phase:

- **Phase 0** — config, the `ResolvedEvent`/`Verdict` domain models, the streaming JSON:API parser, and
  a profiling script.
- **Phase 1** — the deterministic rules engine (8 rules) + tests.
- **Phase 2** — LLM judges, the versioned prompt registry, the cost-metered LLM gateway.
- **Phase 3** — the eval harness with a regression gate.
- **Phase 4** — pipeline orchestration (routing, tiered escalation, proposal-only remediation).
- **Phase 5–6** — async SQLAlchemy storage and the monitoring/observability framework.
- **Phase 7** — the read-only Streamlit Decision Intelligence Console.

Every phase landed MyPy-strict-clean, Ruff-clean, and fully tested before the next began. The repo is at
**157 tests** today. The discipline of "no placeholders, no toy code, stop for review" kept the codebase
honest — there's no dead scaffolding waiting to be filled in.

The most valuable early step was **profiling the real feed before writing a single rule.** The data
contradicted my own design doc: 620K records (not 310K), 29 categories (not 40+), `amount` present in
only 0.8% of records (not ~5%), and 7,875 duplicate event IDs where the spec claimed zero. That profiling
pass directly changed the rules — e.g. conditional-completeness checks `amount_normalized`, not a blind
`amount` requirement, because the naive rule would have flagged 99% of records.

## AI tools used

I'll be direct about this, because Firmable asks for it and because it's the honest picture:

- **Claude Code (Opus)** was the primary build tool — used for architecture discussion, implementation,
  test authoring, refactoring, and documentation. The phased, design-review-first workflow above was run
  *through* Claude Code: I'd agree the design for a phase, have it generate only the approved files, then
  review and gate before moving on.
- **The `ReplayJudge` pattern is itself an AI-tooling decision** — it let me develop and test the entire
  LLM layer against recorded fixtures with zero live spend, which is how the whole thing was buildable in
  a weekend without burning a budget.

What AI tooling did *not* do: make the load-bearing judgment calls. Those were mine.

## Human decisions vs AI assistance

The decisions I owned (and would defend in a design review):

- **The deliverable scope** — "assessment-now, production-shaped" vs. a full service. This framed every
  subsequent trade-off.
- **The rule-vs-LLM split** — the heuristic "if you can write it as a regex, range, set-membership, or
  join, it's a rule; if it needs reading prose, it's an LLM check." That's the thing the assessment is
  really testing, and it's a human call.
- **Replay-first development** — choosing reproducibility and \$0 iteration over the convenience of live
  calls.
- **Fail-safe routing** — every ambiguity or error biases toward human REVIEW, never a silent pass; and
  remediation is proposal-only.
- **Reading the profiling output and changing the rules because of it** — the `amount_normalized` fix and
  taking duplicate detection seriously came from looking at real numbers, not from a spec.

AI assistance accelerated the *expression* of these decisions into typed, tested code. The decisions
themselves came from understanding the data and the problem.

## Hardest challenges

- **Conditional completeness.** The naive rule ("financing events must have `amount`") would have been
  catastrophic — `amount` is present in only ~0.8% of records and even in `receives_financing` only ~15%.
  The fix was to check the derived `amount_normalized` feature, not the raw field. This is the clearest
  example of why profiling-before-rules matters.
- **Idempotency vs. NULLs.** SQL treats NULLs as distinct in a unique constraint, which would have
  *defeated* idempotency for rule verdicts (whose `prompt_version`/`model` are absent). Storing those as
  empty strings rather than NULL was a small, easy-to-miss decision with large correctness implications.
- **Keeping monitoring acyclic.** The monitoring layer had to observe the pipeline without depending on
  it. The answer was to have `AlertEvaluator` take primitives (a `BudgetStatus`, a list of regressed
  metrics) rather than the rich pipeline types — dependency inversion that kept the layering clean.
- **Async storage testing.** The `sqlalchemy[asyncio]` extra (which pulls `greenlet`) is required; plain
  `sqlalchemy` fails async tests with an opaque "no greenlet" error. A half-hour of confusion compressed
  into one line in the build notes.

## Tradeoffs

- **Replay everywhere → the live path has never run.** I traded live-validation for reproducibility and
  zero cost. Honest, and documented as the top roadmap item.
- **In-process state → not yet horizontally scalable.** The design is shardable and idempotent, but
  state is in-memory today. A deliberate scope cut, not an oversight.
- **10–12 labels per eval check → the judge is *directed*, not *certified*.** Enough to find where the
  judge is weak (the valuable part), not enough to certify it. The dashboard says so, on the scorecard.
- **Prompts live under `src/veritas/prompt_registry/prompts/`** rather than a top-level `prompts/` — they
  ship with the package and load via `importlib.resources`, at the cost of diverging from the spec's
  expected location.

## What I would change

- **Prove the live path** end-to-end against the Anthropic API on a small batch, then close the
  replay-respend gap with a cache.
- **Externalize state** to Postgres/Redis (the storage URL is already the only thing that changes).
- **Wire alert *delivery*** — the `AlertEvaluator` computes alerts but routes them nowhere yet.
- **Expand the eval sets to ≥30 examples per check** with a second labeller and an agreement score, to
  move the judges from "directed" toward "certified."
- **Promote source to a first-class analysis axis** — this is exactly the Phase 8 direction the Firmable
  feedback pointed at, and the architecture already carries source lineage to support it.

## Lessons learned

1. **Profile the real data before you write a single rule.** Every interesting decision in this build
   came from the feed contradicting the spec.
2. **Pick your currency early.** The single `Verdict` type paid for itself in every layer downstream.
3. **Determinism is a feature, not a constraint.** Replay + pinned models + idempotent writes made the
   system testable, reproducible, and cheap — and made *this very submission* runnable by a reviewer in
   five minutes with no keys.
4. **Measure the judge before you trust it.** The failure-analysis note — *why* the judge got the worst
   cases wrong — turned out to be the most valuable artifact in the whole project, exactly as predicted.
5. **AI tooling is a force multiplier on judgment, not a substitute for it.** The build moved fast
   because the architecture decisions were made deliberately by a human and then expressed precisely with
   AI assistance — not the other way around.
