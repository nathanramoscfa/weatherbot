# scripts/record_fixtures.py
"""Record live fixtures of every ``required`` source in the data-source register.

``docs/DATA_SOURCES.md`` names the sources, their endpoints, the shared ArcGIS query
parameters, and the User-Agent. This development script (Phase 2 builds the real clients
in ``weatherbot.sources``) fetches each ``required`` source and stores what it received in
``tests/fixtures/recorded/<source-id>/<yyyy-mm-dd>/``, with one ``manifest.json`` per
capture directory. The directory date is the operator's local date; the manifest times are
UTC. A manifest holds, for every file, the URL, the status, the SHA-256 and size of the
payload as received, the response headers on an allowlist, and the origin. A payload over
1 MiB is stored gzip-compressed with ``mtime=0``, so recording the same bytes twice writes
the same file.

Commands (run from anywhere; every default path is anchored on the repository root)::

    uv run python scripts/record_fixtures.py record --all
    uv run python scripts/record_fixtures.py record --source nhc-current-storms nws-points
    uv run python scripts/record_fixtures.py harvest-v1

``harvest-v1`` extracts the six seven-day Atlantic outlook maps that the 2025 version 1
reports embed, and any restored version 1 cache entry whose URL belongs to a ``required``
source, into the same layout with ``harvest:`` origins.

Requests carry only the public landmarks of ``scripts/public_landmarks.toml``, and ArcGIS
layers are resolved by name from each service's catalog, never by a stored id. Exit status:
0 every source recorded, 1 a source or the harvest failed, 2 a usage error.
"""

import argparse
import base64
import binascii
import gzip
import hashlib
import json
import re
import shutil
import struct
import sys
import time
from collections import defaultdict
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Final, cast
from urllib.parse import urlencode, urlsplit

import httpx

from check_personal_data import Landmark, load_landmarks
from weatherbot.sources import USER_AGENT
from weatherbot.sources.arcgis import COUNT_PARAMETERS, QUERY_PARAMETERS
from weatherbot.sources.http import DEFAULT_INTERVAL, HEADER_ALLOWLIST, HOST_INTERVALS

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPOSITORY_ROOT / "tests" / "fixtures" / "recorded"
DEFAULT_REPORTS = REPOSITORY_ROOT / "reports"
DEFAULT_CACHE = REPOSITORY_ROOT / "cache"

RECORDER_PATH = "scripts/record_fixtures.py"
# USER_AGENT, the header allowlist, the per-host intervals, and the ArcGIS query parameters
# are the package's (weatherbot.sources): one definition each, shared with the clients.
SCHEMA_VERSION = 1
MANIFEST_NAME = "manifest.json"

GZIP_THRESHOLD_BYTES = 1024 * 1024
MAX_STORED_BYTES = 5 * 1024 * 1024

# The recorder's requests run serially, paced by the package's HOST_INTERVALS.
REQUEST_TIMEOUT = httpx.Timeout(60.0, connect=15.0)
REQUEST_ATTEMPTS = 4
BACKOFF_SECONDS = 2.0

NHC_ROOT = "https://www.nhc.noaa.gov"
NWS_ROOT = "https://api.weather.gov"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
MAP_ROOT = "https://mapservices.weather.noaa.gov/tropical/rest/services/tropical"
NOWCOAST_ROOT = "https://nowcoast.noaa.gov/geoserver"

SLOT_PATTERN = re.compile(r"(?:AT|EP|CP)[1-5]")
ZONE_ID_PATTERN = re.compile(r"[A-Z]{2}[A-Z][0-9]{3}")
PRODUCT_ID_PATTERN = re.compile(r"[0-9A-Za-z-]{8,64}")
BASINS = ("AT", "EP", "CP")
GIS_FEEDS = ("at", "ep", "cp")
OUTLOOK_FILES = (
    "two_atl_2d0.png",
    "two_atl_7d0.png",
    "two_pac_2d0.png",
    "two_pac_7d0.png",
    "two_cpac_2d0.png",
    "two_cpac_7d0.png",
)
ZONE_TYPES = {"county": "county", "forecastZone": "forecast", "fireWeatherZone": "fire"}
ALERT_ZONE_FIELDS = ("county", "forecastZone")
HTTP_OK = 200
HTTP_SERVER_ERROR = 500
PROBLEM_JSON = "application/problem+json"
DOCUMENTED_ERROR_STATUSES = (400, 404)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_HEADER_END = 24

OUTLOOK_ALT = "NOAA 7-Day Atlantic Tropical Weather Outlook"
OUTLOOK_URL = f"{NHC_ROOT}/xgtwo/two_atl_7d0.png"
DATA_URI_PREFIX = "data:image/png;base64,"
OUTLOOK_SOURCE = "nhc-outlook-graphics"
REPORT_GLOB = "hurricane_threat_analysis_2025*.html"
REPORT_NAME = re.compile(r"hurricane_threat_analysis_(\d{8})_(\d{6})\.html")
# Version 1 stamped reports with local time, and every 2025 report falls in daylight time.
EDT = timezone(timedelta(hours=-4), "EDT")
DAYLIGHT_TIME_ENDS = date(2025, 11, 2)

ORIGIN_LIVE = "live"
ORIGIN_REPORT = "harvest:v1-report"
ORIGIN_CACHE = "harvest:v1-cache"


class RecorderError(Exception):
    """A problem that fails one source or the harvest; the message names it.

    Messages carry URLs without their query strings and never a response body.
    """


def utc_text(moment: datetime) -> str:
    """Return ``moment`` as UTC, to the second, with a ``Z`` suffix.

    Args:
        moment: A timezone-aware time.

    Returns:
        For example ``2026-10-20T15:02:11Z``.
    """
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_json(body: bytes, what: str) -> object:
    """Parse JSON bytes.

    Args:
        body: The payload.
        what: What the payload is, for the error message.

    Returns:
        The parsed value.

    Raises:
        RecorderError: The payload is not JSON.
    """
    try:
        value: object = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        message = f"{what} is not valid JSON"
        raise RecorderError(message) from error
    return value


