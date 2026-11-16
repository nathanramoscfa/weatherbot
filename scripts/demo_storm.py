# scripts/demo_storm.py
"""A synthetic Atlantic hurricane in the live feeds' own formats, for the demonstration scenarios.

The recordings hold one storm, Eastern Pacific Hurricane Simon, so the default
demonstration never puts an Atlantic storm on screen, and the replay corpus cannot fill
the gap: a replay snapshot is never assessed into history, and the archive's sphere is
never relabelled as WGS 84. This module builds, for one stage of one synthetic storm,
every answer a live cycle requests for it: the roster entry with its product links; the
tropical weather summary service's storm layers (the forecast cone, the track, the
forecast points with their intensity, the watch-warning segments with their ``tcww``
codes, the forecast wind radii and the advisory wind field, and both arrival-time
layers), its past points, track, and wind swath; the 34-, 50-, and 64-kt wind-speed
probability bands; the two 34-kt arrival-time KMZs at the URLs the roster names; and the
slot's TCP list and product.

The storm is Hurricane Demo, ``AL802026`` in slot ``AT1``. ATCF reserves storm numbers 80
to 89 for test storms, so no real storm carries the id, and the name says it is a
demonstration. Its track runs west-northwest from north of Hispaniola, about 71 km south
of the Nassau landmark (``"Parliament Square"``), to landfall at the Miami-Dade landmark,
so one storm explains every scenario's map. Every answer starts from its recorded
template's field shapes (``tests/fixtures/recorded/``), so the parsers' declared field
lists are satisfied; every coordinate is written at two decimals, because the
personal-data rule refuses three; and every answer says it is synthetic in its own
fields: a ``snippet`` note and ``"synthetic": true`` on each feature, roster entry, and
list item, the KML's ``storm`` and ``synthetic`` data, and the TCP's text. The fetcher
still stamps each record with the register's source id, as it does for
``scripts/synthetic_surge.py``'s surge.

``stage_answers(stage, issued_at)`` builds one stage's answers, keyed by the URL a cycle
requests: ``cone`` (advisory 3, a tropical storm forecast to become a hurricane only after
it passes Nassau), ``watch`` (advisory 6, with hurricane and tropical storm watches), and
``landfall`` (advisory 8, a major hurricane forecast to reach the Miami-Dade landmark in
24 hours, with warnings). A stage's geometry is fixed; its times follow ``issued_at``, so a
scenario can show any stage as the current advisory, while the landfall scenario's
history shows the stages one after another at the times ``HISTORY_ISSUED_AT`` names.
"""

from __future__ import annotations

import io
import itertools
import json
import math
import sys
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, cast

import httpx

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
for _extra in (
    REPO_ROOT / "src",
    REPO_ROOT / "tests" / "contract",
    REPO_ROOT / "tests" / "sources",
):
    _text = str(_extra)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from fixture_support import as_object, latest_live  # noqa: E402
from source_support import entry, layer_name  # noqa: E402

type Point = tuple[float, float]
"""``(longitude, latitude)`` in degrees, WGS 84."""
type StageName = Literal["cone", "watch", "landfall"]
type ArrivalKind = Literal["earliest_reasonable", "most_likely"]

ATCF_ID: Final = "AL802026"
SLOT: Final = "AT1"
NAME: Final = "Demo"
STORM_NUMBER: Final = 80
SYNTHETIC_NOTE: Final = "synthetic demonstration storm, not a real storm (two-decimal coordinates)"
"""The note every synthetic feature carries in its own ``snippet`` field."""
STAGE_NAMES: Final[tuple[StageName, ...]] = ("cone", "watch", "landfall")
ARRIVAL_KINDS: Final[tuple[ArrivalKind, ...]] = ("earliest_reasonable", "most_likely")

EDT: Final = timezone(timedelta(hours=-4), "EDT")
FORMATION: Final = datetime(2026, 10, 11, 0, tzinfo=UTC)
"""The synoptic time of advisory 1, when the storm is at ``TRACK_START``."""
LANDFALL: Final = datetime(2026, 10, 13, 18, tzinfo=UTC)
"""When the center reaches ``TRACK_END``, the Miami-Dade landmark's coast."""
TRACK_START: Final[Point] = (-71.50, 21.43)
TRACK_END: Final[Point] = (-80.20, 25.78)
HISTORY_ISSUED_AT: Final[Mapping[StageName, datetime]] = {
    "cone": datetime(2026, 10, 11, 15, tzinfo=UTC),
    "watch": datetime(2026, 10, 12, 9, tzinfo=UTC),
    "landfall": datetime(2026, 10, 12, 21, tzinfo=UTC),
}
"""When the landfall history issues each stage's advisory (11 AM, 5 AM, and 5 PM EDT)."""
SYNOPTIC_LEAD: Final = timedelta(hours=3)
"""An advisory is issued three hours after its synoptic time."""
TAUS: Final = (0, 12, 24, 36, 48, 60, 72, 96, 120)
RADII_TAUS: Final = (12, 24, 36, 48, 72)
CONE_RADII_NMI: Final[Mapping[int, float]] = {
    0: 8,
    12: 26,
    24: 39,
    36: 53,
    48: 67,
    60: 84,
    72: 97,
    96: 128,
    120: 182,
}
"""The cone's radius at each forecast hour, close to NHC's Atlantic cone."""
INTENSITY_HISTORY: Final = ((-12, 25), (-6, 30), (0, 35), (12, 45), (24, 55), (30, 60), (42, 90))
"""The best track's maximum wind (kt) by hours from ``FORMATION``."""
ARRIVAL_LEAD_H: Final[Mapping[ArrivalKind, int]] = {"earliest_reasonable": 18, "most_likely": 12}
"""How many hours ahead of the center an isochrone sits: the winds' leading edge."""
KM_PER_DEGREE: Final = 111.32
KM_PER_NMI: Final = 1.852
_DECIMALS: Final = 2
_CAP_STEP_DEG: Final = 15
_EPOCH: Final = datetime(1970, 1, 1, tzinfo=UTC)
_HURRICANE_KT: Final = 64
_MAJOR_KT: Final = 96
_STORM_KT: Final = 34
_DEPRESSION_H: Final = -6
"""The best track's first depression, six hours before ``FORMATION``."""
_SAFFIR_SIMPSON: Final = ((137, 5), (113, 4), (96, 3), (83, 2), (64, 1))

GEOJSON: Final = "application/geo+json;charset=UTF-8"
ARCGIS_JSON: Final = "application/json;charset=UTF-8"
KMZ_TYPE: Final = "application/vnd.google-earth.kmz"
LD_JSON: Final = "application/ld+json"
ROSTER_URL: Final = "https://www.nhc.noaa.gov/CurrentStorms.json"
KMZ_URL: Final = "https://www.nhc.noaa.gov/storm_graphics/api/{atcf}_{adv:03d}adv_{kind}_toa_34.kmz"
API_ROOT: Final = "https://api.weather.gov"

