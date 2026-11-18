from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import ClaimStatus


class ClaimCreate(BaseModel):
    found_item_id: uuid.UUID
    proof_text: str = Field(
        min_length=10, max_length=1000,
        description="Describe something only the owner would know (marks, contents, stickers).",
    )
    lost_report_id: uuid.UUID | None = None


class ApproveIn(BaseModel):
    pickup_instructions: str | None = Field(default=None, min_length=5, max_length=500)


class RejectIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class ClaimOut(BaseModel):
    """What the claimant sees."""

    id: uuid.UUID
    found_item_id: uuid.UUID
    item_title: str
    status: ClaimStatus
    created_at: datetime
    decided_at: datetime | None
    decision_note: str | None
    pickup_instructions: str | None


class ClaimantOut(BaseModel):
    id: uuid.UUID
    display_name: str | None


class ClaimReviewOut(ClaimOut):
    """What the holder (finder or desk) sees when deciding."""

    proof_text: str
    proof_strength: str | None
    proof_score: float | None
    private_detail: str | None
    claimant: ClaimantOut
