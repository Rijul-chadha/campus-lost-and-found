"""What the public is allowed to see about a found item.

Rules:
  * Contact details and long digit sequences (student numbers, card numbers) are redacted
    from public text on write, so they never leak via search, the LLM, or email.
  * Sensitive item types (IDs, bank cards, wallets) get a generic public title, no public
    description and no public photos; only the holder, desk staff and an approved claimant
    see the full record. Matching still uses the full private text server-side.
  * The finder's verification detail is never public, never sent to the LLM, never matched on.
"""

from __future__ import annotations

import re

from app.domain.vocabulary import SENSITIVE_ITEM_TYPES

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\d)")
_LONG_DIGITS = re.compile(r"(?<!\d)\d(?:[\s-]?\d){5,}(?!\d)")


def redact(text: str | None) -> str | None:
    if not text:
        return text
    text = _EMAIL.sub("[email hidden]", text)
    text = _PHONE.sub("[phone hidden]", text)
    return _LONG_DIGITS.sub("[number hidden]", text)


def is_sensitive(item_type: str | None) -> bool:
    return item_type in SENSITIVE_ITEM_TYPES


_GENERIC_TITLES = {
    "student_card": "Student / campus card",
    "drivers_license": "Driver's licence",
    "bank_card": "Bank or transit card",
    "health_card": "Health card",
    "passport": "Passport",
    "wallet": "Wallet",
}


def public_title(title: str, item_type: str | None) -> str:
    if is_sensitive(item_type) and item_type:
        return _GENERIC_TITLES.get(item_type, "Personal item")
    return redact(title) or title
