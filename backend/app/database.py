# ============================================================
# Database engine / session management (async SQLAlchemy)
# Supports: Supabase Postgres (asyncpg) and local SQLite (aiosqlite)
# ============================================================
from collections.abc import AsyncGenerator

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import settings

_database_url = settings.database_uri


def _clean_database_url(url: str) -> str:
    """Sanitize a provider-generated connection string for asyncpg.

    Supabase pooler URIs may carry a `?pgbouncer=true` hint (used by some
    libpq-based tools). asyncpg does not understand it, so drop unsupported
    query params before handing the URL to the engine.
    """
    parsed = make_url(url)
    unsupported = {"pgbouncer"} & set(parsed.query.keys())
    if unsupported:
        query = dict(parsed.query)
        for key in unsupported:
            query.pop(key, None)
        parsed = parsed.set(query=query)
    return parsed.render_as_string(hide_password=False)


def _build_engine():
    database_url = _clean_database_url(_database_url)
    if database_url.startswith("sqlite"):
        return create_async_engine(
            database_url,
            echo=False,
            connect_args={"check_same_thread": False},
        )

    connect_args: dict = {}
    if database_url.startswith("postgresql+asyncpg"):
        # Disable asyncpg's prepared-statement cache so the connection remains
        # compatible with Supabase's pooler (pgbouncer recycles server
        # connections and cached prepared statements go stale across sessions).
        connect_args["statement_cache_size"] = 0

    return create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        connect_args=connect_args,
    )


engine = _build_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create all tables. For production prefer running supabase/schema.sql."""
    from . import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