def as_object(value: object, what: str) -> dict[str, object]:
    """Return ``value`` as a JSON object.

    Args:
        value: A parsed JSON value.
        what: What the value is, for the error message.

    Returns:
        The object.

    Raises:
        RecorderError: The value is not an object.
    """
    if not isinstance(value, dict):
        message = f"{what} is not a JSON object"
        raise RecorderError(message)
    return cast("dict[str, object]", value)


def as_list(value: object, what: str) -> list[object]:
    """Return ``value`` as a JSON array.

    Args:
        value: A parsed JSON value.
        what: What the value is, for the error message.

    Returns:
        The array.

    Raises:
        RecorderError: The value is not an array.
    """
    if not isinstance(value, list):
        message = f"{what} is not a JSON array"
        raise RecorderError(message)
    return cast("list[object]", value)


def slugify(name: str) -> str:
    """Return a file-name slug of a layer name: lower case, runs of other characters to ``-``.

    Args:
        name: A layer name such as ``EP5 Forecast Cone``.

    Returns:
        For example ``ep5-forecast-cone``.
    """
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def png_dimensions(data: bytes) -> tuple[int, int]:
    """Return the width and height a PNG's header states.

    Args:
        data: The PNG bytes.

    Returns:
        The width and height in pixels.

    Raises:
        RecorderError: The bytes lack the PNG signature or an ``IHDR`` chunk.
    """
    if len(data) < PNG_HEADER_END or not data.startswith(PNG_SIGNATURE) or data[12:16] != b"IHDR":
        message = "the payload is not a PNG"
        raise RecorderError(message)
    width, height = struct.unpack(">II", data[16:PNG_HEADER_END])
    if width == 0 or height == 0:
        message = "the PNG states a zero dimension"
        raise RecorderError(message)
    return width, height


def display_path(path: Path) -> str:
    """Return a repository-relative POSIX path, or the path itself outside the repository.

    Args:
        path: A file or directory.

    Returns:
        The path text to print.
    """
    resolved = path.resolve()
    if resolved.is_relative_to(REPOSITORY_ROOT):
        return resolved.relative_to(REPOSITORY_ROOT).as_posix()
    return str(resolved)


@dataclass(frozen=True)
class Fetched:
    """One HTTP response: its URL, status, body, and allowlisted headers."""

    url: str
    status: int
    body: bytes
    headers: Mapping[str, str]
    fetched_at: datetime

    @property
    def content_type(self) -> str:
        """The response's ``Content-Type`` header, or an empty string."""
        return self.headers.get("content-type", "")


@dataclass(frozen=True)
class Capture:
    """One file to store in a capture directory, with its provenance."""

    name: str
    url: str
    status: int
    fetched_at: datetime
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict[str, str])
    origin: str = ORIGIN_LIVE
    notes: str = ""
    harvested_from: str | None = None


def capture_of(fetched: Fetched, name: str, notes: str = "") -> Capture:
    """Turn a live response into a capture.

    Args:
        fetched: The response.
        name: The file name before compression, with its extension.
        notes: A short note for the manifest.

    Returns:
        The capture.
    """
    return Capture(
        name=name,
        url=fetched.url,
        status=fetched.status,
        fetched_at=fetched.fetched_at,
        body=fetched.body,
        headers=fetched.headers,
        notes=notes,
    )


def json_name(stem: str, body: bytes) -> str:
    """Name a JSON payload ``.geojson`` when it is a FeatureCollection, else ``.json``.

    Args:
        stem: The file name without an extension.
        body: The payload.

    Returns:
        The file name.
    """
    try:
        document = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return f"{stem}.json"
    if isinstance(document, dict) and cast("dict[str, object]", document).get("type") == (
        "FeatureCollection"
    ):
        return f"{stem}.geojson"
    return f"{stem}.json"


def kept_headers(headers: httpx.Headers) -> dict[str, str]:
    """Keep only the allowlisted response headers (never ``set-cookie``).

    Args:
        headers: The response headers.

    Returns:
        The kept headers, lower-cased and sorted by name.
    """
    return {name: value for name, value in sorted(headers.items()) if name in HEADER_ALLOWLIST}


class Pacer:
    """Keeps a minimum interval between two requests to one host."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        intervals: Mapping[str, float] = HOST_INTERVALS,
        default: float = DEFAULT_INTERVAL,
    ) -> None:
        """Create a pacer.

        Args:
            clock: Returns seconds on a monotonic clock.
            sleep: Waits for a number of seconds.
            intervals: The minimum interval per host name.
            default: The minimum interval for any other host.
        """
        self._clock = clock
        self._sleep = sleep
        self._intervals = intervals
        self._default = default
        self._last: dict[str, float] = {}

    def wait(self, host: str) -> None:
        """Wait until a request to ``host`` may go out, then count it as sent.

        Args:
            host: The request's host name.
        """
        last = self._last.get(host)
        if last is not None:
            remaining = last + self._intervals.get(host, self._default) - self._clock()
            if remaining > 0:
                self._sleep(remaining)
        self._last[host] = self._clock()


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Fetcher:
    """Sends the recorder's requests: User-Agent, pacing, retries with backoff."""

    client: httpx.Client
    pacer: Pacer = field(default_factory=Pacer)
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], datetime] = _now
    attempts: int = REQUEST_ATTEMPTS
    backoff_seconds: float = BACKOFF_SECONDS

    def get(self, url: str, *, source: str, accept: Collection[int] = (200,)) -> Fetched:
        """Fetch ``url``, retrying a 5xx response or a connection error with backoff.

        Args:
            url: The complete request URL, query string included.
            source: The register id, for error messages.
            accept: The statuses to return; any other status is an error.

        Returns:
            The response.

        Raises:
            RecorderError: The retries ran out, or the status is not accepted.
        """
        parts = urlsplit(url)
        shown = parts._replace(query="").geturl()
        problem = ""
        for attempt in range(self.attempts):
            if attempt:
                self.sleep(self.backoff_seconds * 2 ** (attempt - 1))
            self.pacer.wait(parts.hostname or "")
            try:
                response = self.client.get(
                    url, headers={"User-Agent": USER_AGENT}, follow_redirects=False
                )
            except httpx.TransportError as error:
                problem = type(error).__name__
                continue
            if response.status_code >= HTTP_SERVER_ERROR:
                problem = f"HTTP {response.status_code}"
                continue
            if response.status_code not in accept:
                message = f"{source}: unexpected HTTP {response.status_code} from {shown}"
                raise RecorderError(message)
            return Fetched(
                url=url,
                status=response.status_code,
                body=response.content,
                headers=kept_headers(response.headers),
                fetched_at=self.now(),
            )
        message = f"{source}: {shown} failed after {self.attempts} attempts ({problem})"
        raise RecorderError(message)