# The layers this module writes, by the name the summary service gives them.
FORECAST_POINTS: Final = "Forecast Points"
FORECAST_TRACK: Final = "Forecast Track"
FORECAST_CONE: Final = "Forecast Cone"
WATCH_WARNING: Final = "Watch-Warning"
FORECAST_WIND_RADII: Final = "Forecast Wind Radii"
ADVISORY_WIND_FIELD: Final = "Advisory Wind Field"
EARLIEST_ARRIVAL: Final = "Earliest Reasonable Arrival Time"
MOST_LIKELY_ARRIVAL: Final = "Most Likely Arrival Time"
PAST_POINTS: Final = "Past Points"
PAST_TRACK: Final = "Past Track"
PAST_SWATH: Final = "Past Cumulative Wind Swath"
WIND_LAYERS: Final[Mapping[int, str]] = {
    34: "Probabilistic Winds 34 kts",
    50: "Probabilistic Winds 50 kts",
    64: "Probabilistic Winds 64 kts",
}
STORM_LAYERS: Final = (
    FORECAST_CONE,
    FORECAST_POINTS,
    FORECAST_TRACK,
    WATCH_WARNING,
    FORECAST_WIND_RADII,
    ADVISORY_WIND_FIELD,
    EARLIEST_ARRIVAL,
    MOST_LIKELY_ARRIVAL,
    PAST_POINTS,
    PAST_TRACK,
    PAST_SWATH,
)
"""Every per-storm summary layer a cycle queries (products, then display layers)."""

# The coasts the watches and warnings follow; each end sits on a breakpoint of the
# recorded catalogue, which names it (Palm Beach/Martin County Line, Card Sound Bridge,
# Ocean Reef, Seven Mile Bridge, Bahamas (NW), and Bahamas (Andros Island)).
FLORIDA_EAST: Final[tuple[Point, ...]] = (
    (-80.08, 26.97),
    (-80.05, 26.60),
    (-80.08, 26.32),
    (-80.12, 25.98),
    (-80.13, 25.77),
    (-80.16, 25.66),
    (-80.25, 25.45),
    (-80.37, 25.29),
)
FLORIDA_KEYS: Final[tuple[Point, ...]] = (
    (-80.26, 25.33),
    (-80.45, 25.10),
    (-80.77, 24.84),
    (-81.15, 24.70),
)
BAHAMAS_NW: Final[tuple[Point, ...]] = (
    (-77.56, 25.02),
    (-77.47, 25.08),
    (-77.34, 25.09),
    (-77.20, 25.05),
    (-77.10, 25.00),
)
ANDROS: Final[tuple[Point, ...]] = ((-78.00, 24.70), (-77.80, 24.40), (-77.70, 24.10))

type Band = tuple[str, float, int]
"""A wind-speed probability band: its label, its radius (nmi), and its last forecast hour."""


@dataclass(frozen=True)
class StormStage:
    """One advisory of the storm: its number, forecast, watches and warnings, and bands."""

    name: StageName
    advisory: int
    forecast_kt: Mapping[int, int]
    segments: tuple[tuple[str, tuple[Point, ...]], ...]
    bands: Mapping[int, tuple[Band, ...]]
    headline: str
    watches: str
    discussion: str


STAGES: Final[Mapping[StageName, StormStage]] = {
    "cone": StormStage(
        name="cone",
        advisory=3,
        forecast_kt={0: 45, 12: 50, 24: 55, 36: 60, 48: 70, 60: 75, 72: 70, 96: 80, 120: 75},
        segments=(),
        bands={
            34: (
                ("<5%", 260, 120),
                ("5-10%", 210, 120),
                ("10-20%", 170, 108),
                ("20-30%", 135, 96),
                ("30-40%", 105, 84),
                ("40-50%", 80, 72),
                ("50-60%", 60, 60),
                ("60-70%", 25, 48),
            ),
            50: (
                ("<5%", 200, 120),
                ("5-10%", 150, 108),
                ("10-20%", 110, 96),
                ("20-30%", 75, 84),
                ("30-40%", 50, 72),
                ("40-50%", 20, 60),
            ),
            64: (
                ("<5%", 150, 120),
                ("5-10%", 60, 108),
                ("10-20%", 28, 96),
                ("20-30%", 15, 72),
            ),
        },
        headline="DEMO FORECAST TO STRENGTHEN AS IT PASSES SOUTH OF THE NORTHWESTERN BAHAMAS",
        watches="There are no coastal watches or warnings in effect.",
        discussion=(
            "Demo is forecast to remain a tropical storm as it passes south of New\n"
            "Providence and to become a hurricane before it reaches southeastern Florida."
        ),
    ),
    "watch": StormStage(
        name="watch",
        advisory=6,
        forecast_kt={0: 60, 12: 75, 24: 90, 36: 100, 48: 70, 60: 65, 72: 75, 96: 70, 120: 45},
        segments=(
            ("HWA", FLORIDA_EAST),
            ("TWA", FLORIDA_KEYS),
            ("TWA", BAHAMAS_NW),
            ("HWA", ANDROS),
        ),
        bands={
            34: (
                ("<5%", 260, 120),
                ("5-10%", 210, 120),
                ("10-20%", 170, 108),
                ("20-30%", 140, 96),
                ("30-40%", 115, 84),
                ("40-50%", 95, 72),
                ("50-60%", 80, 60),
                ("60-70%", 65, 48),
                ("70-80%", 52, 42),
                ("80-90%", 20, 36),
            ),
            50: (
                ("<5%", 200, 120),
                ("5-10%", 160, 108),
                ("10-20%", 120, 96),
                ("20-30%", 95, 84),
                ("30-40%", 75, 72),
                ("40-50%", 58, 60),
                ("50-60%", 20, 40),
            ),
            64: (
                ("<5%", 150, 120),
                ("5-10%", 100, 108),
                ("10-20%", 60, 96),
                ("20-30%", 25, 72),
                ("30-40%", 12, 48),
            ),
        },
        headline="HURRICANE WATCH ISSUED FOR SOUTHEASTERN FLORIDA",
        watches=(
            "A Hurricane Watch is in effect for...\n"
            "* Palm Beach/Martin County Line to Card Sound Bridge\n"
            "* Andros Island\n"
            " \n"
            "A Tropical Storm Watch is in effect for...\n"
            "* Ocean Reef to Seven Mile Bridge\n"
            "* New Providence and the northwestern Bahamas"
        ),
        discussion=(
            "Demo is forecast to become a hurricane later today and to reach\n"
            "southeastern Florida as a major hurricane in about 36 hours."
        ),
    ),
    "landfall": StormStage(
        name="landfall",
        advisory=8,
        forecast_kt={0: 90, 12: 105, 24: 115, 36: 80, 48: 75, 60: 70, 72: 80, 96: 60, 120: 35},
        segments=(
            ("HWR", FLORIDA_EAST),
            ("TWR", FLORIDA_KEYS),
            ("TWR", BAHAMAS_NW),
            ("HWR", ANDROS),
        ),
        bands={
            34: (
                ("<5%", 280, 120),
                ("5-10%", 230, 120),
                ("10-20%", 190, 108),
                ("20-30%", 160, 96),
                ("30-40%", 135, 84),
                ("40-50%", 115, 72),
                ("50-60%", 100, 60),
                ("60-70%", 85, 48),
                ("70-80%", 72, 36),
                ("80-90%", 62, 30),
                (">90%", 55, 24),
            ),
            50: (
                ("<5%", 210, 120),
                ("5-10%", 170, 108),
                ("10-20%", 130, 96),
                ("20-30%", 105, 84),
                ("30-40%", 85, 72),
                ("40-50%", 70, 60),
                ("50-60%", 58, 48),
                ("60-70%", 48, 36),
                ("70-80%", 20, 28),
            ),
            64: (
                ("<5%", 160, 120),
                ("5-10%", 110, 108),
                ("10-20%", 80, 96),
                ("20-30%", 55, 72),
                ("30-40%", 28, 48),
                ("40-50%", 20, 36),
                ("50-60%", 12, 30),
            ),
        },
        headline="DEMO STRENGTHENING AS IT NEARS SOUTHEASTERN FLORIDA",
        watches=(
            "A Hurricane Warning is in effect for...\n"
            "* Palm Beach/Martin County Line to Card Sound Bridge\n"
            "* Andros Island\n"
            " \n"
            "A Tropical Storm Warning is in effect for...\n"
            "* Ocean Reef to Seven Mile Bridge\n"
            "* New Providence and the northwestern Bahamas"
        ),
        discussion=(
            "Demo is forecast to become a major hurricane tonight and to make\n"
            "landfall in southeastern Florida in about 24 hours."
        ),
    ),
}


