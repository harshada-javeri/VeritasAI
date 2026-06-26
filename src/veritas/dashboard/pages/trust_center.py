"""Trust Center page — Can we trust today's data?"""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from veritas.dashboard.components import states, widgets
from veritas.dashboard.viewmodels.trust import TrustCenterVM


def render(build: Callable[[], TrustCenterVM]) -> None:
    widgets.workspace_header("Trust Center", "Can we trust today's data?")
    try:
        with states.loading("Scoring trust…"):
            vm = build()
    except Exception as exc:
        states.error_state(str(exc))
        return

    if vm.is_empty:
        states.empty_state("No events have been processed yet.", hint="Run the pipeline first.")
        return

    # --- Hero: the trust score is the focal point (read in <10 seconds) -------
    score_display = vm.data_quality_index.display if vm.data_quality_index else "—"
    widgets.hero_score(
        title="Trust Score — Data Quality Index",
        score_display=score_display,
        scale="/ 100",
        band=vm.banner,
        explanation=vm.headline,
    )

    # --- Current status at a glance ------------------------------------------
    widgets.metric_grid(
        [(b.label, f"{b.count:,} ({b.rate * 100:.0f}%)") for b in vm.status_composition]
    )

    left, right = st.columns([3, 2])
    with left:
        if vm.data_quality_index is not None:
            idx = vm.data_quality_index
            widgets.section("How the score is built", caption=idx.formula_label)
            widgets.table(
                ["driver", "rate x weight = contribution"],
                [[c.name, c.display] for c in idx.components],
            )
        widgets.section("What is driving non-clean status")
        widgets.table(
            ["check", "verdict", "count", "share"],
            [
                [d.check_name, d.verdict, f"{d.count:,}", f"{d.share * 100:.0f}%"]
                for d in vm.drivers
            ],
            empty_message="No non-clean verdicts — every check passed.",
        )
    with right:
        widgets.section("Integrity & duplicates")
        widgets.metric(vm.duplicate.label, f"{vm.duplicate.display} {vm.duplicate.unit}")
        widgets.metric(vm.integrity.label, vm.integrity.display)
        widgets.distribution(vm.judge_confidence)
