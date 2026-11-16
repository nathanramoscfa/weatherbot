# scripts/demo_scenarios.py
"""The five demonstration scenarios: every level on screen while the real tropics are quiet.

``SCENARIOS`` declares each scenario's expectation, the level and deciding rule each public
landmark must read, as a literal that ``scripts/verify_phase08.py`` reads by AST; the
scenarios are the table of ``docs/roadmap/phase08-roadmap.md``'s Decision 2:

- ``quiet``: no storm, no alert, and no outlook area; both landmarks read level 1.
- ``outlook``: no storm and one synthetic seven-day development region over both
  landmarks; both read level 2 by ``development_region``.
- ``cone``: Hurricane Demo (``scripts/demo_storm.py``) still a tropical storm at its
  closest approach to the Nassau landmark (level 2, ``storm_cone``) and a hurricane by the
  Miami-Dade landmark's (level 3, ``hurricane_cone``); its 64-kt band at Nassau stays
  below the hurricane floor, or ``hurricane_wind_probability`` would outrank the cone.
- ``watch``: an NWS Hurricane Watch for the Miami-Dade landmark's zone and NHC ``HWA``
  and ``TWA`` segments (levels 4 and 3).
- ``landfall``: a major hurricane near landfall with an NWS Hurricane Warning and ``HWR``
  and ``TWR`` segments (levels 5 and 4), after a seeded history of the ``outlook``,
  ``cone``, and ``watch`` stages as earlier advisories.

Each stage stages the roster, the storm's answers, the outlook layers, the window watch's
cone attributes, and the NWS alert answers for every query the Miami-Dade landmark makes
(its point, its forecast zone, and its county zone), built from ``register_alert``'s shape
for the four ladder events, so no recorded alert leaks in. Every other source answers
from the recordings through ``recorded_services()``, whose router refuses any request it
does not know. ``Staging`` installs every URL of every stage of a scenario on that router
and serves the stage shown, so ``run_history`` can run the landfall history's cycles one
stage at a time, each through ``MonitorService.run_cycle`` at its own earlier instant and
the existing ``roster`` trigger, before the server's startup cycle.

``seed_ai`` stores, through ``ChangeSummaryService`` and ``BriefingService`` and whatever
client it is handed (``serve_demo.py``'s replay), each landmark's last escalation summary
in a scenario with a history and every landmark's briefing, because ``serve``'s
``ChangeSummarizer`` never backfills. ``build_database`` builds a scenario's database in a
directory with the same code ``serve_demo.py --scenario`` runs, for the tests and for
``scripts/record_ai_fixtures.py --scenario``.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast
from urllib.parse import urlencode

import httpx

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    import respx
    from anthropic import AsyncAnthropic

    from weatherbot.services.monitor import CycleResult
    from weatherbot.services.notifications import Channel
    from weatherbot.services.persistence.database import Database
    from weatherbot.sources.http import Fetcher, ValidatorStore

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
for _extra in (
    REPO_ROOT / "src",
    REPO_ROOT / "scripts",
    REPO_ROOT / "tests" / "cli",
    REPO_ROOT / "tests" / "contract",
    REPO_ROOT / "tests" / "sources",
):
    _text = str(_extra)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from cli_support import (  # noqa: E402
    COUNTY_ALERTS,
    NASSAU,
    landmark,
    quiet_fetcher,
    recorded_services,
    run,
    runtime,
    urls,
)
from fixture_support import as_object, latest_live, register_alert  # noqa: E402
from source_support import NOW, entry  # noqa: E402

import demo_storm  # noqa: E402
from demo_storm import ARCGIS_JSON, ROSTER_URL, StagedAnswer  # noqa: E402
from simulate_advisory import FORECAST_ALERTS_URL, FORECAST_ZONE_URL, SIMULATED_MIAMI  # noqa: E402
from weatherbot.services.ai.briefing import BriefingService, Done, Withheld  # noqa: E402
from weatherbot.services.ai.guard import ai_engine  # noqa: E402
from weatherbot.services.ai.service import AiService  # noqa: E402
from weatherbot.services.ai.summaries import ChangeSummaryService  # noqa: E402
from weatherbot.services.config import AppPaths, Settings, load_settings  # noqa: E402
from weatherbot.services.monitor import SCHEDULED_SOURCE_CADENCE_S, MonitorService  # noqa: E402
from weatherbot.services.network import Network  # noqa: E402
from weatherbot.services.notifications import LogChannel  # noqa: E402
from weatherbot.services.persistence.database import open_database  # noqa: E402
from weatherbot.services.persistence.repositories import AssessmentRepository  # noqa: E402
from weatherbot.services.schedule import MonitorSchedule  # noqa: E402
from weatherbot.sources.arcgis import ATTRIBUTE_PARAMETERS, TROPICAL_SUMMARY  # noqa: E402
from weatherbot.sources.nhc_map import CONE_ADVISORY_FIELDS  # noqa: E402
from weatherbot.sources.nws import point_alerts_url  # noqa: E402

SCENARIOS: Final = {
    "quiet": {
        "simulated Miami-Dade": {"level": 1, "rule": "all_clear"},
        "Parliament Square": {"level": 1, "rule": "all_clear"},
    },
    "outlook": {
        "simulated Miami-Dade": {"level": 2, "rule": "development_region"},
        "Parliament Square": {"level": 2, "rule": "development_region"},
    },
    "cone": {
        "simulated Miami-Dade": {"level": 3, "rule": "hurricane_cone"},
        "Parliament Square": {"level": 2, "rule": "storm_cone"},
    },
    "watch": {
        "simulated Miami-Dade": {"level": 4, "rule": "hurricane_watch"},
        "Parliament Square": {"level": 3, "rule": "tropical_storm_watch"},
    },
    "landfall": {
        "simulated Miami-Dade": {"level": 5, "rule": "hurricane_warning"},
        "Parliament Square": {"level": 4, "rule": "tropical_storm_warning"},
    },
}
"""Each scenario's level and deciding rule for each landmark: Decision 2's table."""
HISTORY: Final = {"landfall": ("outlook", "cone", "watch")}
"""The earlier stages a scenario stores before its own, as earlier advisories."""
PORTS: Final = {"quiet": 8802, "outlook": 8803, "cone": 8804, "watch": 8805, "landfall": 8806}
"""The loopback port each scenario's browser server uses (8803 to 8805: Step 8's harness)."""
LANDMARKS: Final = {"simulated Miami-Dade": "miami-dade", "Parliament Square": "nassau"}
"""Each landmark's name and the key ``scripts/public_landmarks.toml`` and recordings use."""
SCENARIO_NAMES: Final = tuple(SCENARIOS)

