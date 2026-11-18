"""Authorisation rules for found items, in one place so they are easy to audit and test."""

from __future__ import annotations

from app.core.security import Principal
from app.domain.enums import HolderType, ItemStatus
from app.modules.items.models import FoundItem


def is_reporter(p: Principal, item: FoundItem) -> bool:
    return item.reporter_id == p.user_id


def can_view_private(p: Principal, item: FoundItem, *, is_approved_claimant: bool) -> bool:
    if item.campus_id != p.campus_id:
        return False
    return is_reporter(p, item) or p.is_staff or is_approved_claimant


def can_view(p: Principal, item: FoundItem) -> bool:
    if item.campus_id != p.campus_id:
        return False
    if item.status in (ItemStatus.REMOVED, ItemStatus.REPORTED):
        return is_reporter(p, item) or p.is_staff
    return True


def can_claim(p: Principal, item: FoundItem) -> bool:
    return (item.campus_id == p.campus_id and item.status is ItemStatus.AVAILABLE
            and not is_reporter(p, item))


def can_review_claims(p: Principal, item: FoundItem) -> bool:
    """The current holder decides: the finder while they hold it, desk staff once handed in."""
    if item.campus_id != p.campus_id:
        return False
    if item.holder_type is HolderType.FINDER:
        return is_reporter(p, item) or p.is_staff
    return p.is_staff
