"""Organization workspace API (/org/*): interview list, invite and team actions."""

import json

from alex_db import AuditEvent, Interview, session_scope
from alex_db import User as DBUser
from api_helpers import create_invite, fresh_client, signup, start_with_invite
from sqlalchemy import select, update

from core.auth import AuthStore


async def login(client, email, password):
    return await client.post("/auth/login", json={"email": email, "password": password})


# =============================================================================
# Interviews
# =============================================================================


async def test_interviews_come_from_postgres_with_live_progress(client, redis):
    await signup(client)
    await client.post("/admin/roles/", json={"role_id": "swe-1", "role_title": "SWE", "job_description": "Build"})
    invite = await create_invite(client, role_id="swe-1", candidate_email="cara@example.com")
    async with fresh_client(client) as cand:
        sid = (await start_with_invite(cand, invite["token"])).json()["session_id"]

    # Running: live fields come from Redis
    await redis.hset(f"context:{sid}", mapping={"turn_count": "3", "max_turns": "20", "integrity_score": "0.75"})
    [row] = (await client.get("/org/interviews")).json()["interviews"]
    assert row["session_id"] == sid
    assert (row["candidate_name"], row["candidate_email"], row["role_title"]) == ("Cara", "cara@example.com", "SWE")
    assert (row["status"], row["turn_count"], row["integrity_score"]) == ("in_progress", 3, 0.75)

    # Ended and gone from Redis: still listed, from Postgres
    async with session_scope() as db:
        await db.execute(
            update(Interview)
            .where(Interview.session_id == sid)
            .values(status="ended", scores={"turn_count": 9, "integrity_score": 0.9}, end_reason="completed")
        )
    await redis.delete(f"context:{sid}")
    [row] = (await client.get("/org/interviews")).json()["interviews"]
    assert (row["status"], row["turn_count"], row["integrity_score"]) == ("completed", 9, 0.9)

    # Another organization sees none of it
    async with fresh_client(client) as other:
        await signup(other, org="Globex", email="b@globex.test")
        assert (await other.get("/org/interviews")).json()["interviews"] == []


async def _started_interview(client, email="cara@example.com"):
    await client.post("/admin/roles/", json={"role_id": "swe-1", "role_title": "SWE", "job_description": "Build"})
    invite = await create_invite(client, role_id="swe-1", candidate_email=email)
    async with fresh_client(client) as cand:
        return (await start_with_invite(cand, invite["token"])).json()["session_id"]


async def test_interview_detail_live_then_from_postgres(client, redis):
    await signup(client)
    sid = await _started_interview(client)

    # Running: the worker's state and full transcript in Redis
    await redis.hset(f"context:{sid}", mapping={
        "turn_count": "2", "max_turns": "20", "integrity_score": "0.8", "interview_ended": "0",
        "messages": json.dumps([{"role": "user", "content": "recent only"}]),
        "cheat_flags": json.dumps([{"flag_type": "tab_switch", "severity": "low"}]),
    })
    for entry in ({"role": "assistant", "content": "Hello", "turn": 0},
                  {"role": "user", "content": "Hi", "turn": 1}):
        await redis.rpush(f"transcript:{sid}", json.dumps(entry))

    r = await client.get(f"/org/interviews/{sid}")
    assert r.status_code == 200
    d = r.json()
    assert (d["candidate_name"], d["candidate_email"], d["role_title"]) == ("Cara", "cara@example.com", "SWE")
    assert (d["status"], d["live"], d["turn_count"], d["report_status"]) == ("in_progress", True, 2, "not_started")
    assert [m["content"] for m in d["transcript"]["messages"]] == ["Hello", "Hi"]
    assert d["integrity"]["cheat_flags"][0]["flag_type"] == "tab_switch"
    assert d["integrity"]["integrity_score"] == 0.8
    assert d["decision"] is None and d["can_decide"] is True
    assert "internals" not in d

    # Ended and gone from Redis: everything from Postgres
    saved = [{"role": "assistant", "content": f"m{i}"} for i in range(15)]
    async with session_scope() as db:
        await db.execute(update(Interview).where(Interview.session_id == sid).values(
            status="ended", end_reason="completed",
            report={"summary": "Solid", "recommendation": "yes"},
            scores={"turn_count": 9, "integrity_score": 0.9},
            integrity={"cheat_flags": [], "integrity_report": {"integrity_score": 0.9}},
            transcript={"messages": saved, "summary": None},
        ))
    async with session_scope() as db:
        await db.execute(update(Interview).where(Interview.session_id == sid).values(
            scores={"turn_count": 9, "integrity_score": 0.9,
                    "completion": {"end_reason": "no_response", "incomplete": True, "unanswered_questions": 3}},
            integrity={"cheat_flags": [], "integrity_report": {"integrity_score": 0.9},
                       "response_timings": [{"turn": 2, "latency_ms": 4000, "words": 30}]},
        ))
    await redis.delete(f"context:{sid}", f"transcript:{sid}")
    d = (await client.get(f"/org/interviews/{sid}")).json()
    assert (d["status"], d["live"], d["turn_count"], d["report_status"]) == ("completed", False, 9, "ready")
    assert d["report"]["summary"] == "Solid"
    assert len(d["transcript"]["messages"]) == 15
    assert d["integrity"]["integrity_report"] == {"integrity_score": 0.9}
    assert d["completion"]["end_reason"] == "no_response" and d["completion"]["incomplete"]
    assert d["integrity"]["response_timings"][0]["latency_ms"] == 4000


