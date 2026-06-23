"""Reads over ``quality_verdicts`` — the hot table.

Histogram bucketing uses ``CAST(confidence*10 AS INT)`` (portable across SQLite
and Postgres); the service merges the edge bucket. Day buckets use ``func.date``.
Percentiles are NOT computed in SQL (SQLite has no ``percentile_cont``); the
repository returns raw latency samples and the service computes percentiles.
"""

from __future__ import annotations

from sqlalchemy import Integer, cast, func, select

from veritas.dashboard.repositories.base import ReadRepository
from veritas.dashboard.repositories.rows import (
    CategoryCheckCount,
    CheckDayVerdictCount,
    CheckHistogramBin,
    CheckVerdictCount,
    DayCount,
    HistogramBin,
    ModelLatencies,
    VerdictDTO,
)
from veritas.store.models import EventCleanRow, QualityVerdictRow

_QV = QualityVerdictRow


class VerdictRepository(ReadRepository):
    def count(self) -> int:
        with self._sm() as session:
            return int(session.scalar(select(func.count()).select_from(_QV)) or 0)

    def count_by_check(self, check_name: str, verdict: str) -> int:
        stmt = (
            select(func.count())
            .select_from(_QV)
            .where(_QV.check_name == check_name, _QV.verdict == verdict)
        )
        with self._sm() as session:
            return int(session.scalar(stmt) or 0)

    def breakdown(self, check_type: str | None = None) -> list[CheckVerdictCount]:
        stmt = select(_QV.check_name, _QV.verdict, func.count()).group_by(
            _QV.check_name, _QV.verdict
        )
        if check_type is not None:
            stmt = stmt.where(_QV.check_type == check_type)
        with self._sm() as session:
            rows = session.execute(stmt).all()
        return [
            CheckVerdictCount(check_name=str(r[0]), verdict=str(r[1]), count=int(r[2]))
            for r in rows
        ]

    def rule_breakdown(self) -> list[CheckVerdictCount]:
        return self.breakdown("rule")

    def llm_verdict_mix(self) -> list[CheckVerdictCount]:
        return self.breakdown("llm")

    def timeseries_by_check(self, check_name: str, verdict: str) -> list[DayCount]:
        day = func.date(_QV.created_at)
        stmt = (
            select(day, func.count())
            .where(_QV.check_name == check_name, _QV.verdict == verdict)
            .group_by(day)
            .order_by(day)
        )
        with self._sm() as session:
            rows = session.execute(stmt).all()
        return [DayCount(day=str(r[0]), count=int(r[1])) for r in rows]

    def rule_timeseries(self) -> list[CheckDayVerdictCount]:
        day = func.date(_QV.created_at)
        stmt = (
            select(_QV.check_name, day, _QV.verdict, func.count())
            .where(_QV.check_type == "rule")
            .group_by(_QV.check_name, day, _QV.verdict)
            .order_by(_QV.check_name, day)
        )
        with self._sm() as session:
            rows = session.execute(stmt).all()
        return [
            CheckDayVerdictCount(
                check_name=str(r[0]), day=str(r[1]), verdict=str(r[2]), count=int(r[3])
            )
            for r in rows
        ]

    def confidence_histogram(self, check_type: str = "llm") -> list[HistogramBin]:
        bucket = cast(_QV.confidence * 10, Integer).label("bucket")
        stmt = (
            select(bucket, func.count())
            .where(_QV.check_type == check_type, _QV.confidence.is_not(None))
            .group_by(bucket)
            .order_by(bucket)
        )
        with self._sm() as session:
            rows = session.execute(stmt).all()
        return [HistogramBin(bucket=int(r[0]), count=int(r[1])) for r in rows]

    def confidence_histogram_by_check(self, check_type: str = "llm") -> list[CheckHistogramBin]:
        bucket = cast(_QV.confidence * 10, Integer).label("bucket")
        stmt = (
            select(_QV.check_name, bucket, func.count())
            .where(_QV.check_type == check_type, _QV.confidence.is_not(None))
            .group_by(_QV.check_name, bucket)
            .order_by(_QV.check_name, bucket)
        )
        with self._sm() as session:
            rows = session.execute(stmt).all()
        return [
            CheckHistogramBin(check_name=str(r[0]), bucket=int(r[1]), count=int(r[2]))
            for r in rows
        ]

    def failures_by_category(self) -> list[CategoryCheckCount]:
        stmt = (
            select(EventCleanRow.category, _QV.check_name, func.count())
            .select_from(_QV)
            .join(EventCleanRow, EventCleanRow.event_id == _QV.event_id)
            .where(_QV.check_type == "rule", _QV.verdict == "fail")
            .group_by(EventCleanRow.category, _QV.check_name)
            .order_by(func.count().desc())
        )
        with self._sm() as session:
            rows = session.execute(stmt).all()
        return [
            CategoryCheckCount(
                category=(str(r[0]) if r[0] is not None else None),
                check_name=str(r[1]),
                count=int(r[2]),
            )
            for r in rows
        ]

    def latency_by_model(self) -> list[ModelLatencies]:
        stmt = (
            select(_QV.model, _QV.latency_ms)
            .where(_QV.check_type == "llm", _QV.latency_ms.is_not(None))
            .order_by(_QV.model)
        )
        with self._sm() as session:
            rows = session.execute(stmt).all()
        grouped: dict[str, list[int]] = {}
        for r in rows:
            grouped.setdefault(str(r[0]), []).append(int(r[1]))
        return [ModelLatencies(model=model, values=tuple(vals)) for model, vals in grouped.items()]

    def latency_samples_by_day(self) -> list[tuple[str, int]]:
        day = func.date(_QV.created_at)
        stmt = select(day, _QV.latency_ms).where(
            _QV.check_type == "llm", _QV.latency_ms.is_not(None)
        )
        with self._sm() as session:
            rows = session.execute(stmt).all()
        return [(str(r[0]), int(r[1])) for r in rows]

    def list_for_event(self, event_id: str) -> list[VerdictDTO]:
        stmt = select(_QV).where(_QV.event_id == event_id).order_by(_QV.id)
        with self._sm() as session:
            rows = list(session.scalars(stmt))
        return [
            VerdictDTO(
                check_name=row.check_name,
                check_type=row.check_type,
                status=row.verdict,
                confidence=row.confidence,
                reason=row.reason,
                evidence_span=row.evidence_span,
                prompt_version=row.prompt_version,
                model=row.model,
                input_tokens=row.input_tokens,
                output_tokens=row.output_tokens,
                cost_usd=row.cost_usd,
                latency_ms=row.latency_ms,
                ts=row.ts,
            )
            for row in rows
        ]
