# Final Submission Audit — VeritasAI

**Reviewer roles:** Senior Staff Engineer · Founding Engineer · Firmable Assessment Reviewer
**Date:** 2026-06-24 · **Branch:** `main` · **HEAD:** `b333e5c`
**Mode:** Read-only verification. No code modified, nothing committed.
**Method:** The repository was read as a reviewer would — and, critically, *as a fresh `git clone` would
present it* (committed state), not just the local working tree.

---

## ⚠ Headline finding (read first)

**The repository is content-complete but not commit-complete.** Several files the committed README links
to — including the single highest-visibility Firmable deliverable, `skills/` — **exist on disk but are
untracked in git**. A reviewer who clones the repo at `HEAD` gets broken links and missing deliverables.

Untracked (invisible on clone), verified via `git ls-files`:

| Path | Why it matters | README links to it? |
|---|---|---|
| `skills/` (both `SKILL.md` files) | **The #1 named deliverable.** Its absence is the most visible possible gap. | Yes (§5, multiple) |
| `docs/eval-results.md` | "The most valuable artifact in the whole submission" (per the README itself) | Yes |
| `docs/EXECUTIVE_OVERVIEW.md` | Five-minute overview; Roadmap link target | Yes |
| `docs/STAKEHOLDER_FEEDBACK_INTEGRATION.md` | Firmable feedback response | Yes |
| `docs/checks-writeup.md` | Notion Part 2 (per-check writeup) | No (linked from other docs) |
| `docs/source-drift-intelligence.md` | Phase 8 proposal | No (linked from HOW_I_BUILT_THIS + others) |
| `docs/DEMO_SCRIPT.md`, `docs/WEEKEND_SUBMISSION_NOTE.md` | Supporting | No |

Also uncommitted (working-tree modifications): `docs/HOW_I_BUILT_THIS.md`,
`src/veritas/dashboard/app.py`, `src/veritas/dashboard/repositories/base.py`,
`src/veritas/dashboard/repositories/__init__.py`, and a new `.streamlit/config.toml`.

**This is a one-commit fix.** The engineering and the documents are done; they simply are not in the
tree a reviewer downloads. Everything below is reported against this reality: where a reference resolves
locally but not on clone, that distinction is called out.

---

## Task 1 — README Reference Verification

Legend: ✅ exists & committed · 🟡 exists on disk but **untracked (404 on clone)** · ⚠ exists but
outdated/mismatched · ❌ missing entirely

### Linked documents

| Reference | On disk | In clone | Verdict |
|---|---|---|---|
| `docs/PRODUCTION_READINESS_REVIEW.md` | yes | tracked | ✅ |
| `docs/pipeline-design.md` | yes | tracked | ✅ |
| `docs/HOW_I_BUILT_THIS.md` | yes | tracked (uncommitted edits) | ✅ |
| `screenshots/README.md` | yes | tracked | ✅ |
| `docs/eval-results.md` | yes | **untracked** | 🟡 |
| `docs/EXECUTIVE_OVERVIEW.md` | yes | **untracked** | 🟡 |
| `docs/STAKEHOLDER_FEEDBACK_INTEGRATION.md` | yes | **untracked** | 🟡 |
| `#quickstart-for-reviewers` (anchor) | heading `# Quickstart (for reviewers)` present → slug matches | n/a | ✅ |
| `https://docs.astral.sh/uv/` | external | n/a | ✅ |

### Scripts, paths, commands

