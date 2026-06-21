"""Rule registry and default wiring.

The registry is the single place rules are assembled. ``default_registry`` builds
the standard set in evaluation order; ``default_context`` builds a ``RuleContext``
from settings. Keeping registration explicit (rather than import-time magic) makes
the active rule set obvious and the engine trivial to construct for tests.
"""

from __future__ import annotations

from datetime import datetime

from veritas.config import Settings, get_settings
from veritas.rules.base import Rule, RuleContext
from veritas.rules.checks import (
    CONDITIONAL_FIELDS,
    KNOWN_CATEGORIES,
    CategoryKnownRule,
    ConditionalCompletenessRule,
    ConfidenceFloorRule,
    ConfidenceRangeRule,
    DateSanityRule,
    EventIdUuidRule,
    ExactDuplicateRule,
    ReferentialIntegrityRule,
)
from veritas.rules.engine import RuleEngine


class RuleRegistry:
    """An ordered, name-addressable collection of rules."""

    def __init__(self) -> None:
        self._rules: dict[str, Rule] = {}

    def register(self, rule: Rule) -> Rule:
        if rule.name in self._rules:
            raise ValueError(f"rule {rule.name!r} is already registered")
        self._rules[rule.name] = rule
        return rule

    def get(self, name: str) -> Rule:
        return self._rules[name]

    def rules(self) -> list[Rule]:
        return list(self._rules.values())

    def build_engine(self) -> RuleEngine:
        return RuleEngine(self.rules())


def default_registry() -> RuleRegistry:
    """Build the standard rule set in evaluation order (fresh, stateful instances)."""
    registry = RuleRegistry()
    for rule in (
        EventIdUuidRule(),
        ConfidenceRangeRule(),
        ConfidenceFloorRule(),
        CategoryKnownRule(),
        DateSanityRule(),
        ReferentialIntegrityRule(),
        ConditionalCompletenessRule(),
        ExactDuplicateRule(),
    ):
        registry.register(rule)
    return registry


def default_context(now: datetime, settings: Settings | None = None) -> RuleContext:
    """Build a rule context from settings, with ``now`` injected by the caller."""
    resolved = settings if settings is not None else get_settings()
    return RuleContext(
        now=now,
        thresholds=resolved.thresholds,
        known_categories=KNOWN_CATEGORIES,
        conditional_fields=CONDITIONAL_FIELDS,
    )
