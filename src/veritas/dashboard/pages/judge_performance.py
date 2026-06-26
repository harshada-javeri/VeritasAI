"""AI Judge Performance page — Where is AI failing?"""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from veritas.dashboard.components import states, widgets
from veritas.dashboard.viewmodels.judge import JudgePerformanceVM


def render(build: Callable[[], JudgePerformanceVM]) -> None:
    widgets.workspace_header("AI Judge Performance", "Where is AI failing?")
    try:
        with states.loading("Running offline eval…"):
            vm = build()
    except Exception as exc:
        states.error_state(str(exc))
        return

    if vm.is_empty:
        states.empty_state("No eval datasets are packaged.")
        return

    st.warning(vm.data_note)

    widgets.section(
        "Judge Reliability",
        caption="How accurate each AI judge is on its labelled gold set (worst first).",
    )
    widgets.table(
        ["check", "version", "examples (n)", "accuracy", "precision", "recall", "F1", "confidence"],
        [
            [
                s.check_name,
                s.prompt_version,
                str(s.n),
                f"{s.accuracy:.2f}",
                f"{s.macro_precision:.2f}",
                f"{s.macro_recall:.2f}",
                f"{s.macro_f1:.2f}",
                ("⚠ small sample — directional only" if s.sample_warning else "ok"),
            ]
            for s in sorted(vm.scorecards, key=lambda s: s.macro_f1)
        ],
    )

    if vm.comparison is not None:
        cmp = vm.comparison
        widgets.section(
            "Prompt Comparison & Regression Status",
            caption=f"{cmp.dataset}:  {cmp.baseline_version} → {cmp.candidate_version}",
        )
        status = "🔴 Regression detected" if cmp.regressed else "🟢 No regression — safe to ship"
        (st.error if cmp.regressed else st.success)(f"**{status}.** {cmp.recommendation}")
        widgets.bars("Metric drops (baseline - candidate)", [(d.label, d.value) for d in cmp.drops])

    widgets.section(
        "Known Weaknesses",
        caption="Where the judge is confidently wrong — the most valuable thing to read.",
    )
    widgets.table(
        ["event", "category", "should be", "judge said", "confidence", "why it slipped"],
        [
            [m.event_id, m.category or "—", m.gold, m.predicted, m.confidence_display, m.reason]
            for m in vm.worst_failures
        ],
        empty_message="No misclassifications in the gold set.",
    )

    widgets.section(
        "Live verdict mix",
        caption="What the judges are deciding in production (descriptive — no ground truth).",
    )
    for mix in vm.live_verdict_mix:
        widgets.bars(mix.check_name, [(b.label, float(b.count)) for b in mix.buckets])
