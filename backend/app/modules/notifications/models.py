from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Enum, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CampusScoped, Timestamps, UUIDPk
from app.domain.enums import NotificationKind


class Notification(UUIDPk, CampusScoped, Timestamps, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_inbox", "user_id", text("created_at DESC")),
        Index("ix_notifications_unread", "user_id", postgresql_where=text("read_at IS NULL")),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[NotificationKind] = mapped_column(
        Enum(NotificationKind, name="notification_kind",
             values_callable=lambda x: [m.value for m in x])
    )
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(300))
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    # e.g. "match:<lost_id>:<item_id>". Unique => retries never double-notify.
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    read_at: Mapped[datetime | None]
    emailed_at: Mapped[datetime | None]
