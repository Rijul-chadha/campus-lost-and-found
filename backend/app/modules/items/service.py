from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.pagination import apply_cursor, next_cursor_for
from app.core.security import Principal
from app.domain import privacy
from app.domain.enums import CustodyEventType, HolderType, ItemStatus
from app.domain.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from app.domain.extraction import canonical_brand, canonical_color, extract_all
from app.domain.state_machine import ACTIVE_CLAIM_STATUSES, ITEM
from app.domain.vocabulary import ITEM_TYPE_TO_CATEGORY
from app.events.outbox import EventType, emit
from app.modules.campus.models import Desk, Location
from app.modules.claims.models import Claim
from app.modules.items import policy
from app.modules.items.models import CustodyEvent, FoundItem
from app.modules.items.schemas import FoundItemCreate


def upload_prefix(p: Principal) -> str:
    return f"uploads/{p.campus_id}/{p.user_id}/"


def holder_label(item: FoundItem) -> str:
    return f"desk:{item.holder_desk_id}" if item.holder_type is HolderType.DESK else "finder"


def record_custody(session: AsyncSession, item: FoundItem, event: CustodyEventType,
                   actor_id: uuid.UUID | None, *, note: str | None = None,
                   from_holder: str | None = None, to_holder: str | None = None) -> None:
    session.add(CustodyEvent(campus_id=item.campus_id, found_item_id=item.id, event_type=event,
                             actor_id=actor_id, note=note, from_holder=from_holder,
                             to_holder=to_holder))


def transition(item: FoundItem, action: str) -> None:
    item.status = ITEM.next(action, item.status)


async def get_item(session: AsyncSession, p: Principal, item_id: uuid.UUID, *,
                   for_update: bool = False) -> FoundItem:
    stmt = select(FoundItem).where(FoundItem.id == item_id, FoundItem.campus_id == p.campus_id)
    if for_update:
        stmt = stmt.with_for_update()
    item = (await session.execute(stmt)).scalar_one_or_none()
    if item is None or not policy.can_view(p, item):
        raise NotFound("Item not found")
    return item


async def _validate_refs(session: AsyncSession, p: Principal, body: FoundItemCreate) -> None:
    if body.found_location_id:
        loc = await session.get(Location, body.found_location_id)
        if loc is None or loc.campus_id != p.campus_id:
            raise ValidationFailed("Unknown location")
    if body.holder_type is HolderType.DESK:
        if body.holder_desk_id is None:
            raise ValidationFailed("Choose which desk has the item")
        desk = await session.get(Desk, body.holder_desk_id)
        if desk is None or desk.campus_id != p.campus_id:
            raise ValidationFailed("Unknown desk")
        # Only desk staff can record an item as already at a desk; a finder who plans to drop
        # it off reports it as held by them and the desk "receives" it (custody handover).
        if not p.is_staff:
            raise PermissionDenied("Only desk staff can log an item as held at a desk")
    prefix = upload_prefix(p)
    if any(not k.startswith(prefix) for k in body.upload_keys):
        raise ValidationFailed("Invalid upload key")


async def create_found_item(session: AsyncSession, settings: Settings, p: Principal,
                            body: FoundItemCreate, campus_tz: str) -> FoundItem:
    now = datetime.now(UTC)
    if body.found_at > now + timedelta(minutes=10):
        raise ValidationFailed("found_at is in the future")
    if body.found_at < now - timedelta(days=30):
        raise ValidationFailed("Items found more than 30 days ago should go to a desk directly")
    await _validate_refs(session, p, body)

    # Fill missing attributes from free text; canonicalise anything the user selected.
    text = f"{body.title}. {body.description or ''}"
    ex = extract_all(text, now=now, tz=ZoneInfo(campus_tz))
    item_type = body.item_type or ex.item_type
    category = body.category or (ITEM_TYPE_TO_CATEGORY.get(item_type) if item_type else None) \
        or ex.category
    colors = [c for c in (canonical_color(c) for c in body.colors) if c] or ex.colors
    brand = canonical_brand(body.brand) or ex.brand

    item = FoundItem(
        id=uuid.uuid4(), campus_id=p.campus_id, reporter_id=p.user_id,
        title=body.title.strip(), description=(body.description or "").strip() or None,
        public_title=privacy.public_title(body.title.strip(), item_type),
        public_description=privacy.redact(body.description),
        category=category, item_type=item_type, colors=colors, brand=brand,
        is_sensitive=privacy.is_sensitive(item_type),
        found_location_id=body.found_location_id,
        found_location_detail=privacy.redact(body.found_location_detail),
        found_at=body.found_at, holder_type=body.holder_type,
        holder_desk_id=body.holder_desk_id if body.holder_type is HolderType.DESK else None,
        status=ItemStatus.REPORTED, upload_keys=body.upload_keys, photo_keys=[],
        private_detail=body.private_detail,
        expires_at=now + timedelta(days=settings.item_retention_days),
    )
    session.add(item)
    await session.flush()  # no ORM relationships, so persist the parent before its log row
    record_custody(session, item, CustodyEventType.REPORTED, p.user_id,
                   to_holder=holder_label(item))
    # Embedding, photo scrubbing and reverse matching happen asynchronously in the worker.
    emit(session, EventType.FOUND_ITEM_CREATED, item.id, {"campus_id": str(p.campus_id)})
    await session.commit()
    return item


async def browse(session: AsyncSession, p: Principal, *, category: str | None,
                 location_id: uuid.UUID | None, cursor: str | None,
                 limit: int) -> tuple[list[FoundItem], str | None]:
    stmt = select(FoundItem).where(FoundItem.campus_id == p.campus_id,
                                   FoundItem.status == ItemStatus.AVAILABLE)
    if category:
        stmt = stmt.where(FoundItem.category == category)
    if location_id:
        stmt = stmt.where(FoundItem.found_location_id == location_id)
    rows = list((await session.execute(
        apply_cursor(stmt, FoundItem.created_at, FoundItem.id, cursor, limit))).scalars().all())
    return next_cursor_for(rows, limit)


async def mine(session: AsyncSession, p: Principal, cursor: str | None,
               limit: int) -> tuple[list[FoundItem], str | None]:
    stmt = select(FoundItem).where(FoundItem.campus_id == p.campus_id,
                                   FoundItem.reporter_id == p.user_id)
    rows = list((await session.execute(
        apply_cursor(stmt, FoundItem.created_at, FoundItem.id, cursor, limit))).scalars().all())
    return next_cursor_for(rows, limit)


async def withdraw(session: AsyncSession, p: Principal, item_id: uuid.UUID) -> None:
    """Finder retracts a report (posted by mistake / owner found them directly)."""
    item = await get_item(session, p, item_id, for_update=True)
    if not (policy.is_reporter(p, item) or p.is_staff):
        raise PermissionDenied("Only the finder or desk staff can withdraw this report")
    active = (await session.execute(
        select(func.count()).select_from(Claim).where(
            Claim.found_item_id == item.id, Claim.status.in_(ACTIVE_CLAIM_STATUSES))
    )).scalar_one()
    if active:
        raise Conflict("Someone has an active claim on this item; resolve it first")
    transition(item, "remove")
    record_custody(session, item, CustodyEventType.REMOVED, p.user_id, note="withdrawn")
    await session.commit()
