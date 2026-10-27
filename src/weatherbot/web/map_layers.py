# src/weatherbot/web/map_layers.py
"""GeoJSON map layer builders, antimeridian unwrapping, and bounded per-snapshot cache.

``map_layers`` converts domain ``Snapshot`` and ``Location`` records into ``MapResponse``
and ``StormsResponse`` models without importing ``weatherbot.engine``, ``weatherbot.sources``,
or ``weatherbot.cli``. Every GeoJSON geometry, feature, and feature collection carries its
explicit ``crs`` member (``name`` and ``datum``, without ``wkt``) straight from the stored
``Geometry.crs``, without coordinate transformation or rounding.

Storm geometries (cones, tracks, forecast points, and coastal watch-warning segments) are
unwrapped into a continuous longitude domain relative to the storm's first forecast point
so Eastern and Central Pacific tracks crossing ``±180°`` render cleanly in Leaflet without
splitting polygons. Wind radii, wind-speed probabilities, breakpoints, and surge are not
served on the map in Phase 5 (Phase 7).

Per-snapshot derived payloads are cached in memory keyed by ``snapshot_id`` (bounded to the
8 most recent snapshot ids) so ``/api/map``, ``/api/storms``, and ``/api/alerts`` do not
re-decompress ``geometry_contents`` on every poll. The locations layer is built fresh on
every request so newly added locations and evacuation-order changes appear immediately.
"""

from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, cast
from uuid import UUID

from weatherbot.models import (
    Breakpoint,
    ConeGeometry,
    ForecastTrack,
    Geometry,
    Location,
    OutlookArea,
    Snapshot,
    StormProducts,
    TrackPoint,
    WatchWarningSegment,
)
from weatherbot.services.assessments import segment_breakpoint_names
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.persistence.repositories import (
    DriftWarning,
    SnapshotRepository,
    StoredAssessment,
)
from weatherbot.web.schemas import (
    ArrivalProductSummaryResponse,
    DriftWarningResponse,
    GeoJsonCrsResponse,
    GeoJsonFeatureCollectionResponse,
    GeoJsonFeatureResponse,
    GeoJsonGeometryResponse,
    MapResponse,
    OutlookAreaSummaryResponse,
    SnapshotSummaryResponse,
    StormMapLayersResponse,
    StormProductsSummaryResponse,
    StormSummaryResponse,
    WindProbabilitySummaryResponse,
)

MAX_SNAPSHOT_CACHE_SIZE: Final[int] = 8
ANTIMERIDIAN_HALF_TURN_DEG: Final[float] = 180.0
FULL_TURN_DEG: Final[float] = 360.0
DEFAULT_WGS84_CRS: Final = GeoJsonCrsResponse(name="EPSG:4326", datum=None)


def crs_to_response(geometry: Geometry) -> GeoJsonCrsResponse:
    """Extract ``name`` and ``datum`` (without ``wkt``) from a domain ``Geometry.crs``."""
    return GeoJsonCrsResponse(name=geometry.crs.name, datum=geometry.crs.datum)


def unwrap_longitude(lon: float, ref_lon: float) -> float:
    """Unwrap ``lon`` into a continuous domain within ``±180°`` of ``ref_lon``."""
    delta = lon - ref_lon
    if delta > ANTIMERIDIAN_HALF_TURN_DEG:
        return lon - FULL_TURN_DEG
    if delta < -ANTIMERIDIAN_HALF_TURN_DEG:
        return lon + FULL_TURN_DEG
    return lon


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _json_coordinates(coordinates: object) -> object:
    """Convert nested coordinate tuples to JSON-compatible lists without altering values."""
    if not isinstance(coordinates, (list, tuple)):
        return coordinates
    seq = cast("Sequence[object]", coordinates)
    if len(seq) >= 2 and _is_number(seq[0]) and _is_number(seq[1]):  # noqa: PLR2004 - [lon, lat] pair
        return [float(cast("int | float", v)) if _is_number(v) else v for v in seq]
    return [_json_coordinates(item) for item in seq]