@dataclass(frozen=True)
class StagedAnswer:
    """One answer a staged URL serves: its status, its bytes, and its content type."""

    status: int
    body: bytes
    content_type: str

    def response(self) -> httpx.Response:
        """Build a fresh response for one request.

        Returns:
            The answer as ``httpx`` serves it.
        """
        return httpx.Response(
            self.status, content=self.body, headers={"content-type": self.content_type}
        )

    @classmethod
    def json(cls, document: object, content_type: str = GEOJSON) -> StagedAnswer:
        """A JSON answer.

        Args:
            document: The parsed document.
            content_type: Its content type.

        Returns:
            The answer, ``200``.
        """
        return cls(200, json.dumps(document).encode("utf-8"), content_type)


class DemoStormError(RuntimeError):
    """A recorded template no longer has the shape the synthetic storm copies."""


# Templates ------------------------------------------------------------------------------


def _capture(source: str, name: str) -> tuple[dict[str, object], bytes]:
    directory = latest_live(source)
    if directory is None:
        message = f"{source} has no live capture to copy"
        raise DemoStormError(message)
    item = entry(directory, name)
    return item, directory.payload(item)


def summary_layer_urls() -> dict[str, str]:
    """The URL a cycle queries for each summary-service layer, from the recorded capture.

    Returns:
        The query URL by layer name.

    Raises:
        DemoStormError: The capture is missing.
    """
    directory = latest_live("nhc-map-tropical-summary")
    if directory is None:
        message = "nhc-map-tropical-summary has no live capture"
        raise DemoStormError(message)
    found: dict[str, str] = {}
    for item in directory.entries:
        name = layer_name(item)
        if name is not None and str(item["file"]).startswith("query-"):
            found[name] = str(item["url"])
    return found


def template_properties(layer: str) -> dict[str, object]:
    """The first feature's properties of a recorded summary layer, as a template."""
    directory = latest_live("nhc-map-tropical-summary")
    if directory is None:
        message = "nhc-map-tropical-summary has no live capture"
        raise DemoStormError(message)
    for item in directory.entries:
        if layer_name(item) == layer:
            features = cast("list[object]", json.loads(directory.payload(item))["features"])
            if features:
                feature = as_object(features[0])
                properties = dict(as_object(feature["properties"]))
                # The shape statistics describe the recorded geometry, not this one.
                return {
                    key: value for key, value in properties.items() if not key.startswith("st_")
                }
    message = f"the recorded {layer!r} layer holds no feature to copy"
    raise DemoStormError(message)


def _template_storm() -> dict[str, object]:
    _item, body = _capture("nhc-current-storms", "CurrentStorms.json")
    storms = cast("list[object]", json.loads(body)["activeStorms"])
    return dict(as_object(storms[0]))


# Geometry --------------------------------------------------------------------------------


def _hours(delta: timedelta) -> float:
    return delta.total_seconds() / 3600.0


def position(at: datetime) -> Point:
    """Where the center is at an instant of the landfall history (extrapolated past its ends).

    Args:
        at: The instant, on the history's timeline.

    Returns:
        The center, unrounded.
    """
    fraction = _hours(at - FORMATION) / _hours(LANDFALL - FORMATION)
    return (
        TRACK_START[0] + (TRACK_END[0] - TRACK_START[0]) * fraction,
        TRACK_START[1] + (TRACK_END[1] - TRACK_START[1]) * fraction,
    )


def _heading() -> float:
    middle = math.radians((TRACK_START[1] + TRACK_END[1]) / 2)
    east = (TRACK_END[0] - TRACK_START[0]) * math.cos(middle)
    north = TRACK_END[1] - TRACK_START[1]
    return math.degrees(math.atan2(east, north)) % 360


HEADING_DEG: Final = _heading()
SPEED_KMH: Final = math.hypot(
    (TRACK_END[0] - TRACK_START[0])
    * KM_PER_DEGREE
    * math.cos(math.radians((TRACK_START[1] + TRACK_END[1]) / 2)),
    (TRACK_END[1] - TRACK_START[1]) * KM_PER_DEGREE,
) / _hours(LANDFALL - FORMATION)


def _offset(point: Point, bearing_deg: float, km: float) -> Point:
    """Move a point ``km`` along a bearing, on the local plane."""
    angle = math.radians(bearing_deg)
    east, north = km * math.sin(angle), km * math.cos(angle)
    lon = point[0] + east / (KM_PER_DEGREE * math.cos(math.radians(point[1])))
    return (lon, point[1] + north / KM_PER_DEGREE)


def _rounded(point: Point) -> Point:
    return (round(point[0], _DECIMALS), round(point[1], _DECIMALS))


def _signed_area(ring: Sequence[Point]) -> float:
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in itertools.pairwise(ring)) / 2


