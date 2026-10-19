# scripts/fetch_replay_corpus.py
"""Record, fetch, verify, and convert the public NHC historical replay corpus.

Normal fetches trust only the committed manifest. ``manifest`` is the explicit
trust-on-first-record operation: discover links from GIS listings, fetch bytes,
record hashes, then inspect those verified bytes. No archive is extracted.
GeoJSON-shaped output preserves the native geographic CRS; in particular D_Sphere
is NOT RFC 7946 WGS84. Consumers must read ``source_crs`` before using coordinates.

``convert`` rebuilds the committed subset: every forecast product, plus each 5 km
wind-speed-probability product clipped to the landmark windows (one degree of latitude
and longitude on each side of each landmark in ``scripts/public_landmarks.toml``).
``convert --refresh-subset`` deliberately rewrites the manifest's ``subset`` and
``subset_rule`` from the verified cache; the originals' checksums never change.
``convert --full --out DIR`` writes a complete conversion (every forecast product, every
probability product unclipped, every arrival-time KMZ as received) with its own manifest
to a directory outside the checkout, for the operator's own locations.
"""

import argparse
import gzip
import hashlib
import io
import json
import math
import os
import re
import sys
import zipfile
from collections import defaultdict
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import NoReturn, cast
from urllib.parse import urljoin, urlsplit

import httpx
import shapefile  # pyright: ignore[reportMissingTypeStubs] - pyshp has inline types, no py.typed
import shapely
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, box, mapping, shape
from shapely.geometry.base import BaseGeometry

from check_personal_data import Landmark, load_landmarks
from record_fixtures import (
    NHC_ROOT,
    REPOSITORY_ROOT,
    REQUEST_TIMEOUT,
    USER_AGENT,
    Fetcher,
    Pacer,
    RecorderError,
    as_list,
    as_object,
    parse_json,
    stored_form,
)

DEFAULT_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "replay"
DEFAULT_MANIFEST = DEFAULT_ROOT / "corpus-manifest.json"
DEFAULT_CACHE = REPOSITORY_ROOT / ".cache" / "replay-corpus"
STORMS = ("AL112017", "AL052019", "AL092022", "AL142024")
GIS_ROOT = f"{NHC_ROOT}/gis/"
MAX_SUBSET_BYTES = 10 * 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_MEMBERS = 256
FLOAT_DECIMALS = 7
SPHERE_RADIUS = 6_371_200.0
FORECAST_PRODUCTS = {"_5day_pgn": "cone", "_5day_lin": "track", "_5day_pts": "points"}
COORDINATE_POLICY = (
    "Native geographic coordinates; no transformation or WGS84 relabeling. "
    "D_Sphere (radius 6371200 m) approved by the operator 2026-10-15. "
    "Read source_crs; D_Sphere output is not RFC 7946 WGS84."
)
ALL_ADVISORIES = "Every forecast advisory and every available forecast geometry product."
REGION_RULE = (
    "Keep advisories whose cone or watch-warning intersects 20N-31N, 88W-72W, "
    "plus each storm's first and last advisory."
)
WSP_ARCHIVE = "wsp_120hr5km"
WSP_THRESHOLDS = (34, 50, 64)
WINDOW_HALF_WIDTH_DEG = 1
WINDOW_RULE = (
    "Plus each 5 km wind-speed-probability product, clipped to the boxes reaching one degree "
    "of latitude and longitude on each side of each public landmark."
)
FULL_RULE = (
    "A complete conversion: every forecast product, every 5 km wind-speed-probability "
    "product unclipped, and every arrival-time KMZ as received."
)
MANIFEST_NAME = "corpus-manifest.json"


def subset_rule(forecast_rule: str) -> str:
    """Name the committed subset: its forecast rule, then the landmark windows."""
    return f"{forecast_rule} {WINDOW_RULE}"


def fail(message: str) -> NoReturn:
    """Raise a corpus error without printing archive content."""
    raise RecorderError(message)


def text_value(value: object) -> str:
    """Validate a JSON string."""
    if not isinstance(value, str):
        fail("manifest: expected a string")
    return value


def number_value(value: object) -> int:
    """Validate a nonnegative JSON integer."""
    if type(value) is not int or value < 0:
        fail("manifest: expected a nonnegative integer")
    return value


def strings(value: object) -> list[str]:
    """Validate a JSON array of strings."""
    return [text_value(item) for item in as_list(value, "manifest list")]


def safe_path(root: Path, name: str) -> Path:
    """Resolve a portable relative path, rejecting traversal and symlink escapes."""
    parts = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or ":" in name
        or parts.is_absolute()
        or any(part in {"..", ".", ""} for part in name.split("/"))
    ):
        fail("unsafe relative path")
    target = root.joinpath(*parts.parts)
    if not target.resolve().is_relative_to(root.resolve()):
        fail("path escapes its root")
    return target


def official_url(url: str) -> str:
    """Allow only keyless HTTPS archive downloads from the official NHC host."""
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.netloc != "www.nhc.noaa.gov"
        or parts.query
        or parts.fragment
        or not parts.path.startswith(("/gis/forecast/archive/", "/storm_graphics/api/"))
    ):
        fail("manifest contains a non-archive URL")
    safe_path(Path(), parts.path.lstrip("/"))
    return url