def unwrap_coordinates(coordinates: object, ref_lon: float) -> object:
    """Recursively unwrap GeoJSON coordinate arrays relative to ``ref_lon``."""
    if not isinstance(coordinates, (list, tuple)):
        return coordinates
    seq = cast("Sequence[object]", coordinates)
    if len(seq) >= 2 and _is_number(seq[0]) and _is_number(seq[1]):  # noqa: PLR2004 - [lon, lat] pair
        lon_val = cast("int | float", seq[0])
        unwrapped_lon = unwrap_longitude(float(lon_val), ref_lon)
        rest = [float(cast("int | float", v)) if _is_number(v) else v for v in seq[1:]]
        return [unwrapped_lon, *rest]
    return [unwrap_coordinates(item, ref_lon) for item in seq]


def _first_longitude(coordinates: object) -> float | None:
    """Return the first longitude encountered in a nested GeoJSON coordinate structure."""
    if not isinstance(coordinates, (list, tuple)):
        return None
    seq = cast("Sequence[object]", coordinates)
    if len(seq) >= 2 and _is_number(seq[0]) and _is_number(seq[1]):  # noqa: PLR2004 - [lon, lat] pair
        return float(cast("int | float", seq[0]))
    for item in seq:
        found = _first_longitude(item)
        if found is not None:
            return found
    return None


def storm_reference_longitude(storm: StormProducts) -> float | None:
    """Determine a storm's reference longitude from its first forecast point (or fallback)."""
    if storm.track_points:
        first_point = storm.track_points[0].position.coordinates
        found = _first_longitude(first_point)
        if found is not None:
            return found
    if storm.summary is not None:
        return storm.summary.longitude
    if storm.track is not None:
        found = _first_longitude(storm.track.geometry.coordinates)
        if found is not None:
            return found
    if storm.cone is not None:
        return _first_longitude(storm.cone.geometry.coordinates)
    return None


def geometry_to_response(
    geometry: Geometry, *, ref_lon: float | None = None
) -> GeoJsonGeometryResponse:
    """Turn a domain ``Geometry`` into a ``GeoJsonGeometryResponse``, unwrapping when asked."""
    raw_coords = geometry.coordinates
    coordinates = (
        unwrap_coordinates(raw_coords, ref_lon)
        if ref_lon is not None
        else _json_coordinates(raw_coords)
    )
    return GeoJsonGeometryResponse(
        type=geometry.type,
        coordinates=coordinates,
        crs=crs_to_response(geometry),
    )


def _feature(
    geometry: Geometry,
    properties: dict[str, object],
    *,
    ref_lon: float | None = None,
) -> GeoJsonFeatureResponse:
    geom_response = geometry_to_response(geometry, ref_lon=ref_lon)
    return GeoJsonFeatureResponse(
        geometry=geom_response,
        properties=properties,
        crs=geom_response.crs,
    )


def _feature_collection(
    features: Sequence[GeoJsonFeatureResponse],
    *,
    default_crs: GeoJsonCrsResponse = DEFAULT_WGS84_CRS,
) -> GeoJsonFeatureCollectionResponse:
    crs = features[0].crs if features else default_crs
    return GeoJsonFeatureCollectionResponse(
        features=tuple(features),
        crs=crs,
    )


def _iso(instant: datetime | None) -> str | None:
    return instant.isoformat() if instant is not None else None


def _cone_feature(
    cone: ConeGeometry,
    storm_name: str,
    storm_type: str | None,
    *,
    ref_lon: float | None,
) -> GeoJsonFeatureResponse:
    return _feature(
        cone.geometry,
        {
            "atcf_id": cone.atcf_id,
            "storm_name": storm_name,
            "storm_type": storm_type,
            "advisory": str(cone.advisory.number),
            "issued_at": _iso(cone.advisory.issued_at),
            "forecast_period_h": cone.forecast_period_h,
        },
        ref_lon=ref_lon,
    )


def _track_feature(
    track: ForecastTrack,
    storm_name: str,
    storm_type: str | None,
    *,
    ref_lon: float | None,
) -> GeoJsonFeatureResponse:
    return _feature(
        track.geometry,
        {
            "atcf_id": track.atcf_id,
            "storm_name": storm_name,
            "storm_type": storm_type,
            "advisory": str(track.advisory.number),
            "issued_at": _iso(track.advisory.issued_at),
        },
        ref_lon=ref_lon,
    )


