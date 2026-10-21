# tests/cli/test_commands.py
"""Every command through Typer's runner, offline, against the recorded answers.

Each test runs in its own temporary data directory (the isolation fixture), so the first
command of a test creates the database and shows the disclaimer. Every ``--json``
document is validated against its committed schema before it is read.
"""

import json
import re
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cli_support import (
    MIAMI,
    NASSAU,
    SUMMARY_CATALOG,
    add_landmark,
    county_statement,
    parse,
    recorded_services,
    run,
    runtime,
    urls,
)
from source_support import NOW, recorded_roster_document

from weatherbot.cli.documents import (
    AlertsDocument,
    DoctorDocument,
    FetchDocument,
    LocationsDocument,
    SnapshotInfo,
    StormsDocument,
)
from weatherbot.models import SourceOutcome
from weatherbot.services.config import AppPaths
from weatherbot.services.disclaimer import NOTICE, SHOWN_AT_KEY
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import SettingsRepository, SnapshotRepository

UNAVAILABLE = httpx.Response(503, headers={"content-type": "text/plain"})
USAGE = 2


def _empty_roster() -> bytes:
    document = recorded_roster_document()
    document["activeStorms"] = []
    return json.dumps(document).encode()


def _outcomes(snapshot: SnapshotInfo) -> dict[str, SourceOutcome]:
    return {outcome.source_id: outcome for outcome in snapshot.source_outcomes}


# locations ---------------------------------------------------------------------------------


def test_locations_add_list_and_remove_round_trip() -> None:
    with recorded_services():
        added = add_landmark(MIAMI, "miami-dade")
        outside = add_landmark(NASSAU, "nassau")
    listed = run(["locations", "list"])
    document = parse(run(["locations", "list", "--json"]), LocationsDocument)
    removed = run(["locations", "remove", NASSAU])
    after = parse(run(["locations", "list", "--json"]), LocationsDocument)

    assert added.exit_code == 0
    assert "NWS MFL, zones FLZ173 and FLC086" in added.stdout
    assert outside.exit_code == 0
    assert "outside NWS coverage" in outside.stdout
    assert listed.exit_code == 0
    assert MIAMI in listed.stdout
    assert listed.stdout.rstrip().endswith(NOTICE)
    assert [location.name for location in document.data.locations] == [MIAMI, NASSAU]
    assert document.data.locations[1].nws is None
    assert document.data.locations[1].country_code == "BS"
    assert removed.exit_code == 0
    assert [location.name for location in after.data.locations] == [MIAMI]


def test_locations_add_stores_a_zone_polygon_for_a_us_location() -> None:
    with recorded_services():
        added = add_landmark(MIAMI, "miami-dade", "--polygon", "county")
    listed = parse(run(["locations", "list", "--json"]), LocationsDocument)

    assert added.exit_code == 0
    assert listed.data.locations[0].has_polygon is True


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["", "--lat", "1", "--lon", "1"], "1 to 64 printable characters"),
        (["x" * 65, "--lat", "1", "--lon", "1"], "1 to 64 printable characters"),
        (["Tab\there", "--lat", "1", "--lon", "1"], "1 to 64 printable characters"),
        (["Here", "--lat", "91", "--lon", "1"], "latitude must be a number from -90 to 90"),
        (["Here", "--lat", "nan", "--lon", "1"], "latitude must be a number from -90 to 90"),
        (["Here", "--lat", "1", "--lon", "-180.5"], "longitude must be a number from -180"),
    ],
)
def test_locations_add_refuses_a_bad_name_or_point_before_any_request(
    args: list[str], message: str
) -> None:
    with recorded_services() as router:
        result = run(["locations", "add", *args])
        sent = urls(router)

    assert result.exit_code == USAGE
    assert message in result.stderr
    assert sent == []