def advisory_key(advisory: str) -> tuple[int, str]:
    """Sort full and intermediate advisories in issuance order."""
    if not re.fullmatch(r"[0-9]{3}[A-Z]?", advisory):
        fail("invalid advisory identifier")
    return int(advisory[:3]), advisory[3:]


@dataclass(frozen=True)
class CRS:
    """A shapefile's original geographic datum and exact WKT."""

    datum: str
    wkt: str


def geographic_crs(wkt: str) -> CRS:
    """Validate the explicitly supported native geographic CRS definitions."""
    datum = re.search(r'DATUM\s*\[\s*"([^"]+)"', wkt, re.IGNORECASE)
    spheroid = re.search(
        r'SPHEROID\s*\[\s*"[^"]+"\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)', wkt, re.IGNORECASE
    )
    if (
        not wkt.lstrip().upper().startswith("GEOGCS[")
        or "PROJCS" in wkt.upper()
        or datum is None
        or not re.search(r'UNIT\s*\[\s*"Degree"\s*,\s*0\.0174532925199433', wkt, re.IGNORECASE)
        or not re.search(r'PRIMEM\s*\[\s*"Greenwich"\s*,\s*0(?:\.0)?\s*\]', wkt, re.IGNORECASE)
    ):
        fail("projected, missing, or unsupported geographic CRS; stop for operator review")
    name = datum[1]
    if name not in {"D_Sphere", "D_WGS_1984", "WGS_1984", "D_North_American_1983", "NAD83"}:
        fail("unsupported datum; stop for operator review")
    expected = (SPHERE_RADIUS, 0.0)
    if name in {"D_WGS_1984", "WGS_1984"}:
        expected = (6_378_137.0, 298.257223563)
    elif name in {"D_North_American_1983", "NAD83"}:
        expected = (6_378_137.0, 298.257222101)
    if spheroid is None or (float(spheroid[1]), float(spheroid[2])) != expected:
        fail("unsupported spheroid; stop for operator review")
    return CRS(name, wkt)


@dataclass
class Archive:
    """One downloaded file and its advisory associations (WSP is shared by time)."""

    file: str
    url: str
    bytes: int
    sha256: str
    storm: str
    advisories: list[str]
    product: str
    prj: dict[str, CRS] = field(default_factory=dict[str, CRS])
    synoptic_time: str | None = None


@dataclass(frozen=True)
class Output:
    """One compressed subset file traced to its original archive and member."""

    file: str
    source: str
    member: str
    product: str
    sha256: str
    bytes: int


@dataclass
class Storm:
    """Archive coverage, including unavailable products and deliberate subset gaps."""

    advisories: list[str]
    missing_fcst: list[str]
    missing_arrival: list[str]
    synoptic_times: list[str]
    omitted_advisories: list[str] = field(default_factory=list[str])


@dataclass
class Manifest:
    """Versioned corpus inventory, native CRS policy, and reproducible subset provenance."""

    storms: dict[str, Storm]
    files: list[Archive]
    subset: list[Output] = field(default_factory=list[Output])
    subset_rule: str = ALL_ADVISORIES
    recorded_on: str = ""
    schema: int = 1
    user_agent: str = USER_AGENT
    coordinate_policy: str = COORDINATE_POLICY
    float_decimals: int = FLOAT_DECIMALS


def write_manifest(manifest: Manifest, path: Path) -> None:
    """Atomically write a sorted, platform-independent JSON manifest."""
    atomic_write(path, (json.dumps(asdict(manifest), sort_keys=True, indent=2) + "\n").encode())


def recorded_day(obj: dict[str, object]) -> str:
    """Validate the day the originals were recorded, ``YYYY-MM-DD``."""
    recorded_on = text_value(obj.get("recorded_on"))
    try:
        date.fromisoformat(recorded_on)
    except ValueError:
        fail("manifest recorded_on is not a YYYY-MM-DD date")
    return recorded_on


