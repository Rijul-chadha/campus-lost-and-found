from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.session import get_sessionmaker
from app.domain.enums import Role
from app.workers import tasks
from tests.integration.conftest import make_user, run_outbox

pytestmark = pytest.mark.integration


def iso(dt: datetime) -> str:
    return dt.isoformat()


async def report(client: httpx.AsyncClient, h: dict[str, str], campus: dict[str, Any],
                 **over: Any) -> dict[str, Any]:
    body = {"title": "Black backpack", "description": "Black Herschel backpack with textbook",
            "found_location_id": str(campus["lib"]),
            "found_at": iso(datetime.now(UTC) - timedelta(minutes=30)),
            "private_detail": "cactus keychain on the zipper"} | over
    r = await client.post("/api/v1/items", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def test_watch_then_found_item_notifies_owner_exactly_once(
        app_client: httpx.AsyncClient, campus: dict[str, Any]) -> None:
    owner = await make_user(campus, "owner@test.edu")
    finder = await make_user(campus, "finder@test.edu")
    now = datetime.now(UTC)

    r = await app_client.post("/api/v1/lost-reports", headers=owner, json={
        "title": "Black backpack", "description": "lost my black herschel backpack in the library",
        "location_id": str(campus["lib"]), "lost_from": iso(now - timedelta(hours=3)),
        "lost_to": iso(now - timedelta(hours=1))})
    assert r.status_code == 201, r.text
    await run_outbox()

    item = await report(app_client, finder, campus)
    assert item["status"] == "reported"
    await run_outbox()
    # Re-running the job (at-least-once delivery) must not double-notify.
    await tasks.process_found_item({"job_try": 1}, item["id"])

    notes = (await app_client.get("/api/v1/notifications", headers=owner)).json()["items"]
    matches = [n for n in notes if n["kind"] == "possible_match"]
    assert len(matches) == 1
    assert matches[0]["payload"]["found_item_id"] == item["id"]
    # The finder is never matched against their own report.
    assert (await app_client.get("/api/v1/notifications/unread-count",
                                 headers=finder)).json()["unread"] == 0


async def test_assistant_finds_item_and_never_leaks_secret(
        app_client: httpx.AsyncClient, campus: dict[str, Any]) -> None:
    finder = await make_user(campus, "finder@test.edu")
    owner = await make_user(campus, "owner@test.edu")
    item = await report(app_client, finder, campus)
    await run_outbox()

    r = await app_client.post("/api/v1/assistant/chat", headers=owner, json={
        "messages": [{"role": "user", "content": "I lost my black backpack in the library today"}]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["extracted"]["item_type"] == "backpack"
    assert out["matches"] and out["matches"][0]["item"]["id"] == item["id"]
    assert out["watch_draft"]["item_type"] == "backpack"
    assert "cactus" not in r.text  # verification secret must never reach the owner side


async def test_sensitive_item_is_redacted_publicly(
        app_client: httpx.AsyncClient, campus: dict[str, Any]) -> None:
    finder = await make_user(campus, "finder@test.edu")
    other = await make_user(campus, "other@test.edu")
    item = await report(app_client, finder, campus, title="Jane Doe student card",
                        description="Student card 1004567890 for Jane Doe")
    await run_outbox()
    pub = (await app_client.get(f"/api/v1/items/{item['id']}", headers=other)).json()
    assert pub["title"] == "Student / campus card"
    assert pub["description"] is None
    assert "private_detail" not in pub
    mine = (await app_client.get(f"/api/v1/items/{item['id']}", headers=finder)).json()
    assert mine["private_detail"] == "cactus keychain on the zipper"


async def test_full_claim_lifecycle_resolves_watch(
        app_client: httpx.AsyncClient, campus: dict[str, Any]) -> None:
    finder = await make_user(campus, "finder@test.edu")
    owner = await make_user(campus, "owner@test.edu")
    now = datetime.now(UTC)
    watch = (await app_client.post("/api/v1/lost-reports", headers=owner, json={
        "title": "Black backpack", "description": "black herschel backpack",
        "lost_from": iso(now - timedelta(hours=4)), "lost_to": iso(now - timedelta(hours=1))
    })).json()
    item = await report(app_client, finder, campus)
    await run_outbox()

    claim = await app_client.post("/api/v1/claims", headers=owner, json={
        "found_item_id": item["id"], "lost_report_id": watch["id"],
        "proof_text": "There is a small cactus keychain on the zipper"})
    assert claim.status_code == 201, claim.text
    cid = claim.json()["id"]

    queue = (await app_client.get("/api/v1/claims/review", headers=finder)).json()
    assert queue[0]["proof_strength"] == "strong"

    assert (await app_client.post(f"/api/v1/claims/{cid}/approve", headers=finder,
                                  json={"pickup_instructions": "Library steps at 3pm"})
            ).status_code == 200
    # Owner can now see pickup instructions.
    mine = (await app_client.get("/api/v1/claims/mine", headers=owner)).json()
    assert mine[0]["pickup_instructions"] == "Library steps at 3pm"

    assert (await app_client.post(f"/api/v1/claims/{cid}/complete", headers=finder)
            ).status_code == 200
    final = (await app_client.get(f"/api/v1/items/{item['id']}", headers=finder)).json()
    assert final["status"] == "returned"
    assert [e["event_type"] for e in final["custody"]] == [
        "reported", "claim_opened", "claim_approved", "returned"]
    w = (await app_client.get(f"/api/v1/lost-reports/{watch['id']}", headers=owner)).json()
    assert w["status"] == "resolved"


async def test_concurrent_approvals_only_one_wins(
        app_client: httpx.AsyncClient, campus: dict[str, Any]) -> None:
    finder = await make_user(campus, "finder@test.edu")
    a = await make_user(campus, "a@test.edu")
    b = await make_user(campus, "b@test.edu")
    item = await report(app_client, finder, campus)
    await run_outbox()
    ids = []
    for h in (a, b):
        r = await app_client.post("/api/v1/claims", headers=h, json={
            "found_item_id": item["id"], "proof_text": "it is my black backpack honestly"})
        ids.append(r.json()["id"])

    results = await asyncio.gather(*[
        app_client.post(f"/api/v1/claims/{cid}/approve", headers=finder, json={})
        for cid in ids])
    codes = sorted(r.status_code for r in results)
    assert codes == [200, 409], [r.text for r in results]


async def test_desk_receives_item_and_closes_out_expired(
        app_client: httpx.AsyncClient, campus: dict[str, Any]) -> None:
    finder = await make_user(campus, "finder@test.edu")
    desk = await make_user(campus, "desk@test.edu", Role.DESK, desk=True)
    item = await report(app_client, finder, campus)
    await run_outbox()
    r = await app_client.post(f"/api/v1/desk/items/{item['id']}/receive", headers=desk, json={})
    assert r.status_code == 200 and r.json()["holder_type"] == "desk"

    # Donating an AVAILABLE item is illegal: it must expire first.
    r = await app_client.post(f"/api/v1/desk/items/{item['id']}/close", headers=desk,
                              json={"action": "donate"})
    assert r.status_code == 409

    async with get_sessionmaker()() as s:
        await s.execute(text("UPDATE found_items SET expires_at = now() - interval '1 day'"))
        await s.commit()
    assert await tasks.expire_items({}) == 1
    r = await app_client.post(f"/api/v1/desk/items/{item['id']}/close", headers=desk,
                              json={"action": "donate", "note": "campus clothing drive"})
    assert r.status_code == 200 and r.json()["status"] == "donated"
    overview = (await app_client.get("/api/v1/desk/overview", headers=desk)).json()
    assert overview["by_status"]["donated"] == 1


async def test_custody_log_is_append_only(app_client: httpx.AsyncClient,
                                          campus: dict[str, Any]) -> None:
    finder = await make_user(campus, "finder@test.edu")
    await report(app_client, finder, campus)
    async with get_sessionmaker()() as s:
        with pytest.raises(DBAPIError, match="append-only"):
            await s.execute(text("UPDATE custody_events SET note = 'tampered'"))
        await s.rollback()
        with pytest.raises(DBAPIError, match="append-only"):
            await s.execute(text("DELETE FROM custody_events"))


async def test_csrf_header_required_for_cookie_writes(app_client: httpx.AsyncClient,
                                                      campus: dict[str, Any]) -> None:
    r = await app_client.post("/api/v1/notifications/read", json={"all": True},
                              cookies={"cl_session": "x"})
    assert r.status_code == 403


async def test_only_staff_can_browse_all_items(app_client: httpx.AsyncClient,
                                              campus: dict[str, Any]) -> None:
    member = await make_user(campus, "member@test.edu")
    desk = await make_user(campus, "desk@test.edu", Role.DESK, desk=True)
    assert (await app_client.get("/api/v1/items", headers=member)).status_code == 403
    assert (await app_client.get("/api/v1/items", headers=desk)).status_code == 200
