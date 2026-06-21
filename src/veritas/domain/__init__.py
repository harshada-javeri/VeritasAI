"""Domain models. Every model here is Pydantic v2 and is the contract the rest
of the system is written against."""

from veritas.domain.models import (
    Article,
    CheckType,
    Company,
    ParseError,
    ResolvedEvent,
    Verdict,
    VerdictStatus,
)

__all__ = [
    "Article",
    "CheckType",
    "Company",
    "ParseError",
    "ResolvedEvent",
    "Verdict",
    "VerdictStatus",
]