def load_manifest(path: Path = DEFAULT_MANIFEST) -> Manifest:
    """Read and validate the trusted inventory before any network or filesystem use."""
    obj = as_object(parse_json(path.read_bytes(), "corpus manifest"), "corpus manifest")
    if (
        obj.get("schema") != 1
        or obj.get("user_agent") != USER_AGENT
        or obj.get("coordinate_policy") != COORDINATE_POLICY
        or obj.get("float_decimals") != FLOAT_DECIMALS
    ):
        fail("unsupported corpus manifest schema or coordinate policy")
    storms: dict[str, Storm] = {}
    for key, value in as_object(obj.get("storms"), "storms").items():
        info = as_object(value, "storm")
        storms[key] = Storm(
            strings(info.get("advisories")),
            strings(info.get("missing_fcst")),
            strings(info.get("missing_arrival")),
            strings(info.get("synoptic_times")),
            strings(info.get("omitted_advisories")),
        )
    if set(storms) != set(STORMS):
        fail("manifest must cover all four replay storms")
    files: list[Archive] = []
    for value in as_list(obj.get("files"), "files"):
        item = as_object(value, "archive")
        prj: dict[str, CRS] = {}
        for member, crs_value in as_object(item.get("prj"), "prj").items():
            crs = as_object(crs_value, "CRS")
            parsed = geographic_crs(text_value(crs.get("wkt")))
            if parsed.datum != crs.get("datum"):
                fail("manifest datum disagrees with WKT")
            safe_path(Path(), member)
            prj[member] = parsed
        entry = Archive(
            text_value(item.get("file")),
            official_url(text_value(item.get("url"))),
            number_value(item.get("bytes")),
            text_value(item.get("sha256")),
            text_value(item.get("storm")),
            strings(item.get("advisories")),
            text_value(item.get("product")),
            prj,
            None if item.get("synoptic_time") is None else text_value(item.get("synoptic_time")),
        )
        safe_path(DEFAULT_CACHE, entry.file)
        if (
            not re.fullmatch(r"[0-9a-f]{64}", entry.sha256)
            or entry.storm not in storms
            or not entry.advisories
            or not set(entry.advisories) <= set(storms[entry.storm].advisories)
            or entry.bytes > MAX_ARCHIVE_BYTES
        ):
            fail("invalid archive identity, checksum, size, or coverage")
        files.append(entry)
    subset: list[Output] = []
    for value in as_list(obj.get("subset"), "subset"):
        item = as_object(value, "subset file")
        output = Output(
            text_value(item.get("file")),
            text_value(item.get("source")),
            text_value(item.get("member")),
            text_value(item.get("product")),
            text_value(item.get("sha256")),
            number_value(item.get("bytes")),
        )
        safe_path(DEFAULT_ROOT, output.file)
        subset.append(output)
    names = [entry.file for entry in files]
    if not files or len(set(names)) != len(names):
        fail("empty inventory or duplicate cache filenames")
    return Manifest(storms, files, subset, text_value(obj.get("subset_rule")), recorded_day(obj))


def atomic_write(path: Path, body: bytes) -> None:
    """Write beside the destination, replacing it only once all bytes are written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    if partial.is_symlink():
        fail("refusing a symlink staging file")
    partial.write_bytes(body)
    partial.replace(path)


def checked_bytes(entry: Archive, body: bytes) -> bytes:
    """Fail on a size or checksum mismatch before any parsing."""
    if len(body) != entry.bytes or hashlib.sha256(body).hexdigest() != entry.sha256:
        fail(f"checksum or size mismatch: {entry.file}")
    return body


def read_verified(entry: Archive, cache: Path) -> bytes:
    """Read one cache file and verify it before returning it to a parser."""
    return checked_bytes(entry, safe_path(cache, entry.file).read_bytes())


@contextmanager
def archive_members(body: bytes) -> Generator[zipfile.ZipFile]:
    """Open a bounded archive in memory, rejecting traversal and ambiguous members."""
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if (
            len(infos) > MAX_MEMBERS
            or len(set(names)) != len(names)
            or sum(info.file_size for info in infos) > MAX_EXPANDED_BYTES
        ):
            fail("archive has duplicate members or exceeds expansion limits")
        for info in infos:
            safe_path(Path(), info.orig_filename.rstrip("/"))
            safe_path(Path(), info.filename.rstrip("/"))
            if info.file_size > MAX_MEMBER_BYTES or info.flag_bits & 1:
                fail("archive member exceeds limit or is encrypted")
        yield archive


@contextmanager
def shape_reader(archive: zipfile.ZipFile, member: str) -> Generator[shapefile.Reader]:
    """Read the verified shapefile triplet directly from in-memory zip members."""
    stem = member.removesuffix(".shp")
    reader = shapefile.Reader(
        shp=io.BytesIO(archive.read(member)),
        shx=io.BytesIO(archive.read(stem + ".shx")),
        dbf=io.BytesIO(archive.read(stem + ".dbf")),
        encoding="utf-8",
    )
    with reader:
        yield reader


def inspect_archive(entry: Archive, cache: Path) -> None:
    """Record every source .prj and the radii package's authoritative synoptic time."""
    with archive_members(read_verified(entry, cache)) as archive:
        for member in sorted(archive.namelist()):
            if member.endswith(".prj"):
                entry.prj[member] = geographic_crs(archive.read(member).decode("utf-8").strip())
            if entry.product == "fcst" and member.endswith("initialradii.shp"):
                with shape_reader(archive, member) as reader:
                    times = {
                        str(record.as_dict()["SYNOPTIME"])
                        for record in reader.records()
                        if record is not None
                    }
                if len(times) != 1 or not re.fullmatch(r"[0-9]{10}", next(iter(times), "")):
                    fail(f"missing or ambiguous SYNOPTIME: {entry.file}")
                entry.synoptic_time = next(iter(times))
        for member in archive.namelist():
            if member.endswith(".shp") and member[:-4] + ".prj" not in entry.prj:
                fail(f"shapefile lacks a CRS: {entry.file}")


class Listing(HTMLParser):
    """Collect only anchor hrefs; unrelated links never become download requests."""

    def __init__(self) -> None:
        """Start an empty link inventory."""
        super().__init__(convert_charrefs=True)
        self.links: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Collect a link from an anchor."""
        if tag == "a" and (href := dict(attrs).get("href")):
            self.links.add(href)


def listing_links(fetcher: Fetcher, url: str) -> set[str]:
    """Resolve the archive's listed links without guessing filenames."""
    parser = Listing()
    parser.feed(fetcher.get(url, source="nhc-gis-archive").body.decode("utf-8"))
    return {urljoin(url, link) for link in parser.links}


