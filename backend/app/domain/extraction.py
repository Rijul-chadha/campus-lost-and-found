"""Rule-based attribute extraction.

Used in three places:
  1. As the fallback "assistant brain" when the LLM is unavailable or not configured.
  2. To canonicalise LLM output (the LLM may say "navy-ish", we store "navy").
  3. To enrich finder reports that only have free-text descriptions.

Deterministic and fast, so it is also the baseline the matching eval runs against.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.domain.vocabulary import (
    BRANDS,
    CATALOG,
    COLORS,
    IMPLIED_BRANDS,
    ITEM_TYPE_TO_CATEGORY,
)

_WORD_CLEAN = re.compile(r"[^a-z0-9'\- ]+")


def normalize(text: str) -> str:
    text = text.lower().replace("’", "'")
    text = _WORD_CLEAN.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _phrase_pattern(phrases: Sequence[str]) -> re.Pattern[str]:
    # Longest first so "water bottle" wins over "bottle" and "apple watch" over "watch".
    ordered = sorted({p for p in phrases if p}, key=len, reverse=True)
    alternation = "|".join(re.escape(p) for p in ordered)
    return re.compile(rf"(?<![a-z0-9])(?:{alternation})(?![a-z0-9])")


@lru_cache(maxsize=1)
def _item_index() -> tuple[re.Pattern[str], dict[str, str]]:
    synonym_to_type: dict[str, str] = {}
    for types in CATALOG.values():
        for item_type, synonyms in types.items():
            for s in synonyms:
                synonym_to_type.setdefault(s, item_type)
    return _phrase_pattern(list(synonym_to_type)), synonym_to_type


@lru_cache(maxsize=1)
def _color_pattern() -> re.Pattern[str]:
    return _phrase_pattern(list(COLORS))


@lru_cache(maxsize=1)
def _brand_pattern() -> re.Pattern[str]:
    return _phrase_pattern(list(BRANDS) + list(IMPLIED_BRANDS))


@dataclass(frozen=True)
class LocationRef:
    id: str
    name: str
    aliases: tuple[str, ...] = ()


@dataclass
class Extracted:
    category: str | None = None
    item_type: str | None = None
    colors: list[str] = field(default_factory=list)
    brand: str | None = None
    location_ids: list[str] = field(default_factory=list)
    time_from: datetime | None = None
    time_to: datetime | None = None
    other_items: list[str] = field(default_factory=list)

    @property
    def missing(self) -> list[str]:
        """Fields worth asking a follow-up question about, most valuable first."""
        out = []
        if not self.item_type:
            out.append("item_type")
        if not self.colors:
            out.append("color")
        if not self.location_ids:
            out.append("location")
        if not self.time_from:
            out.append("time")
        return out


def extract_item(text: str) -> tuple[str | None, str | None, list[str]]:
    """Return (category, item_type, other_item_types) - first mention is the primary item."""
    pattern, synonym_to_type = _item_index()
    found: list[str] = []
    for m in pattern.finditer(normalize(text)):
        t = synonym_to_type[m.group(0)]
        if t not in found:
            found.append(t)
    if not found:
        return None, None, []
    primary = found[0]
    return ITEM_TYPE_TO_CATEGORY[primary], primary, found[1:]


def extract_colors(text: str) -> list[str]:
    out: list[str] = []
    for m in _color_pattern().finditer(normalize(text)):
        canon = COLORS[m.group(0)][0]
        if canon not in out:
            out.append(canon)
    return out


def canonical_color(raw: str) -> str | None:
    raw_n = normalize(raw)
    if raw_n in COLORS:
        return COLORS[raw_n][0]
    found = extract_colors(raw_n)
    return found[0] if found else None


def extract_brand(text: str) -> str | None:
    norm = normalize(text)
    implied: str | None = None
    for m in _brand_pattern().finditer(norm):
        token = m.group(0)
        if token in BRANDS:
            return BRANDS[token]
        implied = implied or IMPLIED_BRANDS.get(token)
    return implied


def canonical_brand(raw: str | None) -> str | None:
    if not raw:
        return None
    norm = normalize(raw)
    return BRANDS.get(norm) or extract_brand(norm) or norm or None


def extract_locations(text: str, locations: Sequence[LocationRef]) -> list[str]:
    norm = normalize(text)
    hits: list[tuple[int, str]] = []
    for loc in locations:
        for name in (loc.name, *loc.aliases):
            n = normalize(name)
            if not n:
                continue
            m = re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", norm)
            if m:
                hits.append((m.start(), loc.id))
                break
    hits.sort()
    seen: list[str] = []
    for _, loc_id in hits:
        if loc_id not in seen:
            seen.append(loc_id)
    return seen


_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_DAYS_AGO = re.compile(r"(\d{1,2}|a|one|two|three|four|five|six) days? ago")
_NUM_WORDS = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def _day_window(day: datetime, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day.date(), time.min, tzinfo=tz)
    return start, start + timedelta(days=1)


def extract_time_window(
    text: str, now: datetime, tz: ZoneInfo
) -> tuple[datetime, datetime] | None:
    """Best-effort window for when something was lost. Returns aware datetimes, end <= now."""
    norm = normalize(text)
    local_now = now.astimezone(tz)

    def clamp(w: tuple[datetime, datetime]) -> tuple[datetime, datetime]:
        return w[0], min(w[1], local_now)

    if "last night" in norm:
        y = local_now - timedelta(days=1)
        return clamp((datetime.combine(y.date(), time(17, 0), tzinfo=tz),
                      datetime.combine(local_now.date(), time(6, 0), tzinfo=tz)))
    if "yesterday" in norm:
        return clamp(_day_window(local_now - timedelta(days=1), tz))
    if any(p in norm for p in ("today", "this morning", "this afternoon", "tonight",
                               "this evening", "an hour ago", "few hours ago", "just now")):
        return clamp(_day_window(local_now, tz))
    m = _DAYS_AGO.search(norm)
    if m:
        raw = m.group(1)
        n = int(raw) if raw.isdigit() else _NUM_WORDS[raw]
        return clamp(_day_window(local_now - timedelta(days=n), tz))
    for idx, wd in enumerate(_WEEKDAYS):
        if re.search(rf"(?<![a-z]){wd}(?![a-z])", norm):
            delta = (local_now.weekday() - idx) % 7
            if "last " + wd in norm and delta == 0:
                delta = 7
            return clamp(_day_window(local_now - timedelta(days=delta), tz))
    if "this week" in norm:
        start = local_now - timedelta(days=local_now.weekday())
        return clamp((datetime.combine(start.date(), time.min, tzinfo=tz), local_now))
    if "last week" in norm:
        return clamp((local_now - timedelta(days=14), local_now))
    return None


def extract_all(
    text: str,
    *,
    now: datetime,
    tz: ZoneInfo,
    locations: Sequence[LocationRef] = (),
) -> Extracted:
    category, item_type, others = extract_item(text)
    window = extract_time_window(text, now, tz)
    return Extracted(
        category=category,
        item_type=item_type,
        colors=extract_colors(text),
        brand=extract_brand(text),
        location_ids=extract_locations(text, locations),
        time_from=window[0] if window else None,
        time_to=window[1] if window else None,
        other_items=others,
    )


def embedding_text(
    *,
    title: str | None,
    description: str | None,
    item_type: str | None,
    category: str | None,
    colors: Sequence[str],
    brand: str | None,
) -> str:
    """Canonical text that gets embedded for both found items and lost reports.

    Putting the canonical attributes first means both sides share vocabulary even when the
    free text differs ("AirPods" vs "white wireless earbuds").
    """
    parts = [
        " ".join(colors),
        brand or "",
        (item_type or "").replace("_", " "),
        category or "",
        title or "",
        description or "",
    ]
    return " . ".join(p.strip() for p in parts if p and p.strip())
