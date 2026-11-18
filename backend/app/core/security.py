"""Passwordless auth: campus-email one-time code -> signed JWT in an httpOnly cookie.

* Codes are 6 digits, stored only as an HMAC in Redis with a TTL and an attempt counter,
  so a Redis dump does not reveal live codes and brute force is capped per email.
* The JWT carries user id, campus id and role. It is accepted from the cookie (browser)
  or an Authorization: Bearer header (API clients, tests).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.core.config import Settings
from app.domain.enums import Role
from app.domain.errors import Unauthenticated


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    campus_id: UUID
    role: Role

    @property
    def is_staff(self) -> bool:
        return self.role in (Role.DESK, Role.ADMIN)


def generate_login_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(settings: Settings, email: str, code: str) -> str:
    msg = f"{email.lower()}:{code}".encode()
    return hmac.new(settings.jwt_secret.encode(), msg, hashlib.sha256).hexdigest()


def codes_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


def issue_token(settings: Settings, principal: Principal) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=settings.access_token_ttl_minutes)
    payload = {
        "sub": str(principal.user_id),
        "cid": str(principal.campus_id),
        "role": principal.role.value,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), exp


def decode_token(settings: Settings, token: str) -> Principal:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "cid", "role", "exp"]},
        )
        return Principal(UUID(payload["sub"]), UUID(payload["cid"]), Role(payload["role"]))
    except (jwt.PyJWTError, ValueError, KeyError) as e:
        raise Unauthenticated("Invalid or expired session") from e
