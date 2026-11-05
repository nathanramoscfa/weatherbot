# tests/web/test_retention_routes.py
"""Tests for ``GET /api/retention`` and ``POST /api/retention/run``."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING

from cli_support import (
    MIAMI,
    add_landmark,
    quiet_fetcher,
    recorded_services,
)
from fastapi.testclient import TestClient
from source_support import NOW

from weatherbot.services.config import AppPaths, Settings
from weatherbot.services.locks import ProcessLock
from weatherbot.services.monitor import MonitorService
from weatherbot.services.network import Network
from weatherbot.services.persistence.database import open_database
from weatherbot.web.app import WebState, create_app

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

WRITE_HEADERS = {"Origin": "http://127.0.0.1:8765"}
CROSS_SITE_HEADERS = {"Origin": "https://evil.example"}


@contextmanager
def _make_state(
    *,
    now: datetime = NOW,
    settings: Settings | None = None,
    environ: Mapping[str, str] | None = None,
) -> Generator[WebState]:
    paths = AppPaths.resolve()
    with open_database(paths, now=lambda: now) as database:
        yield WebState(
            database=database,
            paths=paths,
            settings=settings or Settings(),
            clock=lambda: now,
            started_at=NOW,
            environ={} if environ is None else environ,
        )


def test_get_retention_and_post_retention_run_validate_and_prune() -> None:
    base = NOW
    current_now = base + timedelta(days=90)
    paths = AppPaths.resolve()

    with recorded_services():
        assert add_landmark(MIAMI, "miami-dade").exit_code == 0
        with open_database(paths) as db:
            for instant in (base, base + timedelta(minutes=30), current_now):
                monitor = MonitorService(
                    db.engine,
                    paths=paths,
                    settings=Settings(),
                    runner="check-once",
                    network=Network(
                        make_fetcher=lambda client, store, t=instant: quiet_fetcher(
                            client, store, now=t
                        )
                    ),
                    now=lambda t=instant: t,
                )
                asyncio.run(monitor.run_cycle("manual"))

    with _make_state(now=current_now) as state:
        client = TestClient(create_app(state), base_url="http://127.0.0.1:8765")

        # 1. Default GET /api/retention (history_days = 0 -> 365-day preview)
        resp = client.get("/api/retention")
        assert resp.status_code == HTTPStatus.OK
        data = resp.json()
        assert data["database_bytes"] > 0
        assert data["setting"]["history_days"] == 0
        assert data["setting"]["editable"] is True
        assert data["last_run"] is None
        assert data["plan"]["days"] == 365  # noqa: PLR2004
        assert data["plan"]["total_rows"] == 0

        # 2. Preview for ?days=30 shows the Day 0 snapshot and cycle will be removed
        resp30 = client.get("/api/retention?days=30")
        assert resp30.status_code == HTTPStatus.OK
        plan30 = resp30.json()["plan"]
        assert plan30["days"] == 30  # noqa: PLR2004
        assert plan30["counts"]["snapshots"] == 1
        assert plan30["total_rows"] > 0

        # 3. Out-of-range ?days= -> 422
        assert client.get("/api/retention?days=29").status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert client.get("/api/retention?days=3651").status_code == HTTPStatus.UNPROCESSABLE_ENTITY

        # 4. Cross-site POST /api/retention/run -> 403
        cross = client.post(
            "/api/retention/run",
            headers=CROSS_SITE_HEADERS,
            json={"cutoff": plan30["cutoff"]},
        )
        assert cross.status_code == HTTPStatus.FORBIDDEN

        # 5. Out-of-range cutoff on POST /api/retention/run -> 422
        bad_cutoff = client.post(
            "/api/retention/run",
            headers=WRITE_HEADERS,
            json={"cutoff": (current_now - timedelta(days=5)).isoformat()},
        )
        assert bad_cutoff.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

        # 6. Held retention.lock -> 409
        ret_lock = ProcessLock(state.paths.retention_lock_path)
        assert ret_lock.try_acquire()
        try:
            busy = client.post(
                "/api/retention/run",
                headers=WRITE_HEADERS,
                json={"cutoff": plan30["cutoff"]},
            )
        finally:
            ret_lock.release()
        assert busy.status_code == HTTPStatus.CONFLICT
        assert "already running" in busy.json()["detail"]

        # 7. Valid POST /api/retention/run -> 202 Accepted, runs background task, records last_run
        run_resp = client.post(
            "/api/retention/run",
            headers=WRITE_HEADERS,
            json={"cutoff": plan30["cutoff"]},
        )
        assert run_resp.status_code == HTTPStatus.ACCEPTED
        assert run_resp.json()["status"] == "accepted"

        after = client.get("/api/retention?days=30").json()
        assert after["last_run"] is not None
        assert after["last_run"]["status"] == "complete"
        assert after["last_run"]["total_deleted"] == plan30["total_rows"]
        assert after["plan"]["total_rows"] == 0
