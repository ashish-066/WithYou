"""Health/readiness endpoints and client IP behind reverse proxies."""

from types import SimpleNamespace

from api_helpers import fresh_client, signup

import main
from core.config import settings
from core.rate_limit import client_ip


async def test_ready_when_redis_and_database_answer(client):
    r = await client.get("/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready", "checks": {"redis": "ok", "database": "ok"}}


async def test_not_ready_when_a_dependency_is_down(client, monkeypatch):
    async def down():
        raise ConnectionError("redis gone")

    monkeypatch.setattr(main, "_check_redis", down)
    r = await client.get("/ready")
    assert r.status_code == 503
    assert r.json()["checks"] == {"redis": "unavailable", "database": "ok"}
    # liveness stays up: restarting the process wouldn't fix Redis
    assert (await client.get("/health")).status_code == 200


def request(xff: str | None, peer: str = "10.0.0.5"):
    headers = {"x-forwarded-for": xff} if xff is not None else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=peer))


def test_client_ip_ignores_forwarded_header_without_trusted_proxies(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_hops", 0)
    assert client_ip(request("1.2.3.4")) == "10.0.0.5"


def test_client_ip_takes_entry_added_by_outermost_trusted_proxy(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)
    assert client_ip(request("203.0.113.9")) == "203.0.113.9"
    # a client-sent value is left of the one our proxy appended
    assert client_ip(request("6.6.6.6, 203.0.113.9")) == "203.0.113.9"

    monkeypatch.setattr(settings, "trusted_proxy_hops", 2)  # load balancer + nginx
    assert client_ip(request("6.6.6.6, 203.0.113.9, 10.1.0.2")) == "203.0.113.9"
    assert client_ip(request("203.0.113.9")) == "203.0.113.9"  # fewer entries than hops
    assert client_ip(request(None)) == "10.0.0.5"


async def test_spoofed_forwarded_header_does_not_dodge_rate_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)
    await signup(client)
    async with fresh_client(client) as attacker:
        codes = [
            (
                await attacker.post(
                    "/auth/login",
                    json={"email": "a@acme.test", "password": "guess-guess-1"},
                    headers={"X-Forwarded-For": f"9.9.9.{i}, 198.51.100.7"},
                )
            ).status_code
            for i in range(12)
        ]
    assert codes[-1] == 429
