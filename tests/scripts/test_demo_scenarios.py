# tests/scripts/test_demo_scenarios.py
"""Every demonstration scenario, run offline: its declared levels, rules, history, and AI."""

import io
import json
import os
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fixture_support import capture_directories
from source_support import entry

import demo_scenarios
import demo_storm
from serve_demo import DemoReplay, demo_claude
from weatherbot.services.ai.outputs import OutputRepository
from weatherbot.services.config import Settings
from weatherbot.services.notifications import NotificationService
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import AssessmentRepository, StoredAssessment

MIAMI = "simulated Miami-Dade"
NASSAU = "Parliament Square"
STAND_IN_KMZ = "https://www.nhc.noaa.gov/storm_graphics/api/EP202026_022adv_{kind}_toa_34.kmz"


@pytest.fixture(scope="module")
def built(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[dict[str, demo_scenarios.ScenarioDatabase]]:
    """Build every scenario once, with its AI seeded from the replay, in its own directory."""
    with pytest.MonkeyPatch.context() as patch:
        for name in [name for name in os.environ if name.startswith(("WEATHERBOT_", "ANTHROPIC_"))]:
            patch.delenv(name)
        profiles = tmp_path_factory.mktemp("anthropic")
        patch.setenv("ANTHROPIC_CONFIG_DIR", str(profiles))
        patch.chdir(tmp_path_factory.mktemp("cwd"))
        yield {
            name: demo_scenarios.build_database(
                name,
                tmp_path_factory.mktemp(name),
                claude=demo_claude(DemoReplay(stream_seconds=0.0, scenario=name)),
            )
            for name in demo_scenarios.SCENARIOS
        }


def _history(built: demo_scenarios.ScenarioDatabase, location: str) -> list[StoredAssessment]:
    with open_database(built.paths) as database:
        return list(reversed(AssessmentRepository(database.engine).history(location, 20)))


@pytest.mark.parametrize("scenario", demo_scenarios.SCENARIO_NAMES)
def test_each_scenario_stores_its_declared_level_and_rule_complete(
    built: dict[str, demo_scenarios.ScenarioDatabase], scenario: str
) -> None:
    for location, expected in demo_scenarios.SCENARIOS[scenario].items():
        latest = _history(built[scenario], location)[-1].assessment

        assert (int(latest.level), str(latest.rule)) == (expected["level"], expected["rule"])
        assert latest.complete, [item.reason for item in latest.unavailable]


@pytest.mark.parametrize("scenario", demo_scenarios.SCENARIO_NAMES)
def test_every_cycle_is_complete_with_no_failed_source_or_drift(
    built: dict[str, demo_scenarios.ScenarioDatabase], scenario: str
) -> None:
    cycles = built[scenario].cycles

    assert [cycle.trigger for cycle in cycles][-1] == "startup"
    for cycle in cycles:
        assert cycle.status == "complete"
        assert cycle.snapshot is not None
        assert not [o for o in cycle.snapshot.source_outcomes if o.status == "failed"]
        assert cycle.drift_warnings == ()


def _recorded_urls() -> set[str]:
    return {str(item["url"]) for directory in capture_directories() for item in directory.entries}


@pytest.mark.parametrize("scenario", demo_scenarios.SCENARIO_NAMES)
def test_no_request_left_the_router(
    built: dict[str, demo_scenarios.ScenarioDatabase], scenario: str
) -> None:
    staged = {url for answers in built[scenario].staging.answers for url in answers}
    stand_ins = {STAND_IN_KMZ.format(kind=kind) for kind in demo_storm.ARRIVAL_KINDS}
    requested = set(built[scenario].requested)

    assert requested
    assert requested <= staged | _recorded_urls() | stand_ins
    if scenario in demo_storm.STAGE_NAMES:
        stage = demo_storm.STAGES[scenario]  # pyright: ignore[reportArgumentType] - a storm stage
        kmz = {demo_storm.kmz_url(stage, kind) for kind in demo_storm.ARRIVAL_KINDS}
        assert kmz <= requested
        assert demo_storm.tcp_list_url() in requested


def test_the_landfall_history_advances_one_stage_at_a_time(
    built: dict[str, demo_scenarios.ScenarioDatabase],
) -> None:
    stages = (*demo_scenarios.HISTORY["landfall"], "landfall")

    for location in (MIAMI, NASSAU):
        history = _history(built["landfall"], location)
        assert len(history) >= len(stages)
        read = [(int(s.assessment.level), str(s.assessment.rule)) for s in history]
        expected = [
            (
                demo_scenarios.SCENARIOS[stage][location]["level"],
                demo_scenarios.SCENARIOS[stage][location]["rule"],
            )
            for stage in stages
        ]
        assert read == expected
        assert all(stored.assessment.complete for stored in history)
        instants = [stored.assessment.as_of for stored in history]
        assert instants == sorted(instants)


def test_the_landfall_history_notified_each_escalation(
    built: dict[str, demo_scenarios.ScenarioDatabase],
) -> None:
    scenario = built["landfall"]
    with open_database(scenario.paths) as database:
        stored = NotificationService(database.engine, settings=Settings()).recent(50)

    escalations = {
        (n.location_name, int(n.level or 0)) for n in stored if n.escalation and n.level is not None
    }
    assert {(MIAMI, 3), (MIAMI, 4), (MIAMI, 5), (NASSAU, 3), (NASSAU, 4)} <= escalations


def test_the_landfall_summaries_are_stored_for_both_landmarks(
    built: dict[str, demo_scenarios.ScenarioDatabase],
) -> None:
    scenario = built["landfall"]
    with open_database(scenario.paths) as database:
        summaries = OutputRepository(database.engine, now=scenario.clock).summaries(None, 10)
        latest = {
            location: AssessmentRepository(database.engine).latest(location)
            for location in (MIAMI, NASSAU)
        }

    by_location = {summary.location_name: summary for summary in summaries}
    assert set(by_location) == {MIAMI, NASSAU}
    for location, stored in latest.items():
        assert stored is not None
        assert by_location[location].assessment_id == stored.id
        assert by_location[location].status == "ok"
    assert scenario.ai[f"{MIAMI} summary"] == "ok"
    assert scenario.ai[f"{NASSAU} summary"] == "ok"


def test_the_landfall_miami_dade_briefing_replays_ok_never_withheld(
    built: dict[str, demo_scenarios.ScenarioDatabase],
) -> None:
    assert built["landfall"].ai[f"{MIAMI} briefing"] == "ok"


@pytest.mark.parametrize("scenario", demo_scenarios.SCENARIO_NAMES)
def test_every_scenario_stores_both_briefings(
    built: dict[str, demo_scenarios.ScenarioDatabase], scenario: str
) -> None:
    outcomes = built[scenario].ai

    assert outcomes[f"{MIAMI} briefing"] in {"ok", "withheld"}
    assert outcomes[f"{NASSAU} briefing"] in {"ok", "withheld"}


def _features(document: dict[str, object]) -> list[dict[str, object]]:
    found = document.get("features")
    return list(found) if isinstance(found, list) else []  # pyright: ignore[reportUnknownArgumentType] - parsed JSON


@pytest.mark.parametrize("scenario", demo_scenarios.SCENARIO_NAMES)
def test_every_staged_answer_has_two_decimal_coordinates_and_its_synthetic_label(
    built: dict[str, demo_scenarios.ScenarioDatabase], scenario: str
) -> None:
    for answers in built[scenario].staging.answers:
        positions = demo_storm.synthetic_positions(
            {url: answer for url, answer in answers.items() if "api.weather.gov/alerts" not in url}
        )
        assert all(demo_storm.decimals(value) <= 2 for value in positions)  # noqa: PLR2004 - R2's bound
        for url, answer in answers.items():
            if answer.content_type == demo_storm.KMZ_TYPE:
                with zipfile.ZipFile(io.BytesIO(answer.body)) as archive:
                    kml = archive.read(archive.namelist()[0]).decode("utf-8")
                assert '<Data name="synthetic"><value>true</value></Data>' in kml
                continue
            document = json.loads(answer.body)
            for feature in _features(document):
                properties = feature.get("properties", feature.get("attributes"))
                assert isinstance(properties, dict)
                assert properties["synthetic"] is True, url  # pyright: ignore[reportUnknownMemberType] - parsed JSON
                if "api.weather.gov/alerts" in url:
                    assert "synthetic demonstration" in str(properties["senderName"])  # pyright: ignore[reportUnknownArgumentType]
                    assert "synthetic demonstration" in str(properties["headline"])  # pyright: ignore[reportUnknownArgumentType]
            for storm in document.get("activeStorms", []):
                assert storm["synthetic"] is True


def test_the_quiet_scenario_holds_no_storm_alert_or_outlook_area(
    built: dict[str, demo_scenarios.ScenarioDatabase],
) -> None:
    snapshot = built["quiet"].cycles[-1].snapshot

    assert snapshot is not None
    assert snapshot.storms == ()
    assert snapshot.outlook_areas == ()
    assert snapshot.wind_probabilities == ()
    assert all(alerts == () for alerts in snapshot.alerts.values())


def test_the_storm_names_no_real_storm(
    built: dict[str, demo_scenarios.ScenarioDatabase],
) -> None:
    snapshot = built["landfall"].cycles[-1].snapshot

    assert snapshot is not None
    (storm,) = snapshot.storms
    assert (storm.atcf_id, storm.name) == ("AL802026", "Demo")


def test_an_unknown_scenario_is_refused() -> None:
    with pytest.raises(demo_scenarios.ScenarioError, match="no scenario"):
        demo_scenarios.Staging("hurricane")


def test_the_declared_table_and_ports_cover_every_scenario() -> None:
    assert demo_scenarios.SCENARIO_NAMES == ("quiet", "outlook", "cone", "watch", "landfall")
    assert set(demo_scenarios.PORTS) == set(demo_scenarios.SCENARIOS)
    assert sorted(demo_scenarios.PORTS.values()) == list(range(8802, 8807))
    for expectations in demo_scenarios.SCENARIOS.values():
        assert set(expectations) == set(demo_scenarios.LANDMARKS)


def test_a_scenario_recording_is_found_by_landmark_and_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(demo_scenarios, "FIXTURES", tmp_path)
    (tmp_path / "scenario-landfall-miami-dade.sse").write_text("event: x", encoding="utf-8")
    text = json.dumps([{"role": "user", "content": f'{{"location": "{MIAMI}"}}'}])

    assert demo_scenarios.case_name("landfall", MIAMI) == "scenario-landfall-miami-dade"
    assert demo_scenarios.case_name("landfall", NASSAU, "summary") == (
        "scenario-landfall-nassau-summary"
    )
    assert demo_scenarios.scenario_recording("landfall", "briefing", "no landmark") is None
    assert demo_scenarios.scenario_recording("landfall", "briefing", text) == (
        "scenario-landfall-miami-dade"
    )
    assert demo_scenarios.scenario_recording("landfall", "summary", text) is None


def test_the_cone_attributes_url_is_the_window_watchs(
    built: dict[str, demo_scenarios.ScenarioDatabase],
) -> None:
    del built
    directory = next(d for d in capture_directories() if d.source == "nhc-map-tropical-summary")
    catalog = json.loads(directory.payload(entry(directory, "catalog.json")))
    (cone,) = [layer["id"] for layer in catalog["layers"] if layer["name"] == "Forecast Cone"]

    assert demo_scenarios.cone_attributes_url().endswith(
        f"/{cone}/query?where=1%3D1&outFields=binnumber,advisnum&returnGeometry=false&f=json"
    )