CURRENT_ISSUED_AT: Final[Mapping[str, datetime]] = {
    "quiet": NOW,
    "outlook": datetime(2026, 10, 12, 18, tzinfo=UTC),
    "cone": datetime(2026, 10, 12, 21, tzinfo=UTC),
    "watch": datetime(2026, 10, 12, 21, tzinfo=UTC),
    "landfall": datetime(2026, 10, 12, 21, tzinfo=UTC),
}
"""When a scenario's own stage is issued: the 2 PM EDT outlook, or the 5 PM EDT advisory."""
HISTORY_ISSUED_AT: Final[Mapping[str, datetime]] = {
    "outlook": datetime(2026, 10, 10, 18, tzinfo=UTC),
    **demo_storm.HISTORY_ISSUED_AT,
}
"""When the landfall history issues each stage: an outlook, then advisories 3, 6, and 8."""
CYCLE_DELAY: Final = timedelta(minutes=30)
"""A history cycle runs half an hour after its stage was issued."""
ALERT_DELAY: Final = timedelta(minutes=22)
"""NWS Miami issues its alert this long after the NHC advisory."""
ALERT_LIFETIME: Final = timedelta(hours=48)
"""How long a staged alert stays in effect, so a demonstration server can run for a day."""
ALERTS: Final[Mapping[str, str]] = {"watch": "Hurricane Watch", "landfall": "Hurricane Warning"}
"""The NWS ladder event each stage stages for the Miami-Dade landmark."""
OUTLOOK_LAYERS: Final = (
    "Two-Day: Current Location",
    "Seven-Day: Current Location",
    "Seven-Day: Development Motion",
    "Seven-Day: Potential Development Region",
)
DEVELOPMENT_REGION: Final[tuple[demo_storm.Point, ...]] = (
    (-69.80, 20.20),
    (-70.20, 22.20),
    (-74.00, 24.20),
    (-77.20, 26.20),
    (-80.60, 27.20),
    (-81.70, 26.30),
    (-81.30, 24.90),
    (-78.20, 23.70),
    (-74.60, 22.10),
    (-71.20, 20.00),
    (-69.80, 20.20),
)
"""The synthetic seven-day region: from the disturbance over Nassau to past Miami."""
_EVENT_CODES: Final = {
    "Hurricane Warning": ("HU.W", "Extreme", "Likely", "Expected"),
    "Tropical Storm Warning": ("TR.W", "Severe", "Likely", "Expected"),
    "Hurricane Watch": ("HU.A", "Severe", "Possible", "Future"),
    "Tropical Storm Watch": ("TR.A", "Moderate", "Possible", "Future"),
}
"""Each ladder event's code, severity, certainty, and urgency, as NWS issues them."""
FIXTURES: Final = REPO_ROOT / "tests" / "fixtures" / "ai"


