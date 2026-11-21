"""FastAPI route definitions for the Avatar Service (call management)."""

from fastapi import APIRouter

from api.call_routes import router as call_router

router = APIRouter()
router.include_router(call_router)
