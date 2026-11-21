"""Ended interviews are copied to Postgres."""

from alex_db import Interview, Organization, session_scope

from brain.processor import MessageProcessor
from services.interview_store import save_interview_outcome
from services.streams import StreamMessage

STATE = {
    "session_id": "session-1",
    "interview_ended": True,
    "end_reason": "user_ended",
    "descriptive_report": {"summary": "Strong backend fundamentals"},
    "analytics_data": {"talk_ratio": 0.6},
    "running_scores": {"technical": 7.5},
    "trust_score": 0.9,
    "skill_tree": {"skills": {"python": 3}},
    "cheat_flags": [],
    "messages": [{"role": "user", "content": "hi"}],
}


async def get(session_id):
    async with session_scope() as db:
        return await db.get(Interview, session_id)


async def test_outcome_inserted_for_unknown_session(db):
    assert await save_interview_outcome("session-1", STATE)

    row = await get("session-1")
    assert row.status == "ended" and row.org_id is None
    assert row.report == {"summary": "Strong backend fundamentals"}
    assert row.scores["running_scores"] == {"technical": 7.5}
    assert row.transcript["messages"][0]["content"] == "hi"


async def test_resave_keeps_owner_and_first_end_time(db):
    async with session_scope() as s:
        s.add(Organization(id="org-1", name="Acme"))
        await s.flush()  # no ORM relationship, so insert the org first explicitly
        s.add(Interview(session_id="session-1", org_id="org-1", status="created",
                        candidate_name="Cara"))
    await save_interview_outcome("session-1", STATE)
    first_end = (await get("session-1")).ended_at

    later = {**STATE, "analytics_data": {"dsa_report": "done"}}
    await save_interview_outcome("session-1", later)

    row = await get("session-1")
    assert row.org_id == "org-1" and row.candidate_name == "Cara"
    assert row.ended_at == first_end
    assert row.analytics == {"dsa_report": "done"}


async def test_processor_saves_outcome_when_interview_ends(db, redis):
    class EndingGraph:
        async def ainvoke(self, state, config=None):
            return {**state, **STATE, "session_id": state["session_id"], "response": ""}

    msg = StreamMessage("1-0", "s", "session-9", "end_call", "", "", {"end_reason": "user_ended"})
    result = await MessageProcessor(redis, graph=EndingGraph()).process(msg)

    assert result["success"]
    row = await get("session-9")
    assert row is not None and row.report["summary"] == "Strong backend fundamentals"
