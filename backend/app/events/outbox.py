from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.events.models import OutboxEvent


class EventType(StrEnum):
    FOUND_ITEM_CREATED = "found_item.created"
    LOST_REPORT_CREATED = "lost_report.created"
    LOST_REPORT_RENEWED = "lost_report.renewed"
    NOTIFICATION_CREATED = "notification.created"


def emit(session: AsyncSession, event_type: EventType, aggregate_id: object,
         payload: dict[str, Any] | None = None) -> None:
    """Stage an event in the caller's transaction. Published only if the transaction commits."""
    session.add(OutboxEvent(event_type=event_type.value, aggregate_id=str(aggregate_id),
                            payload=payload or {}))
