"""Show saved session text in the language the learner is using now.

A session's recap and concepts are written in that session's language; the app
may be set to another (a Malayalam session, viewed in Telugu). Translated with
Sarvam Translate (`sarvam-translate:v1`, POST /translate), cached in Redis so a
string is translated once. Any failure shows the original text: never an error.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging

import httpx

from agents import language as lang
from core.config import settings
from core.redis import get_redis_client

logger = logging.getLogger(__name__)

URL = "https://api.sarvam.ai/translate"
CACHE_TTL_S = 30 * 24 * 3600
_LIMIT = asyncio.Semaphore(6)  # parallel requests per API process


def _key(text: str, target: str) -> str:
    return f"translate:{target}:{hashlib.sha256(text.encode()).hexdigest()[:32]}"


def needs_translation(text: str | None, target: str) -> bool:
    """Only text that isn't already in the target language (by script)."""
    if not text or not text.strip():
        return False
    return lang.language_of(text, default=target) != target


async def translate(text: str | None, target: str) -> str | None:
    if not needs_translation(text, target) or not settings.sarvam_api_key:
        return text
    redis = get_redis_client()
    try:
        cached = await redis.get(_key(text, target))
        if cached:
            return cached
    except Exception:
        cached = None
    source = lang.language_of(text, default="en-IN")
    try:
        async with _LIMIT, httpx.AsyncClient(timeout=8) as http:
            r = await http.post(
                URL,
                headers={"api-subscription-key": settings.sarvam_api_key},
                json={
                    "input": text[:1000],
                    "source_language_code": source,
                    "target_language_code": target,
                    "model": "sarvam-translate:v1",
                },
            )
            r.raise_for_status()
            out = (r.json().get("translated_text") or "").strip() or text
    except Exception as e:
        logger.warning(f"Translate {source}->{target} failed, showing original: {type(e).__name__}: {e}")
        return text
    try:
        await redis.set(_key(text, target), out, ex=CACHE_TTL_S)
    except Exception:
        pass
    return out


async def translate_many(texts: list[str | None], target: str) -> list[str | None]:
    return list(await asyncio.gather(*(translate(t, target) for t in texts)))
