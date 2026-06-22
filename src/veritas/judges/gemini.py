"""Gemini-bound judge. Same check flow; resolved model must be a Gemini model.

Demonstrates vendor-agnosticism: the only difference from ``AnthropicJudge`` is
the provider the model routes to — the prompt, schema, and Verdict mapping are
identical, and the gateway handles the wire-format differences.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from veritas.judges.base import BaseLLMJudge, _utcnow
from veritas.llm_gateway.types import Completer
from veritas.prompt_registry.registry import PromptRegistry


class GeminiJudge(BaseLLMJudge):
    """A judge whose resolved model must be a Gemini model."""

    provider = "gemini"

    def __init__(
        self,
        *,
        gateway: Completer,
        registry: PromptRegistry,
        model: str,
        check_name: str = "semantic_accuracy",
        prompt_name: str = "semantic_accuracy",
        prompt_version: str | None = None,
        max_tokens: int = 512,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        # model is required: shipped prompts pin Anthropic models, so a Gemini
        # judge must override it explicitly with a Gemini model id.
        super().__init__(
            check_name=check_name,
            prompt_name=prompt_name,
            gateway=gateway,
            registry=registry,
            prompt_version=prompt_version,
            model=model,
            max_tokens=max_tokens,
            clock=clock,
        )
