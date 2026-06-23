"""Reads over ``events_clean`` (+ a confidence join for the review viewer)."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import func, select

from veritas.dashboard.repositories.base import ReadRepository
from veritas.dashboard.repositories.rows import (
    CategoryCount,
    EventHeaderDTO,
    StatusCount,
    StatusListItem,
)
from veritas.store.models import EventCleanRow, QualityVerdictRow

OrderBy = Literal["recent", "confidence"]


class EventRepository(ReadRepository):
    def count(self) -> int:
        with self._sm() as session:
            return int(session.scalar(select(func.count()).select_from(EventCleanRow)) or 0)

    def count_by_status(self) -> list[StatusCount]:
        stmt = select(EventCleanRow.status, func.count()).group_by(EventCleanRow.status)
        with self._sm() as session:
            rows = session.execute(stmt).all()
        return [StatusCount(status=str(r[0]), count=int(r[1])) for r in rows]

    def count_by_category(self) -> list[CategoryCount]:
        stmt = (
            select(EventCleanRow.category, func.count())
            .group_by(EventCleanRow.category)
            .order_by(func.count().desc())
        )
        with self._sm() as session:
            rows = session.execute(stmt).all()
        return [
            CategoryCount(category=(str(r[0]) if r[0] is not None else None), count=int(r[1]))
            for r in rows
        ]

    def get_header(self, event_id: str) -> EventHeaderDTO | None:
        with self._sm() as session:
            row = session.get(EventCleanRow, event_id)
            if row is None:
                return None
            return EventHeaderDTO(
                event_id=row.event_id,
                category=row.category,
                summary=row.summary,
                found_at=row.found_at,
                company1_id=row.company1_id,
                company2_id=row.company2_id,
                status=row.status,
            )

    def list_by_status(
        self, status: str, *, limit: int = 50, offset: int = 0, order_by: OrderBy = "recent"
    ) -> list[StatusListItem]:
        min_conf = (
            select(
                QualityVerdictRow.event_id.label("event_id"),
                func.min(QualityVerdictRow.confidence).label("min_conf"),
            )
            .where(QualityVerdictRow.check_type == "llm")
            .group_by(QualityVerdictRow.event_id)
            .subquery()
        )
        stmt = (
            select(
                EventCleanRow.event_id,
                EventCleanRow.category,
                EventCleanRow.summary,
                EventCleanRow.found_at,
                EventCleanRow.status,
                min_conf.c.min_conf,
            )
            .select_from(EventCleanRow)
            .join(min_conf, min_conf.c.event_id == EventCleanRow.event_id, isouter=True)
            .where(EventCleanRow.status == status)
        )
        if order_by == "confidence":
            stmt = stmt.order_by(min_conf.c.min_conf.asc().nulls_last())
        else:
            stmt = stmt.order_by(EventCleanRow.updated_at.desc())
        stmt = stmt.limit(limit).offset(offset)
        with self._sm() as session:
            rows = session.execute(stmt).all()
        return [
            StatusListItem(
                event_id=str(r[0]),
                category=(str(r[1]) if r[1] is not None else None),
                summary=(str(r[2]) if r[2] is not None else None),
                found_at=r[3],
                status=str(r[4]),
                min_llm_confidence=(float(r[5]) if r[5] is not None else None),
            )
            for r in rows
        ]
