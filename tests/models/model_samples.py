# tests/models/model_samples.py
"""Minimal valid instances of every public model, for the convention tests.

Coordinates come from the public landmarks in ``scripts/public_landmarks.toml`` or from
the recorded fixtures, computed at run time; this module holds no coordinate literal.
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

from check_personal_data import load_landmarks
from weatherbot.models import (
    WGS84,
    Advisory,
    AdvisoryNumber,
    AdvisoryRecord,
    AlertCategory,
    AlertCertainty,
    AlertMessageType,
    AlertQuery,
    AlertSeverity,
    AlertStatus,
    AlertUrgency,
    ArrivalResolution,
    ArrivalTimeLine,
    ArrivalTimeProduct,
    Breakpoint,
    ConeGeometry,
    Crs,
    DisplayLayer,
    DomainModel,
    ForecastTrack,
    GeocodeResult,
    Geometry,
    GisFeedItem,
    LatLon,
    Location,
    MapCatalog,
    MapLayer,
    NwsAlert,
    NwsCoverage,
    NwsZone,
    OutlookArea,
    OutlookGraphic,
    OutlookRisk,
    OverlayCatalog,
    OverlayLayer,
    Provenance,
    RosterProduct,
    Snapshot,
    SourceId,
    SourceOutcome,
    StormClassification,
    StormProducts,
    StormSummary,
    TextProduct,
    TrackPoint,
    WatchWarningSegment,
    WatchWarningType,
    WindProbabilityBand,
    WindProbabilityProduct,
    WindRadii,
    parse_nhc_local_time,
)
from weatherbot.models.codes import (
    AlertCategoryCode,
    AlertCertaintyCode,
    AlertMessageTypeCode,
    AlertSeverityCode,
    AlertStatusCode,
    AlertUrgencyCode,
    OutlookRiskCode,
    StormClassificationCode,
    WatchWarningCode,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RECORDED = REPOSITORY_ROOT / "tests" / "fixtures" / "recorded"
TROPICAL = RECORDED / "nhc-map-tropical-weather" / "2026-10-12"
FETCHED_AT = datetime(2026, 10, 13, 1, 8, 56, tzinfo=UTC)
ATCF_ID = "EP202026"
# The recorded EP5 cone's advisory and the arrival lines' full advisory (2026-10-12).
INTERMEDIATE_TEXT = "500 PM MST Mon Oct 12 2026"
FULL_TEXT = "200 PM MST Mon Oct 12 2026"
SNAPSHOT_ID = UUID("00000000-0000-4000-8000-000000000001")


def recorded_features(name: str) -> list[dict[str, object]]:
    """Return the features of one recorded EP5 or basin-wide query."""
    document = json.loads((TROPICAL / name).read_text(encoding="utf-8"))
    return cast("list[dict[str, object]]", document["features"])


def recorded_arrival_labels(name: str) -> list[str]:
    """Return the ``arrival_time`` label of every recorded arrival line, as received."""
    return [
        cast("str", cast("dict[str, object]", feature["properties"])["arrival_time"])
        for feature in recorded_features(name)
    ]


def recorded_geometry(name: str, index: int = 0) -> Geometry:
    """Return one recorded feature's geometry, labelled as the live query asked."""
    geometry = cast("dict[str, object]", recorded_features(name)[index]["geometry"])
    return Geometry.from_geojson(geometry, WGS84)


def landmark_point(key: str = "miami-dade") -> Geometry:
    """Return a landmark as a Point."""
    landmark = next(item for item in load_landmarks() if item.key == key)
    return Geometry(type="Point", coordinates=(float(landmark.lon), float(landmark.lat)), crs=WGS84)


def landmark_square(key: str = "miami-dade", half: float = 0.05) -> Geometry:
    """Return a small closed square around a landmark."""
    centre = cast("tuple[float, float]", landmark_point(key).coordinates)
    lon, lat = centre
    ring = (
        (lon - half, lat - half),
        (lon + half, lat - half),
        (lon + half, lat + half),
        (lon - half, lat + half),
        (lon - half, lat - half),
    )
    return Geometry(type="Polygon", coordinates=(ring,), crs=WGS84)


