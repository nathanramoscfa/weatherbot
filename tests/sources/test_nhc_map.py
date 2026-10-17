# tests/sources/test_nhc_map.py
"""Tests of the NHC map clients over the recorded captures of all four queried services."""

import copy
import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from fixture_support import as_list, as_object
from source_support import (
    Quiet,
    entry,
    layer_name,
    recorded,
    recorded_result,
    recorded_storms,
    serve,
)

from weatherbot.models import (
    AdvisoryNumber,
    ArrivalTimeProduct,
    Breakpoint,
    ConeGeometry,
    DisplayLayer,
    DomainModel,
    MapCatalog,
    Provenance,
    RosterProduct,
    StormSummary,
    TrackPoint,
    WindProbabilityProduct,
    WindRadii,
)
from weatherbot.sources import nhc_map
from weatherbot.sources.arcgis import (
    BREAKPOINTS,
    PEAK_SURGE,
    TROPICAL_SUMMARY,
    TROPICAL_WEATHER,
    MapService,
    feature_collection,
    parse_catalog,
)
from weatherbot.sources.drift import DRIFT_ATTRIBUTE
from weatherbot.sources.errors import SourceSchemaError

ADVISORY_ISSUED = datetime(2026, 10, 13, tzinfo=UTC)
ARRIVAL_ISSUED = datetime(2026, 10, 12, 21, tzinfo=UTC)
EARLIEST = "Earliest Reasonable Arrival Time"
BREAKPOINT_COUNT = 549
CONE_PERIOD_H = 120
FIELD_RADII = 3
ARRIVAL_LINES = 7
THRESHOLDS = (34, 50, 64)
BANDS = 11
TRACK_POINTS = 8
SEGMENTS = 2
RADII = 24
DISPLAY_COUNT = 3
OUTLOOK_AREAS = 6
STORM_QUERIES = 8
SYNOPTIC = datetime(2026, 10, 12, 18, tzinfo=UTC)


def _collection(service: MapService, layer: str) -> tuple[dict[str, object], Provenance]:
    """Return a deep copy of a recorded layer's FeatureCollection and its provenance."""
    directory = recorded(service.source_id)
    item = next(i for i in directory.entries if layer_name(i) == layer)
    result = recorded_result(directory, item)
    return copy.deepcopy(dict(feature_collection(result, layer))), result.provenance()


def _parse(
    service: MapService, layer: str, storms: tuple[StormSummary, ...] | None = None
) -> tuple[DomainModel, ...]:
    collection, provenance = _collection(service, layer)
    return nhc_map.parse_layer(
        layer, collection, provenance, recorded_storms() if storms is None else storms
    )


def _typed[T: DomainModel](
    kind: type[T],
    service: MapService,
    layer: str,
    storms: tuple[StormSummary, ...] | None = None,
) -> list[T]:
    records = _parse(service, layer, storms)
    assert all(isinstance(record, kind) for record in records)
    return [record for record in records if isinstance(record, kind)]


def _drift(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if hasattr(r, DRIFT_ATTRIBUTE)]


@pytest.mark.parametrize("service", [TROPICAL_SUMMARY, TROPICAL_WEATHER], ids=lambda s: s.name)
def test_every_recorded_capture_parses(
    service: MapService, caplog: pytest.LogCaptureFixture
) -> None:
    directory = recorded(service.source_id)
    storms = recorded_storms()
    parsed: dict[str, int] = {}
    for item in directory.entries:
        layer = layer_name(item)
        if layer is None or str(item["file"]).startswith("count-"):
            continue
        base = nhc_map.base_layer_name(layer)
        if base not in nhc_map.FIELDS_READ and base not in nhc_map.DISPLAY_LAYERS:
            continue  # the register's "not used in 2.0" and doctor-only layers
        result = recorded_result(directory, item)
        records = nhc_map.parse_layer(
            layer, feature_collection(result, layer), result.provenance(), storms
        )
        parsed[base] = len(records)
    assert parsed == {
        "Two-Day: Current Location": 2,
        "Seven-Day: Current Location": 2,
        "Seven-Day: Development Motion": 0,
        "Seven-Day: Potential Development Region": 2,
        "Forecast Points": 8,
        "Forecast Track": 1,
        "Forecast Cone": 1,
        "Watch-Warning": 2,
        "Past Points": 1,
        "Past Track": 1,
        "Past Cumulative Wind Swath": 1,
        "Forecast Wind Radii": 21,
        "Advisory Wind Field": 3,
        "Earliest Reasonable Arrival Time": 1,
        "Most Likely Arrival Time": 1,
        "Probabilistic Winds 34 kts": 1,
        "Probabilistic Winds 50 kts": 1,
        "Probabilistic Winds 64 kts": 1,
    }
    assert _drift(caplog) == []