class ScenarioError(RuntimeError):
    """A scenario did not stage, store, or decide what it declares."""


def case_name(scenario: str, location: str, kind: str = "briefing") -> str:
    """Name a scenario's recording: ``scenario-<scenario>-<landmark>`` (``-summary`` added).

    Args:
        scenario: The scenario.
        location: The landmark's name.
        kind: ``briefing`` or ``summary``.

    Returns:
        The case name in ``tests/fixtures/ai/``.
    """
    name = f"scenario-{scenario}-{LANDMARKS[location]}"
    return f"{name}-summary" if kind == "summary" else name


def scenario_recording(scenario: str, kind: str, text: str) -> str | None:
    """Find the recording that answers a scenario's briefing or summary request.

    Args:
        scenario: The scenario the server runs.
        kind: ``briefing`` or ``summary``.
        text: The request's messages, which name the landmark.

    Returns:
        The case, or ``None`` when no landmark is named or no such recording exists.
    """
    location = next((name for name in LANDMARKS if name in text), None)
    if location is None:
        return None
    name = case_name(scenario, location, kind)
    recorded = any((FIXTURES / f"{name}{suffix}").is_file() for suffix in (".sse", ".json"))
    return name if recorded else None


# Answers ---------------------------------------------------------------------------------


def _empty() -> dict[str, object]:
    return {"type": "FeatureCollection", "features": []}


def cone_attributes_url() -> str:
    """The cone layer's attribute query the window watch sends (``nhc_map.fetch_cone_advisories``).

    Returns:
        The URL, with the recorded catalog's layer id for ``Forecast Cone``.

    Raises:
        ScenarioError: The recorded catalog does not name exactly one cone layer.
    """
    directory = latest_live("nhc-map-tropical-summary")
    if directory is None:
        message = "nhc-map-tropical-summary has no live capture"
        raise ScenarioError(message)
    catalog = as_object(json.loads(directory.payload(entry(directory, "catalog.json"))))
    layers = [as_object(layer) for layer in cast("list[object]", catalog["layers"])]
    found = [layer["id"] for layer in layers if layer.get("name") == demo_storm.FORECAST_CONE]
    if len(found) != 1:
        message = "the recorded catalog does not name exactly one Forecast Cone layer"
        raise ScenarioError(message)
    parameters = {
        "where": ATTRIBUTE_PARAMETERS["where"],
        "outFields": ",".join(CONE_ADVISORY_FIELDS),
        "returnGeometry": ATTRIBUTE_PARAMETERS["returnGeometry"],
        "f": ATTRIBUTE_PARAMETERS["f"],
    }
    return f"{TROPICAL_SUMMARY.url}/{found[0]}/query?{urlencode(parameters, safe='*,')}"


def _outlook_properties(layer: str, issued_at: datetime, prefix: str) -> dict[str, object]:
    template = demo_storm.template_properties(layer)
    return {
        **template,
        "objectid": 1,
        "basin": "Atlantic",
        "prob2day": "20%",
        "risk2day": "Low",
        "prob7day": "60%",
        "risk7day": "Medium",
        "idp_source": f"{prefix}_{issued_at:%Y%m%d%H%M}",
        "idp_filedate": int((issued_at - datetime(1970, 1, 1, tzinfo=UTC)).total_seconds() * 1000),
        "snippet": demo_storm.SYNTHETIC_NOTE,
        "synthetic": True,
    }


