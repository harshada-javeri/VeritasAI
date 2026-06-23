"""Generic presentational primitives. Pages pass pre-formatted view-model fields."""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st

from veritas.dashboard.viewmodels.common import Band, DistributionVM, Sparkline

_SEVERITY_COLOR = {"trusted": "green", "caution": "orange", "blocked": "red"}
_SEVERITY_ICON = {"trusted": "🟢", "caution": "🟠", "blocked": "🔴"}


def workspace_header(title: str, question: str) -> None:
    st.subheader(title)
    st.caption(question)


def band_badge(band: Band) -> None:
    color = _SEVERITY_COLOR.get(band.severity, "gray")
    icon = _SEVERITY_ICON.get(band.severity, "•")
    st.markdown(f"{icon} :{color}[**{band.severity.upper()}**] — {band.reason}")


def metric(label: str, display: str, *, help_text: str | None = None) -> None:
    st.metric(label, display, help=help_text)


def metric_grid(items: Sequence[tuple[str, str]]) -> None:
    if not items:
        return
    columns = st.columns(len(items))
    for column, (label, display) in zip(columns, items, strict=True):
        with column:
            st.metric(label, display)


def sparkline(label: str, spark: Sparkline) -> None:
    st.caption(label)
    if spark.is_empty:
        st.caption("— no trend yet —")
        return
    st.line_chart(list(spark.points), height=120)


def distribution(dist: DistributionVM) -> None:
    st.caption(dist.label)
    if dist.is_empty:
        st.caption("— no measurements —")
        return
    data = {f"{b.lower:.1f}-{b.upper:.1f}": b.count for b in dist.bins}
    st.bar_chart(data, height=160)


def bars(label: str, pairs: Sequence[tuple[str, float]]) -> None:
    st.caption(label)
    if not pairs:
        st.caption("— none —")
        return
    st.bar_chart(dict(pairs), height=200)


def table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    if not rows:
        st.caption("— no rows —")
        return
    st.dataframe(
        [dict(zip(headers, row, strict=True)) for row in rows],
        use_container_width=True,
        hide_index=True,
    )
