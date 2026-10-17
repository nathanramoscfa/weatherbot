# tests/services/test_snapshots.py
"""The snapshot service's rules: KMZ supersession, drift collection, and what it stores."""

import logging

import httpx
import pytest
from cli_support import directory, quiet_fetcher, recorded_services
from snapshot_support import ARCHIVE, dorian
from source_support import NOW, entry, recorded_result

from check_personal_data import load_landmarks, synthetic_coordinates
from weatherbot.models import Advisory, ArrivalTimeLine, ArrivalTimeProduct, StormProducts
from weatherbot.services.config import AppPaths
from weatherbot.services.logs import collect_drift, configure_logging
from weatherbot.services.network import Network, product_key
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import DriftWarning, SnapshotRepository
from weatherbot.services.snapshots import SNAPSHOT_SOURCES, SnapshotService, merge_arrivals
from weatherbot.sources.drift import warn_drift
from weatherbot.sources.http import FetchResult
from weatherbot.sources.nhc_arrival_times import parse_arrival_kmz
from weatherbot.sources.nominatim import reverse_url
from weatherbot.sources.nws import point_alerts_url, points_url


def _kmz(kind: str) -> ArrivalTimeProduct:
    capture = directory("nhc-arrival-times")
    result = recorded_result(capture, entry(capture, ARCHIVE.format(kind=kind).rsplit("/", 1)[1]))
    return parse_arrival_kmz(result.body, result.provenance(), dorian())


def _map_layer(product: ArrivalTimeProduct) -> ArrivalTimeProduct:
    return ArrivalTimeProduct(
        atcf_id=product.atcf_id,
        advisory=Advisory(
            atcf_id=product.atcf_id,
            number=product.advisory.number,
            issued_at=product.advisory.issued_at,
            local_text=None,
            issued_at_source="roster",
        ),
        provenance=product.provenance,
        kind=product.kind,
        time_zone=None,
        published_at=None,
        published_local_text=None,
        origin="map_layer",
        lines=tuple(
            ArrivalTimeLine.resolve(line.label, line.geometry, origin="map_layer")
            for line in product.lines
        ),
    )


def test_a_kmz_product_supersedes_the_map_layer_product_of_its_storm_advisory_and_kind() -> None:
    earliest, likely = _kmz("earliest_reasonable"), _kmz("most_likely")
    storm = StormProducts(
        summary=dorian(), arrival_times=(_map_layer(earliest), _map_layer(likely))
    )

    merged = merge_arrivals(storm, [earliest])

    assert merged == (earliest, _map_layer(likely))
    assert [p.origin for p in merge_arrivals(storm, [earliest, likely])] == ["kmz", "kmz"]


def test_the_map_layer_product_stays_when_the_kmz_failed() -> None:
    earliest = _kmz("earliest_reasonable")
    storm = StormProducts(summary=dorian(), arrival_times=(_map_layer(earliest),))

    assert merge_arrivals(storm, []) == (_map_layer(earliest),)


def test_drift_is_collected_even_when_the_log_level_hides_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("ERROR")
    with collect_drift() as collector:
        warn_drift("nhc-text-products", "the TCP names another storm")
    logging.getLogger("weatherbot.sources").warning("not drift")

    assert collector.warnings == [DriftWarning("nhc-text-products", "the TCP names another storm")]
    assert capsys.readouterr().err == ""
    configure_logging("WARNING")


def test_a_product_key_never_holds_a_coordinate() -> None:
    lat, lon = (float(value) for value in synthetic_coordinates(load_landmarks(), (), seed=9))

    def key(url: str) -> str:
        return product_key(FetchResult("nws-alerts-point", url, 200, b"", {}, NOW, "0" * 64))

    assert key(point_alerts_url(lat, lon)) == "/alerts/active?point=<redacted>"
    assert key(points_url(lat, lon)) == "/points/<redacted>"
    assert key(reverse_url(lat, lon)) == ("/reverse?format=jsonv2&lat=<redacted>&lon=<redacted>")
    assert key("https://www.nhc.noaa.gov/CurrentStorms.json") == "/CurrentStorms.json"


@pytest.mark.anyio
async def test_a_fetched_snapshot_is_stored_with_its_answers_and_drift() -> None:
    paths = AppPaths.resolve()
    with recorded_services(), open_database(paths) as database:
        service = SnapshotService(
            database.engine, network=Network(make_fetcher=quiet_fetcher), now=lambda: NOW
        )
        fetched = await service.fetch_snapshot([])
        stored = service.latest_drift_warnings()
        loaded = SnapshotRepository(database.engine).load(fetched.snapshot.snapshot_id)

    assert loaded == fetched.snapshot
    assert [o.source_id for o in fetched.snapshot.source_outcomes] == list(SNAPSHOT_SOURCES)
    assert stored == (fetched.snapshot.snapshot_id, fetched.drift_warnings)
    assert all(not warning.message.startswith("Source drift") for warning in fetched.drift_warnings)
    assert fetched.snapshot.alerts == {}


@pytest.mark.anyio
async def test_a_failed_roster_skips_the_storm_sources_and_fails_the_snapshot() -> None:
    roster = "https://www.nhc.noaa.gov/CurrentStorms.json"
    with (
        recorded_services(overrides={roster: httpx.Response(503)}),
        open_database(AppPaths.resolve()) as database,
    ):
        service = SnapshotService(
            database.engine, network=Network(make_fetcher=quiet_fetcher), now=lambda: NOW
        )
        snapshot = (await service.fetch_snapshot([])).snapshot

    outcomes = {o.source_id: o for o in snapshot.source_outcomes}
    assert snapshot.status == "failed"
    assert outcomes["nhc-current-storms"].error_kind == "unavailable"
    assert outcomes["nhc-arrival-times"].reason == "the storm roster failed"
    assert outcomes["nhc-map-tropical-summary"].status == "ok"
    assert snapshot.storms == ()
    assert snapshot.outlook_areas