def record_archive(  # noqa: PLR0913 - explicit archive identity and recording dependencies
    fetcher: Fetcher,
    cache: Path,
    url: str,
    storm: str,
    advisories: list[str],
    *,
    product: str,
    reuse_downloads: bool = False,
) -> Archive:
    """Explicitly record one archive's bytes and then inspect the verified copy."""
    official_url(url)
    name = urlsplit(url).path.rsplit("/", 1)[-1]
    filename = f"{storm}/{name}"
    path = safe_path(cache, filename)
    body = (
        path.read_bytes()
        if reuse_downloads and path.is_file()
        else fetcher.get(url, source="nhc-gis-archive").body
    )
    if len(body) > MAX_ARCHIVE_BYTES:
        fail(f"archive exceeds download limit: {filename}")
    entry = Archive(
        filename, url, len(body), hashlib.sha256(body).hexdigest(), storm, advisories, product
    )
    atomic_write(safe_path(cache, filename), body)
    inspect_archive(entry, cache)
    print(f"recorded {filename}: {entry.bytes} bytes", flush=True)
    return entry


def discover(fetcher: Fetcher, cache: Path, *, reuse_downloads: bool = False) -> Manifest:  # noqa: C901 - explicit product discovery gates
    """Discover all forecast, shapefile WSP, and available KMZ arrival products."""
    manifest = Manifest({}, [], recorded_on=datetime.now(UTC).date().isoformat())
    # This results endpoint ignores its filters; fetch the complete list just once.
    arrival = listing_links(fetcher, f"{GIS_ROOT}archive_toa_results.php")
    for storm in STORMS:
        year = storm[4:]
        forecast = listing_links(
            fetcher, f"{GIS_ROOT}archive_forecast_results.php?id={storm[:4].lower()}&year={year}"
        )
        wsp = listing_links(fetcher, f"{GIS_ROOT}archive_wsp.php?year={year}")
        forecast_files: list[Archive] = []
        pattern = re.compile(rf"{storm.lower()}_(5day|fcst)_([0-9]{{3}}[A-Z]?)\.zip", re.IGNORECASE)
        wanted: list[tuple[str, str, str]] = []
        for url in forecast:
            match = pattern.fullmatch(url.rsplit("/", 1)[-1])
            if match:
                wanted.append((match[2].upper(), match[1].lower(), url))
        if not wanted or not any(product == "5day" for _, product, _ in wanted):
            fail(f"archive listing has no forecast packages for {storm}")
        for adv, product, url in sorted(wanted, key=lambda x: (advisory_key(x[0]), x[1])):
            forecast_files.append(
                record_archive(
                    fetcher,
                    cache,
                    url,
                    storm,
                    [adv],
                    product=product,
                    reuse_downloads=reuse_downloads,
                )
            )
        manifest.files.extend(forecast_files)
        advisories = [entry.advisories[0] for entry in forecast_files if entry.product == "5day"]
        synoptic: defaultdict[str, list[str]] = defaultdict(list)
        for entry in forecast_files:
            if entry.synoptic_time is not None:
                synoptic[entry.synoptic_time].extend(entry.advisories)
        for moment, associated in sorted(synoptic.items()):
            for suffix in ("wsp_120hr5km.zip", "wsp_120hrhalfDeg.zip"):
                matches = sorted(url for url in wsp if url.endswith(f"/{moment}_{suffix}"))
                if len(matches) != 1:
                    fail(f"missing or ambiguous WSP {moment} {suffix} for {storm}")
                entry = record_archive(
                    fetcher,
                    cache,
                    matches[0],
                    storm,
                    associated,
                    product=suffix[:-4],
                    reuse_downloads=reuse_downloads,
                )
                entry.synoptic_time = moment
                manifest.files.append(entry)
        arrival_advisories: set[str] = set()
        for url in sorted(arrival):
            match = re.fullmatch(
                rf"{storm}_([0-9]{{3}})adv_(earliest_reasonable|most_likely)_toa_34\.kmz",
                url.rsplit("/", 1)[-1],
            )
            if match and match[1] in advisories:
                manifest.files.append(
                    record_archive(
                        fetcher,
                        cache,
                        url,
                        storm,
                        [match[1]],
                        product=f"toa_{match[2]}",
                        reuse_downloads=reuse_downloads,
                    )
                )
                arrival_advisories.add(match[1])
        fcst_advisories = {
            entry.advisories[0] for entry in forecast_files if entry.product == "fcst"
        }
        manifest.storms[storm] = Storm(
            advisories,
            sorted(set(advisories) - fcst_advisories, key=advisory_key),
            sorted(set(advisories) - arrival_advisories, key=advisory_key),
            sorted(synoptic),
        )
    manifest.files.sort(key=lambda entry: entry.file)
    return manifest


def fetch(manifest: Manifest, cache: Path, fetcher: Fetcher) -> None:
    """Download missing entries; fail closed on any corrupt existing or fetched file."""
    for entry in manifest.files:
        path = safe_path(cache, entry.file)
        if path.exists():
            read_verified(entry, cache)
            continue
        body = checked_bytes(entry, fetcher.get(entry.url, source="nhc-gis-archive").body)
        atomic_write(path, body)
        print(f"fetched {entry.file}", flush=True)


