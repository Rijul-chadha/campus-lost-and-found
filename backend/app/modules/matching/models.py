from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ARRAY, Enum, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CampusScoped, Timestamps, UUIDPk
from app.domain.enums import MatchStatus


class Match(UUIDPk, CampusScoped, Timestamps, Base):
    __tablename__ = "matches"
    __table_args__ = (
        # Idempotency for the matcher: re-running a job can never create a duplicate pair,
        # so it can never notify twice for the same pair either.
        UniqueConstraint("lost_report_id", "found_item_id", name="uq_matches_pair"),
        Index("ix_matches_found_item", "found_item_id"),
    )

    lost_report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lost_reports.id", ondelete="CASCADE"), index=True
    )
    found_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("found_items.id", ondelete="CASCADE")
    )
    score: Mapped[float] = mapped_column(Float)
    components: Mapped[dict[str, Any]]
    reasons: Mapped[list[str]] = mapped_column(ARRAY(String(200)), default=list)
    status: Mapped[MatchStatus] = mapped_column(
        Enum(MatchStatus, name="match_status", values_callable=lambda x: [m.value for m in x]),
        default=MatchStatus.SUGGESTED,
    )
