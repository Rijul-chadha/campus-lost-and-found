from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OutboxEvent(Base):
    """Transactional outbox.

    Domain writes insert a row here in the SAME transaction as the state change. A relay in
    the worker publishes unpublished rows to the job queue. So either both the state change
    and the event happen, or neither does: no lost notifications if the process crashes
    between "commit" and "enqueue".
    """

    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_unpublished", "id", postgresql_where=text("published_at IS NULL")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(80))
    aggregate_id: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    published_at: Mapped[datetime | None]
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
