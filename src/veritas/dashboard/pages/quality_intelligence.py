"""Data Quality Intelligence page — Is quality improving / what's drifting?"""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from veritas.dashboard.components import states, widgets
from veritas.dashboard.viewmodels.quality import QualityIntelligenceVM


def render(build: Callable[[], QualityIntelligenceVM]) -> None:
    widgets.workspace_header(
        "Data Quality Intelligence", "Is quality improving, and what's drifting?"
    )
    try:
        with states.loading("Reading rule outcomes…"):
            vm = build()
    except Exception as exc:
        states.error_state(str(exc))
        return

    if vm.is_empty:
        states.empty_state("No rule verdicts recorded yet.")
        return

    st.markdown("#### Rule failures (worst rate first)")
    widgets.table(
        ["rule", "fail rate", "fail", "review", "total", "baseline"],
        [
            [
                r.check_name,
                r.fail_rate_display,
                f"{r.fail:,}",
                f"{r.review:,}",
                f"{r.total:,}",
                (f"{r.baseline_rate * 100:.1f}%" if r.baseline_rate is not None else "—"),
            ]
            for r in vm.rule_stats
        ],
    )

    left, right = st.columns(2)
    with left:
        widgets.bars(
            "Event category composition",
            [(b.label, float(b.count)) for b in vm.categories[:15]],
        )
    with right:
        st.markdown("#### Rule failures by category")
        widgets.table(
            ["category", "rule", "fails"],
            [
                [c.category or "—", c.check_name, f"{c.count:,}"]
                for c in vm.failures_by_category[:20]
            ],
        )

    st.markdown("#### Judge confidence by check")
    for dist in vm.confidence_by_check:
        widgets.distribution(dist)
