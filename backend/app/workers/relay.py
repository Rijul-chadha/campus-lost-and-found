"""Outbox relay: moves committed events from Postgres into the job queue.

* `FOR UPDATE SKIP LOCKED` lets any number of worker replicas relay concurrently without
  double-publishing or blocking each other.
* `_job_id=evt:<id>` makes enqueueing idempotent at the queue level too, so a crash between
  enqueue and marking `published_at` cannot produce two jobs for one event.
* Handlers are idempotent anyway (unique constraints, status checks), i.e. at-least-once
  delivery with effectively-once effects.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from app.core.logging import get_logger
from app.core.metrics import OUTBOX_LAG
from app.db.session import get_sessionmaker
from app.events.models import OutboxEvent
from app.events.outbox import EventType

log = get_logger(__name__)

ROUTES: dict[str, str] = {
    EventType.FOUND_ITEM_CREATED.value: "process_found_item",
    EventType.LOST_REPORT_CREATED.value: "match_lost_report",
    EventType.LOST_REPORT_RENEWED.value: "match_lost_report",
    EventType.NOTIFICATION_CREATED.value: "send_notification_email",
}
MAX_ATTEMPTS = 10


async def relay_batch(ctx: dict[str, Any], batch: int = 100) -> int:
    async with get_sessionmaker()() as s:
        events = (await s.execute(
            select(OutboxEvent).where(OutboxEvent.published_at.is_(None),
                                      OutboxEvent.attempts < MAX_ATTEMPTS)
            .order_by(OutboxEvent.id).limit(batch).with_for_update(skip_locked=True)
        )).scalars().all()
        for ev in events:
            fn = ROUTES.get(ev.event_type)
            if fn is None:
                ev.published_at = datetime.now(UTC)  # nothing subscribes; mark done
                continue
            try:
                await ctx["redis"].enqueue_job(fn, ev.aggregate_id, _job_id=f"evt:{ev.id}")
                ev.published_at = datetime.now(UTC)
            except Exception as e:
                ev.attempts += 1
                ev.last_error = str(e)[:500]
                log.warning("outbox_enqueue_failed", event_id=ev.id, error=str(e))
        await s.commit()
        lag = (await s.execute(select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.published_at.is_(None)))).scalar_one()
        OUTBOX_LAG.set(lag)
        return len(events)


async def relay_forever(ctx: dict[str, Any]) -> None:
    log.info("outbox_relay_started")
    while True:
        try:
            n = await relay_batch(ctx)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("outbox_relay_error")
            n = 0
        # Drain quickly when busy, poll gently when idle (sub-second end-to-end latency).
        await asyncio.sleep(0.05 if n else 0.5)
