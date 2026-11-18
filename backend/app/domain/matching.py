"""Deterministic matching between lost reports and found items.

Pipeline (the DB layer does step 1; this module does 2-4):
  1. Candidate generation: SQL hard filters (campus, status, time) + pgvector ANN top-K.
  2. Vetoes: physically impossible pairs (found before it was lost, incompatible category).
  3. Component scores in [0, 1]: semantic, item type, colour, brand, location, time.
  4. Weighted sum, renormalised over the signals that are actually present, then lightly
     discounted when few signals are present (sparse info => less confident).

Why not let the LLM decide? Scores here are explainable, reproducible, unit-testable and
cost nothing per comparison. Reverse matching runs once per new item against every open
watch, which would be unaffordable with an LLM call per pair.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.domain.vocabulary import (
    ADJACENT_COLOR_FAMILIES,
    CANONICAL_COLOR_FAMILY,
    COMPATIBLE_CATEGORIES,
    CONFUSABLE_ITEM_TYPES,
)


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lng: float


@dataclass(frozen=True)
class MatchSubject:
    """Either side of a match. For a found item, occurred_from == occurred_to == found_at."""

    id: str
    category: str | None
    item_type: str | None
    colors: tuple[str, ...]
    brand: str | None
    embedding: Sequence[float] | None
    location_id: str | None
    geo: GeoPoint | None
    occurred_from: datetime
    occurred_to: datetime


@dataclass(frozen=True)
class Weights:
    semantic: float = 0.35
    item_type: float = 0.20
    color: float = 0.15
    brand: float = 0.10
    location: float = 0.12
    time: float = 0.08

    def as_dict(self) -> dict[str, float]:
        return {k: getattr(self, k) for k in ("semantic", "item_type", "color", "brand",
                                               "location", "time")}


@dataclass(frozen=True)
class SemanticCalibration:
    """Map raw cosine similarity to [0, 1]. Each embedding model has its own distribution."""

    floor: float = 0.20  # cosine at/below this => 0
    ceiling: float = 0.85  # cosine at/above this => 1

    def scale(self, cosine: float) -> float:
        if self.ceiling <= self.floor:
            return max(0.0, min(1.0, cosine))
        return max(0.0, min(1.0, (cosine - self.floor) / (self.ceiling - self.floor)))


@dataclass(frozen=True)
class MatchConfig:
    weights: Weights = field(default_factory=Weights)
    calibration: SemanticCalibration = field(default_factory=SemanticCalibration)
    # People misremember when they lost something; allow the item to be "found" a bit earlier.
    found_before_lost_slack: timedelta = timedelta(hours=12)
    time_half_life: timedelta = timedelta(days=3)
    near_radius_m: float = 75.0
    distance_decay_m: float = 400.0
    sparse_floor: float = 0.75  # multiplier when only the weakest signals are present
    cap_wrong_item_type: float = 0.35
    cap_color_conflict: float = 0.55
    cap_color_weak: float = 0.66


@dataclass(frozen=True)
class ScoreResult:
    lost_id: str
    found_id: str
    total: float
    components: dict[str, float]
    reasons: tuple[str, ...]
    vetoed: str | None = None

    @property
    def eligible(self) -> bool:
        return self.vetoed is None


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def haversine_m(a: GeoPoint, b: GeoPoint) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lng - a.lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def color_similarity(a: Iterable[str], b: Iterable[str]) -> float:
    best = 0.0
    for ca in a:
        for cb in b:
            if ca == cb:
                return 1.0
            fa, fb = CANONICAL_COLOR_FAMILY.get(ca), CANONICAL_COLOR_FAMILY.get(cb)
            if fa is None or fb is None:
                continue
            if "multi" in (fa, fb):
                best = max(best, 0.5)
            elif fa == fb:
                best = max(best, 0.8)
            else:
                best = max(best, ADJACENT_COLOR_FAMILIES.get(frozenset({fa, fb}), 0.0))
    return best


def categories_compatible(a: str | None, b: str | None) -> bool:
    if a is None or b is None or a == b or "other" in (a, b):
        return True
    return b in COMPATIBLE_CATEGORIES.get(a, frozenset()) or a in COMPATIBLE_CATEGORIES.get(
        b, frozenset()
    )


def _fmt_distance(m: float) -> str:
    return f"{round(m / 10) * 10:.0f} m" if m < 1000 else f"{m / 1000:.1f} km"


def _fmt_delay(td: timedelta) -> str:
    hours = td.total_seconds() / 3600
    if hours < 1:
        return "within the hour"
    if hours < 24:
        return f"{hours:.0f} h later"
    return f"{hours / 24:.0f} day(s) later"


def score_pair(lost: MatchSubject, found: MatchSubject, cfg: MatchConfig) -> ScoreResult:
    found_at = found.occurred_from

    # --- vetoes -------------------------------------------------------------------------
    if found_at < lost.occurred_from - cfg.found_before_lost_slack:
        return ScoreResult(lost.id, found.id, 0.0, {}, (), vetoed="found_before_lost")
    if not categories_compatible(lost.category, found.category):
        return ScoreResult(lost.id, found.id, 0.0, {}, (), vetoed="category_mismatch")

    comps: dict[str, float] = {}
    reasons: list[str] = []

    # --- semantic -------------------------------------------------------------------------
    if lost.embedding is not None and found.embedding is not None:
        comps["semantic"] = cfg.calibration.scale(cosine(lost.embedding, found.embedding))

    # --- item type ------------------------------------------------------------------------
    if lost.item_type and found.item_type:
        if lost.item_type == found.item_type:
            comps["item_type"] = 1.0
            reasons.append(f"Same kind of item ({found.item_type.replace('_', ' ')})")
        else:
            pair = frozenset({lost.item_type, found.item_type})
            comps["item_type"] = CONFUSABLE_ITEM_TYPES.get(pair, 0.0)
            if comps["item_type"]:
                reasons.append(
                    f"Similar kind of item ({found.item_type.replace('_', ' ')})"
                )

    # --- colour ---------------------------------------------------------------------------
    if lost.colors and found.colors:
        comps["color"] = color_similarity(lost.colors, found.colors)
        if comps["color"] >= 0.8:
            reasons.append(f"Colour matches ({', '.join(found.colors)})")

    # --- brand ----------------------------------------------------------------------------
    if lost.brand and found.brand:
        comps["brand"] = 1.0 if lost.brand == found.brand else 0.0
        if comps["brand"]:
            reasons.append(f"Same brand ({found.brand})")

    # --- location -------------------------------------------------------------------------
    if lost.location_id and found.location_id and lost.location_id == found.location_id:
        comps["location"] = 1.0
        reasons.append("Found where you said you lost it")
    elif lost.geo and found.geo:
        d = haversine_m(lost.geo, found.geo)
        comps["location"] = (
            1.0 if d <= cfg.near_radius_m
            else math.exp(-(d - cfg.near_radius_m) / cfg.distance_decay_m)
        )
        if comps["location"] >= 0.5:
            reasons.append(f"Found {_fmt_distance(d)} from where you lost it")

    # --- time -----------------------------------------------------------------------------
    delay = found_at - lost.occurred_to
    if delay <= timedelta(hours=6):
        comps["time"] = 1.0
        if found_at >= lost.occurred_from:
            reasons.append("Found around the time you lost it")
    else:
        comps["time"] = 0.5 ** (delay / cfg.time_half_life)
        if comps["time"] >= 0.5:
            reasons.append(f"Found {_fmt_delay(delay)}")

    # --- combine --------------------------------------------------------------------------
    weights = cfg.weights.as_dict()
    present_w = sum(weights[k] for k in comps)
    if present_w == 0:
        return ScoreResult(lost.id, found.id, 0.0, comps, tuple(reasons))
    raw = sum(weights[k] * v for k, v in comps.items()) / present_w
    coverage = present_w / sum(weights.values())
    total = raw * (cfg.sparse_floor + (1 - cfg.sparse_floor) * coverage)

    # Explicit contradictions cap the score. Caps sit below the notify threshold on purpose:
    # a contradicted pair may still be *suggested* when the owner browses (people misremember
    # colours), but it must never trigger a push notification.
    if comps.get("item_type") == 0.0:
        total = min(total, cfg.cap_wrong_item_type)
    color = comps.get("color")
    if color is not None and color < 0.4:
        total = min(total, cfg.cap_color_conflict if color == 0.0 else cfg.cap_color_weak)

    return ScoreResult(lost.id, found.id, round(total, 4), comps, tuple(reasons))


def rank(
    lost: MatchSubject,
    candidates: Iterable[MatchSubject],
    cfg: MatchConfig,
    *,
    min_score: float = 0.0,
    limit: int = 10,
) -> list[ScoreResult]:
    results = [score_pair(lost, c, cfg) for c in candidates]
    kept = [r for r in results if r.eligible and r.total >= min_score]
    kept.sort(key=lambda r: r.total, reverse=True)
    return kept[:limit]


def rank_reverse(
    found: MatchSubject,
    open_reports: Iterable[MatchSubject],
    cfg: MatchConfig,
    *,
    min_score: float,
) -> list[ScoreResult]:
    """New found item vs every candidate open watch (the 'notify me later' path)."""
    results = [score_pair(lr, found, cfg) for lr in open_reports]
    kept = [r for r in results if r.eligible and r.total >= min_score]
    kept.sort(key=lambda r: r.total, reverse=True)
    return kept
