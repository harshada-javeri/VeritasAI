"""Repositories: the only code that talks SQL.

Storage-pure: they speak domain types (``Verdict``) and primitives, never
pipeline types — so the pipeline stays storage-independent. Writes are idempotent
(select-by-key then insert-or-update), which is portable across SQLite and
Postgres and makes re-running the pipeline replay-safe.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from veritas.domain.models import CheckType, Verdict, VerdictStatus
from veritas.store.models import EventCleanRow, QualityVerdictRow, TraceLogRow


def _now() -> datetime:
    return datetime.now(tz=UTC)


class EventRepository:
    """``events_clean`` — one row per event, keyed by ``event_id`` (upsert)."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    async def upsert(
        self,
        *,
        event_id: str,
        status: str,
        category: str | None = None,
        summary: str | None = None,
        found_at: datetime | None = None,
        company1_id: str | None = None,
        company2_id: str | None = None,
    ) -> None:
        async with self._sm() as session, session.begin():
            row = await session.get(EventCleanRow, event_id)
            if row is None:
                session.add(
                    EventCleanRow(
                        event_id=event_id,
                        category=category,
                        summary=summary,
                        found_at=found_at,
                        company1_id=company1_id,
                        company2_id=company2_id,
                        status=status,
                        updated_at=_now(),
                    )
                )
            else:
                row.category = category
                row.summary = summary
                row.found_at = found_at
                row.company1_id = company1_id
                row.company2_id = company2_id
                row.status = status
                row.updated_at = _now()

    async def get(self, event_id: str) -> EventCleanRow | None:
        async with self._sm() as session:
            return await session.get(EventCleanRow, event_id)

    async def count(self) -> int:
        async with self._sm() as session:
            return int(await session.scalar(select(func.count()).select_from(EventCleanRow)) or 0)


class VerdictRepository:
    """``quality_verdicts`` — idempotent on (event_id, check_name, prompt_version, model)."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    async def upsert_verdicts(self, verdicts: Sequence[Verdict]) -> None:
        async with self._sm() as session, session.begin():
            for verdict in verdicts:
                prompt_version = verdict.prompt_version or ""
                model = verdict.model or ""
                existing = await session.scalar(
                    select(QualityVerdictRow).where(
                        QualityVerdictRow.event_id == verdict.event_id,
                        QualityVerdictRow.check_name == verdict.check_name,
                        QualityVerdictRow.prompt_version == prompt_version,
                        QualityVerdictRow.model == model,
                    )
                )
                if existing is None:
                    session.add(self._to_row(verdict, prompt_version, model))
                else:
                    self._apply(existing, verdict)  # created_at unchanged (first write wins)

    async def list_for_event(self, event_id: str) -> list[Verdict]:
        async with self._sm() as session:
            rows = await session.scalars(
                select(QualityVerdictRow)
                .where(QualityVerdictRow.event_id == event_id)
                .order_by(QualityVerdictRow.id)
            )
            return [self._to_verdict(row) for row in rows]

    async def count(self) -> int:
        async with self._sm() as session:
            return int(
                await session.scalar(select(func.count()).select_from(QualityVerdictRow)) or 0
            )

    @staticmethod
    def _to_row(verdict: Verdict, prompt_version: str, model: str) -> QualityVerdictRow:
        return QualityVerdictRow(
            event_id=verdict.event_id,
            check_name=verdict.check_name,
            check_type=verdict.check_type.value,
            prompt_version=prompt_version,
            model=model,
            verdict=verdict.status.value,
            confidence=verdict.confidence,
            reason=verdict.reason,
            evidence_span=verdict.evidence_span,
            input_tokens=verdict.input_tokens,
            output_tokens=verdict.output_tokens,
            cost_usd=verdict.cost_usd,
            latency_ms=verdict.latency_ms,
            ts=verdict.ts,
            created_at=_now(),
        )

    @staticmethod
    def _apply(row: QualityVerdictRow, verdict: Verdict) -> None:
        row.check_type = verdict.check_type.value
        row.verdict = verdict.status.value
        row.confidence = verdict.confidence
        row.reason = verdict.reason
        row.evidence_span = verdict.evidence_span
        row.input_tokens = verdict.input_tokens
        row.output_tokens = verdict.output_tokens
        row.cost_usd = verdict.cost_usd
        row.latency_ms = verdict.latency_ms
        row.ts = verdict.ts

    @staticmethod
    def _to_verdict(row: QualityVerdictRow) -> Verdict:
        return Verdict(
            event_id=row.event_id,
            check_name=row.check_name,
            check_type=CheckType(row.check_type),
            status=VerdictStatus(row.verdict),
            confidence=row.confidence,
            reason=row.reason,
            evidence_span=row.evidence_span,
            prompt_version=row.prompt_version or None,
            model=row.model or None,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            cost_usd=row.cost_usd,
            latency_ms=row.latency_ms,
            ts=row.ts,
        )


class TraceRepository:
    """``trace_logs`` — append-only audit trail (one row per stage emission)."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    async def append(
        self, *, event_id: str, trace_id: str, stage: str, payload_hash: str
    ) -> None:
        async with self._sm() as session, session.begin():
            session.add(
                TraceLogRow(
                    event_id=event_id,
                    trace_id=trace_id,
                    stage=stage,
                    payload_hash=payload_hash,
                    created_at=_now(),
                )
            )

    async def list_for_event(self, event_id: str) -> list[TraceLogRow]:
        async with self._sm() as session:
            rows = await session.scalars(
                select(TraceLogRow)
                .where(TraceLogRow.event_id == event_id)
                .order_by(TraceLogRow.id)
            )
            return list(rows)

    async def count(self) -> int:
        async with self._sm() as session:
            return int(await session.scalar(select(func.count()).select_from(TraceLogRow)) or 0)
