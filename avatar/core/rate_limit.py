"""Fixed-window rate limiting backed by Redis.

Usage as a FastAPI dependency:

    @router.post("/login", dependencies=[Depends(rate_limit("login", 10, 60))])

The key is the client IP by default. Behind reverse proxies set
TRUSTED_PROXY_HOPS so the IP comes from X-Forwarded-For (see client_ip).
"""

from collections.abc import Callable

from fastapi import HTTPException, Request

from core.config import settings
from core.redis import get_redis_client


def client_ip(request: Request) -> str:
    """The caller's IP, trusting only the configured number of proxies.

    Each trusted proxy appends the address it received the request from, so the
    entry TRUSTED_PROXY_HOPS from the right is the one the outermost trusted
    proxy saw. Anything further left was sent by the client and can be forged.
    """
    hops = settings.trusted_proxy_hops
    if hops > 0:
        forwarded = [
            part.strip()
            for part in request.headers.get("x-forwarded-for", "").split(",")
            if part.strip()
        ]
        if forwarded:
            return forwarded[-hops] if len(forwarded) >= hops else forwarded[0]
    return request.client.host if request.client else "unknown"


def rate_limit(
    name: str,
    limit: int,
    window_seconds: int,
    key: Callable[[Request], str] = client_ip,
):
    async def dependency(request: Request) -> None:
        redis = get_redis_client()
        bucket = f"ratelimit:{name}:{key(request)}"
        count = await redis.incr(bucket)
        if count == 1:
            await redis.expire(bucket, window_seconds)
        if count > limit:
            ttl = await redis.ttl(bucket)
            raise HTTPException(
                status_code=429,
                detail="Too many requests, please slow down",
                headers={"Retry-After": str(max(ttl, 1))},
            )

    return dependency
