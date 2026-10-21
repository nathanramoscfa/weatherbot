# tests/cli/test_cli_privacy.py
"""No command logs a location's coordinates above DEBUG or prints them outside ``list``.

The coordinates come from ``synthetic_coordinates()`` at run time, never from a literal;
the NWS and Nominatim answers for them are the Miami-Dade landmark's recorded answers.
An assessment's distances and bearings locate the location as surely, so ``status``
prints them to the terminal only, and no log record above DEBUG holds one.
"""

import logging
import re

import pytest
from cli_support import CORPUS, Ran, history, recorded_services, run, urls

from check_personal_data import load_landmarks, synthetic_coordinates
from weatherbot.services.logs import configure_logging

# A standalone decimal with three or more places; dotted ids such as an alert's
# ``urn:oid:2.49.0.1.840...`` are not numbers.
DECIMAL_COORDINATE = re.compile(r"(?<![\d.])\d{1,3}\.\d{3,}(?![\d.])")
NAME = "Synthetic place"


@pytest.fixture
def coordinates() -> tuple[str, str]:
    """A synthetic latitude and longitude, far from every landmark."""
    return synthetic_coordinates(load_landmarks(), (), seed=6)


def leaks(text: str, coordinates: tuple[str, str]) -> bool:
    renderings = {
        rendering
        for value in coordinates
        for rendering in (value, str(float(value)), f"{float(value):.4f}", value.lstrip("-"))
    }
    return any(value in text for value in renderings) or bool(DECIMAL_COORDINATE.search(text))


def test_no_command_logs_or_prints_a_coordinate_except_locations_list(
    coordinates: tuple[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    lat, lon = coordinates
    commands = [
        ["fetch"],
        ["fetch", "--json"],
        ["storms"],
        ["storms", "--json"],
        ["storms", "--no-fetch", "--json"],
        ["alerts"],
        ["alerts", "--json"],
        ["alerts", "--no-fetch"],
        ["doctor"],
        ["doctor", "--json"],
        ["doctor", "--offline", "--json"],
        ["status"],
        ["status", "--json"],
        ["status", "--no-fetch"],
        ["locations", "evacuation", NAME, "on"],
        ["status", "--no-fetch", "--json"],
        ["replay", "AL142024", "--location", NAME, "--corpus", str(CORPUS)],
        ["replay", "AL142024", "--location", NAME, "--corpus", str(CORPUS), "--json"],
    ]
    with recorded_services() as router:
        added = run(["locations", "add", NAME, "--lat", lat, "--lon", lon, "--polygon", "forecast"])
        ran: list[Ran] = [added, *(run(command) for command in commands)]
        listed = run(["locations", "list"])
        listed_json = run(["locations", "list", "--json"])
        removed = run(["locations", "remove", NAME])
        sent = urls(router)

    assert added.exit_code == 0, added.stderr
    for result in [*ran, removed]:
        assert not leaks(result.stdout, coordinates)
        assert not leaks(result.stderr, coordinates)
    assert str(float(lat)) in listed.stdout
    assert str(float(lon)) in listed.stdout
    assert lat in listed_json.stdout
    above_debug = [r.getMessage() for r in caplog.records if r.levelno > logging.DEBUG]
    assert above_debug
    assert not [message for message in above_debug if leaks(message, coordinates)]
    # The point left the machine for api.weather.gov and, once, for Nominatim only.
    carrying = [url for url in sent if f"{float(lat):.4f}" in url]
    assert {url.split("/")[2] for url in carrying} == {
        "api.weather.gov",
        "nominatim.openstreetmap.org",
    }
    assert sum("nominatim" in url for url in carrying) == 1


def _renderings(value: float) -> set[str]:
    """How a distance or a bearing could be written: whole, and to one or two decimals."""
    written = {repr(value), f"{value:.1f}", f"{value:.2f}"}
    whole = f"{value:.0f}"
    # A short whole number also counts answers and records; three digits or more locate.
    return written | ({whole} if len(whole) >= 3 else set())  # noqa: PLR2004


def test_status_logs_no_coordinate_and_no_distance_above_debug(
    coordinates: tuple[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    lat, lon = coordinates
    with recorded_services():
        added = run(["locations", "add", NAME, "--lat", lat, "--lon", lon])
        first = run(["status"])
        second = run(["status", "--json"])

    assert added.exit_code == 0, added.stderr
    assert first.exit_code == 0, first.stderr
    assert second.exit_code == 0, second.stderr
    assessments = [stored.assessment for stored in history(NAME)]
    assert len(assessments) == 2  # noqa: PLR2004 - each run fetched its own snapshot
    measured = [
        value
        for assessment in assessments
        for threat in assessment.threats
        for value in (
            threat.distance_km,
            threat.bearing_deg,
            threat.closest_approach_km,
            threat.lead_h,
        )
        if value is not None
    ]
    measured += [
        value
        for assessment in assessments
        for value in (
            *(p.distance_km for p in assessment.official),
            *(e.distance_km for e in assessment.evidence),
        )
        if value is not None
    ]
    assert measured, "the recorded storm gives the location a distance and a bearing"
    renderings = set[str]().union(*(_renderings(value) for value in measured))
    # A whole number, not a run of digits inside another, such as the 4326 of EPSG:4326.
    written = [re.compile(rf"(?<![\d.]){re.escape(value)}(?![\d])") for value in renderings]
    above_debug = [r.getMessage() for r in caplog.records if r.levelno > logging.DEBUG]
    assessed = [message for message in above_debug if "level" in message]
    assert assessed, "the assessment service logs each location's level at INFO"
    assert not [message for message in above_debug if leaks(message, coordinates)]
    assert not [
        (message, pattern.pattern)
        for message in above_debug
        for pattern in written
        if pattern.search(message)
    ]


def test_the_cli_handler_redacts_a_coordinate_any_logger_writes_above_debug(
    coordinates: tuple[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    lat, lon = coordinates
    configure_logging("INFO")
    logging.getLogger("elsewhere").info("GET https://api.weather.gov/points/%s,%s", lat, lon)
    logging.getLogger("elsewhere").warning("lat=%s&lon=%s", lat, lon)
    logging.getLogger("elsewhere").debug("at DEBUG: %s,%s", lat, lon)

    written = capsys.readouterr().err
    assert "points/<redacted>" in written
    assert "lat=<redacted>&lon=<redacted>" in written
    assert not leaks(written, coordinates)
    assert "at DEBUG" not in written


def test_httpx_and_alembic_stay_quiet_unless_verbose() -> None:
    configure_logging("INFO")
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("alembic").level == logging.WARNING
    configure_logging("DEBUG")
    assert logging.getLogger("httpx").level == logging.DEBUG
    handlers = [
        h for h in logging.getLogger().handlers if type(h).__name__ == "StandardErrorHandler"
    ]
    assert len(handlers) == 1
    configure_logging("WARNING")
