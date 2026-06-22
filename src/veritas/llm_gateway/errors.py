"""LLM gateway error hierarchy.

The split that matters for the retry policy: ``TransientLLMError`` is safe to
retry (rate limits, 5xx, network blips); ``PermanentLLMError`` is not (bad
request, auth, a structurally wrong response). Budget and pinning failures are
permanent and surfaced distinctly so callers can react to them specifically.
"""

from __future__ import annotations


class LLMError(Exception):
    """Base class for all gateway errors."""


class TransientLLMError(LLMError):
    """A retryable failure (429, 5xx, timeout, connection error)."""


class PermanentLLMError(LLMError):
    """A non-retryable failure (4xx other than 429, malformed response)."""


class StructuredOutputError(PermanentLLMError):
    """The provider response did not contain the expected structured output."""


class BudgetExceededError(LLMError):
    """The configured cost budget has been exhausted."""


class ModelNotPinnedError(LLMError):
    """A request named a model that is not in the pinned allowlist / has no client."""
