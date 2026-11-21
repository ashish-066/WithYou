"""Authentication and authorization.

Learners log in with email + password; an HttpOnly session cookie carries a
signed token. Sign-up creates a personal organization, so each learner only
sees their own sessions.

Storage is Postgres (tables in the shared alex_db package): organizations,
users, and interviews (study sessions; records the organization that owns each
session).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt
from alex_db import Interview, Organization, session_scope
from alex_db import User as DBUser
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

import core.db  # noqa: F401  (configures the database)
from core.config import settings

USER_COOKIE = "alex_session"

Role = Literal["admin", "recruiter"]
ROLES: tuple[str, ...] = ("admin", "recruiter")

_JWT_ALG = "HS256"


# =============================================================================
# Passwords (scrypt, stdlib)
# =============================================================================

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def generate_password() -> str:
    """One-time password for a new or reset account: 16 characters, no look-alikes, in groups of four."""
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    chars = "".join(secrets.choice(alphabet) for _ in range(16))
    return "-".join(chars[i : i + 4] for i in range(0, 16, 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    salt_b64 = base64.b64encode(salt).decode()
    digest_b64 = base64.b64encode(digest).decode()
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt_b64}${digest_b64}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
        )
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))
    except Exception:
        return False


# A real hash to compare against when the email doesn't exist, so login takes
# the same time either way (no account enumeration by timing)
_DUMMY_HASH = hash_password(secrets.token_hex(8))


# =============================================================================
# Signed tokens
# =============================================================================


def _encode(payload: dict, ttl: timedelta) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {**payload, "iat": now, "exp": now + ttl},
        settings.effective_auth_secret,
        algorithm=_JWT_ALG,
    )


def _decode(token: str, kind: str, verify_exp: bool = True) -> dict | None:
    try:
        data = jwt.decode(
            token,
            settings.effective_auth_secret,
            algorithms=[_JWT_ALG],
            options={"verify_exp": verify_exp},
        )
    except jwt.PyJWTError:
        return None
    return data if data.get("kind") == kind else None


def _set_cookie(response: Response, name: str, token: str, ttl: timedelta) -> None:
    response.set_cookie(
        name,
        token,
        max_age=int(ttl.total_seconds()),
        httponly=True,  # not readable by page scripts
        secure=settings.environment != "development",  # HTTPS-only outside dev
        samesite="strict",  # not sent on cross-site requests (CSRF)
        path="/",
    )


def set_user_cookie(response: Response, user_id: str) -> None:
    ttl = timedelta(hours=settings.session_ttl_hours)
    _set_cookie(response, USER_COOKIE, _encode({"kind": "user", "sub": user_id}, ttl), ttl)


def clear_cookies(response: Response) -> None:
    response.delete_cookie(USER_COOKIE, path="/")


# =============================================================================
# Store
# =============================================================================


def _now() -> datetime:
    return datetime.now(UTC)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _user_dict(u: DBUser) -> dict:
    return {
        "user_id": u.id,
        "email": u.email,
        "name": u.name,
        "password_hash": u.password_hash,
        "org_id": u.org_id,
        "role": u.role,
        "is_platform_admin": u.is_platform_admin,
        "created_at": _iso(u.created_at),
    }


class AuthStore:
    # ---- organizations & users ----

    async def create_org(self, name: str) -> str:
        org_id = f"org-{uuid.uuid4().hex[:12]}"
        async with session_scope() as db:
            db.add(Organization(id=org_id, name=name))
        return org_id

    async def delete_org(self, org_id: str) -> None:
        async with session_scope() as db:
            org = await db.get(Organization, org_id)
            if org is not None:
                await db.delete(org)

    async def get_org(self, org_id: str) -> dict | None:
        async with session_scope() as db:
            org = await db.get(Organization, org_id)
            return {"name": org.name, "created_at": _iso(org.created_at)} if org else None

    async def create_user(
        self,
        *,
        email: str,
        name: str,
        password: str,
        org_id: str,
        role: Role,
        is_platform_admin: bool = False,
    ) -> str:
        user_id = f"user-{uuid.uuid4().hex[:12]}"
        try:
            async with session_scope() as db:
                db.add(
                    DBUser(
                        id=user_id,
                        org_id=org_id,
                        email=normalize_email(email),
                        name=name,
                        password_hash=hash_password(password),
                        role=role,
                        is_platform_admin=is_platform_admin,
                    )
                )
        except IntegrityError as e:
            # Unique email: two sign-ups can't take the same address
            raise ValueError("An account with this email already exists") from e
        return user_id

    async def get_user(self, user_id: str) -> dict | None:
        async with session_scope() as db:
            user = await db.get(DBUser, user_id)
            return _user_dict(user) if user else None

    async def authenticate(self, email: str, password: str) -> dict | None:
        async with session_scope() as db:
            user = await db.scalar(select(DBUser).where(DBUser.email == normalize_email(email)))
        stored = user.password_hash if user else _DUMMY_HASH
        ok = verify_password(password, stored)
        return _user_dict(user) if (user and ok) else None

    async def set_role(self, user_id: str, org_id: str, role: Role) -> dict | None:
        """Change a member's access. Refuses to leave the organization without an admin."""
        async with session_scope() as db:
            user = await db.scalar(select(DBUser).where(DBUser.id == user_id, DBUser.org_id == org_id).with_for_update())
            if user is None:
                return None
            if user.role == "admin" and role != "admin" and await self._other_admins(db, org_id, user_id) == 0:
                raise ValueError("The organization needs at least one admin")
            user.role = role
            await db.flush()
            return _user_dict(user)

    async def set_password(self, user_id: str, org_id: str, password: str) -> bool:
        async with session_scope() as db:
            changed = await db.scalar(
                update(DBUser)
                .where(DBUser.id == user_id, DBUser.org_id == org_id)
                .values(password_hash=hash_password(password))
                .returning(DBUser.id)
            )
        return changed is not None

    async def remove_user(self, user_id: str, org_id: str) -> bool:
        """Delete a member. Refuses to remove the organization's last admin."""
        async with session_scope() as db:
            user = await db.scalar(select(DBUser).where(DBUser.id == user_id, DBUser.org_id == org_id).with_for_update())
            if user is None:
                return False
            if user.role == "admin" and await self._other_admins(db, org_id, user_id) == 0:
                raise ValueError("The organization needs at least one admin")
            await db.delete(user)
        return True

    @staticmethod
    async def _other_admins(db, org_id: str, user_id: str) -> int:
        rows = await db.scalars(
            select(DBUser.id)
            .where(DBUser.org_id == org_id, DBUser.role == "admin", DBUser.id != user_id)
            .with_for_update()
        )
        return len(list(rows))

    async def list_org_users(self, org_id: str) -> list[dict]:
        async with session_scope() as db:
            rows = await db.scalars(
                select(DBUser).where(DBUser.org_id == org_id).order_by(DBUser.created_at)
            )
            return [_user_dict(u) for u in rows]

    # ---- interview session ownership ----

    async def create_interview(self, session_id: str, org_id: str | None, **fields) -> None:
        async with session_scope() as db:
            db.add(Interview(session_id=session_id, org_id=org_id, status="created", **fields))

    async def session_org(self, session_id: str) -> str | None:
        async with session_scope() as db:
            return await db.scalar(
                select(Interview.org_id).where(Interview.session_id == session_id)
            )

    async def org_session_ids(self, org_id: str) -> set[str]:
        async with session_scope() as db:
            rows = await db.scalars(
                select(Interview.session_id).where(Interview.org_id == org_id)
            )
            return set(rows)