def _ring(points: Sequence[Point], *, counterclockwise: bool = True) -> list[list[float]]:
    """Round a ring to two decimals, drop repeated points, close it, and orient it."""
    ring: list[Point] = []
    for point in points:
        rounded = _rounded(point)
        if not ring or ring[-1] != rounded:
            ring.append(rounded)
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    if (_signed_area(ring) > 0) != counterclockwise:
        ring.reverse()
    return [[lon, lat] for lon, lat in ring]


def _line(points: Sequence[Point]) -> list[list[float]]:
    return [[lon, lat] for lon, lat in (_rounded(point) for point in points)]


def _corridor(centres: Sequence[tuple[Point, float]]) -> list[Point]:
    """The outline of a funnel along the track: offsets on each side and round end caps.

    Args:
        centres: Points along the track, in order, with the radius (km) at each.

    Returns:
        The outline, unclosed and unrounded.
    """
    left = [_offset(point, HEADING_DEG - 90, radius) for point, radius in centres]
    right = [_offset(point, HEADING_DEG + 90, radius) for point, radius in centres]
    end, end_radius = centres[-1]
    start, start_radius = centres[0]
    steps = range(_CAP_STEP_DEG, 180, _CAP_STEP_DEG)
    front = [_offset(end, HEADING_DEG - 90 + step, end_radius) for step in steps]
    back = [_offset(start, HEADING_DEG + 90 + step, start_radius) for step in steps]
    return [*left, *front, *reversed(right), *back]


def _compass(bearing_deg: float) -> str:
    points = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE")
    points += ("S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")
    return points[round(bearing_deg / 22.5) % 16]


def _distance_km(a: Point, b: Point) -> float:
    lat1, lat2 = math.radians(a[1]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, math.radians(b[0] - a[0])
    half = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(half))


def _bearing_deg(a: Point, b: Point) -> float:
    lat1, lat2 = math.radians(a[1]), math.radians(b[1])
    dlon = math.radians(b[0] - a[0])
    east = math.sin(dlon) * math.cos(lat2)
    north = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return math.degrees(math.atan2(east, north)) % 360


# Times and words -------------------------------------------------------------------------


def _local_text(at: datetime) -> str:
    """NHC's local issuance text: ``500 PM EDT Mon Oct 12 2026``."""
    local = at.astimezone(EDT)
    hour = local.hour % 12 or 12
    meridiem = "AM" if local.hour < 12 else "PM"  # noqa: PLR2004 - noon
    return f"{hour}{local:%M} {meridiem} EDT {local:%a %b %d %Y}"


def _clock_text(local: datetime) -> str:
    """A local clock reading such as ``5:00 PM``."""
    meridiem = "AM" if local.hour < 12 else "PM"  # noqa: PLR2004 - noon
    return f"{local.hour % 12 or 12}:{local:%M} {meridiem}"


def _label(at: datetime) -> str:
    """An arrival-time label: ``Mon 8 pm``."""
    local = at.astimezone(EDT)
    hour = local.hour % 12 or 12
    meridiem = "am" if local.hour < 12 else "pm"  # noqa: PLR2004 - noon
    return f"{local:%a} {hour} {meridiem}"


def _epoch_ms(at: datetime) -> int:
    return int((at - _EPOCH).total_seconds() * 1000)


def _stamp(at: datetime) -> str:
    return f"{at:%Y%m%d%H}"


def _instant(at: datetime) -> str:
    return at.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def intensity_at(hours: float) -> int:
    """The best track's maximum wind (kt), hours after ``FORMATION``.

    Args:
        hours: Hours from ``FORMATION``.

    Returns:
        The wind, linear between the best track's points and held past its ends.
    """
    points = INTENSITY_HISTORY
    if hours <= points[0][0]:
        return points[0][1]
    for (h0, w0), (h1, w1) in itertools.pairwise(points):
        if hours <= h1:
            return round(w0 + (w1 - w0) * (hours - h0) / (h1 - h0))
    return points[-1][1]


def _category(wind_kt: int) -> int:
    return next((number for floor, number in _SAFFIR_SIMPSON if wind_kt >= floor), 0)


def _kind(wind_kt: int) -> tuple[str, str, str]:
    """``(stormtype, dvlbl, tcdvlp)`` for a maximum wind."""
    if wind_kt >= _MAJOR_KT:
        return "HU", "M", "Major Hurricane"
    if wind_kt >= _HURRICANE_KT:
        return "HU", "H", "Hurricane"
    if wind_kt >= _STORM_KT:
        return "TS", "S", "Tropical Storm"
    return "TD", "D", "Tropical Depression"


def _title(wind_kt: int) -> str:
    return "Hurricane" if wind_kt >= _HURRICANE_KT else "Tropical Storm"


def _pressure_mb(wind_kt: int) -> int:
    return round(1013 - (wind_kt - 25) * 0.6 - max(0, wind_kt - _HURRICANE_KT) * 0.25)


def _gust_kt(wind_kt: int) -> int:
    return round(wind_kt * 1.2 / 5) * 5


def _mph(wind_kt: int) -> int:
    return round(wind_kt * 1.15078 / 5) * 5


# The stage ------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Clock:
    """A stage's times: its history synoptic time, and the shift to the shown issuance."""

    stage: StormStage
    issued_at: datetime

    @property
    def shift(self) -> timedelta:
        return self.issued_at - HISTORY_ISSUED_AT[self.stage.name]

    @property
    def synoptic(self) -> datetime:
        """The synoptic time as shown."""
        return self.issued_at - SYNOPTIC_LEAD

    @property
    def history_synoptic(self) -> datetime:
        return HISTORY_ISSUED_AT[self.stage.name] - SYNOPTIC_LEAD

    def centre(self, tau: float) -> Point:
        """The forecast center ``tau`` hours after the synoptic time."""
        return position(self.history_synoptic + timedelta(hours=tau))

    def shown(self, history: datetime) -> datetime:
        return history + self.shift


def _feature(
    geometry: Mapping[str, object] | None, properties: dict[str, object]
) -> dict[str, object]:
    labelled = {**properties, "snippet": SYNTHETIC_NOTE, "synthetic": True}
    return {"type": "Feature", "geometry": geometry, "properties": labelled}


def _collection(features: Sequence[dict[str, object]]) -> dict[str, object]:
    return {"type": "FeatureCollection", "features": list(features)}


def _common(clock: _Clock) -> dict[str, object]:
    """The advisory fields every storm layer of the summary service repeats."""
    stage = clock.stage
    return {
        "basin": "AL",
        "advdate": _local_text(clock.issued_at),
        "advisnum": str(stage.advisory),
        "fcstprd": 120,
        "stormnum": STORM_NUMBER,
        "idp_filedate": _epoch_ms(clock.issued_at),
        "idp_ingestdate": _epoch_ms(clock.issued_at + timedelta(seconds=30)),
        "binnumber": SLOT,
    }


