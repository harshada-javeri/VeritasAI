"""Repository-backed implementations of the pipeline's storage seams.

These adapt pipeline types (``EventOutcome``) to the storage-pure repositories,
keeping the repositories free of any pipeline dependency. ``RepositoryVerdictSink``
implements ``VerdictSink``; ``RepositoryTraceSink`` implements ``PipelineTraceSink``
and persists both ``events_clean`` (from the outcome snapshot) and ``trace_logs``.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence

from veritas.domain.models import Verdict
from veritas.pipeline.contracts import EventOutcome
from veritas.store.repositories import EventRepository, TraceRepository, VerdictRepository

_TRACE_NAMESPACE = uuid.UUID("00000000-0000-0000-0000-00000000feed")
_STAGE = "finalized"


class RepositoryVerdictSink:
    """Implements ``VerdictSink``."""

    def __init__(self, verdicts: VerdictRepository) -> None:
        self._verdicts = verdicts

    async def upsert_verdicts(self, verdicts: Sequence[Verdict]) -> None:
        await self._verdicts.upsert_verdicts(verdicts)


class RepositoryTraceSink:
    """Implements ``PipelineTraceSink``: persists the event row and a trace row."""

    def __init__(self, traces: TraceRepository, events: EventRepository | None = None) -> None:
        self._traces = traces
        self._events = events

    async def on_outcome(self, outcome: EventOutcome) -> None:
        if self._events is not None and outcome.snapshot is not None:
            snap = outcome.snapshot
            await self._events.upsert(
                event_id=snap.event_id,
                status=outcome.final_status.value,
                category=snap.category,
                summary=snap.summary,
                found_at=snap.found_at,
                company1_id=snap.company1_id,
                company2_id=snap.company2_id,
            )
        payload_hash = hashlib.sha256(outcome.model_dump_json().encode("utf-8")).hexdigest()
        trace_id = str(uuid.uuid5(_TRACE_NAMESPACE, outcome.event_id))
        await self._traces.append(
            event_id=outcome.event_id,
            trace_id=trace_id,
            stage=_STAGE,
            payload_hash=payload_hash,
        )
