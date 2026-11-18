from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domain.enums import Role


class RequestCodeIn(BaseModel):
    email: EmailStr


class VerifyCodeIn(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    campus_id: uuid.UUID
    email: str
    display_name: str | None
    role: Role
    desk_id: uuid.UUID | None


class UpdateProfileIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
