"""Empty / loading / error states — consistent across every workspace."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import streamlit as st


def empty_state(message: str, *, hint: str | None = None) -> None:
    st.info(f"**Nothing to show yet.** {message}")
    if hint:
        st.caption(hint)


def error_state(message: str) -> None:
    st.error(f"**Could not load this view.** {message}")
    st.caption("The rest of the console is unaffected — try Refresh, or another workspace.")


def note(message: str) -> None:
    st.caption(message)


@contextmanager
def loading(label: str = "Loading…") -> Iterator[None]:
    with st.spinner(label):
        yield
