"""LLM Pool: Sarvam-105B for the spoken replies, Gemini behind it and for analysis.

- Fast Pool: Sarvam-105B first (Indian languages), then the Gemini fallback list
- Slow Pool: Gemini (reports, scoring, structured JSON)

Pool provides round-robin load balancing across multiple client instances
and automatic failover across candidate models.
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================


class SecurityError(Exception):
    """Raised when a security check fails."""

    pass


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class LLMConfig:
    """Configuration for LLM instances."""

    model_name: str
    temperature: float = 0.7
    max_output_tokens: int = 1024
    top_p: float = 0.95
    top_k: int = 40


FALLBACK_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3-flash-preview",
    "gemma-4-26b-a4b-it",
    "gemini-3.5-flash",
]

# Default configurations for each brain type
FAST_BRAIN_CONFIG = LLMConfig(
    model_name="gemini-3.5-flash-lite",
    temperature=0.7,
    max_output_tokens=1024,
    top_p=0.9,
)

SLOW_BRAIN_CONFIG = LLMConfig(
    model_name="gemini-3.5-flash-lite",
    temperature=0.3,
    max_output_tokens=2048,
    top_p=0.95,
)


# =============================================================================
# Sarvam (OpenAI-compatible chat completions)
# =============================================================================

SARVAM_CHAT_URL = "https://api.sarvam.ai/v2/chat/completions"
_sarvam_http: httpx.AsyncClient | None = None


def _sarvam_enabled() -> bool:
    from core.config import settings

    return bool(settings.sarvam_api_key) and settings.fast_llm_provider == "sarvam"


async def sarvam_generate(
    prompt: str,
    system_instruction: str | None,
    temperature: float,
    max_tokens: int,
) -> str:
    """One chat completion from Sarvam. Raises on any failure or an empty answer.

    reasoning_effort="none": the model otherwise spends its whole token budget on
    hidden reasoning (empty answer at 1024 tokens; ~6 s with "low", ~1 s with "none").
    """
    from core.config import settings

    global _sarvam_http
    if _sarvam_http is None:
        _sarvam_http = httpx.AsyncClient(timeout=settings.sarvam_llm_timeout_seconds)
    messages = [{"role": "user", "content": prompt}]
    if system_instruction:
        messages.insert(0, {"role": "system", "content": system_instruction})
    response = await _sarvam_http.post(
        SARVAM_CHAT_URL,
        headers={
            "api-subscription-key": settings.sarvam_api_key,
            "Authorization": f"Bearer {settings.sarvam_api_key}",
        },
        json={
            "model": settings.sarvam_llm_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "reasoning_effort": settings.sarvam_reasoning_effort,
        },
    )
    response.raise_for_status()
    content = (response.json()["choices"][0]["message"].get("content") or "").strip()
    if not content:
        raise RuntimeError("Sarvam returned an empty answer")
    return content


# =============================================================================
# LLM Wrapper
# =============================================================================


@dataclass
class LLMClient:
    """Wrapper around Google GenAI Client with native async and auto-fallback."""

    client: genai.Client
    config: LLMConfig
    client_id: int
    brain_type: Literal["fast", "slow"]
    system_instruction: str | None = None
    request_count: int = 0
    error_count: int = 0
    # Track the active model per-client to avoid mutating the shared config
    _current_model: str = field(default="", init=False)

    def __post_init__(self) -> None:
        """Initialize current model from config."""
        self._current_model = self.config.model_name

    def _get_candidate_models(self) -> list[str]:
        """Return prioritized list of models starting with current model."""
        current = self._current_model
        ordered = [current] + [m for m in FALLBACK_MODELS if m != current]
        return ordered

    async def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        user_input: str | None = None,
    ) -> str:
        """Generate a response from the model with automatic fallback."""
        from core.prompt_firewall import get_firewall

        # SECURITY LAYER 2: Firewall check before sending to LLM
        firewall = get_firewall()
        firewall_decision = firewall.analyze(prompt, user_input or "")

        if firewall_decision.action == "block":
            logger.error(
                f"[SECURITY] Prompt BLOCKED by firewall (client {self.client_id}): "
                f"{firewall_decision.reason}"
            )
            raise SecurityError(f"Prompt blocked by security firewall: {firewall_decision.reason}")

        if firewall_decision.action == "warn":
            logger.warning(
                f"[SECURITY] Prompt WARNING from firewall (client {self.client_id}): "
                f"{firewall_decision.reason}"
            )

        sys_inst = system_instruction or self.system_instruction

        # Spoken replies: Sarvam-105B first; on any failure, the Gemini list below
        if self.brain_type == "fast" and _sarvam_enabled():
            started = time.perf_counter()
            try:
                text = await sarvam_generate(
                    prompt,
                    sys_inst,
                    temperature or self.config.temperature,
                    max_tokens or self.config.max_output_tokens,
                )
                self.request_count += 1
                logger.info(f"[LLM] sarvam answered in {time.perf_counter() - started:.2f}s")
                return text
            except Exception as e:
                logger.warning(
                    f"[LLM] Sarvam failed after {time.perf_counter() - started:.2f}s "
                    f"({type(e).__name__}: {str(e)[:120]}); falling back to Gemini"
                )

        gen_config = types.GenerateContentConfig(
            system_instruction=sys_inst,
            temperature=temperature or self.config.temperature,
            max_output_tokens=max_tokens or self.config.max_output_tokens,
        )

        candidate_models = self._get_candidate_models()
        last_exception: Exception | None = None

        for model_name in candidate_models:
            try:
                response = await self.client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=gen_config,
                )

                # Track which model succeeded per-client (no shared state mutation)
                self._current_model = model_name
                self.request_count += 1

                if response.text:
                    return response.text
                else:
                    # Empty response from this model — try next
                    logger.warning(f"Empty response from model {model_name} (client {self.client_id}), trying next...")
                    continue

            except Exception as e:
                err_str = str(e)
                last_exception = e
                logger.warning(
                    f"Model {model_name} failed (client {self.client_id}): {err_str[:120]}. "
                    f"Attempting fallback..."
                )
                continue

        self.error_count += 1
        logger.error(f"All LLM models failed (client {self.client_id}): {last_exception}")
        raise last_exception if last_exception else RuntimeError("LLM generation failed on all models")

    async def generate_with_schema(
        self,
        prompt: str,
        response_schema: dict[str, Any],
        system_instruction: str | None = None,
    ) -> dict[str, Any]:
        """Generate a response with structured output (JSON mode) with auto-fallback."""
        sys_inst = system_instruction or self.system_instruction
        gen_config = types.GenerateContentConfig(
            system_instruction=sys_inst,
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_output_tokens,
            response_mime_type="application/json",
        )

        candidate_models = self._get_candidate_models()
        last_exception: Exception | None = None

        for model_name in candidate_models:
            try:
                response = await self.client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=gen_config,
                )

                self._current_model = model_name
                self.request_count += 1

                if response.text:
                    raw = response.text.strip()
                    if raw.startswith("```json"):
                        raw = raw[7:]
                    elif raw.startswith("```"):
                        raw = raw[3:]
                    if raw.endswith("```"):
                        raw = raw[:-3]
                    return json.loads(raw.strip())
                # Empty response — try next model
                continue

            except Exception as e:
                err_str = str(e)
                last_exception = e
                logger.warning(
                    f"Structured model {model_name} failed (client {self.client_id}): {err_str[:120]}. "
                    f"Attempting fallback..."
                )
                continue

        self.error_count += 1
        logger.error(f"All structured LLM models failed (client {self.client_id}): {last_exception}")
        raise last_exception if last_exception else RuntimeError("Structured generation failed on all models")


# =============================================================================
# LLM Pool
# =============================================================================


@dataclass
class GeminiLLMPool:
    """Connection pool for Gemini LLM instances using modern google.genai."""

    fast_pool_size: int = 3
    slow_pool_size: int = 2
    fast_clients: list[LLMClient] = field(default_factory=list)
    slow_clients: list[LLMClient] = field(default_factory=list)
    _fast_index: int = 0
    _slow_index: int = 0
    _initialized: bool = False
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def initialize(self, api_key: str | None = None) -> None:
        """Initialize the LLM pool with Gemini clients."""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            if not key:
                raise ValueError(
                    "Google API key not found. "
                    "Set GOOGLE_API_KEY or GEMINI_API_KEY environment variable."
                )

            genai_client = genai.Client(api_key=key)

            # Create fast brain clients — each gets its OWN config copy to avoid
            # shared mutable state bugs when fallback mutates model_name
            for i in range(self.fast_pool_size):
                sys_prompt = self._get_fast_brain_system_prompt()
                client = LLMClient(
                    client=genai_client,
                    config=LLMConfig(
                        model_name=FAST_BRAIN_CONFIG.model_name,
                        temperature=FAST_BRAIN_CONFIG.temperature,
                        max_output_tokens=FAST_BRAIN_CONFIG.max_output_tokens,
                        top_p=FAST_BRAIN_CONFIG.top_p,
                        top_k=FAST_BRAIN_CONFIG.top_k,
                    ),
                    client_id=i,
                    brain_type="fast",
                    system_instruction=sys_prompt,
                )
                self.fast_clients.append(client)

            # Create slow brain clients — each gets its OWN config copy
            for i in range(self.slow_pool_size):
                sys_prompt = self._get_slow_brain_system_prompt()
                client = LLMClient(
                    client=genai_client,
                    config=LLMConfig(
                        model_name=SLOW_BRAIN_CONFIG.model_name,
                        temperature=SLOW_BRAIN_CONFIG.temperature,
                        max_output_tokens=SLOW_BRAIN_CONFIG.max_output_tokens,
                        top_p=SLOW_BRAIN_CONFIG.top_p,
                        top_k=SLOW_BRAIN_CONFIG.top_k,
                    ),
                    client_id=i,
                    brain_type="slow",
                    system_instruction=sys_prompt,
                )
                self.slow_clients.append(client)

            self._initialized = True
            logger.info(
                f"LLM Pool initialized: {self.fast_pool_size} fast clients, "
                f"{self.slow_pool_size} slow clients"
            )

    def get_fast_client(self) -> LLMClient:
        """Get a fast brain client using round-robin selection."""
        if not self.fast_clients:
            raise RuntimeError("LLM Pool not initialized. Call initialize() first.")

        client = self.fast_clients[self._fast_index % len(self.fast_clients)]
        self._fast_index += 1
        return client

    def get_slow_client(self) -> LLMClient:
        """Get a slow brain client using round-robin selection."""
        if not self.slow_clients:
            raise RuntimeError("LLM Pool not initialized. Call initialize() first.")

        client = self.slow_clients[self._slow_index % len(self.slow_clients)]
        self._slow_index += 1
        return client

    def get_client(self, brain_type: Literal["fast", "slow"]) -> LLMClient:
        """Get a client of the specified brain type."""
        if brain_type == "fast":
            return self.get_fast_client()
        return self.get_slow_client()

    def get_healthiest_client(self, brain_type: Literal["fast", "slow"]) -> LLMClient:
        """Get the client with the lowest error rate."""
        clients = self.fast_clients if brain_type == "fast" else self.slow_clients
        if not clients:
            raise RuntimeError("LLM Pool not initialized.")

        def error_rate(c: LLMClient) -> float:
            if c.request_count == 0:
                return 0.0
            return c.error_count / c.request_count

        return min(clients, key=error_rate)

    def get_stats(self) -> dict[str, Any]:
        """Get pool statistics."""
        return {
            "fast_pool": {
                "size": len(self.fast_clients),
                "total_requests": sum(c.request_count for c in self.fast_clients),
                "total_errors": sum(c.error_count for c in self.fast_clients),
            },
            "slow_pool": {
                "size": len(self.slow_clients),
                "total_requests": sum(c.request_count for c in self.slow_clients),
                "total_errors": sum(c.error_count for c in self.slow_clients),
            },
        }

    def _get_fast_brain_system_prompt(self) -> str:
        """System prompt for the fast brain (the study buddy's spoken replies)."""
        return """You are a warm, encouraging study buddy talking with a learner by voice.
Reply quickly, briefly and kindly, in plain spoken sentences. Follow the task and the output
format you are given exactly. Never grade or judge the learner."""

    def _get_slow_brain_system_prompt(self) -> str:
        """System prompt for slow brain (analysis-focused)."""
        return """You are an AI system doing careful analysis for a study-buddy app.

Your role in this mode (Slow Brain):
- Track what the learner understands, from their own words
- Write kind, encouraging session summaries for the learner
- Provide structured, data-rich outputs

Guidelines:
- Be thorough and evidence-based
- Cite sources for all claims
- Use structured formats (JSON when requested)
- Prioritize accuracy over speed
- Flag any inconsistencies or concerns"""


# =============================================================================
# Singleton Pattern
# =============================================================================


_pool_instance: GeminiLLMPool | None = None
_pool_lock = asyncio.Lock()


async def get_llm_pool() -> GeminiLLMPool:
    """Get the global LLM pool instance (singleton)."""
    global _pool_instance

    if _pool_instance is None:
        async with _pool_lock:
            if _pool_instance is None:
                _pool_instance = GeminiLLMPool()
                await _pool_instance.initialize()

    return _pool_instance


def get_llm_pool_sync() -> GeminiLLMPool | None:
    """Get the pool instance synchronously (may be None if not initialized)."""
    return _pool_instance
