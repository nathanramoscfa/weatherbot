# tests/web/test_replay_writes_nothing.py
"""Proof that scrubbing a storm writes no database rows, publishes no events, and calls no AI."""

import asyncio
from collections.abc import Mapping
from datetime import timedelta
from http import HTTPStatus
from urllib.parse import quote

import httpx
from cli_support import CORPUS, NASSAU, add_landmark, recorded_services, run
from source_support import NOW
from sqlalchemy import text
from sqlalchemy.engine import Engine

from weatherbot.services.config import AppPaths, load_settings, setting_origins
from weatherbot.services.events import EventHub, EventKind
from weatherbot.services.notifications import Delivery, StoredNotification
from weatherbot.services.persistence.database import open_database
from weatherbot.services.replay import ReplayCorpus
from weatherbot.web.app import WebState, create_app
from weatherbot.web.map_layers import SNAPSHOT_CACHE
from weatherbot.web.schemas import ReplayTimelineResponse

TABLES = (
    "snapshots",
    "assessments",
    "notifications",
    "notification_deliveries",
    "ai_calls",
    "ai_outputs",
)


class _RecordingChannel:
    """Test notification channel that records every delivery attempt."""

    def __init__(self) -> None:
        self.delivered: list[StoredNotification] = []

    @property
    def name(self) -> str:
        return "toast"

    @property
    def interrupts(self) -> bool:
        return True

    async def deliver(self, notification: StoredNotification) -> Delivery:
        self.delivered.append(notification)
        return Delivery(result="delivered", detail="recorded")


def _table_signatures(engine: Engine) -> dict[str, tuple[int, str | None]]:
    signatures: dict[str, tuple[int, str | None]] = {}
    with engine.connect() as conn:
        for table in TABLES:
            row = conn.execute(
                text(f"SELECT COUNT(*), MAX(id) FROM {table}")  # noqa: S608 - fixed table constant
            ).one()
            signatures[table] = (int(row[0]), str(row[1]) if row[1] is not None else None)
    return signatures


def test_scrubbing_an_entire_storm_writes_publishes_and_sends_nothing() -> None:
    with recorded_services():
        assert add_landmark(NASSAU, "nassau").exit_code == 0
        assert run(["check", "--once"]).exit_code == 0

    SNAPSHOT_CACHE.clear()
    paths = AppPaths.resolve()
    corpus = ReplayCorpus.open(CORPUS)
    hub = EventHub()
    published: list[EventKind] = []
    original_publish = hub.publish

    def _spy_publish(kind: EventKind, data: Mapping[str, object] | None = None) -> None:
        published.append(kind)
        original_publish(kind, data)

    hub.publish = _spy_publish  # type: ignore[method-assign]
    channel = _RecordingChannel()

    with open_database(paths, now=lambda: NOW) as database:
        before = _table_signatures(database.engine)
        state = WebState(
            database=database,
            paths=paths,
            settings=load_settings(paths),
            setting_origins=setting_origins(paths),
            clock=lambda: NOW,
            started_at=NOW - timedelta(minutes=5),
            corpus=corpus,
            hub=hub,
            channels=(channel,),
        )
        app = create_app(state)

        async def _scrub_storm() -> None:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                storms_res = await client.get("/api/replay")
                assert storms_res.status_code == HTTPStatus.OK

                tl_res = await client.get(f"/api/replay/AL142024/timeline?location={quote(NASSAU)}")
                assert tl_res.status_code == HTTPStatus.OK
                timeline = ReplayTimelineResponse.model_validate_json(tl_res.text)
                assert len(timeline.steps) == 41  # noqa: PLR2004

                for step in timeline.steps:
                    map_res = await client.get(f"/api/replay/AL142024/{step.advisory_id}")
                    assert map_res.status_code == HTTPStatus.OK
                    assess_res = await client.get(
                        f"/api/replay/AL142024/{step.advisory_id}/assessment"
                        f"?location={quote(NASSAU)}"
                    )
                    assert assess_res.status_code == HTTPStatus.OK

        asyncio.run(_scrub_storm())
        after = _table_signatures(database.engine)

    assert after == before
    assert published == []
    assert channel.delivered == []
