"""The learner's history, session detail and progress (api/me_routes.py)."""

from datetime import UTC, datetime, timedelta

from alex_db import Interview, session_scope
from api_helpers import fresh_client, signup


async def add(user, sid, days_ago, mode="study", topic="photosynthesis", ideas=None, report=None, today=None):
    created = (today or datetime(2026, 11, 22, 6, 0, tzinfo=UTC)) - timedelta(days=days_ago)
    async with session_scope() as db:
        db.add(Interview(
            session_id=sid, org_id=user["org_id"], user_id=user["user_id"], status="ended",
            interview_mode=mode, language="te-IN", topic=topic, created_at=created,
            report=report or {"title": "బాగా చేశావు", "summary": "ఈ రోజు బాగా నేర్చుకున్నావు", "next_time": "ఆక్సిజన్",
                              "covered": ["private?"], "improved": ["x"]},
            analytics={"topic": topic, "language": "te-IN", "ideas": ideas or []},
        ))


IDEAS = [{"text": "a", "status": "understood"}, {"text": "b", "status": "understood"}, {"text": "c", "status": "partial"}]


async def test_sessions_list_detail_and_privacy(client):
    user = await signup(client)
    await add(user, "s-study", 1, ideas=IDEAS)
    await add(user, "s-talk", 0, mode="talk", topic=None)

    sessions = (await client.get("/me/sessions")).json()["sessions"]
    assert [s["session_id"] for s in sessions] == ["s-talk", "s-study"]  # newest first
    study = sessions[1]
    assert (study["mode"], study["topic"], study["language"]) == ("study", "photosynthesis", "te-IN")
    assert (study["ideas_understood"], study["ideas_total"]) == (2, 3)

    detail = (await client.get("/me/sessions/s-study")).json()
    assert detail["recap"]["summary"] == "ఈ రోజు బాగా నేర్చుకున్నావు" and len(detail["ideas"]) == 3
    talk = (await client.get("/me/sessions/s-talk")).json()
    assert talk["mode"] == "talk" and talk["recap"]["covered"] == [] and talk["ideas"] == []

    async with fresh_client(client) as other:
        await signup(other, org="Globex", email="b@globex.test")
        assert (await other.get("/me/sessions")).json()["sessions"] == []
        assert (await other.get("/me/sessions/s-study")).status_code == 404


async def test_stats_streak_week_ideas_and_topics(client):
    user = await signup(client)
    today = datetime(2026, 11, 22, 6, 0, tzinfo=UTC)
    # Sessions today, yesterday, 2 days ago (streak 3), and 10 days ago (not this week)
    await add(user, "a", 0, ideas=IDEAS, today=today)
    await add(user, "b", 1, topic="Gravity", ideas=IDEAS[:1], today=today)
    await add(user, "c", 2, mode="talk", topic=None, today=today)
    await add(user, "d", 10, topic="Photosynthesis", today=today)

    stats = (await client.get("/me/stats", params={"today": "2026-11-22"})).json()
    assert stats["streak_days"] == 3
    assert (stats["sessions_total"], stats["sessions_this_week"]) == (4, 3)
    assert stats["ideas_understood"] == 3
    topics = {t["topic"].lower(): t for t in stats["topics"]}
    assert set(topics) == {"photosynthesis", "gravity"}  # talk sessions aren't topics; case merged
    assert topics["photosynthesis"]["sessions"] == 2 and topics["photosynthesis"]["ideas_understood"] == 2
    assert len(stats["last_14_days"]) == 14 and stats["last_14_days"][-1] == {"day": "2026-11-22", "active": True}

    # No session today yet: yesterday's streak still counts
    assert (await client.get("/me/stats", params={"today": "2026-11-23"})).json()["streak_days"] == 3
    assert (await client.get("/me/stats", params={"today": "2026-11-25"})).json()["streak_days"] == 0


async def test_new_call_records_mode_language_topic_and_owner(client, redis):
    user = await signup(client)
    call = (await client.post("/calls/", json={"language": "te-IN", "mode": "study", "topic": " Gravity ", "voice": "shubh"})).json()
    async with session_scope() as db:
        row = await db.get(Interview, call["session_id"])
    assert (row.interview_mode, row.language, row.topic, row.user_id) == ("study", "te-IN", "Gravity", user["user_id"])
    inits = [d for _, d in await redis.xrange("interview:requests") if d["message_type"] == "system_init"]
    assert inits[-1]["topic"] == "Gravity"
    from services import active_calls

    assert (await active_calls.get(call["call_id"]))["voice"] == "shubh"
