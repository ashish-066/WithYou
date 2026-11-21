"""Job role management API routes.

Provides endpoints for CRUD operations on job roles/positions.
These roles can be selected during interview creation instead of
requiring candidates to enter job descriptions.

Roles are stored in Postgres and belong to the organization that created
them; role ids are global (rankings key on them), so an id can only be
claimed once.
"""

import logging
from datetime import UTC, datetime

from alex_db import JobRole, session_scope
from alex_db.audit import record
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from api.admin_schemas import (
    JobRoleCreate,
    JobRoleListResponse,
    JobRoleResponse,
    JobRoleUpdate,
)
from core.auth import User, require_user
from core.roles import role_dict

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/roles", tags=["Job Roles"])


def _response(role: JobRole) -> JobRoleResponse:
    data = role_dict(role)
    return JobRoleResponse(
        role_id=data["role_id"],
        role_title=data["role_title"],
        job_description=data["job_description"],
        is_active=data["is_active"],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )


async def _owned_role(db, role_id: str, user: User) -> JobRole:
    """The role if the caller's organization owns it (404 otherwise)."""
    role = await db.get(JobRole, role_id)
    if role is None or not user.can_access_org(role.org_id):
        raise HTTPException(status_code=404, detail=f"Role '{role_id}' not found")
    return role


@router.post("/", response_model=JobRoleResponse)
async def create_role(
    request: JobRoleCreate, user: User = Depends(require_user)
) -> JobRoleResponse:
    """Create a new job role.

    Args:
        request: Job role creation request

    Returns:
        Created job role details
    """
    try:
        async with session_scope() as db:
            role = JobRole(
                id=request.role_id,
                org_id=user.org_id,
                role_title=request.role_title,
                job_description=request.job_description,
                is_active=request.is_active,
            )
            db.add(role)
            await db.flush()
            await db.refresh(role)
            response = _response(role)
    except IntegrityError as e:
        # Primary key: two organizations must not end up with the same role id
        raise HTTPException(
            status_code=400,
            detail=f"Role with ID '{request.role_id}' already exists",
        ) from e

    logger.info(f"Created job role: {request.role_id}")
    await record(
        "role.create", actor_type="user", actor_id=user.user_id, org_id=user.org_id,
        target_type="job_role", target_id=request.role_id,
    )
    return response


@router.get("/", response_model=JobRoleListResponse)
async def list_roles(
    active_only: bool = True, user: User = Depends(require_user)
) -> JobRoleListResponse:
    """List the caller's organization's job roles.

    Args:
        active_only: If True, only return active roles

    Returns:
        List of job roles
    """
    query = select(JobRole).order_by(JobRole.created_at.desc())
    if not user.is_platform_admin:
        query = query.where(JobRole.org_id == user.org_id)
    if active_only:
        query = query.where(JobRole.is_active.is_(True))

    async with session_scope() as db:
        roles = [_response(r) for r in await db.scalars(query)]

    return JobRoleListResponse(total_roles=len(roles), roles=roles)


@router.get("/{role_id}", response_model=JobRoleResponse)
async def get_role(role_id: str, user: User = Depends(require_user)) -> JobRoleResponse:
    """Get a specific job role by ID.

    Args:
        role_id: The role identifier

    Returns:
        Job role details
    """
    async with session_scope() as db:
        return _response(await _owned_role(db, role_id, user))


@router.put("/{role_id}", response_model=JobRoleResponse)
async def update_role(
    role_id: str, request: JobRoleUpdate, user: User = Depends(require_user)
) -> JobRoleResponse:
    """Update an existing job role.

    Args:
        role_id: The role identifier
        request: Update request with fields to change

    Returns:
        Updated job role details
    """
    async with session_scope() as db:
        role = await _owned_role(db, role_id, user)
        changed = False
        if request.role_title is not None:
            role.role_title = request.role_title
            changed = True
        if request.job_description is not None:
            role.job_description = request.job_description
            changed = True
        if request.is_active is not None:
            role.is_active = request.is_active
            changed = True
        if changed:
            role.updated_at = datetime.now(UTC)
        await db.flush()
        response = _response(role)

    logger.info(f"Updated job role: {role_id}")
    await record(
        "role.update", actor_type="user", actor_id=user.user_id, org_id=user.org_id,
        target_type="job_role", target_id=role_id,
    )
    return response


@router.delete("/{role_id}")
async def delete_role(role_id: str, user: User = Depends(require_user)) -> dict:
    """Delete a job role.

    Args:
        role_id: The role identifier

    Returns:
        Success message
    """
    async with session_scope() as db:
        role = await _owned_role(db, role_id, user)
        await db.delete(role)

    logger.info(f"Deleted job role: {role_id}")
    await record(
        "role.delete", actor_type="user", actor_id=user.user_id, org_id=user.org_id,
        target_type="job_role", target_id=role_id,
    )
    return {"message": f"Role '{role_id}' deleted successfully"}