def test_locations_add_refuses_a_taken_name_and_a_polygon_outside_the_us() -> None:
    with recorded_services() as router:
        add_landmark(MIAMI, "miami-dade")
        before = len(urls(router))
        again = add_landmark(MIAMI, "miami-dade")
        assert len(urls(router)) == before
        outside = add_landmark(NASSAU, "nassau", "--polygon", "forecast")
        later = urls(router)[before:]

    assert again.exit_code == USAGE
    assert "already exists" in again.stderr
    assert outside.exit_code == USAGE
    assert "does not cover" in outside.stderr
    assert any("/points/" in url for url in later)
    assert not any("nominatim" in url for url in later)


def test_locations_remove_of_an_unknown_name_is_a_usage_error() -> None:
    result = run(["locations", "remove", "Nowhere"])

    assert result.exit_code == USAGE
    assert "no location is named 'Nowhere'" in result.stderr


def test_locations_evacuation_sets_and_clears_the_toggle_with_its_instant() -> None:
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
    on = run(["locations", "evacuation", MIAMI, "on"])
    again = run(["locations", "evacuation", MIAMI, "on"], runtime(now=NOW + timedelta(hours=1)))
    listed = parse(run(["locations", "list", "--json"]), LocationsDocument)
    table = run(["locations", "list"])
    off = run(["locations", "evacuation", MIAMI, "off"], runtime(now=NOW + timedelta(hours=2)))
    cleared = parse(run(["locations", "list", "--json"]), LocationsDocument)

    assert on.exit_code == 0, on.stderr
    assert (
        f"The evacuation-order toggle of '{MIAMI}' is on since 2026-10-13 01:30 UTC "
        "(2026-10-12 21:30 EDT)." in on.stdout
    )
    assert "holds 'Miami-Dade County Hall' at level 4 (Warning / Watch / Evacuation) or above" in (
        on.stdout
    )
    assert f"weatherbot locations evacuation '{MIAMI}' off" in on.stdout
    assert "The next weatherbot status, which fetches a snapshot, assesses with it." in on.stdout
    assert "is already on since 2026-10-13 01:30 UTC" in again.stdout
    (entry,) = listed.data.locations
    assert (entry.evacuation_order_in_effect, entry.evacuation_order_set_at) == (True, NOW)
    assert "on since 2026-10-13 01:30 UTC (2026-10-12 21:30 EDT)" in table.stdout
    assert off.exit_code == 0
    assert "is off since 2026-10-13 03:30 UTC" in off.stdout
    assert "is no longer held at level 4" in off.stdout
    (entry,) = cleared.data.locations
    assert entry.evacuation_order_in_effect is False
    assert entry.evacuation_order_set_at == NOW + timedelta(hours=2)


@pytest.mark.parametrize("args", [["Nowhere", "on"], [MIAMI, "maybe"]])
def test_locations_evacuation_of_an_unknown_name_or_state_is_a_usage_error(
    args: list[str],
) -> None:
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")

    result = run(["locations", "evacuation", *args])

    assert result.exit_code == USAGE


def test_locations_list_shows_the_span_once_status_finds_it() -> None:
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        add_landmark(NASSAU, "nassau")
        before = parse(run(["locations", "list", "--json"]), LocationsDocument)
        run(["status"])
    after = parse(run(["locations", "list", "--json"]), LocationsDocument)
    table = run(["locations", "list"])

    assert [entry.breakpoint_span for entry in before.data.locations] == [None, None]
    miami, nassau = after.data.locations
    assert miami.breakpoint_span is not None
    assert miami.breakpoint_span.names == ("Ocean Reef", "Miami-Dade/Broward County Line")
    assert nassau.breakpoint_span is not None
    assert nassau.breakpoint_span.is_region
    assert "Ocean Reef to Miami-Dade/Broward County Line (United States)" in table.stdout
    assert "Bahamas (NW)" in table.stdout


def test_locations_list_without_locations_says_how_to_add_one() -> None:
    result = run(["locations", "list"])

    assert result.exit_code == 0
    assert "weatherbot locations add NAME --lat LAT --lon LON" in result.stdout


