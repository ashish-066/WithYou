"""Platform console API (/platform/*): platform admins only, across organizations."""

import json
import re
from datetime import UTC, datetime

from alex_db import Interview, session_scope
from alex_db import User as DBUser
from alex_db.audit import record
from api_helpers import create_invite, fresh_client, signup, start_with_invite
from sqlalchemy import update

from core.config import settings


def platform_routes():
    import main

    for path, ops in main.app.openapi()["paths"].items():
        if path.startswith("/platform"):
            for method in ops:
                yield method.upper(), path


async def make_platform_admin(email):
    async with session_scope() as db:
        await db.execute(update(DBUser).where(DBUser.email == email).values(is_platform_admin=True))


async def test_platform_routes_are_not_found_for_everyone_else(client):
    await signup(client)
    checked = 0
    for method, path in platform_routes():
        r = await client.request(method, re.sub(r"\{[^}]+\}", "x", path))
        assert r.status_code == 404, f"{method} {path} -> {r.status_code}"
        checked += 1
    assert checked >= 7


async def test_organizations_and_interviews_across_orgs(client):
    await signup(client, org="Acme", email="a@acme.test")
    acme_org = (await client.get("/auth/me")).json()["org_id"]
    async with fresh_client(client) as cand:
        sid = (await start_with_invite(cand, (await create_invite(client))["token"])).json()["session_id"]
    async with session_scope() as db:
        db.add(Interview(session_id="session-unowned", status="ended"))

    async with fresh_client(client) as admin:
        await signup(admin, org="Platform", email="p@platform.test")
        await make_platform_admin("p@platform.test")

        orgs = {o["name"]: o for o in (await admin.get("/platform/organizations")).json()["organizations"]}
        assert (orgs["Acme"]["members"], orgs["Acme"]["interviews"]) == (1, 1)
        assert orgs["Platform"]["interviews"] == 0

        detail = (await admin.get(f"/platform/organizations/{acme_org}")).json()
        assert [m["email"] for m in detail["members"]] == ["a@acme.test"]
        assert [i["session_id"] for i in detail["recent_interviews"]] == [sid]
        assert (await admin.get("/platform/organizations/org-nope")).status_code == 404

        rows = (await admin.get("/platform/interviews")).json()["interviews"]
        assert [(r["session_id"], r["org_name"]) for r in rows] == [(sid, "Acme")]
        everything = (await admin.get("/platform/interviews?include_unowned=true")).json()["interviews"]
        assert {r["session_id"] for r in everything} == {sid, "session-unowned"}


async def test_health_workers_and_queues(client, redis):
    await signup(client, org="Platform", email="p@platform.test")
    await make_platform_admin("p@platform.test")
    now = datetime.now(UTC).isoformat()
    await redis.set("worker:heartbeat:w1", json.dumps(
        {"worker_id": "w1", "hostname": "box", "status": "busy", "last_heartbeat": now, "current_session": "s1"}))
    await redis.set("worker:heartbeat:w2", json.dumps(
        {"worker_id": "w2", "status": "idle", "last_heartbeat": "2026-01-01T00:00:00+00:00"}))
    await redis.hset("worker:metrics:w1", mapping={"messages_processed": "12", "avg_latency_ms": "840.5"})
    await redis.xadd(settings.dead_letter_stream, {"session_id": "s9", "error": "boom", "payload": '{"x": 1}'})

    health = (await client.get("/platform/health")).json()
    parts = {p["part"]: p for p in health["parts"]}
    assert parts["database"]["state"] == "ok" and parts["redis"]["state"] == "ok"
    assert parts["workers"]["state"] == "warn" and "1 of 2" in parts["workers"]["detail"]
    assert parts["dead_letters"]["state"] == "warn"
    assert health["state"] in ("warn", "down")

    workers = (await client.get("/platform/workers")).json()["workers"]
    assert [(w["worker_id"], w["stale"]) for w in workers] == [("w1", False), ("w2", True)]
    assert (workers[0]["messages_processed"], workers[0]["avg_latency_ms"]) == (12, 840.5)

    q = (await client.get("/platform/queues")).json()
    assert [s["kind"] for s in q["streams"]] == ["requests", "responses"]
    assert q["dead_letters_total"] == 1
    assert q["dead_letters"][0]["payload"] == '{"x": 1}'


