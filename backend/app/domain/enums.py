from enum import StrEnum


class Role(StrEnum):
    MEMBER = "member"  # any student/staff: can be a finder and an owner
    DESK = "desk"  # lost-and-found desk staff / facilitators
    ADMIN = "admin"


class HolderType(StrEnum):
    FINDER = "finder"  # the person who found it still has it
    DESK = "desk"  # handed in to a lost-and-found desk


class ItemStatus(StrEnum):
    REPORTED = "reported"  # saved, still being processed (embedding, photo scrub)
    AVAILABLE = "available"  # searchable and claimable
    CLAIMED = "claimed"  # a claim was approved; waiting for physical handover
    RETURNED = "returned"  # handed back to owner (terminal)
    EXPIRED = "expired"  # retention window passed, awaiting desk decision
    DONATED = "donated"  # terminal
    DISPOSED = "disposed"  # terminal
    REMOVED = "removed"  # moderation / spam (terminal)


class ClaimStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class LostReportStatus(StrEnum):
    OPEN = "open"  # a standing watch: matched against every new found item
    RESOLVED = "resolved"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class MatchStatus(StrEnum):
    SUGGESTED = "suggested"  # above suggest threshold: shown when owner browses
    NOTIFIED = "notified"  # above notify threshold: owner was notified
    DISMISSED = "dismissed"  # owner said "not mine" (feedback signal)
    CLAIMED = "claimed"


class CustodyEventType(StrEnum):
    REPORTED = "reported"
    TRANSFERRED_TO_DESK = "transferred_to_desk"
    CLAIM_OPENED = "claim_opened"
    CLAIM_APPROVED = "claim_approved"
    CLAIM_REJECTED = "claim_rejected"
    CLAIM_CANCELLED = "claim_cancelled"
    RETURNED = "returned"
    EXPIRED = "expired"
    RETENTION_EXTENDED = "retention_extended"
    DONATED = "donated"
    DISPOSED = "disposed"
    REMOVED = "removed"


class NotificationKind(StrEnum):
    POSSIBLE_MATCH = "possible_match"
    CLAIM_RECEIVED = "claim_received"
    CLAIM_APPROVED = "claim_approved"
    CLAIM_REJECTED = "claim_rejected"
    ITEM_RETURNED = "item_returned"
    WATCH_EXPIRING = "watch_expiring"
    ITEMS_EXPIRED = "items_expired"