| Reference | Verdict | Note |
|---|---|---|
| `scripts/seed_demo_db.py` | ✅ | tracked; runs; seeds 168/646/336 rows |
| `src/veritas/dashboard/app.py` | ✅ | run command correct |
| `src/veritas/evals/datasets/` | ✅ | three versioned dataset dirs present |
| `skills/news-events-quality-check/SKILL.md` | 🟡 | exists, **untracked** |
| `skills/news-events-remediation/SKILL.md` | 🟡 | exists, **untracked** |
| `make check`, `make eval` | ✅ | both targets exist and pass green |
| `uv sync`, `cp .env.example .env` | ✅ | `.env.example` present |
| `./veritas.db` | ✅ | default `database_url`; git-ignored as intended |
| `python evals/run.py` (§7) | ⚠ | **stale command** — no such file. Real entry: `make eval` / `python -m veritas.evals` |
| `prompts/` (§5) + `semantic_accuracy.v3.txt` | ⚠ | **path & format mismatch** — actual: `src/veritas/prompt_registry/prompts/*.yaml`, version `v1`, YAML not `.txt`, no `v3` |
| `eda/ … sql/ …` layout (§10) | ⚠ | **aspirational layout** — `eda/` and `sql/` were never created |

> The three ⚠ items all live in the **original technical-design narrative (§1–12)**, which predates the
> implementation and describes the *intended* shape. They are not in the reviewer-facing Quickstart, but
> a reviewer who reads top-to-bottom will hit `python evals/run.py` and `prompts/` as if runnable. They
> should be reconciled with reality (or explicitly marked "original design spec").

### Stated metrics

| Claim | Reality | Verdict |
|---|---|---|
| "157 tests passing" | 157 passed | ✅ |
| "Ruff clean" | clean | ✅ |
| "MyPy strict clean (115 files)" | now **116 files** (the committed `scripts/seed_demo_db.py` adds one) | ⚠ off by one |
| "eval gate green" | `make eval` exits 0 | ✅ |

---

## Task 2 — Reflection Review (`docs/HOW_I_BUILT_THIS.md`), as a CTO

A genuinely strong document — concrete, specific, and honest about both AI usage and limitations. It is
anchored in real engineering detail (the `amount_normalized` fix, NULL-vs-idempotency, the `greenlet`
extra, `AlertEvaluator` taking primitives to stay acyclic) rather than generalities, which is what
separates an authentic reflection from a generated one.

| Dimension | Score | Notes |
|---|---|---|
| Authenticity | 8/10 | Specific war-stories ground it; prose *cadence* (uniform em-dashes, bolded lead-in on every bullet, triadic phrasing) reads slightly AI-polished. |
| Technical depth | 9/10 | Real decisions with real consequences; nothing hand-wavy. |
| AI-native engineering mindset | 9/10 | `ReplayJudge` and the skills-as-contract framing are genuinely AI-native, not bolt-on. |
| Ownership | 9/10 | Clear separation of human-owned decisions vs. AI-assisted expression. |
| Humility | 8/10 | Names the gaps (live path unrun, 10–12 labels, alert delivery) without defensiveness. |
| Production thinking | 8/10 | "9/10 design, 3/10 surface" self-assessment is mature; roadmap is concrete. |
| Communication | 9/10 | Tight, scannable, well-structured. |

**Average ≈ 8.6 / 10.**

