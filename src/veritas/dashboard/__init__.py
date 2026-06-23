"""VeritasAI reviewer dashboard & analytics console (Phase 7, V1).

A read-only Streamlit console over the existing storage layer. Strict layering:

    repository -> service -> view-model -> component -> page

Only ``components/``, ``pages/`` and ``app`` import Streamlit. Only
``repositories/`` issue SQL. ``services/`` hold all business logic and return
frozen, ``extra="forbid"`` Pydantic view-models. V1 reads only data that exists
today (``events_clean``, ``quality_verdicts``, ``trace_logs``) plus the offline
eval harness — no V2 features (no historical-metrics, human-review workflow,
lineage, impact model, decision capture, or alert routing).
"""

from __future__ import annotations

__all__ = ["__doc__"]
