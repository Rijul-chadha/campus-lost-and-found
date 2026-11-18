from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.pagination import apply_cursor, next_cursor_for
from app.core.security import Principal
from app.domain.enums import ItemStatus, MatchStatus
from app.domain.errors import NotFound, ValidationFailed
from app.domain.extraction import canonical_brand, canonical_color, embedding_text, extract_all
from app.domain.state_machine import LOST_REPORT
from app.domain.vocabulary import ITEM_TYPE_TO_CATEGORY
from app.events.outbox import EventType, emit
from app.integrations.embeddings import embed_texts
from app.modules.campus.models import Location
from app.modules.campus.service import campus_overview, get_campus, tz
from app.modules.items import presenter
from app.modules.items.models import FoundItem
from app.modules.lost_reports.models import LostReport
from app.modules.lost_reports.schemas import (
    LostReportCreate,
    LostReportDetail,
    LostReportOut,
    MatchOut,
)
from app.modules.matching.models import Match


async def create(session: AsyncSession, settings: Settings, p: Principal,
                 body: LostReportCreate) -> LostReport:
    now = datetime.now(UTC)
    if body.lost_to > now + timedelta(minutes=10):
        raise ValidationFailed("lost_to is in the future")
    if body.lost_from < now - timedelta(days=settings.lost_report_ttl_days):
        raise ValidationFailed("That is too long ago; check with the desk directly")
    if body.location_id:
        loc = await session.get(Location, body.location_id)
        if loc is None or loc.campus_id != p.campus_id:
            raise ValidationFailed("Unknown location")

    campus = await get_campus(session, p.campus_id)
    ex = extract_all(f"{body.title}. {body.description}", now=now, tz=tz(campus))
    item_type = body.item_type or ex.item_type
    category = body.category or (ITEM_TYPE_TO_CATEGORY.get(item_type) if item_type else None) \
        or ex.category
    colors = [c for c in (canonical_color(c) for c in body.colors) if c] or ex.colors
    brand = canonical_brand(body.brand) or ex.brand

    vectors, model = await embed_texts(settings, [embedding_text(
        title=body.title, description=body.description, item_type=item_type,
        category=category, colors=colors, brand=brand)])

    report = LostReport(
        id=uuid.uuid4(), campus_id=p.campus_id, owner_id=p.user_id, title=body.title.strip(),
        description=body.description.strip(), category=category, item_type=item_type,
        colors=colors, brand=brand, location_id=body.location_id,
        location_detail=body.location_detail, lost_from=body.lost_from, lost_to=body.lost_to,
        embedding=vectors[0], embedding_model=model,
        expires_at=now + timedelta(days=settings.lost_report_ttl_days),
    )
    session.add(report)
    emit(session, EventType.LOST_REPORT_CREATED, report.id)
    await session.commit()
    return report


async def _own(session: AsyncSession, p: Principal, report_id: uuid.UUID) -> LostReport:
    r = await session.get(LostReport, report_id, with_for_update=True)
    if r is None or r.owner_id != p.user_id:
        raise NotFound("Lost report not found")
    return r


async def _to_out(session: AsyncSession, p: Principal, reports: list[LostReport]
                  ) -> list[LostReportOut]:
    campus = await campus_overview(session, p.campus_id)
    locs = {loc.id: loc for loc in campus.locations}
    counts: dict[uuid.UUID, int] = {}
    if reports:
        rows = (await session.execute(
            select(Match.lost_report_id, func.count()).where(
                Match.lost_report_id.in_([r.id for r in reports]),
                Match.status != MatchStatus.DISMISSED)
            .group_by(Match.lost_report_id))).all()
        counts = {rid: n for rid, n in rows}
    return [LostReportOut(
        id=r.id, title=r.title, description=r.description, category=r.category,
        item_type=r.item_type, colors=r.colors or [], brand=r.brand,
        location=locs.get(r.location_id) if r.location_id else None,
        location_detail=r.location_detail, lost_from=r.lost_from, lost_to=r.lost_to,
        status=r.status, expires_at=r.expires_at, created_at=r.created_at,
        match_count=counts.get(r.id, 0),
    ) for r in reports]


async def list_mine(session: AsyncSession, p: Principal, cursor: str | None,
                    limit: int) -> tuple[list[LostReportOut], str | None]:
    stmt = select(LostReport).where(LostReport.owner_id == p.user_id)
    rows = list((await session.execute(
        apply_cursor(stmt, LostReport.created_at, LostReport.id, cursor, limit))).scalars().all())
    rows, nxt = next_cursor_for(rows, limit)
    return await _to_out(session, p, rows), nxt


async def detail(session: AsyncSession, p: Principal, report_id: uuid.UUID) -> LostReportDetail:
    r = await session.get(LostReport, report_id)
    if r is None or r.owner_id != p.user_id:
        raise NotFound("Lost report not found")
    rows = (await session.execute(
        select(Match, FoundItem).join(FoundItem, FoundItem.id == Match.found_item_id)
        .where(Match.lost_report_id == r.id, Match.status != MatchStatus.DISMISSED,
               FoundItem.status.in_([ItemStatus.AVAILABLE, ItemStatus.CLAIMED,
                                     ItemStatus.RETURNED]))
        .order_by(Match.score.desc()).limit(20)
    )).all()
    items = await presenter.present_many(session, p, [it for _, it in rows])
    [base] = await _to_out(session, p, [r])
    return LostReportDetail(
        **base.model_dump(),
        matches=[MatchOut(id=m.id, score=m.score, reasons=m.reasons or [], status=m.status,
                          item=io) for (m, _), io in zip(rows, items, strict=True)],
    )


async def act(session: AsyncSession, settings: Settings, p: Principal, report_id: uuid.UUID,
              action: str) -> LostReport:
    r = await _own(session, p, report_id)
    r.status = LOST_REPORT.next(action, r.status)
    if action == "renew":
        r.expires_at = datetime.now(UTC) + timedelta(days=settings.lost_report_ttl_days)
        emit(session, EventType.LOST_REPORT_RENEWED, r.id)
    await session.commit()
    return r


async def dismiss_match(session: AsyncSession, p: Principal, report_id: uuid.UUID,
                        match_id: uuid.UUID) -> None:
    """Owner says "not mine". Kept as a labelled negative for tuning the matcher."""
    r = await _own(session, p, report_id)
    m = await session.get(Match, match_id)
    if m is None or m.lost_report_id != r.id:
        raise NotFound("Match not found")
    m.status = MatchStatus.DISMISSED
    await session.commit()
