from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import PrincipalDep, SessionDep, SettingsDep, StaffDep, rate_limit
from app.core.pagination import Page
from app.integrations.storage import get_storage
from app.modules.campus.service import get_campus
from app.modules.items import presenter, service
from app.modules.items.schemas import (
    FoundItemCreate,
    FoundItemOut,
    FoundItemPrivateOut,
    UploadIntentIn,
    UploadIntentOut,
)

router = APIRouter(tags=["found items"])

_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/heic": "heic",
        "image/heif": "heif"}


@router.post("/uploads", response_model=UploadIntentOut,
             dependencies=[Depends(rate_limit("uploads", "rl_reports_per_hour", 600))])
async def create_upload(body: UploadIntentIn, principal: PrincipalDep,
                        settings: SettingsDep) -> UploadIntentOut:
    """Presigned direct-to-bucket upload. The API never streams image bytes."""
    key = f"{service.upload_prefix(principal)}{uuid.uuid4().hex}.{_EXT[body.content_type]}"
    signed = get_storage().presign_upload(key, body.content_type)
    return UploadIntentOut(key=key, url=signed["url"], fields=signed["fields"],
                           max_bytes=settings.upload_max_bytes)


@router.post("/items", response_model=FoundItemPrivateOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit("reports", "rl_reports_per_hour", 3600))])
async def report_found_item(body: FoundItemCreate, principal: PrincipalDep,
                            session: SessionDep, settings: SettingsDep) -> FoundItemPrivateOut:
    campus = await get_campus(session, principal.campus_id)
    item = await service.create_found_item(session, settings, principal, body, campus.timezone)
    out = await presenter.present_one(session, principal, item)
    assert isinstance(out, FoundItemPrivateOut)
    return out


@router.get("/items", response_model=Page[FoundItemOut])
async def browse_items(principal: StaffDep, session: SessionDep,
                       category: str | None = None, location_id: uuid.UUID | None = None,
                       cursor: str | None = None,
                       limit: int = Query(24, ge=1, le=60)) -> Page[FoundItemOut]:
    """Full list of items waiting for owners. Desk staff only.

    Members never browse the whole pile: that would let anyone fish for a wallet or phone
    and file a false claim. Owners find items by describing them (assistant / watches),
    which only surfaces items that actually match what they lost.
    """
    rows, nxt = await service.browse(session, principal, category=category,
                                     location_id=location_id, cursor=cursor, limit=limit)
    return Page(items=await presenter.present_many(session, principal, rows), next_cursor=nxt)


@router.get("/items/mine", response_model=Page[FoundItemOut])
async def my_found_items(principal: PrincipalDep, session: SessionDep, cursor: str | None = None,
                         limit: int = Query(24, ge=1, le=60)) -> Page[FoundItemOut]:
    rows, nxt = await service.mine(session, principal, cursor, limit)
    return Page(items=await presenter.present_many(session, principal, rows), next_cursor=nxt)


@router.get("/items/{item_id}", response_model=FoundItemPrivateOut | FoundItemOut)
async def get_item(item_id: uuid.UUID, principal: PrincipalDep,
                   session: SessionDep) -> FoundItemOut | FoundItemPrivateOut:
    item = await service.get_item(session, principal, item_id)
    return await presenter.present_one(session, principal, item)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def withdraw_item(item_id: uuid.UUID, principal: PrincipalDep, session: SessionDep) -> None:
    await service.withdraw(session, principal, item_id)
