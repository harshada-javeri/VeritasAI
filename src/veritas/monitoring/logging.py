"""Structured JSON logging for the pipeline.

Emits one JSON object per event. ``emit`` is injectable (tests capture the lines);
the default writes to the stdlib logger. ``clock`` is injectable so timestamps are
deterministic in tests (omitted entirely when no clock is given).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any


def _stdlib_emit(name: str) -> Callable[[str], None]:
    logger = logging.getLogger(name)

    def emit(line: str) -> None:
        logger.info(line)

    return emit


class PipelineLogger:
    def __init__(
        self,
        *,
        name: str = "veritas.pipeline",
        emit: Callable[[str], None] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._emit = emit if emit is not None else _stdlib_emit(name)
        self._clock = clock

    def log(self, event: str, **fields: Any) -> None:
        record: dict[str, Any] = {"event": event}
        if self._clock is not None:
            record["ts"] = self._clock()
        record.update(fields)
        self._emit(json.dumps(record, default=str, sort_keys=True))
