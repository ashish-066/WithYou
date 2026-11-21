"""The voice agent ending a call itself."""

from alex_db import Interview, session_scope
from api_helpers import signup, start_call

from services.call_finisher import finish_session
from services.livekit_service import livekit_service


async def test_agent_ends_the_call(client, redis, monkeypatch):
    deleted = []

    async def delete_room(name):
        deleted.append(name)

    monkeypatch.setattr(livekit_service, "delete_room", delete_room)
    await signup(client)
    call = (await start_call(client)).json()
    sid = call["session_id"]

    assert await finish_session(sid, "no_response")
    assert deleted == [call["room_name"]]
    async with session_scope() as db:
        row = await db.get(Interview, sid)
    assert (row.status, row.end_reason) == ("ended", "no_response")
    # The worker already knows: no second end signal is sent
    assert not [d for _, d in await redis.xrange("interview:requests") if d["message_type"] == "end_call"]

    # Ending again is a no-op
    assert not await finish_session(sid, "no_response")
