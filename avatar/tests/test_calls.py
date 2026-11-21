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


async def test_progress_shows_topic_and_ideas_to_the_owner_only(client, redis):
    import json

    from api_helpers import fresh_client

    _, call = await start_call(client)
    sid = call["session_id"]
    assert (await client.get(f"/calls/{call['call_id']}/progress")).json() == {
        "topic": None, "language": "ml-IN", "ideas": [], "covered": 0,
    }
    understanding = {"topic": "photosynthesis", "points": [
        {"id": "p1", "text": "Plants make food from sunlight", "status": "understood", "evidence": "x"},
        {"id": "p2", "text": "Chlorophyll is green", "status": "partial", "evidence": ""},
    ]}
    await redis.hset(f"context:{sid}", mapping={
        "current_topic": "photosynthesis", "language": "te-IN", "understanding": json.dumps(understanding),
    })
    body = (await client.get(f"/calls/{call['call_id']}/progress")).json()
    assert body["topic"] == "photosynthesis" and body["language"] == "te-IN" and body["covered"] == 1
    assert body["ideas"][1] == {"text": "Chlorophyll is green", "status": "partial"}  # no evidence/scores
    async with fresh_client(client) as other:
        await signup(other, org="Globex", email="b@globex.test")
        assert (await other.get(f"/calls/{call['call_id']}/progress")).status_code == 404


async def test_recap_is_pending_then_ready_for_the_owner_only(client, redis):
    import json

    from api_helpers import fresh_client

    _, call = await start_call(client)
    sid = call["session_id"]
    assert (await client.get(f"/calls/recap/{sid}")).json() == {"status": "pending", "recap": None}
    recap = {"title": "ఈ రోజు మనం నేర్చుకున్నది", "summary": "బాగా చేశావు!", "covered": ["photosynthesis"],
             "improved": [], "next_time": "", "language": "te-IN"}
    await redis.hset(f"context:{sid}", mapping={"descriptive_report": json.dumps(recap), "report_status": "completed"})
    body = (await client.get(f"/calls/recap/{sid}")).json()
    assert body["status"] == "ready" and body["recap"]["summary"] == "బాగా చేశావు!"
    async with fresh_client(client) as other:
        await signup(other, org="Globex", email="b@globex.test")
        assert (await other.get(f"/calls/recap/{sid}")).status_code == 404
