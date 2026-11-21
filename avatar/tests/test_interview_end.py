"""Signals the voice agent reads, and the agent ending a call itself."""

from alex_db import Interview, session_scope
from api_helpers import create_invite, fresh_client, signup, start_with_invite

from services.call_finisher import finish_session
from services.livekit_service import livekit_service
from services.presence import code_activity_key


async def start_call(client):
    await signup(client)
    invite = await create_invite(client)
    cand = fresh_client(client)
    r = await start_with_invite(cand, invite["token"])
    assert r.status_code == 200, r.text
    return cand, invite, r.json()


async def test_browser_cannot_report_camera_checks(client):
    """Camera checks run on the server; there is no endpoint to fake them."""
    cand, _, call = await start_call(client)
    r = await cand.post("/proctoring/presence", json={"session_id": call["session_id"], "face_visible": True})
    assert r.status_code in (404, 405)
    await cand.aclose()


async def test_code_snapshots_mark_coding_activity(client, redis):
    cand, _, call = await start_call(client)
    sid = call["session_id"]
    r = await cand.post("/calls/dsa/code_snapshot", json={"session_id": sid, "code": "def f(): pass"})
    assert r.status_code == 200
    assert await redis.get(code_activity_key(sid))
    await cand.aclose()


async def test_agent_ends_the_call_and_rejoining_is_refused(client, redis, monkeypatch):
    deleted = []

    async def delete_room(name):
        deleted.append(name)

    monkeypatch.setattr(livekit_service, "delete_room", delete_room)
    cand, invite, call = await start_call(client)
    sid = call["session_id"]

    assert await finish_session(sid, "no_response")
    assert deleted == [call["room_name"]]
    async with session_scope() as db:
        row = await db.get(Interview, sid)
    assert (row.status, row.end_reason) == ("ended", "no_response")
    # The worker already knows: no second end signal is sent
    assert not [d for _, d in await redis.xrange("interview:requests") if d["message_type"] == "end_call"]

    # Ending again is a no-op, and the candidate can't rejoin an ended interview
    assert not await finish_session(sid, "no_response")
    r = await start_with_invite(cand, invite["token"])
    assert r.status_code != 200 or r.json()["status"] != "rejoined"
    await cand.aclose()


async def test_evidence_photo_is_served_to_the_org_only_and_audited(client, redis, tmp_path, monkeypatch):
    from alex_db import AuditEvent
    from sqlalchemy import select, update

    from core import recordings
    from core.recordings import evidence_key, put_evidence

    monkeypatch.setattr(recordings, "LOCAL_EVIDENCE_DIR", tmp_path)

    cand, _, call = await start_call(client)
    await cand.aclose()
    sid = call["session_id"]
    key = evidence_key(sid, "flag-1")
    assert put_evidence(key, b"\xff\xd8jpeg-bytes")
    flags = [{"id": "flag-1", "flag_type": "phone_detected", "evidence": {"photo_key": key}},
             {"id": "flag-2", "flag_type": "phone_detected", "evidence": {"photo_key": "evidence/other/x.jpg"}}]
    async with session_scope() as db:
        await db.execute(update(Interview).where(Interview.session_id == sid).values(integrity={"cheat_flags": flags}))

    r = await client.get(f"/org/interviews/{sid}/evidence/flag-1")
    assert r.status_code == 200 and r.content == b"\xff\xd8jpeg-bytes"
    assert r.headers["content-type"] == "image/jpeg" and "no-store" in r.headers["cache-control"]
    # A key pointing at another interview is refused; unknown flags too
    assert (await client.get(f"/org/interviews/{sid}/evidence/flag-2")).status_code == 404
    assert (await client.get(f"/org/interviews/{sid}/evidence/nope")).status_code == 404

    async with fresh_client(client) as other:
        await signup(other, org="Globex", email="b@globex.test")
        assert (await other.get(f"/org/interviews/{sid}/evidence/flag-1")).status_code == 404

    async with session_scope() as db:
        views = (await db.scalars(select(AuditEvent).where(AuditEvent.action == "evidence.view"))).all()
    assert [v.details["flag_id"] for v in views] == ["flag-1"]
