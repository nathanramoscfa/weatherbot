# tests/scripts/test_fetch_replay_corpus.py
"""Offline tests of corpus trust boundaries, discovery, and conversion."""

import gzip
import hashlib
import io
import json
import zipfile
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, cast

import httpx
import pytest
import respx
import shapefile  # pyright: ignore[reportMissingTypeStubs] - inline types, no py.typed
from shapely.geometry import MultiPolygon, Polygon, box, shape

import fetch_replay_corpus as corpus
from record_fixtures import Fetcher, Pacer, RecorderError, load_landmarks

type Json = dict[str, object]

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


def _square(lon: float, lat: float, half: float) -> list[tuple[float, float]]:
    return [
        (lon - half, lat - half),
        (lon - half, lat + half),
        (lon + half, lat + half),
        (lon + half, lat - half),
        (lon - half, lat - half),
    ]


def wsp_zip(moment: str = SYNOPTIME) -> bytes:
    """Build synthetic 5 km probability shapefiles around the first public landmark.

    34 kt: a band inside the landmark's window, a self-intersecting (bowtie) band inside
    it, a band far outside every window, and a NULL record. 50 kt: only a band far
    outside. 64 kt: a band that runs west past -180 degrees.
    """
    landmark = load_landmarks()[0]
    lon, lat = float(landmark.lon), float(landmark.lat)
    bowtie = [(lon - 0.4, lat - 0.4), (lon + 0.4, lat + 0.4), (lon + 0.4, lat - 0.4)]
    bowtie += [(lon - 0.4, lat + 0.4), (lon - 0.4, lat - 0.4)]
    bands: dict[int, list[tuple[str, list[tuple[float, float]] | None]]] = {
        34: [
            ("5-10%", _square(lon, lat, 0.5)),
            ("<5%", bowtie),
            ("10-20%", _square(lon + 20, lat, 0.5)),
            ("20-30%", None),
        ],
        50: [("5-10%", _square(lon + 20, lat, 0.5))],
        64: [("5-10%", _square(lon - 100, lat, 5))],
    }
    members: dict[str, bytes] = {}
    for threshold, records in bands.items():
        shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
        writer = shapefile.Writer(
            shp=cast("shapefile.WriteSeekableBinStream", shp),
            shx=cast("shapefile.WriteSeekableBinStream", shx),
            dbf=cast("shapefile.WriteSeekableBinStream", dbf),
            shapeType=shapefile.POLYGON,
        )
        add_field = cast("Callable[[str, str], None]", writer.field)
        add_field("PERCENTAGE", "C")
        for label, ring in records:
            if ring is None:
                writer.null()
            else:
                writer.poly(cast("list[shapefile.PointsT]", [ring]))
            writer.record(label)
        writer.close()
        stem = f"{moment}_wsp{threshold}knt120hr_5km"
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
            router.get(wsp_urls[0]).respond(200, content=wsp_zip())
            router.get(wsp_urls[1]).respond(200, content=forecast_zip(radii=True))
        manifest = corpus.discover(Fetcher(client, Pacer(default=0)), tmp_path)
    assert set(manifest.storms) == set(corpus.STORMS)
    assert len(manifest.files) == 4 * len(corpus.STORMS)
    assert all(info.synoptic_times == [SYNOPTIME] for info in manifest.storms.values())
    assert all(info.missing_arrival == ["001"] for info in manifest.storms.values())
    bodies, manifest.subset, manifest.subset_rule = corpus.build_subset(manifest, tmp_path)
    assert len(bodies) == (FORECAST_PRODUCT_COUNT + len(corpus.WSP_THRESHOLDS)) * len(corpus.STORMS)
    assert manifest.subset_rule == corpus.subset_rule(corpus.ALL_ADVISORIES)
    assert manifest.recorded_on
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
    assert rule == corpus.subset_rule(corpus.ALL_ADVISORIES)
    retained_bytes = sum(len(body) for name, body in all_bodies.items() if "/002/" not in name)
    monkeypatch.setattr(corpus, "MAX_SUBSET_BYTES", retained_bytes)
    bodies, _, rule = corpus.build_subset(manifest, tmp_path)
    assert rule == corpus.subset_rule(corpus.REGION_RULE)
    assert {name.split("/")[1] for name in bodies} == {"001", "003"}
    monkeypatch.setattr(corpus, "MAX_SUBSET_BYTES", retained_bytes - 1)
    with pytest.raises(RecorderError, match="still exceeds"):
        corpus.build_subset(manifest, tmp_path)


# Landmark windows, the full conversion, and the deliberate refresh


