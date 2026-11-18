from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.domain.matching import (
    GeoPoint,
    MatchConfig,
    MatchSubject,
    color_similarity,
    rank,
    rank_reverse,
    score_pair,
)
from app.integrations.embeddings.hashing import HashingEmbedder

T0 = datetime(2026, 11, 16, 14, 0, tzinfo=UTC)
LIB = GeoPoint(43.6644, -79.3995)
GYM = GeoPoint(43.6626, -79.4005)  # ~220 m away
FAR = GeoPoint(43.6532, -79.3832)  # ~1.8 km away
CFG = MatchConfig(calibration=HashingEmbedder.calibration)
EMB = HashingEmbedder()


def subj(
    sid: str,
    text: str,
    *,
    item_type: str | None,
    category: str | None,
    colors: tuple[str, ...] = (),
    brand: str | None = None,
    geo: GeoPoint | None = None,
    loc: str | None = None,
    start: datetime = T0,
    end: datetime | None = None,
) -> MatchSubject:
    return MatchSubject(
        id=sid, category=category, item_type=item_type, colors=colors, brand=brand,
        embedding=EMB.embed([text])[0], location_id=loc, geo=geo,
        occurred_from=start, occurred_to=end or start,
    )


LOST = subj("L", "black apple airpods case", item_type="earbuds", category="electronics",
            colors=("black",), brand="apple", geo=LIB, start=T0, end=T0 + timedelta(hours=3))


def test_true_match_scores_high() -> None:
    found = subj("F", "black airpods in charging case", item_type="earbuds",
                 category="electronics", colors=("black",), brand="apple", geo=LIB,
                 start=T0 + timedelta(hours=4))
    r = score_pair(LOST, found, CFG)
    assert r.eligible
    assert r.total >= 0.8, r
    assert "Same kind of item (earbuds)" in r.reasons


def test_found_before_lost_is_vetoed() -> None:
    found = subj("F", "black airpods", item_type="earbuds", category="electronics",
                 colors=("black",), start=T0 - timedelta(days=2))
    assert score_pair(LOST, found, CFG).vetoed == "found_before_lost"


def test_small_clock_skew_is_tolerated() -> None:
    found = subj("F", "black airpods", item_type="earbuds", category="electronics",
                 colors=("black",), start=T0 - timedelta(hours=2))
    assert score_pair(LOST, found, CFG).eligible


def test_incompatible_category_vetoed_but_wallet_and_cards_compatible() -> None:
    bottle = subj("F", "black bottle", item_type="water_bottle", category="bottles",
                  colors=("black",), start=T0 + timedelta(hours=1))
    assert score_pair(LOST, bottle, CFG).vetoed == "category_mismatch"

    lost_wallet = subj("L2", "brown leather wallet", item_type="wallet", category="wallet",
                       colors=("brown",))
    card = subj("F2", "student card", item_type="student_card", category="cards",
                start=T0 + timedelta(hours=1))
    assert score_pair(lost_wallet, card, CFG).eligible


def test_wrong_item_type_is_capped() -> None:
    phone = subj("F", "black apple iphone", item_type="phone", category="electronics",
                 colors=("black",), brand="apple", geo=LIB, start=T0 + timedelta(hours=1))
    assert score_pair(LOST, phone, CFG).total <= 0.35


def test_colour_contradiction_never_reaches_notify_threshold() -> None:
    # Regression from the eval: "red water bottle" matched a clear Nalgene at 0.79.
    lost = subj("L", "red water bottle", item_type="water_bottle", category="bottles",
                colors=("red",), geo=GYM)
    found = subj("F", "clear nalgene water bottle", item_type="water_bottle",
                 category="bottles", colors=("clear",), geo=GYM, start=T0 + timedelta(hours=1))
    r = score_pair(lost, found, CFG)
    assert r.eligible  # still browsable as a suggestion
    assert r.total <= CFG.cap_color_conflict < 0.70


def test_unknown_signals_do_not_penalise_much() -> None:
    sparse = subj("F", "airpods", item_type="earbuds", category="electronics",
                  start=T0 + timedelta(hours=2))
    r = score_pair(LOST, sparse, CFG)
    assert "brand" not in r.components and "color" not in r.components
    assert r.total >= 0.6


def test_distance_and_time_decay_monotonically() -> None:
    base = subj("F", "black airpods case", item_type="earbuds", category="electronics",
                colors=("black",), brand="apple", geo=LIB, start=T0 + timedelta(hours=4))
    near = score_pair(LOST, base, CFG).total
    mid = score_pair(LOST, replace(base, geo=GYM), CFG).total
    far = score_pair(LOST, replace(base, geo=FAR), CFG).total
    assert near > mid > far

    later = replace(base, occurred_from=T0 + timedelta(days=6),
                    occurred_to=T0 + timedelta(days=6))
    assert score_pair(LOST, later, CFG).total < near


def test_same_location_id_beats_geo() -> None:
    a = replace(LOST, location_id="lib", geo=None)
    f = subj("F", "black airpods", item_type="earbuds", category="electronics",
             colors=("black",), loc="lib", start=T0 + timedelta(hours=1))
    assert score_pair(a, f, CFG).components["location"] == 1.0


def test_color_similarity_families() -> None:
    assert color_similarity(["navy"], ["blue"]) == 0.8
    assert color_similarity(["black"], ["charcoal"]) == 0.45
    assert color_similarity(["red"], ["green"]) == 0.0
    assert color_similarity(["white", "red"], ["red"]) == 1.0


def test_rank_orders_and_filters() -> None:
    good = subj("good", "black airpods case apple", item_type="earbuds",
                category="electronics", colors=("black",), brand="apple", geo=LIB,
                start=T0 + timedelta(hours=4))
    meh = subj("meh", "white earbuds", item_type="earbuds", category="electronics",
               colors=("white",), geo=FAR, start=T0 + timedelta(days=4))
    bad = subj("bad", "red water bottle", item_type="water_bottle", category="bottles",
               colors=("red",), start=T0 + timedelta(hours=4))
    ranked = rank(LOST, [meh, bad, good], CFG, min_score=0.1)
    assert [r.found_id for r in ranked] == ["good", "meh"]


def test_reverse_matching_finds_the_right_watch() -> None:
    found = subj("F", "black airpods", item_type="earbuds", category="electronics",
                 colors=("black",), brand="apple", geo=LIB, start=T0 + timedelta(hours=5))
    other = subj("L-other", "blue umbrella", item_type="umbrella", category="accessories",
                 colors=("blue",))
    res = rank_reverse(found, [other, LOST], CFG, min_score=0.5)
    assert [r.lost_id for r in res] == ["L"]
