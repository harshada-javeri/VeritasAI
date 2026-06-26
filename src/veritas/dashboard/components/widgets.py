"""Generic presentational primitives. Pages pass pre-formatted view-model fields."""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st

from veritas.dashboard.viewmodels.common import Band, DistributionVM, Sparkline

_SEVERITY_COLOR = {"trusted": "green", "caution": "orange", "blocked": "red"}
_SEVERITY_ICON = {"trusted": "🟢", "caution": "🟠", "blocked": "🔴"}
# Hex equivalents for inline-styled hero/cards (read cleanly on the dark theme).
_SEVERITY_HEX = {"trusted": "#16a34a", "caution": "#d97706", "blocked": "#dc2626"}
_SEVERITY_WORD = {"trusted": "TRUSTED", "caution": "CAUTION", "blocked": "BLOCKED"}


def workspace_header(title: str, question: str) -> None:
    st.subheader(title)
    st.caption(question)


def section(title: str, *, caption: str | None = None) -> None:
    """Consistent section header (replaces ad-hoc markdown ####)."""
    st.markdown(f"#### {title}")
    if caption:
        st.caption(caption)


def band_badge(band: Band) -> None:
    color = _SEVERITY_COLOR.get(band.severity, "gray")
    icon = _SEVERITY_ICON.get(band.severity, "•")
    st.markdown(f"{icon} :{color}[**{band.severity.upper()}**] — {band.reason}")


def hero_score(
    *,
    title: str,
    score_display: str,
    scale: str,
    band: Band,
    explanation: str,
) -> None:
    """The single focal point of a workspace: one big number + health badge.

    Inline styles only (no ``<style>`` block) so there are no curly braces to
    escape and the card renders identically wherever it is dropped.
    """
    color = _SEVERITY_HEX.get(band.severity, "#64748b")
    word = _SEVERITY_WORD.get(band.severity, band.severity.upper())
    st.markdown(
        f'<div style="padding:1.1rem 1.4rem;border:1px solid rgba(148,163,184,0.18);'
        f"border-left:6px solid {color};border-radius:14px;"
        f'background:rgba(148,163,184,0.05);margin-bottom:0.5rem;">'
        f'<div style="font-size:0.78rem;letter-spacing:0.10em;text-transform:uppercase;'
        f'color:#94a3b8;font-weight:600;">{title}</div>'
        f'<div style="display:flex;align-items:baseline;gap:0.7rem;margin:0.15rem 0 0.35rem;">'
        f'<span style="font-size:3.6rem;font-weight:800;line-height:1;color:{color};">'
        f"{score_display}</span>"
        f'<span style="font-size:1rem;color:#64748b;">{scale}</span>'
        f'<span style="margin-left:auto;background:{color};color:#0b0f19;font-weight:700;'
        f'padding:0.3rem 0.85rem;border-radius:999px;font-size:0.85rem;'
        f'letter-spacing:0.04em;">{word}</span></div>'
        f'<div style="color:#cbd5e1;font-size:0.95rem;line-height:1.4;">{explanation}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def summary_cards(items: Sequence[tuple[str, str, str]]) -> None:
    """A row of executive emphasis cards: (label, big value, sub-caption)."""
    if not items:
        return
    for column, (label, value, sub) in zip(st.columns(len(items)), items, strict=True):
        with column:
            st.markdown(
                f'<div style="padding:0.85rem 1rem;border:1px solid rgba(148,163,184,0.18);'
                f'border-radius:12px;background:rgba(148,163,184,0.04);height:100%;">'
                f'<div style="font-size:0.72rem;letter-spacing:0.07em;text-transform:uppercase;'
                f'color:#94a3b8;font-weight:600;">{label}</div>'
                f'<div style="font-size:1.35rem;font-weight:700;color:#f1f5f9;'
                f'margin:0.2rem 0 0.1rem;">{value}</div>'
                f'<div style="font-size:0.82rem;color:#94a3b8;">{sub}</div></div>',
                unsafe_allow_html=True,
            )


def metric(label: str, display: str, *, help_text: str | None = None) -> None:
    st.metric(label, display, help=help_text)


def metric_grid(items: Sequence[tuple[str, str]]) -> None:
    if not items:
        return
    columns = st.columns(len(items))
    for column, (label, display) in zip(columns, items, strict=True):
        with column:
            st.metric(label, display)


def sparkline(label: str, spark: Sparkline, *, empty_message: str = "— no trend yet —") -> None:
    st.caption(label)
    if spark.is_empty or len(spark.points) < 2:
        st.caption(empty_message)
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


def table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    empty_message: str = "— no rows —",
) -> None:
    if not rows:
        st.caption(empty_message)
        return
    st.dataframe(
        [dict(zip(headers, row, strict=True)) for row in rows],
        width="stretch",
        hide_index=True,
    )
