"""Async engine, session factory and connection lifecycle."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings

logger = logging.getLogger(__name__)


def _engine_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "echo": settings.DB_ECHO,
        "pool_pre_ping": settings.DB_POOL_PRE_PING,
        "future": True,
    }

    connect_args: dict[str, Any] = {
        # Postgres treats this as the application_name, which makes it easy to
        # spot API traffic in Supabase's pg_stat_activity view.
        "server_settings": {"application_name": settings.PROJECT_NAME},
    }

    if settings.DB_DISABLE_PREPARED_STATEMENTS:
        # Supabase's transaction-mode pooler multiplexes server connections, so
        # a prepared statement created on one may not exist on the next. Both
        # knobs are required: asyncpg caches statements *and* names them.
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_cache_size"] = 0
        # asyncpg names prepared statements from a per-process counter
        # (__asyncpg_stmt_N__), which collides once the pooler hands two
        # concurrent connections to different backend sessions that both
        # reach the same N. A random name per statement avoids that clash.
        connect_args["prepared_statement_name_func"] = (
            lambda: f"__asyncpg_{uuid.uuid4()}__"
        )
        # NullPool hands every checkout a fresh connection; the pooler already
        # does the pooling, so client-side pooling only duplicates it.
        kwargs["poolclass"] = NullPool
    else:
        kwargs["pool_size"] = settings.DB_POOL_SIZE
        kwargs["max_overflow"] = settings.DB_MAX_OVERFLOW
        kwargs["pool_recycle"] = settings.DB_POOL_RECYCLE_SECONDS

    kwargs["connect_args"] = connect_args
    return kwargs


engine: AsyncEngine = create_async_engine(settings.sqlalchemy_url, **_engine_kwargs())

SessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a session that rolls back on failure."""
    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def verify_connection() -> None:
    """Fail fast at boot if the database is unreachable or misconfigured."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("Database connection verified")


async def dispose_engine() -> None:
    await engine.dispose()
    logger.info("Database engine disposed")