async def test_finished_interview_without_report_is_pending(client, redis):
    await signup(client)
    sid = await _started_interview(client)
    async with session_scope() as db:
        await db.execute(update(Interview).where(Interview.session_id == sid).values(status="ended"))
    d = (await client.get(f"/org/interviews/{sid}")).json()
    assert (d["status"], d["report_status"], d["report"]) == ("completed", "pending", None)


async def test_decision_set_changed_cleared_and_audited(client):
    await signup(client)
    sid = await _started_interview(client)

    r = await client.put(f"/org/interviews/{sid}/decision", json={"decision": "advance", "note": " Strong "})
    assert r.status_code == 200
    decision = r.json()["decision"]
    assert (decision["decision"], decision["note"]) == ("advance", "Strong")
    assert decision["decided_by"]["email"] == "a@acme.test" and decision["decided_at"]
    assert (await client.get(f"/org/interviews/{sid}")).json()["decision"]["decision"] == "advance"

    await client.put(f"/org/interviews/{sid}/decision", json={"decision": "reject"})
    d = (await client.get(f"/org/interviews/{sid}")).json()["decision"]
    assert (d["decision"], d["note"]) == ("reject", "")

    assert (await client.put(f"/org/interviews/{sid}/decision", json={"decision": None})).json()["decision"] is None
    assert (await client.get(f"/org/interviews/{sid}")).json()["decision"] is None

    bad = await client.put(f"/org/interviews/{sid}/decision", json={"decision": "maybe"})
    assert bad.status_code == 422

    async with session_scope() as db:
        events = (await db.scalars(
            select(AuditEvent).where(AuditEvent.action == "interview.decision").order_by(AuditEvent.id)
        )).all()
    assert [e.details["decision"] for e in events] == ["advance", "reject", None]
    assert events[1].details["previous"] == "advance"


async def test_interview_detail_access(client, redis):
    await signup(client)
    sid = await _started_interview(client)
    assert (await client.get("/org/interviews/session-nope")).status_code == 404

    # Another organization: not found, can't decide
    async with fresh_client(client) as other:
        await signup(other, org="Globex", email="b@globex.test")
        assert (await other.get(f"/org/interviews/{sid}")).status_code == 404
        r = await other.put(f"/org/interviews/{sid}/decision", json={"decision": "reject"})
        assert r.status_code == 404

    # Platform admin of another org: may read (with internals), not decide
    async with fresh_client(client) as admin:
        await signup(admin, org="Platform", email="p@platform.test")
        async with session_scope() as db:
            await db.execute(update(DBUser).where(DBUser.email == "p@platform.test").values(is_platform_admin=True))
        await redis.hset(f"context:{sid}", mapping={"turn_count": "1", "brain_mode": "fast"})
        d = (await admin.get(f"/org/interviews/{sid}")).json()
        assert d["session_id"] == sid and d["can_decide"] is False
        assert d["internals"]["live_state"]["brain_mode"] == "fast"
        assert d["internals"]["stored"]["status"] == "created"
        r = await admin.put(f"/org/interviews/{sid}/decision", json={"decision": "reject"})
        assert r.status_code == 403
    assert (await client.get(f"/org/interviews/{sid}")).json()["decision"] is None


