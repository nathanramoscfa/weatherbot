# tests/models/test_records.py
"""Each record's own rules: issue #11's arrival times, issue #12's probabilities, the snapshot."""

import gzip
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from model_samples import (
    ATCF_ID,
    FULL_TEXT,
    INTERMEDIATE_TEXT,
    REPOSITORY_ROOT,
    advisory,
    alert,
    alert_query,
    arrival_product,
    cone,
    feed_item,
    landmark_point,
    location,
    outcomes,
    outlook_area,
    provenance,
    recorded_geometry,
    snapshot,
    storm_products,
    summary,
    text_product,
    track_point,
    watch_warning,
    wind_product,
    wind_radii,
)
from pydantic import BaseModel, ValidationError

from weatherbot.models import (
    WGS84,
    Advisory,
    AdvisoryNumber,
    AlertQuery,
    ArrivalTimeLine,
    ArrivalTimeProduct,
    Crs,
    Geometry,
    GisFeedItem,
    Location,
    NwsAlert,
    OutlookArea,
    Snapshot,
    SourceOutcome,
    StormProducts,
    StormSummary,
    TextProduct,
    TrackPoint,
    WatchWarningSegment,
    WatchWarningType,
    WindProbabilityProduct,
    WindRadii,
)

MODELS_SOURCE = REPOSITORY_ROOT / "src/weatherbot/models"
ARRIVAL_LAYER = "query-ep5-earliest-reasonable-arrival-time.geojson"


def revalidate[M: BaseModel](model: M, **changes: object) -> M:
    """Validate ``model`` again from Python input with some fields changed."""
    return type(model).model_validate({**dict(model), **changes})


# Arrival times (issue #11)


def test_the_recorded_kmz_product_carries_its_zone_publication_and_instants() -> None:
    product = arrival_product()

    assert (product.time_zone, product.origin, product.published_local_text) == (
        "MST",
        "kmz",
        FULL_TEXT,
    )
    assert product.published_at == datetime(2026, 10, 12, 21, tzinfo=UTC)
    assert [line.valid_at for line in product.lines if not line.is_outer_contour] == [
        datetime(2026, 10, 13, 3, tzinfo=UTC),
        datetime(2026, 10, 13, 15, tzinfo=UTC),
        datetime(2026, 10, 14, 3, tzinfo=UTC),
        datetime(2026, 10, 14, 15, tzinfo=UTC),
        datetime(2026, 10, 15, 3, tzinfo=UTC),
        datetime(2026, 10, 15, 15, tzinfo=UTC),
    ]
    outer = [line for line in product.lines if line.is_outer_contour]
    assert [(line.label, line.valid_at, line.unresolved_reason) for line in outer] == [
        (None, None, None)
    ]


def test_a_map_layer_product_never_carries_a_zone_or_an_instant() -> None:
    lines = tuple(
        ArrivalTimeLine.resolve(line.label, line.geometry, origin="map_layer")
        for line in arrival_product().lines
    )
    fallback = revalidate(
        arrival_product(),
        origin="map_layer",
        time_zone=None,
        published_at=None,
        published_local_text=None,
        lines=lines,
    )

    assert all(line.valid_at is None for line in fallback.lines)
    assert {line.unresolved_reason for line in fallback.lines if line.label} == {
        "the map layer carries no date or time zone"
    }
    with pytest.raises(ValidationError, match="no zone"):
        revalidate(fallback, time_zone="MST")
    with pytest.raises(ValidationError, match="no zone"):
        revalidate(fallback, withheld_reason="drift")
    with pytest.raises(ValidationError, match="resolve_arrival_label"):
        revalidate(fallback, lines=arrival_product().lines)


def test_a_kmz_line_that_was_not_resolved_by_the_rule_is_rejected() -> None:
    product = arrival_product()
    first = product.lines[0].valid_at
    assert first is not None
    tampered = product.lines[0].model_copy(update={"valid_at": first + timedelta(days=7)})

    with pytest.raises(ValidationError, match="resolve_arrival_label"):
        revalidate(product, lines=(tampered, *product.lines[1:]))


