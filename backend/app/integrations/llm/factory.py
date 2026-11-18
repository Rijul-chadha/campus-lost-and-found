from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.integrations.llm.base import LLMMessage, LLMProvider, LLMUnavailable


class NoLLM:
    """Configured when LLM_PROVIDER=none. Every call fails fast into the rule-based path."""

    name = "none"

    async def complete(self, messages: list[LLMMessage], *, purpose: str,
                       json_mode: bool = False, temperature: float = 0.2,
                       max_tokens: int = 400) -> str:
        raise LLMUnavailable("no LLM configured")


@lru_cache
def get_llm() -> LLMProvider:
    s = get_settings()
    if s.llm_provider == "openai_compat":
        from app.integrations.llm.openai_compat import OpenAICompatProvider

        return OpenAICompatProvider(base_url=s.llm_base_url, api_key=s.llm_api_key,
                                    model=s.llm_model, timeout_s=s.llm_timeout_seconds)
    return NoLLM()
