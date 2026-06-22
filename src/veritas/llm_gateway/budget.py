"""Cost budget guard.

A single running meter against a hard ceiling. The gateway checks availability
before each call and records the cost after, so once the ceiling is reached the
next call raises rather than spending. This is the throttle the README's cost
model relies on.
"""

from __future__ import annotations

from veritas.llm_gateway.errors import BudgetExceededError


class BudgetGuard:
    def __init__(self, limit_usd: float) -> None:
        if limit_usd <= 0:
            raise ValueError("budget limit must be positive")
        self._limit = limit_usd
        self._spent = 0.0

    @property
    def limit(self) -> float:
        return self._limit

    @property
    def spent(self) -> float:
        return self._spent

    def remaining(self) -> float:
        return max(0.0, self._limit - self._spent)

    def ensure_available(self) -> None:
        """Raise if the budget is already exhausted."""
        if self._spent >= self._limit:
            raise BudgetExceededError(
                f"cost budget exhausted: spent ${self._spent:.4f} of ${self._limit:.2f}"
            )

    def record(self, cost_usd: float) -> None:
        self._spent += cost_usd
