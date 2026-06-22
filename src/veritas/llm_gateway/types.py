"""Vendor-agnostic request/response types for the gateway.

``LLMRequest`` and ``LLMResponse`` are the gateway's public currency; provider
clients translate to and from vendor wire formats and return a ``ProviderResult``
(content + token counts) which the gateway enriches with cost, latency, and
provider before returning an ``LLMResponse``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class LLMRequest(BaseModel):
    """A single structured-output completion request."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    model: str
    prompt: str
    response_schema: dict[str, Any]
    schema_name: str = "judge_output"
    system: str | None = None
    max_tokens: int = Field(default=512, gt=0)
    metadata: dict[str, str] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    """A completed request: the structured content plus accounting metadata."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    content: dict[str, Any]
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float


@dataclass(frozen=True, slots=True)
class ProviderResult:
    """What a provider client returns before the gateway adds cost/latency."""

    content: dict[str, Any]
    model: str
    input_tokens: int
    output_tokens: int


@runtime_checkable
class Completer(Protocol):
    """The single method judges depend on. ``LLMGateway`` implements it."""

    async def complete(self, request: LLMRequest) -> LLMResponse: ...