def provenance(source_id: SourceId = "nhc-map-tropical-weather") -> Provenance:
    """Return a provenance for one recorded response."""
    return Provenance(
        source_id=source_id,
        url="https://mapservices.weather.noaa.gov/tropical/rest/services",
        status=200,
        fetched_at=FETCHED_AT,
        sha256="ab" * 32,
    )


def advisory(text: str = INTERMEDIATE_TEXT, number: str = "22A") -> Advisory:
    """Return an EP202026 advisory."""
    return Advisory(
        atcf_id=ATCF_ID,
        number=AdvisoryNumber.parse(number),
        issued_at=parse_nhc_local_time(text),
        local_text=text,
    )


def recorded_storm() -> dict[str, object]:
    """Return the recorded roster's one storm."""
    path = RECORDED / "nhc-current-storms" / "2026-10-12" / "CurrentStorms.json"
    storms = cast(
        "list[dict[str, object]]", json.loads(path.read_text(encoding="utf-8"))["activeStorms"]
    )
    return storms[0]


def summary() -> StormSummary:
    """Return the recorded roster storm, as a parser builds it."""
    issued = datetime(2026, 10, 13, tzinfo=UTC)
    storm = recorded_storm()
    return StormSummary(
        atcf_id=ATCF_ID,
        slot="EP5",
        name="Simon",
        classification=StormClassification.parse("HU"),
        intensity_kt=85,
        pressure_mb=969,
        latitude=cast("float", storm["latitudeNumeric"]),
        longitude=cast("float", storm["longitudeNumeric"]),
        movement_dir_deg=300,
        movement_speed_mph=3,
        last_update=issued,
        public_advisory=RosterProduct(advisory=AdvisoryNumber.parse("022a"), issued_at=issued),
        has_storm_surge_watch_warning=False,
        has_potential_storm_surge_flooding=False,
        has_peak_surge=False,
    )


def cone() -> ConeGeometry:
    """Return the recorded EP5 cone."""
    return ConeGeometry(
        atcf_id=ATCF_ID,
        advisory=advisory(),
        provenance=provenance(),
        forecast_period_h=120,
        geometry=recorded_geometry("query-ep5-forecast-cone.geojson"),
    )


def track_point() -> TrackPoint:
    """Return the recorded EP5 tau-12 point, whose pressure, direction, and speed are 9999."""
    return TrackPoint(
        atcf_id=ATCF_ID,
        advisory=advisory(),
        provenance=provenance(),
        tau_h=12,
        valid_at=datetime(2026, 10, 13, 6, tzinfo=UTC),
        valid_local_text="2026-10-12 11:00 PM Mon MST",
        position=recorded_geometry("query-ep5-forecast-points.geojson", 1),
        max_wind_kt=75,
        gust_kt=90,
        mslp_mb=None,
        direction_deg=None,
        speed_kt=None,
        development="Hurricane",
        storm_type="HU",
        saffir_simpson=1,
        label="H",
    )


def track() -> ForecastTrack:
    """Return the recorded EP5 track."""
    return ForecastTrack(
        atcf_id=ATCF_ID,
        advisory=advisory(),
        provenance=provenance(),
        geometry=recorded_geometry("query-ep5-forecast-track.geojson"),
    )


def watch_warning() -> WatchWarningSegment:
    """Return the recorded EP5 hurricane watch."""
    return WatchWarningSegment(
        atcf_id=ATCF_ID,
        advisory=advisory(),
        provenance=provenance(),
        tcww=WatchWarningType.parse("HWA"),
        geometry=recorded_geometry("query-ep5-watch-warning.geojson"),
    )


def wind_radii() -> WindRadii:
    """Return the recorded EP5 34-kt advisory wind field."""
    return WindRadii(
        atcf_id=ATCF_ID,
        advisory=AdvisoryNumber.parse("22A"),
        provenance=provenance(),
        threshold_kt=34,
        tau_h=0,
        valid_at=datetime(2026, 10, 13, tzinfo=UTC),
        synoptic_at=datetime(2026, 10, 12, 18, tzinfo=UTC),
        ne_extent_nmi=40,
        se_extent_nmi=40,
        sw_extent_nmi=20,
        nw_extent_nmi=30,
        is_advisory_field=True,
        geometry=recorded_geometry("query-ep5-advisory-wind-field.geojson"),
    )


