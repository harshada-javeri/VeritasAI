"""Tests for the judges layer: output schema, base flow, provider binding, replay."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from veritas.domain.models import (
    Article,
    CheckType,
    Company,
    ResolvedEvent,
    Verdict,
    VerdictStatus,
)
from veritas.judges import (
    AnthropicJudge,
    GeminiJudge,
    JudgeOutput,
    LLMJudge,
    ReplayJudge,
    ReplayMiss,
)
from veritas.llm_gateway.errors import PermanentLLMError
from veritas.llm_gateway.types import LLMRequest, LLMResponse
from veritas.prompt_registry import PromptRegistry

NOW = datetime(2026, 6, 22, tzinfo=UTC)


def make_event(event_id: str = "11111111-1111-1111-1111-111111111111") -> ResolvedEvent:
    return ResolvedEvent(
        event_id=event_id,
        category="launches",
        summary="Acme launches Widget",
        article_sentence="Acme launched Widget.",
        company1=Company(id="c1", name="Acme", domain="acme.com"),
        company1_id="c1",
        source_article=Article(id="a1", title="t", body="b", url="https://news.example.com/x"),
        source_article_id="a1",
    )


class _FakeCompleter:
    def __init__(self, content: dict[str, object]) -> None:
        self._content = content
        self.last: LLMRequest | None = None

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.last = request
        return LLMResponse(
            content=self._content,
            model=request.model,
            provider="anthropic",
            input_tokens=100,
            output_tokens=20,
            cost_usd=0.0012,
            latency_ms=42.0,
        )


def test_judge_output_validation_and_clamp() -> None:
    out = JudgeOutput.model_validate({"verdict": "pass", "confidence": 1.5, "reason": "x"})
    assert out.confidence == 1.0
    assert out.verdict is VerdictStatus.PASS


def test_anthropic_judge_returns_llm_verdict() -> None:
    gateway = _FakeCompleter(
        {
            "verdict": "fail",
            "confidence": 0.82,
            "reason": "category mismatch",
            "evidence_span": "acquired",
        }
    )
    judge = AnthropicJudge(gateway=gateway, registry=PromptRegistry.default(), clock=lambda: NOW)
    verdict = asyncio.run(judge.evaluate(make_event()))
    assert verdict.check_type is CheckType.LLM
    assert verdict.status is VerdictStatus.FAIL
    assert verdict.prompt_version == "v1"
    assert verdict.model is not None and verdict.model.startswith("claude")
    assert verdict.cost_usd == pytest.approx(0.0012)
    assert verdict.ts == NOW
    assert gateway.last is not None and "launches" in gateway.last.prompt


def test_gemini_judge_rejects_claude_model() -> None:
    gateway = _FakeCompleter({"verdict": "pass", "confidence": 0.5, "reason": "x"})
    # The shipped semantic_accuracy prompt pins a Claude model; forcing a Gemini
    # judge onto a Claude model must be rejected before any call.
    judge = GeminiJudge(
        gateway=gateway, registry=PromptRegistry.default(), model="claude-haiku-4-5-20251001"
    )
    with pytest.raises(PermanentLLMError):
        asyncio.run(judge.evaluate(make_event()))


def test_gemini_judge_accepts_gemini_model() -> None:
    gateway = _FakeCompleter({"verdict": "pass", "confidence": 0.7, "reason": "ok"})
    judge = GeminiJudge(
        gateway=gateway, registry=PromptRegistry.default(), model="gemini-2.5-flash"
    )
    verdict = asyncio.run(judge.evaluate(make_event()))
    assert verdict.status is VerdictStatus.PASS
    assert gateway.last is not None and gateway.last.model == "gemini-2.5-flash"


def test_replay_judge_returns_recorded() -> None:
    recorded = Verdict(
        event_id="e1",
        check_name="semantic_accuracy",
        check_type=CheckType.LLM,
        status=VerdictStatus.PASS,
        confidence=0.9,
        reason="r",
        ts=NOW,
    )
    judge = ReplayJudge("semantic_accuracy", {"e1": recorded})
    out = asyncio.run(judge.evaluate(make_event("e1")))
    assert out is recorded


def test_replay_miss_raises() -> None:
    judge = ReplayJudge("semantic_accuracy", {})
    with pytest.raises(ReplayMiss):
        asyncio.run(judge.evaluate(make_event("missing")))


def test_all_judges_satisfy_protocol() -> None:
    gateway = _FakeCompleter({"verdict": "pass", "confidence": 0.5, "reason": "x"})
    registry = PromptRegistry.default()
    gemini = GeminiJudge(gateway=gateway, registry=registry, model="gemini-2.5-flash")
    assert isinstance(AnthropicJudge(gateway=gateway, registry=registry), LLMJudge)
    assert isinstance(gemini, LLMJudge)
    assert isinstance(ReplayJudge("c", {}), LLMJudge)
