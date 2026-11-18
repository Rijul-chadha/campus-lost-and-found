from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, literal_column, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.metrics import MATCH_LATENCY, MATCHES_CREATED
from app.domain.enums import MatchStatus, NotificationKind
from app.domain.matching import (
    MatchConfig,
    MatchSubject,
    ScoreResult,
    rank,
    rank_reverse,
    score_pair,
)
from app.integrations.embeddings import get_embedder
from app.modules.campus.models import Location
from app.modules.campus.service import geo_index
from app.modules.items.models import FoundItem
from app.modules.lost_reports.models import LostReport
from app.modules.matching import repository as repo
from app.modules.matching.models import Match
from app.modules.notifications.service import notify

log = get_logger(__name__)

MAX_NOTIFICATIONS_PER_ITEM = 15  # a vague item ("black bag") must not spam every watch


def match_config(settings: Settings) -> MatchConfig:
    emb = get_embedder(settings.embedding_provider, settings.embedding_model)
    return MatchConfig(calibration=emb.calibration)


async def search_items(
    session: AsyncSession, settings: Settings, *, campus_id: uuid.UUID, query: MatchSubject,
    exclude_reporter: uuid.UUID | None, limit: int = 5,
) -> list[tuple[FoundItem, ScoreResult]]:
    """Synchronous search used by the assistant: top matches for a description right now."""
    assert query.embedding is not None
    cfg = match_config(settings)
    start = time.perf_counter()
    items = await repo.item_candidates(
        session, campus_id=campus_id, vector=query.embedding, lost_from=query.occurred_from,
        category=query.category, item_type=query.item_type, slack=cfg.found_before_lost_slack,
        k=settings.match_candidate_pool, exclude_reporter=exclude_reporter,
    )
    geo = await geo_index(session, campus_id)
    subjects = {str(i.id): i for i in items}
    ranked = rank(query, (repo.item_subject(i, geo) for i in items), cfg,
                  min_score=settings.match_suggest_threshold, limit=limit)
    MATCH_LATENCY.labels("search").observe(time.perf_counter() - start)
    return [(subjects[r.found_id], r) for r in ranked]


async def _persist(
    session: AsyncSession, settings: Settings, report: LostReport, item: FoundItem,
    result: ScoreResult, *, allow_notify: bool,
) -> bool:
    """Upsert the pair; notify the owner once if it crosses the notify threshold."""
    row = (await session.execute(
        pg_insert(Match)
        .values(id=uuid.uuid4(), campus_id=report.campus_id, lost_report_id=report.id,
                found_item_id=item.id, score=result.total, components=result.components,
                reasons=list(result.reasons), status=MatchStatus.SUGGESTED)
        .on_conflict_do_update(
            constraint="uq_matches_pair",
            set_={"score": result.total, "components": result.components,
                  "reasons": list(result.reasons), "updated_at": func.now()},
            # Owner feedback wins: a dismissed/claimed pair is never revived.
            where=Match.status == MatchStatus.SUGGESTED,
        )
        .returning(Match.id, Match.status, literal_column("(xmax = 0)").label("inserted"))
    )).one_or_none()
    if row is None:
        return False  # existed and was dismissed/claimed
    if row.inserted:
        MATCHES_CREATED.labels("suggested").inc()

    if not allow_notify or result.total < settings.match_notify_threshold:
        return False
    if row.status is not MatchStatus.SUGGESTED:
        return False
    loc = await session.get(Location, item.found_location_id) if item.found_location_id else None
    where = loc.name if loc else "campus"
    created = await notify(
        session, campus_id=report.campus_id, user_id=report.owner_id,
        kind=NotificationKind.POSSIBLE_MATCH,
        title=f"Possible match for your lost {report.title.lower()}",
        body=(f"Someone reported finding “{item.public_title}” at {where} on "
              f"{item.found_at:%b %d}. Open it to check the details and claim it if it's yours."),
        link=f"/items/{item.id}?watch={report.id}",
        payload={"lost_report_id": str(report.id), "found_item_id": str(item.id),
                 "score": result.total, "reasons": list(result.reasons)},
        dedupe_key=f"match:{report.id}:{item.id}",
    )
    if created:
        await session.execute(update(Match).where(Match.id == row.id)
                              .values(status=MatchStatus.NOTIFIED))
        MATCHES_CREATED.labels("notified").inc()
    return created


async def match_found_item(session: AsyncSession, settings: Settings, item: FoundItem) -> int:
    """Reverse matching: a new item against every open watch. Returns notifications sent."""
    assert item.embedding is not None
    cfg = match_config(settings)
    start = time.perf_counter()
    reports = await repo.watch_candidates(
        session, campus_id=item.campus_id, vector=list(item.embedding), found_at=item.found_at,
        category=item.category, item_type=item.item_type, slack=cfg.found_before_lost_slack,
        k=settings.match_candidate_pool * 4, exclude_owner=item.reporter_id,
    )
    geo = await geo_index(session, item.campus_id)
    by_id = {str(r.id): r for r in reports}
    results = rank_reverse(repo.item_subject(item, geo),
                           (repo.report_subject(r, geo) for r in reports), cfg,
                           min_score=settings.match_suggest_threshold)
    sent = 0
    for i, res in enumerate(results):
        sent += await _persist(session, settings, by_id[res.lost_id], item, res,
                               allow_notify=i < MAX_NOTIFICATIONS_PER_ITEM)
    MATCH_LATENCY.labels("reverse").observe(time.perf_counter() - start)
    log.info("reverse_match", item_id=str(item.id), candidates=len(reports),
             matched=len(results), notified=sent)
    return sent


async def match_lost_report(session: AsyncSession, settings: Settings,
                            report: LostReport) -> int:
    """Forward matching for a new/renewed watch: persist suggestions for the owner's watch page.

    No push notifications here: the owner just saw these results in the assistant. Only items
    reported *later* (reverse matching) trigger notifications.
    """
    assert report.embedding is not None
    cfg = match_config(settings)
    start = time.perf_counter()
    items = await repo.item_candidates(
        session, campus_id=report.campus_id, vector=list(report.embedding),
        lost_from=report.lost_from, category=report.category, item_type=report.item_type,
        slack=cfg.found_before_lost_slack, k=settings.match_candidate_pool,
        exclude_reporter=report.owner_id,
    )
    geo = await geo_index(session, report.campus_id)
    q = repo.report_subject(report, geo)
    sent = 0
    for item in items:
        res = score_pair(q, repo.item_subject(item, geo), cfg)
        if res.eligible and res.total >= settings.match_suggest_threshold:
            sent += await _persist(session, settings, report, item, res, allow_notify=False)
    report.last_matched_at = datetime.now(UTC)
    MATCH_LATENCY.labels("forward").observe(time.perf_counter() - start)
    return sent
