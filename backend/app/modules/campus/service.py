"""Campus reference data. Read-heavy and rarely changes, so it is cached in Redis."""

from __future__ import annotations

import json
import uuid
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.domain.errors import NotFound
from app.domain.extraction import LocationRef
from app.domain.matching import GeoPoint
from app.modules.campus.models import Campus, Desk, Location
from app.modules.campus.schemas import CampusOut, DeskOut, LocationOut

_TTL = 300


async def get_campus(session: AsyncSession, campus_id: uuid.UUID) -> Campus:
    campus = await session.get(Campus, campus_id)
    if campus is None:
        raise NotFound("Campus not found")
    return campus


async def campus_for_email(session: AsyncSession, email: str) -> Campus | None:
    domain = email.rsplit("@", 1)[-1].lower()
    return (await session.execute(
        select(Campus).where(Campus.email_domains.any(domain))  # type: ignore[arg-type]
    )).scalar_one_or_none()


async def campus_overview(session: AsyncSession, campus_id: uuid.UUID) -> CampusOut:
    redis = get_redis()
    key = f"campus:{campus_id}:overview"
    if cached := await redis.get(key):
        return CampusOut.model_validate_json(cached)
    campus = await get_campus(session, campus_id)
    locs = (await session.execute(
        select(Location).where(Location.campus_id == campus_id).order_by(Location.name)
    )).scalars().all()
    desks = (await session.execute(
        select(Desk).where(Desk.campus_id == campus_id).order_by(Desk.name)
    )).scalars().all()
    out = CampusOut(
        id=campus.id, slug=campus.slug, name=campus.name, timezone=campus.timezone,
        locations=[LocationOut.model_validate(x) for x in locs],
        desks=[DeskOut.model_validate(d) for d in desks],
    )
    await redis.set(key, out.model_dump_json(), ex=_TTL)
    return out


async def location_refs(session: AsyncSession, campus_id: uuid.UUID) -> list[LocationRef]:
    rows = (await session.execute(
        select(Location.id, Location.name, Location.aliases).where(Location.campus_id == campus_id)
    )).all()
    return [LocationRef(str(r.id), r.name, tuple(r.aliases or ())) for r in rows]


async def geo_index(session: AsyncSession, campus_id: uuid.UUID) -> dict[str, GeoPoint]:
    redis = get_redis()
    key = f"campus:{campus_id}:geo"
    if cached := await redis.get(key):
        return {k: GeoPoint(*v) for k, v in json.loads(cached).items()}
    rows = (await session.execute(
        select(Location.id, Location.lat, Location.lng).where(
            Location.campus_id == campus_id, Location.lat.is_not(None)
        )
    )).all()
    out = {str(r.id): GeoPoint(r.lat, r.lng) for r in rows}
    await redis.set(key, json.dumps({k: [v.lat, v.lng] for k, v in out.items()}), ex=_TTL)
    return out


def tz(campus: Campus) -> ZoneInfo:
    return ZoneInfo(campus.timezone)