# the disclaimer ----------------------------------------------------------------------------


def test_the_first_command_shows_the_disclaimer_once_and_records_the_time() -> None:
    first = run(["locations", "list"])
    second = run(["locations", "list"])
    with open_database(AppPaths.resolve()) as database:
        shown = SettingsRepository(database.engine).get(SHOWN_AT_KEY)

    assert first.stdout.startswith("DISCLAIMER\nWeatherbot is informational only.")
    assert "DISCLAIMER\n" not in second.stdout
    assert second.stdout.rstrip().endswith(NOTICE)
    assert shown == NOW.isoformat()


def test_under_json_the_disclaimer_goes_to_standard_error() -> None:
    result = run(["locations", "list", "--json"])
    document = parse(result, LocationsDocument)

    assert "DISCLAIMER\nWeatherbot is informational only." in result.stderr
    assert document.disclaimer == NOTICE
    assert result.stdout.lstrip().startswith("{")


# fetch -------------------------------------------------------------------------------------


def test_fetch_stores_a_complete_snapshot_and_prints_every_outcome() -> None:
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        add_landmark(NASSAU, "nassau")
        result = run(["fetch"])
        ran = run(["fetch", "--json"])
    document = parse(ran, FetchDocument)

    assert result.exit_code == 0, result.stderr
    assert ": complete." in result.stdout
    for source in ("nhc-current-storms", "nhc-arrival-times", "nws-alerts-zone"):
        assert f"{source} " in result.stdout
    assert result.stdout.rstrip().endswith(NOTICE)
    assert ran.exit_code == 0
    assert document.snapshot.status == "complete"
    assert document.data.alerts == {MIAMI: 1}
    assert document.data.counts.storms == 1
    # The stand-in KMZ's advisory disagrees with its URL: the run's Source drift.
    assert {warning.source_id for warning in document.data.drift_warnings} == {"nhc-arrival-times"}


def test_a_source_answering_503_makes_a_partial_snapshot_that_exits_1() -> None:
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        complete = run(["fetch"])
    with recorded_services(overrides={SUMMARY_CATALOG: UNAVAILABLE}):
        partial = run(["fetch"])
        fetched = run(["fetch", "--json"])
        storms_ran = run(["storms", "--json"])
    document = parse(fetched, FetchDocument)
    storms = parse(storms_ran, StormsDocument)

    assert complete.exit_code == 0
    assert partial.exit_code == 1
    assert ": partial." in partial.stdout
    assert "nhc-map-tropical-summary failed (unavailable); its part is empty." in partial.stdout
    assert "nhc-map-tropical-summary  failed   unavailable" in partial.stdout
    assert fetched.exit_code == 1
    outcomes = _outcomes(document.snapshot)
    assert outcomes["nhc-map-tropical-summary"] == SourceOutcome(
        source_id="nhc-map-tropical-summary", status="failed", error_kind="unavailable"
    )
    assert outcomes["nhc-current-storms"].status == "ok"
    # Nothing from the earlier, complete snapshot fills the failed source's part.
    assert storms_ran.exit_code == 1
    assert storms.data.outlook == ()
    assert storms.data.wind_probabilities == ()
    (storm,) = storms.data.storms
    assert storm.products.cone is False
    assert [a.origin for a in storm.products.arrival_times] == ["kmz", "kmz"]


def test_a_second_fetch_is_conditional_and_a_304_is_not_modified() -> None:
    def conditional(request: httpx.Request) -> httpx.Response:
        asked = "if-none-match" in request.headers or "if-modified-since" in request.headers
        return httpx.Response(304 if asked else 500)

    with recorded_services() as router:
        run(["fetch"])
        for feed in ("at", "ep", "cp"):
            router.get(f"https://www.nhc.noaa.gov/gis-{feed}.xml").mock(side_effect=conditional)
        ran = run(["fetch", "--json"], runtime(now=NOW + timedelta(minutes=10)))
    document = parse(ran, FetchDocument)
    with open_database(AppPaths.resolve()) as database:
        latest = SnapshotRepository(database.engine).latest()

    assert _outcomes(document.snapshot)["nhc-gis-rss"].status == "not_modified"
    assert ran.exit_code == 0
    assert latest is not None
    assert latest.snapshot_id == document.snapshot.snapshot_id
    assert latest.gis_feed_items


