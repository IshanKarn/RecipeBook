import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import AppEnv, Settings, to_async_database_url, to_sync_database_url

pytestmark = pytest.mark.unit


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_defaults_load() -> None:
    settings = make_settings()
    assert settings.app_env in set(AppEnv)
    assert settings.max_audio_mb == 50
    assert settings.max_video_mb == 500
    assert settings.max_image_mb == 10
    assert settings.max_cooking_images == 20
    assert settings.storage_backend == "local"
    assert settings.image_provider == "wikimedia"


def test_cors_origins_accepts_comma_separated_and_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    assert make_settings().cors_origins == ["http://a.test", "http://b.test"]
    monkeypatch.setenv("CORS_ORIGINS", '["http://c.test"]')
    assert make_settings().cors_origins == ["http://c.test"]


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        make_settings(
            app_env=AppEnv.PRODUCTION,
            cors_origins=["*"],
            database_url="postgresql+asyncpg://u:p@db/app",
        )


def test_production_requires_explicit_database_url() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        make_settings(app_env=AppEnv.PRODUCTION, cors_origins=["https://app.test"])


def test_production_accepts_valid_config() -> None:
    settings = make_settings(
        app_env=AppEnv.PRODUCTION,
        cors_origins=["https://app.test"],
        database_url="postgresql+asyncpg://u:p@db/app",
    )
    assert settings.is_production


def test_secrets_are_not_exposed_in_repr() -> None:
    settings = make_settings(gemini_api_key=SecretStr("super-secret-gemini-key"))
    assert "super-secret-gemini-key" not in repr(settings)
    assert "super-secret-gemini-key" not in str(settings.model_dump())


def test_secret_values_include_keys_and_database_password() -> None:
    settings = make_settings(
        gemini_api_key=SecretStr("gemini-key-123"),
        database_url="postgresql+asyncpg://user:db-pass-456@localhost/app",
    )
    values = settings.secret_values()
    assert "gemini-key-123" in values
    assert "db-pass-456" in values


@pytest.mark.parametrize(
    ("url", "expected_async", "expected_sync"),
    [
        (
            "postgresql://u:p@h/db",
            "postgresql+asyncpg://u:p@h/db",
            "postgresql+psycopg://u:p@h/db",
        ),
        (
            "postgresql+asyncpg://u:p@h/db",
            "postgresql+asyncpg://u:p@h/db",
            "postgresql+psycopg://u:p@h/db",
        ),
    ],
)
def test_database_url_driver_conversion(url: str, expected_async: str, expected_sync: str) -> None:
    assert to_async_database_url(url) == expected_async
    assert to_sync_database_url(url) == expected_sync
