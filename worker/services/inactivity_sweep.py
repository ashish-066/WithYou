"""Close interviews that nobody is attending.

The voice agent ends interviews after silence or an absence, but if the
candidate's browser and the agent both disappear, nothing would. This sweep
(one worker at a time) asks the worker to end any interview with no activity
for a while, so every interview reaches an end and gets a report.
"""

import logging
from datetime import UTC, datetime

from redis.asyncio import Redis

from core.config import settings

logger = logging.getLogger(__name__)

LOCK_KEY = "sweep:inactive:lock"
# Remember sessions already asked to end, so they're not asked again each sweep
ASKED_KEY = "sweep:inactive:asked:{session_id}"


def _age_minutes(iso: str | None, now: datetime) -> float | None:
    if not iso:
        return None
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=UTC)
    return (now - then).total_seconds() / 60


async def sweep_inactive(redis: Redis, now: datetime | None = None) -> list[str]:
    """Ask the worker to end idle interviews. Returns the session ids asked."""
    now = now or datetime.now(UTC)
    # One worker sweeps at a time
    if not await redis.set(LOCK_KEY, settings.worker_id, nx=True, ex=max(10, settings.inactivity_sweep_seconds - 5)):
        return []

    asked: list[str] = []
    async for key in redis.scan_iter(match=settings.context_key.format(session_id="*"), count=200):
        session_id = key.split(":", 1)[1]
        ended, last_updated, report_status, attempts = await redis.hmget(
            key, "interview_ended", "last_updated", "report_status", "report_attempts"
        )
        if str(ended).lower() in ("1", "true"):
            # Ended without a report: try again (a few times, a couple of minutes apart)
            age = _age_minutes(last_updated, now)
            if (
                report_status == "failed"
                and int(attempts or 0) < settings.report_retry_attempts
                and age is not None
                and age >= settings.report_retry_minutes
                and await redis.set(f"sweep:report:{session_id}:{attempts or 0}", "1", nx=True, ex=3600)
            ):
                await redis.xadd(
                    settings.request_stream,
                    {"session_id": session_id, "message_type": "regenerate_report", "content": "",
                     "timestamp": now.isoformat(), "source": "inactivity_sweep"},
                    maxlen=settings.stream_maxlen, approximate=True,
                )
                logger.warning(f"Retrying the report for {session_id} (attempt {int(attempts or 0) + 1})")
            continue
        age = _age_minutes(last_updated, now)
        if age is None or age < settings.inactivity_end_minutes:
            continue
        if not await redis.set(ASKED_KEY.format(session_id=session_id), "1", nx=True, ex=3600):
            continue
        await redis.xadd(
            settings.request_stream,
            {
                "session_id": session_id,
                "message_type": "end_call",
                "content": "",
                "timestamp": now.isoformat(),
                "source": "inactivity_sweep",
                "end_reason": "abandoned",
            },
            maxlen=settings.stream_maxlen,
            approximate=True,
        )
        asked.append(session_id)
        logger.warning(f"Ending idle interview {session_id} (no activity for {age:.0f} min)")
    return asked
