from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


class LLMUnavailable(Exception):
    """Raised for any provider failure. Callers always have a non-LLM fallback."""


@dataclass(frozen=True)
class LLMMessage:
    role: Literal["system", "user", "assistant"]
    content: str


class LLMProvider(Protocol):
    name: str

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        purpose: str,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 400,
    ) -> str: ...