def test_a_kmz_product_with_an_unknown_zone_keeps_every_line_unresolved() -> None:
    product = arrival_product()
    lines = tuple(
        ArrivalTimeLine.resolve(
            line.label,
            line.geometry,
            origin="kmz",
            published_at=product.published_at,
            time_zone="XYZ",
        )
        for line in product.lines
    )

    unknown = revalidate(product, time_zone="XYZ", lines=lines)

    assert all(line.valid_at is None for line in unknown.lines)
    assert all(
        "time zone" in (line.unresolved_reason or "") for line in unknown.lines if line.label
    )


def test_a_kmz_product_that_disagrees_with_the_roster_withholds_every_instant() -> None:
    product = arrival_product()
    reason = "the KMZ's advisoryNum disagrees with the roster"
    lines = tuple(
        ArrivalTimeLine.resolve(
            line.label,
            line.geometry,
            origin="kmz",
            published_at=product.published_at,
            time_zone=product.time_zone,
            withheld_reason=reason,
        )
        for line in product.lines
    )

    withheld = revalidate(product, withheld_reason=reason, lines=lines)

    assert {line.unresolved_reason for line in withheld.lines if line.label} == {reason}
    assert all(line.valid_at is None for line in withheld.lines)
    with pytest.raises(ValidationError, match="resolve_arrival_label"):
        revalidate(product, withheld_reason=reason)
    with pytest.raises(ValidationError, match="resolve_arrival_label"):
        revalidate(withheld, withheld_reason=None)


def test_an_arrival_product_belongs_to_a_full_advisory_and_its_own_text() -> None:
    with pytest.raises(ValidationError, match="full advisories"):
        revalidate(arrival_product(), advisory=advisory())
    with pytest.raises(ValidationError, match="published_local_text"):
        revalidate(arrival_product(), published_at=datetime(2026, 10, 12, 22, tzinfo=UTC))


def test_the_blank_recorded_label_is_the_outer_contour() -> None:
    blank = ArrivalTimeLine.resolve(" ", recorded_geometry(ARRIVAL_LAYER, 6), origin="kmz")

    assert (blank.label, blank.is_outer_contour, blank.valid_at) == (None, True, None)
    with pytest.raises(ValidationError):
        revalidate(blank, is_outer_contour=False)
    with pytest.raises(ValidationError, match="outer contour has no time"):
        revalidate(blank, unresolved_reason="none")


def test_an_arrival_line_is_a_line() -> None:
    with pytest.raises(ValidationError, match="arrival line"):
        ArrivalTimeLine.resolve(None, landmark_point(), origin="kmz")


# Wind probabilities (issue #12)


def test_wind_probabilities_have_no_storm_field_and_live_in_the_snapshot() -> None:
    fields = set(WindProbabilityProduct.model_fields)

    assert not {name for name in fields if "storm" in name or "atcf" in name or "advisory" in name}
    assert "wind_probabilities" in Snapshot.model_fields
    assert not any("wind_prob" in name for name in StormProducts.model_fields)
    assert not any(
        "wind_prob" in name for name in StormSummary.model_fields if "issued" not in name
    )
    assert snapshot().wind_probabilities == (wind_product(),)


def test_a_snapshot_holds_one_wind_probability_product_per_threshold() -> None:
    with pytest.raises(ValidationError, match="per threshold"):
        revalidate(snapshot(), wind_probabilities=(wind_product(), wind_product()))
    fifty = wind_product().model_copy(update={"threshold_kt": 50})

    both = revalidate(snapshot(), wind_probabilities=(wind_product(), fifty))

    assert [p.threshold_kt for p in both.wind_probabilities] == [34, 50]


def test_a_wind_probability_threshold_is_34_50_or_64() -> None:
    with pytest.raises(ValidationError):
        revalidate(wind_product(), threshold_kt=40)


# Storms and advisory products


def test_a_storm_s_slot_belongs_to_its_basin() -> None:
    with pytest.raises(ValidationError, match="slot"):
        revalidate(summary(), slot="AT5")
    with pytest.raises(ValidationError):
        revalidate(summary(), atcf_id="ep202026")


