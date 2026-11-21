"""Settings: consumer name derivation and production fail-fast."""

import pytest

from core.config import Settings


def test_consumer_name_follows_worker_id(monkeypatch):
    monkeypatch.setenv("WORKER_ID", "abc")

    assert Settings().consumer_name == "worker-abc"


def test_production_requires_google_key():
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        Settings(environment="production", GOOGLE_API_KEY="")


def test_development_does_not_require_keys():
    assert Settings(environment="development", GOOGLE_API_KEY="").environment == "development"


def test_production_requires_redis_password():
    with pytest.raises(ValueError, match="REDIS_URL"):
        Settings(
            environment="production", GOOGLE_API_KEY="k",
            redis_url="redis://redis:6379/0", database_url="postgresql://u:p@db/alex",
        )
    ok = Settings(
        environment="production", GOOGLE_API_KEY="k",
        redis_url="rediss://:s3cret@redis:6380/0", database_url="postgresql://u:p@db/alex",
    )
    assert ok.environment == "production"
