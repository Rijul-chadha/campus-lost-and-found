from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class DeskOverview(BaseModel):
    by_status: dict[str, int]
    pending_claims: int
    held_by_finders: int
    expiring_within_7d: int
    awaiting_decision: int
    returned_last_30d: int
    reported_last_30d: int
    return_rate_last_30d: float
    open_watches: int


class ReceiveIn(BaseModel):
    desk_id: uuid.UUID | None = None  # defaults to the staff member's own desk
    note: str | None = Field(default=None, max_length=300)


class CloseOutIn(BaseModel):
    action: Literal["donate", "dispose", "extend"]
    note: str | None = Field(default=None, max_length=300)
    extend_days: int = Field(default=30, ge=1, le=180)
