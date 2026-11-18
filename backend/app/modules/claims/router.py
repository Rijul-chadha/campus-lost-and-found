from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from app.core.deps import PrincipalDep, SessionDep, SettingsDep, rate_limit
from app.modules.claims import service
from app.modules.claims.schemas import ApproveIn, ClaimCreate, ClaimOut, ClaimReviewOut, RejectIn

router = APIRouter(prefix="/claims", tags=["claims"])


@router.post("", response_model=ClaimOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit("claims", "rl_claims_per_hour", 3600))])
async def open_claim(body: ClaimCreate, principal: PrincipalDep, session: SessionDep,
                     settings: SettingsDep) -> ClaimOut:
    claim, item = await service.open_claim(session, settings, principal, body.found_item_id,
                                           body.proof_text, body.lost_report_id)
    return service.to_claimant_view(claim, item)


@router.get("/mine", response_model=list[ClaimOut])
async def my_claims(principal: PrincipalDep, session: SessionDep) -> list[ClaimOut]:
    return await service.my_claims(session, principal)


@router.get("/review", response_model=list[ClaimReviewOut])
async def review_queue(principal: PrincipalDep, session: SessionDep,
                       item: uuid.UUID | None = None) -> list[ClaimReviewOut]:
    return await service.review_queue(session, principal, item)


@router.post("/{claim_id}/approve", response_model=ClaimReviewOut)
async def approve(claim_id: uuid.UUID, body: ApproveIn, principal: PrincipalDep,
                  session: SessionDep) -> ClaimReviewOut:
    c, i = await service.approve(session, principal, claim_id, body.pickup_instructions)
    return await service.to_review_view(session, c, i)


@router.post("/{claim_id}/reject", response_model=ClaimReviewOut)
async def reject(claim_id: uuid.UUID, body: RejectIn, principal: PrincipalDep,
                 session: SessionDep) -> ClaimReviewOut:
    c, i = await service.reject(session, principal, claim_id, body.note)
    return await service.to_review_view(session, c, i)


@router.post("/{claim_id}/complete", response_model=ClaimReviewOut)
async def complete(claim_id: uuid.UUID, principal: PrincipalDep,
                   session: SessionDep) -> ClaimReviewOut:
    c, i = await service.complete(session, principal, claim_id)
    return await service.to_review_view(session, c, i)


@router.post("/{claim_id}/cancel", response_model=ClaimOut)
async def cancel(claim_id: uuid.UUID, principal: PrincipalDep, session: SessionDep) -> ClaimOut:
    c, i = await service.cancel(session, principal, claim_id)
    return service.to_claimant_view(c, i)