def test_fetch_without_us_locations_skips_the_alert_sources() -> None:
    with recorded_services() as router:
        add_landmark(NASSAU, "nassau")
        ran = run(["fetch", "--json"])
        sent = urls(router)
    outcomes = _outcomes(parse(ran, FetchDocument).snapshot)

    assert outcomes["nws-alerts-point"].status == "skipped"
    assert outcomes["nws-alerts-point"].reason == "no location inside NWS coverage"
    assert any("CurrentStorms" in url for url in sent)
    assert not any("/alerts/" in url for url in sent)


# storms ------------------------------------------------------------------------------------


def test_storms_prints_the_storm_its_products_the_outlook_and_the_synoptic_time() -> None:
    with recorded_services():
        result = run(["storms"])
        document = parse(run(["storms", "--json"]), StormsDocument)

    assert result.exit_code == 0, result.stderr
    assert "EP202026  Simon" in result.stdout
    assert "22A at 2026-10-13 00:00 UTC" in result.stdout
    assert "earliest reasonable arrival times (kmz, adv 22)" in result.stdout
    assert "Outlook: Atlantic" in result.stdout
    assert "of synoptic time 2026-10-12 18:00 UTC" in result.stdout
    assert result.stdout.rstrip().endswith(NOTICE)
    (storm,) = document.data.storms
    assert (storm.atcf_id, storm.advisory, storm.classification.raw) == ("EP202026", "22A", "HU")
    assert {p.threshold_kt for p in document.data.wind_probabilities} == {34, 50, 64}


def test_the_kmz_arrival_products_supersede_the_map_layer_ones() -> None:
    with recorded_services():
        document = parse(run(["storms", "--json"]), StormsDocument)

    (storm,) = document.data.storms
    assert [(a.kind, a.origin, a.advisory) for a in storm.products.arrival_times] == [
        ("earliest_reasonable", "kmz", "22"),
        ("most_likely", "kmz", "22"),
    ]


def test_storms_with_an_empty_roster_says_so_and_still_prints_the_outlook() -> None:
    with recorded_services(roster=_empty_roster()):
        result = run(["storms"])
        document = parse(run(["storms", "--json"]), StormsDocument)

    assert result.exit_code == 0, result.stderr
    assert "No active storm" in result.stdout
    assert "Outlook: Atlantic" in result.stdout
    assert document.data.storms == ()
    assert document.data.outlook
    assert _outcomes(document.snapshot)["nhc-arrival-times"].reason == "no active storm"


def test_storms_no_fetch_reads_the_latest_snapshot_and_prints_its_age() -> None:
    with recorded_services():
        run(["fetch"])
    later = runtime(now=NOW + timedelta(minutes=42))
    result = run(["storms", "--no-fetch"], later)
    document = parse(run(["storms", "--no-fetch", "--json"], later), StormsDocument)

    assert result.exit_code == 0
    assert ": complete, 42 min old." in result.stdout
    assert document.snapshot.age_seconds == 42 * 60


@pytest.mark.parametrize("command", ["storms", "alerts"])
def test_no_fetch_without_a_stored_snapshot_fails_with_advice(command: str) -> None:
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
    result = run([command, "--no-fetch"])

    assert result.exit_code == 1
    assert "no snapshot is stored yet; run weatherbot fetch first" in result.stderr


def test_storms_renders_rich_tables_in_a_terminal() -> None:
    with recorded_services():
        result = run(["storms"], runtime(terminal=True, width=200))

    assert result.exit_code == 0
    assert "Active storms" in result.stdout
    # Rich draws the header heavy on some consoles and light on others.
    assert re.search(r"[│┃] ATCF id\s+[│┃] Name", result.stdout)
    assert re.search(r"│ EP202026\s+│ Simon", result.stdout)


