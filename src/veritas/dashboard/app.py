"""Composition root for the VeritasAI Decision Intelligence Console.

Wires the dedicated read-only engine -> repositories -> services -> pages, owns
caching and the left-rail navigation. The engine is created once
(``cache_resource``); view-models are cached keyed by a coarse data-version token
so a new pipeline run busts the cache, and the Refresh button clears it.

Run with:  ``uv run streamlit run src/veritas/dashboard/app.py``
"""

from __future__ import annotations

import streamlit as st

from veritas.config import Settings, get_settings
from veritas.dashboard.pages import (
    cost_efficiency,
    event_detail,
    judge_performance,
    platform_health,
    quality_intelligence,
    review_viewer,
    trust_center,
)
from veritas.dashboard.repositories import (
    CostRepository,
    EvalRepository,
    EventRepository,
    MetaRepository,
    TraceRepository,
    VerdictRepository,
    build_read_sessionmaker,
    create_read_engine,
    ensure_schema,
)
from veritas.dashboard.services import (
    CostService,
    EventService,
    JudgeService,
    PlatformService,
    QualityService,
    ReviewService,
    TrustService,
)
from veritas.dashboard.viewmodels.cost import CostEfficiencyVM
from veritas.dashboard.viewmodels.event_detail import EventDetailVM
from veritas.dashboard.viewmodels.judge import JudgePerformanceVM
from veritas.dashboard.viewmodels.platform import PlatformHealthVM
from veritas.dashboard.viewmodels.quality import QualityIntelligenceVM
from veritas.dashboard.viewmodels.review import ReviewQueueVM
from veritas.dashboard.viewmodels.trust import TrustCenterVM


class Console:
    """Holds the read engine and the fully-wired service layer."""

    def __init__(self, settings: Settings) -> None:
        engine = create_read_engine(settings.database_url)
        ensure_schema(engine)  # materialize empty tables so an unseeded DB renders, not crashes
        sm = build_read_sessionmaker(engine)
        events = EventRepository(sm)
        verdicts = VerdictRepository(sm)
        traces = TraceRepository(sm)
        cost = CostRepository(sm)
        evals = EvalRepository(settings)

        self.meta = MetaRepository(sm)
        self.trust = TrustService(events, verdicts)
        self.cost = CostService(cost, events, settings)
        self.quality = QualityService(verdicts, events)
        self.platform = PlatformService(verdicts, traces, events)
        self.judge = JudgeService(evals, verdicts)
        self.review = ReviewService(events)
        self.event = EventService(events, verdicts, traces)


@st.cache_resource
def get_console() -> Console:
    return Console(get_settings())


def data_version() -> str:
    return get_console().meta.data_version()


@st.cache_data
def vm_trust(_dv: str) -> TrustCenterVM:
    return get_console().trust.build()


@st.cache_data
def vm_cost(_dv: str) -> CostEfficiencyVM:
    return get_console().cost.build()


@st.cache_data
def vm_quality(_dv: str) -> QualityIntelligenceVM:
    return get_console().quality.build()


@st.cache_data
def vm_platform(_dv: str) -> PlatformHealthVM:
    return get_console().platform.build()


@st.cache_data
def vm_judge(_dv: str) -> JudgePerformanceVM:
    return get_console().judge.build()


@st.cache_data
def vm_event(_dv: str, event_id: str) -> EventDetailVM:
    return get_console().event.build(event_id)


@st.cache_data
def vm_review(_dv: str, status: str, order: str) -> ReviewQueueVM:
    return get_console().review.build(status, order_by=order)


_WORKSPACES = (
    "Trust Center",
    "Cost & Efficiency",
    "Data Quality Intelligence",
    "Human Review Queue",
    "Platform Health",
    "AI Judge Performance",
    "Event Detail",
)


def main() -> None:
    st.set_page_config(
        page_title="VeritasAI — Decision Intelligence Console",
        page_icon="🛡️",
        layout="wide",
    )
    st.sidebar.title("🛡️ VeritasAI")
    st.sidebar.caption("Decision Intelligence Console · V1")
    if st.sidebar.button("↻ Refresh data"):
        st.cache_data.clear()
    choice = st.sidebar.radio("Workspace", _WORKSPACES)
    st.sidebar.caption(f"data version: {data_version()[:19] or 'empty'}")

    dv = data_version()
    if choice == "Trust Center":
        trust_center.render(lambda: vm_trust(dv))
    elif choice == "Cost & Efficiency":
        cost_efficiency.render(lambda: vm_cost(dv))
    elif choice == "Data Quality Intelligence":
        quality_intelligence.render(lambda: vm_quality(dv))
    elif choice == "Human Review Queue":
        review_viewer.render(lambda status, order: vm_review(dv, status, order))
    elif choice == "Platform Health":
        platform_health.render(lambda: vm_platform(dv))
    elif choice == "AI Judge Performance":
        judge_performance.render(lambda: vm_judge(dv))
    elif choice == "Event Detail":
        event_detail.render(lambda event_id: vm_event(dv, event_id))


if __name__ == "__main__":
    main()
