"""Application configuration using Pydantic Settings.

Environment variables are loaded from .env file or system environment.
"""

import uuid
from functools import lru_cache
from urllib.parse import urlparse

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings

# Load .env file before settings are instantiated
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # development | staging | production
    environment: str = "development"

    # Redis Configuration
    redis_url: str = "redis://localhost:6379/0"

    # Postgres (durable data: final interview reports). Development defaults to
    # the local container; production must set it.
    database_url: str = ""

    # Worker Configuration
    worker_id: str = str(uuid.uuid4())[:8]  # Unique ID for this worker instance
    consumer_group: str = "brain-workers"
    consumer_name: str = ""  # Defaults to worker-{worker_id}, see _default_consumer_name

    # Stream Names
    request_stream: str = "interview:requests"
    response_stream: str = "interview:responses"
    # Messages given up on after max_delivery_attempts (kept for inspection/replay)
    dead_letter_stream: str = "interview:dead"
    # Keep about this many entries per stream (XADD MAXLEN ~); far above any
    # backlog, but stops the streams growing forever
    stream_maxlen: int = 100_000

    # Stream Recovery Configuration
    reclaim_interval_seconds: int = 15  # How often to reclaim stuck pending messages
    reclaim_min_idle_ms: int = 30000  # Pending this long = owner crashed or failed
    max_delivery_attempts: int = 3  # Drop (ACK) a message after this many failures

    # Distributed Lock Configuration
    lock_ttl_ms: int = 5000  # Lock timeout in milliseconds (renewed while held)
    lock_retry_delay_ms: int = 100  # Delay between lock acquisition retries
    lock_max_retries: int = 100  # ~10s wait: another worker may hold it for a full graph run

    # Context Configuration
    context_prefix: str = "context"  # Redis key prefix for interview context
    lock_prefix: str = "lock:session"  # Redis key prefix for distributed locks
    # Interviews with no activity for this long are ended as "abandoned"
    # (services/inactivity_sweep.py); the voice agent normally ends them much sooner
    inactivity_end_minutes: float = 10.0
    inactivity_sweep_seconds: int = 60
    # Reports that failed are written again this many times, this far apart
    report_retry_attempts: int = 3
    report_retry_minutes: float = 2.0
    # Full transcript (transcript:{session_id}); Postgres keeps it once the interview ends
    transcript_ttl_seconds: int = 30 * 24 * 3600

    # LLM Configuration
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    google_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    )  # For Gemini models - accepts either GOOGLE_API_KEY or GEMINI_API_KEY
    gemini_model: str = "gemini-3.8-flash"
    # Sarvam (Malayalam STT/TTS and the sarvam-105b brain); https://dashboard.sarvam.ai
    sarvam_api_key: str = ""
    # Language the buddy speaks: "en" (Phase 1) or "ml" (Malayalam, Phase 2)
    buddy_language: str = "en"
    # Scoring pipeline (JD parse, ladders, question selection, evidence): fail fast
    # instead of holding the worker while Gemini is slow. Each step has a fallback.
    scoring_llm_timeout_seconds: float = 20.0  # per Gemini request
    scoring_llm_max_retries: int = 1
    scoring_init_timeout_seconds: float = 90.0  # whole skill-tree setup at system_init

    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Heartbeat Configuration
    heartbeat_interval_seconds: int = 10  # How often to send heartbeat
    heartbeat_ttl_seconds: int = 30  # How long before worker considered dead

    # Metrics Configuration
    metrics_publish_interval_seconds: int = 5  # How often to publish metrics

    # Redis Stream Initialization Retries
    redis_init_retries: int = 5
    redis_init_delay_seconds: int = 2

    @model_validator(mode="after")
    def _default_consumer_name(self) -> "Settings":
        # Derive after env loading so WORKER_ID also sets the consumer name
        if not self.consumer_name:
            self.consumer_name = f"worker-{self.worker_id}"
        return self

    @model_validator(mode="after")
    def _require_production_secrets(self) -> "Settings":
        # Fail at startup instead of on the first interview turn
        if self.environment == "production" and not self.google_api_key:
            raise ValueError(
                "Missing required settings for production: GOOGLE_API_KEY (or GEMINI_API_KEY)"
            )
        if self.environment == "production" and not self.database_url:
            raise ValueError("Missing required settings for production: DATABASE_URL")
        if self.environment == "production" and not urlparse(self.redis_url).password:
            # Redis holds every candidate's data: never run it unauthenticated
            raise ValueError(
                "REDIS_URL must include a password in production "
                "(redis://:<password>@host or rediss:// for TLS)"
            )
        return self

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        if self.environment == "production":
            return ""
        return "postgresql://alex:alex-dev-password@127.0.0.1:5434/alex"

    @property
    def context_key(self) -> str:
        """Format string for context keys."""
        return f"{self.context_prefix}:{{session_id}}"

    @property
    def lock_key(self) -> str:
        """Format string for lock keys."""
        return f"{self.lock_prefix}:{{session_id}}"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
