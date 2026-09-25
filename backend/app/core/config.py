"""Application settings. The only place that reads environment variables."""

import json
from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Any

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_DEV_DATABASE_URL = "postgresql+asyncpg://recipebook:recipebook@localhost:5434/recipebook"
_DEV_TEST_DATABASE_URL = "postgresql+asyncpg://recipebook:recipebook@localhost:5434/recipebook_test"


class AppEnv(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_env: AppEnv = AppEnv.DEVELOPMENT
    app_name: str = "RecipeBook API"
    log_level: str = "INFO"
    public_base_url: str = "http://localhost:8000"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    # Database
    database_url: str = _DEV_DATABASE_URL
    test_database_url: str = _DEV_TEST_DATABASE_URL
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_connect_timeout_seconds: float = 5.0
    db_echo: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # AI (validated lazily by the AI adapter, not at boot)
    gemini_api_key: SecretStr | None = None

    # Storage (turned into an enum by the storage module)
    storage_backend: str = "local"
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None

    # Ingredient image search
    image_provider: str = "wikimedia"
    unsplash_access_key: SecretStr | None = None
    pexels_api_key: SecretStr | None = None

    # Upload limits
    max_audio_mb: int = 50
    max_video_mb: int = 500
    max_image_mb: int = 10
    max_cooking_images: int = 20

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: Any) -> Any:
        """Accept a JSON array or a comma-separated string."""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return json.loads(stripped)
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _validate_production(self) -> "Settings":
        if self.app_env is not AppEnv.PRODUCTION:
            return self
        if "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS must list explicit origins in production (no '*').")
        if "database_url" not in self.model_fields_set:
            raise ValueError("DATABASE_URL must be set explicitly in production.")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PRODUCTION

    def secret_values(self) -> list[str]:
        """Every secret value currently configured, used for log redaction."""
        values: list[str] = []
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, SecretStr) and value.get_secret_value():
                values.append(value.get_secret_value())
        for url in (self.database_url, self.test_database_url, self.redis_url):
            password = _password_from_url(url)
            if password:
                values.append(password)
        return values


def _password_from_url(url: str) -> str | None:
    """Return the password part of `scheme://user:password@host/...`, if any."""
    if "@" not in url or "://" not in url:
        return None
    credentials = url.split("://", 1)[1].rsplit("@", 1)[0]
    if ":" not in credentials:
        return None
    return credentials.split(":", 1)[1] or None


def to_async_database_url(url: str) -> str:
    """Normalise any PostgreSQL URL to the asyncpg driver used by the app."""
    for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix) :]
    return url


def to_sync_database_url(url: str) -> str:
    """Normalise any PostgreSQL URL to the psycopg (sync) driver used by Alembic."""
    for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
