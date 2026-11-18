from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import PrincipalDep, SessionDep, SettingsDep, rate_limit
from app.core.pagination import Page
from app.modules.lost_reports import service
from app.modules.lost_reports.schemas import LostReportCreate, LostReportDetail, LostReportOut

router = APIRouter(prefix="/lost-reports", tags=["lost reports (watches)"])


@router.post("", response_model=LostReportDetail, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit("reports", "rl_reports_per_hour", 3600))])
async def create_watch(body: LostReportCreate, principal: PrincipalDep, session: SessionDep,
                       settings: SettingsDep) -> LostReportDetail:
    report = await service.create(session, settings, principal, body)
    return await service.detail(session, principal, report.id)


@router.get("", response_model=Page[LostReportOut])
async def my_watches(principal: PrincipalDep, session: SessionDep, cursor: str | None = None,
                     limit: int = Query(20, ge=1, le=50)) -> Page[LostReportOut]:
    items, nxt = await service.list_mine(session, principal, cursor, limit)
    return Page(items=items, next_cursor=nxt)


@router.get("/{report_id}", response_model=LostReportDetail)
async def get_watch(report_id: uuid.UUID, principal: PrincipalDep,
                    session: SessionDep) -> LostReportDetail:
    return await service.detail(session, principal, report_id)


@router.post("/{report_id}/{action}", response_model=LostReportDetail)
async def change_watch(report_id: uuid.UUID, action: Literal["cancel", "renew", "resolve"],
                       principal: PrincipalDep, session: SessionDep,
                       settings: SettingsDep) -> LostReportDetail:
    await service.act(session, settings, principal, report_id, action)
    return await service.detail(session, principal, report_id)


@router.post("/{report_id}/matches/{match_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss(report_id: uuid.UUID, match_id: uuid.UUID, principal: PrincipalDep,
                  session: SessionDep) -> None:
    await service.dismiss_match(session, principal, report_id, match_id)
