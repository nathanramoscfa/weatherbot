# tests/web/test_map_layers.py
"""Tests for ``weatherbot.web.map_layers``: GeoJSON layers, antimeridian unwrap, and LRU cache."""

import asyncio
from datetime import timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from collections.abc import Sequence

import httpx
import pytest
from cli_support import MIAMI, NASSAU, add_landmark, recorded_services, run
from source_support import NOW

from weatherbot.models import (
    WGS84,
    Advisory,
    AdvisoryNumber,
    ArchiveStorm,
    ConeGeometry,
    ForecastTrack,
    Geometry,
    Provenance,
    Snapshot,
    StormProducts,
    TrackPoint,
    WatchWarningSegment,
    WatchWarningType,
)
from weatherbot.services.config import AppPaths, load_settings, setting_origins
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import SnapshotRepository
from weatherbot.web.app import WebState, create_app
from weatherbot.web.map_layers import (
    MAX_SNAPSHOT_CACHE_SIZE,
    SNAPSHOT_CACHE,
    SnapshotLayerCache,
    build_storm_map_layers,
    unwrap_longitude,
)
from weatherbot.web.schemas import MapResponse


def _provenance() -> Provenance:
    return Provenance(
        source_id="nhc-map-tropical-weather",
        url="https://mapservices.weather.noaa.gov/tropical/rest/services/tropical/NHC_tropical_weather_summary/MapServer/0/query",
        status=200,
        fetched_at=NOW,
        sha256="a" * 64,
        issued_at=NOW,
        advisory=AdvisoryNumber.parse("1"),
    )


def _advisory(atcf_id: str = "CP012026") -> Advisory:
    return Advisory(
        atcf_id=atcf_id,
        number=AdvisoryNumber.parse("1"),
        issued_at=NOW,
        local_text="1100 AM HST Mon Oct 12 2026",
        issued_at_source="roster",
    )


def _collect_longitudes(coordinates: object) -> list[float]:
    if not isinstance(coordinates, (list, tuple)):
        return []
    seq = cast("Sequence[object]", coordinates)
    if (
        len(seq) >= 2  # noqa: PLR2004
        and isinstance(seq[0], (int, float))
        and isinstance(seq[1], (int, float))
    ):
        return [float(seq[0])]
    out: list[float] = []
    for item in seq:
        out.extend(_collect_longitudes(item))
    return out


def test_recorded_snapshot_map_layers_counts_properties_crs_and_omits_wind_radii() -> None:
    with recorded_services():
        assert add_landmark(MIAMI, "miami-dade", "--polygon", "forecast").exit_code == 0
        assert add_landmark(NASSAU, "nassau").exit_code == 0
        assert run(["check", "--once"]).exit_code == 0

    SNAPSHOT_CACHE.clear()
    paths = AppPaths.resolve()
    database = open_database(paths, now=lambda: NOW)
    try:
        state = WebState(
            database=database,
            paths=paths,
            settings=load_settings(paths),
            setting_origins=setting_origins(paths),
            clock=lambda: NOW,
            started_at=NOW - timedelta(minutes=10),
        )
        app = create_app(state)

        async def _get_map() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                return await client.get("/api/map")

        response = asyncio.run(_get_map())
    finally:
        database.close()

    assert response.status_code == HTTPStatus.OK
    raw = cast("dict[str, object]", response.json())
    assert {"wind_probabilities", "wind_radii", "display_layers"}.isdisjoint(raw)

    parsed = MapResponse.model_validate_json(response.text)
    assert (parsed.snapshot_id is not None, parsed.origin, len(parsed.storms)) == (
        True,
        "live",
        1,
    )

    storm = parsed.storms[0]
    assert (storm.atcf_id, storm.name) == ("EP202026", "Simon")
    assert storm.cone is not None
    assert (storm.cone.crs.name, storm.cone.crs.datum) == ("EPSG:4326", None)
    assert "wkt" not in cast("dict[str, object]", raw["storms"][0]["cone"]["crs"])  # type: ignore[index]
    assert storm.track is not None
    assert storm.track.crs.name == "EPSG:4326"
    assert len(storm.forecast_points.features) > 0
    assert storm.forecast_points.crs.name == "EPSG:4326"
    first_pt = storm.forecast_points.features[0]
    assert first_pt.properties["atcf_id"] == "EP202026"
    assert first_pt.properties["storm_name"] == "Simon"
    assert {"valid_at", "max_wind_kt", "storm_type"} <= set(first_pt.properties)

    assert parsed.outlook_areas.crs.name == "EPSG:4326"
    assert len(parsed.outlook_areas.features) > 0
    assert {"basin", "chance_2day_pct", "chance_7day_pct"} <= set(
        parsed.outlook_areas.features[0].properties
    )

    # 2 location point features + 1 stored forecast polygon feature = 3 features in `locations`
    assert len(parsed.locations.features) == 3  # noqa: PLR2004
    assert len(parsed.location_polygons.features) == 1
    assert parsed.location_polygons.features[0].properties["name"] == MIAMI


