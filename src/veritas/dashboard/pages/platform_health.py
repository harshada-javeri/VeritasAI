"""Platform Health page — Is the platform healthy?"""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from veritas.dashboard.components import states, widgets
from veritas.dashboard.viewmodels.platform import PlatformHealthVM


def render(build: Callable[[], PlatformHealthVM]) -> None:
    widgets.workspace_header("Platform Health", "Is the platform healthy?")
    try:
        with states.loading("Reading telemetry…"):
            vm = build()
    except Exception as exc:
        states.error_state(str(exc))
        return

    if vm.is_empty:
        states.empty_state("No processing telemetry recorded yet.")
        return

    st.markdown("#### LLM latency by model")
    widgets.table(
        ["model", "p50", "p90", "p99", "samples"],
        [
            [m.model, f"{m.p50_ms:,} ms", f"{m.p90_ms:,} ms", f"{m.p99_ms:,} ms", f"{m.count:,}"]
            for m in vm.latency
        ],
    )

    left, right = st.columns(2)
    with left:
        widgets.sparkline("LLM latency p90 trend (ms)", vm.latency_trend)
    with right:
        widgets.sparkline("Processing throughput (per day)", vm.throughput)

    widgets.metric_grid([(t.table, f"{t.rows:,} rows") for t in vm.storage])
    widgets.bars("Trace volume by stage", [(b.label, float(b.count)) for b in vm.stage_volume])

    states.note(vm.unavailable_note)
