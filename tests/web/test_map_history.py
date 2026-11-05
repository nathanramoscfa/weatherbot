# tests/web/test_map_history.py
"""Tests for ``advisory_steps``, ``GET /api/map/advisories``, and ``GET /api/map?snapshot_id=``."""

import asyncio
from datetime import timedelta
from http import HTTPStatus
from uuid import UUID, uuid4

import httpx
import pytest
from cli_support import MIAMI, NASSAU, add_landmark, county_statement, recorded_services, run
from source_support import NOW

from weatherbot.models import AdvisoryNumber, Snapshot
from weatherbot.services.config import AppPaths, load_settings, setting_origins
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import AssessmentRepository, SnapshotRepository
from weatherbot.web.app import WebState, create_app
from weatherbot.web.map_layers import SNAPSHOT_CACHE
from weatherbot.web.schemas import (
    ALL_MAP_LAYERS,
    STORED_ADVISORY_MAP_LAYERS,
    MapAdvisoriesResponse,
    MapResponse,
)


def test_advisory_steps_deduplicates_by_storm_and_advisory_without_loading_geometry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with recorded_services(overrides=county_statement()):
        assert add_landmark(MIAMI, "miami-dade", "--polygon", "forecast").exit_code == 0
        assert add_landmark(NASSAU, "nassau").exit_code == 0
        assert run(["check", "--once"]).exit_code == 0

    paths = AppPaths.resolve()
    with open_database(paths, now=lambda: NOW) as database:
        repo = SnapshotRepository(database.engine)
        first_id = repo.latest_id()
        assert first_id is not None
        first_snap = repo.load(first_id)
        assert first_snap is not None

        # Second snapshot with the SAME advisory ("15") at a later completed_at:
        # advisory_steps must pick the newest snapshot for (EP202026, 15).
        second_id = uuid4()
        second_snap = first_snap.model_copy(
            update={
                "snapshot_id": second_id,
                "started_at": NOW + timedelta(minutes=10),
                "completed_at": NOW + timedelta(minutes=10),
            }
        )
        repo.save(second_snap)

        # Third snapshot with a NEW advisory ("16") at an even later completed_at.
        storm0 = first_snap.storms[0]
        assert storm0.summary is not None
        first_adv = str(storm0.summary.public_advisory.advisory)
        pub16 = storm0.summary.public_advisory.model_copy(
            update={
                "advisory": AdvisoryNumber.parse("16"),
                "issued_at": NOW + timedelta(hours=3),
            }
        )
        summary16 = storm0.summary.model_copy(update={"public_advisory": pub16})
        third_id = uuid4()
        third_snap = first_snap.model_copy(
            update={
                "snapshot_id": third_id,
                "started_at": NOW + timedelta(minutes=20),
                "completed_at": NOW + timedelta(minutes=20),
                "storms": (storm0.model_copy(update={"summary": summary16}),),
            }
        )
        repo.save(third_snap)

        def fail_if_load_called(_self: SnapshotRepository, _snapshot_id: UUID) -> Snapshot | None:
            msg = "advisory_steps must not call SnapshotRepository.load"
            raise AssertionError(msg)

        monkeypatch.setattr(SnapshotRepository, "load", fail_if_load_called)
        steps = repo.advisory_steps(limit=96)

    assert len(steps) == 2  # noqa: PLR2004
    assert (steps[0].snapshot_id, steps[0].advisory) == (third_id, "16")
    assert (steps[1].snapshot_id, steps[1].advisory) == (second_id, first_adv)


def test_map_snapshot_id_uses_cache_stored_assessments_and_returns_generic_404_on_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with recorded_services(overrides=county_statement()):
        assert add_landmark(MIAMI, "miami-dade", "--polygon", "forecast").exit_code == 0
        assert run(["locations", "evacuation", MIAMI, "on"]).exit_code == 0
        assert run(["check", "--once"]).exit_code == 0
        assert run(["locations", "evacuation", MIAMI, "off"]).exit_code == 0
        assert run(["check", "--once"]).exit_code == 0
        # Add Nassau AFTER both snapshots so the earlier snapshots have no assessment for Nassau.
        assert add_landmark(NASSAU, "nassau").exit_code == 0

    SNAPSHOT_CACHE.clear()
    paths = AppPaths.resolve()
    database = open_database(paths, now=lambda: NOW)
    try:
        assess_repo = AssessmentRepository(database.engine)
        history_miami = assess_repo.history(MIAMI, limit=10)
        assert len(history_miami) == 2  # noqa: PLR2004
        older_stored = history_miami[1]
        assert int(history_miami[0].assessment.level) < int(older_stored.assessment.level)
        older_snapshot_id = older_stored.assessment.snapshot_id
        for_older = assess_repo.for_snapshot(older_snapshot_id)
        assert set(for_older) == {MIAMI}
        assert int(for_older[MIAMI].assessment.level) == int(older_stored.assessment.level)

        load_calls: list[UUID] = []
        original_load = SnapshotRepository.load

        def counting_load(self: SnapshotRepository, snapshot_id: UUID) -> Snapshot | None:
            load_calls.append(snapshot_id)
            return original_load(self, snapshot_id)

        monkeypatch.setattr(SnapshotRepository, "load", counting_load)

        app = create_app(
            WebState(
                database=database,
                paths=paths,
                settings=load_settings(paths),
                setting_origins=setting_origins(paths),
                clock=lambda: NOW,
                started_at=NOW - timedelta(minutes=10),
            )
        )
        unknown_id = uuid4()

        async def _exercise() -> dict[str, httpx.Response]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                return {
                    "advisories": await client.get("/api/map/advisories?limit=10"),
                    "bad_limit": await client.get("/api/map/advisories?limit=201"),
                    "latest": await client.get("/api/map"),
                    "past1": await client.get(f"/api/map?snapshot_id={older_snapshot_id}"),
                    "past2": await client.get(f"/api/map?snapshot_id={older_snapshot_id}"),
                    "unknown": await client.get(f"/api/map?snapshot_id={unknown_id}"),
                }

        res = asyncio.run(_exercise())
    finally:
        database.close()

    assert res["advisories"].status_code == HTTPStatus.OK
    adv_doc = MapAdvisoriesResponse.model_validate_json(res["advisories"].text)
    assert (adv_doc.limit, len(adv_doc.steps) >= 1) == (10, True)
    assert res["bad_limit"].status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert res["unknown"].status_code == HTTPStatus.NOT_FOUND
    assert res["unknown"].json() == {"detail": "unknown snapshot parameter: snapshot_id"}
    assert str(unknown_id) not in res["unknown"].text

    latest_map = MapResponse.model_validate_json(res["latest"].text)
    past_map = MapResponse.model_validate_json(res["past1"].text)
    assert latest_map.available_layers == ALL_MAP_LAYERS
    assert past_map.available_layers == STORED_ADVISORY_MAP_LAYERS
    # SnapshotRepository.load was called once for older_snapshot_id (past2 hit cache).
    assert load_calls.count(older_snapshot_id) == 1
    # Miami-Dade carries its older assessment level; Nassau (added later) has level=None.
    point_levels = {
        str(f.properties["name"]): f.properties["level"]
        for f in past_map.locations.features
        if f.geometry.type == "Point"
    }
    assert point_levels[MIAMI] == int(older_stored.assessment.level)
    assert point_levels[NASSAU] is None
