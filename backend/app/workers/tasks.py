"""Background jobs. Every job is idempotent: safe to retry, safe to run twice."""

from __future__ import annotations

import asyncio
import functools
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from arq import Retry
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import JOBS, NOTIFICATIONS_SENT
from app.db.session import get_sessionmaker
from app.domain.enums import CustodyEventType, ItemStatus, LostReportStatus, NotificationKind
from app.domain.extraction import embedding_text
from app.domain.state_machine import LOST_REPORT
from app.events.models import OutboxEvent
from app.integrations.email import send_email
from app.integrations.embeddings import embed_texts
from app.integrations.images import scrub
from app.integrations.storage import get_storage
from app.modules.auth.models import User
from app.modules.items.models import FoundItem
from app.modules.items.service import holder_label, record_custody, transition
from app.modules.lost_reports.models import LostReport
from app.modules.matching import service as matching
from app.modules.notifications.models import Notification
from app.modules.notifications.service import notify, notify_desk

log = get_logger(__name__)
JobFn = Callable[..., Awaitable[Any]]


def job(fn: JobFn) -> JobFn:
    """Metrics + exponential retry for transient failures."""

    @functools.wraps(fn)
    async def wrapper(ctx: dict[str, Any], *args: Any) -> Any:
        try:
            result = await fn(ctx, *args)
            JOBS.labels(fn.__name__, "ok").inc()
            return result
        except Retry:
            raise
        except Exception as e:
            tries = ctx.get("job_try", 1)
            JOBS.labels(fn.__name__, "error").inc()
            log.exception("job_failed", job=fn.__name__, args=[str(a) for a in args], tries=tries)
            if tries < 5:
                raise Retry(defer=min(300, 2 ** tries * 5)) from e
            raise

    return wrapper


@job
async def process_found_item(ctx: dict[str, Any], item_id: str) -> str:
    """Scrub photos, embed, publish, then reverse-match against open watches."""
    settings = get_settings()
    storage = get_storage()
    sm = get_sessionmaker()
    uploads_to_delete: list[str] = []

    async with sm() as s:
        item = await s.get(FoundItem, uuid.UUID(item_id), with_for_update=True)
        if item is None:
            return "missing"
        if item.status is not ItemStatus.REPORTED:
            return f"skip:{item.status.value}"  # already processed or withdrawn

        photo_keys: list[str] = []
        for n, key in enumerate(item.upload_keys):
            try:
                full, thumb = await asyncio.to_thread(scrub, await storage.get_bytes(key))
            except ValueError:
                log.warning("invalid_upload_skipped", item_id=item_id, key=key)
                continue
            base = f"items/{item.campus_id}/{item.id}/{n}"
            await storage.put_bytes(f"{base}.jpg", full, "image/jpeg")
            await storage.put_bytes(f"{base}_t.jpg", thumb, "image/jpeg")
            photo_keys.append(base)
            uploads_to_delete.append(key)

        # Embed the FULL text (server-side only) so sensitive items still match well.
        vectors, model = await embed_texts(settings, [embedding_text(
            title=item.title, description=item.description, item_type=item.item_type,
            category=item.category, colors=item.colors, brand=item.brand)])
        item.photo_keys, item.upload_keys = photo_keys, []
        item.embedding, item.embedding_model = vectors[0], model
        transition(item, "publish")
        await s.commit()

    for key in uploads_to_delete:  # best-effort; a bucket lifecycle rule also expires uploads/
        try:
            await storage.delete(key)
        except Exception as e:
            log.info("upload_delete_failed", key=key, error=str(e))

    async with sm() as s:
        item = await s.get(FoundItem, uuid.UUID(item_id))
        assert item is not None
        sent = await matching.match_found_item(s, settings, item)
        await s.commit()
    return f"published:notified={sent}"


@job
async def match_lost_report(ctx: dict[str, Any], report_id: str) -> str:
    settings = get_settings()
    async with get_sessionmaker()() as s:
        report = await s.get(LostReport, uuid.UUID(report_id))
        if report is None or report.status is not LostReportStatus.OPEN:
            return "skip"
        if report.embedding is None:
            vectors, model = await embed_texts(settings, [embedding_text(
                title=report.title, description=report.description, item_type=report.item_type,
                category=report.category, colors=report.colors, brand=report.brand)])
            report.embedding, report.embedding_model = vectors[0], model
        n = await matching.match_lost_report(s, settings, report)
        await s.commit()
    return f"matched:notified={n}"


