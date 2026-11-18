from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.core.security import Principal, codes_equal, generate_login_code, hash_code, issue_token
from app.domain.enums import Role
from app.domain.errors import NotFound, PermissionDenied, RateLimited, Unauthenticated
from app.integrations.email import send_email
from app.modules.auth.models import User
from app.modules.campus.service import campus_for_email

log = get_logger(__name__)


def _key(email: str) -> str:
    return f"login:{email.lower()}"


async def request_code(session: AsyncSession, settings: Settings, email: str) -> None:
    campus = await campus_for_email(session, email)
    if campus is None:
        raise PermissionDenied("Use your campus email address to sign in.")

    code = generate_login_code()
    redis = get_redis()
    key = _key(email)
    # Overwrite any previous code and reset attempts; TTL bounds the window.
    await redis.hset(key, mapping={"h": hash_code(settings, email, code), "tries": 0})
    await redis.expire(key, settings.login_code_ttl_seconds)

    if settings.dev_log_login_codes and not settings.is_production:
        log.info("dev_login_code", email=email, code=code)
    try:
        await send_email(
            settings, to=email, subject=f"Your Campus Lost & Found sign-in code: {code}",
            body=f"Your sign-in code is {code}. It expires in "
                 f"{settings.login_code_ttl_seconds // 60} minutes.\n\n"
                 "If you didn't request this, you can ignore this email.",
        )
    except Exception as e:  # email outage must not 500 the request in dev
        log.warning("login_email_failed", error=str(e))
        if settings.is_production:
            raise


async def verify_code(session: AsyncSession, settings: Settings, email: str,
                      code: str) -> tuple[User, str, datetime]:
    redis = get_redis()
    key = _key(email)
    data = await redis.hgetall(key)
    if not data:
        raise Unauthenticated("That code has expired. Request a new one.")
    tries = await redis.hincrby(key, "tries", 1)
    if tries > settings.login_code_max_attempts:
        await redis.delete(key)
        raise RateLimited("Too many attempts. Request a new code.")
    if not codes_equal(data["h"], hash_code(settings, email, code)):
        raise Unauthenticated("That code is not right.")
    await redis.delete(key)  # single use

    campus = await campus_for_email(session, email)
    if campus is None:
        raise PermissionDenied("Campus not found for this email")

    user = (await session.execute(
        select(User).where(User.campus_id == campus.id, func.lower(User.email) == email.lower())
    )).scalar_one_or_none()
    if user is None:
        user = User(id=uuid.uuid4(), campus_id=campus.id, email=email.lower(),
                    display_name=email.split("@")[0], role=Role.MEMBER)
        session.add(user)
    user.last_login_at = datetime.now(UTC)
    await session.commit()

    token, exp = issue_token(settings, Principal(user.id, user.campus_id, user.role))
    return user, token, exp


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFound("User not found")
    return user
