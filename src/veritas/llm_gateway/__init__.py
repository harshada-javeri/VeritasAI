"""Vendor-agnostic LLM gateway: routing, retry, token accounting, budget, pinning."""

from veritas.llm_gateway.budget import BudgetGuard
from veritas.llm_gateway.errors import (
    BudgetExceededError,
    LLMError,
    ModelNotPinnedError,
    PermanentLLMError,
    StructuredOutputError,
    TransientLLMError,
)
from veritas.llm_gateway.gateway import LLMGateway, build_gateway, provider_for_model
from veritas.llm_gateway.pricing import DEFAULT_PRICING, PriceRate, PricingTable
from veritas.llm_gateway.providers import (
    AnthropicClient,
    GeminiClient,
    HttpxTransport,
    ProviderClient,
    Transport,
    TransportResponse,
)
from veritas.llm_gateway.retry import RetryPolicy, with_retry
from veritas.llm_gateway.types import (
    Completer,
    LLMRequest,
    LLMResponse,
    ProviderResult,
)

__all__ = [
    "DEFAULT_PRICING",
    "AnthropicClient",
    "BudgetExceededError",
    "BudgetGuard",
    "Completer",
    "GeminiClient",
    "HttpxTransport",
    "LLMError",
    "LLMGateway",
    "LLMRequest",
    "LLMResponse",
    "ModelNotPinnedError",
    "PermanentLLMError",
    "PriceRate",
    "PricingTable",
    "ProviderClient",
    "ProviderResult",
    "RetryPolicy",
    "StructuredOutputError",
    "TransientLLMError",
    "Transport",
    "TransportResponse",
    "build_gateway",
    "provider_for_model",
    "with_retry",
]