def test_the_roster_units_are_named_by_nhc_s_reference() -> None:
    fields = set(StormSummary.model_fields)

    assert {"intensity_kt", "pressure_mb", "movement_dir_deg", "movement_speed_mph"} <= fields
    assert {"max_wind_kt", "gust_kt", "mslp_mb", "direction_deg", "speed_kt"} <= set(
        TrackPoint.model_fields
    )
    assert {"ne_extent_nmi", "se_extent_nmi", "sw_extent_nmi", "nw_extent_nmi"} <= set(
        WindRadii.model_fields
    )


def test_an_advisory_s_instant_is_the_one_its_text_names() -> None:
    with pytest.raises(ValidationError, match="local_text"):
        revalidate(advisory(), issued_at=datetime(2026, 10, 13, 1, tzinfo=UTC))
    unknown = Advisory(
        atcf_id=ATCF_ID,
        number=AdvisoryNumber.parse("22"),
        issued_at=None,
        local_text="200 PM XYZ Mon Oct 12 2026",
    )

    assert unknown.issued_at is None


def test_an_advisory_may_take_its_instant_from_the_roster() -> None:
    later = datetime(2026, 10, 13, 2, tzinfo=UTC)
    kept = revalidate(advisory(), issued_at=later, issued_at_source="roster")
    assert (kept.issued_at, kept.local_text) == (later, INTERMEDIATE_TEXT)
    untexted = Advisory(
        atcf_id=ATCF_ID,
        number=AdvisoryNumber.parse("22"),
        issued_at=later,
        local_text=None,
        issued_at_source="roster",
    )
    assert untexted.local_text is None
    with pytest.raises(ValidationError, match="instant"):
        revalidate(untexted, issued_at=None)
    with pytest.raises(ValidationError, match="local_text"):
        revalidate(untexted, issued_at_source="local_text")
    with pytest.raises(ValidationError, match="NHC local time"):
        revalidate(kept, local_text="tomorrow")


def test_a_record_s_advisory_belongs_to_its_storm() -> None:
    with pytest.raises(ValidationError, match="belong to its storm"):
        revalidate(cone(), atcf_id="EP192026")


def test_a_track_point_never_stores_the_9999_sentinel() -> None:
    with pytest.raises(ValidationError, match="9999"):
        revalidate(track_point(), mslp_mb=9999)
    with pytest.raises(ValidationError, match="track point"):
        revalidate(track_point(), position=cone().geometry)


def test_the_geometry_of_each_record_has_the_right_type() -> None:
    with pytest.raises(ValidationError, match="cone"):
        revalidate(cone(), geometry=landmark_point())
    with pytest.raises(ValidationError, match="wind radii"):
        revalidate(wind_radii(), geometry=landmark_point())
    with pytest.raises(ValidationError, match="outlook"):
        revalidate(outlook_area(), kind="two_day_location")
    assert (
        revalidate(outlook_area(), kind="two_day_location", geometry=landmark_point()).kind
        == "two_day_location"
    )


def test_the_advisory_wind_field_is_at_tau_0() -> None:
    with pytest.raises(ValidationError, match="tau 0"):
        revalidate(wind_radii(), tau_h=12)


def replay_point_segments() -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for path in sorted(
        Path(REPOSITORY_ROOT / "tests/fixtures/replay/AL052019").glob(
            "05[6-9]*/watch-warning.geojson.gz"
        )
    ):
        collection = json.loads(gzip.decompress(path.read_bytes()))
        found += [
            {**feature, "source_crs": collection["source_crs"]}
            for feature in collection["features"]
            if feature["geometry"]["type"] == "Point"
        ]
    return found


