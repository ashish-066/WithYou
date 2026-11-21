"""API authentication and authorization.

Runs the FastAPI app in-process against the test Redis db, with LiveKit and
S3 calls replaced by fakes.
"""

import re
from datetime import timedelta

from api_helpers import create_invite, fresh_client, signup, start_with_invite

from core.auth import AuthStore
from core.config import settings

# Endpoints that are intentionally reachable without signing in
PUBLIC = {
    ("GET", "/health"),
    ("GET", "/ready"),
    ("GET", "/auth/config"),
    ("POST", "/auth/signup"),
    ("POST", "/auth/login"),
    ("POST", "/auth/logout"),
    ("POST", "/auth/invites/lookup"),
}


# =============================================================================
# Every non-public route requires sign-in
# =============================================================================


def all_routes():
    import main

    schema = main.app.openapi()
    for path, ops in schema["paths"].items():
        for method in ops:
            yield method.upper(), path


async def test_every_non_public_route_requires_sign_in(client):
    checked = 0
    for method, path in all_routes():
        if (method, path) in PUBLIC:
            continue
        url = re.sub(r"\{[^}]+\}", "x", path)
        if path == "/resumes/upload":  # multipart: a body without a file is a 422
            r = await client.post(url, files={"file": ("cv.pdf", b"%PDF-1.4", "application/pdf")})
        else:
            r = await client.request(method, url, json={})
        assert r.status_code == 401, f"{method} {path} -> {r.status_code}"
        checked += 1
    assert checked > 40  # the whole API, not a handful


async def test_public_routes_work_without_sign_in(client):
    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/auth/config")).json() == {"signup_enabled": True, "demo_enabled": True}


# =============================================================================
# Sign-in
# =============================================================================


async def test_signup_login_logout(client):
    user = await signup(client)
    assert user["role"] == "admin"
    me = await client.get("/auth/me")
    assert me.status_code == 200 and me.json()["org_name"] == "Acme"

    cookie = client.cookies.get("alex_session")
    assert cookie

    await client.post("/auth/logout")
    client.cookies.clear()
    assert (await client.get("/auth/me")).status_code == 401

    r = await client.post("/auth/login", json={"email": "A@acme.test", "password": "correct-horse-1"})
    assert r.status_code == 200
    assert (await client.get("/auth/me")).status_code == 200


async def test_session_cookie_is_httponly_and_strict(client):
    r = await client.post(
        "/auth/signup",
        json={"org_name": "Acme", "name": "Ann", "email": "c@acme.test", "password": "correct-horse-1"},
    )
    set_cookie = r.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=strict" in set_cookie


async def test_wrong_password_and_duplicate_email(client):
    await signup(client)
    async with fresh_client(client) as other:
        r = await other.post("/auth/login", json={"email": "a@acme.test", "password": "nope-nope-nope"})
        assert r.status_code == 401
        r = await other.post(
            "/auth/signup",
            json={"org_name": "X", "name": "X", "email": "a@acme.test", "password": "correct-horse-2"},
        )
        assert r.status_code == 409


async def test_login_is_rate_limited(client):
    await signup(client)
    async with fresh_client(client) as attacker:
        codes = [
            (await attacker.post("/auth/login", json={"email": "a@acme.test", "password": "guess-guess-1"})).status_code
            for _ in range(12)
        ]
    assert codes[:10] == [401] * 10
    assert codes[-1] == 429


