"""Call lifecycle: Redis tracking, interview records, private recordings."""

import asyncio

from alex_db import AuditEvent, Interview, session_scope
from api_helpers import create_invite, fresh_client, signup, start_with_invite
from sqlalchemy import select

from core.config import settings
from services.livekit_service import livekit_service


async def interview(session_id):
    async with session_scope() as db:
        return await db.get(Interview, session_id)


async def start_call(client):
    user = await signup(client)
    invite = await create_invite(client)
    cand = fresh_client(client)
    r = await start_with_invite(cand, invite["token"])
    assert r.status_code == 200, r.text
    return user, cand, r.json()


async def test_call_is_tracked_in_redis_and_recorded_in_postgres(client, redis):
    user, cand, call = await start_call(client)
    assert await redis.exists(f"call:{call['call_id']}")
    row = await interview(call["session_id"])
    assert row.org_id == user["org_id"] and row.status == "created"
    assert row.candidate_name == "Cara" and row.invite_id

    r = await cand.delete(f"/calls/{call['call_id']}")
    await cand.aclose()
    assert r.status_code == 200 and r.json()["message"] == "Call ended successfully"

    assert not await redis.exists(f"call:{call['call_id']}")
    row = await interview(call["session_id"])
    assert row.status == "ended" and row.ended_at is not None and row.end_reason == "user_ended"


async def test_concurrent_end_requests_clean_up_once(client, monkeypatch):
    deleted = []

    async def delete_room(name):
        await asyncio.sleep(0.05)
        deleted.append(name)

    monkeypatch.setattr(livekit_service, "delete_room", delete_room)
    _, cand, call = await start_call(client)
    results = await asyncio.gather(*(cand.delete(f"/calls/{call['call_id']}") for _ in range(5)))
    await cand.aclose()
    assert all(r.status_code == 200 for r in results)
    assert len(deleted) == 1  # only one request did the cleanup


async def test_recording_link_is_signed_short_lived_and_audited(client, monkeypatch):
    async def start_recording(room, session):
        return "egress-123"

    monkeypatch.setattr(livekit_service, "start_recording", start_recording)
    monkeypatch.setattr(settings, "s3_bucket", "alex-recordings-test")
    monkeypatch.setattr(settings, "s3_access_key", "AKIATESTTESTTEST")
    monkeypatch.setattr(settings, "s3_secret_key", "test-secret")

    user, cand, call = await start_call(client)
    await cand.aclose()
    sid = call["session_id"]
    row = await interview(sid)
    assert row.recording_key == f"recordings/{sid}/interview-{sid}.mp4"
    assert row.recording_status == "recording"

    r = await client.get(f"/calls/recordings/{sid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "X-Amz-Signature=" in body["url"] and "X-Amz-Expires=900" in body["url"]
    assert body["expires_in_seconds"] == 900

    async with session_scope() as db:
        events = (await db.scalars(select(AuditEvent).where(AuditEvent.action == "recording.view"))).all()
    assert len(events) == 1 and events[0].target_id == sid and events[0].actor_id == user["user_id"]

    # session detail also hands out a fresh signed link, never a stored URL
    async with fresh_client(client) as other:
        await signup(other, org="Globex", email="b@globex.test")
        assert (await other.get(f"/calls/recordings/{sid}")).status_code == 404


async def test_no_recording_is_404(client):
    _, cand, call = await start_call(client)
    await cand.aclose()
    assert (await client.get(f"/calls/recordings/{call['session_id']}")).status_code == 404


async def test_invite_requiring_the_app_rejects_a_browser_and_stays_unused(client):
    await signup(client)
    invite = await create_invite(client, require_secure_app=True)
    browser = fresh_client(client)

    r = await start_with_invite(browser, invite["token"])
    assert r.status_code == 403
    assert "Presence View app" in r.json()["detail"]

    # The refused attempt didn't use up the link
    desktop = fresh_client(client)
    desktop.headers["X-Presence-Desktop"] = "0.1.0"
    assert (await start_with_invite(desktop, invite["token"])).status_code == 200


async def test_rejoining_also_requires_the_app(client):
    await signup(client)
    invite = await create_invite(client, require_secure_app=True)
    desktop = fresh_client(client)
    desktop.headers["X-Presence-Desktop"] = "0.1.0"
    assert (await start_with_invite(desktop, invite["token"])).status_code == 200

    # Same browser cookies, but without the app's header
    del desktop.headers["X-Presence-Desktop"]
    assert (await start_with_invite(desktop, invite["token"])).status_code == 403


async def test_ordinary_invite_still_works_in_a_browser(client):
    await signup(client)
    invite = await create_invite(client)
    assert (await start_with_invite(fresh_client(client), invite["token"])).status_code == 200


async def test_candidate_page_learns_whether_the_app_is_required(client):
    await signup(client)
    invite = await create_invite(client, require_secure_app=True)
    browser = fresh_client(client)
    r = await browser.post("/auth/invites/lookup", json={"token": invite["token"]})
    assert r.status_code == 200 and r.json()["require_secure_app"] is True