def arrival_product() -> ArrivalTimeProduct:
    """Return the recorded earliest-arrival lines as a KMZ product of advisory 22."""
    published = parse_nhc_local_time(FULL_TEXT)
    name = "query-ep5-earliest-reasonable-arrival-time.geojson"
    lines = tuple(
        ArrivalTimeLine.resolve(
            label,
            recorded_geometry(name, index),
            origin="kmz",
            published_at=published,
            time_zone="MST",
        )
        for index, label in enumerate(recorded_arrival_labels(name))
    )
    return ArrivalTimeProduct(
        atcf_id=ATCF_ID,
        advisory=advisory(FULL_TEXT, "22"),
        provenance=provenance(),
        kind="earliest_reasonable",
        time_zone="MST",
        published_at=published,
        published_local_text=FULL_TEXT,
        origin="kmz",
        lines=lines,
    )


def outlook_area() -> OutlookArea:
    """Return the recorded Atlantic development region."""
    return OutlookArea(
        kind="development_region",
        basin="Atlantic",
        chance_2day_pct=20,
        chance_7day_pct=20,
        risk_2day=OutlookRisk.parse("Low"),
        risk_7day=OutlookRisk.parse("Low"),
        outlook_stamp="gtwo_areas_202610122308",
        issued_at=datetime(2026, 10, 12, 23, 17, 54, tzinfo=UTC),
        geometry=recorded_geometry("query-seven-day-potential-development-region.geojson"),
        provenance=provenance(),
    )


def wind_band() -> WindProbabilityBand:
    """Return the recorded 34-kt ``5-10%`` band."""
    return WindProbabilityBand.from_label(
        "5-10%", recorded_geometry("query-probabilistic-winds-34-kts.geojson", 1)
    )


def wind_product() -> WindProbabilityProduct:
    """Return a 34-kt product with one recorded band."""
    return WindProbabilityProduct(
        threshold_kt=34,
        synoptic_at=datetime(2026, 10, 12, 18, tzinfo=UTC),
        bands=(wind_band(),),
        provenance=provenance(),
    )


def alert_query() -> AlertQuery:
    """Return a county-zone query."""
    return AlertQuery(kind="zone", zone_id="FLC086", provenance=provenance("nws-alerts-zone"))


def alert() -> NwsAlert:
    """Return a synthetic coastal-flood statement shaped like the register's FLC086 example."""
    sent = datetime(2026, 10, 12, 19, 39, tzinfo=UTC)
    return NwsAlert(
        id="urn:oid:2.49.0.1.840.0.example.001.1",
        event="Coastal Flood Statement",
        headline="Coastal Flood Statement issued by NWS Miami FL",
        severity=AlertSeverity.parse("Minor"),
        certainty=AlertCertainty.parse("Likely"),
        urgency=AlertUrgency.parse("Expected"),
        status=AlertStatus.parse("Actual"),
        message_type=AlertMessageType.parse("Alert"),
        category=AlertCategory.parse("Met"),
        sent=sent,
        effective=sent,
        onset=None,
        expires=sent + timedelta(hours=12),
        ends=None,
        area_desc="Coastal Collier County; Mainland Monroe; Far South Miami-Dade County",
        sender_name="NWS Miami FL",
        references=(),
        vtec=(),
        nws_headline=(),
        description="Synthetic text.",
        instruction=None,
        affected_zone_ids=("FLZ069", "FLZ075", "FLZ174"),
        geocode_same=("012021", "012087", "012086"),
        geocode_ugc=("FLZ069", "FLZ075", "FLZ174"),
        geometry=None,
        found_by=(alert_query(),),
    )


def zone() -> NwsZone:
    """Return a zone record with a landmark square for its shape."""
    return NwsZone(
        id="FLZ173",
        type="public",
        name="Coastal Miami Dade County",
        state="FL",
        cwa=("MFL",),
        time_zone=("America/New_York",),
        effective_date=datetime(2026, 4, 16, 18, tzinfo=UTC),
        geometry=landmark_square(),
        provenance=provenance("nws-zones"),
    )


def geocode() -> GeocodeResult:
    """Return the recorded Nassau reverse lookup."""
    return GeocodeResult(
        display_name="Parliament Square, Nassau, New Providence, The Bahamas",
        name="Parliament Square",
        country_code="bs",
        country="The Bahamas",
        licence="Data © OpenStreetMap contributors, ODbL 1.0. http://osm.org/copyright",
        osm_type="relation",
        osm_id=14900727,
        provenance=provenance("geocode-nominatim"),
    )


