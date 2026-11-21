"""Helpers for API tests (the `client` fixture lives in conftest.py)."""

import httpx


async def signup(client, org="Acme", email="a@acme.test", password="correct-horse-1"):
    r = await client.post(
        "/auth/signup",
        json={"org_name": org, "name": "Ann", "email": email, "password": password},
    )
    assert r.status_code == 200, r.text
    return r.json()


def fresh_client(client) -> httpx.AsyncClient:
    """Separate browser (own cookies) talking to the same app."""
    return httpx.AsyncClient(transport=client._transport, base_url="http://test")


async def create_invite(client, **overrides):
    body = {"candidate_name": "Cara", "interview_mode": "round1", **overrides}
    r = await client.post("/auth/invites", json=body)
    assert r.status_code == 200, r.text
    return r.json()


async def start_with_invite(browser, token):
    return await browser.post("/calls/", json={"invite_token": token, "candidate_name": "Cara"})
