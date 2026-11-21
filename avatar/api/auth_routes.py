"""Sign-in, team members and candidate invites.

    POST /auth/signup            create an organization + its first admin (if enabled)
    POST /auth/login             email + password -> session cookie
    POST /auth/logout            clear cookies
    GET  /auth/me                current user
    GET  /auth/users             org members (org admin)
    POST /auth/users             add a team member (org admin)
    POST /auth/invites           create a single-use interview link (recruiter)
    GET  /auth/invites           org's invites with status (recruiter)
    POST /auth/invites/lookup    what an invite is for (public; token in body, not URL)
"""

import logging
from datetime import timedelta
from typing import Literal
from urllib.parse import urlparse

from alex_db.audit import record
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from core.auth import (
    ROLES,
    AuthStore,
    User,
    clear_cookies,
    generate_password,
    invite_is_expired,
    normalize_email,
    read_invite_token,
    require_org_admin,
    require_user,
    set_user_cookie,
)
from core.config import settings
from core.rate_limit import client_ip, rate_limit
from core.roles import get_role

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
    org_name: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=256)


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class NewUserRequest(_Email):
    name: str = Field(min_length=1, max_length=120)
    # Left out: the server generates a one-time password and returns it once
    password: str | None = Field(default=None, min_length=10, max_length=256)
    role: Literal["admin", "recruiter"] = "recruiter"


def _clean_url(value: str | None) -> str | None:
    """A web address (http/https) or nothing. Bare "github.com/x" gets https://."""
    value = (value or "").strip()
    if not value:
        return None
    if "://" not in value:
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or "." not in parsed.hostname:
        raise ValueError(f"Not a web address: {value}")
    return value


