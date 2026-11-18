from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.extraction import (
    LocationRef,
    canonical_color,
    extract_all,
    extract_brand,
    extract_colors,
    extract_item,
    extract_time_window,
)

TZ = ZoneInfo("America/Toronto")
# Tuesday 2026-11-17 15:00 local
NOW = datetime(2026, 11, 17, 20, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("text", "category", "item_type"),
    [
        ("I lost my AirPods case", "electronics", "earbuds"),
        ("black backpack with a macbook inside", "bags", "backpack"),
        ("Hydro Flask water bottle, dented", "bottles", "water_bottle"),
        ("found someone's student card near the gym", "cards", "student_card"),
        ("keys on a red lanyard", "keys", "keys"),
        ("Apple Watch with a blue strap", "electronics", "smartwatch"),
        ("a grey hoodie", "clothing", "hoodie"),
        ("something shiny", None, None),
    ],
)
def test_extract_item(text: str, category: str | None, item_type: str | None) -> None:
    cat, typ, _ = extract_item(text)
    assert (cat, typ) == (category, item_type)


def test_word_boundaries_avoid_false_hits() -> None:
    # "keyboard" must not be keys, "open" must not be pen, "headphones" must not be phone
    assert extract_item("left the keyboard open")[1] is None
    assert extract_item("Sony headphones")[1] == "headphones"


def test_secondary_items_are_kept() -> None:
    _, primary, others = extract_item("backpack with my laptop and charger")
    assert primary == "backpack"
    assert others == ["laptop", "charger"]


def test_colors_canonicalise_and_dedupe() -> None:
    assert extract_colors("Navy blue jacket with grey and gray stripes") == ["navy", "gray"]
    assert canonical_color("Dark Grey") == "charcoal"
    assert canonical_color("chartreuse-ish") is None


def test_brand_explicit_beats_implied() -> None:
    assert extract_brand("my airpods") == "apple"
    assert extract_brand("Samsung galaxy buds") == "samsung"
    assert extract_brand("north face jacket") == "the north face"
    assert extract_brand("plain bag") is None


def test_time_windows() -> None:
    y = extract_time_window("lost it yesterday", NOW, TZ)
    assert y is not None and y[0].day == 16 and y[1].day == 17
    mon = extract_time_window("I had it on Monday", NOW, TZ)
    assert mon is not None and mon[0].date().isoformat() == "2026-11-16"
    tue = extract_time_window("last tuesday", NOW, TZ)
    assert tue is not None and tue[0].date().isoformat() == "2026-11-10"
    two = extract_time_window("about 2 days ago", NOW, TZ)
    assert two is not None and two[0].date().isoformat() == "2026-11-15"
    today = extract_time_window("this morning", NOW, TZ)
    assert today is not None and today[1] <= NOW
    assert extract_time_window("no idea when", NOW, TZ) is None


def test_extract_all_with_locations() -> None:
    locs = [
        LocationRef("lib", "Robarts Library", ("library", "robarts")),
        LocationRef("gym", "Athletic Centre", ("gym", "AC")),
    ]
    e = extract_all("Lost black Nike backpack in the library yesterday", now=NOW, tz=TZ,
                    locations=locs)
    assert e.item_type == "backpack"
    assert e.colors == ["black"]
    assert e.brand == "nike"
    assert e.location_ids == ["lib"]
    assert e.time_from is not None
    assert e.missing == []

    sparse = extract_all("lost something", now=NOW, tz=TZ)
    assert sparse.missing == ["item_type", "color", "location", "time"]
