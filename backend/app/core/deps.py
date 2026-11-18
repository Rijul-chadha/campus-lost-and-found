from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.rate_limit import RateLimiter
from app.core.redis import get_redis
from app.core.security import Principal, decode_token
from app.db.session import session_dependency
from app.domain.errors import PermissionDenied, Unauthenticated

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(session_dependency)]


def _token_from(request: Request, settings: Settings) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(settings.cookie_name)


async def current_principal(request: Request, settings: SettingsDep) -> Principal:
    token = _token_from(request, settings)
    if not token:
        raise Unauthenticated("Please sign in")
    principal = decode_token(settings, token)
    request.state.principal = principal  # for access logs / rate-limit keys
    return principal


async def require_staff(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
    if not principal.is_staff:
        raise PermissionDenied("Lost-and-found staff only")
    return principal


PrincipalDep = Annotated[Principal, Depends(current_principal)]
StaffDep = Annotated[Principal, Depends(require_staff)]


def rate_limit(bucket: str, limit_attr: str, window_seconds: int) -> Callable[..., Awaitable[None]]:
    """Per-user limiter (falls back to client IP when anonymous). Limit comes from settings."""

    async def _dep(request: Request, settings: SettingsDep) -> None:
        # Route-level dependencies resolve before endpoint params, so decode the session here
        # rather than relying on current_principal having run.
        principal: Principal | None = getattr(request.state, "principal", None)
        if principal is None and (token := _token_from(request, settings)):
            try:
                principal = decode_token(settings, token)
            except Unauthenticated:
                principal = None
        subject = str(principal.user_id) if principal else (
            request.client.host if request.client else "unknown"
        )
        await RateLimiter(get_redis()).hit(
            bucket, subject, limit=getattr(settings, limit_attr), window_seconds=window_seconds
        )

    return _dep
