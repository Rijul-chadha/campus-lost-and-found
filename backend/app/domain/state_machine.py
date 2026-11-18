"""Explicit state machines for every entity with a lifecycle.

All status changes in the codebase go through `Machine.assert_can` / `Machine.next`, so an
illegal transition (e.g. donating an item that has a pending claim) is impossible to write
by accident, and the full lifecycle is reviewable in one screen of code.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

from app.domain.enums import ClaimStatus, ItemStatus, LostReportStatus
from app.domain.errors import InvalidTransition

S = TypeVar("S", bound=StrEnum)


@dataclass(frozen=True)
class Machine(Generic[S]):
    name: str
    # action -> {from_state -> to_state}
    transitions: Mapping[str, Mapping[S, S]]
    terminal: frozenset[S]

    def can(self, action: str, current: S) -> bool:
        return current in self.transitions.get(action, {})

    def next(self, action: str, current: S) -> S:
        table = self.transitions.get(action)
        if table is None:
            raise InvalidTransition(f"{self.name}: unknown action '{action}'")
        if current not in table:
            allowed = sorted(s.value for s in table)
            raise InvalidTransition(
                f"{self.name}: cannot '{action}' from '{current.value}'",
                details={"action": action, "current": current.value, "allowed_from": allowed},
            )
        return table[current]

    def assert_can(self, action: str, current: S) -> None:
        self.next(action, current)

    def actions_from(self, current: S) -> list[str]:
        return sorted(a for a, table in self.transitions.items() if current in table)


I = ItemStatus
ITEM = Machine[ItemStatus](
    name="found_item",
    transitions={
        "publish": {I.REPORTED: I.AVAILABLE},
        "approve_claim": {I.AVAILABLE: I.CLAIMED},
        "revert_claim": {I.CLAIMED: I.AVAILABLE},  # approved claimant cancelled / no-show
        "return": {I.CLAIMED: I.RETURNED},
        "expire": {I.AVAILABLE: I.EXPIRED},
        "extend": {I.EXPIRED: I.AVAILABLE},
        "donate": {I.EXPIRED: I.DONATED},
        "dispose": {I.EXPIRED: I.DISPOSED},
        "remove": {I.REPORTED: I.REMOVED, I.AVAILABLE: I.REMOVED, I.EXPIRED: I.REMOVED},
    },
    terminal=frozenset({I.RETURNED, I.DONATED, I.DISPOSED, I.REMOVED}),
)

C = ClaimStatus
CLAIM = Machine[ClaimStatus](
    name="claim",
    transitions={
        "approve": {C.PENDING: C.APPROVED},
        "reject": {C.PENDING: C.REJECTED},
        "complete": {C.APPROVED: C.COMPLETED},
        "cancel": {C.PENDING: C.CANCELLED, C.APPROVED: C.CANCELLED},
    },
    terminal=frozenset({C.REJECTED, C.COMPLETED, C.CANCELLED}),
)

L = LostReportStatus
LOST_REPORT = Machine[LostReportStatus](
    name="lost_report",
    transitions={
        "resolve": {L.OPEN: L.RESOLVED},
        "expire": {L.OPEN: L.EXPIRED},
        "renew": {L.OPEN: L.OPEN, L.EXPIRED: L.OPEN},
        "cancel": {L.OPEN: L.CANCELLED, L.EXPIRED: L.CANCELLED},
    },
    terminal=frozenset({L.RESOLVED, L.CANCELLED}),
)

# Statuses in which a found item is visible to search and matching.
SEARCHABLE_ITEM_STATUSES = frozenset({I.AVAILABLE})
# Claims that still "hold a seat" on an item.
ACTIVE_CLAIM_STATUSES = frozenset({C.PENDING, C.APPROVED})