# =============================================================================
# Request principals and FastAPI dependencies
# =============================================================================


@dataclass
class User:
    user_id: str
    email: str
    name: str
    org_id: str
    role: str
    is_platform_admin: bool

    def can_access_org(self, org_id: str | None) -> bool:
        # Data with no owning org (created before auth existed) is visible to
        # platform admins only
        if org_id is None or org_id == "":
            return self.is_platform_admin
        return self.is_platform_admin or org_id == self.org_id


async def optional_user(request: Request) -> User | None:
    token = request.cookies.get(USER_COOKIE)
    data = _decode(token, "user") if token else None
    if not data:
        return None
    record = await AuthStore().get_user(data.get("sub", ""))
    if not record:
        return None  # user deleted: token no longer valid
    return User(
        user_id=record["user_id"],
        email=record["email"],
        name=record.get("name", ""),
        org_id=record["org_id"],
        role=record.get("role", "recruiter"),
        is_platform_admin=bool(record.get("is_platform_admin")),
    )


_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in"
)


async def require_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise _UNAUTHENTICATED
    return user


async def require_org_admin(user: User = Depends(require_user)) -> User:
    if user.role != "admin" and not user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Organization admin only")
    return user


async def require_platform_admin(user: User = Depends(require_user)) -> User:
    if not user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Platform admin only")
    return user


async def ensure_session_user_access(session_id: str, user: User) -> None:
    """Only users of the owning organization may see a session."""
    org_id = await AuthStore().session_org(session_id)
    if not user.can_access_org(org_id):
        raise HTTPException(status_code=404, detail="Session not found")
