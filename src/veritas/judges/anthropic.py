"""Anthropic-bound judge. Defaults to the semantic-accuracy workhorse on Haiku."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from veritas.judges.base import BaseLLMJudge, _utcnow
from veritas.llm_gateway.types import Completer
from veritas.prompt_registry.registry import PromptRegistry


class AnthropicJudge(BaseLLMJudge):
    """A judge whose resolved model must be an Anthropic (Claude) model."""

    provider = "anthropic"

    def __init__(
        self,
        *,
        gateway: Completer,
        registry: PromptRegistry,
        check_name: str = "semantic_accuracy",
        prompt_name: str = "semantic_accuracy",
        prompt_version: str | None = None,
        model: str | None = None,
        max_tokens: int = 512,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
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