def stored_form(name: str, body: bytes) -> tuple[str, bytes, str]:
    """Choose how a payload is stored: raw, or gzip above 1 MiB.

    Args:
        name: The file name before compression.
        body: The payload as received.

    Returns:
        The stored file name, the stored bytes, and ``raw`` or ``gzip``.
    """
    if len(body) > GZIP_THRESHOLD_BYTES:
        # mtime=0 and no embedded file name: the same bytes always give the same file.
        return f"{name}.gz", gzip.compress(body, compresslevel=9, mtime=0), "gzip"
    return name, body, "raw"


def manifest_entry(capture: Capture, stored_name: str, stored_as: str) -> dict[str, object]:
    """Build one manifest ``captures`` entry.

    Args:
        capture: The capture.
        stored_name: The stored file name.
        stored_as: ``raw`` or ``gzip``.

    Returns:
        The entry, in the schema's key order.
    """
    entry: dict[str, object] = {
        "file": stored_name,
        "url": capture.url,
        "status": capture.status,
        "fetched_at": utc_text(capture.fetched_at),
        "sha256": hashlib.sha256(capture.body).hexdigest(),
        "bytes": len(capture.body),
        "stored_as": stored_as,
        "headers": dict(capture.headers),
        "origin": capture.origin,
        "notes": capture.notes,
    }
    if capture.harvested_from is not None:
        entry["harvested_from"] = capture.harvested_from
    return entry