# alerts ------------------------------------------------------------------------------------


def test_alerts_for_a_us_location_print_its_alerts_in_utc_and_local_time() -> None:
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        result = run(["alerts"])
        document = parse(run(["alerts", "--json"]), AlertsDocument)

    assert result.exit_code == 0, result.stderr
    assert "Rip Current Statement" in result.stdout
    assert "  Covers this location: the point query returned it" in result.stdout
    assert "No NHC watch-warning segment covers it." in result.stdout
    assert "Effective 2026-10-17 07:40 UTC (2026-10-17 03:40 EDT)" in result.stdout
    assert "Found by  the point, FLC086, FLZ173" in result.stdout
    assert result.stdout.rstrip().endswith(NOTICE)
    assert document.data.alerts is not None
    (alert,) = document.data.alerts
    assert alert.effective_local == "2026-10-17T03:40:00-04:00"
    assert [query.kind for query in alert.found_by] == ["point", "zone", "zone"]
    assert alert.affected_zone_ids == ("FLZ168", "FLZ172", "FLZ173")
    assert (alert.covers, alert.rule) == (True, None)
    assert alert.coverage.startswith("the point query returned it")
    assert document.data.watch_warnings == ()


def test_alerts_mark_a_county_zone_alert_outside_the_location_s_zones() -> None:
    with recorded_services(overrides=county_statement()):
        add_landmark(MIAMI, "miami-dade")
        result = run(["alerts"])
        document = parse(run(["alerts", "--json"]), AlertsDocument)

    assert result.exit_code == 0, result.stderr
    assert (
        "Coastal Flood Statement\n  Does not cover this location: county-zone alert outside "
        "this location's zones"
    ) in result.stdout
    assert document.data.alerts is not None
    by_event = {alert.event: alert for alert in document.data.alerts}
    assert by_event["Coastal Flood Statement"].covers is False
    assert by_event["Rip Current Statement"].covers is True


def test_alerts_outside_nws_coverage_list_the_segments_covering_ones_first() -> None:
    with recorded_services() as router:
        add_landmark(NASSAU, "nassau")
        result = run(["alerts"])
        document = parse(run(["alerts", "--json"]), AlertsDocument)
        sent = urls(router)

    assert result.exit_code == 0, result.stderr
    assert "Parliament Square is outside NWS coverage" in result.stdout
    assert "Watch-warning segments of the active storms, those that cover it first" in (
        result.stdout
    )
    assert "Simon  EP202026  HWR   Hurricane Warning  22A       does not cover it" in result.stdout
    assert "Phase 3" not in result.stdout
    assert document.data.alerts is None
    assert {segment.tcww.raw for segment in document.data.watch_warnings} == {"HWA", "HWR"}
    assert not any(segment.covers for segment in document.data.watch_warnings)
    assert any("CurrentStorms" in url for url in sent)
    assert not any("/alerts/" in url for url in sent)


def test_alerts_needs_a_location_and_names_the_choices() -> None:
    none = run(["alerts"])
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        add_landmark(NASSAU, "nassau")
    several = run(["alerts"])
    unknown = run(["alerts", "--location", "Nowhere"])

    assert none.exit_code == USAGE
    assert "weatherbot locations add NAME --lat LAT --lon LON" in none.stderr
    assert several.exit_code == USAGE
    assert f"'{MIAMI}', '{NASSAU}'" in several.stderr
    assert unknown.exit_code == USAGE


def test_alerts_without_an_alert_list_for_the_location_exits_1() -> None:
    zone = "https://api.weather.gov/alerts/active/zone/FLC086"
    with recorded_services(overrides={zone: UNAVAILABLE}):
        add_landmark(MIAMI, "miami-dade")
        ran = run(["alerts", "--json"])
    document = parse(ran, AlertsDocument)

    assert ran.exit_code == 1
    assert document.data.alerts is None
    assert "alert sources failed" in str(document.data.note)
    assert _outcomes(document.snapshot)["nws-alerts-zone"].status == "failed"