def test_central_pacific_storm_crossing_antimeridian_is_unwrapped_to_continuous_lons() -> None:
    # All coordinate literals use at most two decimal places.
    prov = _provenance()
    adv = _advisory("CP012026")
    pt0 = TrackPoint(
        atcf_id="CP012026",
        advisory=adv,
        provenance=prov,
        tau_h=0,
        valid_at=NOW,
        valid_local_text=None,
        position=Geometry.from_geojson({"type": "Point", "coordinates": [-179.5, 18.0]}, WGS84),
        max_wind_kt=75,
        gust_kt=90,
        mslp_mb=985,
        direction_deg=280,
        speed_kt=12,
        development="Hurricane",
        storm_type="HU",
        saffir_simpson=1,
        label="H",
    )
    pt12 = TrackPoint(
        atcf_id="CP012026",
        advisory=adv,
        provenance=prov,
        tau_h=12,
        valid_at=NOW + timedelta(hours=12),
        valid_local_text=None,
        position=Geometry.from_geojson({"type": "Point", "coordinates": [179.5, 18.5]}, WGS84),
        max_wind_kt=80,
        gust_kt=95,
        mslp_mb=980,
        direction_deg=280,
        speed_kt=12,
        development="Hurricane",
        storm_type="HU",
        saffir_simpson=1,
        label="H",
    )
    cone = ConeGeometry(
        atcf_id="CP012026",
        advisory=adv,
        provenance=prov,
        forecast_period_h=120,
        geometry=Geometry.from_geojson(
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-179.5, 18.0],
                        [179.5, 18.5],
                        [178.5, 19.0],
                        [-178.5, 18.5],
                        [-179.5, 18.0],
                    ]
                ],
            },
            WGS84,
        ),
    )
    track = ForecastTrack(
        atcf_id="CP012026",
        advisory=adv,
        provenance=prov,
        geometry=Geometry.from_geojson(
            {
                "type": "LineString",
                "coordinates": [[-179.5, 18.0], [179.5, 18.5], [178.5, 19.0]],
            },
            WGS84,
        ),
    )
    segment = WatchWarningSegment(
        atcf_id="CP012026",
        advisory=adv,
        provenance=prov,
        tcww=WatchWarningType.parse("HWR"),
        geometry=Geometry.from_geojson(
            {
                "type": "LineString",
                "coordinates": [[-179.2, 18.2], [179.2, 18.4]],
            },
            WGS84,
        ),
    )
    storm = StormProducts(
        summary=None,
        archived=ArchiveStorm(
            atcf_id="CP012026",
            name="Keli",
            storm_type="HU",
            provenance=prov.model_copy(update={"source_id": "nhc-gis-archive"}),
        ),
        cone=cone,
        track=track,
        track_points=(pt0, pt12),
        watch_warnings=(segment,),
    )

    layers = build_storm_map_layers(storm)
    assert layers.cone is not None
    assert layers.track is not None
    cone_lons = _collect_longitudes(layers.cone.geometry.coordinates)
    track_lons = _collect_longitudes(layers.track.geometry.coordinates)
    point_lons = [
        lon
        for feat in layers.forecast_points.features
        for lon in _collect_longitudes(feat.geometry.coordinates)
    ]
    seg_lons = [
        lon
        for feat in layers.watch_warnings.features
        for lon in _collect_longitudes(feat.geometry.coordinates)
    ]

    assert cone_lons == [-179.5, -180.5, -181.5, -178.5, -179.5]
    assert track_lons == [-179.5, -180.5, -181.5]
    assert point_lons == [-179.5, -180.5]
    assert seg_lons == [-179.2, -180.8]
    # Also verify unwrap_longitude when ref_lon is positive (+179.5) and lon is negative (-179.5).
    assert unwrap_longitude(-179.5, 179.5) == 180.5  # noqa: PLR2004