def test_a_replay_one_vertex_watch_warning_is_a_noted_point() -> None:
    features = replay_point_segments()
    assert features
    feature = features[0]
    properties = cast("dict[str, object]", feature["properties"])
    crs = Crs.native(cast("dict[str, object]", feature["source_crs"]))

    segment = WatchWarningSegment(
        atcf_id="AL052019",
        advisory=Advisory(
            atcf_id="AL052019",
            number=AdvisoryNumber.parse(cast("str", properties["ADVISNUM"])),
            issued_at=None,
            local_text="500 PM XYZ Sat Sep 07 2019",
        ),
        provenance=provenance("nhc-gis-archive"),
        tcww=WatchWarningType.parse(cast("str", properties["TCWW"])),
        geometry=Geometry.from_geojson(cast("dict[str, object]", feature["geometry"]), crs),
        geometry_note=cast("str", feature["geometry_note"]),
    )

    assert segment.geometry.type == "Point"
    assert segment.tcww.recognized
    with pytest.raises(ValidationError, match="geometry_note"):
        revalidate(segment, geometry_note=None)


def test_an_unknown_tcww_code_is_kept() -> None:
    segment = revalidate(watch_warning(), tcww=WatchWarningType.parse("SSW"))

    assert (segment.tcww.raw, segment.tcww.recognized) == ("SSW", False)


# Alerts, products, and locations


def test_an_alert_query_names_a_zone_exactly_when_it_is_a_zone_query() -> None:
    assert alert_query().zone_id == "FLC086"
    assert AlertQuery(kind="point", provenance=provenance("nws-alerts-point")).zone_id is None
    with pytest.raises(ValidationError, match="zone"):
        AlertQuery(kind="zone", provenance=provenance("nws-alerts-zone"))
    with pytest.raises(ValidationError, match="zone"):
        AlertQuery(kind="point", zone_id="FLZ173", provenance=provenance("nws-alerts-point"))


def test_an_alert_is_found_by_at_least_one_query_and_keeps_issue_10_inputs() -> None:
    record = alert()

    assert record.affected_zone_ids == ("FLZ069", "FLZ075", "FLZ174")
    assert "012086" in record.geocode_same
    with pytest.raises(ValidationError):
        revalidate(record, found_by=())
    assert {"found_by", "affected_zone_ids", "geocode_same", "geocode_ugc"} <= set(
        NwsAlert.model_fields
    )


def test_unknown_cap_codes_are_kept_on_an_alert() -> None:
    record = revalidate(alert(), severity=alert().severity.parse("Catastrophic"))

    assert (record.severity.raw, record.severity.recognized) == ("Catastrophic", False)


def test_a_two_names_no_storm() -> None:
    with pytest.raises(ValidationError, match="TWO"):
        revalidate(text_product(), code="TWO")
    assert (
        revalidate(text_product(), code="TWO", atcf_id=None, advisory=None, location="AT").code
        == "TWO"
    )


def test_the_feed_placeholder_has_no_time_and_no_storm() -> None:
    with pytest.raises(ValidationError, match="placeholder"):
        revalidate(feed_item(), published_at=datetime(2026, 10, 14, 11, 3, tzinfo=UTC))
    with pytest.raises(ValidationError, match="is_placeholder"):
        revalidate(feed_item(), is_placeholder=False)
    item = revalidate(
        feed_item(), title="Summary", is_placeholder=False, atcf_id=ATCF_ID, slot="EP5"
    )
    assert isinstance(item, GisFeedItem)


def test_a_location_holds_no_operator_value_by_default() -> None:
    required = {name for name, field in Location.model_fields.items() if field.is_required()}

    assert required == {"name", "point"}
    assert Location.model_fields["evacuation_order_in_effect"].default is False
    assert Location.model_fields["breakpoint_span"].default is None


@pytest.mark.parametrize("name", ["", " ", "a\tb", "x" * 65, "line\nbreak"])
def test_a_location_name_is_1_to_64_printable_characters(name: str) -> None:
    with pytest.raises(ValidationError):
        revalidate(location(), name=name)


def test_a_location_polygon_is_areal_and_coverage_is_optional() -> None:
    with pytest.raises(ValidationError, match="polygon"):
        revalidate(location(), polygon=landmark_point())
    outside = revalidate(location(), nws=None, country_code="BS")
    assert outside.nws is None
    with pytest.raises(ValidationError):
        revalidate(location(), country_code="bs")


