"""Live call tracking in Redis (shared by all API instances, survives restarts).

    call:{call_id}               JSON record of a live call
    call_session:{session_id}    call_id of that session's live call
    call_ended:{call_id}         session_id, briefly, so duplicate "end" requests succeed

Records expire after CALL_TTL so abandoned calls don't linger.
"""

import json

from core.redis import get_redis_client

CALL_TTL_SECONDS = 12 * 3600
RECENTLY_ENDED_TTL_SECONDS = 60


async def save(call: dict) -> None:
    redis = get_redis_client()
    pipe = redis.pipeline(transaction=True)
    pipe.set(f"call:{call['call_id']}", json.dumps(call), ex=CALL_TTL_SECONDS)
    pipe.set(f"call_session:{call['session_id']}", call["call_id"], ex=CALL_TTL_SECONDS)
    await pipe.execute()


async def get(call_id: str) -> dict | None:
    raw = await get_redis_client().get(f"call:{call_id}")
    return json.loads(raw) if raw else None


async def get_by_session(session_id: str) -> dict | None:
    call_id = await get_redis_client().get(f"call_session:{session_id}")
    return await get(call_id) if call_id else None


async def claim_for_ending(call_id: str) -> dict | None:
    """Atomically take the call out of the live set. Only one caller gets it."""
    redis = get_redis_client()
    raw = await redis.getdel(f"call:{call_id}")
    if not raw:
        return None
    call = json.loads(raw)
    pipe = redis.pipeline(transaction=True)
    pipe.delete(f"call_session:{call['session_id']}")
    pipe.set(f"call_ended:{call_id}", call["session_id"], ex=RECENTLY_ENDED_TTL_SECONDS)
    await pipe.execute()
    return call


async def recently_ended(call_id: str) -> bool:
    return bool(await get_redis_client().exists(f"call_ended:{call_id}"))


async def forget_ended(call_id: str) -> None:
    await get_redis_client().delete(f"call_ended:{call_id}")
