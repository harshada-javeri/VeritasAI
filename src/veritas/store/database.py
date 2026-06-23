"""Async engine + session factory.

SQLite (aiosqlite) by default; the URL is the only thing that changes for
async Postgres (asyncpg). ``create_all`` is fine for dev/SQLite — Alembic owns
schema for Postgres (see docs/storage-design.md).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from veritas.config import Settings, get_settings
from veritas.store.base import Base


class Database:
    """Owns the async engine and a session factory."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    @classmethod
    def from_url(cls, url: str, *, echo: bool = False) -> Database:
        return cls(create_async_engine(url, echo=echo))

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> Database:
        resolved = settings if settings is not None else get_settings()
        return cls.from_url(resolved.database_url)

    @classmethod
    def in_memory(cls) -> Database:
        """A shared-connection in-memory SQLite DB (tests). StaticPool keeps all
        sessions on one connection so the schema and data are visible across them."""
        engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        return cls(engine)

    @property
    def sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        return self._sessionmaker

    async def create_all(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_all(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    async def dispose(self) -> None:
        await self._engine.dispose()