def location() -> Location:
    """Return the Miami-Dade landmark as a location."""
    lon, lat = cast("tuple[float, float]", landmark_point().coordinates)
    return Location(
        name="Miami-Dade County Hall",
        point=LatLon(latitude=lat, longitude=lon),
        polygon=landmark_square(),
        country_code="US",
        display_name="Miami-Dade County Office",
        nws=NwsCoverage(
            forecast_zone="FLZ173",
            county_zone="FLC086",
            cwa="MFL",
            time_zone="America/New_York",
            city="Miami",
            state="FL",
        ),
        geocoding=provenance("geocode-nominatim"),
    )


def text_product() -> TextProduct:
    """Return the recorded TCP's header facts."""
    return TextProduct(
        product_id="8916389a-6334-4134-b9a5-26ab195a7381",
        code="TCP",
        location="EP5",
        wmo_collective_id="WTPZ35",
        issuing_office="KNHC",
        issued_at=datetime(2026, 10, 12, 23, 33, tzinfo=UTC),
        text="Hurricane Simon Intermediate Advisory Number 22A",
        atcf_id=ATCF_ID,
        advisory=AdvisoryNumber.parse("22A"),
        provenance=provenance("nhc-text-products"),
    )


def feed_item() -> GisFeedItem:
    """Return the recorded Atlantic placeholder item."""
    return GisFeedItem(
        feed="at",
        guid="https://www.nhc.noaa.gov/gis/",
        title="There are no tropical cyclones at this time.",
        link="https://www.nhc.noaa.gov/gis/",
        published_at=None,
        is_placeholder=True,
        atcf_id=None,
        slot=None,
        provenance=provenance("nhc-gis-rss"),
    )


def graphic() -> OutlookGraphic:
    """Return the recorded Atlantic two-day map."""
    return OutlookGraphic(
        basin="atl",
        horizon="2d0",
        width_px=900,
        height_px=679,
        provenance=provenance("nhc-outlook-graphics"),
    )


def breakpoint_record() -> Breakpoint:
    """Return a breakpoint at the Nassau landmark."""
    return Breakpoint(
        name="Bahamas (NW)",
        state=None,
        country="Bahamas",
        position=landmark_point("nassau"),
        provenance=provenance("nhc-map-breakpoints"),
    )


def map_catalog() -> MapCatalog:
    """Return a one-layer catalog."""
    return MapCatalog(
        service="tropical/NHC_tropical_weather",
        read_at=FETCHED_AT,
        layers=(
            MapLayer(
                id=1,
                name="Two-Day: Current Location",
                type="Feature Layer",
                geometry_type="esriGeometryPoint",
                group_path=("Graphical Tropical Weather Outlook",),
            ),
        ),
        provenance=provenance(),
    )


def overlay_catalog() -> OverlayCatalog:
    """Return a one-layer WMS catalog."""
    return OverlayCatalog(
        service="weather_radar",
        layers=(
            OverlayLayer(
                name="conus_base_reflectivity_mosaic",
                time_default=datetime(2026, 10, 13, 0, 59, 55, tzinfo=UTC),
            ),
        ),
        provenance=provenance("overlay-radar"),
    )


def display_layer() -> DisplayLayer:
    """Return the recorded empty peak-surge points layer, raw."""
    return DisplayLayer(
        layer_name="Points",
        feature_collection={"type": "FeatureCollection", "features": []},
        crs=WGS84,
        provenance=provenance("nhc-map-peak-surge"),
    )


def storm_products() -> StormProducts:
    """Return the recorded storm with every product kind."""
    return StormProducts(
        summary=summary(),
        cone=cone(),
        track_points=(track_point(),),
        track=track(),
        watch_warnings=(watch_warning(),),
        wind_radii=(wind_radii(),),
        arrival_times=(arrival_product(),),
    )


def outcomes(*source_ids: SourceId) -> tuple[SourceOutcome, ...]:
    """Return an ``ok`` outcome per source, the roster first."""
    ids: list[SourceId] = ["nhc-current-storms", *source_ids]
    return tuple(SourceOutcome(source_id=source_id, status="ok") for source_id in ids)


