"""Business logic — composition, derivation, ranking, formatting.

Services consume repositories and return frozen view-models. They never issue
SQL and never import Streamlit. All thresholds, weights, percentile math, and
unit formatting live here (or in ``scoring``/``formatting``).
"""

from __future__ import annotations

from veritas.dashboard.services.cost_service import CostService
from veritas.dashboard.services.event_service import EventService
from veritas.dashboard.services.judge_service import JudgeService
from veritas.dashboard.services.platform_service import PlatformService
from veritas.dashboard.services.quality_service import QualityService
from veritas.dashboard.services.review_service import ReviewService
from veritas.dashboard.services.trust_service import TrustService

__all__ = [
    "CostService",
    "EventService",
    "JudgeService",
    "PlatformService",
    "QualityService",
    "ReviewService",
    "TrustService",
]