class InviteRequest(BaseModel):
    candidate_name: str = Field(min_length=1, max_length=120)
    candidate_email: str | None = Field(default=None, max_length=254)
    role_id: str | None = Field(default=None, max_length=120)
    interview_mode: Literal["round1", "round2_dsa"] = "round1"
    dsa_problem_id: str | None = Field(default=None, max_length=120)
    require_secure_app: bool = False
    expires_in_hours: int | None = Field(default=None, ge=1)
    # Candidate background (the interviewer asks about it and checks claims against it)
    github_url: str | None = Field(default=None, max_length=500)
    linkedin_url: str | None = Field(default=None, max_length=500)
    other_links: list[str] = Field(default_factory=list, max_length=10)
    resume_text: str | None = Field(default=None, max_length=100_000)
    linkedin_text: str | None = Field(default=None, max_length=100_000)

    @field_validator("github_url", "linkedin_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        return _clean_url(v)

    @field_validator("other_links")
    @classmethod
    def _links(cls, v: list[str]) -> list[str]:
        cleaned = [u for u in (_clean_url(x) for x in v) if u and len(u) <= 500]
        return list(dict.fromkeys(cleaned))  # no duplicates, order kept

    @field_validator("resume_text", "linkedin_text")
    @classmethod
    def _text(cls, v: str | None) -> str | None:
        return (v or "").strip() or None


class InviteLookup(BaseModel):
    token: str = Field(max_length=2048)


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


def _invite_status(invite: dict) -> str:
    if invite.get("used_session_id"):
        return "used"
    if invite.get("revoked_at"):
        return "revoked"
    if invite_is_expired(invite):
        return "expired"
    return "pending"


def _public_invite(invite: dict) -> dict:
    return {
        "invite_id": invite["invite_id"],
        "candidate_name": invite.get("candidate_name", ""),
        "candidate_email": invite.get("candidate_email", ""),
        "role_id": invite.get("role_id", ""),
        "role_title": invite.get("role_title", ""),
        "interview_mode": invite.get("interview_mode", "round1"),
        "dsa_problem_id": invite.get("dsa_problem_id", ""),
        "require_secure_app": invite.get("require_secure_app", False),
        "created_at": invite.get("created_at", ""),
        "expires_at": invite.get("expires_at", ""),
        "status": _invite_status(invite),
        "session_id": invite.get("used_session_id", ""),
        # Recruiters only (the candidate's lookup returns a fixed subset)
        "background": invite.get("background") or {},
    }


# =============================================================================
# Sign-in
# =============================================================================


@router.post("/signup", dependencies=[Depends(rate_limit("signup", 5, 3600))])
async def signup(request: SignupRequest, response: Response, http: Request) -> dict:
    if not settings.signup_enabled:
        raise HTTPException(status_code=403, detail="Sign-up is disabled")
    store = _store()
    org_id = await store.create_org(request.org_name.strip())
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
    """What the sign-in page and the dashboard should offer."""
    return {"signup_enabled": settings.signup_enabled, "demo_enabled": settings.demo_enabled}


# =============================================================================
# Team members
# =============================================================================


@router.get("/users")
async def list_users(user: User = Depends(require_org_admin)) -> dict:
    users = await _store().list_org_users(user.org_id)
    return {"users": [_public_user(u) for u in users]}


@router.post("/users")
async def add_user(request: NewUserRequest, user: User = Depends(require_org_admin)) -> dict:
    if request.role not in ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    store = _store()
    password = request.password or generate_password()
    try:
        user_id = await store.create_user(
            email=request.email,
            name=request.name.strip(),
            password=password,
            org_id=user.org_id,
            role=request.role,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    await record("user.create", actor_type="user", actor_id=user.user_id, org_id=user.org_id,
                 target_type="user", target_id=user_id, details={"role": request.role})
    created = _public_user(await store.get_user(user_id))
    if request.password is None:
        created["one_time_password"] = password
    return created


# =============================================================================
# Candidate invites
# =============================================================================


@router.post("/invites")
async def create_invite(request: InviteRequest, user: User = Depends(require_user)) -> dict:
    role_title = None
    if request.role_id:
        role = await get_role(request.role_id)
        if not role or not user.can_access_org(role.get("org_id")):
            raise HTTPException(status_code=404, detail="Role not found")
        role_title = role.get("role_title")
    if request.interview_mode == "round2_dsa" and not request.dsa_problem_id:
        raise HTTPException(status_code=400, detail="Choose a DSA problem for a coding round")

    hours = min(
        request.expires_in_hours or settings.invite_default_ttl_hours,
        settings.invite_max_ttl_hours,
    )
    invite_id, token, expires_at = await _store().create_invite(
        org_id=user.org_id,
        created_by=user.user_id,
        ttl=timedelta(hours=hours),
        candidate_name=request.candidate_name.strip(),
        candidate_email=request.candidate_email,
        role_id=request.role_id,
        role_title=role_title,
        interview_mode=request.interview_mode,
        dsa_problem_id=request.dsa_problem_id if request.interview_mode == "round2_dsa" else None,
        require_secure_app=request.require_secure_app,
        github_url=request.github_url,
        linkedin_url=request.linkedin_url,
        other_links=request.other_links,
        resume_text=request.resume_text,
        linkedin_text=request.linkedin_text,
    )
    await record("invite.create", actor_type="user", actor_id=user.user_id, org_id=user.org_id,
                 target_type="invite", target_id=invite_id)
    return {
        "invite_id": invite_id,
        "token": token,
        "path": f"/interview?invite={token}",
        "expires_at": expires_at,
    }


@router.get("/invites")
async def list_invites(user: User = Depends(require_user)) -> dict:
    invites = await _store().list_org_invites(user.org_id)
    return {"invites": [_public_invite(i) for i in invites]}


@router.post("/invites/lookup", dependencies=[Depends(rate_limit("invite_lookup", 60, 300))])
async def lookup_invite(request: InviteLookup) -> dict:
    invite_id = read_invite_token(request.token)
    invite = await _store().get_invite(invite_id) if invite_id else None
    if invite is None:
        raise HTTPException(status_code=404, detail="This interview link is not valid")
    public = _public_invite(invite)
    # Candidates only need what the setup screen shows
    return {
        k: public[k]
        for k in ("candidate_name", "role_title", "interview_mode", "dsa_problem_id", "require_secure_app", "expires_at", "status")
    }
