"""Study a textbook page: the learner photographs a page, Gemini reads it.

POST /pages/read  {image: data-URL (jpeg/png/webp), language}
  -> {page_id, topic, points[], summary}
The page (text + key ideas) is kept in Redis for a day under page:{user}:{id};
POST /calls/ with page_id starts a session that teaches from exactly that page.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.rate_limit import rate_limit
from core.auth import User, require_user
from core.config import settings
from core.redis import get_redis_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pages", tags=["Pages"])

PAGE_TTL = 24 * 3600
MAX_IMAGE_BYTES = 6 * 1024 * 1024
LANGUAGE_NAMES = {"ml-IN": "Malayalam", "te-IN": "Telugu", "ta-IN": "Tamil", "hi-IN": "Hindi", "en-IN": "English"}

PROMPT = """This is a photo of a school textbook or notes page (it may be in English, Malayalam, Telugu, Tamil or Hindi).
Read it and return JSON only:
{{
  "is_study_page": true/false,   // false if it is not study material or unreadable
  "topic": "short topic name, max 6 words, in {language}",
  "points": ["2 to 4 key ideas a student must understand from THIS page, each one short sentence, in {language}"],
  "summary": "one friendly sentence on what the page is about, in {language}",
  "page_text": "the page's important text, cleaned up, max 1500 characters, original language"
}}
English technical terms are fine inside {language}."""


class ReadPageRequest(BaseModel):
    image: str = Field(..., max_length=9_000_000)  # data URL
    language: str = "en-IN"


class PageResponse(BaseModel):
    page_id: str
    topic: str
    points: list[str]
    summary: str


def _decode(data_url: str) -> tuple[str, bytes]:
    m = re.match(r"^data:(image/(?:jpeg|png|webp));base64,(.+)$", data_url, re.S)
    if not m:
        raise HTTPException(400, "Send a JPEG, PNG or WebP photo.")
    try:
        raw = base64.b64decode(m.group(2), validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "The photo could not be read.") from None
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "The photo is too big.")
    return m.group(1), raw


def _parse(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


async def _gemini(mime: str, raw: bytes, language: str) -> dict:
    if not settings.google_api_key:
        raise HTTPException(503, "Reading pages is not set up.")
    body = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": mime, "data": base64.b64encode(raw).decode()}},
                {"text": PROMPT.format(language=LANGUAGE_NAMES.get(language, "English"))},
            ]
        }],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    # Lite models read a page in ~2 s; the next one is the backup when one is busy
    for model in [m.strip() for m in settings.page_models.split(",") if m.strip()]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(url, params={"key": settings.google_api_key}, json=body)
            if r.status_code != 200:
                logger.warning(f"Page read with {model} failed: {r.status_code} {r.text[:200]}")
                continue
            text = "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"])
            data = _parse(text)
            if data:
                return data
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            logger.warning(f"Page read with {model} failed: {type(e).__name__}")
    raise HTTPException(502, "Couldn't read the page right now. Try again.")


@router.post("/read", response_model=PageResponse, dependencies=[Depends(rate_limit("read_page", 15, 600))])
async def read_page(request: ReadPageRequest, user: User = Depends(require_user)) -> PageResponse:
    mime, raw = _decode(request.image)
    data = await _gemini(mime, raw, request.language)
    points = [str(p).strip()[:200] for p in data.get("points") or [] if str(p).strip()][:4]
    topic = str(data.get("topic") or "").strip()[:120]
    if not data.get("is_study_page", True) or not topic or not points:
        raise HTTPException(422, "That doesn't look like a study page. Try a clearer photo.")
    page = {
        "topic": topic,
        "points": points,
        "summary": str(data.get("summary") or "").strip()[:300],
        "page_text": str(data.get("page_text") or "").strip()[:1500],
    }
    page_id = uuid.uuid4().hex[:12]
    redis = get_redis_client()
    try:
        await redis.set(f"page:{user.user_id}:{page_id}", json.dumps(page, ensure_ascii=False), ex=PAGE_TTL)
    finally:
        await redis.aclose()
    return PageResponse(page_id=page_id, topic=topic, points=points, summary=page["summary"])


async def load_page(user_id: str, page_id: str) -> dict | None:
    """A page this learner read (None if unknown / expired / someone else's)."""
    if not re.fullmatch(r"[0-9a-f]{12}", page_id or ""):
        return None
    redis = get_redis_client()
    try:
        raw = await redis.get(f"page:{user_id}:{page_id}")
    finally:
        await redis.aclose()
    return json.loads(raw) if raw else None