def _point_feature(
    point: TrackPoint, storm_name: str, *, ref_lon: float | None
) -> GeoJsonFeatureResponse:
    return _feature(
        point.position,
        {
            "atcf_id": point.atcf_id,
            "storm_name": storm_name,
            "advisory": str(point.advisory.number),
            "issued_at": _iso(point.advisory.issued_at),
            "valid_at": _iso(point.valid_at),
            "valid_local_text": point.valid_local_text,
            "tau_h": point.tau_h,
            "storm_type": point.storm_type,
            "development": point.development,
            "saffir_simpson": point.saffir_simpson,
            "label": point.label,
            "max_wind_kt": point.max_wind_kt,
            "gust_kt": point.gust_kt,
            "mslp_mb": point.mslp_mb,
            "direction_deg": point.direction_deg,
            "speed_kt": point.speed_kt,
        },
        ref_lon=ref_lon,
    )


def _watch_warning_feature(
    segment: WatchWarningSegment,
    storm_name: str,
    breakpoints: Sequence[Breakpoint],
    *,
    ref_lon: float | None,
) -> GeoJsonFeatureResponse:
    return _feature(
        segment.geometry,
        {
            "atcf_id": segment.atcf_id,
            "storm_name": storm_name,
            "advisory": str(segment.advisory.number),
            "issued_at": _iso(segment.advisory.issued_at),
            "tcww": segment.tcww.raw,
            "code": segment.tcww.code.value if segment.tcww.code is not None else None,
            "breakpoints": list(segment_breakpoint_names(segment.geometry, breakpoints)),
            "geometry_note": segment.geometry_note,
        },
        ref_lon=ref_lon,
    )


def _storm_advisory_and_issued_at(
    storm: StormProducts,
) -> tuple[str | None, datetime | None]:
    if storm.summary is not None:
        return (
            str(storm.summary.public_advisory.advisory),
            storm.summary.public_advisory.issued_at,
        )
    if storm.cone is not None:
        return str(storm.cone.advisory.number), storm.cone.advisory.issued_at
    if storm.track is not None:
        return str(storm.track.advisory.number), storm.track.advisory.issued_at
    if storm.track_points:
        first = storm.track_points[0]
        return str(first.advisory.number), first.advisory.issued_at
    return None, None


def build_storm_map_layers(
    storm: StormProducts,
    *,
    breakpoints: Sequence[Breakpoint] = (),
) -> StormMapLayersResponse:
    """Build the GeoJSON map layers for a single active or replayed storm."""
    ref_lon = storm_reference_longitude(storm)
    storm_name = storm.name
    advisory, issued_at = _storm_advisory_and_issued_at(storm)
    classification = (
        storm.summary.classification.raw
        if storm.summary is not None
        else (storm.archived.storm_type if storm.archived is not None else None)
    )
    intensity_kt = (
        storm.summary.intensity_kt
        if storm.summary is not None
        else (storm.track_points[0].max_wind_kt if storm.track_points else None)
    )
    pressure_mb = (
        storm.summary.pressure_mb
        if storm.summary is not None
        else (storm.track_points[0].mslp_mb if storm.track_points else None)
    )

    cone_feature = (
        _cone_feature(storm.cone, storm_name, classification, ref_lon=ref_lon)
        if storm.cone is not None
        else None
    )
    track_feature = (
        _track_feature(storm.track, storm_name, classification, ref_lon=ref_lon)
        if storm.track is not None
        else None
    )
    storm_crs = (
        cone_feature.crs
        if cone_feature is not None
        else (track_feature.crs if track_feature is not None else DEFAULT_WGS84_CRS)
    )
    point_features = [_point_feature(pt, storm_name, ref_lon=ref_lon) for pt in storm.track_points]
    segment_features = [
        _watch_warning_feature(seg, storm_name, breakpoints, ref_lon=ref_lon)
        for seg in storm.watch_warnings
    ]

    return StormMapLayersResponse(
        atcf_id=storm.atcf_id,
        name=storm_name,
        classification=classification,
        intensity_kt=intensity_kt,
        pressure_mb=pressure_mb,
        advisory=advisory,
        issued_at=issued_at,
        cone=cone_feature,
        track=track_feature,
        forecast_points=_feature_collection(point_features, default_crs=storm_crs),
        watch_warnings=_feature_collection(segment_features, default_crs=storm_crs),
    )


