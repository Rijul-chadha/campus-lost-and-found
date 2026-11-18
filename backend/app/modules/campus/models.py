from __future__ import annotations

import uuid

from sqlalchemy import ARRAY, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CampusScoped, Timestamps, UUIDPk


class Campus(UUIDPk, Timestamps, Base):
    __tablename__ = "campuses"

    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    # Sign-in is restricted to these email domains (e.g. ["mail.utoronto.ca", "utoronto.ca"]).
    email_domains: Mapped[list[str]] = mapped_column(ARRAY(String(253)))
    timezone: Mapped[str] = mapped_column(String(64), default="America/Toronto")


class Location(UUIDPk, CampusScoped, Base):
    """Buildings / areas. Finders pick one; owners can mention one in free text."""

    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("campus_id", "name"),)

    name: Mapped[str] = mapped_column(String(200))
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String(100)), default=list)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)


class Desk(UUIDPk, CampusScoped, Base):
    """An official lost-and-found desk (security office, library front desk...)."""

    __tablename__ = "desks"
    __table_args__ = (UniqueConstraint("campus_id", "name"),)

    name: Mapped[str] = mapped_column(String(200))
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )
    hours: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(String(320))
