"""Admin API routes for dashboard functionality.

Provides endpoints for:
- Worker monitoring and metrics
- Session listing and detail views
- Ops statistics and real-time SSE streams
- Scalability demo orchestration
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException

from api.admin_schemas import (
    DemoConfig,
    DemoStatus,
    SessionListResponse,
    SessionSummary,
    StreamStats,
)
from core.auth import (
    AuthStore,
    User,
    require_platform_admin,
    require_user,
)
from core.config import settings
from core.redis import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])

# Key patterns (matching worker service)
HEARTBEAT_KEY_PREFIX = "worker:heartbeat"
METRICS_KEY_PREFIX = "worker:metrics"
CONTEXT_KEY_PREFIX = "context"


# =============================================================================
# Helper Functions
# =============================================================================


async def _get_workers(redis) -> list[dict]:
    """Get all registered workers from Redis."""
    workers = []
    cursor = 0

    while True:
        cursor, keys = await redis.scan(
            cursor, match=f"{HEARTBEAT_KEY_PREFIX}:*", count=100
        )
        for key in keys:
            data = await redis.get(key)
            if data:
                try:
                    workers.append(json.loads(data))
                except json.JSONDecodeError:
                    pass
        if cursor == 0:
            break

    return workers


async def _get_session_ids(redis) -> list[str]:
    """Get all session IDs from Redis."""
    sessions = []
    cursor = 0

    while True:
        cursor, keys = await redis.scan(
            cursor, match=f"{CONTEXT_KEY_PREFIX}:*", count=100
        )
        for key in keys:
            # Extract session_id from key like "context:session-abc123"
            session_id = key.split(":", 1)[1] if ":" in key else key
            sessions.append(session_id)
        if cursor == 0:
            break

    return sessions


async def _get_session_state(redis, session_id: str) -> dict | None:
    """Get full session state from Redis hash."""
    key = f"{CONTEXT_KEY_PREFIX}:{session_id}"
    data = await redis.hgetall(key)

    if not data:
        return None

    # Parse JSON fields
    json_fields = [
        "messages",
        "message_summary",
        "topics_covered",
        "running_scores",
        "tool_results",
        "tool_queue",
        "pending_claims",
        "verified_claims",
        "candidate_profile",
        "timestamp_notes",
        "descriptive_report",
        "analytics_data",
        "dfa",
        "candidate_urls",
        "suggested_tools",
        "suggested_tool_params",
        "pending_slow_tasks",
        "completed_slow_tasks",
        "skill_tree",
        "cheat_flags",
        "integrity_report",
    ]

    result = {}
    for k, v in data.items():
        if k in json_fields:
            try:
                result[k] = json.loads(v) if v else None
            except json.JSONDecodeError:
                result[k] = v
        elif k in ("turn_count", "max_turns"):
            result[k] = int(v) if v else 0
        elif k in ("trust_score", "routing_confidence", "integrity_score"):
            result[k] = float(v) if v else 0.0
        elif k == "interview_ended":
            result[k] = v.lower() == "true" if v else False
        else:
            result[k] = v

    result["session_id"] = session_id
    return result


async def _get_stream_stats(redis, stream_name: str) -> StreamStats:
    """Get statistics for a Redis stream."""
    try:
        info = await redis.xinfo_stream(stream_name)

        # Get pending count
        pending = 0
        try:
            groups = await redis.xinfo_groups(stream_name)
            for group in groups:
                pending += group.get("pending", 0)
        except Exception:
            pass

        return StreamStats(
            length=info.get("length", 0),
            first_entry_id=info.get("first-entry", [None])[0]
            if info.get("first-entry")
            else None,
            last_entry_id=info.get("last-entry", [None])[0]
            if info.get("last-entry")
            else None,
            consumer_groups=info.get("groups", 0),
            pending_messages=pending,
        )
    except Exception as e:
        # Stream doesn't exist yet - this is normal on startup
        logger.debug(f"Stream {stream_name} not found or empty: {e}")
        return StreamStats()


# =============================================================================
# Session Endpoints
# =============================================================================


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(user: User = Depends(require_user), own_org_only: bool = False):
    """List interview sessions of the caller's organization (all, for platform admins).

    own_org_only: platform admins also get only their own organization's sessions
    (the organization workspace uses this; the platform console doesn't).
    """
    redis = get_redis_client()
    try:
        session_ids = await _get_session_ids(redis)
        if not user.is_platform_admin or own_org_only:
            own = await AuthStore().org_session_ids(user.org_id)
            session_ids = [sid for sid in session_ids if sid in own]
        sessions = []
        active_count = 0

        for session_id in session_ids:
            state = await _get_session_state(redis, session_id)
            if state:
                is_active = not state.get("interview_ended", False)
                if is_active:
                    active_count += 1

                sessions.append(
                    SessionSummary(
                        session_id=session_id,
                        candidate_id=state.get("candidate_id"),
                        turn_count=state.get("turn_count", 0),
                        max_turns=state.get("max_turns", 20),
                        brain_mode=state.get("brain_mode", "idle"),
                        interview_ended=state.get("interview_ended", False),
                        trust_score=state.get("trust_score", 1.0),
                        integrity_score=state.get("integrity_score", 1.0),
                        started_at=state.get("started_at"),
                        last_updated=state.get("last_updated"),
                    )
                )

        # Sort by last_updated descending
        sessions.sort(key=lambda s: s.last_updated or "", reverse=True)

        return SessionListResponse(
            total_sessions=len(sessions),
            active_sessions=active_count,
            sessions=sessions,
        )
    finally:
        await redis.aclose()


# =============================================================================
# Demo Endpoints (to be implemented with orchestrator)
# =============================================================================

# Global demo state (will be replaced with proper orchestrator)
_demo_status = DemoStatus()


def _require_demo(user: User = Depends(require_platform_admin)) -> User:
    if not settings.demo_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    return user


@router.post("/demo/start", response_model=DemoStatus, dependencies=[Depends(_require_demo)])
async def start_demo(config: DemoConfig | None = None):
    """Start the scalability demo."""
    global _demo_status

    if _demo_status.running:
        raise HTTPException(status_code=400, detail="Demo already running")

    # Use defaults if no config provided
    if config is None:
        config = DemoConfig()

    # Import here to avoid circular imports
    from services.demo_orchestrator import demo_orchestrator

    try:
        _demo_status = await demo_orchestrator.start_demo(config)
        return _demo_status
    except Exception as e:
        logger.error(f"Failed to start demo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/demo/stop", response_model=DemoStatus, dependencies=[Depends(_require_demo)])
async def stop_demo():
    """Stop the scalability demo."""
    global _demo_status

    if not _demo_status.running:
        return _demo_status

    from services.demo_orchestrator import demo_orchestrator

    try:
        _demo_status = await demo_orchestrator.stop_demo()
        return _demo_status
    except Exception as e:
        logger.error(f"Failed to stop demo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/demo/status", response_model=DemoStatus, dependencies=[Depends(_require_demo)])
async def get_demo_status():
    """Get current demo status including ELO leaderboard."""
    from services.demo_orchestrator import demo_orchestrator

    return await demo_orchestrator.get_status()
