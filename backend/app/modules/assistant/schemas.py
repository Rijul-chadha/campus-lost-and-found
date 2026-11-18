from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.modules.items.schemas import FoundItemOut
from app.modules.lost_reports.schemas import LostReportCreate


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1000)


class ChatIn(BaseModel):
    """Stateless: the client sends the running conversation each turn.

    Keeps the API horizontally scalable with no session store, and caps cost per turn.
    """

    messages: list[ChatMessage] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _last_is_user(self) -> ChatIn:
        if self.messages[-1].role != "user":
            raise ValueError("last message must be from the user")
        if sum(len(m.content) for m in self.messages) > 8000:
            raise ValueError("conversation too long; start a new search")
        return self


class Extracted(BaseModel):
    category: str | None
    item_type: str | None
    colors: list[str]
    brand: str | None
    location_id: uuid.UUID | None
    location_name: str | None
    lost_from: datetime
    lost_to: datetime
    time_is_guess: bool


class AssistantMatch(BaseModel):
    score: float
    reasons: list[str]
    item: FoundItemOut


class ChatOut(BaseModel):
    reply: str
    extracted: Extracted
    missing: list[str]
    matches: list[AssistantMatch]
    watch_draft: LostReportCreate | None
    used_llm: bool
