"""Import every model so Base.metadata is complete (used by Alembic and tests)."""

from app.db.base import Base
from app.events.models import OutboxEvent
from app.modules.auth.models import User
from app.modules.campus.models import Campus, Desk, Location
from app.modules.claims.models import Claim
from app.modules.items.models import CustodyEvent, FoundItem
from app.modules.lost_reports.models import LostReport
from app.modules.matching.models import Match
from app.modules.notifications.models import Notification

__all__ = [
    "Base", "Campus", "Claim", "CustodyEvent", "Desk", "FoundItem", "Location", "LostReport",
    "Match", "Notification", "OutboxEvent", "User",
]
