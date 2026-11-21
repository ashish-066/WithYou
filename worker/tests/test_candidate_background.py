"""The candidate's background: gathering it safely, giving it to the
interviewer, and checking claims against it."""

import pytest

from brain import candidate_background as bg
from brain.brains import slow_brain
from brain.processor import MessageProcessor
from brain.tools import safe_fetch
from brain.tools.safe_fetch import UnsafeURLError, fetch_page, page_text
from services.streams import StreamMessage

PROFILE = {
    "resume": {
        "experience": [{"company": "Acme Pay", "title": "Backend Engineer", "start_year": 2021, "end_year": 2024,
                        "description": "Built the payments ledger in Go"}],
        "projects": [{"name": "rate-limiter", "description": "Token bucket service", "technologies": ["Redis"]}],
        "education": ["BSc Computer Science"],
    },
    "linkedin_export": {"experience": [{"company": "Acme Pay", "title": "Senior Backend Engineer"}]},
    "github": {"username": "jane", "repos": [
        {"name": "ledger-sim", "description": "Double-entry ledger simulator", "language": "Go", "stars": 42,
         "pushed_at": "2026-09-01T00:00:00Z", "fork": False},
        {"name": "someone-elses-lib", "fork": True},
    ]},
    "links": [{"url": "https://jane.dev", "title": "Jane's blog", "text": "Writing about distributed systems"}],
    "skills_extracted": ["Go", "Redis", "PostgreSQL"],
}


# =============================================================================
# Safe fetching of recruiter-provided links
# =============================================================================


@pytest.mark.parametrize("url", [
    "http://localhost/admin",
    "http://127.0.0.1:80/",
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata
    "http://10.0.0.5/",
    "http://[::1]/",
    "file:///etc/passwd",
    "ftp://example.com/x",
    "https://user:pass@example.com/",
    "https://example.com:8443/",
])
async def test_unsafe_links_are_refused(url):
    with pytest.raises(UnsafeURLError):
        await fetch_page(url)


