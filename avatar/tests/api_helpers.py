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


async def start_call(browser, name="Ann"):
    return await browser.post("/calls/", json={"candidate_name": name})
