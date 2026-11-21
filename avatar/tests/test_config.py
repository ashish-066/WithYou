"""Production fail-fast for required settings."""

import pytest

from core.config import Settings

FULL = dict(
    livekit_url="wss://x",
    livekit_api_key="k",
    livekit_api_secret="s",
    bey_api_key="b",
    sarvam_api_key="sv",
    auth_secret="x" * 32,
    redis_url="redis://:pw@redis:6379/0",
    database_url="postgresql://u:p@db:5432/alex",
)


def test_production_with_all_keys_starts():
    assert Settings(_env_file=None, environment="production", **FULL).environment == "production"


def test_production_names_missing_keys():
    with pytest.raises(ValueError, match="LIVEKIT_URL, SARVAM_API_KEY"):
        Settings(
            _env_file=None,
            environment="production",
            **{**FULL, "livekit_url": "", "sarvam_api_key": ""},
        )


def test_development_does_not_require_keys():
    assert Settings(_env_file=None).environment == "development"


def test_production_requires_strong_auth_secret_and_explicit_cors():
    with pytest.raises(ValueError, match="AUTH_SECRET") as e:
        Settings(
            _env_file=None, environment="production",
            **{**FULL, "auth_secret": "short", "cors_origins": "*"},
        )
    assert "CORS_ORIGINS" in str(e.value)


def test_signup_off_by_default_in_production():
    s = Settings(_env_file=None, environment="production", **FULL)
    assert not s.signup_enabled
    assert Settings(_env_file=None).signup_enabled


def test_production_requires_redis_password():
    with pytest.raises(ValueError, match="REDIS_URL"):
        Settings(_env_file=None, environment="production", **{**FULL, "redis_url": "redis://redis:6379/0"})


def test_production_requires_database_url():
    with pytest.raises(ValueError, match="DATABASE_URL"):
        Settings(_env_file=None, environment="production", **{**FULL, "database_url": ""})


def test_development_defaults_to_local_database():
    assert "5434" in Settings(_env_file=None).effective_database_url
