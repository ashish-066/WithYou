"""Job role lookups shared by the role, call, invite and ranking routes."""

from alex_db import JobRole, session_scope

import core.db  # noqa: F401  (configures the database)


def role_dict(role: JobRole) -> dict:
    return {
        "role_id": role.id,
        "org_id": role.org_id,
        "role_title": role.role_title,
        "job_description": role.job_description,
        "is_active": role.is_active,
        "created_at": role.created_at.isoformat() if role.created_at else "",
        "updated_at": role.updated_at.isoformat() if role.updated_at else None,
    }


async def get_role(role_id: str) -> dict | None:
    async with session_scope() as db:
        role = await db.get(JobRole, role_id)
        return role_dict(role) if role else None