def recorded_wsp(tmp_path: Path) -> corpus.Archive:
    """Stage the synthetic 5 km probability archive as a manifest entry would pin it."""
    body = wsp_zip()
    entry = replace(
        recorded(tmp_path, body),
        file=f"AL112017/{SYNOPTIME}_wsp_120hr5km.zip",
        product=corpus.WSP_ARCHIVE,
        synoptic_time=SYNOPTIME,
    )
    corpus.atomic_write(tmp_path / entry.file, body)
    corpus.inspect_archive(entry, tmp_path)
    return entry


def collections_of(entry: corpus.Archive, tmp_path: Path, *, windowed: bool) -> dict[str, Json]:
    """Each threshold's converted collection, by product."""
    window = corpus.window_member(load_landmarks()) if windowed else None
    return {
        product: collection
        for _, product, collection in corpus.wsp_collections(entry, tmp_path, window)
    }


def features_of(collection: Json) -> list[Json]:
    """A collection's features."""
    return cast("list[Json]", collection["features"])


def labels_of(collection: Json) -> list[object]:
    """A collection's band labels, in order."""
    return [
        cast("Json", feature["properties"])["PERCENTAGE"] for feature in features_of(collection)
    ]


def test_each_band_is_clipped_to_the_landmark_windows(tmp_path: Path) -> None:
    collections = collections_of(recorded_wsp(tmp_path), tmp_path, windowed=True)
    boxes = MultiPolygon([box(*bounds) for bounds in corpus.window_boxes(load_landmarks())])

    assert set(collections) == {"wsp-34kt", "wsp-50kt", "wsp-64kt"}
    assert labels_of(collections["wsp-34kt"]) == ["5-10%", "<5%"]
    inside = features_of(collections["wsp-34kt"])
    for feature in inside:
        band = shape(cast("Json", feature["geometry"]))
        assert band.is_valid
        assert boxes.covers(band)
    assert "geometry_note" not in inside[0]
    note = str(inside[1]["geometry_note"])
    assert note.startswith("Source band invalid (")
    assert "[" not in note
    assert features_of(collections["wsp-50kt"]) == []
    assert features_of(collections["wsp-64kt"]) == []
    window = cast("Json", collections["wsp-50kt"]["window"])
    assert window["landmarks"] == [landmark.key for landmark in load_landmarks()]
    assert shape(cast("Json", window["geometry"])).equals(boxes)
    assert collections["wsp-50kt"]["threshold_kt"] == 50  # noqa: PLR2004 - the file's threshold
    assert collections["wsp-50kt"]["synoptic_time"] == SYNOPTIME


def test_a_windowed_conversion_is_deterministic(tmp_path: Path) -> None:
    entry = recorded_wsp(tmp_path)
    first = collections_of(entry, tmp_path, windowed=True)
    second = collections_of(entry, tmp_path, windowed=True)

    for product, collection in first.items():
        body = corpus.compressed_json(collection)
        assert body == corpus.compressed_json(second[product])
        assert body[4:8] == bytes(4)


def test_a_full_product_keeps_every_band_unclipped_with_longitudes_in_range(
    tmp_path: Path,
) -> None:
    collections = collections_of(recorded_wsp(tmp_path), tmp_path, windowed=False)

    assert labels_of(collections["wsp-34kt"]) == ["5-10%", "<5%", "10-20%"]
    assert collections["wsp-34kt"]["window"] is None
    (crossing,) = features_of(collections["wsp-64kt"])
    assert crossing["geometry_note"] == corpus.WRAP_NOTE
    rings = cast(
        "list[list[tuple[float, float]]]", cast("Json", crossing["geometry"])["coordinates"]
    )
    longitudes = [position[0] for ring in rings for position in ring]
    assert all(-180.0 <= longitude <= 180.0 for longitude in longitudes)  # noqa: PLR2004 - range
    assert max(longitudes) - min(longitudes) > 180.0  # noqa: PLR2004 - crosses the antimeridian


def test_wrapping_moves_only_longitudes_outside_the_range() -> None:
    landmark = load_landmarks()[0]
    lon, lat = float(landmark.lon), float(landmark.lat)
    west, east = lon - 200, -lon + 200

    assert corpus.wrapped([(west, lat), (lon, lat)]) == ([(west + 360, lat), (lon, lat)], True)
    assert corpus.wrapped([(lon, lat)]) == ([(lon, lat)], False)
    assert corpus.wrapped([[(east, lat)]]) == ([[(east - 360, lat)]], True)


def test_overlapping_windows_are_refused() -> None:
    first = load_landmarks()[0]
    near = replace(first, key="near", lon=first.lon + Decimal("0.5"))

    with pytest.raises(RecorderError, match="overlap"):
        corpus.window_member([first, near])


def test_a_validity_reason_never_names_a_location() -> None:
    landmark = load_landmarks()[0]
    lon, lat = float(landmark.lon), float(landmark.lat)
    bowtie = Polygon([(lon, lat), (lon + 1, lat + 1), (lon + 1, lat), (lon, lat + 1), (lon, lat)])

    assert corpus.validity_reason(bowtie) == "Self-intersection"


