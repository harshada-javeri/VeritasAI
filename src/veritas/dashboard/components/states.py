"""Empty / loading / error states — consistent across every workspace."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import streamlit as st


def empty_state(message: str, *, hint: str | None = None) -> None:
    st.info(f"**Nothing to show yet.** {message}")
    if hint:
        st.caption(hint)


def future_capability(
    *,
    title: str,
    summary: str,
    unlocks: Sequence[str],
    activates_when: str,
) -> None:
    """A clearly-labelled card for a capability that is real in design but not yet
    backed by ingested data. It never shows fabricated numbers — it states exactly
    what becomes available and the single data condition that switches it on.
    """
    st.markdown(
        f'<div style="padding:1rem 1.25rem;border:1px dashed rgba(148,163,184,0.35);'
        f'border-radius:12px;background:rgba(148,163,184,0.04);">'
        f'<div style="display:flex;align-items:center;gap:0.5rem;">'
        f'<span style="font-size:0.7rem;font-weight:700;letter-spacing:0.06em;'
        f"background:#334155;color:#e2e8f0;padding:0.2rem 0.6rem;border-radius:999px;"
        f'text-transform:uppercase;">Future capability</span>'
        f'<span style="font-weight:700;color:#f1f5f9;font-size:1.02rem;">{title}</span></div>'
        f'<div style="color:#cbd5e1;font-size:0.93rem;margin:0.5rem 0 0.2rem;line-height:1.45;">'
        f"{summary}</div></div>",
        unsafe_allow_html=True,
    )
    if unlocks:
        st.markdown("**What it will answer:**\n" + "\n".join(f"- {item}" for item in unlocks))
    st.caption("**Activates automatically when:** " + activates_when)


def error_state(message: str) -> None:
    st.error(f"**Could not load this view.** {message}")
    st.caption("The rest of the console is unaffected — try Refresh, or another workspace.")


def note(message: str) -> None:
    st.caption(message)


@contextmanager
def loading(label: str = "Loading…") -> Iterator[None]:
    with st.spinner(label):
        yield
