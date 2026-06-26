# VeritasAI — Demo Script

*A 2–3 minute live walkthrough for a VP Engineering, CDO, or technical reviewer.*
*Each stop has: **Show** (what's on screen) · **Say** (the line) · **Why it matters** (the takeaway).*

> **The spine of the demo, one sentence:** *Rules gate, LLMs judge, humans backstop — and every*
> *decision is traced, versioned, costed, and measured.* Keep returning to it.

**Opening line (10 sec):**
> "VeritasAI validates ~620,000 news-event records — acquisitions, hires, launches — that other teams
> consume as truth. The whole design is one principle: do the cheap deterministic work with rules,
> reserve the expensive judgment for LLMs, send the genuinely ambiguous cases to a human — and measure
> every step. Let me walk the path a single record takes."

---

## 1 · Dataset

**Show:** A raw JSON:API line — a `news_event` with its `category`, `summary`, `article_sentence`, and
its linked `included` entities (the companies and the source article). Mention the scale: 620K records,
~40 categories, dates spanning 2010–2025.

**Say:**
> "Each record is a news event plus the entities and source article it was extracted from. The feed is
> real and messy — confidence scores spike at zero for noise, one article often spawns many events, and
> we found 7,875 duplicate IDs the spec claimed didn't exist. We profiled the actual data first and
> built the rules to match reality, not the documentation."

**Why it matters:** Sets the stakes (scale, messiness) and signals the work is *empirically grounded* —
the rules exist because the data demanded them, not because a spec said so.

---

## 2 · Rules Engine

**Show:** The 8 deterministic rules — UUID validity, confidence range, confidence floor, known category,
date sanity, referential integrity, conditional completeness, exact duplicate. Show one record hitting a
hard rule and being **quarantined** before any model is touched.

**Say:**
> "Rules run first, on 100% of records, at zero token cost. If a rule hard-fails — broken reference,
> impossible date, a duplicate we've already seen — the record is quarantined immediately and never
> reaches an LLM. Anything a regex, a range, or a join can answer is a rule. This gate is what keeps the
> cost story honest."

**Why it matters:** This is the central design decision — **rules are the gate.** They catch the bulk
of defects for free and protect the LLM budget. No money is spent on questions arithmetic can answer.

---

## 3 · LLM Escalation

**Show:** A record that passes the rules but needs *judgment* — does the summary actually describe its
category? Show the cheap judge (Haiku) returning a verdict, and an `uncertain` result escalating *only
that check* to the stronger judge (Sonnet). Point at the structured JSON output: `verdict`, `confidence`,
`reason`, `evidence_span`.

**Say:**
> "When the question is semantic — does this text really describe an acquisition? is this source genuine
> news or a press release? — we reach for an LLM. The cheap model handles the volume; only the *uncertain*
> check escalates to the stronger model, and we re-judge just that one check, never the whole event. Every
> verdict is structured JSON with a reason and the exact evidence span that drove it. Model IDs are pinned
> — never `latest` — so a verdict is always attributable to an exact model."

**Why it matters:** **LLMs are the judge, and tiered escalation is the cost lever.** We spend more only
on the hard cases, and only on the part that's actually hard. Pinned models + structured output mean
verdicts are reproducible and parseable — never a fragile prose blob.

---

## 4 · Evaluation

**Show:** `make eval` running — per-check precision/recall/F1 against hand-labeled datasets, and the
regression gate (a metric drop beyond threshold exits non-zero). Show the worst-failure dump.

**Say:**
> "We never ship a judge we haven't measured. Every check runs against a labeled set and reports
> precision, recall, and F1, and the harness fails the build if any metric regresses — so a prompt change
> can't silently make the judge worse. We optimize for precision here: a confident wrong 'pass' is far
> more expensive than an extra item sent to review. And every run dumps its worst misclassifications so we
> can read *why* it was wrong."

**Why it matters:** This is what makes it AI-*native*, not AI-*assisted*. The judge is a measured
component with a regression gate — and the metric we gate on is **precision**, exactly the priority our
stakeholder confirmed.

---

## 5 · Storage

**Show:** The three tables — `events_clean` (current state: clean / quarantined / review),
`quality_verdicts` (one row per check), `trace_logs` (append-only audit). Point at the idempotency key
`(event_id, check_name, prompt_version, model)`.

**Say:**
> "Everything persists with full provenance. Each verdict records its prompt version, model, tokens, cost,
> latency, and timestamp. Writes are idempotent on a canonical key, so re-running the pipeline overwrites
> cleanly and never double-writes. It's SQLite by default and Postgres by a URL change — the storage layer
> speaks domain types and doesn't know which database it's talking to."

**Why it matters:** **Defensibility.** For any record, we can answer "why did we decide this, with which
model, at what cost?" The append-only trace is real audit lineage, and idempotency makes replay safe.

---

## 6 · Observability

**Show:** Structured JSON logs, the metrics snapshot, and the `AlertEvaluator` producing alerts — budget
exceeded, eval regression, review/quarantine/provider-failure spikes — with noise suppression.

**Say:**
> "The pipeline emits structured metrics and logs, and an alert evaluator watches for the things that
> matter — budget burn, a quality regression, a spike in failures or review backlog. Monitoring is a
> no-op-by-default seam: the pipeline runs without it and never depends on it, so we can enable real
> telemetry export as configuration, not a rewrite."

**Why it matters:** The system is **observable by design** through clean, optional seams. Alert *logic*
is built and tested; wiring it to a real pager or telemetry backend is configuration, not new
architecture. (Be honest: delivery is the production roadmap, not shipped today.)

---

## 7 · Dashboard

**Show:** The Decision Intelligence Console. Walk three workspaces quickly:
- **Trust Center** — the transparent quality index (show the *formula*, not a magic number).
- **Human Review** — the queue of ambiguous events with the judge's reasoning and evidence.
- **Event Detail** — click any aggregate to drill all the way down to one event's full verdict stack,
  trace, and cost.

**Say:**
> "The console is read-only over that same storage layer — strict layering, no business logic in the UI.
> The Trust Center shows *how* the score is computed, not just the number. Human Review is where the
> ambiguous tail lives — because humans own those decisions, with full context. And everything drills
> down: from any aggregate, one click to a single event's complete story. That drill-down spine is the
> foundation for the next phase — source intelligence and root-cause workflows."

**Why it matters:** **Humans are the backstop, and the dashboard makes every decision inspectable and
attributable.** It closes the loop — from 620K records down to one defensible decision — and points
directly at the roadmap: making quality attributable *by source*.

---

## Closing (15 sec)

> "So: rules gate for free, LLMs judge only where needed and escalate only the hard part, humans own the
> ambiguous tail, and every decision is traced, versioned, costed, and measured. It's built offline and
> deterministically today — 157 tests, strict typing, clean — and it promotes to production along a
> roadmap we've already scoped honestly. The next phase makes quality attributable to the source that
> caused it. That's VeritasAI."

---

### Timing guide

| Stop | Target |
|---|---|
| Opening | 0:10 |
| 1 · Dataset | 0:20 |
| 2 · Rules Engine | 0:25 |
| 3 · LLM Escalation | 0:30 |
| 4 · Evaluation | 0:25 |
| 5 · Storage | 0:20 |
| 6 · Observability | 0:20 |
| 7 · Dashboard | 0:35 |
| Closing | 0:15 |
| **Total** | **~3:00** |

**If you only have 90 seconds:** Opening → Rules Engine → LLM Escalation → Dashboard → Closing. Those
four stops carry the whole thesis: gate, judge, backstop, measured.
