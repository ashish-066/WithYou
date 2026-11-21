"""The organization provides the candidate's background with the invite."""

import json

from api_helpers import create_invite, fresh_client, signup

BACKGROUND = {
    "github_url": "github.com/jane",  # bare: https:// is added
    "linkedin_url": "https://linkedin.com/in/jane",
    "other_links": ["https://jane.dev", "https://jane.dev", "kaggle.com/jane"],
    "resume_text": "Jane Doe. Backend Engineer at Acme Pay 2021-2024.",
    "linkedin_text": "Jane Doe. Senior Backend Engineer, Acme Pay.",
}


async def test_background_is_stored_and_shown_to_the_org_only(client):
    await signup(client)
    invite = await create_invite(client, **BACKGROUND)

    [row] = (await client.get("/auth/invites")).json()["invites"]
    assert row["background"] == {
        "github_url": "https://github.com/jane",
        "linkedin_url": "https://linkedin.com/in/jane",
        "other_links": ["https://jane.dev", "https://kaggle.com/jane"],  # cleaned, no duplicates
        "has_resume": True,
        "has_linkedin_export": True,
    }
    assert "resume_text" not in json.dumps(row)  # documents stay server-side

    # The candidate's view of the link reveals none of it
    async with fresh_client(client) as cand:
        lookup = (await cand.post("/auth/invites/lookup", json={"token": invite["token"]})).json()
    assert "background" not in lookup and "github" not in json.dumps(lookup)


async def test_bad_links_are_refused(client):
    await signup(client)
    for bad in ({"github_url": "javascript:alert(1)"}, {"other_links": ["file:///etc/passwd"]},
                {"other_links": ["not a link"]}, {"other_links": [f"https://x{i}.dev" for i in range(11)]}):
        r = await client.post("/auth/invites", json={"candidate_name": "Cara", **bad})
        assert r.status_code == 422, bad


async def test_interview_uses_the_invites_background_not_the_browsers(client, redis):
    await signup(client)
    invite = await create_invite(client, candidate_name="Jane Doe", **BACKGROUND)
    async with fresh_client(client) as cand:
        r = await cand.post("/calls/", json={
            "invite_token": invite["token"], "candidate_name": "Someone Else",
            "github_url": "https://github.com/impostor", "resume_text": "fake resume",
        })
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]

    [init] = [d for _, d in await redis.xrange("interview:requests")
              if d["message_type"] == "system_init" and d["session_id"] == sid]
    assert json.loads(init["urls"]) == {
        "linkedin": "https://linkedin.com/in/jane",
        "github": "https://github.com/jane",
        "other": ["https://jane.dev", "https://kaggle.com/jane"],
    }
    assert init["resume_text"] == BACKGROUND["resume_text"]
    assert init["linkedin_text"] == BACKGROUND["linkedin_text"]

    call = json.loads(await redis.get(f"call:{r.json()['call_id']}"))
    assert call["candidate_name"] == "Jane Doe"  # the invite's name, not the browser's
