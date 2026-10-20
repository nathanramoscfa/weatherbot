# tests/engine/engine_support.py
"""Shared inputs for the engine tests: the landmarks, the replay corpus, and synthetic products.

Coordinates come from the public landmarks in ``scripts/public_landmarks.toml`` and from
the replay corpus, read at run time through ``weatherbot.sources.nhc_gis_archive``, the
parser replay snapshots use, so the engine tests read replay data exactly as snapshots
do; synthetic shapes are built from the landmarks, the antimeridian, and whole-degree
offsets. The synthetic live products (a storm, its cone, segments, forecast points, and
arrival-time products, wind-speed probabilities, an outlook region, an NWS alert, and the
snapshot holding them) carry ``example.invalid`` provenance. This module holds no
coordinate literal.
"""

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Final, Literal, cast
from uuid import UUID

from check_personal_data import load_landmarks
from weatherbot.models import (
    WGS84,
    Advisory,
    AdvisoryNumber,
    AlertCategory,
    AlertCertainty,
    AlertMessageType,
    AlertQuery,
    AlertSeverity,
    AlertStatus,
    AlertUrgency,
    ArrivalTimeLine,
    ArrivalTimeProduct,
    ConeGeometry,
    Crs,
    Geometry,
    LatLon,
    Location,
    NwsAlert,
    NwsCoverage,
    OutlookArea,
    Provenance,
    RosterProduct,
    Snapshot,
    SourceId,
    SourceOutcome,
    StormClassification,
    StormProducts,
    StormSummary,
    TrackPoint,
    WatchWarningSegment,
    WatchWarningType,
    WindProbabilityBand,
    WindProbabilityProduct,
    parse_nhc_local_time,
)
from weatherbot.sources import nhc_gis_archive
from weatherbot.sources.nhc_gis_archive import CorpusEntry, CorpusManifest

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
REPLAY: Final = REPOSITORY_ROOT / "tests" / "fixtures" / "replay"
IRMA: Final = "AL112017"
DORIAN: Final = "AL052019"
SYNTHETIC_STORM: Final = "CP012026"
SYNTHETIC_AT: Final = datetime(2026, 10, 13, 12, tzinfo=UTC)
SYNTHETIC_SNAPSHOT: Final = UUID("5e0c4d1e-5b7a-4c2e-9d3f-1a2b3c4d5e6f")
# The synthetic arrival products' pubAdvTime: SYNTHETIC_AT, 12:00 UTC.
ARRIVAL_PUBLISHED: Final = "800 AM EDT Tue Oct 13 2026"
MIAMI_DADE: Final = "miami-dade"
NASSAU: Final = "nassau"
# The Miami-Dade landmark's NWS coverage, as the recorded /points answer gives it.
MIAMI_DADE_ZONES: Final = NwsCoverage(
    forecast_zone="FLZ173",
    county_zone="FLC086",
    cwa="MFL",
    time_zone="America/New_York",
    city="Miami",
    state="FL",
)


def landmark(key: str) -> LatLon:
    """Return a public landmark (``miami-dade`` or ``nassau``) as a WGS 84 point."""
    found = next(item for item in load_landmarks() if item.key == key)
    return LatLon(latitude=float(found.lat), longitude=float(found.lon))


@cache
def manifest() -> CorpusManifest:
    """Return the replay corpus manifest, as the archive parser reads it."""
    return nhc_gis_archive.parse_manifest((REPLAY / nhc_gis_archive.MANIFEST_NAME).read_bytes())


def corpus_wkts() -> set[str]:
    """Return every distinct projection WKT the manifest records for the originals."""
    document = json.loads((REPLAY / nhc_gis_archive.MANIFEST_NAME).read_bytes())
    files = cast("list[dict[str, dict[str, dict[str, str]]]]", document["files"])
    return {projection["wkt"] for entry in files for projection in entry["prj"].values()}


def advisories(storm: str) -> list[str]:
    """Return a storm's advisories in advisory order (``22 < 22A < 23``)."""
    return list(manifest().storms[storm].advisories)


def _parsed[T](
    storm: str, advisory: str, product: str, parse: Callable[[bytes, CorpusEntry], T]
) -> T | None:
    file = f"{storm}/{advisory}/{product}.geojson.gz"
    converted = next((item for item in manifest().subset if item.file == file), None)
    if converted is None:
        return None
    return parse((REPLAY / file).read_bytes(), manifest().entry(converted))


def cone(storm: str, advisory: str) -> ConeGeometry | None:
    """Return an advisory's cone, or ``None`` when the corpus lacks it."""
    return _parsed(storm, advisory, "cone", nhc_gis_archive.parse_cone)


