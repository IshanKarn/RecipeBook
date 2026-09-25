"""Shared fixtures.

Integration fixtures run Alembic migrations against TEST_DATABASE_URL once per session
(never `create_all`) and give each test a session inside a rolled-back transaction.
"""

import os

os.environ.setdefault("APP_ENV", "test")

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import AppEnv, Settings, to_async_database_url
from app.db.session import get_session
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(app_env=AppEnv.TEST)


def make_alembic_config(database_url: str) -> Config:
    """Alembic config pointed at `database_url`, without touching the logging setup."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["database_url"] = database_url
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session")
def alembic_config(settings: Settings) -> Config:
    return make_alembic_config(settings.test_database_url)


@pytest.fixture(scope="session")
def migrated_database(alembic_config: Config) -> Iterator[None]:
    command.upgrade(alembic_config, "head")
    yield


@pytest.fixture
async def db_session(settings: Settings, migrated_database: None) -> AsyncIterator[AsyncSession]:
    """A session whose work is rolled back after the test.

    Code under test may call `commit()`: with `create_savepoint` it only releases a
    savepoint, and the outer transaction is still rolled back.
    """
    engine = create_async_engine(
        to_async_database_url(settings.test_database_url), poolclass=NullPool
    )
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def db_app(app: FastAPI, db_session: AsyncSession) -> FastAPI:
    """The app with `get_session` bound to the test transaction."""

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _override_session
    return app


@pytest.fixture
async def client(db_app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=db_app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