def test_the_recorded_breakpoints_and_peak_surge_parse() -> None:
    breakpoints = _typed(Breakpoint, BREAKPOINTS, "Watch_Warning_Breakpoints")
    assert len(breakpoints) == BREAKPOINT_COUNT
    for name in nhc_map.PEAK_SURGE_LAYERS:
        (layer,) = _typed(DisplayLayer, PEAK_SURGE, name)
        assert layer.feature_collection["features"] == []


def test_breakpoints_take_their_position_from_lat_and_lon() -> None:
    collection, _ = _collection(BREAKPOINTS, "Watch_Warning_Breakpoints")
    first = as_object(as_object(as_list(collection["features"])[0])["properties"])
    point = _typed(Breakpoint, BREAKPOINTS, "Watch_Warning_Breakpoints")[0]
    assert point.position.coordinates == (first["lon"], first["lat"])
    assert point.position.crs.name == "EPSG:4326"


def test_the_cone_takes_its_issuance_from_the_roster() -> None:
    (cone,) = _typed(ConeGeometry, TROPICAL_SUMMARY, "Forecast Cone")
    advisory = cone.advisory
    assert advisory.number == AdvisoryNumber.parse("22A")
    assert advisory.issued_at == ADVISORY_ISSUED
    assert advisory.issued_at_source == "roster"
    assert advisory.local_text == "500 PM MST Mon Oct 12 2026"
    assert cone.forecast_period_h == CONE_PERIOD_H
    assert cone.geometry.crs.name == "EPSG:4326"


def test_forecast_points_are_timed_from_the_synoptic_time_and_drop_9999() -> None:
    points = _typed(TrackPoint, TROPICAL_SUMMARY, "Forecast Points")
    first, second = points[0], points[1]
    assert (first.tau_h, first.valid_at) == (0, datetime(2026, 10, 12, 21, tzinfo=UTC))
    assert (second.tau_h, second.valid_at) == (12, datetime(2026, 10, 13, 6, tzinfo=UTC))
    assert (second.mslp_mb, second.direction_deg, second.speed_kt) == (None, None, None)
    assert (first.max_wind_kt, first.speed_kt) == (85, 3)


def test_wind_radii_and_the_advisory_wind_field() -> None:
    radii = _typed(WindRadii, TROPICAL_SUMMARY, "Forecast Wind Radii")
    field = _typed(WindRadii, TROPICAL_SUMMARY, "Advisory Wind Field")
    assert {r.threshold_kt for r in radii} == {34, 50, 64}
    assert all(not r.is_advisory_field for r in radii)
    assert all(r.is_advisory_field and r.tau_h == 0 for r in field)
    assert all(r.synoptic_at == SYNOPTIC for r in (*radii, *field))


def test_the_advisory_wind_field_parses_without_idp_source() -> None:
    collection, provenance = _collection(TROPICAL_SUMMARY, "Advisory Wind Field")
    for feature in as_list(collection["features"]):
        del as_object(as_object(feature)["properties"])["idp_source"]
    records = nhc_map.parse_wind_radii(
        "Advisory Wind Field",
        collection,
        provenance,
        recorded_storms(),
    )
    assert len(records) == FIELD_RADII


def test_arrival_lines_are_label_only_and_dated_by_the_roster() -> None:
    (earliest,) = _typed(ArrivalTimeProduct, TROPICAL_SUMMARY, EARLIEST)
    assert earliest.origin == "map_layer"
    assert earliest.kind == "earliest_reasonable"
    assert earliest.advisory.number == AdvisoryNumber.parse("22")
    assert earliest.advisory.issued_at == ARRIVAL_ISSUED
    assert earliest.advisory.local_text is None
    assert earliest.time_zone is None
    assert earliest.published_at is None
    assert len(earliest.lines) == ARRIVAL_LINES
    assert sum(line.is_outer_contour for line in earliest.lines) == 1
    assert all(line.valid_at is None for line in earliest.lines)


