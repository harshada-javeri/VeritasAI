"""The judge contract: one async method returning exactly a ``Verdict``."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from veritas.domain.models import ResolvedEvent, Verdict


@runtime_checkable
class LLMJudge(Protocol):
    """An LLM-backed quality check. Vendor-agnostic by construction."""

    check_name: str

    async def evaluate(self, event: ResolvedEvent) -> Verdict: ...