async def test_audit_log_filters_and_paging(client):
    await signup(client, org="Acme", email="a@acme.test")
    me = (await client.get("/auth/me")).json()
    await make_platform_admin("a@acme.test")
    for i in range(3):
        await record("invite.create", actor_type="user", actor_id=me["user_id"], org_id=me["org_id"],
                     target_type="invite", target_id=f"inv-{i}")
    await record("user.remove", actor_type="user", actor_id="someone-else", org_id="org-other")

    events = (await client.get("/platform/audit?action=invite.")).json()
    assert all(e["action"].startswith("invite.") for e in events["events"])
    assert events["events"][0]["actor_email"] == "a@acme.test"
    assert events["events"][0]["org_name"] == "Acme"
    assert "user.remove" in events["actions"]

    page = (await client.get("/platform/audit?action=invite.create&limit=2")).json()
    assert [e["target_id"] for e in page["events"]] == ["inv-2", "inv-1"]
    rest = (await client.get(f"/platform/audit?action=invite.create&limit=2&before_id={page['next_before_id']}")).json()
    assert [e["target_id"] for e in rest["events"]] == ["inv-0"] and rest["next_before_id"] is None

    by_actor = (await client.get("/platform/audit?actor=A@ACME.test")).json()["events"]
    assert by_actor and all(e["actor_id"] == me["user_id"] for e in by_actor)
    assert (await client.get("/platform/audit?org_id=org-other")).json()["events"][0]["action"] == "user.remove"


# =============================================================================
# Coding problem library
# =============================================================================


def problem(**overrides):
    return {
        "problem_id": "two_sum_test",
        "title": "Two Sum",
        "statement": "Return indices of two numbers adding up to target.",
        "difficulty": "easy",
        "reference_solution": {
            "algorithm": "hash_map", "time_complexity": "O(n)", "space_complexity": "O(n)",
            "code": "def solution(nums, target): ...",
        },
        "public_test_cases": [{"input": "[2,7] 9", "expected_output": "[0, 1]"}],
        "hidden_test_cases": [{"input": "[3,3] 6", "expected_output": "[0, 1]", "is_hidden": True}],
        **overrides,
    }


async def test_problem_library_crud_validation_and_audit(client):
    await signup(client, org="Platform", email="p@platform.test")
    await make_platform_admin("p@platform.test")

    r = await client.post("/platform/problems", json=problem())
    assert r.status_code == 201 and r.json()["problem"]["created_by"] == "p@platform.test"
    assert (await client.post("/platform/problems", json=problem())).status_code == 409

    [row] = (await client.get("/platform/problems")).json()["problems"]
    assert (row["problem_id"], row["public_tests"], row["hidden_tests"], row["interviews"]) == ("two_sum_test", 1, 1, 0)

    changed = problem(title="Two Sum (pairs)", problem_id="ignored-body-id")
    r = await client.put("/platform/problems/two_sum_test", json=changed)
    assert r.status_code == 200 and r.json()["problem"]["title"] == "Two Sum (pairs)"
    full = (await client.get("/platform/problems/two_sum_test")).json()
    assert full["problem"]["reference_solution"]["algorithm"] == "hash_map"
    assert full["usage"] == {"invites": 0, "interviews": 0}

    # Validation: schema, rubric weights, at least one test
    assert (await client.post("/platform/problems", json={"title": "x"})).status_code == 422
    bad_rubric = problem(problem_id="p2", scoring_rubric={"dimensions": [{"name": "reasoning", "weight": 0.5}]})
    r = await client.post("/platform/problems", json=bad_rubric)
    assert r.status_code == 422 and "100%" in r.json()["detail"]
    no_tests = problem(problem_id="p3", public_test_cases=[], hidden_test_cases=[])
    assert (await client.post("/platform/problems", json=no_tests)).status_code == 422

    assert (await client.delete("/platform/problems/two_sum_test")).status_code == 200
    assert (await client.get("/platform/problems/two_sum_test")).status_code == 404
    assert (await client.delete("/platform/problems/two_sum_test")).status_code == 404

    actions = [e["action"] for e in (await client.get("/platform/audit?action=problem.")).json()["events"]]
    assert actions == ["problem.delete", "problem.update", "problem.create"]
