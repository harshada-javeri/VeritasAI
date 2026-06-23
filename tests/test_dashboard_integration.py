"""Integration + architectural-boundary tests for the dashboard."""

from __future__ import annotations

import pickle
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

import veritas.dashboard as dashboard_pkg
from veritas.config import Settings
from veritas.dashboard.repositories import (
    CostRepository,
    EvalRepository,
    EventRepository,
    TraceRepository,
    VerdictRepository,
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
from veritas.dashboard.viewmodels.trust import TrustCenterVM

_ROOT = Path(dashboard_pkg.__file__).parent


def _sources(subdir: str) -> list[Path]:
    return [p for p in (_ROOT / subdir).glob("*.py") if p.name != "__init__.py"]


def test_no_streamlit_in_logic_layers() -> None:
    for layer in ("repositories", "services", "viewmodels"):
        for path in _sources(layer):
            assert "streamlit" not in path.read_text(), f"streamlit leaked into {path}"


def test_sql_only_in_repositories() -> None:
    for layer in ("services", "viewmodels", "pages", "components"):
        for path in _sources(layer):
            assert "sqlalchemy" not in path.read_text(), f"SQL leaked into {path}"


def test_ui_layers_use_streamlit() -> None:
    for layer in ("pages", "components"):
        for path in _sources(layer):
            assert "import streamlit" in path.read_text(), f"{path} should render via streamlit"


def test_full_pipeline_builds_every_workspace(read_sm: sessionmaker[Session]) -> None:
    events = EventRepository(read_sm)
    verdicts = VerdictRepository(read_sm)
    traces = TraceRepository(read_sm)
    cost = CostRepository(read_sm)
    settings = Settings()

    assert not TrustService(events, verdicts).build().is_empty
    assert not CostService(cost, events, settings).build().is_empty
    assert not QualityService(verdicts, events).build().is_empty
    assert not PlatformService(verdicts, traces, events).build().is_empty
    assert not JudgeService(EvalRepository(settings), verdicts).build().is_empty
    assert not ReviewService(events).build("review").is_empty
    assert EventService(events, verdicts, traces).build("e1").found


def test_viewmodels_are_picklable(read_sm: sessionmaker[Session]) -> None:
    # st.cache_data pickles return values — view-models must round-trip.
    trust = TrustService(EventRepository(read_sm), VerdictRepository(read_sm)).build()
    cost = CostService(CostRepository(read_sm), EventRepository(read_sm), Settings()).build()
    assert isinstance(pickle.loads(pickle.dumps(trust)), TrustCenterVM)
    assert isinstance(pickle.loads(pickle.dumps(cost)), CostEfficiencyVM)
