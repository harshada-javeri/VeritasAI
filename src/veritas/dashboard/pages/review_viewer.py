"""Review Viewer page — What requires human intervention? (read-only viewer)."""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from veritas.dashboard.components import states, widgets
from veritas.dashboard.viewmodels.review import ReviewQueueVM

_ORDER_OPTIONS = {"Lowest judge confidence": "confidence", "Most recent": "recent"}


def render(build: Callable[[str, str], ReviewQueueVM]) -> None:
    widgets.workspace_header(
        "Human Review Queue", "The ambiguous decisions a human owns — not the machine."
    )
    st.info(
        "**Humans own ambiguous decisions.** The system never silently passes an uncertain "
        "record: rules gate, LLM judges escalate, and anything they can't settle lands here for "
        "a person to decide. This is the product's backstop, by design."
    )

    left, right = st.columns(2)
    with left:
        status = st.selectbox("Queue", ["review", "quarantine"], key="review::status")
    with right:
        order_label = st.selectbox("Order by", list(_ORDER_OPTIONS), key="review::order")
    order_by = _ORDER_OPTIONS[order_label]

    try:
        with states.loading("Loading queue…"):
            vm = build(status, order_by)
    except Exception as exc:
        states.error_state(str(exc))
        return

    if vm.is_empty:
        states.empty_state(f"The {status} queue is empty.")
        return

    st.caption(f"Showing {vm.total_shown} items — {vm.order_label}.")
    widgets.table(
        ["event", "category", "confidence", "found at", "summary"],
        [
            [
                i.event_id,
                i.category or "—",
                i.confidence_display,
                i.found_at_display,
                i.summary_excerpt,
            ]
            for i in vm.items
        ],
    )
    st.info(vm.sort_note)
    states.note("This is a read-only viewer. Assignment, SLA, and decision capture are V2.")