# =============================================================================
# Invites
# =============================================================================


async def test_revoked_invite_stops_working(client):
    await signup(client)
    invite = await create_invite(client)
    assert (await client.post(f"/org/invites/{invite['invite_id']}/revoke")).status_code == 200

    statuses = {i["invite_id"]: i["status"] for i in (await client.get("/auth/invites")).json()["invites"]}
    assert statuses[invite["invite_id"]] == "revoked"
    async with fresh_client(client) as cand:
        lookup = (await cand.post("/auth/invites/lookup", json={"token": invite["token"]})).json()
        assert lookup["status"] == "revoked"
        r = await start_with_invite(cand, invite["token"])
        assert r.status_code == 410 and "withdrawn" in r.json()["detail"]

    # Twice, or no link once withdrawn
    assert (await client.post(f"/org/invites/{invite['invite_id']}/revoke")).status_code == 409
    assert (await client.post(f"/org/invites/{invite['invite_id']}/link")).status_code == 409


async def test_used_invite_cannot_be_revoked_and_withdrawn_cannot_be_claimed(client):
    await signup(client)
    used = await create_invite(client)
    async with fresh_client(client) as cand:
        assert (await start_with_invite(cand, used["token"])).status_code == 200
    assert (await client.post(f"/org/invites/{used['invite_id']}/revoke")).status_code == 409

    # Store level: a withdrawn invite can't be claimed even if the API check is skipped
    pending = await create_invite(client)
    store = AuthStore()
    org_id = (await client.get("/auth/me")).json()["org_id"]
    assert await store.revoke_invite(pending["invite_id"], org_id)
    assert not await store.consume_invite(pending["invite_id"], "session-race")


async def test_invite_link_can_be_copied_again(client):
    await signup(client)
    invite = await create_invite(client)
    r = await client.post(f"/org/invites/{invite['invite_id']}/link")
    assert r.status_code == 200
    token = r.json()["path"].split("invite=", 1)[1]
    async with fresh_client(client) as cand:
        lookup = await cand.post("/auth/invites/lookup", json={"token": token})
        assert lookup.status_code == 200 and lookup.json()["candidate_name"] == "Cara"


async def test_other_orgs_invites_are_not_found(client):
    await signup(client)
    invite = await create_invite(client)
    async with fresh_client(client) as other:
        await signup(other, org="Globex", email="b@globex.test")
        for action in ("revoke", "link"):
            assert (await other.post(f"/org/invites/{invite['invite_id']}/{action}")).status_code == 404
    # still pending for its owner
    statuses = {i["invite_id"]: i["status"] for i in (await client.get("/auth/invites")).json()["invites"]}
    assert statuses[invite["invite_id"]] == "pending"


# =============================================================================
# Team
# =============================================================================


async def test_member_gets_a_generated_password_that_works(client):
    await signup(client)
    r = await client.post("/auth/users", json={"name": "Rui", "email": "rui@acme.test", "role": "recruiter"})
    assert r.status_code == 200, r.text
    password = r.json()["one_time_password"]
    assert len(password) == 19  # 16 characters in groups of four
    async with fresh_client(client) as rui:
        assert (await login(rui, "rui@acme.test", password)).status_code == 200


