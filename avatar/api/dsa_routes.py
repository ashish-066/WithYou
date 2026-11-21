"""Admin API routes for DSA problem management.

Provides CRUD endpoints for DSA problem packets:
    POST   /admin/dsa/problems/         - Create a new problem
    GET    /admin/dsa/problems/         - List all problems (metadata only)
    GET    /admin/dsa/problems/{id}     - Get full problem (examiner view)
    PUT    /admin/dsa/problems/{id}     - Update a problem
    DELETE /admin/dsa/problems/{id}     - Delete a problem

Candidate-safe endpoints (used by frontend in DSA interview room; recruiters
or candidates with an active interview):
    GET    /admin/dsa/problems/{id}/public - Get candidate-safe view

Reading needs a signed-in recruiter; creating/changing the shared problem
library needs a platform admin. Do NOT expose reference solutions to candidates.
The /public endpoint only returns DSAProblemPublic (no ground truth).

Implementation note on sys.path:
    dsa.* modules live in worker/ rather than avatar/.
    We inject worker/ into sys.path BEFORE importing dsa.* — then immediately
    remove it so the avatar's own 'services' namespace is never shadowed.
    The imported module objects are cached in module-level variables and reused.
"""

import logging
import os
import sys

from fastapi import APIRouter, Depends, HTTPException

from core.auth import require_platform_admin, require_signed_in, require_user
from core.redis import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/dsa", tags=["DSA Problems"])

# ---------------------------------------------------------------------------
# One-time import of dsa.* under worker/ path context
# ---------------------------------------------------------------------------
_WORKER_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "worker")
)

_inserted = _WORKER_DIR not in sys.path
if _inserted:
    sys.path.insert(0, _WORKER_DIR)

try:
    from dsa.models import DSAProblem as _DSAProblem  # noqa: E402
    from dsa.problem_store import DSAProblemStore as _DSAProblemStore  # noqa: E402
    _DSA_AVAILABLE = True
except ImportError as _e:
    logger.warning(f"DSA modules not importable: {_e}")
    _DSA_AVAILABLE = False
    _DSAProblem = None  # type: ignore
    _DSAProblemStore = None  # type: ignore
finally:
    # Remove worker/ immediately so avatar's 'services' package is never shadowed
    if _inserted and _WORKER_DIR in sys.path:
        sys.path.remove(_WORKER_DIR)


def _require_dsa():
    if not _DSA_AVAILABLE:
        raise HTTPException(status_code=503, detail="DSA modules not available")


# =============================================================================
# Problem CRUD
# =============================================================================


@router.post("/problems/", dependencies=[Depends(require_platform_admin)])
async def create_dsa_problem(problem_data: dict) -> dict:
    """Create a new DSA problem packet.

    The request body is the full DSAProblem schema (JSON).
    Includes reference solution, hidden test cases, scoring rubric etc.

    This endpoint is ADMIN ONLY. Do not expose to candidates.
    """
    _require_dsa()
    redis = get_redis_client()
    try:
        try:
            problem = _DSAProblem.model_validate(problem_data)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Invalid problem schema: {e}")

        store = _DSAProblemStore(redis)
        try:
            created = await store.create(problem)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        logger.info(f"Created DSA problem via API: {created.problem_id}")
        return created.model_dump()
    finally:
        await redis.aclose()


@router.get("/problems/", dependencies=[Depends(require_user)])
async def list_dsa_problems() -> list[dict]:
    """List all DSA problems (metadata only — no reference solutions)."""
    _require_dsa()
    redis = get_redis_client()
    try:
        store = _DSAProblemStore(redis)
        return await store.list_all()
    finally:
        await redis.aclose()


@router.get("/problems/{problem_id}", dependencies=[Depends(require_user)])
async def get_dsa_problem(problem_id: str) -> dict:
    """Get the full DSA problem (ADMIN only — includes reference solution)."""
    _require_dsa()
    redis = get_redis_client()
    try:
        store = _DSAProblemStore(redis)
        problem = await store.get(problem_id)
        if not problem:
            raise HTTPException(status_code=404, detail=f"Problem '{problem_id}' not found")
        return problem.model_dump()
    finally:
        await redis.aclose()


@router.get("/problems/{problem_id}/public", dependencies=[Depends(require_signed_in)])
async def get_dsa_problem_public(problem_id: str) -> dict:
    """Get the candidate-safe view of a DSA problem.

    Strips reference solution, hidden test cases, and scoring rubric.
    Safe to expose to the candidate's interview room frontend.
    """
    _require_dsa()
    redis = get_redis_client()
    try:
        store = _DSAProblemStore(redis)
        problem = await store.get_public(problem_id)
        if not problem:
            raise HTTPException(status_code=404, detail=f"Problem '{problem_id}' not found")
        return problem.model_dump()
    finally:
        await redis.aclose()


@router.put("/problems/{problem_id}", dependencies=[Depends(require_platform_admin)])
async def update_dsa_problem(problem_id: str, problem_data: dict) -> dict:
    """Update an existing DSA problem."""
    _require_dsa()
    redis = get_redis_client()
    try:
        try:
            problem = _DSAProblem.model_validate(problem_data)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Invalid problem schema: {e}")

        if problem.problem_id != problem_id:
            raise HTTPException(
                status_code=400,
                detail="problem_id in URL must match problem_id in body",
            )

        store = _DSAProblemStore(redis)
        try:
            updated = await store.update(problem)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

        logger.info(f"Updated DSA problem via API: {problem_id}")
        return updated.model_dump()
    finally:
        await redis.aclose()


@router.delete("/problems/{problem_id}", dependencies=[Depends(require_platform_admin)])
async def delete_dsa_problem(problem_id: str) -> dict:
    """Delete a DSA problem."""
    _require_dsa()
    redis = get_redis_client()
    try:
        store = _DSAProblemStore(redis)
        deleted = await store.delete(problem_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Problem '{problem_id}' not found")
        return {"deleted": True, "problem_id": problem_id}
    finally:
        await redis.aclose()
