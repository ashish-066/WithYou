"""FastAPI route definitions for Avatar Service.

Provides endpoints for video call management via LiveKit/BeyondPresence
and proctoring/anti-cheating functionality.
"""

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from api.call_routes import router as call_router
from api.proctoring_routes import router as proctoring_router
from core.auth import (
    AuthStore,
    Candidate,
    User,
    invite_is_expired,
    optional_candidate,
    optional_user,
    read_invite_token,
)
from core.rate_limit import rate_limit
from services.ocr import extract_text_from_file

logger = logging.getLogger(__name__)


router = APIRouter()

# Include call management routes
router.include_router(call_router)

# Include proctoring/anti-cheating routes
router.include_router(proctoring_router)


MAX_RESUME_BYTES = 5 * 1024 * 1024

# Detected from the file's first bytes, not the client-supplied content type
_MAGIC_TYPES = (
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)


def _detect_type(content: bytes) -> str | None:
    for magic, content_type in _MAGIC_TYPES:
        if content.startswith(magic):
            return content_type
    return None


async def _invite_is_usable(token: str | None) -> bool:
    invite_id = read_invite_token(token) if token else None
    invite = await AuthStore().get_invite(invite_id) if invite_id else None
    return bool(invite and not invite["used_session_id"] and not invite_is_expired(invite))


@router.post(
    "/resumes/upload",
    tags=["Resumes"],
    dependencies=[Depends(rate_limit("resume_upload", 10, 600))],
)
async def upload_resume(
    file: UploadFile = File(...),
    invite_token: str | None = Form(default=None, max_length=2048),
    user: User | None = Depends(optional_user),
    candidate: Candidate | None = Depends(optional_candidate),
):
    """Upload a resume file and extract text via OCR.

    Supports PDF, PNG and JPEG up to 5 MB. Allowed for signed-in recruiters,
    candidates in an interview, or with a valid unused invite (the setup screen
    uploads the resume before the call starts).
    Returns the extracted text to be passed to start_session.
    """
    if user is None and candidate is None and not await _invite_is_usable(invite_token):
        raise HTTPException(status_code=401, detail="An interview link is required")

    content = await file.read(MAX_RESUME_BYTES + 1)
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=413, detail="Resume must be 5 MB or smaller")
    content_type = _detect_type(content)
    if content_type is None:
        raise HTTPException(status_code=415, detail="Upload a PDF, PNG or JPEG file")

    try:
        text = extract_text_from_file(content, content_type)
    except Exception as e:
        logger.error(f"Resume upload failed: {e}")
        raise HTTPException(status_code=500, detail="Could not read the resume") from e

    if not text:
        raise HTTPException(status_code=400, detail="Could not extract text from file")

    return {"resume_text": text, "filename": file.filename}
