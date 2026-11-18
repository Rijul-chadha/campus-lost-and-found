from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CampusScoped, Timestamps, UUIDPk
from app.domain.enums import CustodyEventType, HolderType, ItemStatus
from app.integrations.embeddings.base import EMBEDDING_DIM


def _enum(e: type, name: str) -> Enum:
    return Enum(e, name=name, values_callable=lambda x: [m.value for m in x])


class FoundItem(UUIDPk, CampusScoped, Timestamps, Base):
    __tablename__ = "found_items"
    __table_args__ = (
        # Main browse / candidate query: campus + status, newest first.
        Index("ix_found_items_campus_status_found_at", "campus_id", "status",
              text("found_at DESC")),
        # ANN index for semantic candidate generation. HNSW: good recall without training.
        Index("ix_found_items_embedding_hnsw", "embedding", postgresql_using="hnsw",
              postgresql_with={"m": 16, "ef_construction": 64},
              postgresql_ops={"embedding": "vector_cosine_ops"}),
        Index("ix_found_items_expiry", "expires_at",
              postgresql_where=text("status = 'available'")),
        Index("ix_found_items_reporter", "reporter_id", text("created_at DESC")),
    )

    reporter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))

    # Full text as entered (private: holder/desk/approved claimant only).
    title: Mapped[str] = mapped_column(String(140))
    description: Mapped[str | None] = mapped_column(Text)
    # Redacted copies, computed on write. Public API only ever reads these.
    public_title: Mapped[str] = mapped_column(String(140))
    public_description: Mapped[str | None] = mapped_column(Text)

    category: Mapped[str | None] = mapped_column(String(40), index=True)
    item_type: Mapped[str | None] = mapped_column(String(40))
    colors: Mapped[list[str]] = mapped_column(ARRAY(String(30)), default=list)
    brand: Mapped[str | None] = mapped_column(String(60))
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)

    found_location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )
    found_location_detail: Mapped[str | None] = mapped_column(String(200))
    found_at: Mapped[datetime]

    holder_type: Mapped[HolderType] = mapped_column(_enum(HolderType, "holder_type"))
    holder_desk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("desks.id", ondelete="SET NULL")
    )
    status: Mapped[ItemStatus] = mapped_column(
        _enum(ItemStatus, "item_status"), default=ItemStatus.REPORTED
    )

    # Object-storage keys of processed photos (originals are scrubbed + re-encoded).
    upload_keys: Mapped[list[str]] = mapped_column(ARRAY(String(300)), default=list)
    photo_keys: Mapped[list[str]] = mapped_column(ARRAY(String(300)), default=list)

    # Ownership-verification secret. Never serialised publicly, never sent to the LLM.
    private_detail: Mapped[str | None] = mapped_column(Text)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(String(80))

    expires_at: Mapped[datetime]
    # Optimistic concurrency: concurrent claim approvals cannot both win.
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class CustodyEvent(CampusScoped, Base):
    """Append-only audit log of who held an item and what happened to it.

    A DB trigger (see migration) rejects UPDATE/DELETE so the history cannot be rewritten.
    """

    __tablename__ = "custody_events"
    __table_args__ = (Index("ix_custody_events_item", "found_item_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    found_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("found_items.id", ondelete="CASCADE")
    )
    event_type: Mapped[CustodyEventType] = mapped_column(
        _enum(CustodyEventType, "custody_event_type")
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    from_holder: Mapped[str | None] = mapped_column(String(80))
    to_holder: Mapped[str | None] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