def test_snapshot_cache_reuses_decoded_snapshot_and_refreshes_on_new_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with recorded_services():
        assert add_landmark(MIAMI, "miami-dade").exit_code == 0
        assert run(["check", "--once"]).exit_code == 0

    SNAPSHOT_CACHE.clear()
    paths = AppPaths.resolve()
    database = open_database(paths, now=lambda: NOW)
    load_calls: list[object] = []
    original_load = SnapshotRepository.load

    def counting_load(self: SnapshotRepository, snapshot_id: object) -> Snapshot | None:
        load_calls.append(snapshot_id)
        return original_load(self, snapshot_id)  # type: ignore[arg-type]

    monkeypatch.setattr(SnapshotRepository, "load", counting_load)

    try:
        state = WebState(
            database=database,
            paths=paths,
            settings=load_settings(paths),
            setting_origins=setting_origins(paths),
            clock=lambda: NOW,
            started_at=NOW - timedelta(minutes=10),
        )
        app = create_app(state)

        async def _poll_three_routes() -> tuple[str, str, str]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                m1 = (await client.get("/api/map")).json()["snapshot_id"]
                m2 = (await client.get("/api/map")).json()["snapshot_id"]
                s1 = (await client.get("/api/storms")).json()["snapshot"]["snapshot_id"]
                a1 = (await client.get("/api/alerts")).json()["snapshot"]["snapshot_id"]
                return str(m1), str(m2), str(s1) if s1 == a1 else ""

        first_id, second_id, shared_id = asyncio.run(_poll_three_routes())
        assert first_id == second_id == shared_id
        # SnapshotRepository.load was called only ONCE across all four requests!
        assert len(load_calls) == 1

        # Store a newer snapshot and verify the next request loads the new snapshot once.
        repo = SnapshotRepository(database.engine)
        latest = original_load(repo, repo.latest_id())  # type: ignore[arg-type]
        assert latest is not None
        newer = latest.model_copy(
            update={
                "snapshot_id": uuid4(),
                "started_at": NOW + timedelta(minutes=15),
                "completed_at": NOW + timedelta(minutes=15),
            }
        )
        repo.save(newer)

        async def _poll_after_new_snapshot() -> str:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                m3 = (await client.get("/api/map")).json()["snapshot_id"]
                m4 = (await client.get("/api/storms")).json()["snapshot"]["snapshot_id"]
                assert m3 == m4
                return str(m3)

        updated_id = asyncio.run(_poll_after_new_snapshot())
        assert updated_id == str(newer.snapshot_id)
        assert len(load_calls) == 2  # noqa: PLR2004

        # Verify bounded LRU eviction at MAX_SNAPSHOT_CACHE_SIZE (8).
        small_cache = SnapshotLayerCache(max_size=MAX_SNAPSHOT_CACHE_SIZE)
        inserted_ids: list[UUID] = []
        for idx in range(MAX_SNAPSHOT_CACHE_SIZE + 3):
            snap = latest.model_copy(
                update={
                    "snapshot_id": uuid4(),
                    "completed_at": NOW + timedelta(minutes=idx),
                }
            )
            inserted_ids.append(snap.snapshot_id)
            small_cache.get_or_build(snap)
        assert len(small_cache) == MAX_SNAPSHOT_CACHE_SIZE
        assert small_cache.keys() == tuple(inserted_ids[-MAX_SNAPSHOT_CACHE_SIZE:])
    finally:
        database.close()
