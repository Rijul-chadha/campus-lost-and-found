from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, MetaData, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# Deterministic constraint names => clean, reviewable Alembic diffs.
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
    type_annotation_map = {
        dict[str, Any]: JSONB,
        datetime: DateTime(timezone=True),
    }


class UUIDPk:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CampusScoped:
    """Every tenant-owned row carries campus_id. Queries always filter on it."""

    @declared_attr
    def campus_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805
        return mapped_column(
            ForeignKey("campuses.id", ondelete="CASCADE"), index=True, nullable=False
        )