def _outlook_features(areas: Sequence[OutlookArea]) -> tuple[GeoJsonFeatureResponse, ...]:
    return tuple(
        _feature(
            area.geometry,
            {
                "basin": area.basin,
                "kind": area.kind,
                "chance_2day_pct": area.chance_2day_pct,
                "chance_7day_pct": area.chance_7day_pct,
                "risk_2day": area.risk_2day.raw if area.risk_2day is not None else None,
                "risk_7day": area.risk_7day.raw if area.risk_7day is not None else None,
                "issued_at": _iso(area.issued_at),
                "outlook_stamp": area.outlook_stamp,
            },
        )
        for area in areas
    )


def build_storm_summaries(snapshot: Snapshot) -> tuple[StormSummaryResponse, ...]:
    """Build geometry-free storm summary entries matching ``StormsDocument``."""
    return tuple(
        StormSummaryResponse(
            atcf_id=summary.atcf_id,
            slot=summary.slot,
            name=summary.name,
            classification=summary.classification,
            intensity_kt=summary.intensity_kt,
            pressure_mb=summary.pressure_mb,
            movement_dir_deg=summary.movement_dir_deg,
            movement_speed_mph=summary.movement_speed_mph,
            advisory=str(summary.public_advisory.advisory),
            advisory_issued_at=summary.public_advisory.issued_at,
            last_update=summary.last_update,
            products=StormProductsSummaryResponse(
                cone=storm.cone is not None,
                track=storm.track is not None,
                track_points=len(storm.track_points),
                watch_warning_segments=len(storm.watch_warnings),
                wind_radii=len(storm.wind_radii),
                arrival_times=tuple(
                    ArrivalProductSummaryResponse(
                        kind=product.kind,
                        origin=product.origin,
                        advisory=str(product.advisory.number),
                        published_at=product.published_at,
                        time_zone=product.time_zone,
                        lines=len(product.lines),
                        withheld_reason=product.withheld_reason,
                    )
                    for product in storm.arrival_times
                ),
            ),
        )
        for storm in snapshot.storms
        if (summary := storm.summary) is not None
    )


def build_outlook_summaries(snapshot: Snapshot) -> tuple[OutlookAreaSummaryResponse, ...]:
    """Build geometry-free Tropical Weather Outlook entries matching ``StormsDocument``."""
    return tuple(
        OutlookAreaSummaryResponse(
            basin=area.basin,
            kind=area.kind,
            chance_2day_pct=area.chance_2day_pct,
            chance_7day_pct=area.chance_7day_pct,
            risk_2day=area.risk_2day,
            risk_7day=area.risk_7day,
            issued_at=area.issued_at,
        )
        for area in snapshot.outlook_areas
    )


def build_wind_probability_summaries(
    snapshot: Snapshot,
) -> tuple[WindProbabilitySummaryResponse, ...]:
    """Build geometry-free wind-probability summaries matching ``StormsDocument``."""
    return tuple(
        WindProbabilitySummaryResponse(
            threshold_kt=product.threshold_kt,
            synoptic_at=product.synoptic_at,
            bands=len(product.bands),
        )
        for product in snapshot.wind_probabilities
    )


@dataclass(frozen=True)
class SnapshotMapLayers:
    """Cached per-snapshot GeoJSON layers (excluding per-request watched locations)."""

    snapshot_id: UUID
    as_of: datetime
    status: str
    origin: str
    storms: tuple[StormMapLayersResponse, ...]
    outlook_areas: GeoJsonFeatureCollectionResponse


@dataclass(frozen=True)
class CachedSnapshotBundle:
    """Cached snapshot, drift warnings, GeoJSON map layers, and geometry-free storm summaries."""

    snapshot: Snapshot
    drift_warnings: tuple[DriftWarning, ...]
    map_layers: SnapshotMapLayers
    storm_summaries: tuple[StormSummaryResponse, ...]
    outlook_summaries: tuple[OutlookAreaSummaryResponse, ...]
    wind_probability_summaries: tuple[WindProbabilitySummaryResponse, ...]

    def summary(self, now: datetime) -> SnapshotSummaryResponse:
        """Build a ``SnapshotSummaryResponse`` with age computed at ``now``."""
        age = round(max((now - self.snapshot.completed_at).total_seconds(), 0.0), 1)
        return SnapshotSummaryResponse(
            snapshot_id=self.snapshot.snapshot_id,
            started_at=self.snapshot.started_at,
            completed_at=self.snapshot.completed_at,
            status=self.snapshot.status,
            age_seconds=age,
            source_outcomes=self.snapshot.source_outcomes,
            drift_warnings=tuple(
                DriftWarningResponse(source_id=w.source_id, message=w.message)
                for w in self.drift_warnings
            ),
        )