def verify(manifest: Manifest, cache: Path) -> None:
    """Verify every inventory entry without parsing archive content or using the network."""
    for entry in manifest.files:
        read_verified(entry, cache)
    total = sum(entry.bytes for entry in manifest.files)
    print(f"verified {len(manifest.files)} files, {total} bytes")


def fixed_json(value: object) -> str:
    """Serialize sorted JSON with fixed seven-decimal finite floats and LF endings."""
    if isinstance(value, float):
        if not math.isfinite(value):
            fail("non-finite number in archive")
        return f"{value:.{FLOAT_DECIMALS}f}"
    if isinstance(value, dict):
        obj = cast("dict[str, object]", value)
        return "{" + ",".join(json.dumps(k) + ":" + fixed_json(obj[k]) for k in sorted(obj)) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(fixed_json(item) for item in cast("Sequence[object]", value)) + "]"
    if isinstance(value, date):
        return json.dumps(value.isoformat())
    return json.dumps(value, ensure_ascii=True, allow_nan=False)


def compressed_json(value: object) -> bytes:
    """Use the recorder's gzip policy where applicable; always compress the replay subset."""
    raw = (fixed_json(value) + "\n").encode("utf-8")
    _, body, form = stored_form("product.geojson", raw)
    return body if form == "gzip" else gzip.compress(raw, compresslevel=9, mtime=0)


def feature_geometry(geometry: dict[str, object]) -> dict[str, object]:
    """Keep a singleton source line as a point, retaining its original geometry."""
    if geometry.get("type") != "LineString":
        return {"geometry": geometry}
    coordinates = as_list(geometry.get("coordinates"), "geometry coordinates")
    if len(coordinates) == 1:
        return {
            "geometry": {"type": "Point", "coordinates": coordinates[0]},
            "source_geometry": geometry,
            "geometry_note": (
                "Source watch-warning line has one vertex; represented as a Point, "
                "no segment invented."
            ),
        }
    return {"geometry": geometry}


def forecast_collections(entry: Archive, cache: Path) -> list[tuple[str, str, dict[str, object]]]:
    """Convert available forecast shapefiles with attributes and native CRS provenance."""
    result: list[tuple[str, str, dict[str, object]]] = []
    with archive_members(read_verified(entry, cache)) as archive:
        for member in sorted(archive.namelist()):
            if not member.endswith(".shp"):
                continue
            stem = member.removesuffix(".shp")
            product = next((v for k, v in FORECAST_PRODUCTS.items() if stem.endswith(k)), None)
            if stem.endswith("_ww_wwlin"):
                product = "watch-warning"
            if product is None:
                fail(f"unknown forecast shapefile: {entry.file} / {member}")
            prj_member = stem + ".prj"
            crs = geographic_crs(archive.read(prj_member).decode("utf-8").strip())
            if entry.prj.get(prj_member) != crs:
                fail(f"CRS differs from manifest: {entry.file}")
            features: list[dict[str, object]] = []
            with shape_reader(archive, member) as reader:
                for item in reader.iterShapeRecords():
                    if item.record is None or item.shape is None:
                        fail(f"missing shape or record: {entry.file}")
                    properties = as_object(item.record.as_dict(), "shapefile attributes")
                    advisory = str(properties.get("ADVISNUM", "")).upper().lstrip("0")
                    if advisory != entry.advisories[0].lstrip("0"):
                        fail(f"feature advisory disagrees with archive: {entry.file}")
                    geometry = as_object(item.shape.__geo_interface__, "shapefile geometry")
                    features.append(
                        {"type": "Feature", "properties": properties, **feature_geometry(geometry)}
                    )
            result.append(
                (
                    member,
                    product,
                    {
                        "type": "FeatureCollection",
                        "features": features,
                        "source_crs": asdict(crs),
                        "storm": entry.storm,
                        "advisory": entry.advisories[0],
                        "source": entry.file,
                    },
                )
            )
    if not {"cone", "track", "points"} <= {product for _, product, _ in result}:
        fail(f"forecast package lacks cone, track, or points: {entry.file}")
    return result


def window_boxes(landmarks: Sequence[Landmark]) -> list[tuple[float, float, float, float]]:
    """Each landmark's window: the box one degree of latitude and longitude on each side."""
    half = Decimal(WINDOW_HALF_WIDTH_DEG)
    return [
        (
            float(landmark.lon - half),
            float(landmark.lat - half),
            float(landmark.lon + half),
            float(landmark.lat + half),
        )
        for landmark in landmarks
    ]


def window_member(landmarks: Sequence[Landmark]) -> dict[str, object]:
    """Describe the windows a windowed collection covers: the landmarks, width, and boxes."""
    covered = shapely.normalize(MultiPolygon([box(*bounds) for bounds in window_boxes(landmarks)]))
    if not covered.is_valid:
        fail("the landmark windows overlap; they cannot form one coverage")
    return {
        "landmarks": [landmark.key for landmark in landmarks],
        "half_width_deg": float(WINDOW_HALF_WIDTH_DEG),
        "geometry": as_object(mapping(covered), "window geometry"),
    }


