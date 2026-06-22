"""Tests for the LLM gateway: routing, pinning, pricing, budget, retry, clients."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import Any

import pytest

from veritas.llm_gateway import (
    BudgetExceededError,
    BudgetGuard,
    LLMGateway,
    LLMRequest,
    ModelNotPinnedError,
    PriceRate,
    PricingTable,
    ProviderResult,
    RetryPolicy,
    TransientLLMError,
    provider_for_model,
    with_retry,
)
from veritas.llm_gateway.errors import PermanentLLMError
from veritas.llm_gateway.providers import (
    AnthropicClient,
    GeminiClient,
    TransportResponse,
    _raise_for_status,
)

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"verdict": {"type": "string"}},
    "required": ["verdict"],
    "additionalProperties": False,
}


def _req(model: str = "claude-haiku-4-5-20251001") -> LLMRequest:
    return LLMRequest(model=model, prompt="hi", response_schema=SCHEMA)


def _make_clock(values: list[float]) -> Callable[[], float]:
    iterator = iter(values)

    def clock() -> float:
        return next(iterator)

    return clock


class _FakeTransport:
    def __init__(self, response: TransportResponse) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    async def post(
        self, url: str, *, headers: Mapping[str, str], json: Mapping[str, Any]
    ) -> TransportResponse:
        self.calls.append({"url": url, "headers": dict(headers), "json": dict(json)})
        return self._response


class _FakeProviderClient:
    provider = "anthropic"

    def __init__(self, result: ProviderResult) -> None:
        self._result = result
        self.calls = 0

    async def complete(self, request: LLMRequest) -> ProviderResult:
        self.calls += 1
        return self._result


# --- routing / pinning / pricing / budget -------------------------------- #


def test_provider_routing() -> None:
    assert provider_for_model("claude-haiku-4-5-20251001") == "anthropic"
    assert provider_for_model("gemini-2.5-flash") == "gemini"
    with pytest.raises(ModelNotPinnedError):
        provider_for_model("gpt-4")


def test_pricing_cost() -> None:
    table = PricingTable({"m": PriceRate(1.0, 5.0)})
    assert table.cost("m", 1_000_000, 2_000_000) == pytest.approx(11.0)
    with pytest.raises(PermanentLLMError):
        table.cost("unknown", 1, 1)


def test_budget_guard() -> None:
    budget = BudgetGuard(1.0)
    budget.ensure_available()
    budget.record(0.6)
    budget.ensure_available()
    budget.record(0.6)
    with pytest.raises(BudgetExceededError):
        budget.ensure_available()
    assert budget.remaining() == 0.0


def test_raise_for_status_classification() -> None:
    with pytest.raises(TransientLLMError):
        _raise_for_status(TransportResponse(429, {}), provider="anthropic")
    with pytest.raises(PermanentLLMError):
        _raise_for_status(TransportResponse(400, {}), provider="anthropic")
    _raise_for_status(TransportResponse(200, {}), provider="anthropic")  # no raise


# --- provider clients (parsing, no network) ------------------------------ #


def test_anthropic_client_parses_tool_use() -> None:
    body = {
        "model": "claude-haiku-4-5-20251001",
        "content": [
            {
                "type": "tool_use",
                "name": "judge_output",
                "input": {"verdict": "pass", "confidence": 0.9, "reason": "ok"},
            }
        ],
        "usage": {"input_tokens": 120, "output_tokens": 30},
    }
    client = AnthropicClient("key", _FakeTransport(TransportResponse(200, body)))
    result = asyncio.run(client.complete(_req()))
    assert result.content["verdict"] == "pass"
    assert result.input_tokens == 120
    assert result.output_tokens == 30


def test_gemini_client_parses_json_part() -> None:
    body = {
        "candidates": [
            {"content": {"parts": [{"text": '{"verdict":"fail","confidence":0.4,"reason":"no"}'}]}}
        ],
        "usageMetadata": {"promptTokenCount": 80, "candidatesTokenCount": 12},
    }
    client = GeminiClient("key", _FakeTransport(TransportResponse(200, body)))
    result = asyncio.run(client.complete(_req("gemini-2.5-flash")))
    assert result.content["verdict"] == "fail"
    assert result.input_tokens == 80


def test_gemini_schema_is_sanitized_in_payload() -> None:
    part_text = '{"verdict":"pass","confidence":1,"reason":"x"}'
    body = {
        "candidates": [{"content": {"parts": [{"text": part_text}]}}],
        "usageMetadata": {},
    }
    transport = _FakeTransport(TransportResponse(200, body))
    client = GeminiClient("key", transport)
    schema = {
        "type": "object",
        "additionalProperties": False,
        "title": "X",
        "properties": {"verdict": {"type": "string"}},
    }
    request = LLMRequest(model="gemini-2.5-flash", prompt="p", response_schema=schema)
    asyncio.run(client.complete(request))
    sent = transport.calls[0]["json"]["generationConfig"]["responseSchema"]
    assert "additionalProperties" not in sent
    assert "title" not in sent


# --- retry --------------------------------------------------------------- #


async def _no_sleep(_: float) -> None:
    return None


def test_with_retry_succeeds_after_transient() -> None:
    state = {"n": 0}

    async def flaky() -> str:
        state["n"] += 1
        if state["n"] < 3:
            raise TransientLLMError("boom")
        return "ok"

    policy = RetryPolicy(max_attempts=3, base_delay_s=0.0)
    out = asyncio.run(with_retry(policy, flaky, sleep=_no_sleep))
    assert out == "ok"
    assert state["n"] == 3


def test_with_retry_exhausts() -> None:
    async def always() -> str:
        raise TransientLLMError("nope")

    policy = RetryPolicy(max_attempts=2, base_delay_s=0.0)
    with pytest.raises(TransientLLMError):
        asyncio.run(with_retry(policy, always, sleep=_no_sleep))


def test_with_retry_does_not_retry_permanent() -> None:
    state = {"n": 0}

    async def perm() -> str:
        state["n"] += 1
        raise PermanentLLMError("bad")

    with pytest.raises(PermanentLLMError):
        asyncio.run(with_retry(RetryPolicy(max_attempts=3), perm, sleep=_no_sleep))
    assert state["n"] == 1


# --- gateway end to end -------------------------------------------------- #


def test_gateway_accounts_cost_and_latency() -> None:
    client = _FakeProviderClient(
        ProviderResult(
            content={"verdict": "pass"},
            model="claude-haiku-4-5-20251001",
            input_tokens=1_000_000,
            output_tokens=0,
        )
    )
    budget = BudgetGuard(100.0)
    gateway = LLMGateway(
        {"anthropic": client},
        pinned_models={"claude-haiku-4-5-20251001"},
        budget=budget,
        pricing=PricingTable({"claude-haiku-4-5-20251001": PriceRate(1.0, 5.0)}),
        clock=_make_clock([1.0, 1.5]),
    )
    response = asyncio.run(gateway.complete(_req()))
    assert response.cost_usd == pytest.approx(1.0)
    assert response.latency_ms == pytest.approx(500.0)
    assert response.provider == "anthropic"
    assert budget.spent == pytest.approx(1.0)


def test_gateway_rejects_unpinned_model() -> None:
    gateway = LLMGateway({}, pinned_models={"claude-haiku-4-5-20251001"}, budget=BudgetGuard(1.0))
    with pytest.raises(ModelNotPinnedError):
        asyncio.run(gateway.complete(_req("claude-sonnet-4-6")))


def test_gateway_enforces_budget_before_next_call() -> None:
    client = _FakeProviderClient(
        ProviderResult(
            content={"verdict": "pass"},
            model="claude-haiku-4-5-20251001",
            input_tokens=1_000_000,
            output_tokens=0,
        )
    )
    gateway = LLMGateway(
        {"anthropic": client},
        pinned_models={"claude-haiku-4-5-20251001"},
        budget=BudgetGuard(1.0),
        pricing=PricingTable({"claude-haiku-4-5-20251001": PriceRate(1.0, 5.0)}),
        clock=_make_clock([0.0, 0.1]),
    )
    asyncio.run(gateway.complete(_req()))  # spends exactly the $1.00 budget
    with pytest.raises(BudgetExceededError):
        asyncio.run(gateway.complete(_req()))