def _compute_snapshot_map_layers(snapshot: Snapshot) -> SnapshotMapLayers:
    storms = tuple(
        build_storm_map_layers(storm, breakpoints=snapshot.breakpoints) for storm in snapshot.storms
    )
    outlook_areas = _feature_collection(_outlook_features(snapshot.outlook_areas))
    return SnapshotMapLayers(
        snapshot_id=snapshot.snapshot_id,
        as_of=snapshot.completed_at,
        status=snapshot.status,
        origin=snapshot.origin,
        storms=storms,
        outlook_areas=outlook_areas,
    )


class SnapshotLayerCache:
    """Bounded LRU cache of at most ``MAX_SNAPSHOT_CACHE_SIZE`` (8) snapshots."""

    def __init__(self, max_size: int = MAX_SNAPSHOT_CACHE_SIZE) -> None:
        """Initialize the cache with ``max_size`` (capped at ``MAX_SNAPSHOT_CACHE_SIZE``)."""
        if max_size < 1 or max_size > MAX_SNAPSHOT_CACHE_SIZE:
            msg = f"max_size must be in 1..{MAX_SNAPSHOT_CACHE_SIZE}"
            raise ValueError(msg)
        self._max_size = max_size
        self._entries: OrderedDict[UUID, CachedSnapshotBundle] = OrderedDict()

    @property
    def max_size(self) -> int:
        """Maximum number of snapshot ids held in the cache."""
        return self._max_size

    def __len__(self) -> int:
        """Current number of cached snapshot ids."""
        return len(self._entries)

    def keys(self) -> tuple[UUID, ...]:
        """Cached snapshot ids from oldest to newest."""
        return tuple(self._entries.keys())

    def clear(self) -> None:
        """Remove all cached snapshot bundles."""
        self._entries.clear()

    def get(self, snapshot_id: UUID) -> CachedSnapshotBundle | None:
        """Return the cached bundle for ``snapshot_id`` and mark it most-recently used."""
        bundle = self._entries.get(snapshot_id)
        if bundle is not None:
            self._entries.move_to_end(snapshot_id)
        return bundle

    def put(self, bundle: CachedSnapshotBundle) -> CachedSnapshotBundle:
        """Insert ``bundle`` into the cache, evicting the oldest entry above ``max_size``."""
        key = bundle.snapshot.snapshot_id
        self._entries[key] = bundle
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_size:
            self._entries.popitem(last=False)
        return bundle

    def get_or_build(
        self,
        snapshot: Snapshot,
        *,
        drift_warnings: tuple[DriftWarning, ...] = (),
    ) -> CachedSnapshotBundle:
        """Return the cached bundle for ``snapshot.snapshot_id``, or build and cache it."""
        existing = self.get(snapshot.snapshot_id)
        if existing is not None:
            return existing
        bundle = CachedSnapshotBundle(
            snapshot=snapshot,
            drift_warnings=drift_warnings,
            map_layers=_compute_snapshot_map_layers(snapshot),
            storm_summaries=build_storm_summaries(snapshot),
            outlook_summaries=build_outlook_summaries(snapshot),
            wind_probability_summaries=build_wind_probability_summaries(snapshot),
        )
        return self.put(bundle)

    def get_or_load(self, repository: SnapshotRepository) -> CachedSnapshotBundle | None:
        """Return the latest stored snapshot's bundle, loading from SQLite only on cache miss."""
        snapshot_id = repository.latest_id()
        if snapshot_id is None:
            return None
        cached = self.get(snapshot_id)
        if cached is not None:
            return cached
        snapshot = repository.load(snapshot_id)
        if snapshot is None:
            return None
        warnings = repository.drift_warnings(snapshot_id)
        return self.get_or_build(snapshot, drift_warnings=warnings)


