"""Frozen, display-ready view-models — the repository/UI contract.

Every model is ``frozen=True, extra="forbid"``. View-models carry pre-computed,
pre-formatted, pre-ranked data: pages and components render them verbatim and
never compute. Collections are tuples so the models are deeply immutable.
"""

from __future__ import annotations
