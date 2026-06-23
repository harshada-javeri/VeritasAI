"""Presentational components — pure render functions of view-models.

The only layer besides ``pages`` and ``app`` that imports Streamlit. Components
contain no data access and no business logic; they map already-computed,
already-formatted view-model fields onto Streamlit primitives.
"""

from __future__ import annotations
