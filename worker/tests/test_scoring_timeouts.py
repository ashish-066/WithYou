"""A slow Gemini during scoring must not hold the worker (one message at a time)."""

import asyncio
import time

from test_processor_early_reply import FakeGraph

from brain.processor import MessageProcessor
from core.config import settings
from scoring.integration import ScoringIntegration
from scoring.llm_client import scoring_llm
from services.streams import StreamMessage


def system_init() -> StreamMessage:
    return StreamMessage(
        "1-0",
        "s",
        "sess-scoring",
        "system_init",
        "",
        "",
        {"job_description": "Backend engineer: Python, Redis, PostgreSQL"},
    )


async def test_hanging_scoring_setup_is_cut_off(redis, monkeypatch):
    async def hang(self, **kwargs):
        await asyncio.sleep(30)  # stands in for Gemini retrying under load

    monkeypatch.setattr(ScoringIntegration, "initialize_scoring", hang)
    monkeypatch.setattr(settings, "scoring_init_timeout_seconds", 0.2)

    start = time.perf_counter()
    result = await MessageProcessor(redis, graph=FakeGraph(scoring_seconds=0)).process(
        system_init()
    )

    assert time.perf_counter() - start < 3
    assert result["success"]  # the interview goes on without the skill tree


def test_scoring_client_has_bounded_waits(monkeypatch):
    monkeypatch.setattr(settings, "google_api_key", "test-key")
    llm = scoring_llm(temperature=0.1)

    assert llm.timeout == settings.scoring_llm_timeout_seconds
    assert llm.max_retries == settings.scoring_llm_max_retries
    assert settings.scoring_llm_timeout_seconds <= 30
    assert settings.scoring_llm_max_retries <= 2
