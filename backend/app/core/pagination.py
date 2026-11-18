"""Keyset (cursor) pagination on (created_at, id).

OFFSET pagination re-scans skipped rows and shows duplicates when new rows arrive; keyset
pagination is O(page size) at any depth and stable under concurrent inserts.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import Select, and_, or_
from sqlalchemy.orm import InstrumentedAttribute

from app.domain.errors import ValidationFailed

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None


def encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    raw = json.dumps([created_at.isoformat(), str(row_id)]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        ts, rid = json.loads(base64.urlsafe_b64decode(padded))
        return datetime.fromisoformat(ts), uuid.UUID(rid)
    except Exception as e:
        raise ValidationFailed("Invalid cursor") from e


def apply_cursor(
    stmt: Select[Any],
    created_col: InstrumentedAttribute[datetime],
    id_col: InstrumentedAttribute[uuid.UUID],
    cursor: str | None,
    limit: int,
) -> Select[Any]:
    if cursor:
        ts, rid = decode_cursor(cursor)
        stmt = stmt.where(or_(created_col < ts, and_(created_col == ts, id_col < rid)))
    return stmt.order_by(created_col.desc(), id_col.desc()).limit(limit + 1)


def next_cursor_for(rows: list[Any], limit: int) -> tuple[list[Any], str | None]:
    if len(rows) <= limit:
        return rows, None
    rows = rows[:limit]
    last = rows[-1]
    return rows, encode_cursor(last.created_at, last.id)
