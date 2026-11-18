"""Candidate generation (the only SQL in matching).

Hybrid retrieval: pgvector ANN top-K UNION exact item_type filter top-K.
ANN alone can miss a perfect attribute match whose free text embeds poorly ("TCard" vs
"student ID"); the attribute arm guarantees those reach the precise scorer.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ItemStatus, LostReportStatus
from app.domain.matching import GeoPoint, MatchSubject
from app.domain.vocabulary import COMPATIBLE_CATEGORIES
from app.modules.items.models import FoundItem
from app.modules.lost_reports.models import LostReport


async def _tune_ann(session: AsyncSession) -> None:
    # Higher ef_search => better recall; iterative scan (pgvector >= 0.8) keeps scanning
    # when WHERE filters discard ANN hits, so filtered queries still return K rows.
    await session.execute(text("SET LOCAL hnsw.ef_search = 100"))
    await session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))


def _category_filter(col: ColumnElement[str | None], category: str | None
                     ) -> ColumnElement[bool] | None:
    if category is None:
        return None
    allowed = {category, "other", *COMPATIBLE_CATEGORIES.get(category, ())}
    return or_(col.is_(None), col.in_(sorted(allowed)))


async def item_candidates(
    session: AsyncSession, *, campus_id: uuid.UUID, vector: Sequence[float],
    lost_from: datetime, category: str | None, item_type: str | None,
    slack: timedelta, k: int, exclude_reporter: uuid.UUID | None = None,
) -> list[FoundItem]:
    await _tune_ann(session)
    filters: list[ColumnElement[bool]] = [
        FoundItem.campus_id == campus_id,
        FoundItem.status == ItemStatus.AVAILABLE,
        FoundItem.found_at >= lost_from - slack,
        FoundItem.embedding.is_not(None),
    ]
    if (cf := _category_filter(FoundItem.category, category)) is not None:
        filters.append(cf)
    if exclude_reporter:
        filters.append(FoundItem.reporter_id != exclude_reporter)

    ann = (await session.execute(
        select(FoundItem).where(*filters)
        .order_by(FoundItem.embedding.cosine_distance(list(vector))).limit(k)
    )).scalars().all()
    by_id = {i.id: i for i in ann}
    if item_type:
        exact = (await session.execute(
            select(FoundItem).where(*filters, FoundItem.item_type == item_type)
            .order_by(FoundItem.found_at.desc()).limit(k // 2)
        )).scalars().all()
        for i in exact:
            by_id.setdefault(i.id, i)
    return list(by_id.values())


async def watch_candidates(
    session: AsyncSession, *, campus_id: uuid.UUID, vector: Sequence[float],
    found_at: datetime, category: str | None, item_type: str | None,
    slack: timedelta, k: int, exclude_owner: uuid.UUID,
) -> list[LostReport]:
    await _tune_ann(session)
    filters: list[ColumnElement[bool]] = [
        LostReport.campus_id == campus_id,
        LostReport.status == LostReportStatus.OPEN,
        LostReport.lost_from <= found_at + slack,
        LostReport.embedding.is_not(None),
        LostReport.owner_id != exclude_owner,  # don't match a finder to their own watch
    ]
    if (cf := _category_filter(LostReport.category, category)) is not None:
        filters.append(cf)

    ann = (await session.execute(
        select(LostReport).where(*filters)
        .order_by(LostReport.embedding.cosine_distance(list(vector))).limit(k)
    )).scalars().all()
    by_id = {r.id: r for r in ann}
    if item_type:
        exact = (await session.execute(
            select(LostReport).where(*filters, LostReport.item_type == item_type)
            .order_by(LostReport.created_at.desc()).limit(k // 2)
        )).scalars().all()
        for r in exact:
            by_id.setdefault(r.id, r)
    return list(by_id.values())


def _vec(v: object) -> list[float] | None:
    return None if v is None else [float(x) for x in v]  # type: ignore[attr-defined]


def item_subject(item: FoundItem, geo: dict[str, GeoPoint]) -> MatchSubject:
    loc = str(item.found_location_id) if item.found_location_id else None
    return MatchSubject(
        id=str(item.id), category=item.category, item_type=item.item_type,
        colors=tuple(item.colors or ()), brand=item.brand, embedding=_vec(item.embedding),
        location_id=loc, geo=geo.get(loc) if loc else None,
        occurred_from=item.found_at, occurred_to=item.found_at,
    )


def report_subject(r: LostReport, geo: dict[str, GeoPoint]) -> MatchSubject:
    loc = str(r.location_id) if r.location_id else None
    return MatchSubject(
        id=str(r.id), category=r.category, item_type=r.item_type, colors=tuple(r.colors or ()),
        brand=r.brand, embedding=_vec(r.embedding), location_id=loc,
        geo=geo.get(loc) if loc else None, occurred_from=r.lost_from, occurred_to=r.lost_to,
    )