# doctor ------------------------------------------------------------------------------------


def test_doctor_offline_reports_the_paths_the_head_and_the_locations() -> None:
    result = run(["doctor", "--offline"])
    document = parse(run(["doctor", "--offline", "--json"]), DoctorDocument)

    assert result.exit_code == 0, result.stdout
    assert "migrations  pass    at revision 0003, the head" in result.stdout
    assert "Offline: no source was probed." in result.stdout
    assert result.stdout.rstrip().endswith(NOTICE)
    assert document.data.database is not None
    assert document.data.database.at_head is True
    assert document.data.locations == 0
    assert document.data.probes == ()


def test_doctor_probes_every_register_source_and_discovers_every_layer() -> None:
    with recorded_services() as router:
        run(["fetch"])
        before = len(urls(router))
        result = run(["doctor"])
        document = parse(run(["doctor", "--json"]), DoctorDocument)
        probed = urls(router)[before:]

    assert result.exit_code == 0, result.stdout
    probes = {probe.source_id: probe for probe in document.data.probes}
    assert len(probes) == 19  # noqa: PLR2004 - every register source
    assert probes["geocode-nominatim"].status == "skip"
    assert "usage policy" in probes["geocode-nominatim"].detail
    assert probes["basemap-osm-tiles"].detail.startswith("display-only")
    assert probes["nhc-gis-archive"].detail.startswith("replay-only")
    layers = {layer.source_id: layer for layer in document.data.layers}
    assert layers["nhc-map-tropical-weather"].resolved == 400  # noqa: PLR2004 - 15 slots
    assert all(layer.missing == () for layer in layers.values())
    assert document.data.drift_warnings
    assert probed
    assert not [url for url in probed if "nominatim" in url or "/points/" in url]
    assert not [url for url in probed if "/alerts/" in url or "/zones/" in url]


def test_doctor_fails_on_an_unreachable_source() -> None:
    with recorded_services(overrides={SUMMARY_CATALOG: UNAVAILABLE}):
        ran = run(["doctor", "--json"])
    document = parse(ran, DoctorDocument)

    assert ran.exit_code == 1
    probes = {probe.source_id: probe for probe in document.data.probes}
    assert probes["nhc-map-tropical-summary"].status == "fail"
    assert probes["nhc-map-tropical-summary"].detail.startswith("unavailable: ")
    assert document.data.failed is True


def test_doctor_fails_on_a_database_at_an_unknown_revision() -> None:
    run(["doctor", "--offline"])
    paths = AppPaths.resolve()
    with open_database(paths) as database, database.engine.begin() as connection:
        connection.exec_driver_sql("UPDATE alembic_version SET version_num = '9999'")
    result = run(["doctor", "--offline"])

    assert result.exit_code == 1
    assert "database    fail" in result.stdout
    assert "revision 9999, which this version of Weatherbot does not know" in result.stdout
    assert "FAILED" in result.stdout


def test_doctor_reports_a_bad_settings_file() -> None:
    paths = AppPaths.resolve()
    paths.config_dir.mkdir(parents=True)
    paths.settings_path.write_text("[http]\ntimeout_seconds = 0\n", encoding="utf-8")
    result = run(["doctor", "--offline"])
    other = run(["locations", "list"])

    assert result.exit_code == 1
    assert "settings    fail    [http] timeout_seconds" in result.stdout
    assert other.exit_code == 1
    assert "[http] timeout_seconds" in other.stderr


def test_the_generated_at_of_a_document_is_the_runtime_clock() -> None:
    moment = datetime(2026, 10, 17, 12, tzinfo=UTC)
    document = parse(run(["doctor", "--offline", "--json"], runtime(now=moment)), DoctorDocument)

    assert document.generated_at == moment
