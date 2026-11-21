"""API authentication and authorization.

Runs the FastAPI app in-process against the test Redis db, with LiveKit
calls replaced by fakes.
"""

import re

from api_helpers import fresh_client, signup, start_call

from core.config import settings

# Endpoints that are intentionally reachable without signing in
PUBLIC = {
    ("GET", "/health"),
    ("GET", "/ready"),
    ("GET", "/auth/config"),
    ("POST", "/auth/signup"),
    ("POST", "/auth/login"),
    ("POST", "/auth/logout"),
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
        r = await client.request(method, url, json={})
        assert r.status_code == 401, f"{method} {path} -> {r.status_code}"
        checked += 1
    assert checked >= 4  # /auth/me + the call routes


async def test_public_routes_work_without_sign_in(client):
    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/auth/config")).json() == {"signup_enabled": True}


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


async def test_config_reports_signup_off_when_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "allow_signup", False)
    assert (await client.get("/auth/config")).json() == {"signup_enabled": False}


async def test_signup_without_org_name_uses_the_learner_name(client):
    r = await client.post(
        "/auth/signup", json={"name": "Ann", "email": "n@x.test", "password": "correct-horse-1"}
    )
    assert r.status_code == 200, r.text
    assert (await client.get("/auth/me")).json()["org_name"] == "Ann"


# =============================================================================
# Learner isolation
# =============================================================================


async def test_learners_cannot_see_each_others_sessions(client):
    await signup(client, org="Acme", email="a@acme.test")
    call = (await start_call(client)).json()

    async with fresh_client(client) as other:
        await signup(other, org="Globex", email="b@globex.test")
        assert (await other.get(f"/calls/{call['call_id']}")).status_code == 404
        assert (await other.delete(f"/calls/{call['call_id']}")).status_code == 404

    assert (await client.get(f"/calls/{call['call_id']}")).status_code == 200


async def test_starting_a_session_needs_sign_in(client):
    async with fresh_client(client) as anon:
        assert (await start_call(anon)).status_code == 401


async def test_client_cannot_choose_session_id(client):
    await signup(client)
    r = await client.post("/calls/", json={"candidate_name": "x", "session_id": "session-victim"})
    assert r.status_code == 200
    assert r.json()["session_id"] != "session-victim"


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
    await start_call(client)

    async with session_scope() as db:
        orgs = await db.scalar(select(func.count()).select_from(Organization))
        actions = set(await db.scalars(select(AuditEvent.action)))
    assert orgs == 1
    assert {"auth.signup", "auth.login_failed", "call.start"} <= actions
