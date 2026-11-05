# tests/web/test_timeline_before.py
"""Tests for ``GET /api/timeline?before=`` cursor pagination across shared cycle instants."""

import asyncio
from datetime import timedelta
from http import HTTPStatus
from typing import Final
from urllib.parse import quote

import httpx
import pytest
from cli_support import (
    MIAMI,
    NASSAU,
    add_landmark,
    county_statement,
    recorded_services,
    run,
    runtime,
)
from source_support import NOW

from weatherbot.services.config import AppPaths, load_settings, setting_origins
from weatherbot.services.notifications import NotificationService
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.services.persistence.repositories import AssessmentRepository
from weatherbot.web.app import WebState, create_app
from weatherbot.web.schemas import TimelineEntryResponse, TimelineResponse

MIN_EXPECTED_ENTRIES: Final = 4
EXPECTED_MIAMI_HISTORY: Final = 2


def _seed_timeline_history() -> None:
    later = NOW + timedelta(minutes=1)
    with recorded_services(overrides=county_statement()):
        assert add_landmark(MIAMI, "miami-dade", "--polygon", "forecast").exit_code == 0
        assert add_landmark(NASSAU, "nassau").exit_code == 0
        assert run(["locations", "evacuation", MIAMI, "on"]).exit_code == 0
        assert run(["check", "--once"]).exit_code == 0
        assert run(["locations", "evacuation", MIAMI, "off"], runtime(now=later)).exit_code == 0
        assert run(["check", "--once"], runtime(now=later)).exit_code == 0


def _open_web_state() -> tuple[WebState, Database]:
    paths = AppPaths.resolve()
    database = open_database(paths, now=lambda: NOW)
    state = WebState(
        database=database,
        paths=paths,
        settings=load_settings(paths),
        setting_origins=setting_origins(paths),
        clock=lambda: NOW + timedelta(minutes=2),
        started_at=NOW - timedelta(minutes=10),
    )
    return state, database


def test_timeline_before_cursor_pages_across_shared_cycle_instants_without_skipping() -> None:
    _seed_timeline_history()
    state, database = _open_web_state()
    try:
        app = create_app(state)

        async def _collect_pages() -> tuple[TimelineResponse, list[TimelineEntryResponse]]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                full_res = await client.get("/api/timeline?limit=50")
                assert full_res.status_code == HTTPStatus.OK
                full_doc = TimelineResponse.model_validate(full_res.json())

                paged: list[TimelineEntryResponse] = []
                cursor: str | None = None
                for _ in range(len(full_doc.entries) + 2):
                    url = "/api/timeline?limit=1"
                    if cursor is not None:
                        url = f"{url}&before={quote(cursor)}"
                    res = await client.get(url)
                    assert res.status_code == HTTPStatus.OK
                    doc = TimelineResponse.model_validate(res.json())
                    paged.extend(doc.entries)
                    cursor = doc.next_before
                    if cursor is None:
                        break
                return full_doc, paged

        full_doc, paged_entries = asyncio.run(_collect_pages())
    finally:
        database.close()

    assert full_doc.next_before is None
    assert len(full_doc.entries) >= MIN_EXPECTED_ENTRIES
    # Two assessments in the first cycle share an identical occurred_at instant with
    # Miami-Dade's level-4 notification; paging 1-by-1 must visit every single one in order.
    assert [(e.kind, e.id, e.occurred_at) for e in paged_entries] == [
        (e.kind, e.id, e.occurred_at) for e in full_doc.entries
    ]


def test_timeline_before_cursor_rejects_malformed_cursors_without_echoing_input() -> None:
    with recorded_services():
        assert add_landmark(MIAMI, "miami-dade", "--polygon", "forecast").exit_code == 0
    state, database = _open_web_state()
    bad_inputs = (
        "BadCursorProbeValue123",
        "not-a-date|assessment|1",
        "2026-10-13T01:30:00|assessment|1",
        "2026-10-13T01:30:00Z|unknown_kind|1",
        "2026-10-13T01:30:00Z|assessment|0",
        "2026-10-13T01:30:00Z|assessment|notanint",
    )
    try:
        app = create_app(state)

        async def _exercise() -> list[httpx.Response]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                return [
                    await client.get(f"/api/timeline?before={quote(raw)}") for raw in bad_inputs
                ]

        responses = asyncio.run(_exercise())
    finally:
        database.close()

    for raw, res in zip(bad_inputs, responses, strict=True):
        assert res.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert res.json() == {"detail": "invalid timeline cursor: before"}
        assert raw not in res.text


def test_repository_history_and_notification_recent_support_datetime_and_tuple_before_bounds() -> (
    None
):
    _seed_timeline_history()
    paths = AppPaths.resolve()
    settings = load_settings(paths)
    with open_database(paths, now=lambda: NOW) as database:
        assessment_repo = AssessmentRepository(database.engine, now=lambda: NOW)
        notif_service = NotificationService(database.engine, settings=settings, now=lambda: NOW)

        all_miami = assessment_repo.history(MIAMI, 10)
        assert len(all_miami) == EXPECTED_MIAMI_HISTORY
        newest, oldest = all_miami[0], all_miami[1]

        by_tuple = assessment_repo.history(MIAMI, 10, before=(newest.assessment.as_of, newest.id))
        assert [item.id for item in by_tuple] == [oldest.id]

        by_dt = assessment_repo.history(MIAMI, 10, before=newest.assessment.as_of)
        assert [item.id for item in by_dt] == [oldest.id]

        all_notifs = notif_service.recent(limit=10)
        assert len(all_notifs) >= 1
        top_notif = all_notifs[0]
        after_top = notif_service.recent(limit=10, before=(top_notif.created_at, top_notif.id))
        assert all(item.id != top_notif.id for item in after_top)
        after_dt = notif_service.recent(limit=10, before=top_notif.created_at)
        assert all(item.created_at < top_notif.created_at for item in after_dt)
        with pytest.raises(ValueError, match="at least 1"):
            notif_service.recent(limit=0)
