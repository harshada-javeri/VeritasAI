# VeritasAI — Data Quality Findings

*Empirical profile of the in-repo feed, run against all 24 shards (~2.5 GB).*
*Date: 2026-06-22 · Source: `scripts/profile_dataset.py` + ad-hoc analysis passes.*

These findings supersede the illustrative numbers in `README.md` §2 where they
differ. They directly shape the Phase 1 rule set: every rule below is justified
by a measured number, not an assumption.

**Headline:** **620,785 events** across **24 `.jsonl` files**, **612,910
distinct event IDs**. The feed is *structurally pristine* — **0 JSON parse
errors, 0 dangling relationship references, `most_relevant_source` present on
100%** — so data-quality work is about *semantics and conditional content*, not
broken structure.

---

## 1. Duplicate ID analysis

| Metric | Value |
|---|---|
| Total events | 620,785 |
| Distinct event IDs | 612,910 |
| Duplicate IDs | **7,875** (1.27% of events) |
| Duplicate occurrences with **identical** `(category, found_at, company1)` | **7,875 (100%)** |
| Duplicate occurrences with **conflicting** content | **0** |
| Occurring **across different shard files** | 7,576 (96.2%) |
| Occurring **within the same file** | 299 (3.8%) |

**Interpretation.** README §2 claimed "**0 duplicate event IDs**." That is
false for this feed — but the duplicates are **benign exact re-emissions**: the
same event re-appears (overwhelmingly across shards), never two *different*
events colliding on one ID. There is no ID-integrity crisis; there is a
**dedup** requirement.

**Implications for rules / pipeline.**
- A deterministic **exact-duplicate rule** keyed on `event_id` is safe and
  cheap: first occurrence wins, subsequent ones are flagged `duplicate` and
  quarantined — **no LLM spend on repeats**.
- The verdict idempotency key `(event_id, check_name, prompt_version)` already
  makes re-runs safe; dedup additionally avoids *re-judging* the ~1.3% repeats.
- Because duplicates span shards, dedup must be **global**, not per-file — a
  seen-set (or a DB unique constraint) at ingest, not a within-file check.

---

## 2. Category distribution analysis

29 distinct categories (README estimated "~40+"). Heavily head-concentrated:
the top 3 are **63%** of the feed.

| Category | Count | Share |
|---|---:|---:|
| launches | 199,986 | 32.22% |
| partners_with | 124,175 | 20.00% |
| hires | 65,431 | 10.54% |
| invests_into | 26,196 | 4.22% |
| recognized_as | 25,103 | 4.04% |
| is_developing | 20,850 | 3.36% |
| receives_award | 18,985 | 3.06% |
| acquires | 18,726 | 3.02% |
| invests_into_assets | 14,405 | 2.32% |
| has_issues_with | 12,501 | 2.01% |
| *(18 more, each <2%)* | … | … |
| identified_as_competitor_of | 3,815 | 0.61% |
| files_suit_against | 2,185 | 0.35% |
| goes_public | 1,304 | 0.21% |
| merges_with | 1,235 | 0.20% |

**Interpretation & implications.**
- The category enum rule should be seeded from this **observed set of 29**;
  anything outside it is a true novelty worth routing to review.
- The **long tail is the LLM-judge risk zone** (README §11). Categories like
  `merges_with`, `goes_public`, `identified_as_competitor_of` have thin signal;
  evals must **deliberately oversample** them rather than sampling uniformly, or
  judge accuracy on them goes unmeasured.
- Head categories (`launches`, `partners_with`) dominate cost — optimizing the
  cheap-rule pass and Haiku prompt for *these two* moves the cost needle most.

---

## 3. Confidence score distribution analysis

`confidence` ∈ [0.0, 1.0], **mean 0.603** (README said 0.64), 0 unparseable.

| Bucket | Count |
|---|---:|
| 0.0–0.1 | 46,260 |
| 0.1–0.2 | 20,099 |
| 0.2–0.3 | 26,027 |
| 0.3–0.4 | 38,416 |
| 0.4–0.5 | 56,030 |
| 0.5–0.6 | 81,083 |
| 0.6–0.7 | 100,670 |
| 0.7–0.8 | 98,308 |
| 0.8–0.9 | 67,055 |
| 0.9–1.0 | 86,829 |

**The 0.0 spike is real and concentrated.** Exactly **29,032 events have
`confidence == 0.0`** (4.7% of the feed) — they sit inside the 0.0–0.1 bucket
(46,260) and account for most of it. The spike is not uniform across categories:

| Category | conf==0.0 | as % of that category |
|---|---:|---:|
| attends_event | 1,286 | 12.2% |
| acquires | 1,558 | 8.3% |
| partners_with | 8,933 | 7.2% |
| invests_into_assets | 997 | ~6.9% |
| launches | 5,199 | 2.6% |
| hires | 2,386 | 3.6% |