def polygons(geometry: BaseGeometry) -> list[Polygon]:
    """Return a shape's non-empty polygons, from a collection's areal parts too."""
    if isinstance(geometry, Polygon):
        return [] if geometry.is_empty else [geometry]
    if isinstance(geometry, MultiPolygon):
        return [part for part in geometry.geoms if not part.is_empty]
    if isinstance(geometry, GeometryCollection):
        collection = cast("GeometryCollection[BaseGeometry]", geometry)
        return [part for item in collection.geoms for part in polygons(item)]
    return []


def validity_reason(geometry: BaseGeometry) -> str:
    """Shapely's reason a shape is invalid, without its bracketed location (a coordinate)."""
    return str(shapely.is_valid_reason(geometry)).split("[", 1)[0].strip()


def clip_band(
    band: BaseGeometry, boxes: Sequence[tuple[float, float, float, float]]
) -> tuple[MultiPolygon | None, str | None]:
    """Clip one probability band to the windows; ``None`` when nothing of it is inside.

    A band Shapely finds invalid is made valid before clipping, and the note records the
    original reason. ``clip_by_rect`` can turn such a band's touching parts into one
    self-touching ring; that clipped part is made valid again, which equals the exact
    intersection.
    """
    note = None
    if not band.is_valid:
        note = f"Source band invalid ({validity_reason(band)}); made valid before clipping."
        band = shapely.make_valid(band)
    parts: list[Polygon] = []
    for bounds in boxes:
        for piece in polygons(shapely.clip_by_rect(band, *bounds)):
            if piece.is_valid:
                parts.append(piece)
                continue
            parts.extend(polygons(shapely.make_valid(piece)))
            note = f"{note or ''} A clipped part was made valid again.".strip()
    if not parts:
        return None, None
    clipped = shapely.normalize(MultiPolygon(parts))
    rounded = shape(json.loads(fixed_json(mapping(clipped))))
    if not clipped.is_valid or not rounded.is_valid:
        fail("a clipped probability band is not valid")
    return clipped, note


WRAP_NOTE = (
    "Longitudes west of -180 degrees brought into [-180, 180] by adding 360 degrees: "
    "the same points, otherwise as received."
)


def wrapped(value: object) -> tuple[object, bool]:
    """Bring each longitude outside [-180, 180] into it by a whole turn; say if any moved.

    The 5 km probability grid runs west past the antimeridian (to -260 degrees). A turn of
    360 degrees names the same point on the same sphere, so nothing is transformed or
    relabeled; a ring that crosses the antimeridian then steps more than 180 degrees,
    which the engine unwraps.
    """
    if isinstance(value, list | tuple):
        items = cast("Sequence[object]", value)
        if len(items) >= 2 and all(isinstance(n, int | float) for n in items):  # noqa: PLR2004 - a position
            longitude = cast("float", items[0])
            turn = 360.0 if longitude < -180.0 else -360.0 if longitude > 180.0 else 0.0  # noqa: PLR2004 - the antimeridian
            return (longitude + turn, *items[1:]), turn != 0.0
        parts = [wrapped(item) for item in items]
        return [part for part, _ in parts], any(moved for _, moved in parts)
    return value, False


def band_feature(
    properties: dict[str, object],
    geometry: dict[str, object],
    boxes: Sequence[tuple[float, float, float, float]] | None,
) -> dict[str, object] | None:
    """One probability band as a feature: whole (no ``boxes``) or clipped to the windows."""
    note: str | None
    if boxes is None:
        coordinates, moved = wrapped(geometry["coordinates"])
        geometry = {**geometry, "coordinates": coordinates}
        note = WRAP_NOTE if moved else None
    else:
        clipped, note = clip_band(shape(geometry), boxes)
        if clipped is None:
            return None
        geometry = as_object(mapping(clipped), "clipped geometry")
    feature: dict[str, object] = {"type": "Feature", "properties": properties, "geometry": geometry}
    if note is not None:
        feature["geometry_note"] = note
    return feature


def wsp_collections(
    entry: Archive, cache: Path, window: dict[str, object] | None
) -> list[tuple[str, str, dict[str, object]]]:
    """Convert a 5 km probability archive: one collection per threshold, windowed or full.

    A record with a NULL shape is a band with no area, and is omitted. A full product keeps
    every other band as received, its longitudes brought into [-180, 180]; a windowed one
    clips each band to the windows.
    """
    if entry.product != WSP_ARCHIVE or entry.synoptic_time is None:
        fail(f"not a 5 km wind-speed-probability archive: {entry.file}")
    boxes = window_boxes(load_landmarks()) if window is not None else None
    result: list[tuple[str, str, dict[str, object]]] = []
    with archive_members(read_verified(entry, cache)) as archive:
        for threshold in WSP_THRESHOLDS:
            stem = f"{entry.synoptic_time}_wsp{threshold}knt120hr_5km"
            crs = geographic_crs(archive.read(stem + ".prj").decode("utf-8").strip())
            if entry.prj.get(stem + ".prj") != crs:
                fail(f"CRS differs from manifest: {entry.file}")
            features: list[dict[str, object]] = []
            with shape_reader(archive, stem + ".shp") as reader:
                for item in reader.iterShapeRecords():
                    if item.record is None or item.shape is None:
                        fail(f"missing shape or record: {entry.file}")
                    if item.shape.shapeType == shapefile.NULL:
                        continue
                    feature = band_feature(
                        as_object(item.record.as_dict(), "shapefile attributes"),
                        as_object(item.shape.__geo_interface__, "shapefile geometry"),
                        boxes,
                    )
                    if feature is not None:
                        features.append(feature)
            result.append(
                (
                    stem + ".shp",
                    f"wsp-{threshold}kt",
                    {
                        "type": "FeatureCollection",
                        "features": features,
                        "source_crs": asdict(crs),
                        "storm": entry.storm,
                        "synoptic_time": entry.synoptic_time,
                        "source": entry.file,
                        "threshold_kt": threshold,
                        "window": window,
                    },
                )
            )
    return result