def test_the_probabilistic_winds_are_three_snapshot_products_with_no_storm() -> None:
    products = [
        product
        for layer in nhc_map.WIND_PROBABILITY_THRESHOLDS
        for product in _typed(WindProbabilityProduct, TROPICAL_SUMMARY, layer)
    ]
    assert len(products) == len(THRESHOLDS)
    for product, threshold in zip(products, THRESHOLDS, strict=True):
        assert product.threshold_kt == threshold
        assert product.synoptic_at == SYNOPTIC
        assert len(product.bands) == BANDS
    assert "atcf_id" not in WindProbabilityProduct.model_fields
    assert "storm" not in " ".join(WindProbabilityProduct.model_fields)


def test_a_wind_probability_issuance_mismatch_is_source_drift(
    caplog: pytest.LogCaptureFixture,
) -> None:
    (product,) = _typed(WindProbabilityProduct, TROPICAL_SUMMARY, "Probabilistic Winds 34 kts")
    storm = recorded_storms()[0].model_copy(
        update={"wind_speed_probabilities_issued_at": SYNOPTIC - timedelta(hours=6)}
    )
    nhc_map.check_wind_probability_issuance([product], [storm])
    (message,) = _drift(caplog)
    assert "EP202026" in message
    nhc_map.check_wind_probability_issuance([product], recorded_storms())
    assert len(_drift(caplog)) == 1


def test_bands_of_two_synoptic_times_break_the_schema() -> None:
    collection, provenance = _collection(TROPICAL_SUMMARY, "Probabilistic Winds 34 kts")
    properties = as_object(as_object(as_list(collection["features"])[1])["properties"])
    properties["idp_source"] = "2026101212_wsp34knt120hr_5km"
    with pytest.raises(SourceSchemaError, match="2 synoptic times"):
        nhc_map.parse_wind_probabilities("Probabilistic Winds 34 kts", collection, provenance)


def _storm_with(**changes: object) -> tuple[StormSummary, ...]:
    return (recorded_storms()[0].model_copy(update=changes),)


def test_a_roster_issuance_more_than_an_hour_off_is_kept_with_a_drift_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    moved = ADVISORY_ISSUED + timedelta(hours=2)
    storms = _storm_with(
        track_cone=RosterProduct(advisory=AdvisoryNumber.parse("22A"), issued_at=moved)
    )
    (cone,) = _typed(ConeGeometry, TROPICAL_SUMMARY, "Forecast Cone", storms)
    assert cone.advisory.issued_at == moved
    (message,) = _drift(caplog)
    assert "more than an hour" in message


def test_a_roster_naming_another_advisory_leaves_the_local_text_to_date_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    storms = _storm_with(
        track_cone=RosterProduct(
            advisory=AdvisoryNumber.parse("23"), issued_at=ADVISORY_ISSUED + timedelta(hours=3)
        )
    )
    (cone,) = _typed(ConeGeometry, TROPICAL_SUMMARY, "Forecast Cone", storms)
    assert cone.advisory.issued_at == ADVISORY_ISSUED
    assert cone.advisory.issued_at_source == "local_text"
    assert len(_drift(caplog)) == 1


def test_arrival_lines_of_another_advisory_than_the_rosters_are_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    storms = _storm_with(
        earliest_arrival_kmz=RosterProduct(
            advisory=AdvisoryNumber.parse("23"), issued_at=ARRIVAL_ISSUED + timedelta(hours=6)
        )
    )
    assert _parse(TROPICAL_SUMMARY, "Earliest Reasonable Arrival Time", storms) == ()
    assert len(_drift(caplog)) == 1


def test_features_of_a_slot_the_roster_lacks_are_skipped(caplog: pytest.LogCaptureFixture) -> None:
    assert _parse(TROPICAL_SUMMARY, "Forecast Cone", ()) == ()
    assert "roster lacks" in _drift(caplog)[0]


def test_a_feature_naming_another_storm_in_the_slot_is_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    storms = _storm_with(atcf_id="EP212026")
    assert _parse(TROPICAL_SUMMARY, "Forecast Points", storms) == ()
    assert _drift(caplog)


def test_an_unknown_watch_warning_code_is_kept_unrecognized() -> None:
    collection, provenance = _collection(TROPICAL_SUMMARY, "Watch-Warning")
    as_object(as_object(as_list(collection["features"])[0])["properties"])["tcww"] = "SSW"
    first, _ = nhc_map.parse_watch_warnings(
        "Watch-Warning", collection, provenance, recorded_storms()
    )
    assert (first.tcww.raw, first.tcww.recognized) == ("SSW", False)


