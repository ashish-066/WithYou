"""Presence View Avatar Service - FastAPI Application.

This service handles the avatar layer for the Presence View AI Interview Platform:
- Creates and manages video interview calls via LiveKit
- Runs LiveKit agents with STT, TTS, and BeyondPresence avatars

The service runs in two modes:
1. FastAPI server (main.py) - HTTP API for call management
2. LiveKit agent server (agents/entrypoint.py) - Handles WebRTC connections
"""

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from alex_db import dispose_engine, get_engine
from alex_db.schema import ensure_schema
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

import core.db  # noqa: F401  (configures the database)
from api.admin_routes import router as admin_router
from api.auth_routes import router as auth_router
from api.dsa_routes import router as dsa_router
from api.elo_routes import router as elo_router
from api.org_routes import router as org_router
from api.platform_routes import router as platform_router
from api.role_routes import router as role_router
from api.routes import router
from core.config import settings
from core.redis import get_redis_client
from services.livekit_service import livekit_service

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    # Startup
    logger.info("Starting Presence View Avatar Service...")
    logger.info(f"LiveKit URL: {settings.livekit_url}")

    # Development applies pending migrations; production refuses to start on a
    # stale schema (migrations are a deploy step)
    await ensure_schema(auto_upgrade=not settings.is_production)

    yield

    # Shutdown
    logger.info("Shutting down Presence View Avatar Service...")

    await livekit_service.close()
    await dispose_engine()

    logger.info("Presence View Avatar Service stopped")


app = FastAPI(
    title="Presence View Avatar Service",
    description="AI Interview Platform - Avatar and Video Call Management",
    version="0.2.0",
    lifespan=lifespan,
)

# Cookies carry auth, so origins must be explicit (a wildcard with credentials
# would let any website make signed-in requests)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(auth_router)
app.include_router(router)
app.include_router(admin_router)
app.include_router(dsa_router)
app.include_router(elo_router)
app.include_router(role_router)
app.include_router(org_router)
app.include_router(platform_router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Liveness: the process is serving requests (no dependency checks)."""
    return {
        "status": "healthy",
        "service": "avatar",
        "version": "0.2.0",
    }


async def _check_redis() -> None:
    await get_redis_client().ping()


async def _check_database() -> None:
    async with get_engine().connect() as conn:
        await conn.execute(text("SELECT 1"))


@app.get("/ready", tags=["Health"])
async def readiness_check():
    """Readiness: Redis and Postgres answer. Load balancers route traffic only
    to instances that pass; 503 takes an instance out of rotation."""
    checks = {}
    for name, check in (("redis", _check_redis), ("database", _check_database)):
        try:
            await asyncio.wait_for(check(), timeout=2)
            checks[name] = "ok"
        except Exception as e:
            logger.warning(f"Readiness check {name} failed: {e!r}")
            checks[name] = "unavailable"
    ready = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "checks": checks},
    )


def main():
    """Run the Avatar Service HTTP API.

    For the LiveKit agent server, run:
        python -m agents.entrypoint dev
    """
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
