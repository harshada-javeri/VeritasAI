"""Provider clients and the transport seam.

This is where the only vendor-specific code lives:

* **Anthropic** — Messages API with a single forced tool; the tool's
  ``input_schema`` is our JSON schema and ``tool_choice`` forces the model to
  emit exactly that structure. The structured output is the tool_use ``input``.
* **Gemini** — ``generateContent`` with ``responseMimeType: application/json``
  and a ``responseSchema`` (sanitized — Gemini rejects ``additionalProperties``,
  ``title``, ``$ref``/``$defs``). The structured output is the JSON text part.

The HTTP boundary is the ``Transport`` Protocol. ``HttpxTransport`` is the real
implementation; tests inject a fake that returns canned provider bodies, so the
request-building and response-parsing logic is exercised without any network.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import httpx

from veritas.llm_gateway.errors import (
    PermanentLLMError,
    StructuredOutputError,
    TransientLLMError,
)
from veritas.llm_gateway.types import LLMRequest, ProviderResult

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

_RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504, 529})
_GEMINI_UNSUPPORTED_SCHEMA_KEYS = frozenset(
    {"additionalProperties", "title", "$schema", "$defs", "$ref", "default"}
)


@dataclass(frozen=True, slots=True)
class TransportResponse:
    status_code: int
    body: dict[str, Any]


@runtime_checkable
class Transport(Protocol):
    async def post(
        self, url: str, *, headers: Mapping[str, str], json: Mapping[str, Any]
    ) -> TransportResponse: ...


class HttpxTransport:
    """Real HTTP transport. Thin by design — all parsing lives in the clients."""

    def __init__(self, timeout_s: float = 30.0) -> None:
        self._timeout_s = timeout_s

    async def post(
        self, url: str, *, headers: Mapping[str, str], json: Mapping[str, Any]
    ) -> TransportResponse:
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            response = await client.post(url, headers=dict(headers), json=dict(json))
        try:
            parsed: Any = response.json()
        except ValueError:
            parsed = {}
        body = parsed if isinstance(parsed, dict) else {"_raw": parsed}
        return TransportResponse(status_code=response.status_code, body=body)


@runtime_checkable
class ProviderClient(Protocol):
    provider: str

    async def complete(self, request: LLMRequest) -> ProviderResult: ...


def _raise_for_status(response: TransportResponse, *, provider: str) -> None:
    if 200 <= response.status_code < 300:
        return
    message = f"{provider} returned HTTP {response.status_code}: {response.body}"
    if response.status_code in _RETRYABLE_STATUS:
        raise TransientLLMError(message)
    raise PermanentLLMError(message)


def _sanitize_gemini_schema(schema: Any) -> Any:
    """Strip JSON-schema keys Gemini's responseSchema does not accept."""
    if isinstance(schema, dict):
        return {
            key: _sanitize_gemini_schema(value)
            for key, value in schema.items()
            if key not in _GEMINI_UNSUPPORTED_SCHEMA_KEYS
        }
    if isinstance(schema, list):
        return [_sanitize_gemini_schema(item) for item in schema]
    return schema


class AnthropicClient:
    provider = "anthropic"

    def __init__(
        self, api_key: str, transport: Transport, *, base_url: str = ANTHROPIC_URL
    ) -> None:
        self._api_key = api_key
        self._transport = transport
        self._url = base_url

    async def complete(self, request: LLMRequest) -> ProviderResult:
        payload: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "tools": [
                {
                    "name": request.schema_name,
                    "description": "Return the structured judgement for this check.",
                    "input_schema": request.response_schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": request.schema_name},
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.system is not None:
            payload["system"] = request.system
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        response = await self._transport.post(self._url, headers=headers, json=payload)
        _raise_for_status(response, provider=self.provider)
        content = _extract_anthropic_tool_input(response.body, request.schema_name)
        usage = response.body.get("usage") or {}
        model = response.body.get("model")
        return ProviderResult(
            content=content,
            model=model if isinstance(model, str) else request.model,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
        )


def _extract_anthropic_tool_input(body: Mapping[str, Any], schema_name: str) -> dict[str, Any]:
    blocks = body.get("content")
    if isinstance(blocks, list):
        for block in blocks:
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("name") == schema_name
                and isinstance(block.get("input"), dict)
            ):
                return dict(block["input"])
    raise StructuredOutputError(
        f"no tool_use block named {schema_name!r} in Anthropic response"
    )


class GeminiClient:
    provider = "gemini"

    def __init__(
        self, api_key: str, transport: Transport, *, base_url: str = GEMINI_BASE_URL
    ) -> None:
        self._api_key = api_key
        self._transport = transport
        self._base_url = base_url

    async def complete(self, request: LLMRequest) -> ProviderResult:
        url = f"{self._base_url}/{request.model}:generateContent?key={self._api_key}"
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": request.prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": _sanitize_gemini_schema(request.response_schema),
                "maxOutputTokens": request.max_tokens,
            },
        }
        if request.system is not None:
            payload["systemInstruction"] = {"parts": [{"text": request.system}]}
        response = await self._transport.post(
            url, headers={"content-type": "application/json"}, json=payload
        )
        _raise_for_status(response, provider=self.provider)
        content = _extract_gemini_json(response.body)
        usage = response.body.get("usageMetadata") or {}
        return ProviderResult(
            content=content,
            model=request.model,
            input_tokens=int(usage.get("promptTokenCount", 0)),
            output_tokens=int(usage.get("candidatesTokenCount", 0)),
        )


def _extract_gemini_json(body: Mapping[str, Any]) -> dict[str, Any]:
    candidates = body.get("candidates")
    if isinstance(candidates, list) and candidates:
        parts = (candidates[0] or {}).get("content", {}).get("parts")
        if isinstance(parts, list) and parts:
            text = parts[0].get("text")
            if isinstance(text, str):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise StructuredOutputError(
                        f"Gemini response was not valid JSON: {exc}"
                    ) from exc
                if isinstance(parsed, dict):
                    return parsed
    raise StructuredOutputError("no JSON content part in Gemini response")