def test_a_layer_v2_does_not_read_has_no_parser() -> None:
    _, provenance = _collection(TROPICAL_SUMMARY, "Forecast Cone")
    with pytest.raises(ValueError, match="parses no layer"):
        nhc_map.parse_layer(
            "Past Wind Radii", {"type": "FeatureCollection", "features": []}, provenance
        )


def _catalog(service: MapService) -> MapCatalog:
    directory = recorded(service.source_id)
    return parse_catalog(recorded_result(directory, entry(directory, "catalog.json")), service)


@pytest.mark.anyio
@pytest.mark.parametrize("service", [TROPICAL_SUMMARY, TROPICAL_WEATHER], ids=lambda s: s.name)
async def test_both_tropical_services_fetch_the_same_products(
    service: MapService, caplog: pytest.LogCaptureFixture
) -> None:
    storms = recorded_storms()
    with respx.mock(assert_all_called=False) as router:
        serve(router, recorded(service.source_id))
        async with httpx.AsyncClient() as client:
            fetcher = Quiet().fetcher(client)
            catalog = _catalog(service)
            fetched = await nhc_map.fetch_storm_products(fetcher, catalog, storms)
            display = await nhc_map.fetch_storm_display_layers(fetcher, catalog, storms)
            outlook = await nhc_map.fetch_outlook(fetcher, catalog)
            winds = await nhc_map.fetch_wind_probabilities(fetcher, catalog, storms)
    (products,) = fetched.records
    assert products.summary.atcf_id == "EP202026"
    assert products.cone is not None
    assert products.track is not None
    assert len(products.track_points) == TRACK_POINTS
    assert len(products.watch_warnings) == SEGMENTS
    assert len(products.wind_radii) == RADII
    assert {a.kind for a in products.arrival_times} == {"earliest_reasonable", "most_likely"}
    assert len(display.records) == DISPLAY_COUNT
    assert len(outlook.records) == OUTLOOK_AREAS
    assert tuple(w.threshold_kt for w in winds.records) == THRESHOLDS
    assert len(fetched.responses) == STORM_QUERIES
    assert _drift(caplog) == []


@pytest.mark.anyio
async def test_no_storm_means_no_storm_request() -> None:
    with respx.mock(assert_all_called=False) as router:
        async with httpx.AsyncClient() as client:
            fetcher = Quiet().fetcher(client)
            catalog = _catalog(TROPICAL_SUMMARY)
            result = await nhc_map.fetch_storm_products(fetcher, catalog, ())
            display = await nhc_map.fetch_storm_display_layers(fetcher, catalog, ())
    assert (result.records, result.responses, display.records) == ((), (), ())
    assert not router.calls


@pytest.mark.anyio
async def test_breakpoints_and_peak_surge_fetch() -> None:
    with respx.mock(assert_all_called=False) as router:
        serve(router, recorded(BREAKPOINTS.source_id))
        serve(router, recorded(PEAK_SURGE.source_id))
        async with httpx.AsyncClient() as client:
            fetcher = Quiet().fetcher(client)
            breakpoints = await nhc_map.fetch_breakpoints(fetcher, _catalog(BREAKPOINTS))
            surge = await nhc_map.fetch_peak_surge(fetcher, _catalog(PEAK_SURGE))
    assert len(breakpoints.records) == BREAKPOINT_COUNT
    assert [layer.layer_name for layer in surge.records] == ["Points", "Lines", "Polygons"]


def test_two_cones_for_one_storm_break_the_schema() -> None:
    (cone,) = _parse(TROPICAL_SUMMARY, "Forecast Cone")
    with pytest.raises(SourceSchemaError, match="2 forecast cones"):
        nhc_map.assemble_storm_products(recorded_storms(), [cone, cone])


def test_drift_warnings_are_logged_on_the_sources_logger(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="weatherbot.sources")
    _parse(TROPICAL_SUMMARY, "Forecast Cone", ())
    (record,) = [r for r in caplog.records if hasattr(r, DRIFT_ATTRIBUTE)]
    assert record.name == "weatherbot.sources"
    assert getattr(record, DRIFT_ATTRIBUTE) == "nhc-map-tropical-summary"