def staged_manifest(tmp_path: Path) -> corpus.Manifest:
    """A manifest whose one advisory has a forecast package, a probability archive, and a KMZ."""
    forecast_body = forecast_zip()
    forecast = replace(recorded(tmp_path, forecast_body), file="AL112017/al112017_5day_001.zip")
    corpus.atomic_write(tmp_path / forecast.file, forecast_body)
    corpus.inspect_archive(forecast, tmp_path)
    kmz_body = packed({"doc.kml": b"<kml/>"})
    kmz = replace(
        recorded(tmp_path, kmz_body),
        file="AL112017/AL112017_001adv_most_likely_toa_34.kmz",
        product="toa_most_likely",
    )
    corpus.atomic_write(tmp_path / kmz.file, kmz_body)
    wsp = recorded_wsp(tmp_path)
    storms = {storm: corpus.Storm([], [], [], []) for storm in corpus.STORMS}
    storms["AL112017"] = corpus.Storm(["001"], [], [], [SYNOPTIME])
    return corpus.Manifest(storms, [forecast, wsp, kmz], recorded_on="2026-10-15")


def test_the_full_conversion_refuses_a_directory_inside_the_checkout(tmp_path: Path) -> None:
    manifest = staged_manifest(tmp_path)
    inside = corpus.REPOSITORY_ROOT / "full-conversion"

    with pytest.raises(RecorderError, match="outside the checkout"):
        corpus.convert_full(manifest, tmp_path, inside)
    assert not inside.exists()


def test_the_cli_refuses_a_full_conversion_into_the_checkout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert corpus.main(["convert", "--full"]) == 1
    assert "outside the checkout" in capsys.readouterr().err


def test_the_full_conversion_writes_every_product_and_its_own_manifest(tmp_path: Path) -> None:
    manifest = staged_manifest(tmp_path)
    out = tmp_path / "full"

    corpus.convert_full(manifest, tmp_path, out)

    written = corpus.load_manifest(out / corpus.MANIFEST_NAME)
    assert written.subset_rule == corpus.FULL_RULE
    assert written.files == manifest.files
    assert written.recorded_on == manifest.recorded_on
    files = {output.file for output in written.subset}
    on_disk = {path.relative_to(out).as_posix() for path in out.rglob("*") if path.is_file()}
    assert on_disk == files | {corpus.MANIFEST_NAME}
    assert len([file for file in files if "/wsp/" in file]) == len(corpus.WSP_THRESHOLDS)
    copied = next(output for output in written.subset if output.product == "toa_most_likely")
    assert (out / copied.file).read_bytes() == (tmp_path / manifest.files[2].file).read_bytes()
    assert copied.sha256 == manifest.files[2].sha256
    for output in written.subset:
        assert hashlib.sha256((out / output.file).read_bytes()).hexdigest() == output.sha256


def test_a_refresh_rewrites_only_the_subset_and_its_rule(tmp_path: Path) -> None:
    manifest = staged_manifest(tmp_path)
    path = tmp_path / "manifest.json"
    corpus.write_manifest(manifest, path)
    out = tmp_path / "subset"

    corpus.refresh_subset(manifest, tmp_path, path, out)

    refreshed = corpus.load_manifest(path)
    assert (refreshed.files, refreshed.storms, refreshed.recorded_on) == (
        manifest.files,
        manifest.storms,
        manifest.recorded_on,
    )
    assert refreshed.subset_rule == corpus.subset_rule(corpus.ALL_ADVISORIES)
    written = {item.relative_to(out).as_posix() for item in out.rglob("*.gz")}
    assert {output.file for output in refreshed.subset} == written
    corpus.convert(refreshed, tmp_path, tmp_path / "again")
    omitted = corpus.Storm(["001"], [], [], [], ["001"])
    omitting = replace(manifest, storms={**manifest.storms, "AL112017": omitted})
    with pytest.raises(RecorderError, match="omit other advisories"):
        corpus.refresh_subset(omitting, tmp_path, path, out)


def test_a_manifest_names_the_day_its_originals_were_recorded(tmp_path: Path) -> None:
    manifest = staged_manifest(tmp_path)
    path = tmp_path / "manifest.json"
    corpus.write_manifest(replace(manifest, recorded_on="15 October"), path)

    with pytest.raises(RecorderError, match="recorded_on"):
        corpus.load_manifest(path)


@pytest.mark.parametrize(
    "argv",
    [
        ["fetch", "--full"],
        ["verify", "--refresh-subset"],
        ["convert", "--full", "--refresh-subset"],
    ],
)
def test_full_and_refresh_are_options_of_convert_alone(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        corpus.main(argv)
    assert error.value.code == USAGE_ERROR
