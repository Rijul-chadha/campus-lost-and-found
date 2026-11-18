from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CampusScoped, Timestamps, UUIDPk
from app.domain.enums import Role


class User(UUIDPk, CampusScoped, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_campus_email", "campus_id", func.lower("email"), unique=True),
    )

    email: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(120))
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="user_role", values_callable=lambda e: [m.value for m in e]),
        default=Role.MEMBER,
    )
    # Desk staff belong to exactly one desk; items they take custody of are held there.
    desk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("desks.id", ondelete="SET NULL")
    )
    last_login_at: Mapped[datetime | None]
