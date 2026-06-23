"""Alembic environment.

Scaffolding only — no version scripts are shipped yet (see docs/storage-design.md).
The schema's single source of truth is ``veritas.store.Base.metadata``; the URL is
resolved from VeritasAI settings and reduced to a sync driver for Alembic.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from veritas.config import get_settings
from veritas.store import Base  # importing the package registers all ORM models

target_metadata = Base.metadata


def _sync_url() -> str:
    url = get_settings().database_url
    return url.replace("+aiosqlite", "").replace("+asyncpg", "")


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        {"sqlalchemy.url": _sync_url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