@job
async def send_notification_email(ctx: dict[str, Any], notification_id: str) -> str:
    settings = get_settings()
    async with get_sessionmaker()() as s:
        n = await s.get(Notification, uuid.UUID(notification_id), with_for_update=True)
        if n is None or n.emailed_at is not None:
            return "skip"
        user = await s.get(User, n.user_id)
        if user is None:
            return "no-user"
        link = f"\n\nOpen: {settings.cors_origins[0]}{n.link}" if n.link else ""
        await send_email(settings, to=user.email, subject=n.title, body=f"{n.body}{link}")
        n.emailed_at = datetime.now(UTC)
        await s.commit()
    NOTIFICATIONS_SENT.labels(n.kind.value, "email").inc()
    return "sent"


# --- scheduled jobs ----------------------------------------------------------------------

async def expire_items(ctx: dict[str, Any]) -> int:
    """Move items past their retention window to EXPIRED and tell the desk what's waiting."""
    now = datetime.now(UTC)
    async with get_sessionmaker()() as s:
        items = (await s.execute(
            select(FoundItem).where(FoundItem.status == ItemStatus.AVAILABLE,
                                    FoundItem.expires_at < now)
            .limit(500).with_for_update(skip_locked=True)
        )).scalars().all()
        per_campus: Counter[uuid.UUID] = Counter()
        for item in items:
            transition(item, "expire")
            record_custody(s, item, CustodyEventType.EXPIRED, None,
                           from_holder=holder_label(item), note="retention window ended")
            per_campus[item.campus_id] += 1
        for campus_id, count in per_campus.items():
            await notify_desk(
                s, campus_id=campus_id, desk_id=None, kind=NotificationKind.ITEMS_EXPIRED,
                title=f"{count} unclaimed item(s) ready for a decision",
                body="Their retention period ended. Donate, dispose or extend them.",
                link="/desk?status=expired",
                dedupe_key=f"expired:{campus_id}:{now:%Y-%m-%dT%H}")
        await s.commit()
    log.info("expire_items", count=len(items))
    return len(items)


async def expire_watches(ctx: dict[str, Any]) -> int:
    now = datetime.now(UTC)
    async with get_sessionmaker()() as s:
        soon = (await s.execute(
            select(LostReport).where(LostReport.status == LostReportStatus.OPEN,
                                     LostReport.expires_at < now + timedelta(days=3),
                                     LostReport.expires_at >= now).limit(500)
        )).scalars().all()
        for r in soon:
            await notify(s, campus_id=r.campus_id, user_id=r.owner_id,
                         kind=NotificationKind.WATCH_EXPIRING,
                         title=f"Still looking for your {r.title.lower()}?",
                         body="Your watch ends in 3 days. Renew it to keep getting alerts.",
                         link=f"/me/watches/{r.id}", dedupe_key=f"watch-expiring:{r.id}")
        expired = (await s.execute(
            select(LostReport).where(LostReport.status == LostReportStatus.OPEN,
                                     LostReport.expires_at < now)
            .limit(500).with_for_update(skip_locked=True)
        )).scalars().all()
        for r in expired:
            r.status = LOST_REPORT.next("expire", r.status)
        await s.commit()
    return len(expired)


async def requeue_stuck_items(ctx: dict[str, Any]) -> int:
    """Safety net: an item stuck in REPORTED (e.g. job exhausted retries) is retried."""
    cutoff = datetime.now(UTC) - timedelta(minutes=15)
    async with get_sessionmaker()() as s:
        ids = (await s.execute(select(FoundItem.id).where(
            FoundItem.status == ItemStatus.REPORTED, FoundItem.created_at < cutoff).limit(100)
        )).scalars().all()
    for i in ids:
        await ctx["redis"].enqueue_job("process_found_item", str(i),
                                       _job_id=f"requeue:{i}:{cutoff:%Y%m%d%H%M}")
    if ids:
        log.warning("requeued_stuck_items", count=len(ids))
    return len(ids)


async def cleanup_outbox(ctx: dict[str, Any]) -> None:
    async with get_sessionmaker()() as s:
        await s.execute(delete(OutboxEvent).where(
            OutboxEvent.published_at < datetime.now(UTC) - timedelta(days=7)))
        await s.commit()


__all__ = [
    "cleanup_outbox", "expire_items", "expire_watches", "match_lost_report",
    "process_found_item", "requeue_stuck_items", "send_notification_email",
]
