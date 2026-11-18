from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Enum, Float, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CampusScoped, Timestamps, UUIDPk
from app.domain.enums import ClaimStatus


class Claim(UUIDPk, CampusScoped, Timestamps, Base):
    __tablename__ = "claims"
    __table_args__ = (
        # A person can hold at most one live claim per item...
        Index("uq_claims_active_per_claimant", "found_item_id", "claimant_id", unique=True,
              postgresql_where=text("status IN ('pending', 'approved')")),
        # ...and an item can have at most one approved claim. Enforced by the DB, not just code,
        # so two desk staff approving different claims at the same moment cannot both succeed.
        Index("uq_claims_one_approved_per_item", "found_item_id", unique=True,
              postgresql_where=text("status = 'approved'")),
        Index("ix_claims_item_status", "found_item_id", "status"),
        Index("ix_claims_claimant", "claimant_id", text("created_at DESC")),
    )

    found_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("found_items.id", ondelete="CASCADE")
    )
    claimant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    lost_report_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lost_reports.id", ondelete="SET NULL")
    )
    proof_text: Mapped[str] = mapped_column(Text)
    # Reviewer-only hint from domain.verification (never shown to the claimant).
    proof_score: Mapped[float | None] = mapped_column(Float)
    proof_strength: Mapped[str | None] = mapped_column(String(16))

    status: Mapped[ClaimStatus] = mapped_column(
        Enum(ClaimStatus, name="claim_status", values_callable=lambda x: [m.value for m in x]),
        default=ClaimStatus.PENDING,
    )
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None]
    decision_note: Mapped[str | None] = mapped_column(Text)
    pickup_instructions: Mapped[str | None] = mapped_column(Text)
