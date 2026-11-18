from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.enums import LostReportStatus, MatchStatus
from app.domain.vocabulary import CATEGORIES, ITEM_TYPE_TO_CATEGORY
from app.modules.campus.schemas import LocationOut
from app.modules.items.schemas import FoundItemOut


class LostReportCreate(BaseModel):
    title: str = Field(min_length=2, max_length=140)
    description: str = Field(min_length=2, max_length=2000)
    category: str | None = None
    item_type: str | None = None
    colors: list[str] = Field(default_factory=list, max_length=4)
    brand: str | None = Field(default=None, max_length=60)
    location_id: uuid.UUID | None = None
    location_detail: str | None = Field(default=None, max_length=200)
    lost_from: datetime
    lost_to: datetime

    @field_validator("category")
    @classmethod
    def _cat(cls, v: str | None) -> str | None:
        if v is not None and v not in CATEGORIES:
            raise ValueError("unknown category")
        return v

    @field_validator("item_type")
    @classmethod
    def _type(cls, v: str | None) -> str | None:
        if v is not None and v not in ITEM_TYPE_TO_CATEGORY:
            raise ValueError("unknown item_type")
        return v

    @model_validator(mode="after")
    def _window(self) -> LostReportCreate:
        if self.lost_from.tzinfo is None or self.lost_to.tzinfo is None:
            raise ValueError("lost_from/lost_to must include a timezone offset")
        if self.lost_from > self.lost_to:
            raise ValueError("lost_from must be before lost_to")
        return self


class LostReportOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    category: str | None
    item_type: str | None
    colors: list[str]
    brand: str | None
    location: LocationOut | None
    location_detail: str | None
    lost_from: datetime
    lost_to: datetime
    status: LostReportStatus
    expires_at: datetime
    created_at: datetime
    match_count: int = 0


class MatchOut(BaseModel):
    id: uuid.UUID
    score: float
    reasons: list[str]
    status: MatchStatus
    item: FoundItemOut


class LostReportDetail(LostReportOut):
    matches: list[MatchOut]
