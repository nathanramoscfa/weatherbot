# scripts/synthetic_surge.py
"""Synthetic peak storm surge display layers for tests and the offline demo server.

Because the recorded ``NHC_PeakStormSurge`` captures (2026-10-12 and 2026-11-03) had no
active U.S. coastal surge features, this module builds a labelled synthetic ``Polygons``
and ``Lines`` fixture in code at two decimal places, using placemark name conventions from
archived Hurricane Milton (``AL142024_PeakStormSurge_008adv.kml``, e.g.
``"Tampa Bay...8-12 ft"`` and ``"Charlotte Harbor...5-10 ft"``). Every coordinate is
rounded to two decimals to satisfy the personal-data rule.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

import httpx

from weatherbot.models import Crs, DisplayLayer, Provenance

if TYPE_CHECKING:
    from pydantic import JsonValue

PEAK_SURGE_LINES_URL: Final = (
    "https://mapservices.weather.noaa.gov/tropical/rest/services/tropical/"
    "NHC_PeakStormSurge/MapServer/1/query"
    "?where=1%3D1&outFields=*&outSR=4326&f=geojson&geometryPrecision=5"
)
PEAK_SURGE_POLYGONS_URL: Final = (
    "https://mapservices.weather.noaa.gov/tropical/rest/services/tropical/"
    "NHC_PeakStormSurge/MapServer/2/query"
    "?where=1%3D1&outFields=*&outSR=4326&f=geojson&geometryPrecision=5"
)

SYNTHETIC_SURGE_NOTE: Final = "synthetic fixture (two-decimal coordinates)"
_DEFAULT_FETCHED_AT: Final = datetime(2026, 10, 12, 21, 42, 0, tzinfo=UTC)


def synthetic_surge_polygons_collection() -> dict[str, JsonValue]:
    """Return a synthetic GeoJSON FeatureCollection for peak-surge ``Polygons``."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-82.75, 27.55],
                            [-82.45, 27.55],
                            [-82.45, 27.85],
                            [-82.75, 27.85],
                            [-82.75, 27.55],
                        ]
                    ],
                },
                "properties": {
                    "objectid": 1,
                    "name": "Tampa Bay...8-12 ft",
                    "snippet": SYNTHETIC_SURGE_NOTE,
                    "popupinfo": '{"peak_surge_range":"8-12 ft","synthetic":true}',
                },
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-82.30, 26.65],
                            [-82.05, 26.65],
                            [-82.05, 26.95],
                            [-82.30, 26.95],
                            [-82.30, 26.65],
                        ]
                    ],
                },
                "properties": {
                    "objectid": 2,
                    "name": "Charlotte Harbor...5-10 ft",
                    "snippet": SYNTHETIC_SURGE_NOTE,
                    "popupinfo": '{"peak_surge_range":"5-10 ft","synthetic":true}',
                },
            },
        ],
    }


def synthetic_surge_lines_collection() -> dict[str, JsonValue]:
    """Return a synthetic GeoJSON FeatureCollection for peak-surge ``Lines``."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [-82.85, 27.60],
                        [-82.80, 27.90],
                        [-82.75, 28.15],
                    ],
                },
                "properties": {
                    "objectid": 1,
                    "name": "Anclote River to Egmont Key...6-9 ft",
                    "snippet": SYNTHETIC_SURGE_NOTE,
                    "popupinfo": '{"peak_surge_range":"6-9 ft","synthetic":true}',
                },
            }
        ],
    }


def synthetic_surge_layers(
    fetched_at: datetime = _DEFAULT_FETCHED_AT,
) -> tuple[DisplayLayer, DisplayLayer]:
    """Build synthetic ``Polygons`` and ``Lines`` ``DisplayLayer`` domain models."""
    crs = Crs(name="EPSG:4326")
    polygons_body = json.dumps(synthetic_surge_polygons_collection()).encode("utf-8")
    lines_body = json.dumps(synthetic_surge_lines_collection()).encode("utf-8")
    polygons_prov = Provenance(
        source_id="nhc-map-peak-surge",
        url=PEAK_SURGE_POLYGONS_URL,
        status=200,
        fetched_at=fetched_at,
        sha256=hashlib.sha256(polygons_body).hexdigest(),
    )
    lines_prov = Provenance(
        source_id="nhc-map-peak-surge",
        url=PEAK_SURGE_LINES_URL,
        status=200,
        fetched_at=fetched_at,
        sha256=hashlib.sha256(lines_body).hexdigest(),
    )
    return (
        DisplayLayer(
            layer_name="Polygons",
            feature_collection=synthetic_surge_polygons_collection(),
            crs=crs,
            provenance=polygons_prov,
        ),
        DisplayLayer(
            layer_name="Lines",
            feature_collection=synthetic_surge_lines_collection(),
            crs=crs,
            provenance=lines_prov,
        ),
    )


def synthetic_surge_polygons_response() -> httpx.Response:
    """Build an ``httpx.Response`` serving the synthetic peak-surge ``Polygons``."""
    return httpx.Response(
        200,
        content=json.dumps(synthetic_surge_polygons_collection()).encode("utf-8"),
        headers={"content-type": "application/geo+json"},
    )


def synthetic_surge_lines_response() -> httpx.Response:
    """Build an ``httpx.Response`` serving the synthetic peak-surge ``Lines``."""
    return httpx.Response(
        200,
        content=json.dumps(synthetic_surge_lines_collection()).encode("utf-8"),
        headers={"content-type": "application/geo+json"},
    )