def segments(storm: str, advisory: str) -> tuple[WatchWarningSegment, ...]:
    """Return an advisory's watch-warning segments; none when the archive has none."""
    return _parsed(storm, advisory, "watch-warning", nhc_gis_archive.parse_watch_warnings) or ()


def replay_track(storm: str, advisory: str) -> list[TrackPoint]:
    """Return an advisory's forecast points, parsed as a replay snapshot parses them.

    The provenance cites the original archive the collection was converted from.
    """
    return list(_parsed(storm, advisory, "points", nhc_gis_archive.parse_track_points) or ())


def synthetic_provenance(
    source_id: SourceId = "nhc-map-tropical-summary", at: datetime = SYNTHETIC_AT
) -> Provenance:
    """Return the provenance of a synthetic product."""
    return Provenance(
        source_id=source_id,
        url="https://example.invalid/synthetic",
        status=200,
        fetched_at=at,
        sha256="0" * 64,
    )


def synthetic_advisory(at: datetime = SYNTHETIC_AT) -> Advisory:
    """Return the synthetic storm's advisory, issued at ``at``."""
    return Advisory(
        atcf_id=SYNTHETIC_STORM,
        number=AdvisoryNumber.parse("1"),
        issued_at=at,
        local_text=None,
        issued_at_source="roster",
    )


