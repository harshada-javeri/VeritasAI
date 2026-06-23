"""Cost & Efficiency page — What is costing money?"""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from veritas.dashboard.components import states, widgets
from veritas.dashboard.viewmodels.cost import CostEfficiencyVM


def render(build: Callable[[], CostEfficiencyVM]) -> None:
    widgets.workspace_header("Cost & Efficiency", "What is costing money?")
    try:
        with states.loading("Tallying spend…"):
            vm = build()
    except Exception as exc:
        states.error_state(str(exc))
        return

    if vm.is_empty:
        states.empty_state("No verdicts recorded yet — nothing has cost anything.")
        return

    widgets.band_badge(vm.budget.band)
    widgets.metric_grid(
        [
            ("Total spend", vm.total_spend.display),
            (vm.cost_per_1k_events.label, vm.cost_per_1k_events.display),
            ("Budget", vm.budget.display),
            ("Escalation rate", vm.escalation_rate.display),
        ]
    )
    st.info(vm.efficiency_statement)
    states.note(f"Escalation: {vm.escalation_rate.note}")

    left, right = st.columns(2)
    with left:
        st.markdown("#### Cost per verdict, by model")
        widgets.table(
            ["model", "verdicts", "total", "avg"],
            [
                [m.model, f"{m.count:,}", m.total_display, m.avg_display]
                for m in vm.cost_per_verdict
            ],
        )
        st.markdown("#### Cost by check")
        widgets.table(
            ["check", "total"],
            [[c.check_name, c.total_display] for c in vm.cost_by_check],
        )
    with right:
        st.markdown("#### Cost by prompt version")
        widgets.table(
            ["prompt", "total", "avg input tok", "verdicts"],
            [
                [p.prompt_version, p.total_display, f"{p.avg_input_tokens:,}", f"{p.count:,}"]
                for p in vm.cost_by_prompt
            ],
        )
        widgets.metric("Tokens", vm.tokens.display)

    widgets.sparkline("Spend trend", vm.spend_trend)
