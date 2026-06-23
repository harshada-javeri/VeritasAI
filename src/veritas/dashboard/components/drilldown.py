"""Renders the Event Detail object view."""

from __future__ import annotations

import streamlit as st

from veritas.dashboard.components import states, widgets
from veritas.dashboard.viewmodels.event_detail import EventDetailVM


def render_event_detail(vm: EventDetailVM) -> None:
    if not vm.found or vm.header is None:
        states.empty_state(
            f"No event found for id `{vm.event_id}`.",
            hint="Check the id, or open one from a queue or ranked table.",
        )
        return

    header = vm.header
    widgets.band_badge(header.status_band)
    st.markdown(f"### `{header.event_id}`")
    widgets.metric_grid(
        [
            ("Status", header.status),
            ("Category", header.category or "—"),
            ("Found at", header.found_at_display),
            ("Cost", vm.cost_summary.display if vm.cost_summary else "—"),
        ]
    )
    if header.summary:
        st.write(header.summary)
    st.caption(f"company1: {header.company1_id or '—'} · company2: {header.company2_id or '—'}")

    st.markdown("#### Verdict stack")
    widgets.table(
        ["check", "type", "verdict", "confidence", "model", "prompt", "cost", "latency", "reason"],
        [
            [
                v.check_name,
                v.check_type,
                v.status,
                v.confidence_display,
                v.model,
                v.prompt_version,
                v.cost_display,
                v.latency_display,
                v.reason,
            ]
            for v in vm.verdicts
        ],
    )

    st.markdown("#### Trace timeline")
    widgets.table(
        ["stage", "trace_id", "payload_hash", "at"],
        [[t.stage, t.trace_id, t.payload_hash, t.created_at_display] for t in vm.trace],
    )