def _forecast_points(clock: _Clock) -> dict[str, object]:
    template = template_properties(FORECAST_POINTS)
    stage = clock.stage
    features: list[dict[str, object]] = []
    for tau in TAUS:
        wind = stage.forecast_kt[tau]
        storm_type, label, development = _kind(wind)
        centre = _rounded(clock.centre(tau))
        valid = clock.synoptic + timedelta(hours=tau)
        local = valid.astimezone(EDT)
        properties = {
            **template,
            **_common(clock),
            "objectid": tau + 1,
            "stormname": f"{_title(wind)} {NAME}",
            "stormtype": storm_type,
            "dvlbl": label,
            "gust": _gust_kt(wind),
            "maxwind": wind,
            "mslp": _pressure_mb(wind),
            "ssnum": _category(wind),
            "datelbl": f"{_clock_text(local)} {local:%a}",
            "tcdvlp": development,
            "tcdir": round(HEADING_DEG),
            "tcspd": round(SPEED_KMH / KM_PER_NMI),
            "fldatelbl": f"{local:%Y-%m-%d} {_clock_text(local)} {local:%a} EDT",
            "lat": centre[1],
            "lon": centre[0],
            "stormsrc": "Tropical Cyclone",
            "timezone": "EDT",
            "validtime": f"{valid:%d/%H%M}",
            "tau": tau,
            "idp_source": f"{ATCF_ID.lower()}-{stage.advisory:03d}_5day_pts",
            "idp_subset": ATCF_ID.lower(),
        }
        features.append(_feature({"type": "Point", "coordinates": list(centre)}, properties))
    return _collection(features)


def _forecast_track(clock: _Clock) -> dict[str, object]:
    template = template_properties(FORECAST_TRACK)
    wind = clock.stage.forecast_kt[0]
    properties = {
        **template,
        **_common(clock),
        "objectid": 1,
        "stormname": NAME,
        "stormtype": _kind(wind)[0],
        "idp_source": f"{ATCF_ID.lower()}-{clock.stage.advisory:03d}_5day_lin",
    }
    line = _line([clock.centre(tau) for tau in TAUS])
    return _collection([_feature({"type": "LineString", "coordinates": line}, properties)])


def _forecast_cone(clock: _Clock) -> dict[str, object]:
    template = template_properties(FORECAST_CONE)
    wind = clock.stage.forecast_kt[0]
    properties = {
        **template,
        **_common(clock),
        "objectid": 1,
        "stormname": NAME,
        "stormtype": _kind(wind)[0],
        "idp_source": f"{ATCF_ID.lower()}-{clock.stage.advisory:03d}_5day_pgn",
    }
    outline = _corridor([(clock.centre(tau), CONE_RADII_NMI[tau] * KM_PER_NMI) for tau in TAUS])
    geometry = {"type": "Polygon", "coordinates": [_ring(outline)]}
    return _collection([_feature(geometry, properties)])


def _watch_warnings(clock: _Clock) -> dict[str, object]:
    template = template_properties(WATCH_WARNING)
    wind = clock.stage.forecast_kt[0]
    features = [
        _feature(
            {"type": "LineString", "coordinates": _line(coast)},
            {
                **template,
                **_common(clock),
                "objectid": index + 1,
                "stormname": NAME,
                "stormtype": _kind(wind)[0],
                "tcww": code,
                "idp_source": f"{ATCF_ID.lower()}-{clock.stage.advisory:03d}_ww_wwlin",
            },
        )
        for index, (code, coast) in enumerate(clock.stage.segments)
    ]
    return _collection(features)


def _quadrants(wind_kt: int, threshold: int) -> tuple[int, int, int, int] | None:
    """The radii (nmi) of a threshold's winds in the NE, SE, SW, and NW quadrants."""
    if wind_kt < threshold:
        return None
    base = {34: (wind_kt - 28) * 2.0, 50: (wind_kt - 45) * 1.3, 64: (wind_kt - 58) * 0.9}
    factors = (1.0, 0.8, 0.55, 0.75)
    radii = tuple(max(5, round(base[threshold] * factor / 5) * 5) for factor in factors)
    return cast("tuple[int, int, int, int]", radii)


def _radii_ring(centre: Point, radii: Sequence[int]) -> list[list[float]]:
    points = [
        _offset(centre, angle, radius * KM_PER_NMI)
        for quadrant, radius in enumerate(radii)
        for angle in range(quadrant * 90, quadrant * 90 + 91, _CAP_STEP_DEG)
    ]
    return _ring(points)


def _wind_radii(clock: _Clock, *, field: bool) -> dict[str, object]:
    template = template_properties(ADVISORY_WIND_FIELD if field else FORECAST_WIND_RADII)
    stage = clock.stage
    taus = (0,) if field else RADII_TAUS
    kind = "initialradii" if field else "forecastradii"
    features: list[dict[str, object]] = []
    for tau in taus:
        wind = stage.forecast_kt[tau]
        for threshold in (34, 50, 64):
            radii = _quadrants(wind, threshold)
            if radii is None:
                continue
            properties = {
                **template,
                "objectid": len(features) + 1,
                "radii": threshold,
                "stormid": ATCF_ID.lower(),
                "basin": "al",
                "stormnum": STORM_NUMBER,
                "advnum": str(stage.advisory),
                "validtime": _stamp(clock.synoptic + timedelta(hours=tau)),
                "synoptime": _stamp(clock.synoptic),
                "timezone": "UTC",
                "tau": tau,
                "ne": radii[0],
                "se": radii[1],
                "sw": radii[2],
                "nw": radii[3],
                "idp_source": f"{ATCF_ID.lower()}_{_stamp(clock.issued_at)}_{kind}",
                "idp_filedate": _epoch_ms(clock.issued_at),
                "idp_ingestdate": _epoch_ms(clock.issued_at + timedelta(seconds=30)),
                "binnumber": SLOT,
            }
            geometry = {"type": "Polygon", "coordinates": [_radii_ring(clock.centre(tau), radii)]}
            features.append(_feature(geometry, properties))
    return _collection(features)


def _band_outline(clock: _Clock, radius_nmi: float, last_tau: int) -> list[Point]:
    radius = radius_nmi * KM_PER_NMI
    return _corridor([(clock.centre(0), radius), (clock.centre(last_tau), radius)])


