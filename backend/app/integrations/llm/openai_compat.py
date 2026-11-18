"""Client for any OpenAI-compatible chat endpoint (Groq, Gemini's OpenAI endpoint, Ollama,
OpenRouter, vLLM...). One adapter instead of one per vendor keeps the provider swappable by
config only.

Resilience: hard timeout, bounded retries with jittered backoff on 429/5xx, and a circuit
breaker so a dead provider costs one fast failure per request instead of a 12 s hang.
"""

from __future__ import annotations

import asyncio
import random
import time

import httpx

from app.core.logging import get_logger
from app.core.metrics import LLM_CALLS, LLM_LATENCY
from app.integrations.llm.base import LLMMessage, LLMUnavailable

log = get_logger(__name__)


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 4, reset_after_s: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.reset_after_s = reset_after_s
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self.reset_after_s:
            return False  # half-open: let one request probe
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = time.monotonic()


class OpenAICompatProvider:
    def __init__(self, *, base_url: str, api_key: str, model: str, timeout_s: float,
                 max_retries: int = 2) -> None:
        if not base_url or not model:
            raise ValueError("LLM_BASE_URL and LLM_MODEL are required for openai_compat")
        self.name = f"openai_compat:{model}"
        self._model = model
        self._max_retries = max_retries
        self._breaker = CircuitBreaker()
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), headers=headers,
            timeout=httpx.Timeout(timeout_s, connect=5.0),
        )

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        purpose: str,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 400,
    ) -> str:
        if self._breaker.is_open:
            LLM_CALLS.labels(purpose, "circuit_open").inc()
            raise LLMUnavailable("circuit open")

        body: dict[str, object] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        last_err: Exception | None = None
        for attempt in range(self._max_retries + 1):
            start = time.perf_counter()
            try:
                resp = await self._client.post("/chat/completions", json=body)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise httpx.HTTPStatusError("retryable", request=resp.request, response=resp)
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise LLMUnavailable("empty completion")
                self._breaker.record_success()
                LLM_CALLS.labels(purpose, "ok").inc()
                return content
            except (httpx.HTTPError, KeyError, ValueError, LLMUnavailable) as e:
                last_err = e
                retryable = isinstance(e, httpx.TransportError | httpx.HTTPStatusError) and (
                    not isinstance(e, httpx.HTTPStatusError)
                    or e.response.status_code in (429, 500, 502, 503, 504)
                )
                if not retryable or attempt == self._max_retries:
                    break
                await asyncio.sleep((0.4 * 2**attempt) + random.random() * 0.2)  # noqa: S311
            finally:
                LLM_LATENCY.labels(purpose).observe(time.perf_counter() - start)

        self._breaker.record_failure()
        LLM_CALLS.labels(purpose, "error").inc()
        log.warning("llm_call_failed", purpose=purpose, error=str(last_err))
        raise LLMUnavailable(str(last_err))