def outlook_answers(issued_at: datetime) -> dict[str, StagedAnswer]:
    """The outlook layers with one synthetic disturbance and its seven-day region.

    Args:
        issued_at: When the outlook is shown as issued.

    Returns:
        The four outlook layers' answers by URL: the disturbance's two-day and seven-day
        location, no motion arrow, and the development region over both landmarks.
    """
    layers = demo_storm.summary_layer_urls()
    disturbance = demo_storm.position(demo_storm.FORMATION - timedelta(hours=6))
    point = {"type": "Point", "coordinates": [round(disturbance[0], 2), round(disturbance[1], 2)]}
    region = {"type": "Polygon", "coordinates": [[list(corner) for corner in DEVELOPMENT_REGION]]}
    documents = {
        "Two-Day: Current Location": (point, "gtwo_points"),
        "Seven-Day: Current Location": (point, "gtwo_points"),
        "Seven-Day: Potential Development Region": (region, "gtwo_areas"),
    }
    answers = {layers["Seven-Day: Development Motion"]: StagedAnswer.json(_empty())}
    for layer, (geometry, prefix) in documents.items():
        properties = _outlook_properties(layer, issued_at, prefix)
        feature = {"type": "Feature", "geometry": geometry, "properties": properties}
        answers[layers[layer]] = StagedAnswer.json(
            {"type": "FeatureCollection", "features": [feature]}
        )
    return answers


def ladder_alert(event: str, *, sent: datetime, stage: str) -> dict[str, object]:
    """Build an NWS alert of one ladder event for the Miami-Dade landmark's forecast zone.

    Args:
        event: ``Hurricane Warning``, ``Tropical Storm Warning``, ``Hurricane Watch``, or
            ``Tropical Storm Watch``.
        sent: Its ``sent``, ``effective``, and ``onset``; it expires 48 hours later.
        stage: The stage, which its id names.

    Returns:
        The alert as one feature, on ``register_alert``'s shape, labelled synthetic in its
        sender, headline, description, and ``synthetic`` property.
    """
    code, severity, certainty, urgency = _EVENT_CODES[event]
    feature = register_alert(sent)
    alert_id = f"urn:oid:2.49.0.1.840.0.synthetic-demo.{stage}.{code}.1"
    feature["id"] = f"https://api.weather.gov/alerts/{alert_id}"
    local = sent.astimezone(demo_storm.EDT)
    properties = cast("dict[str, object]", feature["properties"])
    properties.update(
        {
            "id": alert_id,
            "areaDesc": "Coastal Miami Dade County",
            "geocode": {"SAME": ["012086"], "UGC": ["FLZ173"]},
            "affectedZones": [FORECAST_ZONE_URL],
            "onset": sent.isoformat(),
            "expires": (sent + ALERT_LIFETIME).isoformat(),
            "severity": severity,
            "certainty": certainty,
            "urgency": urgency,
            "event": event,
            "senderName": "NWS Miami FL (synthetic demonstration)",
            "headline": (
                f"{event} issued {local:%B} {local.day} at {local.hour % 12 or 12}:{local:%M}"
                f"{'AM' if local.hour < 12 else 'PM'} EDT by NWS Miami FL "  # noqa: PLR2004 - noon
                "(synthetic demonstration)"
            ),
            "description": (
                f"SYNTHETIC DEMONSTRATION. A {event} for Hurricane Demo, which is not a real "
                "storm. Weatherbot's demonstration scenarios built this alert; it is never "
                "official guidance."
            ),
            "instruction": "This is a demonstration. Follow your local officials' guidance.",
            "parameters": {"NWSheadline": [f"{event.upper()} IN EFFECT (SYNTHETIC DEMONSTRATION)"]},
            "synthetic": True,
        }
    )
    return feature


def _alerts_template(source: str, name: str) -> dict[str, object]:
    directory = latest_live(source)
    if directory is None:
        message = f"{source} has no live capture"
        raise ScenarioError(message)
    return dict(as_object(json.loads(directory.payload(entry(directory, name)))))


