"""Turn FoundItem rows into API views, applying the privacy policy.

Centralising serialisation means there is exactly one code path that decides whether a
description, photo or secret leaves the server.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.domain.enums import ClaimStatus
from app.domain.state_machine import ACTIVE_CLAIM_STATUSES
from app.integrations.storage import get_storage
from app.modules.auth.models import User
from app.modules.campus.schemas import CampusOut
from app.modules.campus.service import campus_overview
from app.modules.claims.models import Claim
from app.modules.items import policy
from app.modules.items.models import CustodyEvent, FoundItem
from app.modules.items.schemas import (
    CustodyEventOut,
    FoundItemOut,
    FoundItemPrivateOut,
    PhotoOut,
    ReporterOut,
    ViewerFlags,
)


def _photos(item: FoundItem, visible: bool) -> list[PhotoOut]:
    if not visible or not item.photo_keys:
        return []
    st = get_storage()
    return [PhotoOut(url=st.presign_get(f"{k}.jpg"), thumb_url=st.presign_get(f"{k}_t.jpg"))
            for k in item.photo_keys]


async def _viewer_claims(session: AsyncSession, p: Principal,
                         item_ids: list[uuid.UUID]) -> dict[uuid.UUID, ClaimStatus]:
    if not item_ids:
        return {}
    rows = (await session.execute(
        select(Claim.found_item_id, Claim.status).where(
            Claim.claimant_id == p.user_id, Claim.found_item_id.in_(item_ids),
            Claim.status.in_(ACTIVE_CLAIM_STATUSES))
    )).all()
    return {r.found_item_id: r.status for r in rows}


def _base(item: FoundItem, p: Principal, campus: CampusOut, claim: ClaimStatus | None,
          private: bool) -> dict[str, object]:
    locs = {loc.id: loc for loc in campus.locations}
    desks = {d.id: d for d in campus.desks}
    hide = item.is_sensitive and not private
    return dict(
        id=item.id,
        title=item.title if private else item.public_title,
        description=(item.description if private else (None if hide
                                                         else item.public_description)),
        category=item.category, item_type=item.item_type, colors=item.colors or [],
        brand=None if hide else item.brand, is_sensitive=item.is_sensitive,
        location=locs.get(item.found_location_id) if item.found_location_id else None,
        location_detail=item.found_location_detail,
        found_at=item.found_at, status=item.status, holder_type=item.holder_type,
        holder_desk=desks.get(item.holder_desk_id) if item.holder_desk_id else None,
        photos=_photos(item, visible=not hide), photos_hidden=hide and bool(item.photo_keys),
        created_at=item.created_at, expires_at=item.expires_at,
        viewer=ViewerFlags(
            is_reporter=policy.is_reporter(p, item), can_view_private=private,
            can_claim=policy.can_claim(p, item) and claim is None,
            has_active_claim=claim is not None,
        ),
    )


async def present_many(session: AsyncSession, p: Principal,
                       items: list[FoundItem]) -> list[FoundItemOut]:
    campus = await campus_overview(session, p.campus_id)
    claims = await _viewer_claims(session, p, [i.id for i in items])
    out = []
    for it in items:
        claim = claims.get(it.id)
        private = policy.can_view_private(p, it,
                                          is_approved_claimant=claim is ClaimStatus.APPROVED)
        out.append(FoundItemOut(**_base(it, p, campus, claim, private)))  # type: ignore[arg-type]
    return out


async def present_one(session: AsyncSession, p: Principal,
                      item: FoundItem) -> FoundItemOut | FoundItemPrivateOut:
    campus = await campus_overview(session, p.campus_id)
    claim = (await _viewer_claims(session, p, [item.id])).get(item.id)
    private = policy.can_view_private(p, item, is_approved_claimant=claim is ClaimStatus.APPROVED)
    base = _base(item, p, campus, claim, private)
    if not private:
        return FoundItemOut(**base)  # type: ignore[arg-type]

    reporter = await session.get(User, item.reporter_id)
    custody = (await session.execute(
        select(CustodyEvent).where(CustodyEvent.found_item_id == item.id)
        .order_by(CustodyEvent.id)
    )).scalars().all()
    # Only the holder side sees the verification secret, not an approved claimant.
    show_secret = policy.is_reporter(p, item) or p.is_staff
    return FoundItemPrivateOut(
        **base,  # type: ignore[arg-type]
        private_detail=item.private_detail if show_secret else None,
        reporter=ReporterOut(id=item.reporter_id,
                             display_name=reporter.display_name if reporter else None),
        custody=[CustodyEventOut.model_validate(c) for c in custody],
    )
