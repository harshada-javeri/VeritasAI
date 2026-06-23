"""SQLAlchemy 2.0 storage layer: async, SQLite-default, Postgres-ready.

Repositories are storage-pure (domain types only); the sinks bridge pipeline
``EventOutcome``s to them, so the pipeline never depends on storage.
"""

from veritas.store.base import Base
from veritas.store.database import Database
from veritas.store.models import EventCleanRow, QualityVerdictRow, TraceLogRow
from veritas.store.repositories import EventRepository, TraceRepository, VerdictRepository
from veritas.store.sinks import RepositoryTraceSink, RepositoryVerdictSink

__all__ = [
    "Base",
    "Database",
    "EventCleanRow",
    "EventRepository",
    "QualityVerdictRow",
    "RepositoryTraceSink",
    "RepositoryVerdictSink",
    "TraceLogRow",
    "TraceRepository",
    "VerdictRepository",
]