def alert_answers(
    features: Sequence[dict[str, object]], updated: datetime
) -> dict[str, StagedAnswer]:
    """Answer the Miami-Dade landmark's three alert queries with the same alerts.

    Args:
        features: The alerts.
        updated: The answers' ``updated`` instant.

    Returns:
        The point, county-zone, and forecast-zone answers by URL, from the recorded
        answers' top-level shape.
    """
    lat, lon = landmark("miami-dade")
    queries = (
        (
            point_alerts_url(float(lat), float(lon)),
            "nws-alerts-point",
            "alerts-point-miami-dade.geojson",
        ),
        (COUNTY_ALERTS, "nws-alerts-zone", "alerts-zone-FLC086.geojson"),
        (FORECAST_ALERTS_URL, "nws-alerts-zone", "alerts-zone-FLZ173.geojson"),
    )
    answers: dict[str, StagedAnswer] = {}
    for url, source, name in queries:
        document = {**_alerts_template(source, name), "updated": updated.isoformat()}
        document["features"] = list(features)
        answers[url] = StagedAnswer.json(document, "application/geo+json")
    return answers


def stage_answers(stage: str, issued_at: datetime) -> dict[str, StagedAnswer]:
    """Every staged answer of one stage: storm, outlook, window watch, and NWS alerts.

    Args:
        stage: A scenario's name, which is also its stage's.
        issued_at: When the stage is shown as issued.

    Returns:
        The answers by URL; every summary layer a cycle queries answers, empty when the
        stage has nothing in it.
    """
    layers = demo_storm.summary_layer_urls()
    names = (*demo_storm.STORM_LAYERS, *demo_storm.WIND_LAYERS.values(), *OUTLOOK_LAYERS)
    answers = {layers[name]: StagedAnswer.json(_empty()) for name in names}
    answers[ROSTER_URL] = StagedAnswer.json(demo_storm.roster_document(None), "application/json")
    storm = stage if stage in demo_storm.STAGE_NAMES else None
    attributes = demo_storm.cone_advisory_attributes(storm)
    answers[cone_attributes_url()] = StagedAnswer.json(attributes, ARCGIS_JSON)
    if storm is not None:
        answers |= demo_storm.stage_answers(storm, issued_at)
    if stage == "outlook":
        answers |= outlook_answers(issued_at)
    sent = issued_at + ALERT_DELAY
    event = ALERTS.get(stage)
    features = [ladder_alert(event, sent=sent, stage=stage)] if event is not None else []
    answers |= alert_answers(features, sent)
    return answers


def scenario_stages(scenario: str) -> tuple[tuple[str, datetime], ...]:
    """A scenario's stages, in order: its history's, then its own.

    Args:
        scenario: The scenario.

    Returns:
        Each stage and when it is issued.
    """
    history = tuple((stage, HISTORY_ISSUED_AT[stage]) for stage in HISTORY.get(scenario, ()))
    return (*history, (scenario, CURRENT_ISSUED_AT[scenario]))


class Staging:
    """Serves one scenario's staged answers, one stage at a time, through routes installed once."""

    def __init__(self, scenario: str) -> None:
        """Build every stage's answers; the scenario's own stage is shown.

        Args:
            scenario: The scenario.

        Raises:
            ScenarioError: The scenario is unknown.
        """
        if scenario not in SCENARIOS:
            message = f"no scenario is named {scenario!r}"
            raise ScenarioError(message)
        self.scenario = scenario
        self.stages = scenario_stages(scenario)
        self.answers = tuple(stage_answers(stage, at) for stage, at in self.stages)
        self.current = len(self.stages) - 1

    def show(self, index: int) -> None:
        """Serve one stage's answers from now on.

        Args:
            index: The stage's position in ``stages``.
        """
        self.current = index

    def install(self, router: respx.MockRouter) -> None:
        """Answer every staged URL of every stage on a router, after its recorded routes.

        Args:
            router: ``recorded_services()``'s router; a route of the same pattern replaces
                the recorded one.
        """
        for url in sorted({url for answers in self.answers for url in answers}):
            router.get(url).mock(side_effect=self._answer(url))

    def _answer(self, url: str) -> Callable[[httpx.Request], httpx.Response]:
        def answer(_request: httpx.Request) -> httpx.Response:
            found = self.answers[self.current].get(url)
            return found.response() if found is not None else httpx.Response(404)

        return answer


