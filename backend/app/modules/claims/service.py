"""Claim workflow: open -> holder reviews -> approve (pickup) -> complete (handover).

Concurrency: every state change locks the item row (SELECT ... FOR UPDATE) and the claim
row, the item has an optimistic version column, and partial unique indexes make
"two approved claims for one item" impossible even if application code had a bug.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import Principal
from app.domain.enums import (
    ClaimStatus,
    CustodyEventType,
    HolderType,
    LostReportStatus,
    MatchStatus,
    NotificationKind,
)
from app.domain.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from app.domain.state_machine import ACTIVE_CLAIM_STATUSES, CLAIM
from app.domain.verification import proof_hint
from app.modules.auth.models import User
from app.modules.campus.models import Desk
from app.modules.claims.models import Claim
from app.modules.claims.schemas import ClaimantOut, ClaimOut, ClaimReviewOut
from app.modules.items import policy
from app.modules.items.models import FoundItem
from app.modules.items.service import get_item, holder_label, record_custody, transition
from app.modules.lost_reports.models import LostReport
from app.modules.matching.models import Match
from app.modules.notifications.service import notify, notify_desk


def to_claimant_view(c: Claim, item: FoundItem) -> ClaimOut:
    return ClaimOut(
        id=c.id, found_item_id=c.found_item_id, item_title=item.public_title, status=c.status,
        created_at=c.created_at, decided_at=c.decided_at, decision_note=c.decision_note,
        pickup_instructions=c.pickup_instructions if c.status in (
            ClaimStatus.APPROVED, ClaimStatus.COMPLETED) else None,
    )


async def to_review_view(session: AsyncSession, c: Claim, item: FoundItem) -> ClaimReviewOut:
    claimant = await session.get(User, c.claimant_id)
    base = to_claimant_view(c, item).model_dump()
    base["pickup_instructions"] = c.pickup_instructions
    return ClaimReviewOut(
        **base, proof_text=c.proof_text, proof_strength=c.proof_strength,
        proof_score=c.proof_score, private_detail=item.private_detail,
        claimant=ClaimantOut(id=c.claimant_id,
                             display_name=claimant.display_name if claimant else None),
    )


async def _notify_holder(session: AsyncSession, item: FoundItem, claim: Claim) -> None:
    title = f"Someone claimed “{item.public_title}”"
    body = "Review their description and approve or reject the claim."
    link = f"/claims/review?item={item.id}"
    if item.holder_type is HolderType.FINDER:
        await notify(session, campus_id=item.campus_id, user_id=item.reporter_id,
                     kind=NotificationKind.CLAIM_RECEIVED, title=title, body=body, link=link,
                     dedupe_key=f"claim-received:{claim.id}")
    else:
        await notify_desk(session, campus_id=item.campus_id, desk_id=item.holder_desk_id,
                          kind=NotificationKind.CLAIM_RECEIVED, title=title, body=body,
                          link=f"/desk?claim={claim.id}", dedupe_key=f"claim-received:{claim.id}")


async def open_claim(session: AsyncSession, settings: Settings, p: Principal,
                     item_id: uuid.UUID, proof_text: str,
                     lost_report_id: uuid.UUID | None) -> tuple[Claim, FoundItem]:
    item = await get_item(session, p, item_id, for_update=True)
    if not policy.can_claim(p, item):
        raise Conflict("This item can't be claimed right now")

    attempts = (await session.execute(
        select(func.count()).select_from(Claim).where(
            Claim.found_item_id == item.id, Claim.claimant_id == p.user_id))).scalar_one()
    if attempts >= settings.max_claim_attempts_per_item:
        raise PermissionDenied("You've reached the claim limit for this item. "
                               "Visit the lost-and-found desk in person.")
    if lost_report_id:
        lr = await session.get(LostReport, lost_report_id)
        if lr is None or lr.owner_id != p.user_id:
            raise ValidationFailed("Unknown lost report")

    hint = proof_hint(item.private_detail, proof_text) if item.private_detail else None
    claim = Claim(
        id=uuid.uuid4(), campus_id=item.campus_id, found_item_id=item.id,
        claimant_id=p.user_id, lost_report_id=lost_report_id, proof_text=proof_text.strip(),
        proof_score=hint.score if hint else None,
        proof_strength=hint.strength.value if hint else None,
    )
    session.add(claim)
    try:
        await session.flush()
    except IntegrityError as e:
        raise Conflict("You already have an open claim on this item") from e
    record_custody(session, item, CustodyEventType.CLAIM_OPENED, p.user_id)
    await _notify_holder(session, item, claim)
    await session.commit()
    return claim, item


async def _load_for_decision(session: AsyncSession, p: Principal,
                             claim_id: uuid.UUID) -> tuple[Claim, FoundItem]:
    claim = (await session.execute(
        select(Claim).where(Claim.id == claim_id, Claim.campus_id == p.campus_id)
        .with_for_update())).scalar_one_or_none()
    if claim is None:
        raise NotFound("Claim not found")
    item = await get_item(session, p, claim.found_item_id, for_update=True)
    if not policy.can_review_claims(p, item):
        raise PermissionDenied("Only the current holder of the item can decide claims")
    return claim, item


async def _default_pickup(session: AsyncSession, item: FoundItem) -> str:
    if item.holder_type is HolderType.DESK and item.holder_desk_id:
        desk = await session.get(Desk, item.holder_desk_id)
        if desk:
            return f"Pick it up at {desk.name}" + (f" ({desk.hours})" if desk.hours else "") + \
                ". Bring your student card."
    return "The finder will contact you through Campus Lost & Found to arrange a handover."


async def approve(session: AsyncSession, p: Principal, claim_id: uuid.UUID,
                  pickup: str | None) -> tuple[Claim, FoundItem]:
    claim, item = await _load_for_decision(session, p, claim_id)
    claim.status = CLAIM.next("approve", claim.status)
    transition(item, "approve_claim")
    claim.decided_by_id, claim.decided_at = p.user_id, datetime.now(UTC)
    claim.pickup_instructions = pickup or await _default_pickup(session, item)
    record_custody(session, item, CustodyEventType.CLAIM_APPROVED, p.user_id)
    await notify(session, campus_id=item.campus_id, user_id=claim.claimant_id,
                 kind=NotificationKind.CLAIM_APPROVED,
                 title=f"Your claim for “{item.public_title}” was approved",
                 body=claim.pickup_instructions, link=f"/items/{item.id}",
                 dedupe_key=f"claim-approved:{claim.id}")
    try:
        await session.commit()
    except IntegrityError as e:  # uq_claims_one_approved_per_item
        await session.rollback()
        raise Conflict("Another claim for this item was approved first") from e
    return claim, item


async def reject(session: AsyncSession, p: Principal, claim_id: uuid.UUID,
                 note: str | None) -> tuple[Claim, FoundItem]:
    claim, item = await _load_for_decision(session, p, claim_id)
    claim.status = CLAIM.next("reject", claim.status)
    claim.decided_by_id, claim.decided_at, claim.decision_note = p.user_id, datetime.now(UTC), note
    record_custody(session, item, CustodyEventType.CLAIM_REJECTED, p.user_id)
    await notify(session, campus_id=item.campus_id, user_id=claim.claimant_id,
                 kind=NotificationKind.CLAIM_REJECTED,
                 title=f"Your claim for “{item.public_title}” wasn't approved",
                 body=note or "The description didn't match. You can visit the desk in person.",
                 link=f"/items/{item.id}", dedupe_key=f"claim-rejected:{claim.id}")
    await session.commit()
    return claim, item


async def complete(session: AsyncSession, p: Principal,
                   claim_id: uuid.UUID) -> tuple[Claim, FoundItem]:
    """Holder confirms the physical handover. Closes the loop everywhere."""
    claim, item = await _load_for_decision(session, p, claim_id)
    claim.status = CLAIM.next("complete", claim.status)
    from_holder = holder_label(item)
    transition(item, "return")
    record_custody(session, item, CustodyEventType.RETURNED, p.user_id,
                   from_holder=from_holder, to_holder=f"owner:{claim.claimant_id}")

    # Everyone else waiting on this item gets a clear answer.
    others = (await session.execute(
        select(Claim).where(Claim.found_item_id == item.id, Claim.id != claim.id,
                            Claim.status.in_(ACTIVE_CLAIM_STATUSES)).with_for_update()
    )).scalars().all()
    for o in others:
        o.status = ClaimStatus.REJECTED
        o.decision_note = "This item was returned to its owner."
        await notify(session, campus_id=item.campus_id, user_id=o.claimant_id,
                     kind=NotificationKind.CLAIM_REJECTED,
                     title=f"“{item.public_title}” was returned to its owner",
                     body=o.decision_note, link=f"/items/{item.id}",
                     dedupe_key=f"claim-closed:{o.id}")

    # Resolve the owner's watch(es) that matched this item.
    watch_ids = {claim.lost_report_id} if claim.lost_report_id else set()
    watch_ids |= set((await session.execute(
        select(Match.lost_report_id).join(LostReport, LostReport.id == Match.lost_report_id)
        .where(Match.found_item_id == item.id, LostReport.owner_id == claim.claimant_id)
    )).scalars().all())
    if watch_ids:
        await session.execute(update(LostReport).where(
            LostReport.id.in_(watch_ids), LostReport.status == LostReportStatus.OPEN
        ).values(status=LostReportStatus.RESOLVED))
        await session.execute(update(Match).where(
            Match.found_item_id == item.id, Match.lost_report_id.in_(watch_ids)
        ).values(status=MatchStatus.CLAIMED))

    if item.reporter_id != p.user_id:
        await notify(session, campus_id=item.campus_id, user_id=item.reporter_id,
                     kind=NotificationKind.ITEM_RETURNED,
                     title="The item you found is back with its owner",
                     body=f"“{item.public_title}” was returned. Thanks for reporting it!",
                     link=f"/items/{item.id}", dedupe_key=f"returned:{item.id}")
    await session.commit()
    return claim, item


async def cancel(session: AsyncSession, p: Principal, claim_id: uuid.UUID
                 ) -> tuple[Claim, FoundItem]:
    claim = (await session.execute(
        select(Claim).where(Claim.id == claim_id, Claim.claimant_id == p.user_id)
        .with_for_update())).scalar_one_or_none()
    if claim is None:
        raise NotFound("Claim not found")
    item = await get_item(session, p, claim.found_item_id, for_update=True)
    was_approved = claim.status is ClaimStatus.APPROVED
    claim.status = CLAIM.next("cancel", claim.status)
    if was_approved:
        transition(item, "revert_claim")
    record_custody(session, item, CustodyEventType.CLAIM_CANCELLED, p.user_id)
    await session.commit()
    return claim, item


async def my_claims(session: AsyncSession, p: Principal) -> list[ClaimOut]:
    rows = (await session.execute(
        select(Claim, FoundItem).join(FoundItem, FoundItem.id == Claim.found_item_id)
        .where(Claim.claimant_id == p.user_id).order_by(Claim.created_at.desc()).limit(50)
    )).all()
    return [to_claimant_view(c, i) for c, i in rows]


async def review_queue(session: AsyncSession, p: Principal,
                       item_id: uuid.UUID | None) -> list[ClaimReviewOut]:
    """Pending/approved claims the caller is allowed to decide."""
    stmt = (select(Claim, FoundItem).join(FoundItem, FoundItem.id == Claim.found_item_id)
            .where(Claim.campus_id == p.campus_id, Claim.status.in_(ACTIVE_CLAIM_STATUSES)))
    if item_id:
        stmt = stmt.where(Claim.found_item_id == item_id)
    if not p.is_staff:
        stmt = stmt.where(FoundItem.reporter_id == p.user_id,
                          FoundItem.holder_type == HolderType.FINDER)
    rows = (await session.execute(stmt.order_by(Claim.created_at).limit(100))).all()
    return [await to_review_view(session, c, i) for c, i in rows
            if policy.can_review_claims(p, i)]
