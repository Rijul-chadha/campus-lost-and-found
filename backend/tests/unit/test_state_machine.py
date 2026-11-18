import pytest

from app.domain.enums import ClaimStatus, ItemStatus, LostReportStatus
from app.domain.errors import InvalidTransition
from app.domain.state_machine import CLAIM, ITEM, LOST_REPORT


def test_happy_path_item_lifecycle() -> None:
    s = ItemStatus.REPORTED
    for action in ("publish", "approve_claim", "return"):
        s = ITEM.next(action, s)
    assert s is ItemStatus.RETURNED
    assert s in ITEM.terminal


def test_unclaimed_item_lifecycle() -> None:
    s = ITEM.next("publish", ItemStatus.REPORTED)
    s = ITEM.next("expire", s)
    assert ITEM.actions_from(s) == ["dispose", "donate", "extend", "remove"]
    assert ITEM.next("donate", s) is ItemStatus.DONATED


@pytest.mark.parametrize(
    ("action", "state"),
    [
        ("donate", ItemStatus.AVAILABLE),  # must expire first
        ("donate", ItemStatus.CLAIMED),  # someone is about to pick it up
        ("return", ItemStatus.AVAILABLE),  # no approved claim
        ("approve_claim", ItemStatus.REPORTED),  # not published yet
        ("publish", ItemStatus.RETURNED),  # terminal
        ("remove", ItemStatus.CLAIMED),
    ],
)
def test_illegal_item_transitions(action: str, state: ItemStatus) -> None:
    assert not ITEM.can(action, state)
    with pytest.raises(InvalidTransition) as exc:
        ITEM.next(action, state)
    assert exc.value.details["current"] == state.value


def test_terminal_states_have_no_exits() -> None:
    for machine in (ITEM, CLAIM, LOST_REPORT):
        for state in machine.terminal:
            assert machine.actions_from(state) == [], (machine.name, state)


def test_claim_lifecycle() -> None:
    assert CLAIM.next("approve", ClaimStatus.PENDING) is ClaimStatus.APPROVED
    assert CLAIM.next("complete", ClaimStatus.APPROVED) is ClaimStatus.COMPLETED
    assert CLAIM.next("cancel", ClaimStatus.APPROVED) is ClaimStatus.CANCELLED
    with pytest.raises(InvalidTransition):
        CLAIM.next("complete", ClaimStatus.PENDING)


def test_lost_report_can_be_renewed_after_expiry() -> None:
    assert LOST_REPORT.next("renew", LostReportStatus.EXPIRED) is LostReportStatus.OPEN


def test_unknown_action() -> None:
    with pytest.raises(InvalidTransition):
        ITEM.next("teleport", ItemStatus.AVAILABLE)
