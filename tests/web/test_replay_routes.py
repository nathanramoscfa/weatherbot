# tests/web/test_replay_routes.py
"""Tests for ``ReplayCorpus.advisories``/``snapshot``, ``/api/replay``, and ``serve --corpus``."""

import asyncio
from datetime import timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Final

import httpx
import pytest
from cli_support import CORPUS, MIAMI, add_landmark, quiet_fetcher, recorded_services, run, runtime
from source_support import NOW

from weatherbot.cli.runtime import Runtime
from weatherbot.services.config import AppPaths, load_settings, setting_origins
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import AssessmentRepository
from weatherbot.services.replay import ReplayCorpus, ReplayError
from weatherbot.web.app import WebState, create_app
from weatherbot.web.map_layers import SNAPSHOT_CACHE
from weatherbot.web.schemas import MapResponse, ReplayStormsResponse

USAGE: Final = 2


def test_replay_corpus_advisories_and_snapshot_match_streamed_snapshots_for_irma() -> None:
    corpus = ReplayCorpus.open(CORPUS)
    advisories = corpus.advisories("AL112017")
    assert len(advisories) > 0
    assert "026A" in advisories

    streamed = list(corpus.snapshots("AL112017"))
    assert len(streamed) == len(advisories)

    for adv, expected in zip(advisories, streamed, strict=True):
        single = corpus.snapshot("AL112017", adv)
        assert single == expected

    with pytest.raises(ReplayError):
        corpus.advisories("AL999999")

    with pytest.raises(ReplayError):
        corpus.snapshot("AL112017", "999Z")


def test_replay_routes_list_storms_and_serve_native_crs_layers_without_storing() -> None:
    with recorded_services():
        assert add_landmark(MIAMI, "miami-dade", "--polygon", "forecast").exit_code == 0

    SNAPSHOT_CACHE.clear()
    paths = AppPaths.resolve()
    corpus = ReplayCorpus.open(CORPUS)
    database = open_database(paths, now=lambda: NOW)
    try:
        state = WebState(
            database=database,
            paths=paths,
            settings=load_settings(paths),
            setting_origins=setting_origins(paths),
            clock=lambda: NOW,
            started_at=NOW - timedelta(minutes=10),
            corpus=corpus,
        )
        app = create_app(state)

        async def _query() -> tuple[
            httpx.Response,
            httpx.Response,
            httpx.Response,
            httpx.Response,
            httpx.Response,
        ]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                health_res = await client.get("/api/health")
                list_res = await client.get("/api/replay")
                layer_res = await client.get("/api/replay/AL112017/026A")
                bad_storm = await client.get("/api/replay/AL999999/026A")
                bad_adv = await client.get("/api/replay/AL112017/999Z")
                return health_res, list_res, layer_res, bad_storm, bad_adv

        health_res, list_res, layer_res, bad_storm, bad_adv = asyncio.run(_query())
        assert AssessmentRepository(database.engine).latest(MIAMI) is None
    finally:
        database.close()

    assert health_res.json()["corpus"] is True
    assert list_res.status_code == HTTPStatus.OK
    storms_doc = ReplayStormsResponse.model_validate_json(list_res.text)
    irma = next(s for s in storms_doc.storms if s.atcf_id == "AL112017")
    assert irma.name == "Irma"
    assert irma.advisory_count == len(irma.advisories)
    assert "026A" in irma.advisories

    assert layer_res.status_code == HTTPStatus.OK
    map_doc = MapResponse.model_validate_json(layer_res.text)
    assert map_doc.origin == "replay"
    assert len(map_doc.storms) == 1
    storm_layer = map_doc.storms[0]
    assert storm_layer.atcf_id == "AL112017"
    assert storm_layer.cone is not None
    assert storm_layer.cone.crs.name == "native"
    assert storm_layer.cone.crs.datum == "D_Sphere"
    assert storm_layer.track is not None
    assert storm_layer.track.crs.name == "native"
    assert storm_layer.forecast_points.crs.name == "native"
    assert storm_layer.watch_warnings.crs.name == "native"
    # Locations layer is included with the stored locations in EPSG:4326.
    assert map_doc.locations.crs.name == "EPSG:4326"
    assert any(f.properties["name"] == MIAMI for f in map_doc.locations.features)

    assert bad_storm.status_code == HTTPStatus.NOT_FOUND
    assert "AL999999" not in bad_storm.text
    assert bad_adv.status_code == HTTPStatus.NOT_FOUND
    assert "999Z" not in bad_adv.text


