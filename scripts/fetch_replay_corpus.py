# scripts/fetch_replay_corpus.py
"""Record, fetch, verify, and convert the public NHC historical replay corpus.

Normal fetches trust only the committed manifest. ``manifest`` is the explicit
trust-on-first-record operation: discover links from GIS listings, fetch bytes,
record hashes, then inspect those verified bytes. No archive is extracted.
GeoJSON-shaped output preserves the native geographic CRS; in particular D_Sphere
is NOT RFC 7946 WGS84. Consumers must read ``source_crs`` before using coordinates.
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
from dataclasses import asdict, dataclass, field
from datetime import date
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import NoReturn, cast
from urllib.parse import urljoin, urlsplit

import httpx
import shapefile  # pyright: ignore[reportMissingTypeStubs] - pyshp has inline types, no py.typed
from shapely.geometry import box, shape

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
    schema: int = 1
    user_agent: str = USER_AGENT
    coordinate_policy: str = COORDINATE_POLICY
    float_decimals: int = FLOAT_DECIMALS


def write_manifest(manifest: Manifest, path: Path) -> None:
    """Atomically write a sorted, platform-independent JSON manifest."""
    atomic_write(path, (json.dumps(asdict(manifest), sort_keys=True, indent=2) + "\n").encode())


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
    return Manifest(storms, files, subset, text_value(obj.get("subset_rule")))


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
    manifest = Manifest({}, [])
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


def build_subset(manifest: Manifest, cache: Path) -> tuple[dict[str, bytes], list[Output], str]:
    """Build all advisory products, falling back to the documented region only if needed."""
    bodies: dict[str, bytes] = {}
    outputs: list[Output] = []
    regional: set[tuple[str, str]] = set()
    region = box(-88, 20, -72, 31)
    for storm, info in manifest.storms.items():
        regional.update((storm, adv) for adv in (info.advisories[0], info.advisories[-1]))
    for entry in manifest.files:
        if entry.product != "5day":
            continue
        for member, product, collection in forecast_collections(entry, cache):
            name = f"{entry.storm}/{entry.advisories[0]}/{product}.geojson.gz"
            body = compressed_json(collection)
            bodies[name] = body
            outputs.append(
                Output(
                    name, entry.file, member, product, hashlib.sha256(body).hexdigest(), len(body)
                )
            )
            if product in {"cone", "watch-warning"}:
                for feature in as_list(collection["features"], "features"):
                    geometry = as_object(as_object(feature, "feature")["geometry"], "geometry")
                    if shape(geometry).intersects(region):
                        regional.add((entry.storm, entry.advisories[0]))
    rule = ALL_ADVISORIES
    if sum(map(len, bodies.values())) > MAX_SUBSET_BYTES:
        rule = REGION_RULE
        bodies = {
            name: body for name, body in bodies.items() if tuple(name.split("/")[:2]) in regional
        }
        outputs = [output for output in outputs if output.file in bodies]
    if sum(map(len, bodies.values())) > MAX_SUBSET_BYTES:
        fail("the documented regional subset still exceeds 10 MiB")
    return bodies, sorted(outputs, key=lambda output: output.file), rule


def convert(manifest: Manifest, cache: Path, out: Path) -> None:
    """Rebuild only the pinned subset; fail before writing on any provenance drift."""
    bodies, outputs, rule = build_subset(manifest, cache)
    if outputs != manifest.subset or rule != manifest.subset_rule:
        fail("conversion differs from the committed manifest; refresh deliberately")
    for name, body in bodies.items():
        atomic_write(safe_path(out, name), body)
    print(f"converted {len(bodies)} files, {sum(map(len, bodies.values()))} stored bytes")


def main(argv: Sequence[str] | None = None) -> int:
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
    args = parser.parse_args(argv)
    if args.reuse_downloads and args.command != "manifest":
        parser.error("--reuse-downloads is allowed only for explicit manifest recording")
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
                kept = {name.split("/")[1] for name in bodies if name.startswith(storm + "/")}
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
