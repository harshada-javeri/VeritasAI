"""ORM row models for the three storage tables.

Idempotency note: ``quality_verdicts`` is unique on
``(event_id, check_name, prompt_version, model)``. SQL treats NULLs as distinct
in a unique constraint, which would *defeat* idempotency for rule verdicts (whose
``prompt_version``/``model`` are absent). So those two columns are stored as
non-null empty strings (``""``) for rules — the constraint then dedupes rules too.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from veritas.store.base import Base


class EventCleanRow(Base):
    __tablename__ = "events_clean"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    found_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    company1_id: Mapped[str | None] = mapped_column(String, nullable=True)
    company2_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QualityVerdictRow(Base):
    __tablename__ = "quality_verdicts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String, index=True)
    check_name: Mapped[str] = mapped_column(String)
    check_type: Mapped[str] = mapped_column(String)
    prompt_version: Mapped[str] = mapped_column(String, default="")  # "" for rules
    model: Mapped[str] = mapped_column(String, default="")  # "" for rules
    verdict: Mapped[str] = mapped_column(String)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    evidence_span: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "event_id", "check_name", "prompt_version", "model", name="verdict_idempotency"
        ),
    )


class TraceLogRow(Base):
    __tablename__ = "trace_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String, index=True)
    trace_id: Mapped[str] = mapped_column(String)
    stage: Mapped[str] = mapped_column(String)
    payload_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
