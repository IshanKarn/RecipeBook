"""Async engine, session factory and session helpers."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings, to_async_database_url


def create_engine(settings: Settings, database_url: str | None = None) -> AsyncEngine:
    return create_async_engine(
        to_async_database_url(database_url or settings.database_url),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        echo=settings.db_echo,
        connect_args={"timeout": settings.db_connect_timeout_seconds},
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@lru_cache
def get_engine() -> AsyncEngine:
    return create_engine(get_settings())


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return create_sessionmaker(get_engine())


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request. Services decide when to commit."""
    async with get_sessionmaker()() as session:
        yield session


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Transactional scope for non-HTTP code (workers, scripts): commit or roll back."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