# Cycles and AI ---------------------------------------------------------------------------


def _fetcher_at(at: datetime) -> Callable[[httpx.AsyncClient, ValidatorStore], Fetcher]:
    def make(client: httpx.AsyncClient, validators: ValidatorStore) -> Fetcher:
        return quiet_fetcher(client, validators, now=at)

    return make


def _fixed(at: datetime) -> Callable[[], datetime]:
    return lambda: at


async def run_history(
    database: Database,
    paths: AppPaths,
    settings: Settings,
    staging: Staging,
    *,
    channels: Sequence[Channel],
) -> tuple[CycleResult, ...]:
    """Store a scenario's history: one ``roster`` cycle per earlier stage, at its own instant.

    Each cycle runs through ``MonitorService.run_cycle`` (never a ``MonitorSchedule``, whose
    second instance ``serve_demo.py`` makes skip its startup cycle) half an hour after its
    stage was issued. The scenario's own stage is shown afterwards.

    Args:
        database: The scenario's database.
        paths: Its paths, for the cycle lock.
        settings: Its settings.
        staging: The scenario's staging, installed on the router.
        channels: Where the escalation notifications are delivered.

    Returns:
        Each history cycle's result.

    Raises:
        ScenarioError: A history cycle was not complete.
    """
    results: list[CycleResult] = []
    for index, (stage, issued_at) in enumerate(staging.stages[:-1]):
        staging.show(index)
        at = issued_at + CYCLE_DELAY
        monitor = MonitorService(
            database.engine,
            paths=paths,
            settings=settings,
            runner="serve",
            network=Network(make_fetcher=_fetcher_at(at)),
            now=_fixed(at),
            cadence_s=SCHEDULED_SOURCE_CADENCE_S,
            channels=channels,
        )
        result = await monitor.run_cycle("roster")
        if result.status != "complete":
            message = f"the {stage} stage's history cycle was {result.status}, not complete"
            raise ScenarioError(message)
        results.append(result)
    staging.show(len(staging.stages) - 1)
    return tuple(results)


async def run_startup(
    database: Database, paths: AppPaths, settings: Settings, clock: Callable[[], datetime]
) -> CycleResult:
    """Run a scenario's startup cycle as ``serve_demo.py``'s first ``MonitorSchedule`` does.

    Args:
        database: The scenario's database.
        paths: Its paths.
        settings: Its settings.
        clock: The demonstration clock.

    Returns:
        The startup cycle's result.
    """
    results: list[CycleResult] = []

    def make(client: httpx.AsyncClient, validators: ValidatorStore) -> Fetcher:
        return quiet_fetcher(client, validators, now=clock())

    schedule = MonitorSchedule(
        database.engine,
        paths,
        settings=settings,
        runner="serve",
        clock=clock,
        make_fetcher=make,
        channels=(LogChannel(),),
        listeners=(results.append,),
        run_startup=True,
    )
    await schedule.run_startup(clock())
    return results[-1]


async def seed_ai(
    database: Database,
    settings: Settings,
    factory: Callable[[], AsyncAnthropic],
    *,
    scenario: str,
    clock: Callable[[], datetime],
) -> dict[str, str]:
    """Store a scenario's AI products before the server binds, as ``serve`` never backfills.

    In a scenario with a history, each landmark's latest assessment (its last escalation)
    gets its change summary first; then every landmark gets its briefing. Each goes through
    the real services and the client ``factory`` builds; a request that cannot be made
    stores nothing.

    Args:
        database: The scenario's database.
        settings: Its settings; ``[ai]`` decides the models and the cap.
        factory: Builds the client, such as ``serve_demo.demo_claude``'s replay.
        scenario: The scenario.
        clock: The demonstration clock.

    Returns:
        How each product ended, by ``"<landmark> summary"`` or ``"<landmark> briefing"``.
    """
    service = AiService(
        ai_engine(database.path), settings.ai, factory=factory, environ={}, now=clock
    )
    outcomes: dict[str, str] = {}
    try:
        assessments = AssessmentRepository(database.engine)
        if scenario in HISTORY:
            summaries = ChangeSummaryService(service)
            for location in LANDMARKS:
                latest = assessments.latest(location)
                if latest is not None:
                    outcomes[f"{location} summary"] = (await summaries.summarize(latest.id)).status
        briefings = BriefingService(service)
        for location in LANDMARKS:
            ended = "unavailable"
            async for event in briefings.stream(location):
                if isinstance(event, Done):
                    ended = "ok"
                elif isinstance(event, Withheld):
                    ended = "withheld"
            outcomes[f"{location} briefing"] = ended
    finally:
        service.engine.dispose()
    return outcomes