# The snapshot


def test_a_snapshot_has_one_outcome_per_source_and_always_the_roster() -> None:
    with pytest.raises(ValidationError, match="roster"):
        revalidate(snapshot(), source_outcomes=snapshot().source_outcomes[1:])
    doubled = (*snapshot().source_outcomes, snapshot().source_outcomes[0])
    with pytest.raises(ValidationError, match="one outcome per source"):
        revalidate(snapshot(), source_outcomes=doubled)


def test_nothing_in_a_snapshot_stands_in_for_a_source_it_did_not_fetch() -> None:
    kept = tuple(o for o in snapshot().source_outcomes if o.source_id != "nhc-gis-rss")
    failed = (*kept, SourceOutcome(source_id="nhc-gis-rss", status="failed", error_kind="timeout"))

    with pytest.raises(ValidationError, match="source has an ok"):
        revalidate(snapshot(), source_outcomes=kept)
    with pytest.raises(ValidationError, match="source has an ok"):
        revalidate(snapshot(), source_outcomes=failed)
    assert revalidate(snapshot(), source_outcomes=failed, gis_feed_items=()).status == "partial"


def test_the_derived_status_follows_the_outcomes() -> None:
    assert snapshot().status == "complete"
    skipped = (
        *outcomes(),
        SourceOutcome(source_id="nws-points", status="skipped", reason="outside NWS coverage"),
    )
    empty = Snapshot(
        snapshot_id=snapshot().snapshot_id,
        started_at=snapshot().started_at,
        completed_at=snapshot().completed_at,
        source_outcomes=skipped,
    )
    assert empty.status == "complete"
    roster_failed = (
        SourceOutcome(source_id="nhc-current-storms", status="failed", error_kind="http_503"),
    )
    assert revalidate(empty, source_outcomes=roster_failed).status == "failed"
    assert "status" not in Snapshot.model_fields


def test_a_snapshot_completes_after_it_starts_and_keys_alerts_by_location_name() -> None:
    with pytest.raises(ValidationError, match="completes after"):
        revalidate(snapshot(), completed_at=snapshot().started_at - timedelta(seconds=1))
    with pytest.raises(ValidationError, match="location name"):
        revalidate(snapshot(), alerts={"": ()})


def test_a_storm_s_products_belong_to_that_storm() -> None:
    other = summary().model_copy(update={"atcf_id": "EP192026"})

    with pytest.raises(ValidationError, match="belongs to that storm"):
        revalidate(storm_products(), summary=other)
    with pytest.raises(ValidationError, match="one entry per storm"):
        revalidate(snapshot(), storms=(storm_products(), storm_products()))


@pytest.mark.parametrize(
    ("status", "detail"),
    [("failed", {}), ("skipped", {}), ("ok", {"reason": "x"}), ("ok", {"error_kind": "x"})],
)
def test_an_outcome_s_detail_fits_its_status(status: str, detail: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        SourceOutcome.model_validate({"source_id": "nws-points", "status": status, **detail})


# Hygiene


def test_model_source_names_no_storm_season_or_place() -> None:
    names = ("Simon", "Irma", "Dorian", "Milton", "Ian", "Miami", "Nassau", "Bahamas", "Florida")
    text = "\n".join(path.read_text("utf-8") for path in sorted(MODELS_SOURCE.glob("*.py")))

    assert not [name for name in names if re.search(rf"\b{name}\b", text)]
    assert not re.search(r"\b(?:AL|EP|CP)\d{6}\b", text)
    assert not re.search(r"\b20\d\d\b", text)


def test_models_are_constructed_only_from_their_own_fields() -> None:
    assert isinstance(revalidate(wind_radii()), WindRadii)
    assert isinstance(revalidate(arrival_product()), ArrivalTimeProduct)
    assert isinstance(revalidate(outlook_area()), OutlookArea)
    assert isinstance(revalidate(text_product()), TextProduct)
    assert isinstance(
        Geometry.from_geojson({"type": "Point", "coordinates": [0, 0]}, WGS84), Geometry
    )