def _wind_bands(clock: _Clock, threshold: int) -> dict[str, object]:
    template = template_properties(WIND_LAYERS[threshold])
    bands = clock.stage.bands[threshold]
    source = f"{_stamp(clock.synoptic)}_wsp{threshold}knt120hr_5km"
    features: list[dict[str, object]] = []
    for index, (label, radius, last_tau) in enumerate(bands):
        rings = [_ring(_band_outline(clock, radius, last_tau))]
        if index + 1 < len(bands):
            _, inner, inner_tau = bands[index + 1]
            rings.append(_ring(_band_outline(clock, inner, inner_tau), counterclockwise=False))
        properties = {
            **template,
            "objectid": index + 1,
            "percentage": label,
            "idp_source": source,
            "idp_filedate": _epoch_ms(clock.issued_at),
            "idp_ingestdate": _epoch_ms(clock.issued_at + timedelta(seconds=30)),
        }
        features.append(_feature({"type": "Polygon", "coordinates": rings}, properties))
    return _collection(features)


@dataclass(frozen=True)
class _ArrivalLine:
    label: str | None
    points: list[list[float]]


def _arrival_lines(clock: _Clock, kind: ArrivalKind) -> list[_ArrivalLine]:
    """The isochrones ahead of the center and the outer 5 percent contour.

    Each isochrone, at 8 am and 8 pm EDT after the advisory and within its 120 hours,
    crosses the track where the center will be ``ARRIVAL_LEAD_H`` hours later: the
    leading edge of the tropical-storm-force winds. Its ends stop well inside the outer
    contour, which is the 34-kt 5 percent band's outline.
    """
    outer_label, outer_radius, outer_tau = clock.stage.bands[34][0]
    del outer_label
    half_width_km = 0.9 * outer_radius * KM_PER_NMI
    lead = ARRIVAL_LEAD_H[kind]
    lines: list[_ArrivalLine] = []
    instant = clock.synoptic.replace(hour=0) + timedelta(hours=12)
    while instant - clock.issued_at < timedelta(hours=120):
        tau = _hours(instant - clock.synoptic) + lead
        if instant > clock.issued_at and tau <= outer_tau:
            centre = clock.centre(tau)
            ends = (
                _offset(centre, HEADING_DEG - 90, half_width_km),
                centre,
                _offset(centre, HEADING_DEG + 90, half_width_km),
            )
            lines.append(_ArrivalLine(_label(instant), _line(ends)))
        instant += timedelta(hours=12)
    outer = _ring(_band_outline(clock, outer_radius, outer_tau))
    lines.append(_ArrivalLine(None, outer))
    return lines


def _arrival_layer(clock: _Clock, kind: ArrivalKind) -> dict[str, object]:
    layer = EARLIEST_ARRIVAL if kind == "earliest_reasonable" else MOST_LIKELY_ARRIVAL
    template = template_properties(layer)
    words = "Earliest-Reasonable" if kind == "earliest_reasonable" else "Most-Likely"
    folder = f"{words} Time of Arrival: {ATCF_ID}_Adv{clock.stage.advisory}"
    features = [
        _feature(
            {"type": "LineString", "coordinates": line.points},
            {
                **template,
                "arrival_time": line.label or " ",
                "objectid": index + 1,
                "folderpath": folder,
                "idp_filedate": _epoch_ms(clock.issued_at),
                "idp_ingestdate": _epoch_ms(clock.issued_at + timedelta(seconds=30)),
                "idp_source": f"{ATCF_ID}_{clock.stage.advisory:03d}adv_{kind}_toa_34",
                "idp_subset": ATCF_ID.lower(),
                "binnumber": SLOT,
                "popupinfo": f"<table><tr><td>{line.label or ' '}</td></tr></table>",
            },
        )
        for index, line in enumerate(_arrival_lines(clock, kind))
    ]
    return _collection(features)


def kmz_url(stage: StormStage, kind: ArrivalKind) -> str:
    """The arrival-time KMZ a stage's roster entry links.

    Args:
        stage: The stage.
        kind: ``earliest_reasonable`` or ``most_likely``.

    Returns:
        The URL, in the register's pattern.
    """
    return KMZ_URL.format(atcf=ATCF_ID, adv=stage.advisory, kind=kind)


def _kml(clock: _Clock, kind: ArrivalKind) -> str:
    words = "Earliest-Reasonable" if kind == "earliest_reasonable" else "Most-Likely"
    wind = clock.stage.forecast_kt[0]
    data = {
        "timezone": "EDT",
        "storm": f"{_title(wind)} {NAME} (synthetic demonstration)",
        "atcfid": ATCF_ID,
        "advisoryNum": str(clock.stage.advisory),
        "pubAdvTime": _local_text(clock.issued_at),
        "synthetic": "true",
    }
    extended = "".join(
        f'<Data name="{name}"><value>{value}</value></Data>' for name, value in data.items()
    )
    placemarks: list[str] = []
    for line in _arrival_lines(clock, kind):
        cell = line.label or "Wind Speed Probability 5% contour"
        coordinates = " ".join(f"{lon:.2f},{lat:.2f},0" for lon, lat in line.points)
        placemarks.append(
            "<Placemark>"
            f'<Snippet maxLines="0">{SYNTHETIC_NOTE}</Snippet>'
            "<styleUrl>#toa_line</styleUrl>"
            f"<description><![CDATA[<table><tr><td>{cell}</td></tr></table>]]></description>"
            f"<LineString><coordinates>{coordinates}</coordinates></LineString>"
            "</Placemark>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://earth.google.com/kml/2.2"><Document>'
        f"<name>{words} Time of Arrival: {ATCF_ID}_Adv{clock.stage.advisory}</name>"
        f"<ExtendedData>{extended}</ExtendedData>"
        '<Style id="toa_line"><LineStyle><color>ff000000</color><width>3</width></LineStyle>'
        "</Style>"
        f"{''.join(placemarks)}"
        "</Document></kml>\n"
    )


