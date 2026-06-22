"""Replay judge: returns recorded verdicts, never calls a model.

This is what makes evals and the pipeline replayable and free to develop
against. Recordings are ``Verdict`` rows keyed by ``event_id`` for one check.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from veritas.domain.models import ResolvedEvent, Verdict


class ReplayMiss(KeyError):
    """No recorded verdict exists for this event under this check."""


class ReplayJudge:
    """Implements ``LLMJudge`` by replaying recorded verdicts."""

    def __init__(self, check_name: str, recordings: Mapping[str, Verdict]) -> None:
        self.check_name = check_name
        self._by_event: dict[str, Verdict] = dict(recordings)

    @classmethod
    def from_file(cls, path: Path, check_name: str) -> ReplayJudge:
        """Load a JSON array of Verdict rows, indexing those matching ``check_name``."""
        rows = json.loads(path.read_text(encoding="utf-8"))
        verdicts = [Verdict.model_validate(row) for row in rows]
        return cls(
            check_name,
            {v.event_id: v for v in verdicts if v.check_name == check_name},
        )

    async def evaluate(self, event: ResolvedEvent) -> Verdict:
        try:
            return self._by_event[event.event_id]
        except KeyError:
            raise ReplayMiss(
                f"no recorded verdict for event {event.event_id!r} / check {self.check_name!r}"
            ) from None