async def test_signup_disabled_in_production(client, monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    r = await client.post(
        "/auth/signup",
        json={"org_name": "X", "name": "X", "email": "p@x.test", "password": "correct-horse-1"},
    )
    assert r.status_code == 403


async def test_config_reports_signup_and_demo_off_when_disabled(client, monkeypatch):
    # Deployed servers set both to false (deploy/docker-compose.prod.yml)
    monkeypatch.setattr(settings, "allow_signup", False)
    monkeypatch.setattr(settings, "enable_demo", False)
    assert (await client.get("/auth/config")).json() == {"signup_enabled": False, "demo_enabled": False}


# =============================================================================
# Organization isolation
# =============================================================================


async def test_orgs_cannot_see_each_others_roles_or_sessions(client):
    await signup(client, org="Acme", email="a@acme.test")
    r = await client.post(
        "/admin/roles/",
        json={"role_id": "acme-swe", "role_title": "SWE", "job_description": "Build things"},
    )
    assert r.status_code == 200, r.text
    invite = await create_invite(client, role_id="acme-swe")
    async with fresh_client(client) as cand:
        call = (await start_with_invite(cand, invite["token"])).json()

    async with fresh_client(client) as other:
        await signup(other, org="Globex", email="b@globex.test")
        roles = (await other.get("/admin/roles/")).json()
        assert roles["roles"] == []
        assert (await other.get("/admin/roles/acme-swe")).status_code == 404
        assert (await other.put("/admin/roles/acme-swe", json={"role_title": "pwned"})).status_code == 404
        assert (await other.delete("/admin/roles/acme-swe")).status_code == 404
        # same role id can't be claimed by another org
        r = await other.post(
            "/admin/roles/",
            json={"role_id": "acme-swe", "role_title": "X", "job_description": "Y"},
        )
        assert r.status_code == 400
        sessions = (await other.get("/admin/sessions")).json()
        assert sessions["sessions"] == []
        for url in (
            f"/org/interviews/{call['session_id']}",
            f"/elo/skill-tree/{call['session_id']}",
            f"/proctoring/sessions/{call['session_id']}/report",
            f"/calls/{call['call_id']}",
        ):
            assert (await other.get(url)).status_code == 404, url
        assert (await other.post("/auth/invites", json={"candidate_name": "x", "role_id": "acme-swe"})).status_code == 404

    # the owning org still can
    assert (await client.get("/admin/roles/acme-swe")).status_code == 200
    assert (await client.get(f"/calls/{call['call_id']}")).status_code == 200


async def test_platform_admin_workspace_shows_only_own_org(client, redis):
    """Platform admins see every org's sessions, except when the workspace asks for its own."""
    from alex_db import User as DBUser
    from alex_db import session_scope
    from sqlalchemy import update

    await signup(client, org="Acme", email="a@acme.test")
    acme = (await start_with_invite(client, (await create_invite(client))["token"])).json()
    async with fresh_client(client) as admin:
        await signup(admin, org="Platform", email="p@platform.test")
        async with session_scope() as db:
            await db.execute(update(DBUser).where(DBUser.email == "p@platform.test").values(is_platform_admin=True))
        own = (await start_with_invite(admin, (await create_invite(admin))["token"])).json()
        # The worker writes these; the API only reads them
        for sid in (acme["session_id"], own["session_id"]):
            await redis.hset(f"context:{sid}", mapping={"session_id": sid, "turn_count": "1"})

        everything = {s["session_id"] for s in (await admin.get("/admin/sessions")).json()["sessions"]}
        assert {acme["session_id"], own["session_id"]} <= everything
        mine = {s["session_id"] for s in (await admin.get("/admin/sessions?own_org_only=true")).json()["sessions"]}
        assert mine == {own["session_id"]}


async def test_platform_routes_need_platform_admin(client):
    await signup(client)
    assert (await client.get("/admin/demo/status")).status_code == 403
    for url in ("/platform/workers", "/platform/queues", "/platform/health"):
        assert (await client.get(url)).status_code == 404, url  # not revealed
    r = await client.post("/admin/dsa/problems/", json={})
    assert r.status_code == 403


# =============================================================================
# Candidate invites
# =============================================================================


async def test_invite_flow_and_candidate_scope(client, redis):
    await signup(client)
    invite = await create_invite(client)
    assert invite["path"].startswith("/interview?invite=")

    async with fresh_client(client) as cand:
        info = (await cand.post("/auth/invites/lookup", json={"token": invite["token"]})).json()
        assert info["candidate_name"] == "Cara" and info["status"] == "pending"

        r = await start_with_invite(cand, invite["token"])
        assert r.status_code == 200, r.text
        sid = r.json()["session_id"]
        assert cand.cookies.get("alex_candidate")

        # own session: allowed
        r = await cand.post("/calls/dsa/execute", json={"session_id": sid, "code": "def solution(): pass"})
        assert r.status_code == 200
        assert (await cand.get(f"/calls/dsa/result/{sid}")).status_code == 200
        # session state is created by the brain worker, which isn't running here
        await redis.hset(f"context:{sid}", mapping={"session_id": sid, "cheat_flags": "[]"})
        r = await cand.post(
            "/proctoring/flags",
            json={"session_id": sid, "flag_type": "tab_switch", "severity": "low",
                  "confidence": 0.5, "description": "switched tab"},
        )
        assert r.status_code == 200, r.text
        # handed to the worker (applied under the session lock), not written here
        queued = [d for _, d in await redis.xrange(settings.request_stream)
                  if d["message_type"] == "proctoring_flags"]
        assert len(queued) == 1 and queued[0]["session_id"] == sid

        # anything else: not allowed
        r = await cand.post("/calls/dsa/execute", json={"session_id": "session-other", "code": "x"})
        assert r.status_code == 401
        for url in (f"/org/interviews/{sid}", "/admin/sessions", "/admin/roles/", f"/elo/skill-tree/{sid}"):
            assert (await cand.get(url)).status_code == 401, url

        # same browser can rejoin after a refresh
        r = await start_with_invite(cand, invite["token"])
        assert r.status_code == 200 and r.json()["status"] == "rejoined"
        assert r.json()["session_id"] == sid

    # a different browser can't reuse the link
    async with fresh_client(client) as other:
        assert (await start_with_invite(other, invite["token"])).status_code == 409

    statuses = (await client.get("/auth/invites")).json()["invites"]
    assert statuses[0]["status"] == "used" and statuses[0]["session_id"] == sid


async def test_invite_decides_the_round(client, redis):
    await signup(client)
    invite = await create_invite(client, interview_mode="round2_dsa", dsa_problem_id="two_sum_001")
    async with fresh_client(client) as cand:
        r = await cand.post(
            "/calls/",
            json={"invite_token": invite["token"], "interview_mode": "round1", "role_id": "someone-else"},
        )
        assert r.status_code == 200
    entries = [d for _, d in await redis.xrange(settings.request_stream)]
    assert any(d["message_type"] == "dsa_init" and d["problem_id"] == "two_sum_001" for d in entries)


async def test_expired_and_forged_invites(client):
    user = await signup(client)
    store = AuthStore()
    _, token, _ = await store.create_invite(
        org_id=user["org_id"], created_by=user["user_id"], ttl=timedelta(seconds=-1),
        candidate_name="Late", interview_mode="round1",
    )
    async with fresh_client(client) as cand:
        assert (await start_with_invite(cand, token)).status_code == 410
        assert (await start_with_invite(cand, token[:-4] + "abcd")).status_code == 404
        assert (await cand.post("/calls/", json={"candidate_name": "x"})).status_code == 401


async def test_client_cannot_choose_session_id(client):
    await signup(client)
    r = await client.post("/calls/", json={"candidate_name": "x", "session_id": "session-victim"})
    assert r.status_code == 200
    assert r.json()["session_id"] != "session-victim"


async def test_resume_upload_checks(client):
    await signup(client)
    invite = await create_invite(client)
    async with fresh_client(client) as cand:
        r = await cand.post("/resumes/upload", files={"file": ("cv.pdf", b"%PDF-1.4 x", "application/pdf")})
        assert r.status_code == 401
        r = await cand.post(
            "/resumes/upload",
            data={"invite_token": invite["token"]},
            files={"file": ("cv.pdf", b"MZ\x90\x00 not a pdf", "application/pdf")},
        )
        assert r.status_code == 415
        r = await cand.post(
            "/resumes/upload",
            data={"invite_token": invite["token"]},
            files={"file": ("cv.pdf", b"%PDF-" + b"0" * (5 * 1024 * 1024 + 10), "application/pdf")},
        )
        assert r.status_code == 413


async def test_team_members(client):
    await signup(client)
    r = await client.post(
        "/auth/users",
        json={"name": "Rex", "email": "rex@acme.test", "password": "correct-horse-9", "role": "recruiter"},
    )
    assert r.status_code == 200
    async with fresh_client(client) as rex:
        await rex.post("/auth/login", json={"email": "rex@acme.test", "password": "correct-horse-9"})
        assert (await rex.get("/auth/me")).json()["role"] == "recruiter"
        # recruiters can't add members
        r = await rex.post(
            "/auth/users",
            json={"name": "Eve", "email": "eve@acme.test", "password": "correct-horse-9"},
        )
        assert r.status_code == 403


async def test_failed_signup_leaves_no_orphan_org_and_actions_are_audited(client):
    from alex_db import AuditEvent, Organization, session_scope
    from sqlalchemy import func, select

    await signup(client)
    async with fresh_client(client) as other:
        r = await other.post(
            "/auth/signup",
            json={"org_name": "Dup", "name": "X", "email": "a@acme.test", "password": "correct-horse-2"},
        )
        assert r.status_code == 409
        await other.post("/auth/login", json={"email": "a@acme.test", "password": "wrong-password-1"})
    await create_invite(client)

    async with session_scope() as db:
        orgs = await db.scalar(select(func.count()).select_from(Organization))
        actions = set(await db.scalars(select(AuditEvent.action)))
    assert orgs == 1
    assert {"auth.signup", "auth.login_failed", "invite.create"} <= actions
