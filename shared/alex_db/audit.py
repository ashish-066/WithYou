"""Append-only audit trail (who did what)."""

import logging
from typing import Any

from alex_db.models import AuditEvent
from alex_db.session import session_scope

logger = logging.getLogger(__name__)


async def record(
    action: str,
    *,
    actor_type: str,
    actor_id: str | None = None,
    org_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    ip: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Write an audit event. Never raises: auditing must not break the action."""
    try:
        async with session_scope() as db:
            db.add(
                AuditEvent(
                    action=action,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    org_id=org_id,
                    target_type=target_type,
                    target_id=target_id,
                    ip=ip,
                    details=details,
                )
            )
    except Exception as e:
        logger.error(f"Failed to write audit event {action}: {e}")
