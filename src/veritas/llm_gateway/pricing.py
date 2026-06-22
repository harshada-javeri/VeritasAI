"""Token pricing and cost computation.

Rates are USD per 1M tokens. Anthropic rates are current (Haiku 4.5 $1/$5,
Sonnet 4.6 $3/$15); the Gemini rate is illustrative and should be verified
against current pricing before a real run. Keyed by exact pinned model id so a
cost can never be silently computed against the wrong rate.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from veritas.llm_gateway.errors import PermanentLLMError


@dataclass(frozen=True, slots=True)
class PriceRate:
    input_per_mtok: float
    output_per_mtok: float


DEFAULT_PRICING: dict[str, PriceRate] = {
    "claude-haiku-4-5-20251001": PriceRate(1.00, 5.00),
    "claude-haiku-4-5": PriceRate(1.00, 5.00),
    "claude-sonnet-4-6": PriceRate(3.00, 15.00),
    "gemini-2.5-flash": PriceRate(0.30, 2.50),  # illustrative — verify before use
}


class PricingTable:
    """Computes USD cost for a model's token usage."""

    def __init__(self, rates: Mapping[str, PriceRate] | None = None) -> None:
        self._rates: dict[str, PriceRate] = dict(rates if rates is not None else DEFAULT_PRICING)

    def cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        rate = self._rates.get(model)
        if rate is None:
            raise PermanentLLMError(f"no pricing configured for model {model!r}")
        return (
            input_tokens / 1_000_000 * rate.input_per_mtok
            + output_tokens / 1_000_000 * rate.output_per_mtok
        )
