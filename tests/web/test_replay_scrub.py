# tests/web/test_replay_scrub.py
"""Tests for ``GET /api/replay/{atcf_id}/timeline`` and ``/assessment`` vs the eight goldens."""

import asyncio
from datetime import timedelta
from http import HTTPStatus
from typing import cast
from urllib.parse import quote

import httpx
import pytest
from cli_support import CORPUS, MIAMI, NASSAU, add_landmark, recorded_services, run
from source_support import NOW

import build_goldens
from ladder_data import GOLDENS, utc
from weatherbot.services.config import AppPaths, load_settings, setting_origins
from weatherbot.services.persistence.database import open_database
from weatherbot.services.replay import ReplayCorpus
from weatherbot.web.app import WebState, create_app
from weatherbot.web.map_layers import SNAPSHOT_CACHE
from weatherbot.web.schemas import (
    MapResponse,
    ReplayAssessmentResponse,
    ReplayTimelineResponse,
)

LANDMARK_BY_KEY = {
    "miami-dade": MIAMI,
    "nassau": NASSAU,
}
GOLDEN_PAIRS = tuple(
    (storm, landmark_key)
    for storm in ("AL052019", "AL092022", "AL112017", "AL142024")
    for landmark_key in ("miami-dade", "nassau")
)


def test_every_scrubbed_step_equals_its_golden_and_dorian_026_reads_level_5_with_hwr() -> None:  # noqa: PLR0915
    with recorded_services():
        assert add_landmark(MIAMI, "miami-dade", "--polygon", "forecast").exit_code == 0
        assert add_landmark(NASSAU, "nassau").exit_code == 0
        assert run(["locations", "evacuation", NASSAU, "on"]).exit_code == 0
        assert run(["check", "--once"]).exit_code == 0

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

        async def _scrub_all() -> tuple[
            dict[tuple[str, str], ReplayTimelineResponse],
            dict[tuple[str, str, str], ReplayAssessmentResponse],
            MapResponse,
        ]:
            transport = httpx.ASGITransport(app=app)
            timelines: dict[tuple[str, str], ReplayTimelineResponse] = {}
            assessments: dict[tuple[str, str, str], ReplayAssessmentResponse] = {}
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                for storm, landmark_key in GOLDEN_PAIRS:
                    loc_name = LANDMARK_BY_KEY[landmark_key]
                    res = await client.get(
                        f"/api/replay/{storm}/timeline?location={quote(loc_name)}"
                    )
                    assert res.status_code == HTTPStatus.OK, (storm, loc_name, res.text)
                    timeline = ReplayTimelineResponse.model_validate_json(res.text)
                    timelines[storm, landmark_key] = timeline

                    # Scrub transition steps (plus Dorian 024 and 026 at Nassau) via /assessment.
                    prev_state: tuple[int, str] | None = None
                    for step in timeline.steps:
                        cur_state = (step.level.number, step.rule)
                        is_transition = cur_state != prev_state
                        prev_state = cur_state
                        if is_transition or (
                            storm == "AL052019"
                            and landmark_key == "nassau"
                            and step.advisory_id in {"024", "026"}
                        ):
                            a_res = await client.get(
                                f"/api/replay/{storm}/{step.advisory_id}/assessment"
                                f"?location={quote(loc_name)}"
                            )
                            assert a_res.status_code == HTTPStatus.OK, a_res.text
                            raw_json = cast("dict[str, object]", a_res.json())
                            assert "id" not in raw_json
                            assert "stored_at" not in raw_json
                            assessments[storm, landmark_key, step.advisory_id] = (
                                ReplayAssessmentResponse.model_validate_json(a_res.text)
                            )

                map_res = await client.get("/api/replay/AL052019/026")
                assert map_res.status_code == HTTPStatus.OK
                map_doc = MapResponse.model_validate_json(map_res.text)
                return timelines, assessments, map_doc

        timelines, assessments, map_doc = asyncio.run(_scrub_all())
    finally:
        database.close()

    # Every scrubbed step across all 8 golden timelines matches its frozen golden document.
    for storm, landmark_key in GOLDEN_PAIRS:
        golden = build_goldens.read_document(GOLDENS / f"{storm}-{landmark_key}.json")
        expected_steps = cast("list[dict[str, object]]", golden["timeline"])
        timeline = timelines[storm, landmark_key]
        assert timeline.atcf_id == storm
        assert timeline.name == golden["archive_name"]
        assert timeline.ruleset == golden["ruleset"]
        actual_steps = [
            {
                "advisory": step.advisory,
                "issued_at": utc(step.issued_at),
                "level": step.level.number,
                "rule": step.rule,
                "changes": [change.kind for change in step.changes],
                "official_codes": list(step.official_codes),
            }
            for step in timeline.steps
        ]
        assert actual_steps == expected_steps, (storm, landmark_key)

    # Every scrubbed /assessment response matches its timeline step and carries origin="replay".
    for (storm, landmark_key, adv_id), assessment_doc in assessments.items():
        timeline = timelines[storm, landmark_key]
        step = next(s for s in timeline.steps if s.advisory_id == adv_id)
        assert assessment_doc.origin == "replay"
        assert assessment_doc.atcf_id == storm
        assert assessment_doc.advisory_id == adv_id
        assert assessment_doc.advisory == step.advisory
        assert assessment_doc.as_of == step.issued_at
        assert assessment_doc.level == step.level
        assert assessment_doc.rule == step.rule
        assert assessment_doc.rule_trigger == step.rule_trigger
        assert assessment_doc.complete == step.complete
        assert assessment_doc.changes == step.changes

    # Dorian at Nassau: 024 is Level 4 (HWA), 026 is Level 5 (HWR), and evacuation note shows.
    nassau_timeline = timelines["AL052019", "nassau"]
    assert any("evacuation-order toggle" in note for note in nassau_timeline.notes)
    dorian_024 = assessments["AL052019", "nassau", "024"]
    assert dorian_024.level.number == 4  # noqa: PLR2004
    assert dorian_024.rule == "hurricane_watch"

    dorian_026 = assessments["AL052019", "nassau", "026"]
    assert dorian_026.level.number == 5  # noqa: PLR2004
    assert dorian_026.rule == "hurricane_warning"
    assert any(
        ev.product == "watch_warning_segment" and ev.code == "HWR" for ev in dorian_026.evidence
    )

    # Replay map markers carry no present-day live level beside the scrubbed one.
    point_features = [f for f in map_doc.locations.features if f.geometry.type == "Point"]
    assert len(point_features) == 2  # noqa: PLR2004
    for feature in map_doc.locations.features:
        assert feature.properties.get("level") is None
        assert feature.properties.get("level_label") is None
        assert feature.properties.get("rule") is None