def synthetic_track(
    start: datetime,
    positions: Sequence[tuple[float, float]],
    *,
    step: timedelta = timedelta(hours=12),
    crs: Crs = WGS84,
    winds_kt: Sequence[int | None] | None = None,
) -> list[TrackPoint]:
    """Build a synthetic forecast track: one point per position, ``step`` apart from ``start``.

    Args:
        start: The first point's instant (UTC).
        positions: Each point's ``(longitude, latitude)``.
        step: The time between consecutive points.
        crs: The points' CRS.
        winds_kt: Each point's maximum wind; none when omitted.

    Returns:
        The points, in order.
    """
    advisory = synthetic_advisory(start)
    provenance = synthetic_provenance(at=start)
    winds = list(winds_kt) if winds_kt is not None else [None] * len(positions)
    return [
        TrackPoint(
            atcf_id=SYNTHETIC_STORM,
            advisory=advisory,
            provenance=provenance,
            tau_h=int(index * step.total_seconds() // 3600),
            valid_at=start + index * step,
            position=Geometry(type="Point", coordinates=position, crs=crs),
            max_wind_kt=winds[index],
            gust_kt=None,
            mslp_mb=None,
            direction_deg=None,
            speed_kt=None,
            development="Hurricane",
            storm_type="HU",
            saffir_simpson=None,
            label="H",
        )
        for index, position in enumerate(positions)
    ]


def square(centre: tuple[float, float], half: float, crs: Crs = WGS84) -> Geometry:
    """Return a closed square ring of half-width ``half`` degrees, as a Polygon."""
    lon, lat = centre
    ring = (
        (lon - half, lat - half),
        (lon + half, lat - half),
        (lon + half, lat + half),
        (lon - half, lat + half),
        (lon - half, lat - half),
    )
    return Geometry(type="Polygon", coordinates=(ring,), crs=crs)


def wrap(longitude: float) -> float:
    """Bring a longitude unwrapped past 180 degrees back into [-180, 180]."""
    if longitude > 180.0:  # noqa: PLR2004 - the antimeridian
        return longitude - 360.0
    if longitude < -180.0:  # noqa: PLR2004 - the antimeridian
        return longitude + 360.0
    return longitude


def wrapped_polygon(ring: Sequence[tuple[float, float]], crs: Crs = WGS84) -> Geometry:
    """Return a Polygon from a ring given in one continuous longitude range, wrapped."""
    return Geometry(
        type="Polygon",
        coordinates=(tuple((wrap(lon), lat) for lon, lat in ring),),
        crs=crs,
    )


def landmark_location(
    key: str = MIAMI_DADE,
    *,
    name: str | None = None,
    nws: NwsCoverage | None = None,
    evacuation: bool = False,
) -> Location:
    """Return a public landmark as a location; Miami-Dade's carries its NWS zones."""
    coverage = nws if nws is not None else (MIAMI_DADE_ZONES if key == MIAMI_DADE else None)
    return Location(
        name=name or f"{key} landmark",
        point=landmark(key),
        nws=coverage,
        evacuation_order_in_effect=evacuation,
    )


def landmark_xy(key: str = MIAMI_DADE) -> tuple[float, float]:
    """Return a landmark's ``(longitude, latitude)``."""
    point = landmark(key)
    return (point.longitude, point.latitude)


def offset(key: str, east_deg: float = 0.0, north_deg: float = 0.0) -> tuple[float, float]:
    """Return the position some degrees east and north of a landmark."""
    lon, lat = landmark_xy(key)
    return (lon + east_deg, lat + north_deg)


def line(*positions: tuple[float, float], crs: Crs = WGS84) -> Geometry:
    """Return a LineString through the positions."""
    return Geometry(type="LineString", coordinates=tuple(positions), crs=crs)


def synthetic_summary(at: datetime = SYNTHETIC_AT, advisory: str = "1") -> StormSummary:
    """Return the synthetic storm's roster entry; its center is the Nassau landmark."""
    lon, lat = landmark_xy(NASSAU)
    product = RosterProduct(advisory=AdvisoryNumber.parse(advisory), issued_at=at)
    return StormSummary(
        atcf_id=SYNTHETIC_STORM,
        slot="CP1",
        name="Synthetic",
        classification=StormClassification.parse("HU"),
        intensity_kt=None,
        pressure_mb=None,
        latitude=lat,
        longitude=lon,
        movement_dir_deg=None,
        movement_speed_mph=None,
        last_update=at,
        public_advisory=product,
        has_storm_surge_watch_warning=False,
        has_potential_storm_surge_flooding=False,
        has_peak_surge=False,
    )


def synthetic_cone(geometry: Geometry, at: datetime = SYNTHETIC_AT) -> ConeGeometry:
    """Return the synthetic storm's cone."""
    return ConeGeometry(
        atcf_id=SYNTHETIC_STORM,
        advisory=synthetic_advisory(at),
        provenance=synthetic_provenance(at=at),
        forecast_period_h=120,
        geometry=geometry,
    )


def synthetic_segment(
    code: str, geometry: Geometry, at: datetime = SYNTHETIC_AT
) -> WatchWarningSegment:
    """Return a watch-warning segment of the synthetic storm with a ``tcww`` code."""
    return WatchWarningSegment(
        atcf_id=SYNTHETIC_STORM,
        advisory=synthetic_advisory(at),
        provenance=synthetic_provenance(at=at),
        tcww=WatchWarningType.parse(code),
        geometry=geometry,
        geometry_note="a one-vertex segment" if geometry.type == "Point" else None,
    )


def synthetic_arrivals(
    lines: Sequence[tuple[str | None, Geometry]],
    *,
    kind: Literal["earliest_reasonable", "most_likely"] = "earliest_reasonable",
    withheld_reason: str | None = None,
) -> ArrivalTimeProduct:
    """Return a KMZ arrival-time product of the synthetic storm, published at SYNTHETIC_AT.

    Args:
        lines: Each line's label (such as ``Tue 2 pm``; ``None`` for the outer contour)
            and geometry. The models resolve each label against the publication.
        kind: The product's kind.
        withheld_reason: Why every instant is withheld, for a withheld product.

    Returns:
        The product.
    """
    published = parse_nhc_local_time(ARRIVAL_PUBLISHED)
    return ArrivalTimeProduct(
        atcf_id=SYNTHETIC_STORM,
        advisory=Advisory(
            atcf_id=SYNTHETIC_STORM,
            number=AdvisoryNumber.parse("1"),
            issued_at=published,
            local_text=ARRIVAL_PUBLISHED,
        ),
        provenance=synthetic_provenance("nhc-arrival-times"),
        kind=kind,
        time_zone="EDT",
        published_at=published,
        published_local_text=ARRIVAL_PUBLISHED,
        origin="kmz",
        lines=tuple(
            ArrivalTimeLine.resolve(
                label,
                geometry,
                origin="kmz",
                published_at=published,
                time_zone="EDT",
                withheld_reason=withheld_reason,
            )
            for label, geometry in lines
        ),
        withheld_reason=withheld_reason,
    )


def synthetic_storm(  # noqa: PLR0913 - one keyword per kind of product
    *,
    cone: Geometry | None = None,
    points: Sequence[TrackPoint] = (),
    segments: Sequence[WatchWarningSegment] = (),
    arrivals: Sequence[ArrivalTimeProduct] = (),
    at: datetime = SYNTHETIC_AT,
    summary: StormSummary | None = None,
) -> StormProducts:
    """Return the synthetic storm with whichever products are given."""
    return StormProducts(
        summary=summary or synthetic_summary(at),
        cone=synthetic_cone(cone, at) if cone is not None else None,
        track_points=tuple(points),
        watch_warnings=tuple(segments),
        arrival_times=tuple(arrivals),
    )


def synthetic_wind(
    threshold: Literal[34, 50, 64],
    bands: Sequence[tuple[str, Geometry]],
    *,
    coverage: Geometry | None = None,
    at: datetime = SYNTHETIC_AT,
) -> WindProbabilityProduct:
    """Return a wind-speed-probability product with the labelled bands."""
    return WindProbabilityProduct(
        threshold_kt=threshold,
        synoptic_at=at - timedelta(hours=3),
        bands=tuple(WindProbabilityBand.from_label(label, shape) for label, shape in bands),
        coverage=coverage,
        provenance=synthetic_provenance(at=at),
    )


def synthetic_region(
    geometry: Geometry, chance_pct: int | None, at: datetime = SYNTHETIC_AT
) -> OutlookArea:
    """Return a seven-day development region with its seven-day chance."""
    return OutlookArea(
        kind="development_region",
        basin="Atlantic",
        chance_2day_pct=chance_pct,
        chance_7day_pct=chance_pct,
        risk_2day=None,
        risk_7day=None,
        outlook_stamp="gtwo_areas_synthetic",
        issued_at=at - timedelta(hours=1),
        geometry=geometry,
        provenance=synthetic_provenance(at=at),
    )


def _query(name: str, at: datetime) -> AlertQuery:
    if name == "point":
        return AlertQuery(kind="point", provenance=synthetic_provenance("nws-alerts-point", at))
    return AlertQuery(
        kind="zone", zone_id=name, provenance=synthetic_provenance("nws-alerts-zone", at)
    )


def synthetic_alert(  # noqa: PLR0913 - every field issue #10's rule reads
    event: str,
    *,
    queries: Sequence[str] = ("point",),
    zones: Sequence[str] = (),
    status: str = "Actual",
    message_type: str = "Alert",
    expires: datetime = SYNTHETIC_AT + timedelta(hours=12),
    at: datetime = SYNTHETIC_AT,
) -> NwsAlert:
    """Return an NWS alert found by the named queries (``point``, or a zone id)."""
    return NwsAlert(
        id=f"urn:oid:synthetic.{event.replace(' ', '-')}",
        event=event,
        headline=None,
        severity=AlertSeverity.parse("Extreme"),
        certainty=AlertCertainty.parse("Likely"),
        urgency=AlertUrgency.parse("Expected"),
        status=AlertStatus.parse(status),
        message_type=AlertMessageType.parse(message_type),
        category=AlertCategory.parse("Met"),
        sent=at - timedelta(hours=1),
        effective=at - timedelta(hours=1),
        onset=None,
        expires=expires,
        ends=None,
        area_desc="Synthetic area",
        sender_name="NWS Synthetic",
        references=(),
        vtec=(),
        nws_headline=(),
        description=None,
        instruction=None,
        affected_zone_ids=tuple(zones),
        geocode_same=(),
        geocode_ugc=tuple(zones),
        geometry=None,
        found_by=tuple(_query(name, at) for name in queries),
    )


SYNTHETIC_SOURCES: Final[tuple[SourceId, ...]] = (
    "nhc-current-storms",
    "nhc-map-tropical-summary",
    "nhc-map-breakpoints",
    "nhc-arrival-times",
    "nws-alerts-point",
    "nws-alerts-zone",
)


def synthetic_snapshot(  # noqa: PLR0913 - one keyword per kind of product
    *,
    storms: Sequence[StormProducts] = (),
    outlook: Sequence[OutlookArea] = (),
    winds: Sequence[WindProbabilityProduct] = (),
    alerts: dict[str, tuple[NwsAlert, ...]] | None = None,
    failed: Sequence[SourceId] = (),
    at: datetime = SYNTHETIC_AT,
) -> Snapshot:
    """Return a live snapshot completed at ``at``; a ``failed`` source holds no records."""
    return Snapshot(
        snapshot_id=SYNTHETIC_SNAPSHOT,
        started_at=at,
        completed_at=at,
        storms=tuple(storms),
        outlook_areas=tuple(outlook),
        wind_probabilities=tuple(winds),
        alerts=alerts if alerts is not None else {},
        source_outcomes=tuple(
            SourceOutcome(source_id=source, status="failed", error_kind="SourceHttpError")
            if source in failed
            else SourceOutcome(source_id=source, status="ok")
            for source in SYNTHETIC_SOURCES
        ),
    )
