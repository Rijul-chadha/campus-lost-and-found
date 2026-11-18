from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import CustodyEventType, HolderType, ItemStatus
from app.domain.vocabulary import CATEGORIES, ITEM_TYPE_TO_CATEGORY
from app.modules.campus.schemas import DeskOut, LocationOut


class FoundItemCreate(BaseModel):
    title: str = Field(min_length=2, max_length=140)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = None
    item_type: str | None = None
    colors: list[str] = Field(default_factory=list, max_length=4)
    brand: str | None = Field(default=None, max_length=60)
    found_location_id: uuid.UUID | None = None
    found_location_detail: str | None = Field(default=None, max_length=200)
    found_at: datetime
    holder_type: HolderType = HolderType.FINDER
    holder_desk_id: uuid.UUID | None = None
    private_detail: str | None = Field(default=None, min_length=3, max_length=500)
    upload_keys: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("category")
    @classmethod
    def _cat(cls, v: str | None) -> str | None:
        if v is not None and v not in CATEGORIES:
            raise ValueError(f"unknown category; expected one of {', '.join(CATEGORIES)}")
        return v

    @field_validator("item_type")
    @classmethod
    def _type(cls, v: str | None) -> str | None:
        if v is not None and v not in ITEM_TYPE_TO_CATEGORY:
            raise ValueError("unknown item_type")
        return v

    @field_validator("found_at")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("found_at must include a timezone offset")
        return v


class PhotoOut(BaseModel):
    url: str
    thumb_url: str


class ViewerFlags(BaseModel):
    is_reporter: bool
    can_view_private: bool
    can_claim: bool
    has_active_claim: bool


class ReporterOut(BaseModel):
    id: uuid.UUID
    display_name: str | None


class CustodyEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_type: CustodyEventType
    actor_id: uuid.UUID | None
    from_holder: str | None
    to_holder: str | None
    note: str | None
    created_at: datetime


class FoundItemOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    category: str | None
    item_type: str | None
    colors: list[str]
    brand: str | None
    is_sensitive: bool
    location: LocationOut | None
    location_detail: str | None
    found_at: datetime
    status: ItemStatus
    holder_type: HolderType
    holder_desk: DeskOut | None
    photos: list[PhotoOut]
    photos_hidden: bool
    created_at: datetime
    expires_at: datetime
    viewer: ViewerFlags


class FoundItemPrivateOut(FoundItemOut):
    private_detail: str | None
    reporter: ReporterOut
    custody: list[CustodyEventOut]


class UploadIntentIn(BaseModel):
    content_type: str = Field(pattern=r"^image/(jpeg|png|webp|heic|heif)$")


class UploadIntentOut(BaseModel):
    key: str
    url: str
    fields: dict[str, str]
    max_bytes: int
