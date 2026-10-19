# tests/engine/engine_support.py
"""Shared inputs for the engine tests: the landmarks, the replay corpus, and track points.

Coordinates come from the public landmarks in ``scripts/public_landmarks.toml`` and from
the replay corpus, read at run time; synthetic shapes are built from the landmarks, the
antimeridian, and whole-degree offsets. This module holds no coordinate literal.
"""

import gzip
import json
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final, cast

from check_personal_data import load_landmarks
from weatherbot.models import (
    WGS84,
    Advisory,
    AdvisoryNumber,
    Crs,
    Geometry,
    LatLon,
    Provenance,
    TrackPoint,
    parse_nhc_local_time,
)
from weatherbot.models.times import resolve_track_valid_time

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
REPLAY: Final = REPOSITORY_ROOT / "tests" / "fixtures" / "replay"
MANIFEST: Final = REPLAY / "corpus-manifest.json"
IRMA: Final = "AL112017"
DORIAN: Final = "AL052019"
MISSING: Final = 9999
SYNTHETIC_STORM: Final = "CP012026"

type Feature = tuple[dict[str, object], Geometry]


def landmark(key: str) -> LatLon:
    """Return a public landmark (``miami-dade`` or ``nassau``) as a WGS 84 point."""
    found = next(item for item in load_landmarks() if item.key == key)
    return LatLon(latitude=float(found.lat), longitude=float(found.lon))


def manifest() -> dict[str, object]:
    """Return the replay corpus manifest."""
    return cast("dict[str, object]", json.loads(MANIFEST.read_text(encoding="utf-8")))


def corpus_wkts() -> set[str]:
    """Return every distinct projection WKT the manifest records for the originals."""
    files = cast("list[dict[str, object]]", manifest()["files"])
    return {
        cast("str", projection["wkt"])
        for entry in files
        for projection in cast("dict[str, dict[str, object]]", entry.get("prj", {})).values()
    }


def advisories(storm: str) -> list[str]:
    """Return a storm's advisory directories in advisory order (``22 < 22A < 23``)."""
    return sorted(
        (path.name for path in (REPLAY / storm).iterdir() if path.is_dir()),
        key=AdvisoryNumber.parse,
    )


def collection(storm: str, advisory: str, product: str) -> dict[str, object] | None:
    """Return one replay FeatureCollection, or ``None`` when the advisory lacks it."""
    path = REPLAY / storm / advisory / f"{product}.geojson.gz"
    if not path.is_file():
        return None
    return cast("dict[str, object]", json.loads(gzip.decompress(path.read_bytes())))


def native_crs(document: dict[str, object]) -> Crs:
    """Return a collection's native CRS, read from its ``source_crs`` as the models read it."""
    return Crs.native(cast("dict[str, object]", document["source_crs"]))


def features(storm: str, advisory: str, product: str) -> list[Feature]:
    """Return each feature's properties and geometry, in the collection's native CRS."""
    document = collection(storm, advisory, product)
    if document is None:
        return []
    crs = native_crs(document)
    return [
        (
            cast("dict[str, object]", feature["properties"]),
            Geometry.from_geojson(cast("dict[str, object]", feature["geometry"]), crs),
        )
        for feature in cast("list[dict[str, object]]", document["features"])
    ]


def _value(properties: dict[str, object], key: str) -> int | None:
    value = cast("int", properties[key])
    return None if value == MISSING else value


def _source(storm: str, advisory: str) -> dict[str, object]:
    subset = cast("list[dict[str, object]]", manifest()["subset"])
    files = cast("list[dict[str, object]]", manifest()["files"])
    entry = next(item for item in subset if item["file"] == f"{storm}/{advisory}/points.geojson.gz")
    return next(item for item in files if item["file"] == entry["source"])


def replay_track(storm: str, advisory: str) -> list[TrackPoint]:
    """Build an advisory's forecast points from its replay collection, as the models hold them.

    The provenance cites the original archive the collection was converted from.
    """
    source = _source(storm, advisory)
    points: list[TrackPoint] = []
    for properties, position in features(storm, advisory, "points"):
        text = cast("str", properties["ADVDATE"])
        issued_at = parse_nhc_local_time(text)
        assert issued_at is not None
        number = AdvisoryNumber.parse(cast("str", properties["ADVISNUM"]))
        points.append(
            TrackPoint(
                atcf_id=storm,
                advisory=Advisory(
                    atcf_id=storm, number=number, issued_at=issued_at, local_text=text
                ),
                provenance=Provenance(
                    source_id="nhc-gis-archive",
                    url=cast("str", source["url"]),
                    status=200,
                    fetched_at=issued_at,
                    sha256=cast("str", source["sha256"]),
                    advisory=number,
                ),
                tau_h=cast("int", properties["TAU"]),
                valid_at=resolve_track_valid_time(cast("str", properties["VALIDTIME"]), issued_at),
                valid_local_text=cast("str", properties["FLDATELBL"]),
                position=position,
                max_wind_kt=_value(properties, "MAXWIND"),
                gust_kt=_value(properties, "GUST"),
                mslp_mb=_value(properties, "MSLP"),
                direction_deg=_value(properties, "TCDIR"),
                speed_kt=_value(properties, "TCSPD"),
                development=cast("str", properties["TCDVLP"]),
                storm_type=cast("str", properties["STORMTYPE"]),
                saffir_simpson=cast("int", properties["SSNUM"]),
                label=cast("str", properties["DVLBL"]),
            )
        )
    return points


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