def add_landmarks(environ: Mapping[str, str] | None = None) -> int:
    """Store both public landmarks through ``locations add``, as ``serve_demo.py`` does.

    Args:
        environ: The environment the command runs in (its data and config directories);
            the process's own when omitted.

    Returns:
        The first nonzero exit code, or 0.
    """
    rt = runtime(environ=environ) if environ is not None else None
    for name, key, extra in (
        (SIMULATED_MIAMI, "miami-dade", ("--polygon", "forecast")),
        (NASSAU, "nassau", ()),
    ):
        lat, lon = landmark(key)
        ran = run(["locations", "add", name, "--lat", lat, "--lon", lon, *extra], rt)
        if ran.exit_code != 0:
            return ran.exit_code
    return 0


def wall_clock(start: datetime = NOW) -> Callable[[], datetime]:
    """A demonstration clock: ``start``, advancing with the wall clock.

    Args:
        start: The clock's first reading.

    Returns:
        The clock.
    """
    began = time.monotonic()
    return lambda: start + timedelta(seconds=max(0.0, time.monotonic() - began))


@dataclass(frozen=True)
class ScenarioDatabase:
    """A built scenario: its paths, settings, staging, cycles, requests, and AI outcomes."""

    paths: AppPaths
    settings: Settings
    staging: Staging
    cycles: tuple[CycleResult, ...]
    requested: tuple[str, ...]
    ai: Mapping[str, str]
    clock: Callable[[], datetime]


def build_database(
    scenario: str,
    root: Path,
    *,
    claude: Callable[[], AsyncAnthropic] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> ScenarioDatabase:
    """Build a scenario's database in a directory, with the code ``serve_demo.py`` runs.

    Both landmarks are stored through ``locations add``; then the history's cycles, the
    startup cycle, and (with ``claude``) the AI products, all behind ``recorded_services()``
    with the scenario's staging, so no request can leave the router.

    Args:
        scenario: The scenario.
        root: An empty directory; the data and config directories are made inside it.
        claude: Builds the AI client that seeds the summaries and briefings; none when
            omitted.
        clock: The demonstration clock; ``source_support.NOW`` advancing when omitted.

    Returns:
        The built scenario.

    Raises:
        ScenarioError: A landmark could not be stored, or a cycle was not complete.
    """
    paths = AppPaths(config_dir=root / "config", data_dir=root / "data")
    # Nothing of the developer's own settings or credential reaches the scenario.
    kept = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("WEATHERBOT_", "ANTHROPIC_"))
    }
    environ = {
        **kept,
        "WEATHERBOT_DATA_DIR": str(paths.data_dir),
        "WEATHERBOT_CONFIG_DIR": str(paths.config_dir),
        "WEATHERBOT_NOTIFICATIONS_TOAST": "false",
    }
    settings = load_settings(paths, environ)
    reading = clock or wall_clock()
    staging = Staging(scenario)
    with recorded_services() as router:
        staging.install(router)
        if add_landmarks(environ) != 0:
            message = "a landmark could not be stored"
            raise ScenarioError(message)
        with open_database(paths) as database:
            history = asyncio.run(
                run_history(database, paths, settings, staging, channels=(LogChannel(),))
            )
            startup = asyncio.run(run_startup(database, paths, settings, reading))
            requested = tuple(urls(router))
            outcomes: Mapping[str, str] = {}
            if claude is not None:
                outcomes = asyncio.run(
                    seed_ai(database, settings, claude, scenario=scenario, clock=reading)
                )
    return ScenarioDatabase(
        paths, settings, staging, (*history, startup), requested, outcomes, reading
    )
