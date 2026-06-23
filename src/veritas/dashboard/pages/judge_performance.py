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

    st.markdown("#### Scorecards (worst F1 first)")
    widgets.table(
        ["check", "version", "n", "accuracy", "macro P", "macro R", "macro F1", "sample"],
        [
            [
                s.check_name,
                s.prompt_version,
                str(s.n),
                f"{s.accuracy:.2f}",
                f"{s.macro_precision:.2f}",
                f"{s.macro_recall:.2f}",
                f"{s.macro_f1:.2f}",
                ("⚠ small-n" if s.sample_warning else "ok"),
            ]
            for s in sorted(vm.scorecards, key=lambda s: s.macro_f1)
        ],
    )

    if vm.comparison is not None:
        cmp = vm.comparison
        st.markdown(f"#### Prompt comparison — {cmp.dataset}")
        st.caption(f"{cmp.baseline_version} → {cmp.candidate_version}")
        widgets.bars("Metric drops (baseline - candidate)", [(d.label, d.value) for d in cmp.drops])
        (st.error if cmp.regressed else st.success)(cmp.recommendation)

    st.markdown("#### Worst failures (confidently wrong first)")
    widgets.table(
        ["event", "category", "gold", "predicted", "confidence", "reason"],
        [
            [m.event_id, m.category or "—", m.gold, m.predicted, m.confidence_display, m.reason]
            for m in vm.worst_failures
        ],
    )

    st.markdown("#### Live verdict mix (descriptive, not accuracy)")
    for mix in vm.live_verdict_mix:
        widgets.bars(mix.check_name, [(b.label, float(b.count)) for b in mix.buckets])
