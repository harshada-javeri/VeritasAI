"""Data access — the ONLY layer that issues SQL.

Read-only, synchronous SQLAlchemy over the three existing tables. Repositories
return typed row DTOs (``rows.py``), never view-models and never business
aggregates beyond GROUP-BY rollups. They reuse the existing ORM models but a
dedicated sync, read-only engine (see ``base.py``) — never the pipeline's async
session — so the dashboard cannot contend with or corrupt pipeline writes.
"""

from __future__ import annotations

from veritas.dashboard.repositories.base import (
    MetaRepository,
    build_read_sessionmaker,
    create_read_engine,
    to_sync_url,
)
from veritas.dashboard.repositories.cost_repository import CostRepository
from veritas.dashboard.repositories.eval_repository import EvalRepository
from veritas.dashboard.repositories.event_repository import EventRepository
from veritas.dashboard.repositories.trace_repository import TraceRepository
from veritas.dashboard.repositories.verdict_repository import VerdictRepository

__all__ = [
    "CostRepository",
    "EvalRepository",
    "EventRepository",
    "MetaRepository",
    "TraceRepository",
    "VerdictRepository",
    "build_read_sessionmaker",
    "create_read_engine",
    "to_sync_url",
]
