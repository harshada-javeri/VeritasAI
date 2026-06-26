"""The dedicated synchronous, read-only engine + session factory.

The pipeline's store is async (``aiosqlite``/``asyncpg``); Streamlit is sync and
re-runs top to bottom on every interaction. Bridging async per-rerun is fragile,
so the dashboard gets its own *sync* engine over the same database URL. It is
read-only by construction — no repository here opens a write transaction.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from veritas.store.base import Base
from veritas.store.models import QualityVerdictRow, TraceLogRow

_ASYNC_TO_SYNC = {
    "+aiosqlite": "",
    "+asyncpg": "+psycopg",
    "+aiomysql": "+pymysql",
}


def to_sync_url(url: str) -> str:
    """Convert an async SQLAlchemy URL to its synchronous equivalent.

    ``sqlite+aiosqlite:///x`` -> ``sqlite:///x``; ``postgresql+asyncpg://…`` ->
    ``postgresql+psycopg://…``. A URL with no async driver is returned unchanged.
    """
    for async_driver, sync_driver in _ASYNC_TO_SYNC.items():
        if async_driver in url:
            return url.replace(async_driver, sync_driver, 1)
    return url


def create_read_engine(url: str, *, echo: bool = False) -> Engine:
    """A sync engine for the dashboard. Accepts an async or sync URL."""
    return create_engine(to_sync_url(url), echo=echo)


def ensure_schema(engine: Engine) -> None:
    """Create the storage tables if they don't exist yet — idempotent.

    The dashboard is read-only with respect to *data*, but a brand-new or
    never-run database has no schema at all, so the first query raises
    ``no such table``. Materializing the (empty) tables lets every page render
    its "no data yet" state instead of crashing. On a populated database this is
    a no-op: ``create_all`` only creates missing tables and writes no rows.
    """
    Base.metadata.create_all(engine)


def build_read_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


class ReadRepository:
    """Common base: holds the session factory, opens read-only sessions."""

    def __init__(self, sessionmaker_: sessionmaker[Session]) -> None:
        self._sm = sessionmaker_


class MetaRepository(ReadRepository):
    """Cross-cutting reads used to drive caching."""

    def data_version(self) -> str:
        """A coarse cache-buster: the latest write time across the hot tables.

        Returns a stable token while no new rows are written, and changes when a
        pipeline run appends verdicts or traces, so cached view-models refresh.
        """
        with self._sm() as session:
            last_verdict = session.scalar(select(func.max(QualityVerdictRow.created_at)))
            last_trace = session.scalar(select(func.max(TraceLogRow.created_at)))
        stamps = [str(value) for value in (last_verdict, last_trace) if value is not None]
        return "|".join(stamps) if stamps else "empty"
