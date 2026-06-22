"""Shared judge implementation: event -> prompt -> gateway -> Verdict.

The vendor difference is concentrated in the gateway's provider clients, so the
judge body here is vendor-neutral. ``AnthropicJudge`` / ``GeminiJudge`` are thin
provider-bound entry points that pin which provider the resolved model must
belong to. ``clock`` is injected so ``ts`` is deterministic in tests.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urlparse

from veritas.domain.models import CheckType, ResolvedEvent, Verdict
from veritas.judges.schema import JUDGE_OUTPUT_SCHEMA, JudgeOutput
from veritas.llm_gateway.errors import PermanentLLMError
from veritas.llm_gateway.gateway import provider_for_model
from veritas.llm_gateway.types import Completer, LLMRequest
from veritas.prompt_registry.registry import PromptRegistry

_BODY_EXCERPT_CHARS = 600


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _domain(url: str | None) -> str:
    if not url:
        return ""
    try:
        return urlparse(url).netloc
    except ValueError:
        return ""


def default_prompt_vars(event: ResolvedEvent) -> dict[str, str]:
    """Common substitution map covering every shipped prompt's placeholders."""
    company1 = event.company1
    company2 = event.company2
    article = event.source_article
    body = (article.body or "")[:_BODY_EXCERPT_CHARS] if article is not None else ""
    return {
        "category": event.category or "",
        "summary": event.summary or "",
        "article_sentence": event.article_sentence or "",
        "company1_name": (company1.name or "") if company1 is not None else "",
        "company1_domain": (company1.domain or "") if company1 is not None else "",
        "company2_name": (company2.name or "") if company2 is not None else "",
        "article_title": (article.title or "") if article is not None else "",
        "article_body": body,
        "url_domain": _domain(article.url) if article is not None else "",
    }


class BaseLLMJudge:
    """Concrete judge flow shared by all providers."""

    #: Provider the resolved model must belong to; subclasses set this.
    provider: str = ""

    def __init__(
        self,
        *,
        check_name: str,
        prompt_name: str,
        gateway: Completer,
        registry: PromptRegistry,
        prompt_version: str | None = None,
        model: str | None = None,
        max_tokens: int = 512,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.check_name = check_name
        self._prompt_name = prompt_name
        self._prompt_version = prompt_version
        self._gateway = gateway
        self._registry = registry
        self._model_override = model
        self._max_tokens = max_tokens
        self._clock = clock

    def prompt_vars(self, event: ResolvedEvent) -> dict[str, str]:
        return default_prompt_vars(event)

    async def evaluate(self, event: ResolvedEvent) -> Verdict:
        spec = self._registry.get(self._prompt_name, self._prompt_version)
        model = self._model_override or spec.model
        if self.provider and provider_for_model(model) != self.provider:
            raise PermanentLLMError(
                f"{type(self).__name__} requires a {self.provider} model, got {model!r}"
            )
        request = LLMRequest(
            model=model,
            prompt=spec.render(self.prompt_vars(event)),
            response_schema=JUDGE_OUTPUT_SCHEMA,
            schema_name="judge_output",
            system=spec.system,
            max_tokens=self._max_tokens,
            metadata={"check": self.check_name, "event_id": event.event_id},
        )
        response = await self._gateway.complete(request)
        output = JudgeOutput.model_validate(response.content)
        return Verdict(
            event_id=event.event_id,
            check_name=self.check_name,
            check_type=CheckType.LLM,
            status=output.verdict,
            confidence=output.confidence,
            reason=output.reason,
            evidence_span=output.evidence_span,
            prompt_version=spec.version,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_usd=response.cost_usd,
            latency_ms=round(response.latency_ms),
            ts=self._clock(),
        )
