from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import NotificationKind


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: NotificationKind
    title: str
    body: str
    link: str | None
    payload: dict[str, Any]
    read_at: datetime | None
    created_at: datetime


class MarkReadIn(BaseModel):
    ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    all: bool = False


class UnreadCount(BaseModel):
    unread: int
