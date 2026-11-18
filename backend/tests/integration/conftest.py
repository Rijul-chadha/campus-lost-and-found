"""Integration fixtures: real Postgres (pgvector) + Redis, app over ASGI, worker jobs inline.

Run with the stack up (`docker compose up -d postgres redis`) after `alembic upgrade head`.
Skipped automatically when the database is unreachable.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-123")
os.environ.setdefault("DATABASE_URL",
                      "postgresql+asyncpg://campus:campus@localhost:5432/campus_lost")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("RL_ASSISTANT_PER_MINUTE", "1000")
os.environ.setdefault("RL_REPORTS_PER_HOUR", "1000")
os.environ.setdefault("RL_CLAIMS_PER_HOUR", "1000")

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.redis import get_redis  # noqa: E402
from app.core.security import Principal, issue_token  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.domain.enums import Role  # noqa: E402
from app.modules.auth.models import User  # noqa: E402
from app.modules.campus.models import Campus, Desk, Location  # noqa: E402

pytestmark = pytest.mark.integration

TABLES = ("outbox_events, notifications, claims, matches, lost_reports, custody_events, "
          "found_items, users, desks, locations, campuses")


@pytest.fixture
async def db() -> AsyncIterator[None]:
    try:
        async with get_sessionmaker()() as s:
            await s.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
            await s.commit()
        await get_redis().flushdb()
    except Exception as e:  # pragma: no cover
        pytest.skip(f"integration stack unavailable: {e}")
    yield


@pytest.fixture
async def campus(db: None) -> dict[str, Any]:
    async with get_sessionmaker()() as s:
        c = Campus(id=uuid.uuid4(), slug="test", name="Test U", email_domains=["test.edu"],
                   timezone="America/Toronto")
        s.add(c)
        lib = Location(id=uuid.uuid4(), campus_id=c.id, name="Main Library",
                       aliases=["library"], lat=43.6644, lng=-79.3995)
        gym = Location(id=uuid.uuid4(), campus_id=c.id, name="Athletic Centre",
                       aliases=["gym"], lat=43.6626, lng=-79.4005)
        s.add_all([lib, gym])
        await s.flush()
        desk = Desk(id=uuid.uuid4(), campus_id=c.id, name="Security", location_id=lib.id)
        s.add(desk)
        await s.commit()
        return {"id": c.id, "lib": lib.id, "gym": gym.id, "desk": desk.id}


@pytest.fixture
async def app_client() -> AsyncIterator[httpx.AsyncClient]:
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def make_user(campus: dict[str, Any], email: str, role: Role = Role.MEMBER,
                    desk: bool = False) -> dict[str, str]:
    async with get_sessionmaker()() as s:
        u = User(id=uuid.uuid4(), campus_id=campus["id"], email=email, display_name=email,
                 role=role, desk_id=campus["desk"] if desk else None)
        s.add(u)
        await s.commit()
    token, _ = issue_token(get_settings(), Principal(u.id, campus["id"], role))
    # Bearer auth => CSRF header not required.
    return {"Authorization": f"Bearer {token}"}


async def run_outbox(kind: str | None = None) -> None:
    """Execute pending outbox events inline (what the relay + worker do in production)."""
    from app.events.models import OutboxEvent
    from app.workers import tasks
    from app.workers.relay import ROUTES

    while True:
        async with get_sessionmaker()() as s:
            from sqlalchemy import select

            ev = (await s.execute(select(OutboxEvent).where(OutboxEvent.published_at.is_(None))
                                  .order_by(OutboxEvent.id).limit(1))).scalar_one_or_none()
            if ev is None:
                return
            fn_name, agg = ROUTES.get(ev.event_type), ev.aggregate_id
            from datetime import UTC, datetime

            ev.published_at = datetime.now(UTC)
            await s.commit()
        if fn_name == "send_notification_email":
            continue  # no SMTP in tests
        if fn_name and (kind is None or kind == fn_name):
            await getattr(tasks, fn_name)({"job_try": 1}, agg)