def snapshot() -> Snapshot:
    """Return a snapshot holding one of every record kind."""
    return Snapshot(
        snapshot_id=SNAPSHOT_ID,
        started_at=FETCHED_AT,
        completed_at=FETCHED_AT + timedelta(seconds=30),
        storms=(storm_products(),),
        outlook_areas=(outlook_area(),),
        wind_probabilities=(wind_product(),),
        text_products=(text_product(),),
        gis_feed_items=(feed_item(),),
        outlook_graphics=(graphic(),),
        breakpoints=(breakpoint_record(),),
        display_layers=(display_layer(),),
        alerts={"Miami-Dade County Hall": (alert(),)},
        source_outcomes=outcomes(
            "nhc-map-tropical-weather",
            "nhc-text-products",
            "nhc-gis-rss",
            "nhc-outlook-graphics",
            "nhc-map-breakpoints",
            "nhc-map-peak-surge",
            "nws-alerts-zone",
        ),
    )


SAMPLES: dict[type[DomainModel], Callable[[], DomainModel]] = {
    Advisory: advisory,
    AdvisoryNumber: lambda: AdvisoryNumber.parse("22A"),
    AdvisoryRecord: lambda: AdvisoryRecord(
        atcf_id=ATCF_ID, advisory=advisory(), provenance=provenance()
    ),
    AlertCategory: lambda: AlertCategory.parse("Met"),
    AlertCertainty: lambda: AlertCertainty.parse("Likely"),
    AlertMessageType: lambda: AlertMessageType.parse("Update"),
    AlertQuery: alert_query,
    AlertSeverity: lambda: AlertSeverity.parse("Minor"),
    AlertStatus: lambda: AlertStatus.parse("Actual"),
    AlertUrgency: lambda: AlertUrgency.parse("Expected"),
    ArrivalResolution: lambda: ArrivalResolution(valid_at=FETCHED_AT, reason=None),
    ArrivalTimeLine: lambda: arrival_product().lines[0],
    ArrivalTimeProduct: arrival_product,
    Breakpoint: breakpoint_record,
    ConeGeometry: cone,
    Crs: lambda: Crs.native({"datum": "D_Sphere", "wkt": 'GEOGCS["GCS_Sphere",DATUM["D_Sphere"]]'}),
    DisplayLayer: display_layer,
    ForecastTrack: track,
    GeocodeResult: geocode,
    Geometry: landmark_square,
    GisFeedItem: feed_item,
    LatLon: lambda: location().point,
    Location: location,
    MapCatalog: map_catalog,
    MapLayer: lambda: map_catalog().layers[0],
    NwsAlert: alert,
    NwsCoverage: lambda: cast("NwsCoverage", location().nws),
    NwsZone: zone,
    OutlookArea: outlook_area,
    OutlookGraphic: graphic,
    OutlookRisk: lambda: OutlookRisk.parse("High"),
    OverlayCatalog: overlay_catalog,
    OverlayLayer: lambda: overlay_catalog().layers[0],
    Provenance: provenance,
    RosterProduct: lambda: summary().public_advisory,
    Snapshot: snapshot,
    SourceOutcome: lambda: SourceOutcome(source_id="nws-points", status="skipped", reason="non-US"),
    StormClassification: lambda: StormClassification.parse("HU"),
    StormProducts: storm_products,
    StormSummary: summary,
    TextProduct: text_product,
    TrackPoint: track_point,
    WatchWarningSegment: watch_warning,
    WatchWarningType: lambda: WatchWarningType.parse("HWR"),
    WindProbabilityBand: wind_band,
    WindProbabilityProduct: wind_product,
    WindRadii: wind_radii,
}

# Every vocabulary, for the coded-value tests.
VOCABULARIES = (
    (StormClassification, StormClassificationCode),
    (WatchWarningType, WatchWarningCode),
    (OutlookRisk, OutlookRiskCode),
    (AlertSeverity, AlertSeverityCode),
    (AlertCertainty, AlertCertaintyCode),
    (AlertUrgency, AlertUrgencyCode),
    (AlertStatus, AlertStatusCode),
    (AlertMessageType, AlertMessageTypeCode),
    (AlertCategory, AlertCategoryCode),
)