async def test_change_access_reset_password_and_remove(client):
    await signup(client)
    member = (await client.post("/auth/users", json={"name": "Rui", "email": "rui@acme.test"})).json()
    uid, first = member["user_id"], member["one_time_password"]

    r = await client.patch(f"/org/users/{uid}", json={"role": "admin"})
    assert r.status_code == 200 and r.json()["role"] == "admin"

    second = (await client.post(f"/org/users/{uid}/reset-password")).json()["one_time_password"]
    assert second != first
    async with fresh_client(client) as rui:
        assert (await login(rui, "rui@acme.test", first)).status_code == 401
        assert (await login(rui, "rui@acme.test", second)).status_code == 200

        assert (await client.delete(f"/org/users/{uid}")).status_code == 200
        # The removed member's session ends at once, and they can't sign in again
        assert (await rui.get("/auth/me")).status_code == 401
        assert (await login(rui, "rui@acme.test", second)).status_code == 401


async def test_team_actions_guard_self_other_orgs_and_recruiters(client):
    me = await signup(client)
    for method, url in (("patch", f"/org/users/{me['user_id']}"), ("post", f"/org/users/{me['user_id']}/reset-password"), ("delete", f"/org/users/{me['user_id']}")):
        r = await getattr(client, method)(url, **({"json": {"role": "recruiter"}} if method == "patch" else {}))
        assert r.status_code == 400, url

    recruiter = (await client.post("/auth/users", json={"name": "Rui", "email": "rui@acme.test"})).json()
    async with fresh_client(client) as rui:
        await login(rui, "rui@acme.test", recruiter["one_time_password"])
        assert (await rui.delete(f"/org/users/{me['user_id']}")).status_code == 403

    async with fresh_client(client) as other:
        await signup(other, org="Globex", email="b@globex.test")
        assert (await other.delete(f"/org/users/{recruiter['user_id']}")).status_code == 404
        assert (await other.patch(f"/org/users/{recruiter['user_id']}", json={"role": "admin"})).status_code == 404


async def test_last_admin_cannot_be_demoted_or_removed(client):
    me = await signup(client)
    store = AuthStore()
    import pytest

    with pytest.raises(ValueError):
        await store.set_role(me["user_id"], me["org_id"], "recruiter")
    with pytest.raises(ValueError):
        await store.remove_user(me["user_id"], me["org_id"])


async def test_failed_report_can_be_retried(client, redis):
    from datetime import UTC, datetime, timedelta

    await signup(client)
    sid = await _started_interview(client)
    async with session_scope() as db:
        await db.execute(update(Interview).where(Interview.session_id == sid).values(
            status="ended", ended_at=datetime.now(UTC) - timedelta(minutes=1)))
    assert (await client.get(f"/org/interviews/{sid}")).json()["report_status"] == "pending"

    # The worker marked it failed (or it's overdue): the page offers a retry
    await redis.hset(f"context:{sid}", "report_status", "failed")
    assert (await client.get(f"/org/interviews/{sid}")).json()["report_status"] == "failed"

    r = await client.post(f"/org/interviews/{sid}/report/retry")
    assert r.status_code == 200
    queued = [d for _, d in await redis.xrange("interview:requests") if d["message_type"] == "regenerate_report"]
    assert [d["session_id"] for d in queued] == [sid]
    assert (await client.get(f"/org/interviews/{sid}")).json()["report_status"] == "pending"

    # Another organization can't; a written report isn't redone
    async with fresh_client(client) as other:
        await signup(other, org="Globex", email="b@globex.test")
        assert (await other.post(f"/org/interviews/{sid}/report/retry")).status_code == 404
    async with session_scope() as db:
        await db.execute(update(Interview).where(Interview.session_id == sid).values(report={"summary": "x"}))
    assert (await client.post(f"/org/interviews/{sid}/report/retry")).status_code == 409


async def test_report_overdue_counts_as_failed(client):
    from datetime import UTC, datetime, timedelta

    await signup(client)
    sid = await _started_interview(client)
    async with session_scope() as db:
        await db.execute(update(Interview).where(Interview.session_id == sid).values(
            status="ended", ended_at=datetime.now(UTC) - timedelta(minutes=30)))
    assert (await client.get(f"/org/interviews/{sid}")).json()["report_status"] == "failed"
