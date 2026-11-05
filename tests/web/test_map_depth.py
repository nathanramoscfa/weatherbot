# tests/web/test_map_depth.py
"""Tests for ``GET /api/map/depth`` and ``MapResponse.available_layers``."""

import asyncio
import json
from datetime import timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import httpx
from cli_support import MIAMI, NASSAU, add_landmark, recorded_services, run
from source_support import NOW

from synthetic_surge import synthetic_surge_layers
from weatherbot.models import (
    WGS84,
    Advisory,
    AdvisoryNumber,
    ArchiveStorm,
    DisplayLayer,
    Geometry,
    Provenance,
    RosterProduct,
    StormClassification,
    StormProducts,
    StormSummary,
    TrackPoint,
    WindRadii,
)
from weatherbot.services.config import AppPaths, load_settings, setting_origins
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import SnapshotRepository
from weatherbot.web.app import WebState, create_app
from weatherbot.web.map_layers import (
    SNAPSHOT_CACHE,
    build_map_depth_response,
    build_storm_map_depth,
)
from weatherbot.web.schemas import (
    ALL_MAP_LAYERS,
    REPLAY_MAP_LAYERS,
    STORED_ADVISORY_MAP_LAYERS,
    MapDepthResponse,
    MapResponse,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


def _provenance() -> Provenance:
    return Provenance(
        source_id="nhc-map-tropical-summary",
        url="https://mapservices.weather.noaa.gov/tropical/rest/services/tropical/NHC_tropical_weather_summary/MapServer/0/query",
        status=200,
        fetched_at=NOW,
        sha256="b" * 64,
        issued_at=NOW,
        advisory=AdvisoryNumber.parse("15"),
    )


def _advisory(atcf_id: str = "AL142026") -> Advisory:
    return Advisory(
        atcf_id=atcf_id,
        number=AdvisoryNumber.parse("15"),
        issued_at=NOW,
        local_text="500 PM EDT Mon Oct 12 2026",
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


def test_recorded_snapshot_map_depth_and_map_payload_size_budget() -> None:
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

        async def _fetch_both() -> tuple[httpx.Response, httpx.Response]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                return await client.get("/api/map"), await client.get("/api/map/depth")

        map_res, depth_res = asyncio.run(_fetch_both())
    finally:
        database.close()

    assert map_res.status_code == HTTPStatus.OK
    assert depth_res.status_code == HTTPStatus.OK

    parsed_map = MapResponse.model_validate_json(map_res.text)
    assert parsed_map.available_layers == ALL_MAP_LAYERS

    # Pin /api/map's recorded answer growth at under 1 KB compared to without available_layers.
    raw_map = cast("dict[str, object]", map_res.json())
    without_available = {k: v for k, v in raw_map.items() if k != "available_layers"}
    growth_bytes = len(json.dumps(raw_map).encode("utf-8")) - len(
        json.dumps(without_available).encode("utf-8")
    )
    assert 0 < growth_bytes < 1024  # noqa: PLR2004

    parsed_depth = MapDepthResponse.model_validate_json(depth_res.text)
    assert parsed_depth.snapshot_id == parsed_map.snapshot_id
    assert len(parsed_depth.storms) == 1
    storm_depth = parsed_depth.storms[0]
    assert storm_depth.atcf_id == "EP202026"
    assert len(storm_depth.wind_radii.features) > 0
    first_radii = storm_depth.wind_radii.features[0]
    assert {
        "threshold_kt",
        "tau_h",
        "valid_at",
        "ne_extent_nmi",
        "se_extent_nmi",
        "sw_extent_nmi",
        "nw_extent_nmi",
        "advisory",
    } <= set(first_radii.properties)

    assert len(storm_depth.past_track.features) > 0
    assert len(storm_depth.past_points.features) > 0
    for feat in (*storm_depth.past_track.features, *storm_depth.past_points.features):
        assert {"lat", "lon", "binnumber", "stormnum"}.isdisjoint(feat.properties)
        assert set(feat.properties) <= {"stormtype", "ss", "intensity", "mslp", "dtg"}


def test_slot_and_stormnum_selection_synthetic_surge_and_antimeridian_unwrap() -> None:
    prov = _provenance()
    adv = _advisory("CP042026")
    summary = StormSummary(
        atcf_id="CP042026",
        slot="CP4",
        name="Akoni",
        classification=StormClassification.parse("HU"),
        intensity_kt=80,
        pressure_mb=978,
        latitude=18.0,
        longitude=-179.5,
        movement_dir_deg=280.0,
        movement_speed_mph=14.0,
        last_update=NOW,
        public_advisory=RosterProduct(advisory=AdvisoryNumber.parse("15"), issued_at=NOW),
        has_storm_surge_watch_warning=False,
        has_potential_storm_surge_flooding=False,
        has_peak_surge=False,
    )
    radii = WindRadii(
        atcf_id="CP042026",
        advisory=AdvisoryNumber.parse("15"),
        provenance=prov,
        threshold_kt=34,
        tau_h=0,
        valid_at=NOW,
        synoptic_at=NOW,
        ne_extent_nmi=90,
        se_extent_nmi=80,
        sw_extent_nmi=60,
        nw_extent_nmi=75,
        is_advisory_field=True,
        geometry=Geometry(
            type="Polygon",
            coordinates=(
                (
                    (-179.5, 18.0),
                    (179.5, 18.5),
                    (178.5, 19.0),
                    (-179.5, 18.0),
                ),
            ),
            crs=WGS84,
        ),
    )
    pt0 = TrackPoint(
        atcf_id="CP042026",
        advisory=adv,
        provenance=prov,
        tau_h=0,
        valid_at=NOW,
        valid_local_text=None,
        position=Geometry(type="Point", coordinates=(-179.5, 18.0), crs=WGS84),
        max_wind_kt=80,
        gust_kt=95,
        mslp_mb=978,
        direction_deg=280,
        speed_kt=12,
        development="Hurricane",
        storm_type="HU",
        saffir_simpson=1,
        label="H",
    )
    storm = StormProducts(
        summary=summary,
        cone=None,
        track=None,
        track_points=(pt0,),
        wind_radii=(radii,),
    )

    past_track_layer = DisplayLayer(
        layer_name="Past Track",
        crs=WGS84,
        provenance=prov,
        feature_collection={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "binnumber": "CP4",
                        "stormnum": 4,
                        "stormtype": "HU",
                        "ss": 1,
                        "lat": 18.0,
                        "lon": -179.5,
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-179.5, 18.0], [179.5, 18.5]],
                    },
                },
                # Reused slot CP4 from a different storm number (stormnum=9) must be excluded.
                {
                    "type": "Feature",
                    "properties": {
                        "binnumber": "CP4",
                        "stormnum": 9,
                        "stormtype": "TS",
                        "ss": 0,
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-150.0, 15.0], [-151.0, 15.5]],
                    },
                },
            ],
        },
    )
    past_points_layer = DisplayLayer(
        layer_name="Past Points",
        crs=WGS84,
        provenance=prov,
        feature_collection={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "binnumber": "CP4",
                        "stormnum": 4,
                        "stormname": "Akoni",
                        "stormtype": "HU",
                        "ss": 1,
                        "intensity": 80,
                        "mslp": 978,
                        "dtg": "2026-10-12 18:00 UTC",
                        "lat": 18.5,
                        "lon": 179.5,
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [179.5, 18.5],
                    },
                },
            ],
        },
    )

    depth = build_storm_map_depth(storm, (past_track_layer, past_points_layer))
    assert len(depth.wind_radii.features) == 1
    assert len(depth.past_track.features) == 1
    assert len(depth.past_points.features) == 1

    radii_lons = _collect_longitudes(depth.wind_radii.features[0].geometry.coordinates)
    track_lons = _collect_longitudes(depth.past_track.features[0].geometry.coordinates)
    point_lons = _collect_longitudes(depth.past_points.features[0].geometry.coordinates)
    assert radii_lons == [-179.5, -180.5, -181.5, -179.5]
    assert track_lons == [-179.5, -180.5]
    assert point_lons == [-180.5]

    pt_props = depth.past_points.features[0].properties
    assert pt_props == {
        "stormtype": "HU",
        "ss": 1,
        "intensity": 80,
        "mslp": 978,
        "dtg": "2026-10-12 18:00 UTC",
    }

    # Replay storm (summary=None, archived set) has no slot and receives empty past collections.
    replay_storm = StormProducts(
        summary=None,
        archived=ArchiveStorm(
            atcf_id="CP042026",
            name="Akoni",
            storm_type="HU",
            provenance=prov.model_copy(update={"source_id": "nhc-gis-archive"}),
        ),
    )
    replay_depth = build_storm_map_depth(replay_storm, (past_track_layer, past_points_layer))
    assert replay_depth.past_track.features == ()
    assert replay_depth.past_points.features == ()

    # Synthetic peak surge layers reduce properties to name and layer.
    with recorded_services():
        assert run(["check", "--once"]).exit_code == 0
    paths = AppPaths.resolve()
    with open_database(paths, now=lambda: NOW) as database:
        repo = SnapshotRepository(database.engine)
        snap = repo.load(repo.latest_id())  # type: ignore[arg-type]
        assert snap is not None
        snap_with_surge = snap.model_copy(
            update={
                "snapshot_id": uuid4(),
                "display_layers": (*snap.display_layers, *synthetic_surge_layers(NOW)),
            }
        )
        full_depth = build_map_depth_response(snap_with_surge)
        assert len(full_depth.peak_surge.features) == 3  # noqa: PLR2004
        for feat in full_depth.peak_surge.features:
            assert set(feat.properties) == {"name", "layer"}
        names = {str(f.properties["name"]) for f in full_depth.peak_surge.features}
        assert "Tampa Bay...8-12 ft" in names
        assert "Anclote River to Egmont Key...6-9 ft" in names

    assert set(REPLAY_MAP_LAYERS).isdisjoint(
        {"wind_radii", "past_track", "peak_surge", "radar", "satellite"}
    )
    assert set(STORED_ADVISORY_MAP_LAYERS).isdisjoint({"radar", "satellite"})
