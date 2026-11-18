from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, Enum, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CampusScoped, Timestamps, UUIDPk
from app.domain.enums import LostReportStatus
from app.integrations.embeddings.base import EMBEDDING_DIM


class LostReport(UUIDPk, CampusScoped, Timestamps, Base):
    """A standing watch: re-matched against every new found item until resolved/expired."""

    __tablename__ = "lost_reports"
    __table_args__ = (
        # Reverse matching only scans OPEN watches on the same campus.
        Index("ix_lost_reports_open", "campus_id", "category", "lost_from",
              postgresql_where=text("status = 'open'")),
        Index("ix_lost_reports_embedding_hnsw", "embedding", postgresql_using="hnsw",
              postgresql_with={"m": 16, "ef_construction": 64},
              postgresql_ops={"embedding": "vector_cosine_ops"}),
        Index("ix_lost_reports_owner", "owner_id", text("created_at DESC")),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    title: Mapped[str] = mapped_column(String(140))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(40))
    item_type: Mapped[str | None] = mapped_column(String(40))
    colors: Mapped[list[str]] = mapped_column(ARRAY(String(30)), default=list)
    brand: Mapped[str | None] = mapped_column(String(60))

    location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )
    location_detail: Mapped[str | None] = mapped_column(String(200))
    lost_from: Mapped[datetime]
    lost_to: Mapped[datetime]

    status: Mapped[LostReportStatus] = mapped_column(
        Enum(LostReportStatus, name="lost_report_status",
             values_callable=lambda x: [m.value for m in x]),
        default=LostReportStatus.OPEN,
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(String(80))
    expires_at: Mapped[datetime]
    last_matched_at: Mapped[datetime | None]
