from fastapi import APIRouter, Query, status

from app.core.deps import PrincipalDep, SessionDep
from app.core.pagination import Page
from app.modules.notifications import service
from app.modules.notifications.schemas import MarkReadIn, NotificationOut, UnreadCount

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=Page[NotificationOut])
async def list_notifications(principal: PrincipalDep, session: SessionDep,
                             cursor: str | None = None,
                             limit: int = Query(20, ge=1, le=50)) -> Page[NotificationOut]:
    rows, nxt = await service.list_for_user(session, principal.user_id, cursor, limit)
    return Page(items=[NotificationOut.model_validate(r) for r in rows], next_cursor=nxt)


@router.get("/unread-count", response_model=UnreadCount)
async def unread(principal: PrincipalDep, session: SessionDep) -> UnreadCount:
    return UnreadCount(unread=await service.unread_count(session, principal.user_id))


@router.post("/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(body: MarkReadIn, principal: PrincipalDep, session: SessionDep) -> None:
    await service.mark_read(session, principal.user_id, body.ids, body.all)