**Watch-outs (minor):** the closing "Lessons learned" aphorisms ("Determinism is a feature, not a
constraint", "force multiplier on judgment") are backed by specifics, but a skeptical CTO may read the
rhythm as LLM-assisted. **Recommendation (optional):** vary sentence structure in 3–4 spots and trim one
or two aphorisms to lower the "AI cadence" signal. No factual or substance changes needed.

---

## Task 3 — Discoverability (3-minute reviewer)

| Directory | Exists | Committed | Obvious purpose | Versioned | Reviewer-friendly |
|---|---|---|---|---|---|
| `skills/` | yes | **NO (untracked)** | yes (clear names + SKILL.md) | n/a | ❌ **invisible on clone** |
| `prompts/` (top-level) | **no** | — | — | — | ❌ reviewer expects it at root per README §5; actual prompts are at `src/veritas/prompt_registry/prompts/` |
| `evals/` (top-level) | **no** | — | — | — | 🟡 actual evals at `src/veritas/evals/` with versioned `datasets/*_v1/` — correct and versioned, but not where §0/§7 imply |

**What would confuse a reviewer in 3 minutes:**
1. **`skills/` is the named deliverable and it isn't in the clone.** Highest-impact confusion possible.
2. **`prompts/` and `evals/` are not at the repo root** where the README's design narrative says they
   are. The content is excellent (versioned YAML prompts, versioned labeled datasets with predictions),
   but a reviewer scanning the root sees neither directory and may conclude they're missing.

---

## Task 4 — Repository Navigation

Can a reviewer quickly locate each concern? (assuming the untracked files get committed)

| Concern | Location | Findable? |
|---|---|---|
| Architecture | README "Architecture Overview" + `docs/architecture-review.md` | ✅ |
| Prompts | `src/veritas/prompt_registry/prompts/*.yaml` | 🟡 not at root; README points to wrong path |
| Evaluation | `src/veritas/evals/` + `docs/eval-results.md` + `docs/evaluation-strategy.md` | 🟡 (eval-results untracked) |
| Dashboard | `src/veritas/dashboard/` + README "Dashboard" | ✅ |
| Monitoring | `src/veritas/monitoring/` + `docs/observability.md` | ✅ |
| Storage | `src/veritas/store/` + `docs/storage-design.md` | ✅ |
| Skills | `skills/` | 🟡 untracked |
| Documentation | `docs/` (rich) | ✅ |
| Production roadmap | README "Roadmap" + `docs/source-drift-intelligence.md` + `docs/PRODUCTION_READINESS_REVIEW.md` | 🟡 (source-drift untracked) |

**Minimal improvement:** commit the untracked files, and add one line in the README architecture section
clarifying that prompts live under `src/veritas/prompt_registry/prompts/` and evals under
`src/veritas/evals/` (so the root-vs-package divergence is intentional and stated, not a surprise).

---

## Task 5 — Broken References

| Type | Finding |
|---|---|
| Dead links **on clone** | `docs/eval-results.md`, `docs/EXECUTIVE_OVERVIEW.md`, `docs/STAKEHOLDER_FEEDBACK_INTEGRATION.md`, and all of `skills/` — linked from the committed README but untracked → **404 after clone** |
| Stale command | README §7 `python evals/run.py` — file does not exist (use `make eval` / `python -m veritas.evals`) |
| Stale path/format | README §5 `prompts/` + `semantic_accuracy.v3.txt` — actual is `src/veritas/prompt_registry/prompts/*.v1.yaml` |
| Missing images | None falsely referenced. README correctly states screenshots are generated locally and not committed; `screenshots/README.md` documents the honest capture path. ✅ |
| Cross-doc links (disk) | All internal `docs/*` ↔ `docs/*` and `screenshots/README.md` → `scripts/*` links resolve **on disk** (they break on clone only for the untracked targets). |
| Renamed/stale filenames | None detected beyond the design-narrative items above. |

---

## Task 6 — Submission Polish

| Check | Result |
|---|---|
| `TODO` / `FIXME` / `XXX` / `HACK` in deliverables | ✅ none (only legitimate hits: a test name, the `$placeholder` template mechanism, and prose saying "no placeholders") |
| `lorem ipsum` / "coming soon" | ✅ none |
| Placeholder / toy code | ✅ none — disciplined phase boundaries, no dead scaffolding |
| "future work" left in a required deliverable | ✅ acceptable — Roadmap/Phase 8 is intentional forward-looking content, not an unfinished required section |
| Duplicated documentation | 🟡 mild — solution summary, architecture, and stakeholder-feedback narratives recur across README, `EXECUTIVE_OVERVIEW.md`, `architecture-review.md`, and `STAKEHOLDER_FEEDBACK_INTEGRATION.md`. Defensible (different audiences) but a reviewer may notice overlap. |
| AI-generated artifacts | 🟡 only the prose-cadence note from Task 2; no fabricated data, no fake screenshots, no invented metrics. |

---

## Task 7 — Final Submission Score

Scored against **committed (clone) state** first, with the post-commit potential in brackets.

```
README ................. 6 / 10   [9 after committing linked files + fixing §5/§7 stale refs]
Repository Structure ... 7 / 10   [9 after committing skills/ + README path note]
Documentation .......... 8 / 10   [9 — content is strong; only tracking lets it down]
Discoverability ........ 6 / 10   [9 once skills/ is in the clone and paths are clarified]
Professionalism ........ 8 / 10   [9 — clean code, honest gaps; commit hygiene is the dent]
Reviewer Experience .... 7 / 10   [9 — Quickstart + demo seeder are excellent once files exist]

Overall Submission ..... 71 / 100   [≈ 90 / 100 after the one-commit fix + minor README edits]
```

The 19-point gap between "as it would clone today" and "after one commit" is the whole story: this is a
**high-quality submission with a packaging defect**, not a weak submission.

---

## Task 8 — Critical Fixes (ranked)

### 🔴 Critical — fix before submitting
1. **Commit the untracked deliverables.** `skills/`, `docs/eval-results.md`,
   `docs/EXECUTIVE_OVERVIEW.md`, `docs/STAKEHOLDER_FEEDBACK_INTEGRATION.md`, `docs/checks-writeup.md`,
   `docs/source-drift-intelligence.md`, `docs/DEMO_SCRIPT.md`, `docs/WEEKEND_SUBMISSION_NOTE.md`. Without
   this, the README links 404 on clone and the headline `skills/` deliverable is absent.

### 🟠 High
2. **Commit the uncommitted dashboard fixes** (`app.py`, `repositories/base.py`, `repositories/__init__.py`,
   `.streamlit/config.toml`, the `HOW_I_BUILT_THIS.md` edits). Otherwise a reviewer hits a hard crash on
   an unseeded `veritas.db` and an unwanted auto page-nav — both already fixed locally but not in the tree.
3. **Fix the stale README §7 command** `python evals/run.py` → `python -m veritas.evals` (or remove).

### 🟡 Medium
4. **Reconcile README §5 prompts path** (`prompts/` + `.v3.txt`) with the real
   `src/veritas/prompt_registry/prompts/*.v1.yaml`, or mark §1–12 explicitly as "original design spec."
5. **Add one navigation line** to the architecture section: prompts under `prompt_registry/`, evals under
   `src/veritas/evals/` — so the package-not-root layout is stated, not surprising.
6. **Update the MyPy file count** "115 files" → "116".

### 🟢 Low
7. Soften 1–2 aphorisms in `HOW_I_BUILT_THIS.md` to reduce AI-cadence signal (optional).
8. Note the intentional doc overlap, or trim the most-duplicated narrative.

---

## Executive Summary

**Is the repository submission-ready?** **Not as it would clone today — but it is one commit away.**

The engineering, documentation, and reviewer tooling are genuinely strong: a clean hexagonal
architecture, a single-`Verdict` design, replay-driven determinism, a five-minute zero-cost Quickstart, a
deterministic demo seeder, honest eval results with failure analysis, two well-formed agent skills, and a
candid build reflection. There is **no placeholder content, no fabricated data, and no fake screenshots.**
On its merits the work scores ≈ 90/100.

The blocker is **commit hygiene, not quality**: the latest commit shipped the README and a few new files
but left the headline `skills/` deliverable and several README-linked docs **untracked**, so a fresh
clone presents broken links and a missing #1 deliverable. That single fact drops the *as-cloned* score to
**71/100**.

**Recommendation:** before submitting, run one commit that adds the untracked `skills/` and `docs/*`
files plus the uncommitted dashboard fixes, then make the three small README corrections (stale
`evals/run.py` command, the `prompts/` path note, and the file-count). After that, this is a confident,
top-decile submission.

*(This audit modified no repository files other than creating this report, and committed nothing, per
instructions.)*