**Interpretation & implications.**
- `confidence == 0.0` behaves as a **"no real signal" sentinel**, not a smooth
  low score — exactly the README example (`conf=0.0 partners_with`). A
  **confidence-floor rule** (`< 0.15` → auto-quarantine) cleanly removes these
  before any token is spent. At the configured floor of **0.15**, roughly
  **66K events (≈10.7%)** quarantine deterministically.
- The bulk of mass (0.5–0.8) is the **ambiguous middle** — precisely where the
  LLM judges earn their keep. Rules cannot adjudicate these.
- Because the 0.0 spike skews by category, the floor rule should be reported
  *per category* in the dashboard, or a genuinely-low-confidence niche category
  could be silently over-quarantined.

---

## 4. Conditional field sparsity analysis

The 29 attribute keys are **conditional, not broken** — each category populates
its own fields. "Missing" is only a defect when the category *implies* the
field. Present-rates for the diagnostic field of each major category:

| Category | n | Expected field(s) | Present rate |
|---|---:|---|---:|
| receives_financing | 9,540 | `amount_normalized`, `financing_type` | **100%**, 80.9% |
| is_developing | 20,850 | `product` | **100%** |
| launches | 199,986 | `product` | **100%** |
| receives_award | 18,985 | `award` | **100%** |
| recognized_as | 25,103 | `recognition` | **100%** |
| hires | 65,431 | `job_title` | **85.8%** |
| invests_into | 26,196 | `amount_normalized` | 53.5% |
| acquires | 18,726 | `amount_normalized` | 26.9% |
| partners_with | 124,175 | *(none specific)* | `location_data` 27.1% |

### Critical sub-finding: `amount` is free-text; `amount_normalized` is numeric

`amount` is **human-formatted text** — `"$1m"`, `"$6 million"`, `"$1.2
billion"`, `"$155,000"`. `amount_normalized` is the parsed integer (`1000000`,
`6000000`, …). Both are present on **100%** of `receives_financing` events.

This corrects the earlier profiler reading of "amount present 0.8%": that number
came from `ResolvedEvent.amount`, whose `_to_float` coercion strips `$`/`,` but
**cannot parse `"1m"`/`"million"`/`"billion"`**, so it returns `None` for ~85%
of financing amounts. The sparsity was a **coercion artifact, not real**.

**Implications.**
- The **conditional-completeness rule must read `amount_normalized`** (the
  numeric signal), never the top-level coerced `amount`.
- **Recommendation (parser tweak, deferred):** promote `amount_normalized` as
  the numeric money field on `ResolvedEvent`, and treat `amount` as the raw
  display string. Tracked for a follow-up; **no Phase 1 code depends on the
  coerced `amount`** — rules will read `attributes["amount_normalized"]`.
- The completeness rule is a **per-category map**, not a blanket "amount should
  be non-null." Acquisitions and generic investments legitimately lack a normalized
  amount ~50–73% of the time, so for those categories a missing amount is
  `review`/informational, **not** a hard fail; financing/award/product/recognition
  categories are the ones where a missing expected field is a genuine defect.

---

## 5. README assumptions vs. actual dataset

| Topic | README §2 assumption | Actual | Verdict |
|---|---|---|---|
| Volume | 310,710 records / 12 files | **620,785 / 24 files** | ~2× larger; rescale cost math ~1.7–2× |
| Categories | "~40+" | **29 distinct** | Fewer; enum seeded from observed 29 |
| Confidence mean | 0.64 | **0.603** | Close; 0.0 spike confirmed (29,032) |
| Date span | 2010–2025 | **2010–2025**, 0 unparseable | Confirmed |
| company1 / company2 / source | ~97% / ~35% / 100% | **97.6% / 33.6% / 100%** | Confirmed |
| Duplicate event IDs | **0** | **7,875** (all benign exact repeats) | **Wrong** — dedup required |
| `amount` sparsity | "~95% null, applies to financing/acq" | `amount`/`amount_normalized` **100%** on financing; **free-text vs numeric** split | **Mischaracterized** — use `amount_normalized` |
| Company name key | `name` | **`company_name`** | Drift; parser reads `company_name` (fixed in Phase 0) |
| Article fields | title/body/url/published_at | + `author`, `image_url` | Extra keys, retained in `attributes` |
| Structural integrity | (implied messy) | **0 parse errors, 0 dangling refs** | Cleaner than assumed |

### Net effect on Phase 1 rule design

1. **Exact-duplicate rule** — global, `event_id`-keyed, first-wins (1.27% of feed).
2. **Confidence-floor rule** — `< 0.15` → quarantine (~10.7% of feed); report per category.
3. **Category-enum rule** — seed from the observed 29; flag novelties for review.
4. **Conditional-completeness rule** — per-category expected-field map, reading
   `amount_normalized` not `amount`; missing-amount is `review` for acquires/invests,
   `fail` for financing/award/product/recognition.
5. **Date-sanity rule** — `found_at` ≤ now, ≥ `min_event_year` (2000); the
   2010–2025 span means stale-resurfacing is the live freshness risk (LLM, later).
6. **Referential-integrity rule** — cheap insurance; the current feed is 100%
   clean, but the rule guards against future shards that are not.
