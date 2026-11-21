"""Sign-in for learners.

    POST /auth/signup            create an account (+ its personal organization), if enabled
    POST /auth/login             email + password -> session cookie
    POST /auth/logout            clear cookies
    GET  /auth/me                current user
    GET  /auth/config            what the sign-in page should offer
"""

import logging

from alex_db.audit import record
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from core.auth import (
    AuthStore,
    User,
    clear_cookies,
    normalize_email,
    require_user,
    set_user_cookie,
)
from core.config import settings
from core.rate_limit import client_ip, rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

def _store() -> AuthStore:
    return AuthStore()


class _Email(BaseModel):
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def _looks_like_email(cls, v: str) -> str:
        v = v.strip()
        local, _, domain = v.partition("@")
        if not local or "." not in domain or " " in v:
            raise ValueError("Enter a valid email address")
        return v


class SignupRequest(_Email):
    # Optional: each learner gets a personal organization named after them
    org_name: str | None = Field(default=None, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=256)


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


def _public_user(user: User | dict) -> dict:
    if isinstance(user, dict):
        return {
            "user_id": user["user_id"],
            "email": user["email"],
            "name": user.get("name", ""),
            "role": user.get("role", "recruiter"),
            "org_id": user["org_id"],
            "is_platform_admin": bool(user.get("is_platform_admin")),
        }
    return {
        "user_id": user.user_id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "org_id": user.org_id,
        "is_platform_admin": user.is_platform_admin,
    }


# =============================================================================
# Sign-in
# =============================================================================


@router.post("/signup", dependencies=[Depends(rate_limit("signup", 5, 3600))])
async def signup(request: SignupRequest, response: Response, http: Request) -> dict:
    if not settings.signup_enabled:
        raise HTTPException(status_code=403, detail="Sign-up is disabled")
    store = _store()
    org_id = await store.create_org((request.org_name or "").strip() or request.name.strip())
    try:
        user_id = await store.create_user(
            email=request.email,
            name=request.name.strip(),
            password=request.password,
            org_id=org_id,
            role="admin",
        )
    except ValueError as e:
        await store.delete_org(org_id)  # don't leave an organization without members
        raise HTTPException(status_code=409, detail=str(e)) from e
    set_user_cookie(response, user_id)
    logger.info(f"New organization {org_id} created by {user_id}")
    await record("auth.signup", actor_type="user", actor_id=user_id, org_id=org_id,
                 ip=client_ip(http))
    return _public_user(await store.get_user(user_id))


@router.post("/login", dependencies=[Depends(rate_limit("login", 10, 300))])
async def login(request: LoginRequest, response: Response, http: Request) -> dict:
    user = await _store().authenticate(request.email, request.password)
    if user is None:
        await record("auth.login_failed", actor_type="anonymous", ip=client_ip(http),
                     details={"email": normalize_email(request.email)[:254]})
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    set_user_cookie(response, user["user_id"])
    await record("auth.login", actor_type="user", actor_id=user["user_id"],
                 org_id=user["org_id"], ip=client_ip(http))
    return _public_user(user)


@router.post("/logout")
async def logout(response: Response) -> dict:
    clear_cookies(response)
    return {"ok": True}


@router.get("/me")
async def me(user: User = Depends(require_user)) -> dict:
    org = await _store().get_org(user.org_id)
    return {**_public_user(user), "org_name": (org or {}).get("name", "")}


@router.get("/config")
async def auth_config() -> dict:
    """What the sign-in page should offer."""
    return {"signup_enabled": settings.signup_enabled}
