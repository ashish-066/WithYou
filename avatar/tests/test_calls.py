"""Call lifecycle: Redis tracking and session records."""

import asyncio

from alex_db import Interview, session_scope
from api_helpers import signup
from api_helpers import start_call as post_call

from services.livekit_service import livekit_service


async def interview(session_id):
    async with session_scope() as db:
        return await db.get(Interview, session_id)


async def start_call(client):
    user = await signup(client)
    r = await post_call(client, "Ann")
    assert r.status_code == 200, r.text
    return user, r.json()


async def test_call_is_tracked_in_redis_and_recorded_in_postgres(client, redis):
    user, call = await start_call(client)
    assert await redis.exists(f"call:{call['call_id']}")
    row = await interview(call["session_id"])
    assert row.org_id == user["org_id"] and row.status == "created"
    assert row.candidate_name == "Ann"

    r = await client.delete(f"/calls/{call['call_id']}")
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
    _, call = await start_call(client)
    results = await asyncio.gather(*(client.delete(f"/calls/{call['call_id']}") for _ in range(5)))
    assert [r.status_code for r in results] == [200] * 5, [r.text for r in results]
    assert len(deleted) == 1  # only one request did the cleanup


async def test_call_records_the_language_and_tells_the_brain(client, redis):
    await signup(client)
    call = (await client.post("/calls/", json={"candidate_name": "Ann", "language": "te-IN"})).json()
    from services import active_calls

    assert (await active_calls.get(call["call_id"]))["language"] == "te-IN"
    inits = [d for _, d in await redis.xrange("interview:requests") if d["message_type"] == "system_init"]
    assert [(d["session_id"], d["language"]) for d in inits] == [(call["session_id"], "te-IN")]
    # Unsupported languages are refused
    assert (await client.post("/calls/", json={"language": "fr-FR"})).status_code == 422


async def test_call_dispatches_our_named_agent(client, monkeypatch):
    dispatched = []

    async def dispatch_agent(room):
        dispatched.append(room)

    monkeypatch.setattr(livekit_service, "dispatch_agent", dispatch_agent)
    _, call = await start_call(client)
    assert dispatched == [call["room_name"]]


async def test_no_recording_is_started(client):
    _, call = await start_call(client)
    row = await interview(call["session_id"])
    assert not row.recording_key and not row.egress_id