@pytest.mark.parametrize(
    ("url", "secret_token"),
    [
        ("/api/replay/AL999999/timeline?location=Parliament%20Square", "AL999999"),
        ("/api/replay/AL052019/timeline?location=UnknownSecretPlace", "UnknownSecretPlace"),
        ("/api/replay/AL999999/026/assessment?location=Parliament%20Square", "AL999999"),
        ("/api/replay/AL052019/999Z/assessment?location=Parliament%20Square", "999Z"),
        (
            "/api/replay/AL052019/026/assessment?location=UnknownSecretPlace",
            "UnknownSecretPlace",
        ),
    ],
)
def test_replay_timeline_and_assessment_return_generic_404_without_echoing_input(
    url: str, secret_token: str
) -> None:
    with recorded_services():
        assert add_landmark(NASSAU, "nassau").exit_code == 0

    paths = AppPaths.resolve()
    corpus = ReplayCorpus.open(CORPUS)
    with open_database(paths, now=lambda: NOW) as database:
        state = WebState(
            database=database,
            paths=paths,
            settings=load_settings(paths),
            setting_origins=setting_origins(paths),
            clock=lambda: NOW,
            started_at=NOW,
            corpus=corpus,
        )
        app = create_app(state)

        async def _get() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                return await client.get(url)

        res = asyncio.run(_get())

    assert res.status_code == HTTPStatus.NOT_FOUND
    assert secret_token not in res.text
