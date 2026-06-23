"""Streamlit pages — UI only.

Each page receives a builder callable that returns a view-model, owns its
loading/empty/error states, and renders via components. No SQL, no business
logic, no formatting here.
"""

from __future__ import annotations
