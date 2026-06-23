"""Display formatters. The single place raw numbers become strings."""

from __future__ import annotations

from datetime import datetime


def money(value: float) -> str:
    if abs(value) < 0.01 and value != 0.0:
        return f"${value:.4f}"
    return f"${value:,.2f}"


def pct(fraction: float, *, digits: int = 1) -> str:
    return f"{fraction * 100:.{digits}f}%"


def count(value: int) -> str:
    return f"{value:,}"


def latency_ms(value: float | int | None) -> str:
    if value is None:
        return "—"
    return f"{round(value):,} ms"


def tokens(value: int) -> str:
    return f"{value:,} tok"


def signed(value: float, *, digits: int = 3) -> str:
    return f"{value:+.{digits}f}"


def dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%Y-%m-%d %H:%M")


def excerpt(text: str | None, *, limit: int = 120) -> str:
    if not text:
        return "—"
    return text if len(text) <= limit else text[: limit - 1] + "…"
