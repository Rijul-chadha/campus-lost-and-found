"""AI-assisted search.

The LLM is used for language only: (1) turning a messy conversation into structured fields,
(2) writing a friendly reply. Ranking is done by the deterministic matcher. Every LLM step
has a rule-based fallback, so the feature degrades gracefully, never breaks.

Security boundaries:
  * The LLM never sees private data: no verification secrets, no reporter identities,
    no private descriptions of sensitive items (only `public_*` fields).
  * Found-item text is user-generated and may contain prompt injection; it is passed in a
    clearly delimited DATA block, the model has no tools, and output is post-filtered
    (URLs stripped, length capped) and rendered as plain text by the client.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ValidationError, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.security import Principal
from app.domain.extraction import (
    canonical_brand,
    canonical_color,
    embedding_text,
    extract_all,
    extract_item,
    extract_locations,
    extract_time_window,
)
from app.domain.matching import MatchSubject
from app.domain.vocabulary import ITEM_TYPE_TO_CATEGORY
from app.integrations.embeddings import embed_texts
from app.integrations.llm import LLMMessage, LLMUnavailable, get_llm
from app.modules.assistant import prompts
from app.modules.assistant.schemas import AssistantMatch, ChatIn, ChatOut, Extracted
from app.modules.campus.service import campus_overview, geo_index, get_campus, location_refs, tz
from app.modules.items import presenter
from app.modules.lost_reports.schemas import LostReportCreate
from app.modules.matching.service import search_items

log = get_logger(__name__)

_URL = re.compile(r"https?://\S+|www\.\S+", re.I)
_JSON_OBJ = re.compile(r"\{.*\}", re.S)

FOLLOW_UPS = {
    "item_type": "What kind of item is it — for example a backpack, AirPods, keys or a jacket?",
    "color": "What colour is it?",
    "location": "Roughly where on campus did you last have it?",
    "time": "When did you last have it?",
}


class _LLMExtraction(BaseModel):
    item_type: str | None = None
    colors: list[str] = []
    brand: str | None = None
    location: str | None = None
    when: str | None = None
    title: str | None = None
    description: str | None = None

    @field_validator("colors", mode="before")
    @classmethod
    def _list(cls, v: Any) -> Any:
        if v is None:
            return []
        return [v] if isinstance(v, str) else v


def _parse_json(raw: str) -> dict[str, Any]:
    m = _JSON_OBJ.search(raw)
    if not m:
        raise ValueError("no JSON object in completion")
    data = json.loads(m.group(0))
    if not isinstance(data, dict):
        raise ValueError("completion is not an object")
    return data


async def _llm_extract(user_text: str, location_names: list[str]) -> _LLMExtraction | None:
    llm = get_llm()
    system = prompts.EXTRACT_SYSTEM.format(
        item_types=json.dumps(sorted(ITEM_TYPE_TO_CATEGORY)),
        locations=json.dumps(location_names[:80]),
    )
    try:
        raw = await llm.complete(
            [LLMMessage("system", system),
             LLMMessage("user", f"<student>\n{user_text}\n</student>")],
            purpose="extract", json_mode=True, temperature=0.0, max_tokens=300,
        )
        return _LLMExtraction.model_validate(_parse_json(raw))
    except (LLMUnavailable, ValueError, ValidationError) as e:
        log.info("llm_extract_fallback", reason=type(e).__name__)
        return None


def _template_reply(n_matches: int, top_title: str | None, follow_up: str | None) -> str:
    if n_matches:
        lead = (f"I found {n_matches} possible match{'es' if n_matches > 1 else ''}. "
                f"The closest is “{top_title}”. Open a card below to check the details and "
                "claim it if it's yours.")
    else:
        lead = ("Nothing matching has been handed in yet. Save this as a watch and I'll "
                "notify you the moment something similar is reported.")
    return f"{lead} {follow_up}" if follow_up else lead


async def _llm_reply(matches_data: list[dict[str, Any]], follow_up: str | None,
                     user_text: str) -> str | None:
    payload = json.dumps({"MATCHES": matches_data, "FOLLOW_UP": follow_up}, default=str)
    try:
        raw = await get_llm().complete(
            [LLMMessage("system", prompts.REPLY_SYSTEM),
             LLMMessage("user", f"Student said:\n<student>\n{user_text[-1500:]}\n</student>\n\n"
                                f"DATA:\n{payload}")],
            purpose="reply", temperature=0.4, max_tokens=220,
        )
    except LLMUnavailable:
        return None
    text = _URL.sub("", raw).strip()
    return text[:800] if text else None


async def chat(session: AsyncSession, settings: Settings, p: Principal, body: ChatIn) -> ChatOut:
    now = datetime.now(UTC)
    campus = await get_campus(session, p.campus_id)
    campus_tz = tz(campus)
    refs = await location_refs(session, p.campus_id)
    user_text = "\n".join(m.content for m in body.messages if m.role == "user")

    # 1. Understand ------------------------------------------------------------------------
    rule = extract_all(user_text, now=now, tz=campus_tz, locations=refs)
    llm = await _llm_extract(user_text, [r.name for r in refs])

    item_type = rule.item_type
    if llm and llm.item_type:
        item_type = (llm.item_type if llm.item_type in ITEM_TYPE_TO_CATEGORY
                     else extract_item(llm.item_type)[1]) or item_type
    category = ITEM_TYPE_TO_CATEGORY.get(item_type) if item_type else rule.category
    colors = rule.colors or [c for c in (canonical_color(x) for x in (llm.colors if llm else []))
                             if c]
    brand = rule.brand or (canonical_brand(llm.brand) if llm else None)

    loc_ids = rule.location_ids or (extract_locations(llm.location, refs)
                                    if llm and llm.location else [])
    location_id = uuid.UUID(loc_ids[0]) if loc_ids else None
    location_name = next((r.name for r in refs if loc_ids and r.id == loc_ids[0]), None)

    window = ((rule.time_from, rule.time_to) if rule.time_from and rule.time_to else
              (extract_time_window(llm.when, now, campus_tz) if llm and llm.when else None))
    time_is_guess = window is None
    lost_from, lost_to = window or (now - timedelta(days=7), now)

    missing = [m for m in ("item_type", "color", "location", "time")
               if (m == "item_type" and not item_type) or (m == "color" and not colors)
               or (m == "location" and not location_id) or (m == "time" and time_is_guess)]
    follow_up = FOLLOW_UPS[missing[0]] if missing else None

    extracted = Extracted(category=category, item_type=item_type, colors=colors, brand=brand,
                          location_id=location_id, location_name=location_name,
                          lost_from=lost_from, lost_to=lost_to, time_is_guess=time_is_guess)

    # 2. Search (only once we know what kind of thing it is) -------------------------------
    matches: list[AssistantMatch] = []
    watch_draft: LostReportCreate | None = None
    if item_type:
        vectors, _ = await embed_texts(settings, [embedding_text(
            title=llm.title if llm else None, description=user_text, item_type=item_type,
            category=category, colors=colors, brand=brand)])
        geo = await geo_index(session, p.campus_id)
        query = MatchSubject(
            id="query", category=category, item_type=item_type, colors=tuple(colors),
            brand=brand, embedding=vectors[0],
            location_id=str(location_id) if location_id else None,
            geo=geo.get(str(location_id)) if location_id else None,
            occurred_from=lost_from, occurred_to=lost_to,
        )
        found = await search_items(session, settings, campus_id=p.campus_id, query=query,
                                   exclude_reporter=p.user_id, limit=5)
        views = await presenter.present_many(session, p, [i for i, _ in found])
        matches = [AssistantMatch(score=r.total, reasons=list(r.reasons), item=v)
                   for (_, r), v in zip(found, views, strict=True)]

        title = (llm.title if llm and llm.title else
                 " ".join(x for x in [colors[0] if colors else "", brand or "",
                                      item_type.replace("_", " ")] if x).strip().capitalize())
        watch_draft = LostReportCreate(
            title=title[:140], description=(llm.description if llm and llm.description
                                            else user_text)[:2000],
            category=category, item_type=item_type, colors=colors[:4], brand=brand,
            location_id=location_id, lost_from=lost_from, lost_to=lost_to,
        )

    # 3. Respond ---------------------------------------------------------------------------
    campus_view = await campus_overview(session, p.campus_id)
    loc_names = {loc.id: loc.name for loc in campus_view.locations}
    reply: str | None = None
    used_llm = llm is not None
    if item_type:
        data = [{"n": i + 1, "title": m.item.title, "colors": m.item.colors,
                 "found_at": m.item.location.name if m.item.location else None,
                 "found_on": m.item.found_at.astimezone(campus_tz).strftime("%a %b %d"),
                 "why": m.reasons[:3]} for i, m in enumerate(matches)]
        if used_llm:
            reply = await _llm_reply(data, follow_up, user_text)
        if reply is None:
            reply = _template_reply(len(matches), matches[0].item.title if matches else None,
                                    follow_up)
    else:
        reply = ("I can help you look. " + FOLLOW_UPS["item_type"])

    log.info("assistant_turn", used_llm=used_llm, prompt_version=prompts.PROMPT_VERSION,
             item_type=item_type, n_matches=len(matches), missing=missing,
             location=loc_names.get(location_id) if location_id else None)
    return ChatOut(reply=reply, extracted=extracted, missing=missing, matches=matches,
                   watch_draft=watch_draft, used_llm=used_llm)
