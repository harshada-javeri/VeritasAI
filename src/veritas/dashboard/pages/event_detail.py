"""Event Detail page — the drill-down object spine."""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from veritas.dashboard.components import drilldown, states, widgets
from veritas.dashboard.viewmodels.event_detail import EventDetailVM

_SELECTED_KEY = "selected_event_id"


def render(build: Callable[[str], EventDetailVM]) -> None:
    widgets.workspace_header("Event Detail", "The full evidence for one event.")

    default = st.session_state.get(_SELECTED_KEY, "")
    event_id = st.text_input("Event id", value=default, key="event_detail::id").strip()
    if not event_id:
        states.empty_state(
            "Enter an event id, or open one from a queue or ranked table.",
            hint="Every aggregate in the console links here.",
        )
        return

    try:
        with states.loading("Loading event…"):
            vm = build(event_id)
    except Exception as exc:
        states.error_state(str(exc))
        return

    drilldown.render_event_detail(vm)
