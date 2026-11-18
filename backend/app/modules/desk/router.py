from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.core.deps import SessionDep, StaffDep
from app.core.pagination import Page
from app.domain.enums import HolderType, ItemStatus
from app.modules.desk import service
from app.modules.desk.schemas import CloseOutIn, DeskOverview, ReceiveIn
from app.modules.items import presenter
from app.modules.items.schemas import FoundItemOut, FoundItemPrivateOut

router = APIRouter(prefix="/desk", tags=["desk (staff)"])


@router.get("/overview", response_model=DeskOverview)
async def overview(principal: StaffDep, session: SessionDep) -> DeskOverview:
    return await service.overview(session, principal)


@router.get("/items", response_model=Page[FoundItemOut])
async def items(principal: StaffDep, session: SessionDep, status: ItemStatus | None = None,
                holder_type: HolderType | None = None, q: str | None = None,
                cursor: str | None = None,
                limit: int = Query(30, ge=1, le=100)) -> Page[FoundItemOut]:
    rows, nxt = await service.list_items(session, principal, status=status,
                                         holder_type=holder_type, q=q, cursor=cursor,
                                         limit=limit)
    return Page(items=await presenter.present_many(session, principal, rows), next_cursor=nxt)


@router.post("/items/{item_id}/receive", response_model=FoundItemPrivateOut)
async def receive(item_id: uuid.UUID, body: ReceiveIn, principal: StaffDep,
                  session: SessionDep) -> FoundItemOut | FoundItemPrivateOut:
    item = await service.receive(session, principal, item_id, body.desk_id, body.note)
    return await presenter.present_one(session, principal, item)


@router.post("/items/{item_id}/close", response_model=FoundItemPrivateOut)
async def close_out(item_id: uuid.UUID, body: CloseOutIn, principal: StaffDep,
                    session: SessionDep) -> FoundItemOut | FoundItemPrivateOut:
    item = await service.close_out(session, principal, item_id, body)
    return await presenter.present_one(session, principal, item)


@router.post("/items/{item_id}/remove", response_model=FoundItemPrivateOut)
async def remove(item_id: uuid.UUID, principal: StaffDep, session: SessionDep,
                 note: str | None = None) -> FoundItemOut | FoundItemPrivateOut:
    item = await service.remove(session, principal, item_id, note)
    return await presenter.present_one(session, principal, item)
