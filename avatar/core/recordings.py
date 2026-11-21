"""Interview recordings in private object storage.

Recordings are written by LiveKit egress to a private bucket (enable default
encryption on the bucket). They are never exposed by a stored public URL:
viewers get a short-lived signed URL generated on request, after an access
check.
"""

import logging
from pathlib import Path

import boto3
from botocore.config import Config

from core.config import settings

logger = logging.getLogger(__name__)

SIGNED_URL_TTL_SECONDS = 15 * 60


def recording_key(session_id: str, room_name: str) -> str:
    return f"recordings/{session_id}/{room_name}.mp4"


def storage_configured() -> bool:
    return bool(settings.s3_bucket and settings.s3_access_key and settings.s3_secret_key)


def _client():
    return boto3.client(
        "s3",
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        endpoint_url=settings.s3_endpoint or None,
        config=Config(signature_version="s3v4"),
    )


def signed_url(key: str, ttl_seconds: int = SIGNED_URL_TTL_SECONDS) -> str | None:
    """A temporary GET link for one recording (signing is local; no network call)."""
    if not storage_configured():
        return None
    client = _client()
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket, "Key": key},
            ExpiresIn=ttl_seconds,
        )
    except Exception as e:
        logger.error(f"Could not sign recording URL: {e}")
        return None


# =============================================================================
# Evidence photos (camera checks: phone, another person, another laptop)
# =============================================================================
# Stored next to the recording, under the same interview, and only served
# through the API after an access check (every view audited). Without cloud
# storage (local development) they go to a local folder instead.

LOCAL_EVIDENCE_DIR = Path(__file__).resolve().parent.parent / ".local-evidence"


def evidence_key(session_id: str, flag_id: str) -> str:
    return f"evidence/{session_id}/{flag_id}.jpg"


def _local_path(key: str) -> Path | None:
    if settings.environment == "production":
        return None
    path = (LOCAL_EVIDENCE_DIR / key).resolve()
    return path if LOCAL_EVIDENCE_DIR in path.parents else None


def put_evidence(key: str, jpeg: bytes) -> bool:
    if storage_configured():
        try:
            _client().put_object(
                Bucket=settings.s3_bucket, Key=key, Body=jpeg, ContentType="image/jpeg",
                ServerSideEncryption="AES256",
            )
            return True
        except Exception as e:
            logger.error(f"Could not store evidence photo {key}: {e}")
            return False
    path = _local_path(key)
    if path is None:
        logger.warning(f"No storage for evidence photo {key}; not kept")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(jpeg)
    return True


def get_evidence(key: str) -> bytes | None:
    if storage_configured():
        try:
            return _client().get_object(Bucket=settings.s3_bucket, Key=key)["Body"].read()
        except Exception as e:
            logger.warning(f"Evidence photo {key} not available: {e}")
            return None
    path = _local_path(key)
    return path.read_bytes() if path is not None and path.is_file() else None
