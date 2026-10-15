# tests/scripts/test_fetch_replay_corpus.py
"""Offline tests of corpus trust boundaries, discovery, and conversion."""

import gzip
import hashlib
import io
import json
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, cast

import httpx
import pytest
import respx
import shapefile  # pyright: ignore[reportMissingTypeStubs] - inline types, no py.typed

import fetch_replay_corpus as corpus
from record_fixtures import Fetcher, Pacer, RecorderError, load_landmarks

if TYPE_CHECKING:
    from collections.abc import Callable

SPHERE = (
    'GEOGCS["GCS_Sphere",DATUM["D_Sphere",SPHEROID["Sphere",6371200.0,0.0]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)
SYNOPTIME = "2017083012"
FORECAST_PRODUCT_COUNT = 4
USAGE_ERROR = 2


def packed(members: dict[str, bytes]) -> bytes:
    """Build a small zip or KMZ in memory."""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return stream.getvalue()


def forecast_zip(*, adv: str = "1", radii: bool = False, longitude_offset: float = 0) -> bytes:
    """Build synthetic shapefiles around an allowlisted public landmark."""
    members: dict[str, bytes] = {}
    landmark = load_landmarks()[0]
    point = (float(landmark.lon) + longitude_offset, float(landmark.lat))
    products = (
        {"initialradii": shapefile.POINT}
        if radii
        else {
            "_5day_pgn": shapefile.POLYGON,
            "_5day_lin": shapefile.POLYLINE,
            "_5day_pts": shapefile.POINT,
            "_ww_wwlin": shapefile.POLYLINE,
        }
    )
    for product, kind in products.items():
        shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
        writer = shapefile.Writer(
            shp=cast("shapefile.WriteSeekableBinStream", shp),
            shx=cast("shapefile.WriteSeekableBinStream", shx),
            dbf=cast("shapefile.WriteSeekableBinStream", dbf),
            shapeType=kind,
        )
        # pyshp wraps field with a descriptor that loses its bound-method type.
        add_field = cast("Callable[[str, str], None]", writer.field)
        add_field("ADVISNUM", "C")
        if radii:
            add_field("SYNOPTIME", "C")
        if kind == shapefile.POINT:
            writer.point(*point)
        elif kind == shapefile.POLYLINE:
            writer.line([[point, (point[0] + 1, point[1] + 1)]])
        else:
            writer.poly(
                [
                    [
                        point,
                        (point[0], point[1] + 1),
                        (point[0] + 1, point[1] + 1),
                        (point[0] + 1, point[1]),
                        point,
                    ]
                ]
            )
        writer.record(*([adv, SYNOPTIME] if radii else [adv]))
        writer.close()
        stem = "synthetic" + product
        members.update(
            {
                stem + ".shp": shp.getvalue(),
                stem + ".shx": shx.getvalue(),
                stem + ".dbf": dbf.getvalue(),
                stem + ".prj": SPHERE.encode(),
            }
        )
    return packed(members)


def recorded(tmp_path: Path, body: bytes) -> corpus.Archive:
    """Stage bytes with their exact expected checksum."""
    entry = corpus.Archive(
        "AL112017/sample.zip",
        f"{corpus.GIS_ROOT}forecast/archive/sample.zip",
        len(body),
        hashlib.sha256(body).hexdigest(),
        "AL112017",
        ["001"],
        "5day",
    )
    corpus.atomic_write(tmp_path / entry.file, body)
    return entry


@pytest.mark.parametrize(
    "path", ["../outside", "/absolute", "a/../../b", "C:/outside", "a\\b", "a//b", "a/./b"]
)
def test_unsafe_paths_are_rejected(tmp_path: Path, path: str) -> None:
    with pytest.raises(RecorderError, match="unsafe"):
        corpus.safe_path(tmp_path, path)


@pytest.mark.parametrize(
    "url",
    [
        "http://www.nhc.noaa.gov/gis/forecast/archive/a.zip",
        "https://example.org/a.zip",
        "https://www.nhc.noaa.gov/gis/forecast/archive/../../a.zip",
        "https://www.nhc.noaa.gov/gis/forecast/archive/a.zip?token=x",
    ],
)
def test_downloads_cannot_escape_the_official_keyless_archive(url: str) -> None:
    with pytest.raises(RecorderError):
        corpus.official_url(url)


@pytest.mark.parametrize(
    "name", ["../outside.shp", "/outside.shp", "C:/outside.shp", "a\\outside.shp"]
)
def test_zip_and_kmz_traversal_are_rejected(name: str) -> None:
    # Windows zipfile normalizes backslashes while writing; plant the raw name
    # in both directory entries to test what a hostile external zip can contain.
    body = packed({name.replace("\\", "/"): b"x"})
    body = body.replace(name.replace("\\", "/").encode(), name.encode())
    with pytest.raises(RecorderError, match="unsafe"), corpus.archive_members(body):
        pytest.fail("unsafe archive was opened")


def test_zip_expansion_limit_is_checked_before_reading(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(corpus, "MAX_MEMBER_BYTES", 1)
    with (
        pytest.raises(RecorderError, match="limit"),
        corpus.archive_members(packed({"doc.kml": bytes(2)})),
    ):
        pytest.fail("oversized member was opened")


@pytest.mark.parametrize(
    "wkt",
    [
        SPHERE.replace("D_Sphere", "D_Unknown"),
        SPHERE.replace("6371200.0", "6371000.0"),
        SPHERE.replace("GEOGCS", "PROJCS"),
        "",
        SPHERE.replace("Greenwich", "Paris"),
    ],
)
def test_unsupported_crs_stops_conversion(wkt: str) -> None:
    with pytest.raises(RecorderError):
        corpus.geographic_crs(wkt)


def test_native_sphere_and_deterministic_gzip_are_preserved(tmp_path: Path) -> None:
    entry = recorded(tmp_path, forecast_zip())
    corpus.inspect_archive(entry, tmp_path)
    collections = corpus.forecast_collections(entry, tmp_path)
    assert len(collections) == FORECAST_PRODUCT_COUNT
    assert {crs.datum for crs in entry.prj.values()} == {"D_Sphere"}
    for _, _, collection in collections:
        assert collection["source_crs"] == {"datum": "D_Sphere", "wkt": SPHERE}
        first = corpus.compressed_json(collection)
        assert first == corpus.compressed_json(collection)
        assert first[4:8] == bytes(4)
        assert json.loads(gzip.decompress(first))["source_crs"]["datum"] == "D_Sphere"


def test_corrupt_archive_is_rejected_before_opening_zip(tmp_path: Path) -> None:
    entry = recorded(tmp_path, b"not even a zip")
    (tmp_path / entry.file).write_bytes(b"different bytes")
    with pytest.raises(RecorderError, match="checksum"):
        corpus.inspect_archive(entry, tmp_path)


def test_mismatched_advisory_is_not_silently_assigned(tmp_path: Path) -> None:
    entry = recorded(tmp_path, forecast_zip(adv="2"))
    corpus.inspect_archive(entry, tmp_path)
    with pytest.raises(RecorderError, match="advisory disagrees"):
        corpus.forecast_collections(entry, tmp_path)


def test_prj_drift_is_rejected_even_with_a_pinned_hash(tmp_path: Path) -> None:
    entry = recorded(tmp_path, forecast_zip())
    with pytest.raises(RecorderError, match="CRS differs"):
        corpus.forecast_collections(entry, tmp_path)


def test_fetch_checks_bytes_before_writing_and_reuses_cache(tmp_path: Path) -> None:
    body = packed({"doc.kml": b"<kml/>"})
    entry = recorded(tmp_path, body)
    (tmp_path / entry.file).unlink()
    manifest = corpus.Manifest({}, [entry])
    with respx.mock as router, httpx.Client() as client:
        request = router.get(entry.url).respond(200, content=body)
        fetcher = Fetcher(client, Pacer(default=0))
        corpus.fetch(manifest, tmp_path, fetcher)
        corpus.fetch(manifest, tmp_path, fetcher)
        assert request.call_count == 1
        assert request.calls.last.request.headers["User-Agent"] == corpus.USER_AGENT
        corpus.verify(manifest, tmp_path)
        bad = replace(entry, sha256="0" * 64, file="AL112017/bad.zip")
        with pytest.raises(RecorderError, match="checksum"):
            corpus.fetch(corpus.Manifest({}, [bad]), tmp_path, fetcher)
        assert not (tmp_path / bad.file).exists()


def test_fetch_refuses_corrupt_cache_and_verify_requires_every_file(tmp_path: Path) -> None:
    entry = recorded(tmp_path, b"one")
    (tmp_path / entry.file).write_bytes(b"two")
    with respx.mock, httpx.Client() as client, pytest.raises(RecorderError, match="checksum"):
        corpus.fetch(corpus.Manifest({}, [entry]), tmp_path, Fetcher(client))
    (tmp_path / entry.file).unlink()
    with pytest.raises(FileNotFoundError):
        corpus.verify(corpus.Manifest({}, [entry]), tmp_path)


def test_fixed_float_serialization_and_nonfinite_rejection() -> None:
    assert corpus.fixed_json({"z": 1 / 3, "a": [2.0]}) == '{"a":[2.0000000],"z":0.3333333}'
    with pytest.raises(RecorderError, match="non-finite"):
        corpus.fixed_json(float("nan"))


def test_single_vertex_warning_preserves_its_coordinate_and_original_geometry() -> None:
    landmark = load_landmarks()[0]
    point = (float(landmark.lon), float(landmark.lat))
    original: dict[str, object] = {"type": "LineString", "coordinates": [point]}
    feature = corpus.feature_geometry(original)
    assert feature["source_geometry"] == original
    assert feature["geometry"] == {"type": "Point", "coordinates": point}
    assert "no segment invented" in str(feature["geometry_note"])
    ordinary: dict[str, object] = {"type": "LineString", "coordinates": [point, point]}
    assert corpus.feature_geometry(ordinary) == {"geometry": ordinary}


@pytest.mark.parametrize(
    ("datum", "inverse"), [("D_WGS_1984", "298.257223563"), ("NAD83", "298.257222101")]
)
def test_supported_ellipsoidal_datums_are_checked(datum: str, inverse: str) -> None:
    wkt = SPHERE.replace("D_Sphere", datum).replace("6371200.0,0.0", f"6378137.0,{inverse}")
    assert corpus.geographic_crs(wkt).datum == datum
    with pytest.raises(RecorderError, match="spheroid"):
        corpus.geographic_crs(wkt.replace("6378137.0", "6378136.0"))


def test_reuse_recording_flag_cannot_change_a_pinned_fetch() -> None:
    with pytest.raises(SystemExit) as error:
        corpus.main(["fetch", "--reuse-downloads"])
    assert error.value.code == USAGE_ERROR  # argparse usage error


def test_discovery_matches_wsp_by_synoptic_time_and_converts(tmp_path: Path) -> None:
    with respx.mock as router, httpx.Client() as client:
        router.get(f"{corpus.GIS_ROOT}archive_toa_results.php").respond(200, text="")
        for storm in corpus.STORMS:
            year = storm[4:]
            urls = [
                f"{corpus.GIS_ROOT}forecast/archive/{storm.lower()}_{product}_001.zip"
                for product in ("5day", "fcst")
            ]
            router.get(
                f"{corpus.GIS_ROOT}archive_forecast_results.php?id={storm[:4].lower()}&year={year}"
            ).respond(200, text="".join(f'<a href="{url}">x</a>' for url in urls))
            for url in urls:
                router.get(url).respond(200, content=forecast_zip(radii="_fcst_" in url))
            wsp_urls = [
                f"{corpus.GIS_ROOT}forecast/archive/{SYNOPTIME}_{suffix}.zip"
                for suffix in ("wsp_120hr5km", "wsp_120hrhalfDeg")
            ]
            router.get(f"{corpus.GIS_ROOT}archive_wsp.php?year={year}").respond(
                200, text="".join(f'<a href="{url}">x</a>' for url in wsp_urls)
            )
            for url in wsp_urls:
                router.get(url).respond(200, content=forecast_zip(radii=True))
        manifest = corpus.discover(Fetcher(client, Pacer(default=0)), tmp_path)
    assert set(manifest.storms) == set(corpus.STORMS)
    assert len(manifest.files) == 4 * len(corpus.STORMS)
    assert all(info.synoptic_times == [SYNOPTIME] for info in manifest.storms.values())
    assert all(info.missing_arrival == ["001"] for info in manifest.storms.values())
    bodies, manifest.subset, manifest.subset_rule = corpus.build_subset(manifest, tmp_path)
    assert len(bodies) == 4 * len(corpus.STORMS)
    path = tmp_path / "manifest.json"
    corpus.write_manifest(manifest, path)
    assert corpus.load_manifest(path) == manifest
    out = tmp_path / "out"
    corpus.convert(manifest, tmp_path, out)
    assert {file.relative_to(out).as_posix() for file in out.rglob("*.gz")} == set(bodies)


def test_cli_missing_cache_fails_safely(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert corpus.main(["verify", "--manifest", str(tmp_path / "missing.json")]) == 1
    assert "FileNotFoundError" in capsys.readouterr().err


def test_region_fallback_keeps_first_and_last_and_explains_the_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entries: list[corpus.Archive] = []
    advisories = ["001", "002", "003"]
    for adv in advisories:
        body = forecast_zip(adv=str(int(adv)), longitude_offset=100)
        entry = replace(recorded(tmp_path, body), file=f"AL112017/{adv}.zip", advisories=[adv])
        corpus.atomic_write(tmp_path / entry.file, body)
        corpus.inspect_archive(entry, tmp_path)
        entries.append(entry)
    manifest = corpus.Manifest({"AL112017": corpus.Storm(advisories, [], [], [])}, entries)
    all_bodies, _, rule = corpus.build_subset(manifest, tmp_path)
    assert rule == corpus.ALL_ADVISORIES
    retained_bytes = sum(len(body) for name, body in all_bodies.items() if "/002/" not in name)
    monkeypatch.setattr(corpus, "MAX_SUBSET_BYTES", retained_bytes)
    bodies, _, rule = corpus.build_subset(manifest, tmp_path)
    assert rule == corpus.REGION_RULE
    assert {name.split("/")[1] for name in bodies} == {"001", "003"}
    monkeypatch.setattr(corpus, "MAX_SUBSET_BYTES", retained_bytes - 1)
    with pytest.raises(RecorderError, match="still exceeds"):
        corpus.build_subset(manifest, tmp_path)
