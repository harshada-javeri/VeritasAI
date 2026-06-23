"""Reads over ``trace_logs`` (append-only): throughput, stage volume, drill-down."""

from __future__ import annotations

from sqlalchemy import func, select

from veritas.dashboard.repositories.base import ReadRepository
from veritas.dashboard.repositories.rows import DayCount, StageCount, TraceDTO
from veritas.store.models import TraceLogRow

_TR = TraceLogRow


class TraceRepository(ReadRepository):
    def count(self) -> int:
        with self._sm() as session:
            return int(session.scalar(select(func.count()).select_from(_TR)) or 0)

    def throughput(self) -> list[DayCount]:
        day = func.date(_TR.created_at)
        stmt = select(day, func.count()).group_by(day).order_by(day)
        with self._sm() as session:
            rows = session.execute(stmt).all()
        return [DayCount(day=str(r[0]), count=int(r[1])) for r in rows]

    def count_by_stage(self) -> list[StageCount]:
        stmt = (
            select(_TR.stage, func.count()).group_by(_TR.stage).order_by(func.count().desc())
        )
        with self._sm() as session:
            rows = session.execute(stmt).all()
        return [StageCount(stage=str(r[0]), count=int(r[1])) for r in rows]

    def list_for_event(self, event_id: str) -> list[TraceDTO]:
        stmt = select(_TR).where(_TR.event_id == event_id).order_by(_TR.id)
        with self._sm() as session:
            rows = list(session.scalars(stmt))
        return [
            TraceDTO(
                stage=row.stage,
                trace_id=row.trace_id,
                payload_hash=row.payload_hash,
                created_at=row.created_at,
            )
            for row in rows
        ]
