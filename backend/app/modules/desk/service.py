from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import apply_cursor, next_cursor_for
from app.core.security import Principal
from app.domain.enums import (
    ClaimStatus,
    CustodyEventType,
    HolderType,
    ItemStatus,
    LostReportStatus,
)
from app.domain.errors import Conflict, ValidationFailed
from app.modules.auth.models import User
from app.modules.campus.models import Desk
from app.modules.claims.models import Claim
from app.modules.desk.schemas import CloseOutIn, DeskOverview
from app.modules.items.models import CustodyEvent, FoundItem
from app.modules.items.service import get_item, holder_label, record_custody, transition
from app.modules.lost_reports.models import LostReport


async def overview(session: AsyncSession, p: Principal) -> DeskOverview:
    now = datetime.now(UTC)
    cid = p.campus_id
    by_status = dict((await session.execute(
        select(FoundItem.status, func.count()).where(FoundItem.campus_id == cid)
        .group_by(FoundItem.status))).all())

    async def count(stmt: object) -> int:
        return int((await session.execute(stmt)).scalar_one())  # type: ignore[call-overload]

    pending = await count(select(func.count()).select_from(Claim).where(
        Claim.campus_id == cid, Claim.status == ClaimStatus.PENDING))
    finders = await count(select(func.count()).select_from(FoundItem).where(
        FoundItem.campus_id == cid, FoundItem.status == ItemStatus.AVAILABLE,
        FoundItem.holder_type == HolderType.FINDER))
    expiring = await count(select(func.count()).select_from(FoundItem).where(
        FoundItem.campus_id == cid, FoundItem.status == ItemStatus.AVAILABLE,
        FoundItem.expires_at < now + timedelta(days=7)))
    month = now - timedelta(days=30)
    reported = await count(select(func.count()).select_from(FoundItem).where(
        FoundItem.campus_id == cid, FoundItem.created_at >= month))
    returned = await count(select(func.count()).select_from(CustodyEvent).where(
        CustodyEvent.campus_id == cid, CustodyEvent.event_type == CustodyEventType.RETURNED,
        CustodyEvent.created_at >= month))
    watches = await count(select(func.count()).select_from(LostReport).where(
        LostReport.campus_id == cid, LostReport.status == LostReportStatus.OPEN))
    return DeskOverview(
        by_status={k.value: v for k, v in by_status.items()}, pending_claims=pending,
        held_by_finders=finders, expiring_within_7d=expiring,
        awaiting_decision=by_status.get(ItemStatus.EXPIRED, 0),
        returned_last_30d=returned, reported_last_30d=reported,
        return_rate_last_30d=round(returned / reported, 3) if reported else 0.0,
        open_watches=watches,
    )


async def list_items(session: AsyncSession, p: Principal, *, status: ItemStatus | None,
                     holder_type: HolderType | None, q: str | None, cursor: str | None,
                     limit: int) -> tuple[list[FoundItem], str | None]:
    stmt = select(FoundItem).where(FoundItem.campus_id == p.campus_id)
    if status:
        stmt = stmt.where(FoundItem.status == status)
    if holder_type:
        stmt = stmt.where(FoundItem.holder_type == holder_type)
    if q:
        like = f"%{q.strip()[:80]}%"
        stmt = stmt.where(or_(FoundItem.title.ilike(like), FoundItem.description.ilike(like)))
    rows = list((await session.execute(
        apply_cursor(stmt, FoundItem.created_at, FoundItem.id, cursor, limit))).scalars().all())
    return next_cursor_for(rows, limit)


async def receive(session: AsyncSession, p: Principal, item_id: uuid.UUID,
                  desk_id: uuid.UUID | None, note: str | None) -> FoundItem:
    """A finder physically dropped the item at a desk; staff take custody."""
    item = await get_item(session, p, item_id, for_update=True)
    if item.status not in (ItemStatus.REPORTED, ItemStatus.AVAILABLE, ItemStatus.CLAIMED):
        raise Conflict(f"Cannot take custody of an item that is {item.status.value}")
    if desk_id is None:
        staff = await session.get(User, p.user_id)
        desk_id = staff.desk_id if staff else None
    if desk_id is None:
        raise ValidationFailed("Choose which desk is receiving the item")
    desk = await session.get(Desk, desk_id)
    if desk is None or desk.campus_id != p.campus_id:
        raise ValidationFailed("Unknown desk")
    if item.holder_type is HolderType.DESK and item.holder_desk_id == desk_id:
        return item  # idempotent

    before = holder_label(item)
    item.holder_type, item.holder_desk_id = HolderType.DESK, desk_id
    record_custody(session, item, CustodyEventType.TRANSFERRED_TO_DESK, p.user_id, note=note,
                   from_holder=before, to_holder=holder_label(item))
    await session.commit()
    return item


async def close_out(session: AsyncSession, p: Principal, item_id: uuid.UUID,
                    body: CloseOutIn) -> FoundItem:
    item = await get_item(session, p, item_id, for_update=True)
    if body.action == "extend":
        transition(item, "extend")
        item.expires_at = datetime.now(UTC) + timedelta(days=body.extend_days)
        event = CustodyEventType.RETENTION_EXTENDED
    else:
        transition(item, body.action)
        event = (CustodyEventType.DONATED if body.action == "donate"
                 else CustodyEventType.DISPOSED)
    record_custody(session, item, event, p.user_id, note=body.note,
                   from_holder=holder_label(item))
    await session.commit()
    return item


async def remove(session: AsyncSession, p: Principal, item_id: uuid.UUID, note: str | None
                 ) -> FoundItem:
    item = await get_item(session, p, item_id, for_update=True)
    transition(item, "remove")
    record_custody(session, item, CustodyEventType.REMOVED, p.user_id, note=note or "moderation")
    await session.commit()
    return item
