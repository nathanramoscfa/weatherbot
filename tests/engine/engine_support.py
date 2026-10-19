# tests/engine/engine_support.py
"""Shared inputs for the engine tests: the landmarks, the replay corpus, and track points.

Coordinates come from the public landmarks in ``scripts/public_landmarks.toml`` and from
the replay corpus, read at run time through ``weatherbot.sources.nhc_gis_archive``, the
parser replay snapshots use, so the engine tests read replay data exactly as snapshots
do; synthetic shapes are built from the landmarks, the antimeridian, and whole-degree
offsets. This module holds no coordinate literal.
"""

import json
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Final, cast

from check_personal_data import load_landmarks
from weatherbot.models import (
    WGS84,
    Advisory,
    AdvisoryNumber,
    ConeGeometry,
    Crs,
    Geometry,
    LatLon,
    Provenance,
    TrackPoint,
    WatchWarningSegment,
)
from weatherbot.sources import nhc_gis_archive
from weatherbot.sources.nhc_gis_archive import CorpusEntry, CorpusManifest

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
REPLAY: Final = REPOSITORY_ROOT / "tests" / "fixtures" / "replay"
IRMA: Final = "AL112017"
DORIAN: Final = "AL052019"
SYNTHETIC_STORM: Final = "CP012026"


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


def synthetic_track(
    start: datetime,
    positions: Sequence[tuple[float, float]],
    *,
    step: timedelta = timedelta(hours=12),
    crs: Crs = WGS84,
) -> list[TrackPoint]:
    """Build a synthetic forecast track: one point per position, ``step`` apart from ``start``.

    Args:
        start: The first point's instant (UTC).
        positions: Each point's ``(longitude, latitude)``.
        step: The time between consecutive points.
        crs: The points' CRS.

    Returns:
        The points, in order.
    """
    advisory = Advisory(
        atcf_id=SYNTHETIC_STORM,
        number=AdvisoryNumber.parse("1"),
        issued_at=start,
        local_text=None,
        issued_at_source="roster",
    )
    provenance = Provenance(
        source_id="nhc-map-tropical-summary",
        url="https://example.invalid/synthetic-track",
        status=200,
        fetched_at=start,
        sha256="0" * 64,
    )
    return [
        TrackPoint(
            atcf_id=SYNTHETIC_STORM,
            advisory=advisory,
            provenance=provenance,
            tau_h=int(index * step.total_seconds() // 3600),
            valid_at=start + index * step,
            position=Geometry(type="Point", coordinates=position, crs=crs),
            max_wind_kt=None,
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
