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

    widgets.band_badge(vm.banner)
    widgets.metric_grid(
        [(b.label, f"{b.count:,} ({b.rate * 100:.0f}%)") for b in vm.status_composition]
    )

    if vm.data_quality_index is not None:
        idx = vm.data_quality_index
        widgets.metric("Data Quality Index (0-100)", idx.display, help_text=idx.formula_label)
        widgets.table(
            ["component", "rate x weight = contribution"],
            [[c.name, c.display] for c in idx.components],
        )

    left, right = st.columns(2)
    with left:
        widgets.metric(vm.duplicate.label, f"{vm.duplicate.display} {vm.duplicate.unit}")
        if vm.duplicate.spark is not None:
            widgets.sparkline("Duplicate trend", vm.duplicate.spark)
    with right:
        widgets.metric(vm.integrity.label, vm.integrity.display)
        if vm.integrity.spark is not None:
            widgets.sparkline("Integrity review trend", vm.integrity.spark)

    widgets.distribution(vm.judge_confidence)

    st.markdown("#### What is driving non-clean status")
    widgets.table(
        ["check", "verdict", "count", "share"],
        [
            [d.check_name, d.verdict, f"{d.count:,}", f"{d.share * 100:.0f}%"]
            for d in vm.drivers
        ],
    )