def wsp_name(entry: Archive, product: str) -> str:
    """Where a probability collection lives: ``<storm>/wsp/<YYYYMMDDHH>/<product>``."""
    return f"{entry.storm}/wsp/{entry.synoptic_time}/{product}.geojson.gz"


def _output(name: str, entry: Archive, member: str, product: str, body: bytes) -> Output:
    return Output(name, entry.file, member, product, hashlib.sha256(body).hexdigest(), len(body))


def forecast_outputs(manifest: Manifest, cache: Path) -> tuple[dict[str, bytes], list[Output]]:
    """Convert every forecast package's products."""
    bodies: dict[str, bytes] = {}
    outputs: list[Output] = []
    for entry in manifest.files:
        if entry.product != "5day":
            continue
        for member, product, collection in forecast_collections(entry, cache):
            name = f"{entry.storm}/{entry.advisories[0]}/{product}.geojson.gz"
            bodies[name] = compressed_json(collection)
            outputs.append(_output(name, entry, member, product, bodies[name]))
    return bodies, outputs


def wsp_outputs(
    manifest: Manifest, cache: Path, window: dict[str, object] | None
) -> tuple[dict[str, bytes], list[Output]]:
    """Convert every 5 km probability archive, windowed or full."""
    bodies: dict[str, bytes] = {}
    outputs: list[Output] = []
    for entry in manifest.files:
        if entry.product != WSP_ARCHIVE:
            continue
        for member, product, collection in wsp_collections(entry, cache, window):
            name = wsp_name(entry, product)
            bodies[name] = compressed_json(collection)
            outputs.append(_output(name, entry, member, product, bodies[name]))
    return bodies, outputs


def regional_advisories(manifest: Manifest, bodies: dict[str, bytes]) -> set[tuple[str, str]]:
    """The advisories the regional fallback keeps: in the region, or first or last."""
    regional: set[tuple[str, str]] = set()
    region = box(-88, 20, -72, 31)
    for storm, info in manifest.storms.items():
        regional.update((storm, adv) for adv in (info.advisories[0], info.advisories[-1]))
    for name, body in bodies.items():
        storm, advisory, file = name.split("/")
        if file not in {"cone.geojson.gz", "watch-warning.geojson.gz"}:
            continue
        collection = as_object(json.loads(gzip.decompress(body)), name)
        for feature in as_list(collection["features"], "features"):
            geometry = as_object(as_object(feature, "feature")["geometry"], "geometry")
            if shape(geometry).intersects(region):
                regional.add((storm, advisory))
    return regional


def build_subset(manifest: Manifest, cache: Path) -> tuple[dict[str, bytes], list[Output], str]:
    """Build every forecast product and window, falling back to the documented region."""
    bodies, outputs = forecast_outputs(manifest, cache)
    windows, window_files = wsp_outputs(manifest, cache, window_member(load_landmarks()))
    window_bytes = sum(map(len, windows.values()))
    rule = ALL_ADVISORIES
    if sum(map(len, bodies.values())) + window_bytes > MAX_SUBSET_BYTES:
        rule = REGION_RULE
        regional = regional_advisories(manifest, bodies)
        bodies = {
            name: body for name, body in bodies.items() if tuple(name.split("/")[:2]) in regional
        }
        outputs = [output for output in outputs if output.file in bodies]
    if sum(map(len, bodies.values())) + window_bytes > MAX_SUBSET_BYTES:
        fail("the documented regional subset still exceeds 10 MiB")
    combined = sorted([*outputs, *window_files], key=lambda output: output.file)
    return {**bodies, **windows}, combined, subset_rule(rule)


def kept_advisories(bodies: dict[str, bytes], storm: str) -> set[str]:
    """The advisories a subset keeps forecast products of."""
    return {
        name.split("/")[1]
        for name in bodies
        if name.startswith(storm + "/") and name.split("/")[1] != "wsp"
    }


def convert(manifest: Manifest, cache: Path, out: Path) -> None:
    """Rebuild only the pinned subset; fail before writing on any provenance drift."""
    bodies, outputs, rule = build_subset(manifest, cache)
    if outputs != manifest.subset or rule != manifest.subset_rule:
        fail("conversion differs from the committed manifest; refresh deliberately")
    for name, body in bodies.items():
        atomic_write(safe_path(out, name), body)
    print(f"converted {len(bodies)} files, {sum(map(len, bodies.values()))} stored bytes")


