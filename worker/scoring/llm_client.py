"""Gemini client for the scoring pipeline, with bounded waits.

The worker handles one message at a time, so a scoring call that hangs blocks every
interview on that worker. langchain-google-genai's defaults are no timeout and 6
retries with growing back-off, which kept a worker busy for minutes while Gemini
reported high demand. Every scoring step already falls back when its call fails, so
failing fast is safe.
"""

from typing import Any


def scoring_llm(temperature: float) -> Any:
    from langchain_google_genai import ChatGoogleGenerativeAI

    from core.config import settings

    return ChatGoogleGenerativeAI(
        model="gemini-3.5-flash",
        google_api_key=settings.google_api_key,
        temperature=temperature,
        timeout=settings.scoring_llm_timeout_seconds,
        max_retries=settings.scoring_llm_max_retries,
    )
