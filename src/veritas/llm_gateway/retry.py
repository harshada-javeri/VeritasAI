"""Async retry with exponential backoff for transient LLM failures.

Only ``TransientLLMError`` is retried; permanent errors propagate immediately.
``sleep`` is injectable so tests run with zero delay and remain deterministic
(no wall-clock dependence).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from veritas.llm_gateway.errors import TransientLLMError


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_s: float = 0.5
    max_delay_s: float = 8.0


async def with_retry[T](
    policy: RetryPolicy,
    func: Callable[[], Awaitable[T]],
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    last_error: TransientLLMError | None = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await func()
        except TransientLLMError as exc:
            last_error = exc
            if attempt >= policy.max_attempts:
                break
            delay = min(policy.max_delay_s, policy.base_delay_s * (2 ** (attempt - 1)))
            await sleep(delay)
    assert last_error is not None  # loop only exits here after catching at least once
    raise last_error