def refresh_subset(manifest: Manifest, cache: Path, manifest_path: Path, out: Path) -> None:
    """Deliberately rewrite the manifest's subset and rule from the verified cache.

    The originals, their checksums, the storms, and the recording date stay as recorded;
    a refresh that would omit other advisories needs a new recording instead.
    """
    bodies, outputs, rule = build_subset(manifest, cache)
    for storm, info in manifest.storms.items():
        omitted = [adv for adv in info.advisories if adv not in kept_advisories(bodies, storm)]
        if omitted != info.omitted_advisories:
            fail("a refreshed subset would omit other advisories; record a new manifest")
    for name, body in bodies.items():
        atomic_write(safe_path(out, name), body)
    write_manifest(replace(manifest, subset=outputs, subset_rule=rule), manifest_path)
    print(f"refreshed the subset: {len(outputs)} files; review the manifest diff")


def build_full(manifest: Manifest, cache: Path) -> tuple[dict[str, bytes], list[Output]]:
    """Convert everything: forecast products, unclipped probabilities, and arrival KMZ."""
    bodies, outputs = forecast_outputs(manifest, cache)
    probabilities, probability_files = wsp_outputs(manifest, cache, None)
    bodies.update(probabilities)
    outputs.extend(probability_files)
    for entry in manifest.files:
        if not entry.product.startswith("toa_"):
            continue
        member = entry.file.rsplit("/", 1)[-1]
        name = f"{entry.storm}/toa/{member}"
        bodies[name] = read_verified(entry, cache)
        outputs.append(_output(name, entry, member, entry.product, bodies[name]))
    return bodies, sorted(outputs, key=lambda output: output.file)


def convert_full(manifest: Manifest, cache: Path, out: Path) -> None:
    """Write a complete conversion and its own manifest to a directory outside the checkout."""
    if out.resolve().is_relative_to(REPOSITORY_ROOT.resolve()):
        fail("--full writes outside the checkout; pass --out with a directory elsewhere")
    bodies, outputs = build_full(manifest, cache)
    storms = {key: replace(info, omitted_advisories=[]) for key, info in manifest.storms.items()}
    full = replace(manifest, storms=storms, subset=outputs, subset_rule=FULL_RULE)
    for name, body in bodies.items():
        atomic_write(safe_path(out, name), body)
    write_manifest(full, out / MANIFEST_NAME)
    print(f"converted {len(bodies)} files, {sum(map(len, bodies.values()))} bytes, to {out}")


def main(argv: Sequence[str] | None = None) -> int:  # noqa: C901 - one branch per command
    """Run a corpus command, returning nonzero on download, verification, or parse failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("fetch", "verify", "convert", "manifest"))
    parser.add_argument(
        "--cache", type=Path, default=Path(os.environ.get("WEATHERBOT_CORPUS_CACHE", DEFAULT_CACHE))
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_ROOT)
    parser.add_argument(
        "--reuse-downloads",
        action="store_true",
        help="manifest only: resume explicit trust-on-first-record from retained downloads",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="convert only: write a complete conversion and its manifest to --out, "
        "a directory outside the checkout",
    )
    parser.add_argument(
        "--refresh-subset",
        action="store_true",
        help="convert only: deliberately rewrite the manifest's subset from the verified "
        "cache; review the diff",
    )
    args = parser.parse_args(argv)
    if args.reuse_downloads and args.command != "manifest":
        parser.error("--reuse-downloads is allowed only for explicit manifest recording")
    if (args.full or args.refresh_subset) and args.command != "convert":
        parser.error("--full and --refresh-subset are options of convert")
    if args.full and args.refresh_subset:
        parser.error("--full and --refresh-subset do not combine")
    cache = cast("Path", args.cache).resolve()
    manifest_path = cast("Path", args.manifest).resolve()
    out = cast("Path", args.out).resolve()
    try:
        if args.command == "manifest":
            with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
                manifest = discover(
                    Fetcher(client, Pacer()), cache, reuse_downloads=bool(args.reuse_downloads)
                )
            bodies, manifest.subset, manifest.subset_rule = build_subset(manifest, cache)
            for storm, info in manifest.storms.items():
                kept = kept_advisories(bodies, storm)
                info.omitted_advisories = [adv for adv in info.advisories if adv not in kept]
            write_manifest(manifest, manifest_path)
            print(f"recorded manifest: {len(manifest.files)} archives; run verify then convert")
        else:
            manifest = load_manifest(manifest_path)
            if args.command == "fetch":
                with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
                    fetch(manifest, cache, Fetcher(client, Pacer()))
            elif args.command == "verify":
                verify(manifest, cache)
            elif args.full:
                convert_full(manifest, cache, out)
            elif args.refresh_subset:
                refresh_subset(manifest, cache, manifest_path, out)
            else:
                convert(manifest, cache, out)
    except (
        RecorderError,
        OSError,
        ValueError,
        KeyError,
        zipfile.BadZipFile,
        shapefile.ShapefileException,
    ) as error:
        # Archive/DBF parser exceptions can include untrusted content; print only our
        # own sanitized messages, otherwise the exception's class.
        detail = str(error) if isinstance(error, RecorderError) else type(error).__name__
        print(f"corpus: FAILED: {detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
