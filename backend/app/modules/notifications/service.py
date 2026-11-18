from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.metrics import NOTIFICATIONS_SENT
from app.core.pagination import apply_cursor, next_cursor_for
from app.domain.enums import NotificationKind, Role
from app.events.outbox import EventType, emit
from app.modules.auth.models import User
from app.modules.notifications.models import Notification


async def notify(
    session: AsyncSession,
    *,
    campus_id: uuid.UUID,
    user_id: uuid.UUID,
    kind: NotificationKind,
    title: str,
    body: str,
    dedupe_key: str,
    link: str | None = None,
    payload: dict[str, Any] | None = None,
) -> bool:
    """Create an in-app notification at most once per dedupe_key, and stage the email.

    Runs inside the caller's transaction. Returns True if this call created it.
    """
    stmt = (
        pg_insert(Notification)
        .values(id=uuid.uuid4(), campus_id=campus_id, user_id=user_id, kind=kind, title=title,
                body=body, link=link, payload=payload or {}, dedupe_key=dedupe_key)
        .on_conflict_do_nothing(index_elements=[Notification.dedupe_key])
        .returning(Notification.id)
    )
    new_id = (await session.execute(stmt)).scalar_one_or_none()
    if new_id is None:
        return False
    emit(session, EventType.NOTIFICATION_CREATED, new_id)
    NOTIFICATIONS_SENT.labels(kind.value, "in_app").inc()
    return True


async def notify_desk(
    session: AsyncSession,
    *,
    campus_id: uuid.UUID,
    desk_id: uuid.UUID | None,
    kind: NotificationKind,
    title: str,
    body: str,
    dedupe_key: str,
    link: str | None = None,
    payload: dict[str, Any] | None = None,
) -> int:
    """Notify staff at a desk (or every desk/admin user on campus when desk_id is None)."""
    stmt = select(User.id).where(User.campus_id == campus_id,
                                 User.role.in_([Role.DESK, Role.ADMIN]))
    if desk_id is not None:
        stmt = stmt.where((User.desk_id == desk_id) | (User.role == Role.ADMIN))
    staff = (await session.execute(stmt)).scalars().all()
    n = 0
    for uid in staff:
        n += await notify(session, campus_id=campus_id, user_id=uid, kind=kind, title=title,
                          body=body, link=link, payload=payload,
                          dedupe_key=f"{dedupe_key}:{uid}")
    return n


async def list_for_user(session: AsyncSession, user_id: uuid.UUID, cursor: str | None,
                        limit: int) -> tuple[list[Notification], str | None]:
    stmt = apply_cursor(select(Notification).where(Notification.user_id == user_id),
                        Notification.created_at, Notification.id, cursor, limit)
    rows = list((await session.execute(stmt)).scalars().all())
    return next_cursor_for(rows, limit)


async def unread_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    return int((await session.execute(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == user_id, Notification.read_at.is_(None))
    )).scalar_one())


async def mark_read(session: AsyncSession, user_id: uuid.UUID, ids: list[uuid.UUID],
                    all_: bool) -> None:
    stmt = update(Notification).where(Notification.user_id == user_id,
                                      Notification.read_at.is_(None))
    if not all_:
        stmt = stmt.where(Notification.id.in_(ids))
    await session.execute(stmt.values(read_at=datetime.now(UTC)))
    await session.commit()