SNAPSHOT_CACHE: Final = SnapshotLayerCache(max_size=MAX_SNAPSHOT_CACHE_SIZE)


def get_cached_snapshot_bundle(
    repository: SnapshotRepository,
    *,
    cache: SnapshotLayerCache = SNAPSHOT_CACHE,
) -> CachedSnapshotBundle | None:
    """Return the latest snapshot's cached bundle through ``cache``."""
    return cache.get_or_load(repository)


def build_snapshot_map_layers(
    snapshot: Snapshot,
    *,
    cache: SnapshotLayerCache = SNAPSHOT_CACHE,
) -> SnapshotMapLayers:
    """Build or retrieve cached ``SnapshotMapLayers`` for ``snapshot``."""
    return cache.get_or_build(snapshot).map_layers


def build_locations_layers(
    locations: Sequence[Location],
    assessments: Mapping[str, StoredAssessment | None] | None = None,
) -> tuple[GeoJsonFeatureCollectionResponse, GeoJsonFeatureCollectionResponse]:
    """Build the ``locations`` and ``location_polygons`` GeoJSON collections per request."""
    all_features: list[GeoJsonFeatureResponse] = []
    polygon_features: list[GeoJsonFeatureResponse] = []
    by_name = assessments or {}

    for location in locations:
        stored = by_name.get(location.name)
        level_num: int | None = None
        level_label: str | None = None
        in_cone: bool | None = None
        if stored is not None:
            level_num = int(stored.assessment.level)
            level_label = stored.assessment.level.label
            cone_flags = [
                threat.in_cone for threat in stored.assessment.threats if threat.in_cone is not None
            ]
            if cone_flags:
                in_cone = any(cone_flags)

        point_geom = GeoJsonGeometryResponse(
            type="Point",
            coordinates=[location.point.longitude, location.point.latitude],
            crs=DEFAULT_WGS84_CRS,
        )
        point_feature = GeoJsonFeatureResponse(
            geometry=point_geom,
            properties={
                "feature_kind": "point",
                "name": location.name,
                "display_name": location.display_name,
                "country_code": location.country_code,
                "inside_nws_coverage": location.nws is not None,
                "level": level_num,
                "label": level_label,
                "in_cone": in_cone,
                "evacuation_order_in_effect": location.evacuation_order_in_effect,
                "has_polygon": location.polygon is not None,
            },
            crs=DEFAULT_WGS84_CRS,
        )
        all_features.append(point_feature)

        if location.polygon is not None:
            poly_feature = _feature(
                location.polygon,
                {
                    "feature_kind": "polygon",
                    "name": location.name,
                    "display_name": location.display_name,
                    "level": level_num,
                    "label": level_label,
                    "in_cone": in_cone,
                    "evacuation_order_in_effect": location.evacuation_order_in_effect,
                },
            )
            all_features.append(poly_feature)
            polygon_features.append(poly_feature)

    return _feature_collection(all_features), _feature_collection(polygon_features)


def build_map_response(
    snapshot: Snapshot | None,
    locations: Sequence[Location],
    *,
    assessments: Mapping[str, StoredAssessment | None] | None = None,
    cache: SnapshotLayerCache = SNAPSHOT_CACHE,
) -> MapResponse:
    """Assemble a full ``MapResponse`` from ``snapshot`` (cached) and ``locations`` (fresh)."""
    locations_fc, polygons_fc = build_locations_layers(locations, assessments)
    if snapshot is None:
        empty = _feature_collection(())
        return MapResponse(
            snapshot_id=None,
            as_of=None,
            status=None,
            origin=None,
            storms=(),
            outlook_areas=empty,
            locations=locations_fc,
            location_polygons=polygons_fc,
            notice=NOTICE,
        )
    layers = build_snapshot_map_layers(snapshot, cache=cache)
    return MapResponse(
        snapshot_id=layers.snapshot_id,
        as_of=layers.as_of,
        status=snapshot.status,
        origin=snapshot.origin,
        storms=layers.storms,
        outlook_areas=layers.outlook_areas,
        locations=locations_fc,
        location_polygons=polygons_fc,
        notice=NOTICE,
    )
