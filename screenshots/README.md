# Dashboard screenshots

**No screenshot PNGs are committed to this repository — by design.** Capturing them requires a
headless browser (Playwright + Chromium) that is not part of the dependency set, and committing images
generated on one machine risks them silently drifting from the live UI. Instead, this repo gives you a
**one-command, deterministic** way to produce real screenshots yourself, plus a written description of
what each workspace shows so a reviewer can evaluate the design without running anything.

Everything below runs **offline, with no API keys and no spend** — the dashboard reads a synthetic demo
database (see [`scripts/seed_demo_db.py`](../scripts/seed_demo_db.py)).

## Capture them yourself (≈2 minutes)

```bash
# 1. Seed the deterministic demo database (fixed RNG seed → identical every run)
uv run python scripts/seed_demo_db.py

# 2a. Automated capture — installs the browser driver, writes 7 PNGs here
uv run pip install playwright && uv run playwright install chromium
DATABASE_URL="sqlite+aiosqlite:///./veritas-demo.db" \
    bash scripts/capture_dashboard_screenshots.sh

# 2b. …or capture manually — launch and screenshot each left-rail workspace
DATABASE_URL="sqlite+aiosqlite:///./veritas-demo.db" \
    uv run streamlit run src/veritas/dashboard/app.py
#    then open http://localhost:8501 and capture each of the 7 workspaces
```

The capture script ([`scripts/capture_dashboard_screenshots.sh`](../scripts/capture_dashboard_screenshots.sh))
writes `01-trust-center.png` … `07-event-detail.png` into this directory. They are git-ignored.

> **Verification without a browser:** `uv run python scripts/dashboard_render_check.py` drives all seven
> workspaces through Streamlit's `AppTest` harness and asserts each renders without raising — this is run
> as part of development and confirms the views are real, not mockups.

## What each workspace shows (example insights)

The demo data mirrors the real feed's profile (≈83% clean / 6% review / 11% quarantined, the same rule
and LLM check names, Haiku/Sonnet cost and latency bands) — so these insights are representative in
*shape*, though the absolute numbers are synthetic. Real numbers come from running the pipeline over the
feed.

| # | Workspace | What it shows | Example insight from the demo data |
|---|---|---|---|
| 1 | **Trust Center** | A transparent quality index — the formula and its inputs, not a single magic number. | "Quality index 0.86 = 83% clean, weighted down by an 11% quarantine rate; here is the arithmetic." |
| 2 | **Cost & Efficiency** | Spend by model and check, tokens, and the triage savings from the rule gate. | "Quarantined records cost \$0 — the rule gate removed 11% of traffic before any token was spent." |
| 3 | **Data Quality Intelligence** | Status mix over time, top failing reasons, category breakdown. | "`confidence_floor` and `category_known` drive most quarantines; `date_sanity` is rare." |
| 4 | **Human Review** | The ambiguous-decision queue — each item with judge verdict, confidence, reason, and evidence. | "Semantic-accuracy `uncertain` verdicts (conf 0.4–0.6) are the bulk of the queue — exactly where humans own the call." |
| 5 | **Platform Health** | Throughput, provider failure rate, latency distribution. | "Sonnet latency (~1.6s) is ≈2× Haiku (~0.9s) — the cost of escalating only the uncertain check." |
| 6 | **AI Judge Performance** | Per-check eval scorecards (P/R/F1) with honest small-sample warnings. | "Scorecards carry a small-sample banner (10–12 labels/check) — the judge is *directed*, not *certified*." |
| 7 | **Event Detail** | Drill-down: one event's full verdict stack, trace, and cost. | "Every aggregate links to a single event — its rule verdicts, LLM verdicts, trace stages, and total cost." |

The seven names above are the exact left-rail labels in
[`src/veritas/dashboard/app.py`](../src/veritas/dashboard/app.py), and they match the filenames the
capture script produces.
