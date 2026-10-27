# tests/live/test_web_live.py
"""Live web test: ``POST /api/cycles`` and ``GET /api/events`` against the live services.

Adds both public landmarks in the test's temporary data directory, starts ``serve``'s web
app over a loopback socket with the real fetcher, opens ``GET /api/events``, triggers a
cycle through ``POST /api/cycles``, and verifies the stream delivers ``hello``, ``cycle``,
``snapshot``, and ``assessment`` events for both landmarks. Marked ``live`` and
``enable_socket``: runs only with ``pytest -m live``.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from http import HTTPStatus

import httpx
import pytest
from cli_support import MIAMI, NASSAU, landmark, run

from weatherbot.cli.runtime import Runtime
from weatherbot.cli.serve import serve_channels
from weatherbot.services.config import AppPaths, Settings
from weatherbot.services.events import BrowserChannel, EventHub
from weatherbot.services.monitor import MonitorService
from weatherbot.services.network import Network
from weatherbot.services.notifications import LogChannel
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.services.persistence.repositories import CycleRepository
from weatherbot.web.app import WebState, create_app
from weatherbot.web.schemas import StreamEvent, TriggerCycleResponse
from weatherbot.web.server import WebServer

pytestmark = [pytest.mark.live, pytest.mark.enable_socket]

LIVE = Runtime(terminal=False)
"""The real fetcher: the register's pacing, retries, and timeouts."""

_SSE_TIMEOUT_S = 90.0
_EXPECTED_LOCATIONS = 2


async def _next_sse_event(lines_iter: AsyncIterator[str]) -> StreamEvent:
    """Read lines from an ``httpx`` stream iterator until the next ``data:`` frame arrives."""
    while True:
        line = await asyncio.wait_for(anext(lines_iter), timeout=_SSE_TIMEOUT_S)
        if line.startswith("data:"):
            raw = line.removeprefix("data:").strip()
            return StreamEvent.model_validate_json(raw)


async def _drive_live_cycle(database: Database, paths: AppPaths, settings: Settings) -> None:
    started_at = datetime.now(UTC)
    loop = asyncio.get_running_loop()
    hub = EventHub(loop, started_at=started_at)
    channels = (
        LogChannel(),
        BrowserChannel(hub, enabled=settings.notifications.browser),
    )
    network = Network(timeout_seconds=settings.http.timeout_seconds)
    monitor = MonitorService(
        database.engine,
        paths=paths,
        settings=settings,
        runner="serve",
        network=network,
        listeners=(hub.cycle_listener,),
        channels=channels,
    )
    state = WebState(
        database=database,
        paths=paths,
        settings=settings,
        started_at=started_at,
        hub=hub,
        channels=channels,
        network=network,
        request_cycle=lambda: monitor.run_cycle("manual"),
    )
    web_server = WebServer(
        create_app(state),
        host="127.0.0.1",
        port=0,
        before_stop=(hub.close,),
    )
    stop = asyncio.Event()
    serve_task = asyncio.create_task(web_server.serve(stop))
    await asyncio.wait_for(web_server.started.wait(), timeout=10.0)
    base_url = web_server.address

    try:
        async with (
            httpx.AsyncClient(
                base_url=base_url,
                trust_env=False,
                timeout=_SSE_TIMEOUT_S,
            ) as client,
            client.stream("GET", "/api/events") as stream,
        ):
            assert stream.status_code == HTTPStatus.OK
            lines = stream.aiter_lines()
            hello = await _next_sse_event(lines)
            assert hello.kind == "hello"

            triggered = await client.post(
                "/api/cycles",
                json={},
                headers={"Origin": base_url},
            )
            assert triggered.status_code == HTTPStatus.ACCEPTED
            body = TriggerCycleResponse.model_validate(triggered.json())
            assert body.status == "accepted"

            received: list[StreamEvent] = []
            assessed_locations: set[str] = set()
            while len(assessed_locations) < _EXPECTED_LOCATIONS:
                event = await _next_sse_event(lines)
                received.append(event)
                if event.kind == "assessment" and event.location is not None:
                    assessed_locations.add(event.location)

            kinds = [event.kind for event in received]
            assert "cycle" in kinds
            assert "snapshot" in kinds
            assert assessed_locations == {MIAMI, NASSAU}
            cycle_event = next(e for e in received if e.kind == "cycle")
            snapshot_event = next(e for e in received if e.kind == "snapshot")
            assert cycle_event.trigger == "manual"
            assert cycle_event.status == "complete"
            assert cycle_event.cycle_id is not None
            assert snapshot_event.snapshot_id is not None
            assert kinds.index("cycle") < kinds.index("snapshot")

            stored = CycleRepository(database.engine).get(cycle_event.cycle_id)
            assert stored is not None
            assert stored.trigger == "manual"
            assert stored.status == "complete"
    finally:
        stop.set()
        await asyncio.wait_for(serve_task, timeout=10.0)


def test_post_cycles_streams_live_cycle_snapshot_and_assessment_events() -> None:
    for name, key in ((MIAMI, "miami-dade"), (NASSAU, "nassau")):
        lat, lon = landmark(key)
        added = run(["locations", "add", name, "--lat", lat, "--lon", lon], LIVE)
        assert added.exit_code == 0, added.stderr

    paths = AppPaths.resolve()
    settings = Settings()
    database = open_database(paths)
    try:
        asyncio.run(_drive_live_cycle(database, paths, settings))
    finally:
        database.close()
    assert serve_channels is not None
