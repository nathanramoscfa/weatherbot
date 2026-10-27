# tests/web/test_event_stream.py
"""Tests for ``GET /api/events`` over a real loopback socket with ``WebServer``."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from http import HTTPStatus

import httpx
from cli_support import MIAMI, add_landmark, quiet_fetcher, recorded_services
from source_support import NOW

from weatherbot.services.config import AppPaths, Settings
from weatherbot.services.events import MAX_SUBSCRIBERS, QUERY_KEYS, BrowserChannel, EventHub
from weatherbot.services.monitor import MonitorService
from weatherbot.services.network import Network
from weatherbot.services.notifications import LogChannel
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.web.app import WebState, create_app
from weatherbot.web.schemas import StreamEvent
from weatherbot.web.server import WebServer

INITIAL_CYCLE_ID = 3


async def _read_next_sse_event(lines_iter: AsyncIterator[str]) -> StreamEvent:
    """Read lines from an ``httpx`` response line iterator until one ``data:`` frame arrives."""
    while True:
        line = await asyncio.wait_for(anext(lines_iter), timeout=5.0)
        if line.startswith("data:"):
            raw = line.removeprefix("data:").strip()
            return StreamEvent.model_validate_json(raw)


async def _assert_stream_hello_and_cycle_events(
    client: httpx.AsyncClient,
    database: Database,
    paths: AppPaths,
    hub: EventHub,
    channels: tuple[LogChannel, BrowserChannel],
) -> None:
    async with client.stream("GET", "/api/events") as response:
        assert response.status_code == HTTPStatus.OK
        assert "text/event-stream" in response.headers["content-type"]
        assert "no-store" in response.headers["cache-control"]
        lines = response.aiter_lines()
        hello = await _read_next_sse_event(lines)
        assert hello.kind == "hello"
        assert hello.started_at == NOW
        assert hello.cycle_id == INITIAL_CYCLE_ID
        assert len(hello.invalidate) == len(QUERY_KEYS)

        monitor = MonitorService(
            database.engine,
            paths=paths,
            settings=Settings(),
            runner="serve",
            network=Network(make_fetcher=quiet_fetcher),
            now=lambda: NOW,
            listeners=(hub.cycle_listener,),
            channels=channels,
        )
        await monitor.run_cycle("startup")

        notif_ev = await _read_next_sse_event(lines)
        cycle_ev = await _read_next_sse_event(lines)
        snap_ev = await _read_next_sse_event(lines)
        assess_ev = await _read_next_sse_event(lines)

        assert [
            notif_ev.kind,
            cycle_ev.kind,
            snap_ev.kind,
            assess_ev.kind,
        ] == ["notification", "cycle", "snapshot", "assessment"]
        assert hello.id < notif_ev.id < cycle_ev.id < snap_ev.id < assess_ev.id
        assert notif_ev.display is True
        assert assess_ev.location == MIAMI


async def _assert_subscriber_cap_and_shutdown(
    client: httpx.AsyncClient,
    hub: EventHub,
    stop: asyncio.Event,
) -> None:
    for _ in range(50):
        if hub.subscriber_count == 0:
            break
        await asyncio.sleep(0.02)
    assert hub.subscriber_count == 0

    async with contextlib.AsyncExitStack() as stack:
        active_iters: list[object] = []
        for _ in range(MAX_SUBSCRIBERS):
            resp = await stack.enter_async_context(client.stream("GET", "/api/events"))
            assert resp.status_code == HTTPStatus.OK
            resp_lines = resp.aiter_lines()
            active_iters.append(resp_lines)
            first = await _read_next_sse_event(resp_lines)
            assert first.kind == "hello"

        assert len(active_iters) == MAX_SUBSCRIBERS
        assert hub.subscriber_count == MAX_SUBSCRIBERS
        seventeenth = await client.get("/api/events")
        assert seventeenth.status_code == HTTPStatus.SERVICE_UNAVAILABLE

    for _ in range(50):
        if hub.subscriber_count == 0:
            break
        await asyncio.sleep(0.02)
    assert hub.subscriber_count == 0

    async with client.stream("GET", "/api/events") as open_resp:
        assert open_resp.status_code == HTTPStatus.OK
        open_lines = open_resp.aiter_lines()
        first_ev = await _read_next_sse_event(open_lines)
        assert first_ev.kind == "hello"

        stop.set()
        remaining = [line async for line in open_lines if line]
        assert remaining == []


def test_event_stream_hello_cycle_events_disconnect_503_limit_and_shutdown() -> None:
    with recorded_services():
        added = add_landmark(MIAMI, "miami-dade")
        assert added.exit_code == 0, added.stderr

        paths = AppPaths.resolve()
        database = open_database(paths, now=lambda: NOW)
        try:

            async def _drive() -> None:
                loop = asyncio.get_running_loop()
                hub = EventHub(
                    loop,
                    now=lambda: NOW,
                    started_at=NOW,
                    newest_cycle_id=INITIAL_CYCLE_ID,
                )
                channels = (LogChannel(), BrowserChannel(hub, enabled=True))
                state = WebState(
                    database=database,
                    paths=paths,
                    settings=Settings(),
                    clock=lambda: NOW,
                    started_at=NOW,
                    hub=hub,
                    channels=channels,
                    network=Network(make_fetcher=quiet_fetcher),
                )
                web_server = WebServer(
                    create_app(state),
                    host="127.0.0.1",
                    port=0,
                    before_stop=(hub.close,),
                )
                stop = asyncio.Event()
                serve_task = asyncio.create_task(web_server.serve(stop))
                await asyncio.wait_for(web_server.started.wait(), timeout=5.0)

                async with httpx.AsyncClient(
                    base_url=web_server.address,
                    trust_env=False,
                    timeout=5.0,
                ) as client:
                    await _assert_stream_hello_and_cycle_events(
                        client,
                        database,
                        paths,
                        hub,
                        channels,
                    )
                    await _assert_subscriber_cap_and_shutdown(client, hub, stop)

                await asyncio.wait_for(serve_task, timeout=5.0)

            asyncio.run(_drive())
        finally:
            database.close()
