from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    lat: float | None = None
    lng: float | None = None


class DeskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    location_id: uuid.UUID | None = None
    hours: str | None = None


class CampusOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    timezone: str
    locations: list[LocationOut]
    desks: list[DeskOut]
