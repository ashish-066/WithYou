"""Application configuration using Pydantic Settings.

Environment variables are loaded from .env file or system environment.
"""

import uuid
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Local development database (docker container alex-postgres, local-only password)
DEV_DATABASE_URL = "postgresql://alex:alex-dev-password@127.0.0.1:5434/alex"

# Settings that must be non-empty when ENVIRONMENT=production
PRODUCTION_REQUIRED = (
    "livekit_url",
    "livekit_api_key",
    "livekit_api_secret",
    "bey_api_key",
    "deepgram_api_key",
)


class Settings(BaseSettings):
    """Avatar Service settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # development | staging | production
    environment: str = "development"

    # Redis Configuration
    redis_url: str = "redis://localhost:6379/0"

    # Postgres (durable data). Development defaults to the local container
    # (see docs: docker run ... alex-postgres on port 5434); production must set it.
    database_url: str = ""

    # Stream Configuration
    request_stream: str = "interview:requests"
    response_stream: str = "interview:responses"
    # Messages the worker gave up on (must match the worker)
    dead_letter_stream: str = "interview:dead"
    # Keep about this many entries per stream (XADD MAXLEN ~); far above any
    # backlog, but stops the streams growing forever
    stream_maxlen: int = 100_000

    # Consumer Group Configuration (for consuming responses)
    consumer_group: str = "avatar-listeners"
    consumer_name: str = f"avatar-{uuid.uuid4().hex[:8]}"

    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8001  # Different from backend's 8000
    debug: bool = False

    # Listener Configuration
    consume_batch_size: int = 10
    consume_block_ms: int = 5000  # Block for 5 seconds when waiting for messages
    idle_claim_ms: int = 30000  # Claim messages idle for 30+ seconds

    # LiveKit Configuration
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    # BeyondPresence Configuration
    bey_api_key: str = ""
    # Video avatar on/off. If it's on but BeyondPresence fails (e.g. out of
    # credits), the session carries on voice-only.
    enable_avatar: bool = True
    bey_avatar_id: str = "b9be11b8-89fb-4227-8f86-4a881393cbdb"  # Default avatar

    # STT Configuration (Deepgram via LiveKit Inference)
    deepgram_api_key: str = ""  # Optional: uses LiveKit Inference if empty

    # TTS Configuration (Cartesia via LiveKit Inference)
    cartesia_api_key: str = ""  # unused (out of credits); kept so existing .env files load
    deepgram_tts_model: str = "aura-2-thalia-en"
    # Sarvam (Malayalam STT/TTS and the sarvam-105b brain); https://dashboard.sarvam.ai
    sarvam_api_key: str = ""

    # Agent Configuration
    agent_name: str = "Study Buddy"
    # Language the buddy greets and nudges in: "en" or "ml" (Malayalam, Phase 2)
    buddy_language: str = "en"
    # The voice agent registers under this name and is dispatched explicitly to
    # each call's room, so no other agent on the same LiveKit project takes it
    agent_dispatch_name: str = "padippu-buddy"
    agent_instructions: str = ""  # unused: the brain worker writes every reply

    # Context Configuration (Must match worker config)
    context_prefix: str = "context"


    # Auth Configuration
    # Signs session cookies. Required (32+ chars) in production;
    # development falls back to a fixed insecure value so restarts keep you logged in.
    auth_secret: str = ""
    session_ttl_hours: int = 12  # learner login
    # Public sign-up creates a new organization; off in production unless enabled
    allow_signup: bool | None = None
    # Browser origins allowed to call the API (comma-separated). The Vite dev
    # proxy makes the frontend same-origin, so this matters for deployed setups.
    cors_origins: str = "http://localhost:3000"
    # Reverse proxies in front of the API that append to X-Forwarded-For
    # (frontend nginx = 1; nginx behind a cloud load balancer = 2). The client
    # IP for rate limits is read that many entries from the right, so a client
    # can't spoof it by sending its own header. 0 = use the socket peer.
    trusted_proxy_hops: int = 0

    # LiveKit agent process (`python -m agents.entrypoint start`)
    # On SIGTERM the agent takes no new interviews and waits this long for
    # running ones to end; the platform's stop grace period must be longer.
    agent_drain_timeout_seconds: int = 3600
    # Health endpoint: GET / (200 when connected to LiveKit), GET /worker
    agent_health_port: int = 8081

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def signup_enabled(self) -> bool:
        return self.allow_signup if self.allow_signup is not None else not self.is_production


    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        if self.is_production:
            return ""
        return DEV_DATABASE_URL

    @property
    def effective_auth_secret(self) -> str:
        return self.auth_secret or "dev-insecure-auth-secret-do-not-use-in-production"

    @model_validator(mode="after")
    def _require_production_secrets(self) -> "Settings":
        # Fail at startup instead of mid-interview when a key is missing
        if self.environment == "production":
            missing = [
                name.upper()
                for name in PRODUCTION_REQUIRED
                if not getattr(self, name)
            ]
            if not self.database_url:
                missing.append("DATABASE_URL")
            if not urlparse(self.redis_url).password:
                missing.append("REDIS_URL with a password (redis://:<password>@host or rediss://)")
            if len(self.auth_secret) < 32:
                missing.append("AUTH_SECRET (32+ characters)")
            if "*" in self.cors_origin_list:
                missing.append("CORS_ORIGINS (explicit origins, not *)")
            if missing:
                raise ValueError(
                    f"Missing required settings for production: {', '.join(missing)}"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