def write_capture_directory(
    out: Path, source: str, day: date, captures: Sequence[Capture], *, recorded_at: datetime
) -> Path:
    """Write ``out/<source>/<day>/`` with its payloads and manifest, replacing a same-day one.

    The directory is built beside its destination and renamed into place, so a failure
    leaves any earlier capture of that day untouched.

    Args:
        out: The recorded-fixtures root.
        source: The register id.
        day: The directory date.
        captures: The files to store.
        recorded_at: The time the manifest states.

    Returns:
        The capture directory.

    Raises:
        RecorderError: Nothing was captured, two captures share a name, a stored file is
            over 5 MiB, or the destination holds something that is not a capture directory.
    """
    if not captures:
        message = f"{source}: nothing was captured"
        raise RecorderError(message)
    names = [capture.name for capture in captures]
    if len(set(names)) != len(names):
        message = f"{source}: two captures share a file name"
        raise RecorderError(message)
    prepared = [(capture, *stored_form(capture.name, capture.body)) for capture in captures]
    for capture, stored_name, stored, _ in prepared:
        if len(stored) > MAX_STORED_BYTES:
            message = (
                f"{source}: the stored file {stored_name} is {len(stored)} bytes, over the "
                f"{MAX_STORED_BYTES} byte limit; shrink it with server-side query parameters "
                f"recorded in the register ({capture.url.split('?', 1)[0]})"
            )
            raise RecorderError(message)
    manifest = {
        "schema": SCHEMA_VERSION,
        "source": source,
        "recorded_at": utc_text(recorded_at),
        "recorder": RECORDER_PATH,
        "user_agent": USER_AGENT,
        "captures": [
            manifest_entry(capture, stored_name, stored_as)
            for capture, stored_name, _, stored_as in prepared
        ],
    }
    target = out / source / day.isoformat()
    staging = out / source / f".{day.isoformat()}.partial"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        for _, stored_name, stored, _ in prepared:
            (staging / stored_name).write_bytes(stored)
        text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        (staging / MANIFEST_NAME).write_bytes(text.encode("utf-8"))
        if target.exists():
            if not (target / MANIFEST_NAME).is_file():
                message = f"{source}: {display_path(target)} exists and is not a capture directory"
                raise RecorderError(message)
            shutil.rmtree(target)
        staging.rename(target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return target


type SourceRecorder = Callable[["Recorder"], Sequence[Capture]]


class Recorder:
    """The state one recording run shares: the fetcher, the landmarks, and memoized lookups."""

    def __init__(self, fetcher: Fetcher, landmarks: Sequence[Landmark]) -> None:
        """Create a recorder.

        Args:
            fetcher: Sends the requests.
            landmarks: The public landmarks whose coordinates requests may carry.
        """
        self.fetcher = fetcher
        self.landmarks = landmarks
        self._roster: Fetched | None = None
        self._points: dict[str, Fetched] = {}

    def roster(self) -> Fetched:
        """Fetch ``CurrentStorms.json`` once per run.

        Returns:
            The response.
        """
        if self._roster is None:
            self._roster = self.fetcher.get(
                f"{NHC_ROOT}/CurrentStorms.json", source="nhc-current-storms"
            )
        return self._roster

    def active_slots(self) -> list[str]:
        """List the storm slots (``EP5``) of the active storms.

        Returns:
            The slots, sorted.

        Raises:
            RecorderError: The roster is malformed or names a slot the register lacks.
        """
        roster = as_object(parse_json(self.roster().body, "CurrentStorms.json"), "the roster")
        slots: set[str] = set()
        for storm in as_list(roster.get("activeStorms"), "activeStorms"):
            slot = as_object(storm, "an active storm").get("binNumber")
            if not isinstance(slot, str) or not SLOT_PATTERN.fullmatch(slot):
                message = "nhc-current-storms: an active storm has an unknown binNumber"
                raise RecorderError(message)
            slots.add(slot)
        return sorted(slots)

    def points(self, landmark: Landmark) -> Fetched:
        """Fetch the NWS ``/points`` response for a landmark once per run.

        The out-of-coverage error (a ``problem+json`` 404) is a documented response.

        Args:
            landmark: A public landmark.

        Returns:
            The response.
        """
        if landmark.key not in self._points:
            url = f"{NWS_ROOT}/points/{coordinates(landmark)}"
            self._points[landmark.key] = self.fetcher.get(
                url, source="nws-points", accept=(200, *DOCUMENTED_ERROR_STATUSES)
            )
            require_documented(self._points[landmark.key], "nws-points")
        return self._points[landmark.key]


def coordinates(landmark: Landmark) -> str:
    """Format a landmark as ``lat,lon`` to four decimals, the way the register writes it.

    Args:
        landmark: A public landmark.

    Returns:
        For example ``25.7757,-80.1966``.
    """
    return f"{landmark.lat:.4f},{landmark.lon:.4f}"


def require_documented(fetched: Fetched, source: str) -> None:
    """Accept a non-200 response only if it is the API's ``problem+json`` error.

    Args:
        fetched: The response.
        source: The register id, for the error message.

    Raises:
        RecorderError: The status is not 200 and the body is not a ``problem+json`` error.
    """
    if fetched.status != HTTP_OK and not fetched.content_type.startswith(PROBLEM_JSON):
        message = f"{source}: HTTP {fetched.status} is not a documented error response"
        raise RecorderError(message)


def require_a_success(captures: Sequence[Capture], source: str) -> None:
    """Fail a source that recorded no 200 response at all.

    Args:
        captures: The source's captures.
        source: The register id, for the error message.

    Raises:
        RecorderError: No capture has status 200.
    """
    if not any(capture.status == HTTP_OK for capture in captures):
        message = f"{source}: no request returned HTTP 200"
        raise RecorderError(message)


def record_current_storms(recorder: Recorder) -> list[Capture]:
    """Record ``CurrentStorms.json``.

    Args:
        recorder: The run's state.

    Returns:
        The captures.
    """
    fetched = recorder.roster()
    parse_json(fetched.body, "CurrentStorms.json")
    return [capture_of(fetched, "CurrentStorms.json")]


@dataclass(frozen=True)
class LayerSpec:
    """One ArcGIS layer the recorder queries, named as the register names it."""

    name: str
    count_only: bool = False


@dataclass(frozen=True)
class MapService:
    """One ArcGIS map service: its catalog is always recorded, then the layers listed."""

    source_id: str
    service: str
    layers: tuple[LayerSpec, ...] = ()
    slot_layers: tuple[LayerSpec, ...] = ()

    @property
    def url(self) -> str:
        """The service's ``MapServer`` URL."""
        return f"{MAP_ROOT}/{self.service}/MapServer"


OUTLOOK_LAYERS = tuple(
    LayerSpec(name)
    for name in (
        "Two-Day: Current Location",
        "Seven-Day: Current Location",
        "Seven-Day: Development Motion",
        "Seven-Day: Potential Development Region",
    )
)
WIND_PROBABILITY_LAYERS = tuple(
    LayerSpec(f"Probabilistic Winds {knots} kts") for knots in (34, 50, 64)
)
# Every feature layer of a storm slot; ``{slot}`` stands for each active slot. A footprint
# layer is counted only: a non-zero count means the slot has an inundation raster.
SLOT_LAYERS = (
    LayerSpec("{slot} Forecast Points"),
    LayerSpec("{slot} Forecast Track"),
    LayerSpec("{slot} Forecast Cone"),
    LayerSpec("{slot} Watch-Warning"),
    LayerSpec("{slot} Past Points"),
    LayerSpec("{slot} Past Track"),
    LayerSpec("{slot} Past Cumulative Wind Swath"),
    LayerSpec("{slot} Past Wind Radii"),
    LayerSpec("{slot} Forecast Wind Radii"),
    LayerSpec("{slot} Advisory Wind Field"),
    LayerSpec("{slot} Earliest Reasonable Arrival Time"),
    LayerSpec("{slot} Most Likely Arrival Time"),
    LayerSpec("Boundary_Inun_{slot}"),
    LayerSpec("Footprint_Inun_{slot}", count_only=True),
    LayerSpec("Boundary_TMask_{slot}"),
    LayerSpec("Footprint_TMask_{slot}", count_only=True),
)
# The summary service holds the same layers across storms, named without the slot.
SUMMARY_LAYERS = tuple(
    LayerSpec(layer.name.replace("{slot} ", "").replace("_{slot}", ""), layer.count_only)
    for layer in SLOT_LAYERS
)

MAP_SERVICES: Final = {
    service.source_id: service
    for service in (
        MapService(
            "nhc-map-tropical-weather",
            "NHC_tropical_weather",
            layers=(*OUTLOOK_LAYERS, *WIND_PROBABILITY_LAYERS),
            slot_layers=SLOT_LAYERS,
        ),
        MapService(
            "nhc-map-tropical-summary",
            "NHC_tropical_weather_summary",
            layers=(*OUTLOOK_LAYERS, *SUMMARY_LAYERS, *WIND_PROBABILITY_LAYERS),
        ),
        MapService(
            "nhc-map-breakpoints",
            "NHC_Breakpoints",
            layers=(
                LayerSpec("Watch_Warning_Breakpoints"),
                LayerSpec("StormSurge_Communication_Points"),
            ),
        ),
        MapService(
            "nhc-map-peak-surge",
            "NHC_PeakStormSurge",
            layers=(LayerSpec("Points"), LayerSpec("Lines"), LayerSpec("Polygons")),
        ),
        # Only the catalog: v2 draws the hazard rasters through `export` and queries no layer.
        MapService("nhc-map-surge-risk", "StormSurgeRisk"),
    )
}


def resolve_layer(catalog: object, name: str) -> int:
    """Find a layer's id by its exact name in a service catalog.

    Args:
        catalog: The parsed ``MapServer?f=json`` document.
        name: The layer's name.

    Returns:
        The layer's id on the day the catalog was read.

    Raises:
        RecorderError: No layer, or more than one, has that name.
    """
    layers = as_list(as_object(catalog, "the catalog").get("layers"), "the catalog's layers")
    found = [
        layer.get("id")
        for layer in (as_object(item, "a catalog layer") for item in layers)
        if layer.get("name") == name
    ]
    if len(found) != 1 or not isinstance(found[0], int):
        message = f"the catalog lists {len(found)} layers named {name!r}, not exactly one"
        raise RecorderError(message)
    return found[0]


def check_query_result(body: bytes, layer: str, *, count_only: bool) -> None:
    """Check an ArcGIS query response: no error object, a FeatureCollection or a count.

    Args:
        body: The response body.
        layer: The layer name, for the error message.
        count_only: Whether the query asked for a count.

    Raises:
        RecorderError: The response is an ArcGIS error, is truncated, or has the wrong shape.
    """
    document = as_object(parse_json(body, f"the query of {layer!r}"), f"the query of {layer!r}")
    if "error" in document:
        message = f"the query of {layer!r} returned an ArcGIS error"
        raise RecorderError(message)
    if count_only:
        if not isinstance(document.get("count"), int):
            message = f"the count of {layer!r} is not a number"
            raise RecorderError(message)
        return
    if document.get("type") != "FeatureCollection" or not isinstance(
        document.get("features"), list
    ):
        message = f"the query of {layer!r} is not a GeoJSON FeatureCollection"
        raise RecorderError(message)
    if document.get("exceededTransferLimit"):
        message = f"the query of {layer!r} exceeded the transfer limit; it needs paging"
        raise RecorderError(message)


def record_map_service(recorder: Recorder, service: MapService) -> list[Capture]:
    """Record a map service's catalog and the layers the register lists for it.

    Layers are resolved by name from the catalog read in this run; storm-slot layers are
    recorded for every active slot.

    Args:
        recorder: The run's state.
        service: The service.

    Returns:
        The captures: the catalog, the layer schemas, then one per queried layer.
    """
    source = service.source_id
    fetcher = recorder.fetcher
    catalog = fetcher.get(f"{service.url}?f=json", source=source)
    schemas = fetcher.get(f"{service.url}/layers?f=json", source=source)
    captures = [capture_of(catalog, "catalog.json"), capture_of(schemas, "layers.json")]
    catalog_document = parse_json(catalog.body, f"the catalog of {source}")
    wanted = [(layer.name, layer) for layer in service.layers]
    if service.slot_layers:
        wanted.extend(
            (layer.name.replace("{slot}", slot), layer)
            for slot in recorder.active_slots()
            for layer in service.slot_layers
        )
    for name, layer in wanted:
        layer_id = resolve_layer(catalog_document, name)
        parameters = COUNT_PARAMETERS if layer.count_only else QUERY_PARAMETERS
        fetched = fetcher.get(
            f"{service.url}/{layer_id}/query?{urlencode(parameters, safe='*')}", source=source
        )
        check_query_result(fetched.body, name, count_only=layer.count_only)
        stem = f"{'count' if layer.count_only else 'query'}-{slugify(name)}"
        extension = "json" if layer.count_only else "geojson"
        captures.append(
            capture_of(fetched, f"{stem}.{extension}", f"layer {name!r}, id {layer_id}")
        )
    return captures


def _map_recorder(source_id: str) -> SourceRecorder:
    def record(recorder: Recorder) -> list[Capture]:
        return record_map_service(recorder, MAP_SERVICES[source_id])

    return record


def record_gis_rss(recorder: Recorder) -> list[Capture]:
    """Record the three NHC GIS RSS feeds.

    Args:
        recorder: The run's state.

    Returns:
        The captures.
    """
    captures: list[Capture] = []
    for feed in GIS_FEEDS:
        fetched = recorder.fetcher.get(f"{NHC_ROOT}/gis-{feed}.xml", source="nhc-gis-rss")
        captures.append(capture_of(fetched, f"gis-{feed}.xml"))
    return captures


def _latest_product_id(listing: Fetched, what: str) -> str | None:
    graph = as_list(as_object(parse_json(listing.body, what), what).get("@graph"), what)
    products = [as_object(item, what) for item in graph]
    dated = [
        (str(product.get("issuanceTime", "")), str(product.get("id", ""))) for product in products
    ]
    if not dated:
        return None
    identifier = max(dated)[1]
    if not PRODUCT_ID_PATTERN.fullmatch(identifier):
        message = f"{what}: the newest product has an unexpected id"
        raise RecorderError(message)
    return identifier


def record_text_products(recorder: Recorder) -> list[Capture]:
    """Record the NHC text products through the NWS API (the register's chosen path).

    For every active storm slot, the TCP list and its newest product; for every basin, the
    TWO list and its newest product.

    Args:
        recorder: The run's state.

    Returns:
        The captures.
    """
    source = "nhc-text-products"
    fetcher = recorder.fetcher
    targets = [("TCP", slot) for slot in recorder.active_slots()]
    targets.extend(("TWO", basin) for basin in BASINS)
    captures: list[Capture] = []
    for kind, location in targets:
        listing = fetcher.get(
            f"{NWS_ROOT}/products/types/{kind}/locations/{location}", source=source
        )
        stem = f"{kind.lower()}-{location.lower()}"
        captures.append(capture_of(listing, f"{stem}-list.json"))
        identifier = _latest_product_id(listing, f"the {kind} list for {location}")
        if identifier is None:
            continue
        product = fetcher.get(f"{NWS_ROOT}/products/{identifier}", source=source)
        parse_json(product.body, f"the {kind} product for {location}")
        captures.append(capture_of(product, f"{stem}-product.json", "the newest product"))
    return captures


def record_outlook_graphics(recorder: Recorder) -> list[Capture]:
    """Record the six NHC outlook maps.

    Args:
        recorder: The run's state.

    Returns:
        The captures, each noting its pixel size.
    """
    captures: list[Capture] = []
    for name in OUTLOOK_FILES:
        fetched = recorder.fetcher.get(f"{NHC_ROOT}/xgtwo/{name}", source=OUTLOOK_SOURCE)
        width, height = png_dimensions(fetched.body)
        captures.append(capture_of(fetched, name, f"PNG {width}x{height}"))
    return captures


def record_nws_points(recorder: Recorder) -> list[Capture]:
    """Record ``/points`` for every landmark, including the documented out-of-coverage error.

    Args:
        recorder: The run's state.

    Returns:
        The captures.
    """
    captures = [
        capture_of(
            fetched := recorder.points(landmark), json_name(f"points-{landmark.key}", fetched.body)
        )
        for landmark in recorder.landmarks
    ]
    require_a_success(captures, "nws-points")
    return captures


def record_nws_alerts_point(recorder: Recorder) -> list[Capture]:
    """Record the active alerts at every landmark's point.

    Args:
        recorder: The run's state.

    Returns:
        The captures; a landmark outside NWS coverage records the API's error response.
    """
    source = "nws-alerts-point"
    captures: list[Capture] = []
    for landmark in recorder.landmarks:
        fetched = recorder.fetcher.get(
            f"{NWS_ROOT}/alerts/active?point={coordinates(landmark)}",
            source=source,
            accept=(200, *DOCUMENTED_ERROR_STATUSES),
        )
        require_documented(fetched, source)
        captures.append(
            capture_of(fetched, json_name(f"alerts-point-{landmark.key}", fetched.body))
        )
    require_a_success(captures, source)
    return captures


def zone_references(recorder: Recorder, fields: Collection[str]) -> list[tuple[str, str]]:
    """List the ``(zone type, zone id)`` pairs the landmarks' ``/points`` responses name.

    Args:
        recorder: The run's state.
        fields: The ``/points`` properties to read (``county``, ``forecastZone``, ...).

    Returns:
        Unique pairs in first-seen order; the type is ``county``, ``forecast``, or ``fire``.

    Raises:
        RecorderError: A property is not an NWS zone URL.
    """
    found: dict[tuple[str, str], None] = {}
    for landmark in recorder.landmarks:
        points = recorder.points(landmark)
        if points.status != HTTP_OK:
            continue
        document = as_object(parse_json(points.body, "a points response"), "a points response")
        properties = as_object(document.get("properties"), "the points properties")
        for field_name, zone_type in ZONE_TYPES.items():
            value = properties.get(field_name)
            if field_name not in fields or value is None:
                continue
            segments = urlsplit(str(value)).path.strip("/").split("/")
            if (
                len(segments) != len(("zones", "type", "id"))
                or segments[0] != "zones"
                or segments[1] != zone_type
                or not ZONE_ID_PATTERN.fullmatch(segments[2])
            ):
                message = f"the points property {field_name} is not an NWS zone URL"
                raise RecorderError(message)
            found[(zone_type, segments[2])] = None
    return list(found)


def record_nws_alerts_zone(recorder: Recorder) -> list[Capture]:
    """Record the active alerts of each county and forecast zone the points name.

    Args:
        recorder: The run's state.

    Returns:
        The captures.
    """
    captures: list[Capture] = []
    for _, zone_id in dict.fromkeys(zone_references(recorder, ALERT_ZONE_FIELDS)):
        fetched = recorder.fetcher.get(
            f"{NWS_ROOT}/alerts/active/zone/{zone_id}", source="nws-alerts-zone"
        )
        captures.append(capture_of(fetched, json_name(f"alerts-zone-{zone_id}", fetched.body)))
    require_a_success(captures, "nws-alerts-zone")
    return captures


def record_nws_zones(recorder: Recorder) -> list[Capture]:
    """Record the county, forecast, and fire-weather zone each landmark's points name.

    Args:
        recorder: The run's state.

    Returns:
        The captures.
    """
    captures: list[Capture] = []
    for zone_type, zone_id in zone_references(recorder, ZONE_TYPES):
        fetched = recorder.fetcher.get(
            f"{NWS_ROOT}/zones/{zone_type}/{zone_id}", source="nws-zones"
        )
        captures.append(capture_of(fetched, f"zone-{zone_type}-{zone_id}.json"))
    require_a_success(captures, "nws-zones")
    return captures


def _overlay_recorder(source_id: str, workspace: str) -> SourceRecorder:
    def record(recorder: Recorder) -> list[Capture]:
        query = urlencode({"service": "WMS", "version": "1.3.0", "request": "GetCapabilities"})
        fetched = recorder.fetcher.get(f"{NOWCOAST_ROOT}/{workspace}/ows?{query}", source=source_id)
        return [capture_of(fetched, "capabilities.xml")]

    return record


def record_nominatim(recorder: Recorder) -> list[Capture]:
    """Record one reverse lookup per landmark.

    Args:
        recorder: The run's state.

    Returns:
        The captures.
    """
    captures: list[Capture] = []
    for landmark in recorder.landmarks:
        query = f"format=jsonv2&lat={landmark.lat:.4f}&lon={landmark.lon:.4f}"
        fetched = recorder.fetcher.get(f"{NOMINATIM_URL}?{query}", source="geocode-nominatim")
        parse_json(fetched.body, "a Nominatim response")
        captures.append(capture_of(fetched, f"reverse-{landmark.key}.json"))
    return captures


# Register ids to recording functions, in register order. The contract tests keep these ids
# equal to the register's `required` rows.
SOURCES: Final[Mapping[str, SourceRecorder]] = {
    "nhc-current-storms": record_current_storms,
    "nhc-map-tropical-weather": _map_recorder("nhc-map-tropical-weather"),
    "nhc-map-tropical-summary": _map_recorder("nhc-map-tropical-summary"),
    "nhc-map-breakpoints": _map_recorder("nhc-map-breakpoints"),
    "nhc-map-peak-surge": _map_recorder("nhc-map-peak-surge"),
    "nhc-map-surge-risk": _map_recorder("nhc-map-surge-risk"),
    "nhc-gis-rss": record_gis_rss,
    "nhc-text-products": record_text_products,
    OUTLOOK_SOURCE: record_outlook_graphics,
    "nws-points": record_nws_points,
    "nws-alerts-point": record_nws_alerts_point,
    "nws-alerts-zone": record_nws_alerts_zone,
    "nws-zones": record_nws_zones,
    "overlay-radar": _overlay_recorder("overlay-radar", "weather_radar"),
    "overlay-satellite": _overlay_recorder("overlay-satellite", "satellite"),
    "geocode-nominatim": record_nominatim,
}


@dataclass(frozen=True)
class Outcome:
    """The result of recording one source."""

    source: str
    directory: Path | None
    files: int
    stored_bytes: int
    problem: str | None = None


def record_sources(
    recorder: Recorder, source_ids: Sequence[str], out: Path, day: date
) -> list[Outcome]:
    """Record sources one after another; a failing source does not stop the others.

    Args:
        recorder: The run's state.
        source_ids: Register ids, each a key of ``SOURCES``.
        out: The recorded-fixtures root.
        day: The capture-directory date.

    Returns:
        One outcome per source, in order.
    """
    outcomes: list[Outcome] = []
    for source in source_ids:
        try:
            captures = SOURCES[source](recorder)
            directory = write_capture_directory(
                out, source, day, captures, recorded_at=recorder.fetcher.now()
            )
        except RecorderError as error:
            outcomes.append(Outcome(source, None, 0, 0, str(error)))
            continue
        stored = sum(path.stat().st_size for path in directory.iterdir())
        outcomes.append(Outcome(source, directory, len(captures), stored))
    return outcomes


class _OutlookFinder(HTMLParser):
    """Collects the base64 payload of each embedded PNG whose ``alt`` names the outlook map."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.payloads: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        attributes = dict(attrs)
        source = attributes.get("src")
        if (
            attributes.get("alt") == OUTLOOK_ALT
            and source is not None
            and source.startswith(DATA_URI_PREFIX)
        ):
            self.payloads.append(source[len(DATA_URI_PREFIX) :])


def report_time(name: str) -> datetime:
    """Read the local (EDT) time a version 1 report's file name carries.

    Args:
        name: A file name such as ``hurricane_threat_analysis_20251003_224500.html``.

    Returns:
        The time, with the EDT offset.

    Raises:
        RecorderError: The name does not match, or the date is outside daylight time.
    """
    match = REPORT_NAME.fullmatch(name)
    if match is None:
        message = f"{name} is not a version 1 report name"
        raise RecorderError(message)
    moment = datetime.strptime(f"{match[1]}{match[2]}", "%Y%m%d%H%M%S").replace(tzinfo=EDT)
    if moment.date() >= DAYLIGHT_TIME_ENDS:
        message = f"{name} falls after daylight time ended; its UTC time is unknown"
        raise RecorderError(message)
    return moment


def harvest_report(path: Path) -> tuple[date, Capture]:
    """Extract the seven-day Atlantic outlook map from one version 1 report.

    Nothing else in the report is read into the result.

    Args:
        path: A report file.

    Returns:
        The report's local date, and the capture of its outlook map.

    Raises:
        RecorderError: The report has no, or more than one, outlook map, or its PNG is bad.
    """
    moment = report_time(path.name)
    finder = _OutlookFinder()
    finder.feed(path.read_text(encoding="utf-8", errors="replace"))
    finder.close()
    if len(finder.payloads) != 1:
        message = f"{path.name} embeds {len(finder.payloads)} outlook maps, not one"
        raise RecorderError(message)
    try:
        data = base64.b64decode("".join(finder.payloads[0].split()), validate=True)
    except binascii.Error as error:
        message = f"{path.name} embeds an outlook map that is not valid base64"
        raise RecorderError(message) from error
    width, height = png_dimensions(data)
    capture = Capture(
        name=OUTLOOK_URL.rsplit("/", 1)[-1],
        url=OUTLOOK_URL,
        status=HTTP_OK,
        fetched_at=moment.astimezone(UTC),
        body=data,
        origin=ORIGIN_REPORT,
        notes=(
            f"PNG {width}x{height}. Version 1 embedded this image in its report; fetched_at is "
            "the report's local time (EDT) converted to UTC."
        ),
        harvested_from=f"reports/{path.name}",
    )
    return moment.date(), capture


def harvest_reports(reports: Path, out: Path, *, recorded_at: datetime) -> list[Path]:
    """Harvest the outlook map of every 2025 report into ``nhc-outlook-graphics``.

    Args:
        reports: The directory holding the version 1 reports.
        out: The recorded-fixtures root.
        recorded_at: The time the manifests state.

    Returns:
        The capture directories written.

    Raises:
        RecorderError: No report was found, two reports share a local date, or one is bad.
    """
    paths = sorted(reports.glob(REPORT_GLOB))
    if not paths:
        message = f"no {REPORT_GLOB} report in {display_path(reports)}"
        raise RecorderError(message)
    harvested = [harvest_report(path) for path in paths]
    days = [day for day, _ in harvested]
    if len(set(days)) != len(days):
        message = "two reports share a local date, so their folders would collide"
        raise RecorderError(message)
    return [
        write_capture_directory(out, OUTLOOK_SOURCE, day, [capture], recorded_at=recorded_at)
        for day, capture in harvested
    ]


V1_MAP_URL = f"{MAP_ROOT}/NHC_tropical_weather/MapServer"
V1_STORMS_URL = f"{NHC_ROOT}/CurrentStorms.json"
V1_ATCF_URL = "https://ftp.nhc.noaa.gov/atcf/btk/"
V1_QUERY_PARAMETERS: Final = tuple(
    {"where": "1=1", "outFields": "*", "f": response_format, "outSR": "4326"}
    for response_format in ("geojson", "json")
)
V1_MAX_LAYER_ID = 511


@dataclass(frozen=True)
class V1Request:
    """A request version 1 made whose cache key can be recomputed."""

    url: str
    source: str | None
    name: str


def _md5(text: str) -> str:
    # Version 1's cache key, not a security use.
    return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()


def v1_requests() -> dict[str, V1Request]:
    """Recompute the cache keys of version 1's request set.

    Version 1 keyed the map service ``md5(f"{url}_{params}")``, current storms ``md5(url)``,
    and ATCF ``"atcf_" + md5(url)``.

    Returns:
        The request per cache key (the cache file's stem). A ``None`` source is a request
        outside the register.
    """
    requests = {
        _md5(f"{V1_MAP_URL}?f=json_None"): V1Request(
            f"{V1_MAP_URL}?f=json", "nhc-map-tropical-weather", "catalog.json"
        ),
        _md5(V1_STORMS_URL): V1Request(V1_STORMS_URL, "nhc-current-storms", "CurrentStorms.json"),
        f"atcf_{_md5(V1_ATCF_URL)}": V1Request(V1_ATCF_URL, None, "atcf-listing.json"),
    }
    for layer_id in range(V1_MAX_LAYER_ID + 1):
        for parameters in V1_QUERY_PARAMETERS:
            url = f"{V1_MAP_URL}/{layer_id}/query"
            extension = "geojson" if parameters["f"] == "geojson" else "json"
            requests[_md5(f"{url}_{parameters}")] = V1Request(
                f"{url}?{urlencode(parameters, safe='*')}",
                "nhc-map-tropical-weather",
                f"v1-layer-{layer_id}-{parameters['f']}.{extension}",
            )
    return requests


@dataclass(frozen=True)
class CacheHarvest:
    """What ``harvest_cache`` did with the version 1 cache files."""

    directories: list[Path]
    unrecoverable: list[str]
    out_of_register: list[str]


def _cache_entry(path: Path) -> tuple[datetime, object] | None:
    """Read a version 1 cache file: its timestamp and parsed data, or None if it is unreadable."""
    try:
        entry = as_object(parse_json(path.read_bytes(), path.name), path.name)
        stamp = entry["timestamp"]
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)):
            return None
        return datetime.fromtimestamp(stamp, UTC), entry["data"]
    except (RecorderError, KeyError, OSError, OverflowError, ValueError):
        return None


def harvest_cache(cache: Path, out: Path, *, recorded_at: datetime) -> CacheHarvest:
    """Harvest restored version 1 cache entries whose URL belongs to a ``required`` source.

    A cache entry holds parsed JSON, not the bytes NOAA sent, so the payload is re-serialized
    and the manifest says so.

    Args:
        cache: The version 1 cache directory (it may not exist).
        out: The recorded-fixtures root.
        recorded_at: The time the manifests state.

    Returns:
        The directories written, and the file names that could not be recovered or lie
        outside the register.

    Raises:
        RecorderError: A harvested capture would replace a live capture directory.
    """
    known = v1_requests()
    groups: defaultdict[tuple[str, date], list[Capture]] = defaultdict(list)
    unrecoverable: list[str] = []
    out_of_register: list[str] = []
    for path in sorted(cache.glob("*.json")) if cache.is_dir() else []:
        request = known.get(path.stem)
        if request is None:
            unrecoverable.append(path.name)
            continue
        if request.source is None:
            out_of_register.append(path.name)
            continue
        entry = _cache_entry(path)
        if entry is None:
            unrecoverable.append(path.name)
            continue
        fetched_at, data = entry
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        capture = Capture(
            name=request.name,
            url=request.url,
            status=HTTP_OK,
            fetched_at=fetched_at,
            body=body,
            origin=ORIGIN_CACHE,
            notes=(
                "Re-serialized from version 1's cache entry (parsed JSON), not the bytes NOAA "
                "sent; fetched_at is the entry's timestamp."
            ),
            harvested_from=f"cache/{path.name}",
        )
        groups[(request.source, fetched_at.astimezone().date())].append(capture)
    directories: list[Path] = []
    for (source, day), captures in groups.items():
        existing = out / source / day.isoformat() / MANIFEST_NAME
        if existing.is_file() and f'"origin": "{ORIGIN_LIVE}"' in existing.read_text("utf-8"):
            message = f"{source}: a live capture of {day} exists; a cache harvest would replace it"
            raise RecorderError(message)
        directories.append(
            write_capture_directory(out, source, day, captures, recorded_at=recorded_at)
        )
    return CacheHarvest(directories, unrecoverable, out_of_register)


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(
        prog="record_fixtures.py",
        description="Record fixtures of the data-source register's required sources.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record", help="fetch sources live and store the responses")
    choice = record.add_mutually_exclusive_group(required=True)
    choice.add_argument("--all", action="store_true", help="record every source")
    choice.add_argument(
        "--source", nargs="+", metavar="ID", choices=sorted(SOURCES), help="register ids"
    )
    record.add_argument(
        "--date",
        type=date.fromisoformat,
        help="capture-directory date, YYYY-MM-DD (tests only; default: today, local time)",
    )
    harvest = commands.add_parser(
        "harvest-v1", help="extract the outlook maps of the 2025 reports and any restored cache"
    )
    harvest.add_argument("--reports", type=Path, default=DEFAULT_REPORTS, help="reports directory")
    harvest.add_argument("--cache", type=Path, default=DEFAULT_CACHE, help="version 1 cache")
    for command in (record, harvest):
        command.add_argument(
            "--out", type=Path, default=DEFAULT_OUT, help="recorded-fixtures directory"
        )
    return parser


def _command_record(args: argparse.Namespace) -> int:
    source_ids: list[str] = list(SOURCES) if args.all else args.source
    day: date = args.date or datetime.now(UTC).astimezone().date()
    out = cast("Path", args.out).resolve()
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        recorder = Recorder(Fetcher(client), load_landmarks())
        outcomes = record_sources(recorder, source_ids, out, day)
    for outcome in outcomes:
        if outcome.problem is None and outcome.directory is not None:
            print(
                f"{outcome.source}: {outcome.files} files, {outcome.stored_bytes} bytes stored "
                f"in {display_path(outcome.directory)}"
            )
        else:
            print(f"{outcome.source}: FAILED, {outcome.problem}", file=sys.stderr)
    failed = [outcome.source for outcome in outcomes if outcome.problem is not None]
    if failed:
        print(
            f"record_fixtures: {len(failed)} sources failed: {', '.join(failed)}", file=sys.stderr
        )
        return 1
    return 0


def _command_harvest(args: argparse.Namespace) -> int:
    out = cast("Path", args.out).resolve()
    recorded_at = datetime.now(UTC)
    try:
        maps = harvest_reports(cast("Path", args.reports).resolve(), out, recorded_at=recorded_at)
        cache = harvest_cache(cast("Path", args.cache).resolve(), out, recorded_at=recorded_at)
    except RecorderError as error:
        print(f"harvest-v1: {error}", file=sys.stderr)
        return 1
    print(f"harvest-v1: {len(maps)} outlook maps from the reports")
    for directory in maps:
        print(f"  {display_path(directory)}")
    print(f"harvest-v1: {len(cache.directories)} capture directories from the cache")
    for directory in cache.directories:
        print(f"  {display_path(directory)}")
    print(f"harvest-v1: {len(cache.out_of_register)} cache files outside the register")
    for name in cache.out_of_register:
        print(f"  {name}")
    print(f"harvest-v1: {len(cache.unrecoverable)} cache files could not be recovered")
    for name in cache.unrecoverable:
        print(f"  {name}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the recorder.

    Args:
        argv: Command-line arguments; ``sys.argv[1:]`` when None.

    Returns:
        The exit status: 0 success, 1 a failed source or harvest, 2 a usage error.
    """
    args = build_parser().parse_args(argv)
    if args.command == "record":
        return _command_record(args)
    return _command_harvest(args)


if __name__ == "__main__":
    raise SystemExit(main())