def test_replay_routes_answer_404_when_no_corpus_is_configured() -> None:
    SNAPSHOT_CACHE.clear()
    paths = AppPaths.resolve()
    database = open_database(paths, now=lambda: NOW)
    try:
        state = WebState(
            database=database,
            paths=paths,
            settings=load_settings(paths),
            setting_origins=setting_origins(paths),
            clock=lambda: NOW,
            started_at=NOW - timedelta(minutes=10),
            corpus=None,
        )
        app = create_app(state)

        async def _query() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                return (
                    await client.get("/api/health"),
                    await client.get("/api/replay"),
                    await client.get("/api/replay/AL112017/026A"),
                )

        health_res, list_res, adv_res = asyncio.run(_query())
    finally:
        database.close()

    assert health_res.json()["corpus"] is False
    assert list_res.status_code == HTTPStatus.NOT_FOUND
    assert adv_res.status_code == HTTPStatus.NOT_FOUND


def test_serve_corpus_flag_exits_2_on_non_corpus_directory_and_opens_valid_corpus(
    tmp_path: Path,
) -> None:
    not_a_corpus = tmp_path / "not-a-corpus"
    not_a_corpus.mkdir()

    bad = run(["serve", "--corpus", str(not_a_corpus)])
    assert bad.exit_code == USAGE

    opened: list[str] = []
    corpus_flag: list[bool] = []
    replay_count: list[int] = []

    async def _query_then_stop(_seconds: float) -> None:
        async with httpx.AsyncClient(trust_env=False, timeout=2.0) as client:
            h = await client.get(f"{opened[0]}/api/health")
            r = await client.get(f"{opened[0]}/api/replay")
            corpus_flag.append(bool(h.json()["corpus"]))
            replay_count.append(len(r.json()["storms"]))
        raise KeyboardInterrupt

    with recorded_services() as router:
        router.route(host="127.0.0.1").pass_through()
        add_landmark(MIAMI, "miami-dade")
        base = runtime(now=NOW)
        rt = Runtime(
            environ=base.environ,
            make_fetcher=quiet_fetcher,
            make_toast=base.make_toast,
            identity=base.identity,
            task_runner=base.task_runner,
            windows=base.windows,
            open_browser=opened.append,
            now=lambda: NOW,
            sleep=_query_then_stop,
            terminal=False,
        )
        ok = run(["serve", "--open", "--corpus", str(CORPUS)], rt)

    assert ok.exit_code == 0, ok.stderr
    assert corpus_flag == [True]
    assert replay_count[0] >= 1


def test_invalid_configured_web_corpus_logs_warning_and_keeps_serve_running(
    tmp_path: Path,
) -> None:
    bad_dir = tmp_path / "bad-configured-corpus"
    paths = AppPaths.resolve()
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    paths.settings_path.write_text(
        f'[web]\ncorpus = "{bad_dir.as_posix()}"\n',
        encoding="utf-8",
    )

    opened: list[str] = []
    corpus_flag: list[bool] = []
    replay_status: list[int] = []

    async def _query_then_stop(_seconds: float) -> None:
        async with httpx.AsyncClient(trust_env=False, timeout=2.0) as client:
            h = await client.get(f"{opened[0]}/api/health")
            r = await client.get(f"{opened[0]}/api/replay")
            corpus_flag.append(bool(h.json()["corpus"]))
            replay_status.append(r.status_code)
        raise KeyboardInterrupt

    with recorded_services() as router:
        router.route(host="127.0.0.1").pass_through()
        add_landmark(MIAMI, "miami-dade")
        base = runtime(now=NOW)
        rt = Runtime(
            environ=base.environ,
            make_fetcher=quiet_fetcher,
            make_toast=base.make_toast,
            identity=base.identity,
            task_runner=base.task_runner,
            windows=base.windows,
            open_browser=opened.append,
            now=lambda: NOW,
            sleep=_query_then_stop,
            terminal=False,
        )
        ok = run(["serve", "--open"], rt)

    assert ok.exit_code == 0, ok.stderr
    assert corpus_flag == [False]
    assert replay_status == [HTTPStatus.NOT_FOUND]
