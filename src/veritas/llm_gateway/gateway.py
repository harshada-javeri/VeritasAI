"""The gateway: model pinning, provider routing, retry, accounting, budget.

``LLMGateway.complete`` is the one entry point judges call. It validates the
model against the pinned allowlist, routes by model id to the right provider
client, retries transient failures, computes cost from the pricing table, meters
it against the budget guard, and returns a vendor-agnostic ``LLMResponse``.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping

from veritas.config import Settings, get_settings
from veritas.llm_gateway.budget import BudgetGuard
from veritas.llm_gateway.errors import ModelNotPinnedError
from veritas.llm_gateway.pricing import PricingTable
from veritas.llm_gateway.providers import (
    AnthropicClient,
    GeminiClient,
    HttpxTransport,
    ProviderClient,
    Transport,
)
from veritas.llm_gateway.retry import RetryPolicy, with_retry
from veritas.llm_gateway.types import LLMRequest, LLMResponse


def provider_for_model(model: str) -> str:
    """Route a model id to its provider by prefix."""
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith("gemini"):
        return "gemini"
    raise ModelNotPinnedError(f"cannot route model {model!r} to a provider")


class LLMGateway:
    """Implements the ``Completer`` protocol."""

    def __init__(
        self,
        clients: Mapping[str, ProviderClient],
        *,
        pinned_models: set[str],
        budget: BudgetGuard,
        pricing: PricingTable | None = None,
        retry: RetryPolicy | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._clients = dict(clients)
        self._pinned = set(pinned_models)
        self._budget = budget
        self._pricing = pricing if pricing is not None else PricingTable()
        self._retry = retry if retry is not None else RetryPolicy()
        self._clock = clock

    @property
    def budget(self) -> BudgetGuard:
        return self._budget

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if request.model not in self._pinned:
            raise ModelNotPinnedError(
                f"model {request.model!r} is not pinned; allowed: {sorted(self._pinned)}"
            )
        provider = provider_for_model(request.model)
        client = self._clients.get(provider)
        if client is None:
            raise ModelNotPinnedError(f"no client registered for provider {provider!r}")

        self._budget.ensure_available()
        start = self._clock()
        result = await with_retry(self._retry, lambda: client.complete(request))
        latency_ms = (self._clock() - start) * 1000.0

        cost = self._pricing.cost(request.model, result.input_tokens, result.output_tokens)
        self._budget.record(cost)
        return LLMResponse(
            content=result.content,
            model=result.model,
            provider=provider,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
        )


def build_gateway(
    *,
    anthropic_api_key: str,
    gemini_api_key: str,
    transport: Transport | None = None,
    settings: Settings | None = None,
    budget: BudgetGuard | None = None,
) -> LLMGateway:
    """Wire a production gateway from settings and provider API keys."""
    resolved = settings if settings is not None else get_settings()
    shared_transport = transport if transport is not None else HttpxTransport()
    clients: dict[str, ProviderClient] = {
        "anthropic": AnthropicClient(anthropic_api_key, shared_transport),
        "gemini": GeminiClient(gemini_api_key, shared_transport),
    }
    pinned = {resolved.models.haiku, resolved.models.sonnet, resolved.models.gemini_flash}
    return LLMGateway(
        clients,
        pinned_models=pinned,
        budget=budget if budget is not None else BudgetGuard(resolved.cost.monthly_budget_usd),
    )