def _kmz(clock: _Clock, kind: ArrivalKind) -> bytes:
    member = f"{ATCF_ID}_{clock.stage.advisory}_{kind}_toa_34.kml"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo(member, date_time=(2026, 10, 12, 21, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, _kml(clock, kind))
    return buffer.getvalue()


def _past(clock: _Clock) -> tuple[dict[str, object], dict[str, object]]:
    """The past points every six hours to the synoptic time, and the past track between them."""
    point_template = template_properties(PAST_POINTS)
    track_template = template_properties(PAST_TRACK)
    end = _hours(clock.history_synoptic - FORMATION)
    hours = [float(hour) for hour in range(-12, int(end) + 1, 6)]
    points: list[dict[str, object]] = []
    lines: list[dict[str, object]] = []
    previous: tuple[Point, str, int] | None = None
    for index, hour in enumerate(hours):
        wind = intensity_at(hour)
        storm_type = _kind(wind)[0] if hour >= _DEPRESSION_H else "LO"
        when = clock.shown(FORMATION + timedelta(hours=hour))
        centre = _rounded(position(FORMATION + timedelta(hours=hour)))
        points.append(
            _feature(
                {"type": "Point", "coordinates": list(centre)},
                {
                    **point_template,
                    "objectid": index + 1,
                    "stormname": NAME.upper() if wind >= _STORM_KT else "EIGHTY",
                    "stormtype": storm_type,
                    "stormnum": STORM_NUMBER,
                    "intensity": wind,
                    "basin": "al",
                    "mslp": _pressure_mb(wind),
                    "dtg": int(_stamp(when)),
                    "year": when.year,
                    "month": f"{when:%m}",
                    "day": when.day,
                    "hhmm": f"{when:%H%M}",
                    "lat": centre[1],
                    "lon": centre[0],
                    "ss": _category(wind),
                    "idp_source": f"{ATCF_ID}_pts",
                    "binnumber": SLOT,
                },
            )
        )
        if previous is not None:
            start, start_type, start_category = previous
            lines.append(
                _feature(
                    {"type": "LineString", "coordinates": _line([start, centre])},
                    {
                        **track_template,
                        "objectid": len(lines) + 1,
                        "stormtype": start_type,
                        "stormnum": STORM_NUMBER,
                        "idp_source": f"{ATCF_ID}_lin",
                        "ss": start_category,
                        "binnumber": SLOT,
                    },
                )
            )
        previous = (centre, storm_type, _category(wind))
    return _collection(points), _collection(lines)


def _roster_entry(clock: _Clock) -> dict[str, object]:
    stage = clock.stage
    template = _template_storm()
    wind = stage.forecast_kt[0]
    issued = _instant(clock.issued_at)
    centre = position(HISTORY_ISSUED_AT[stage.name])
    lat, lon = round(centre[1], 1), round(centre[0], 1)
    return {
        **{key: template[key] for key in ("id", "binNumber", "name", "classification")},
        "id": ATCF_ID.lower(),
        "binNumber": SLOT,
        "name": NAME,
        "classification": _kind(wind)[0],
        "intensity": str(wind),
        "pressure": str(_pressure_mb(wind)),
        "latitude": f"{abs(lat):.1f}{'N' if lat >= 0 else 'S'}",
        "longitude": f"{abs(lon):.1f}{'W' if lon < 0 else 'E'}",
        "latitudeNumeric": lat,
        "longitudeNumeric": lon,
        "movementDir": round(HEADING_DEG),
        "movementSpeed": round(SPEED_KMH / 1.609344),
        "lastUpdate": issued,
        "publicAdvisory": {"advNum": f"{stage.advisory:03d}", "issuance": issued},
        "trackCone": {"advNum": f"{stage.advisory:03d}", "issuance": issued},
        "windSpeedProbabilitiesGIS": {"issuance": _instant(clock.synoptic)},
        "earliestArrivalTimeTSWindsGIS": {
            "advNum": f"{stage.advisory:03d}",
            "issuance": issued,
            "kmzFile": kmz_url(stage, "earliest_reasonable"),
        },
        "mostLikelyTimeTSWindsGIS": {
            "advNum": f"{stage.advisory:03d}",
            "issuance": issued,
            "kmzFile": kmz_url(stage, "most_likely"),
        },
        "stormSurgeWatchWarningGIS": None,
        "potentialStormSurgeFloodingGIS": None,
        "peakSurgeKML": None,
        "synthetic": True,
        "note": SYNTHETIC_NOTE,
    }


def roster_document(
    stage: StageName | None, issued_at: datetime | None = None
) -> dict[str, object]:
    """The roster: the storm at a stage, or no storm at all.

    Args:
        stage: The stage, or ``None`` for an empty roster.
        issued_at: When the stage's advisory is shown as issued.

    Returns:
        ``CurrentStorms.json`` as parsed JSON.
    """
    if stage is None:
        return {"activeStorms": []}
    clock = _Clock(STAGES[stage], issued_at or HISTORY_ISSUED_AT[stage])
    return {"activeStorms": [_roster_entry(clock)]}


def tcp_list_url() -> str:
    """The TCP list of the storm's slot.

    Returns:
        The URL.
    """
    return f"{API_ROOT}/products/types/TCP/locations/{SLOT}"


def tcp_product_id(stage: StormStage) -> str:
    """A stage's TCP product id: synthetic, and in the client's id pattern.

    Args:
        stage: The stage.

    Returns:
        The id.
    """
    return f"synthetic-{ATCF_ID.lower()}-{stage.advisory:03d}"


def _place(centre: Point, landmark: Point, name: str) -> str:
    km = _distance_km(landmark, centre)
    compass = _compass(_bearing_deg(landmark, centre))
    return f"ABOUT {round(km / 1.609344 / 5) * 5} MI...{round(km / 5) * 5} KM {compass} OF {name}"


NASSAU_CITY: Final[Point] = (-77.34, 25.06)
MIAMI_CITY: Final[Point] = (-80.19, 25.77)


def _tcp_text(clock: _Clock) -> str:
    stage = clock.stage
    wind = stage.forecast_kt[0]
    title = _title(wind)
    centre = position(HISTORY_ISSUED_AT[stage.name])
    lat, lon = round(centre[1], 1), round(centre[0], 1)
    local = _local_text(clock.issued_at)
    clock_text = local.split(" EDT ", 1)[0]
    utc = f"{clock.issued_at:%H%M}"
    return "\n".join(
        (
            "000",
            f"WTNT31 KNHC {clock.issued_at:%d%H%M}",
            f"TCP{SLOT}",
            " ",
            "BULLETIN",
            f"{title} {NAME} Advisory Number {stage.advisory:>3}",
            f"NWS National Hurricane Center Miami FL       {ATCF_ID}",
            local,
            " ",
            "...SYNTHETIC DEMONSTRATION: HURRICANE DEMO IS NOT A REAL STORM...",
            f"...{stage.headline}...",
            " ",
            f"SUMMARY OF {clock_text} EDT...{utc} UTC...INFORMATION",
            "----------------------------------------------",
            f"LOCATION...{lat:.1f}N {abs(lon):.1f}W",
            _place(centre, NASSAU_CITY, "NASSAU"),
            _place(centre, MIAMI_CITY, "MIAMI FLORIDA"),
            f"MAXIMUM SUSTAINED WINDS...{_mph(wind)} MPH...{round(wind * 1.852 / 5) * 5} KM/H",
            (
                f"PRESENT MOVEMENT...{_compass(HEADING_DEG)} OR {round(HEADING_DEG)} DEGREES AT "
                f"{round(SPEED_KMH / 1.609344)} MPH...{round(SPEED_KMH)} KM/H"
            ),
            f"MINIMUM CENTRAL PRESSURE...{_pressure_mb(wind)} MB",
            " ",
            "WATCHES AND WARNINGS",
            "--------------------",
            "SUMMARY OF WATCHES AND WARNINGS IN EFFECT:",
            " ",
            stage.watches,
            " ",
            "DISCUSSION AND OUTLOOK",
            "----------------------",
            f"At {clock_text} EDT ({utc} UTC), the center of {title} {NAME} was located",
            f"near latitude {lat:.1f} North, longitude {abs(lon):.1f} West. {NAME} is moving",
            f"toward the west-northwest near {round(SPEED_KMH / 1.609344)} mph.",
            stage.discussion,
            " ",
            "This advisory is synthetic: Weatherbot's demonstration scenarios built it, and",
            "no forecaster issued it. It is never official guidance.",
            " ",
            "$$",
            "Forecaster Synthetic",
            "",
        )
    )


def _tcp_list(clock: _Clock) -> dict[str, object]:
    _item, body = _capture("nhc-text-products", "tcp-ep5-list.json")
    template = cast("dict[str, object]", json.loads(body))
    identifier = tcp_product_id(clock.stage)
    item = {
        "@id": f"{API_ROOT}/products/{identifier}",
        "id": identifier,
        "wmoCollectiveId": "WTNT31",
        "issuingOffice": "KNHC",
        "issuanceTime": clock.issued_at.isoformat(),
        "productCode": "TCP",
        "productName": "Public Tropical Cyclone Advisory",
        "synthetic": True,
    }
    return {**{key: value for key, value in template.items() if key != "@graph"}, "@graph": [item]}


def _tcp_product(clock: _Clock) -> dict[str, object]:
    _item, body = _capture("nhc-text-products", "tcp-ep5-product.json")
    template = cast("dict[str, object]", json.loads(body))
    identifier = tcp_product_id(clock.stage)
    return {
        **template,
        "@id": f"{API_ROOT}/products/{identifier}",
        "id": identifier,
        "wmoCollectiveId": "WTNT31",
        "issuingOffice": "KNHC",
        "issuanceTime": clock.issued_at.isoformat(),
        "productCode": "TCP",
        "productName": "Public Tropical Cyclone Advisory",
        "productText": _tcp_text(clock),
        "synthetic": True,
    }


def stage_answers(stage: StageName, issued_at: datetime | None = None) -> dict[str, StagedAnswer]:
    """Build every answer a live cycle requests for the storm at one stage.

    Args:
        stage: ``cone``, ``watch``, or ``landfall``.
        issued_at: When the stage's advisory is shown as issued; its history time when
            omitted.

    Returns:
        Each answer by the URL a cycle requests it from: the roster, the storm's summary
        layers, its wind-speed probability layers, both arrival-time KMZs, and the TCP
        list and product.
    """
    clock = _Clock(STAGES[stage], issued_at or HISTORY_ISSUED_AT[stage])
    urls = summary_layer_urls()
    past_points, past_track = _past(clock)
    layers: dict[str, dict[str, object]] = {
        FORECAST_CONE: _forecast_cone(clock),
        FORECAST_POINTS: _forecast_points(clock),
        FORECAST_TRACK: _forecast_track(clock),
        WATCH_WARNING: _watch_warnings(clock),
        FORECAST_WIND_RADII: _wind_radii(clock, field=False),
        ADVISORY_WIND_FIELD: _wind_radii(clock, field=True),
        EARLIEST_ARRIVAL: _arrival_layer(clock, "earliest_reasonable"),
        MOST_LIKELY_ARRIVAL: _arrival_layer(clock, "most_likely"),
        PAST_POINTS: past_points,
        PAST_TRACK: past_track,
        PAST_SWATH: _collection([]),
        **{name: _wind_bands(clock, threshold) for threshold, name in WIND_LAYERS.items()},
    }
    answers = {urls[name]: StagedAnswer.json(document) for name, document in layers.items()}
    answers[ROSTER_URL] = StagedAnswer.json(
        roster_document(stage, clock.issued_at), "application/json"
    )
    for kind in ARRIVAL_KINDS:
        answers[kmz_url(clock.stage, kind)] = StagedAnswer(200, _kmz(clock, kind), KMZ_TYPE)
    answers[tcp_list_url()] = StagedAnswer.json(_tcp_list(clock), LD_JSON)
    product_url = f"{API_ROOT}/products/{tcp_product_id(clock.stage)}"
    answers[product_url] = StagedAnswer.json(_tcp_product(clock), LD_JSON)
    return answers


def cone_advisory_attributes(stage: StageName | None) -> dict[str, object]:
    """The cone layer's attribute-only answer the window watch reads (``f=json``).

    Args:
        stage: The stage, or ``None`` when no storm is active.

    Returns:
        The answer: one row with the storm's slot and advisory, or none.
    """
    if stage is None:
        return {"features": []}
    row = {"binnumber": SLOT, "advisnum": str(STAGES[stage].advisory), "synthetic": True}
    return {"features": [{"attributes": row}]}


def kml_positions(body: bytes) -> list[float]:
    """Every coordinate value a KMZ's KML writes.

    Args:
        body: The KMZ.

    Returns:
        Each longitude and latitude, in order.
    """
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        text = archive.read(archive.namelist()[0]).decode("utf-8")
    values: list[float] = []
    for block in text.split("<coordinates>")[1:]:
        for token in block.split("</coordinates>", 1)[0].split():
            values.extend(float(part) for part in token.split(",")[:2])
    return values


def json_positions(value: object, key: str = "") -> list[float]:
    """Every coordinate value a JSON answer writes: geometry, and position fields.

    Args:
        value: A parsed JSON value.
        key: The key that holds it.

    Returns:
        Each value under ``coordinates``, ``lat``, ``lon``, ``latitudeNumeric``, or
        ``longitudeNumeric``.
    """
    if isinstance(value, dict):
        items = cast("dict[str, object]", value).items()
        return [found for name, item in items for found in json_positions(item, name)]
    if isinstance(value, list):
        return [
            found for item in cast("list[object]", value) for found in json_positions(item, key)
        ]
    if isinstance(value, float) and key in _POSITION_KEYS:
        return [value]
    return []


def synthetic_positions(answers: Mapping[str, StagedAnswer]) -> list[float]:
    """Every coordinate value the synthetic answers write, for the two-decimal check.

    Args:
        answers: Staged answers.

    Returns:
        Each longitude and latitude in GeoJSON geometry, in feature and roster position
        fields, and in KML coordinates.
    """
    values: list[float] = []
    for answer in answers.values():
        if answer.content_type == KMZ_TYPE:
            values.extend(kml_positions(answer.body))
        else:
            values.extend(json_positions(json.loads(answer.body)))
    return values


_POSITION_KEYS: Final = frozenset(
    {"coordinates", "lat", "lon", "latitudeNumeric", "longitudeNumeric"}
)


def decimals(value: float) -> int:
    """How many decimals a coordinate is written with.

    Args:
        value: The coordinate.

    Returns:
        The decimals of its shortest representation.
    """
    text = repr(value)
    return len(text.split(".", 1)[1]) if "." in text else 0