async def test_redirect_to_a_private_address_is_refused(monkeypatch):
    calls = []

    async def resolve(host):
        calls.append(host)
        if host == "internal.example":
            raise UnsafeURLError("internal.example is not a public address")

    monkeypatch.setattr(safe_fetch, "_public_address", resolve)

    class Resp:
        is_redirect = True
        headers = {"location": "http://internal.example/secret"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class Client:
        def stream(self, method, url, headers=None):
            return Resp()

    with pytest.raises(UnsafeURLError):
        await fetch_page("https://jane.dev/", client=Client())
    assert calls == ["jane.dev", "internal.example"]  # checked again after the redirect


def test_page_text_drops_scripts_and_navigation():
    title, text = page_text(
        "<html><head><title>Jane</title><script>alert(1)</script></head>"
        "<body><nav>Menu</nav><h1>Projects</h1><p>Ledger   simulator</p></body></html>"
    )
    assert title == "Jane" and text == "Projects Ledger simulator"


# =============================================================================
# What the interviewer sees
# =============================================================================


def test_digest_names_specific_roles_projects_and_repos():
    d = bg.build_digest(PROFILE)
    assert "Backend Engineer, Acme Pay (2021-2024): Built the payments ledger in Go" in d
    assert "Senior Backend Engineer, Acme Pay" in d  # LinkedIn says senior: worth asking about
    assert "ledger-sim (Go, 42 stars" in d and "someone-elses-lib" not in d  # own repos only
    assert "rate-limiter: Token bucket service [Redis]" in d
    assert "Jane's blog" in d and "Skills listed: Go, Redis, PostgreSQL" in d
    assert bg.build_digest(None) == "" and bg.build_digest({}) == ""
    assert len(bg.build_digest(PROFILE, max_chars=100)) == 100


def test_next_probe_prefers_contradictions_and_probes_each_claim_once():
    state = {"verified_claims": [
        {"claim": {"id": "c1", "content": "I led the team"}, "verdict": "unverified",
         "reasoning": "no lead role listed", "suggested_followup": "How big was the team?"},
        {"claim": {"id": "c2", "content": "I was at Acme for five years"}, "verdict": "contradiction",
         "reasoning": "resume says 2021-2024", "suggested_followup": "What did you work on in your first year?"},
        {"claim": {"id": "c3", "content": "I know Go"}, "verdict": "verified", "suggested_followup": None},
    ]}
    cid, text = bg.next_probe(state)
    assert cid == "c2" and "conflicts with" in text and "first year" in text
    state["flow"] = {"probed_claims": ["c2"]}
    assert bg.next_probe(state)[0] == "c1"
    state["flow"] = {"probed_claims": ["c1", "c2"]}
    assert bg.next_probe(state) is None


# =============================================================================
# Checking claims
# =============================================================================


class FakeClient:
    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    async def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def fake_pool(monkeypatch, reply):
    client = FakeClient(reply)

    class Pool:
        def get_slow_client(self):
            return client

    async def get_pool():
        return Pool()

    monkeypatch.setattr("brain.models.llm_pool.get_llm_pool", get_pool)
    return client


async def test_claims_are_checked_against_the_whole_background(monkeypatch):
    client = fake_pool(monkeypatch, '```json\n{"results": ['
        '{"id": "c1", "verdict": "contradiction", "confidence": 0.9, "source": "resume",'
        ' "evidence": "Resume: Acme Pay 2021-2024", "followup": "When did you join Acme?"},'
        '{"id": "c2", "verdict": "verified", "confidence": 0.8, "source": "github",'
        ' "evidence": "ledger-sim repo in Go", "followup": "ignored"}]}\n```')
    claims = [{"id": "c1", "content": "Five years at Acme"}, {"id": "c2", "content": "I wrote a ledger in Go"},
              {"id": "c3", "content": "unanswered by the model"}]
    results = await bg.verify_claims(claims, PROFILE)

    assert [(r["claim"]["id"], r["verdict"]) for r in results] == [("c1", "contradiction"), ("c2", "verified")]
    assert results[0]["suggested_followup"] == "When did you join Acme?"
    assert results[1]["suggested_followup"] is None and results[1]["evidence"][0]["source"] == "github"
    prompt = client.prompts[0]
    assert "[RESUME]" in prompt and "[GITHUB]" in prompt and "[LINK https://jane.dev]" in prompt


async def test_claim_check_falls_back_when_the_model_fails(monkeypatch):
    fake_pool(monkeypatch, RuntimeError("model down"))
    assert await bg.verify_claims([{"id": "c1", "content": "x"}], PROFILE) is None
    assert await bg.verify_claims([{"id": "c1", "content": "x"}], None) is None


# =============================================================================
# Gathering it
# =============================================================================


async def test_crawl_runs_with_only_a_resume_and_uses_the_right_link_keys(monkeypatch):
    seen = {}

    async def crawler(**kwargs):
        seen.update(kwargs)

        class Out:
            success, data = True, {"resume": {}}

        return Out()

    monkeypatch.setattr(slow_brain, "profile_crawler_tool", crawler)

    # Resume only: still gathered
    queued = await slow_brain.analyze_task_node(
        {"session_id": "s", "profile_status": "not_started", "candidate_urls": {}, "candidate_resume_text": "cv"}
    )
    assert queued["pending_slow_tasks"][0]["task_type"] == "profile_crawl"

    # The call sends github / linkedin / other
    state = {"session_id": "s", "pending_slow_tasks": [{
        "task_id": "t", "task_type": "profile_crawl", "priority": 0, "created_at": "",
        "params": {"github": "https://github.com/jane", "linkedin": "https://linkedin.com/in/jane",
                   "other": ["https://jane.dev"]},
    }]}
    await slow_brain.execute_slow_tasks_node(state)
    assert seen["github_url"] == "https://github.com/jane"
    assert seen["other_links"] == ["https://jane.dev"]


async def test_processor_probes_one_doubtful_claim_on_alternate_turns(redis):
    class Graph:
        def __init__(self):
            self.seen = []

        async def ainvoke(self, st, config=None):
            self.seen.append(dict(st))
            return {**st, "turn_count": (st.get("turn_count") or 0) + 1, "response": "ok"}

    graph = Graph()
    p = MessageProcessor(redis, graph=graph)
    await p.context_manager.update_context("s1", {"session_id": "s1", "turn_count": 1, "verified_claims": [
        {"claim": {"id": "c1", "content": "I led the team"}, "verdict": "unverified",
         "reasoning": "no lead role", "suggested_followup": "How big was the team?"}]})

    await p.process(StreamMessage("1-0", "s", "s1", "candidate_response", "answer", "", {}))
    assert "How big was the team?" in graph.seen[-1]["background_probe"]
    ctx = await p.context_manager.get_context("s1")
    assert ctx["background_probe"] == "" and ctx["flow"]["probed_claims"] == ["c1"]

    # Next turns: even turn (none), then odd turn but already probed (none)
    for n in (2, 3):
        await p.process(StreamMessage(f"{n}-0", "s", "s1", "candidate_response", "answer", "", {}))
        assert graph.seen[-1]["background_probe"] == ""


# =============================================================================
# Resume and GitHub alone are enough
# =============================================================================

RESUME_TEXT = "Jane Doe\nBackend Engineer, Acme Pay 2021-2024\nBuilt the payments ledger in Go."
GITHUB_ONLY = {"github": PROFILE["github"]}


def test_resume_reaches_the_interviewer_even_if_parsing_failed():
    # Background not gathered yet (or failed): the resume as written is used
    d = bg.build_digest(None, RESUME_TEXT)
    assert "Resume (as written):" in d and "Built the payments ledger in Go." in d
    # GitHub gathered, resume parsing failed: both are there
    d = bg.build_digest(GITHUB_ONLY, RESUME_TEXT)
    assert "ledger-sim (Go" in d and "Backend Engineer, Acme Pay 2021-2024" in d
    # Parsed resume available: no need for the raw text
    assert "Resume (as written)" not in bg.build_digest(PROFILE, RESUME_TEXT)


def test_claims_are_checked_against_the_resume_as_written():
    profile = bg.profile_for_checks({"candidate_profile": GITHUB_ONLY, "candidate_resume_text": RESUME_TEXT})
    evidence = bg.build_evidence(profile)
    assert "[RESUME TEXT]" in evidence and "Acme Pay 2021-2024" in evidence and "[GITHUB]" in evidence
    # Nothing gathered at all: still checked against the resume
    assert bg.profile_for_checks({"candidate_resume_text": RESUME_TEXT}) == {"resume_text": RESUME_TEXT}
    assert bg.profile_for_checks({}) is None


async def test_interviewer_prompt_carries_resume_and_github(monkeypatch):
    from brain.tools.fast import conversation

    prompts = []

    class Client:
        async def generate(self, prompt, **kwargs):
            prompts.append(prompt)
            return '{"response_text": "Tell me about ledger-sim.", "follow_up_questions": [], ' \
                   '"topics_touched": [], "claims_detected": [], "sentiment": "neutral"}'

    class Pool:
        def get_fast_client(self):
            return Client()

    async def get_pool():
        return Pool()

    monkeypatch.setattr(conversation, "get_llm_pool", get_pool)
    state = {"session_id": "s", "current_input": "Hi, I'm Jane, a backend engineer.", "turn_count": 1,
             "candidate_profile": GITHUB_ONLY, "candidate_resume_text": RESUME_TEXT}
    out = await conversation.conversation_tool(state)

    assert out.success
    background = prompts[0].split("<candidate_background>")[1].split("</candidate_background>")[0]
    assert "ledger-sim" in background and "Acme Pay" in background
    assert "Ground your questions in <candidate_background>" in prompts[0]
