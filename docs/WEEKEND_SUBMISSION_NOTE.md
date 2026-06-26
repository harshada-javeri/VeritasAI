# VeritasAI — Submission Note

*To: Suresh · Firmable leadership · CDO*

Hi all,

Sharing VeritasAI — an AI-native data-quality platform for the news-event feed. The repo is on `main`
and the [README](../README.md) opens with a recruiter-friendly overview; deeper docs are linked below.

**What I built.** A layered pipeline that validates ~620K news-event records on one principle: *rules
gate, LLMs judge, humans backstop — everything logged, versioned, costed, and measured.* Deterministic
rules do the cheap, exact work on 100% of records for free; LLM judges handle only the semantic
questions rules can't settle; ambiguous cases route to a human queue. Phases 0–7 are complete — ingest,
rules, LLM gateway + judges, an eval harness, the pipeline, storage, monitoring, and a read-only
decision dashboard. **157 tests passing, MyPy strict clean, Ruff clean.**

**Key engineering decisions.** A single `Verdict` currency for rules and LLMs; pinned model IDs and
structured output (reproducible, never fragile prose); tiered escalation (cheap judge first, escalate
only the *uncertain* check) as the cost lever; a budget guard on every call; idempotent writes; and
fail-safe routing — every ambiguity biases toward human review, never a silent pass.

**Scale.** It runs offline and deterministically today; the contracts (Verdict, idempotency key,
Protocol seams) hold at far larger scale, with a clear, honest promotion path documented (externalize
state, Postgres, batched writes).

**Stakeholder feedback.** Firmable's three priorities — precision over coverage, humans own ambiguity,
source-level drift over aggregate trends — each *validated* a decision already in the build, and set
the next phase.

**Next iteration.** Phase 8: source intelligence — quality, cost, and drift attributed *by source*,
plus a richer human-review-and-ownership workflow.

Honest framing throughout: the [production-readiness review](PRODUCTION_READINESS_REVIEW.md) states
plainly what's prod-shaped versus prod-ready. Happy to walk through any of it.

Thanks,
Harshada
