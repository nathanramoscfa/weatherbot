# tests/scripts/test_record_fixtures.py
"""Tests for the fixture recorder, ``scripts/record_fixtures.py``, without network.

respx answers every request from a table, a fake clock stands in for time, and every file
lands in ``tmp_path``. The one ``live`` test calls NHC and runs only with ``pytest -m live``.
"""

import base64
import gzip
import hashlib
import io
import json
import os
import struct
import zipfile
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from typing import cast

import httpx
import pytest
import respx

import check_personal_data as checker
import record_fixtures as recorder

FIXED_NOW = datetime(2026, 10, 20, 15, 2, 11, tzinfo=UTC)
DAY = date(2026, 10, 20)

STORMS_URL = f"{recorder.NHC_ROOT}/CurrentStorms.json"
SERVICE = recorder.MapService(
    "nhc-map-peak-surge",
    "NHC_PeakStormSurge",
    layers=(recorder.LayerSpec("Points"), recorder.LayerSpec("Lines")),
)
SLOT_SERVICE = recorder.MapService(
    "nhc-map-tropical-weather",
    "NHC_tropical_weather",
    layers=(recorder.LayerSpec("Seven-Day: Current Location"),),
    slot_layers=(
        recorder.LayerSpec("{slot} Forecast Cone"),
        recorder.LayerSpec("Footprint_Inun_{slot}", count_only=True),
    ),
)
OK = 200
NOT_FOUND = 404
ATTEMPTS_BEFORE_SUCCESS = 3
EMPTY_COLLECTION = '{"type": "FeatureCollection", "features": []}'


class FakeClock:
    """A monotonic clock that only ``sleep`` advances."""

    def __init__(self) -> None:
        """Start at an arbitrary time."""
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        """Return the fake time."""
        return self.now

    def sleep(self, seconds: float) -> None:
        """Advance the fake time instead of waiting."""
        self.sleeps.append(seconds)
        self.now += seconds


@dataclass
class Reply:
    """One scripted answer: a response, or an exception the transport raises."""

    status: int = 200
    body: bytes = b"{}"
    headers: dict[str, str] = field(default_factory=dict[str, str])
    error: Exception | None = None


class FakeNoaa:
    """Answers requests from a table keyed by the full URL, and logs each with the clock."""

    def __init__(self, clock: FakeClock) -> None:
        """Answer nothing until scripted."""
        self._clock = clock
        self._answers: dict[str, list[Reply]] = {}
        self.requests: list[tuple[float, httpx.Request]] = []

    def answer(self, url: str, *replies: Reply) -> None:
        """Script the replies for a URL; the last one repeats."""
        self._answers[url] = list(replies)

    def json(self, url: str, document: object, *, content_type: str = "application/json") -> None:
        """Script a JSON answer for a URL."""
        self.answer(
            url, Reply(body=json.dumps(document).encode(), headers={"content-type": content_type})
        )

    def urls(self) -> list[str]:
        """Return the requested URLs in order."""
        return [str(request.url) for _, request in self.requests]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Log the request and answer it from the script."""
        self.requests.append((self._clock.now, request))
        replies = self._answers.get(str(request.url))
        if replies is None:
            message = f"unexpected request {request.url}"
            raise AssertionError(message)
        reply = replies.pop(0) if len(replies) > 1 else replies[0]
        if reply.error is not None:
            raise reply.error
        return httpx.Response(reply.status, content=reply.body, headers=reply.headers)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def noaa(clock: FakeClock) -> Iterator[FakeNoaa]:
    fake = FakeNoaa(clock)
    with respx.mock(assert_all_called=False) as router:
        router.route().mock(side_effect=fake)
        yield fake


@pytest.fixture
def landmarks() -> tuple[checker.Landmark, ...]:
    return checker.load_landmarks()


@pytest.fixture
def run(
    noaa: FakeNoaa, clock: FakeClock, landmarks: tuple[checker.Landmark, ...]
) -> Iterator[recorder.Recorder]:
    del noaa  # the fixture only has to be active while the client sends requests
    pacer = recorder.Pacer(clock=clock.monotonic, sleep=clock.sleep)
    with httpx.Client() as client:
        fetcher = recorder.Fetcher(client, pacer, clock.sleep, lambda: FIXED_NOW)
        yield recorder.Recorder(fetcher, landmarks)


def roster(*slots: str) -> dict[str, object]:
    return {
        "activeStorms": [{"id": f"x{index}", "binNumber": slot} for index, slot in enumerate(slots)]
    }


def catalog(*layers: tuple[int, str]) -> dict[str, object]:
    return {"layers": [{"id": layer_id, "name": name} for layer_id, name in layers]}


def query_url(service: recorder.MapService, layer_id: int, *, count_only: bool = False) -> str:
    parameters = recorder.COUNT_PARAMETERS if count_only else recorder.QUERY_PARAMETERS
    return f"{service.url}/{layer_id}/query?{recorder.urlencode(parameters, safe='*')}"


def stage_service(noaa: FakeNoaa, service: recorder.MapService, *layers: tuple[int, str]) -> None:
    noaa.json(f"{service.url}?f=json", catalog(*layers))
    noaa.json(f"{service.url}/layers?f=json", {"layers": []})


def png_bytes(width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    rows = (b"\x00" + b"\x7f" * width) * height
    return (
        recorder.PNG_SIGNATURE
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def report_html(*images: tuple[str, bytes]) -> str:
    tags = "".join(
        f'<img src="data:image/png;base64,{base64.b64encode(data).decode()}" alt="{alt}">'
        for alt, data in images
    )
    return f"<html><body><p>Secret analysis text.</p>{tags}</body></html>"


def as_object(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def read_manifest(directory: Path) -> dict[str, object]:
    return as_object(json.loads((directory / "manifest.json").read_text(encoding="utf-8")))


def manifest_entries(directory: Path) -> list[dict[str, object]]:
    entries = read_manifest(directory)["captures"]
    assert isinstance(entries, list)
    return [as_object(entry) for entry in cast("list[object]", entries)]


def test_every_request_carries_the_user_agent(noaa: FakeNoaa, run: recorder.Recorder) -> None:
    noaa.json(STORMS_URL, roster())
    for feed in recorder.GIS_FEEDS:
        noaa.answer(f"{recorder.NHC_ROOT}/gis-{feed}.xml", Reply(body=b"<rss/>"))
    stage_service(noaa, SERVICE, (1, "Points"), (2, "Lines"))
    for layer_id in (1, 2):
        noaa.answer(query_url(SERVICE, layer_id), Reply(body=EMPTY_COLLECTION.encode()))

    for source in ("nhc-current-storms", "nhc-gis-rss"):
        recorder.SOURCES[source](run)
    recorder.record_map_service(run, SERVICE)

    assert len(noaa.requests) == 1 + 3 + 2 + 2
    assert {request.headers["user-agent"] for _, request in noaa.requests} == {recorder.USER_AGENT}


def test_layers_resolve_by_name_when_ids_shift(noaa: FakeNoaa, run: recorder.Recorder) -> None:
    stage_service(noaa, SERVICE, (7, "Points"), (3, "Lines"))
    noaa.answer(query_url(SERVICE, 7), Reply(body=EMPTY_COLLECTION.encode()))
    noaa.answer(query_url(SERVICE, 3), Reply(body=EMPTY_COLLECTION.encode()))
    first = recorder.record_map_service(run, SERVICE)

    # The next day NOAA renumbers the layers; the recorder follows the names.
    stage_service(noaa, SERVICE, (41, "Lines"), (40, "Points"))
    noaa.answer(query_url(SERVICE, 40), Reply(body=EMPTY_COLLECTION.encode()))
    noaa.answer(query_url(SERVICE, 41), Reply(body=EMPTY_COLLECTION.encode()))
    second = recorder.record_map_service(run, SERVICE)

    assert [capture.name for capture in first] == [capture.name for capture in second]
    assert first[2].url == query_url(SERVICE, 7)
    assert second[2].url == query_url(SERVICE, 40)
    assert second[3].url == query_url(SERVICE, 41)


@pytest.mark.parametrize(
    "layers",
    [
        pytest.param([(1, "Other")], id="missing"),
        pytest.param([(1, "Points"), (2, "Points")], id="repeated"),
    ],
)
def test_a_layer_name_must_match_exactly_one_layer(layers: list[tuple[int, str]]) -> None:
    with pytest.raises(recorder.RecorderError, match="not exactly one"):
        recorder.resolve_layer(catalog(*layers), "Points")


def test_slot_layers_are_recorded_for_every_active_slot(
    noaa: FakeNoaa, run: recorder.Recorder
) -> None:
    noaa.json(STORMS_URL, roster("EP5", "AT2", "EP5"))
    stage_service(
        noaa,
        SLOT_SERVICE,
        (1, "Seven-Day: Current Location"),
        (10, "AT2 Forecast Cone"),
        (11, "Footprint_Inun_AT2"),
        (20, "EP5 Forecast Cone"),
        (21, "Footprint_Inun_EP5"),
    )
    for layer_id in (1, 10, 20):
        noaa.answer(query_url(SLOT_SERVICE, layer_id), Reply(body=EMPTY_COLLECTION.encode()))
    for layer_id in (11, 21):
        noaa.answer(query_url(SLOT_SERVICE, layer_id, count_only=True), Reply(body=b'{"count": 0}'))

    captures = recorder.record_map_service(run, SLOT_SERVICE)

    assert [capture.name for capture in captures] == [
        "catalog.json",
        "layers.json",
        "query-seven-day-current-location.geojson",
        "query-at2-forecast-cone.geojson",
        "count-footprint-inun-at2.json",
        "query-ep5-forecast-cone.geojson",
        "count-footprint-inun-ep5.json",
    ]


def test_an_arcgis_error_body_fails_the_source(noaa: FakeNoaa, run: recorder.Recorder) -> None:
    stage_service(noaa, SERVICE, (1, "Points"), (2, "Lines"))
    noaa.answer(query_url(SERVICE, 1), Reply(body=b'{"error": {"code": 400}}'))

    with pytest.raises(recorder.RecorderError, match="ArcGIS error"):
        recorder.record_map_service(run, SERVICE)


def test_a_truncated_arcgis_response_fails_the_source(
    noaa: FakeNoaa, run: recorder.Recorder
) -> None:
    stage_service(noaa, SERVICE, (1, "Points"), (2, "Lines"))
    truncated: dict[str, object] = {
        "type": "FeatureCollection",
        "features": [],
        "exceededTransferLimit": True,
    }
    noaa.answer(query_url(SERVICE, 1), Reply(body=json.dumps(truncated).encode()))

    with pytest.raises(recorder.RecorderError, match="transfer limit"):
        recorder.record_map_service(run, SERVICE)


def test_requests_to_one_host_are_paced(
    noaa: FakeNoaa, clock: FakeClock, run: recorder.Recorder
) -> None:
    fetcher = run.fetcher
    nws = [f"{recorder.NWS_ROOT}/zones/forecast/FLZ17{index}" for index in range(3)]
    nominatim = f"{recorder.NOMINATIM_URL}?format=jsonv2&lat=1&lon=2"
    for url in (*nws, nominatim, STORMS_URL):
        noaa.answer(url, Reply())

    for url in (nws[0], nws[1], nominatim, nws[2], STORMS_URL, nominatim):
        fetcher.get(url, source="test")

    times: dict[str, list[float]] = {}
    for moment, request in noaa.requests:
        times.setdefault(request.url.host, []).append(moment)
    gaps = {host: [b - a for a, b in pairwise(moments)] for host, moments in times.items()}
    assert min(gaps["api.weather.gov"]) >= 1.0
    assert min(gaps["nominatim.openstreetmap.org"]) >= 1.0
    # Each host is paced on its own: a first request to a host never waits, and the repeat
    # request to Nominatim waits only for what the NWS wait had already spent.
    assert clock.sleeps == [pytest.approx(1.2), pytest.approx(1.2), pytest.approx(0.3)]


def test_the_pacer_sleeps_only_the_remaining_interval() -> None:
    clock = FakeClock()
    pacer = recorder.Pacer(
        clock=clock.monotonic, sleep=clock.sleep, intervals={"slow.example": 2.0}
    )

    pacer.wait("slow.example")
    clock.now += 0.5
    pacer.wait("slow.example")
    clock.now += 5.0
    pacer.wait("slow.example")

    assert clock.sleeps == [pytest.approx(1.5)]


def test_a_server_error_is_retried_with_backoff(
    noaa: FakeNoaa, clock: FakeClock, run: recorder.Recorder
) -> None:
    noaa.answer(
        STORMS_URL,
        Reply(status=503),
        Reply(error=httpx.ConnectError("refused")),
        Reply(body=b'{"activeStorms": []}'),
    )

    fetched = run.fetcher.get(STORMS_URL, source="nhc-current-storms")

    assert fetched.status == OK
    assert len(noaa.requests) == ATTEMPTS_BEFORE_SUCCESS
    assert clock.sleeps == [recorder.BACKOFF_SECONDS, recorder.BACKOFF_SECONDS * 2]


def test_retries_run_out(noaa: FakeNoaa, run: recorder.Recorder) -> None:
    noaa.answer(f"{STORMS_URL}?x=1", Reply(status=502))

    with pytest.raises(
        recorder.RecorderError, match=r"failed after 4 attempts \(HTTP 502\)"
    ) as raised:
        run.fetcher.get(f"{STORMS_URL}?x=1", source="nhc-current-storms")

    assert "x=1" not in str(raised.value)
    assert len(noaa.requests) == recorder.REQUEST_ATTEMPTS


def test_a_status_the_register_does_not_document_is_an_error(
    noaa: FakeNoaa, run: recorder.Recorder
) -> None:
    noaa.answer(STORMS_URL, Reply(status=403))

    with pytest.raises(recorder.RecorderError, match="unexpected HTTP 403"):
        run.fetcher.get(STORMS_URL, source="nhc-current-storms")


def test_the_nassau_points_error_is_recorded_with_its_status_and_body(
    noaa: FakeNoaa, run: recorder.Recorder, landmarks: tuple[checker.Landmark, ...]
) -> None:
    problem = {"title": "Data Unavailable For Requested Point", "status": 404}
    for landmark in landmarks:
        url = f"{recorder.NWS_ROOT}/points/{recorder.coordinates(landmark)}"
        if landmark.key == "nassau":
            noaa.answer(
                url,
                Reply(
                    status=404,
                    body=json.dumps(problem).encode(),
                    headers={"content-type": "application/problem+json"},
                ),
            )
        else:
            noaa.json(url, {"properties": {}}, content_type="application/geo+json")

    captures = recorder.record_nws_points(run)

    by_name = {capture.name: capture for capture in captures}
    assert by_name["points-nassau.json"].status == NOT_FOUND
    assert json.loads(by_name["points-nassau.json"].body) == problem


def test_an_unlabelled_error_response_is_not_recorded(
    noaa: FakeNoaa, run: recorder.Recorder, landmarks: tuple[checker.Landmark, ...]
) -> None:
    for landmark in landmarks:
        noaa.answer(
            f"{recorder.NWS_ROOT}/points/{recorder.coordinates(landmark)}",
            Reply(status=404, body=b"<html>Not Found</html>"),
        )

    with pytest.raises(recorder.RecorderError, match="not a documented error"):
        recorder.record_nws_points(run)


def test_zone_sources_follow_the_zones_the_points_response_names(
    noaa: FakeNoaa, run: recorder.Recorder, landmarks: tuple[checker.Landmark, ...]
) -> None:
    zone = f"{recorder.NWS_ROOT}/zones"
    properties = {
        "county": f"{zone}/county/FLC086",
        "forecastZone": f"{zone}/forecast/FLZ173",
        "fireWeatherZone": f"{zone}/fire/FLZ173",
    }
    for landmark in landmarks:
        url = f"{recorder.NWS_ROOT}/points/{recorder.coordinates(landmark)}"
        if landmark.key == "nassau":
            noaa.answer(url, Reply(status=404, headers={"content-type": recorder.PROBLEM_JSON}))
        else:
            noaa.json(url, {"properties": properties}, content_type="application/geo+json")
    for zone_id in ("FLC086", "FLZ173"):
        noaa.json(f"{recorder.NWS_ROOT}/alerts/active/zone/{zone_id}", json.loads(EMPTY_COLLECTION))
    for zone_type, zone_id in (("county", "FLC086"), ("forecast", "FLZ173"), ("fire", "FLZ173")):
        noaa.json(f"{zone}/{zone_type}/{zone_id}", {"type": "Feature"})

    alerts = recorder.record_nws_alerts_zone(run)
    zones = recorder.record_nws_zones(run)

    assert [capture.name for capture in alerts] == [
        "alerts-zone-FLC086.geojson",
        "alerts-zone-FLZ173.geojson",
    ]
    assert [capture.name for capture in zones] == [
        "zone-county-FLC086.json",
        "zone-forecast-FLZ173.json",
        "zone-fire-FLZ173.json",
    ]
    points_requests = [url for url in noaa.urls() if "/points/" in url]
    assert len(points_requests) == len(landmarks)  # the points response is fetched once


def test_a_zone_url_outside_the_zone_pattern_is_refused(
    noaa: FakeNoaa, run: recorder.Recorder, landmarks: tuple[checker.Landmark, ...]
) -> None:
    for landmark in landmarks:
        noaa.json(
            f"{recorder.NWS_ROOT}/points/{recorder.coordinates(landmark)}",
            {"properties": {"county": "https://api.weather.gov/zones/county/../../admin"}},
            content_type="application/geo+json",
        )

    with pytest.raises(recorder.RecorderError, match="not an NWS zone URL"):
        recorder.record_nws_zones(run)


def test_text_products_list_each_basin_and_slot_and_keep_the_newest(
    noaa: FakeNoaa, run: recorder.Recorder
) -> None:
    noaa.json(STORMS_URL, roster("EP5"))
    listings = {
        ("TCP", "EP5"): [
            ("older-0001", "2026-10-12T14:51:00+00:00"),
            ("newer-0002", "2026-10-12T20:51:00+00:00"),
        ],
        ("TWO", "AT"): [("two-at-0001", "2026-10-12T18:00:00+00:00")],
        ("TWO", "EP"): [],
        ("TWO", "CP"): [("two-cp-0001", "2026-10-12T18:00:00+00:00")],
    }
    for (kind, location), products in listings.items():
        graph = [{"id": identifier, "issuanceTime": issued} for identifier, issued in products]
        noaa.json(
            f"{recorder.NWS_ROOT}/products/types/{kind}/locations/{location}", {"@graph": graph}
        )
    for identifier in ("newer-0002", "two-at-0001", "two-cp-0001"):
        noaa.json(f"{recorder.NWS_ROOT}/products/{identifier}", {"productText": "text"})

    captures = recorder.record_text_products(run)

    assert [capture.name for capture in captures] == [
        "tcp-ep5-list.json",
        "tcp-ep5-product.json",
        "two-at-list.json",
        "two-at-product.json",
        "two-ep-list.json",
        "two-cp-list.json",
        "two-cp-product.json",
    ]
    assert not any("older-0001" in url for url in noaa.urls())


def test_manifest_urls_carry_only_landmark_coordinates(
    noaa: FakeNoaa, run: recorder.Recorder, landmarks: tuple[checker.Landmark, ...]
) -> None:
    allowlist = checker.Allowlist.from_landmarks(landmarks)
    for landmark in landmarks:
        noaa.json(
            f"{recorder.NWS_ROOT}/points/{recorder.coordinates(landmark)}", {"properties": {}}
        )
        noaa.json(
            f"{recorder.NWS_ROOT}/alerts/active?point={recorder.coordinates(landmark)}",
            json.loads(EMPTY_COLLECTION),
        )
        noaa.json(
            f"{recorder.NOMINATIM_URL}?format=jsonv2&lat={landmark.lat:.4f}&lon={landmark.lon:.4f}",
            {"display_name": "somewhere"},
        )

    captures = [
        *recorder.record_nws_points(run),
        *recorder.record_nws_alerts_point(run),
        *recorder.record_nominatim(run),
    ]

    pairs = [pair for capture in captures for pair in checker.request_coordinates(capture.url)]
    assert len(pairs) == 3 * len(landmarks)
    for lat, lon in pairs:
        assert allowlist.allows_pair(Decimal(lat), Decimal(lon))


def test_headers_outside_the_allowlist_are_dropped(noaa: FakeNoaa, run: recorder.Recorder) -> None:
    noaa.answer(
        STORMS_URL,
        Reply(
            headers={
                "Content-Type": "application/json",
                "ETag": '"abc"',
                "Set-Cookie": "session=secret",
                "Server": "nginx",
                "X-Request-Id": "r-1",
                "Cache-Control": "max-age=300",
            }
        ),
    )

    fetched = run.fetcher.get(STORMS_URL, source="nhc-current-storms")

    assert dict(fetched.headers) == {
        "cache-control": "max-age=300",
        "content-length": "2",
        "content-type": "application/json",
        "etag": '"abc"',
    }
    assert set(fetched.headers) <= recorder.HEADER_ALLOWLIST


def capture_of_size(size: int, *, name: str = "payload.json") -> recorder.Capture:
    return recorder.Capture(
        name=name,
        url=STORMS_URL,
        status=200,
        fetched_at=FIXED_NOW,
        body=(b'"' + b"a" * (size - 2) + b'"'),
    )


def test_a_payload_over_1_mib_is_stored_gzip_and_the_same_bytes_give_the_same_file(
    tmp_path: Path,
) -> None:
    big = capture_of_size(recorder.GZIP_THRESHOLD_BYTES + 1)
    small = capture_of_size(recorder.GZIP_THRESHOLD_BYTES, name="small.json")

    first = recorder.write_capture_directory(
        tmp_path / "one", "nhc-current-storms", DAY, [big, small], recorded_at=FIXED_NOW
    )
    second = recorder.write_capture_directory(
        tmp_path / "two",
        "nhc-current-storms",
        DAY,
        [big, small],
        recorded_at=datetime(2027, 1, 1, tzinfo=UTC),
    )

    assert sorted(path.name for path in first.iterdir()) == [
        "manifest.json",
        "payload.json.gz",
        "small.json",
    ]
    assert (first / "payload.json.gz").read_bytes() == (second / "payload.json.gz").read_bytes()
    assert gzip.decompress((first / "payload.json.gz").read_bytes()) == big.body
    entries = {entry["file"]: entry for entry in manifest_entries(first)}
    assert entries["payload.json.gz"]["stored_as"] == "gzip"
    assert entries["payload.json.gz"]["sha256"] == hashlib.sha256(big.body).hexdigest()
    assert entries["payload.json.gz"]["bytes"] == len(big.body)
    assert entries["small.json"]["stored_as"] == "raw"


def test_a_stored_file_over_5_mib_fails_naming_the_source_and_size(tmp_path: Path) -> None:
    body = os.urandom(recorder.MAX_STORED_BYTES + 1)
    capture = recorder.Capture("noise.json", STORMS_URL, 200, FIXED_NOW, body)

    with pytest.raises(recorder.RecorderError, match="nws-zones") as raised:
        recorder.write_capture_directory(
            tmp_path, "nws-zones", DAY, [capture], recorded_at=FIXED_NOW
        )

    assert "noise.json.gz" in str(raised.value)
    assert f"is {len(gzip.compress(body, compresslevel=9, mtime=0))} bytes" in str(raised.value)
    assert not (tmp_path / "nws-zones").exists()


def test_a_failed_recording_leaves_the_earlier_capture_of_the_day(tmp_path: Path) -> None:
    good = capture_of_size(100)
    recorder.write_capture_directory(tmp_path, "nws-zones", DAY, [good], recorded_at=FIXED_NOW)
    before = (tmp_path / "nws-zones" / DAY.isoformat() / "payload.json").read_bytes()

    with pytest.raises(recorder.RecorderError):
        recorder.write_capture_directory(tmp_path, "nws-zones", DAY, [], recorded_at=FIXED_NOW)

    assert (tmp_path / "nws-zones" / DAY.isoformat() / "payload.json").read_bytes() == before
    assert [path.name for path in (tmp_path / "nws-zones").iterdir()] == [DAY.isoformat()]


def test_the_manifest_has_the_schema_the_roadmap_specifies(tmp_path: Path) -> None:
    capture = recorder.Capture(
        "a.json", STORMS_URL, 200, FIXED_NOW, b"{}", {"content-type": "application/json"}, notes="n"
    )

    directory = recorder.write_capture_directory(
        tmp_path, "nhc-current-storms", DAY, [capture], recorded_at=FIXED_NOW
    )

    manifest = read_manifest(directory)
    assert list(manifest) == [
        "schema",
        "source",
        "recorded_at",
        "recorder",
        "user_agent",
        "captures",
    ]
    assert manifest["schema"] == 1
    assert manifest["recorded_at"] == "2026-10-20T15:02:11Z"
    assert manifest["recorder"] == "scripts/record_fixtures.py"
    assert list(manifest_entries(directory)[0]) == [
        "file",
        "url",
        "status",
        "fetched_at",
        "sha256",
        "bytes",
        "stored_as",
        "headers",
        "origin",
        "notes",
    ]


def test_record_sources_reports_a_failing_source_and_records_the_rest(
    noaa: FakeNoaa, run: recorder.Recorder, tmp_path: Path
) -> None:
    noaa.json(STORMS_URL, roster())
    for feed in recorder.GIS_FEEDS:
        noaa.answer(f"{recorder.NHC_ROOT}/gis-{feed}.xml", Reply(status=403))

    outcomes = recorder.record_sources(run, ["nhc-gis-rss", "nhc-current-storms"], tmp_path, DAY)

    assert [outcome.source for outcome in outcomes] == ["nhc-gis-rss", "nhc-current-storms"]
    assert outcomes[0].problem is not None
    assert outcomes[1].problem is None
    assert (tmp_path / "nhc-current-storms" / DAY.isoformat() / "manifest.json").is_file()
    assert not (tmp_path / "nhc-gis-rss").exists()


def test_an_unknown_slot_in_the_roster_is_refused(noaa: FakeNoaa, run: recorder.Recorder) -> None:
    noaa.json(STORMS_URL, roster("../x"))

    with pytest.raises(recorder.RecorderError, match="unknown binNumber"):
        run.active_slots()


def test_outlook_graphics_record_their_pixel_size(noaa: FakeNoaa, run: recorder.Recorder) -> None:
    for name in recorder.OUTLOOK_FILES:
        noaa.answer(f"{recorder.NHC_ROOT}/xgtwo/{name}", Reply(body=png_bytes(9, 5)))

    captures = recorder.record_outlook_graphics(run)

    assert [capture.name for capture in captures] == list(recorder.OUTLOOK_FILES)
    assert {capture.notes for capture in captures} == {"PNG 9x5"}


def test_the_harvest_takes_only_the_outlook_map(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    outlook, cone = png_bytes(900, 665), png_bytes(7, 3)
    (reports / "hurricane_threat_analysis_20251004_130458.html").write_text(
        report_html((recorder.OUTLOOK_ALT, outlook), ("Humberto Forecast Cone", cone)),
        encoding="utf-8",
    )
    out = tmp_path / "recorded"

    directories = recorder.harvest_reports(reports, out, recorded_at=FIXED_NOW)

    assert [path.relative_to(out).as_posix() for path in directories] == [
        "nhc-outlook-graphics/2025-10-04"
    ]
    written = sorted(path.name for path in directories[0].iterdir())
    assert written == ["manifest.json", "two_atl_7d0.png"]
    assert (directories[0] / "two_atl_7d0.png").read_bytes() == outlook
    manifest_text = (directories[0] / "manifest.json").read_text(encoding="utf-8")
    assert "Secret analysis text" not in manifest_text
    assert not any(cone == path.read_bytes() for path in out.rglob("*") if path.is_file())
    entry = manifest_entries(directories[0])[0]
    assert entry["origin"] == "harvest:v1-report"
    assert entry["harvested_from"] == "reports/hurricane_threat_analysis_20251004_130458.html"
    assert entry["url"] == "https://www.nhc.noaa.gov/xgtwo/two_atl_7d0.png"
    assert entry["status"] == OK
    assert entry["fetched_at"] == "2025-10-04T17:04:58Z"
    assert "PNG 900x665" in str(entry["notes"])
    assert "EDT" in str(entry["notes"])
    assert entry["sha256"] == hashlib.sha256(outlook).hexdigest()


def test_the_harvest_folder_is_the_local_date_not_the_utc_date(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    name = "hurricane_threat_analysis_20251003_224500.html"
    (reports / name).write_text(
        report_html((recorder.OUTLOOK_ALT, png_bytes(4, 4))), encoding="utf-8"
    )

    directories = recorder.harvest_reports(reports, tmp_path / "recorded", recorded_at=FIXED_NOW)

    assert directories[0].name == "2025-10-03"
    entry = manifest_entries(directories[0])[0]
    assert entry["fetched_at"] == "2025-10-04T02:45:00Z"


def test_the_harvest_ignores_reports_outside_2025(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    page = report_html((recorder.OUTLOOK_ALT, png_bytes(4, 4)))
    (reports / "hurricane_threat_analysis_20251003_224500.html").write_text(page, encoding="utf-8")
    (reports / "hurricane_threat_analysis_20261011_193203.html").write_text(page, encoding="utf-8")

    directories = recorder.harvest_reports(reports, tmp_path / "recorded", recorded_at=FIXED_NOW)

    assert [path.name for path in directories] == ["2025-10-03"]


@pytest.mark.parametrize(
    ("page", "message"),
    [
        pytest.param(
            report_html(("Some other map", png_bytes(4, 4))), "embeds 0 outlook maps", id="none"
        ),
        pytest.param(
            report_html(
                (recorder.OUTLOOK_ALT, png_bytes(4, 4)), (recorder.OUTLOOK_ALT, png_bytes(4, 4))
            ),
            "embeds 2 outlook maps",
            id="two",
        ),
        pytest.param(report_html((recorder.OUTLOOK_ALT, b"not a png")), "not a PNG", id="not-png"),
    ],
)
def test_a_report_without_exactly_one_valid_outlook_map_fails(
    tmp_path: Path, page: str, message: str
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "hurricane_threat_analysis_20251003_224500.html").write_text(page, encoding="utf-8")

    with pytest.raises(recorder.RecorderError, match=message):
        recorder.harvest_reports(reports, tmp_path / "recorded", recorded_at=FIXED_NOW)


def test_a_report_after_daylight_time_ended_is_refused() -> None:
    with pytest.raises(recorder.RecorderError, match="daylight time"):
        recorder.report_time("hurricane_threat_analysis_20251105_120000.html")


def test_the_cache_harvest_recovers_what_version_1_keyed_and_lists_the_rest(tmp_path: Path) -> None:
    keys = recorder.v1_requests()
    by_name = {request.name: key for key, request in keys.items() if request.source is not None}
    atcf = next(key for key, request in keys.items() if request.source is None)
    cache = tmp_path / "cache"
    cache.mkdir()
    stamp = datetime(2025, 10, 4, 15, 0, tzinfo=UTC).timestamp()
    entries: dict[str, object] = {
        by_name["CurrentStorms.json"]: {"activeStorms": []},
        by_name["catalog.json"]: {"layers": []},
        by_name["v1-layer-238-geojson.geojson"]: {"type": "FeatureCollection", "features": []},
    }
    for key, data in entries.items():
        (cache / f"{key}.json").write_text(
            json.dumps({"timestamp": stamp, "data": data}), encoding="utf-8"
        )
    (cache / f"{atcf}.json").write_text(
        json.dumps({"timestamp": stamp, "data": {"text": ""}}), encoding="utf-8"
    )
    (cache / "193f11c264cdfd847af278c0adbe9599.json").write_text(
        json.dumps({"timestamp": stamp, "data": {"test": "data"}}), encoding="utf-8"
    )
    (cache / f"{by_name['v1-layer-5-json.json']}.json").write_text("not json", encoding="utf-8")
    out = tmp_path / "recorded"

    result = recorder.harvest_cache(cache, out, recorded_at=FIXED_NOW)

    assert result.out_of_register == [f"{atcf}.json"]
    assert sorted(result.unrecoverable) == sorted(
        ["193f11c264cdfd847af278c0adbe9599.json", f"{by_name['v1-layer-5-json.json']}.json"]
    )
    written = sorted(path.relative_to(out).parts[0] for path in result.directories)
    assert written == ["nhc-current-storms", "nhc-map-tropical-weather"]
    weather = next(
        path for path in result.directories if path.parent.name == "nhc-map-tropical-weather"
    )
    assert sorted(path.name for path in weather.iterdir()) == [
        "catalog.json",
        "manifest.json",
        "v1-layer-238-geojson.geojson",
    ]
    entry = manifest_entries(weather)[1]
    assert entry["origin"] == "harvest:v1-cache"
    assert str(entry["harvested_from"]).startswith("cache/")
    assert str(entry["url"]).startswith(f"{recorder.V1_MAP_URL}/238/query?")


def test_the_cache_harvest_without_a_cache_directory_finds_nothing(tmp_path: Path) -> None:
    result = recorder.harvest_cache(
        tmp_path / "missing", tmp_path / "recorded", recorded_at=FIXED_NOW
    )

    assert (result.directories, result.unrecoverable, result.out_of_register) == ([], [], [])


def test_a_cache_harvest_never_replaces_a_live_capture(tmp_path: Path) -> None:
    out = tmp_path / "recorded"
    cache = tmp_path / "cache"
    cache.mkdir()
    stamp = datetime(2025, 10, 4, 15, 0, tzinfo=UTC)
    key = next(
        key
        for key, request in recorder.v1_requests().items()
        if request.name == "CurrentStorms.json"
    )
    (cache / f"{key}.json").write_text(
        json.dumps({"timestamp": stamp.timestamp(), "data": {}}), encoding="utf-8"
    )
    live = recorder.Capture("CurrentStorms.json", STORMS_URL, 200, stamp, b"{}")
    recorder.write_capture_directory(
        out, "nhc-current-storms", stamp.astimezone().date(), [live], recorded_at=FIXED_NOW
    )

    with pytest.raises(recorder.RecorderError, match="a live capture"):
        recorder.harvest_cache(cache, out, recorded_at=FIXED_NOW)


def test_helpers() -> None:
    assert recorder.slugify("Seven-Day: Current Location") == "seven-day-current-location"
    assert recorder.slugify("Boundary_Inun_EP5") == "boundary-inun-ep5"
    assert recorder.json_name("a", EMPTY_COLLECTION.encode()) == "a.geojson"
    assert recorder.json_name("a", b'{"type": "Feature"}') == "a.json"
    assert recorder.json_name("a", b"<xml/>") == "a.json"
    assert recorder.png_dimensions(png_bytes(900, 665)) == (900, 665)
    with pytest.raises(recorder.RecorderError):
        recorder.png_dimensions(b"GIF89a" + bytes(40))


def test_the_summary_layers_are_the_slot_layers_without_the_slot() -> None:
    assert [layer.name for layer in recorder.SUMMARY_LAYERS][:2] == [
        "Forecast Points",
        "Forecast Track",
    ]
    assert "Footprint_Inun" in {layer.name for layer in recorder.SUMMARY_LAYERS if layer.count_only}
    assert len(recorder.SUMMARY_LAYERS) == len(recorder.SLOT_LAYERS)


@pytest.mark.live
@pytest.mark.enable_socket
def test_live_current_storms_capture_has_a_valid_manifest(
    tmp_path: Path, landmarks: tuple[checker.Landmark, ...]
) -> None:
    with httpx.Client(timeout=recorder.REQUEST_TIMEOUT) as client:
        run = recorder.Recorder(recorder.Fetcher(client), landmarks)
        outcomes = recorder.record_sources(run, ["nhc-current-storms"], tmp_path, DAY)

    assert outcomes[0].problem is None
    directory = tmp_path / "nhc-current-storms" / DAY.isoformat()
    manifest = read_manifest(directory)
    assert manifest["schema"] == 1
    assert manifest["source"] == "nhc-current-storms"
    assert manifest["user_agent"] == recorder.USER_AGENT
    entries = manifest_entries(directory)
    assert len(entries) == 1
    entry = entries[0]
    payload = (directory / str(entry["file"])).read_bytes()
    assert entry["url"] == STORMS_URL
    assert entry["status"] == OK
    assert entry["sha256"] == hashlib.sha256(payload).hexdigest()
    assert entry["bytes"] == len(payload)
    assert set(as_object(entry["headers"])) <= recorder.HEADER_ALLOWLIST
    assert isinstance(as_object(json.loads(payload))["activeStorms"], list)


ARRIVAL_ROOT = f"{recorder.NHC_ROOT}/storm_graphics/api"
KML = (
    b'<kml xmlns="http://earth.google.com/kml/2.2"><Document><ExtendedData>'
    b'<Data name="timezone"><value>MST</value></Data></ExtendedData></Document></kml>'
)


def kmz_bytes(*members: tuple[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members:
            archive.writestr(name, data)
    return buffer.getvalue()


def arrival_storm(storm_id: str, advisory: str) -> dict[str, object]:
    def product(kind: str) -> dict[str, object]:
        return {
            "advNum": advisory,
            "issuance": "2026-10-20T15:00:00.000Z",
            "kmzFile": f"{ARRIVAL_ROOT}/{storm_id.upper()}_{advisory}adv_{kind}_toa_34.kmz",
        }

    return {
        "id": storm_id,
        "binNumber": "EP1",
        "earliestArrivalTimeTSWindsGIS": product("earliest_reasonable"),
        "mostLikelyTimeTSWindsGIS": product("most_likely"),
    }


def test_arrival_times_record_the_archived_pair_and_every_roster_link(
    noaa: FakeNoaa, run: recorder.Recorder
) -> None:
    noaa.json(STORMS_URL, {"activeStorms": [arrival_storm("ep212026", "015")]})
    body = kmz_bytes(("doc.kml", KML), ("labels/am.png", b"png"))
    linked = [f"{ARRIVAL_ROOT}/EP212026_015adv_{kind}_toa_34.kmz" for kind in recorder.KINDS]
    for url in (*recorder.ARCHIVED_ARRIVAL_PAIR, *linked):
        noaa.answer(
            url, Reply(body=body, headers={"content-type": "application/vnd.google-earth.kmz"})
        )

    captures = recorder.record_arrival_times(run)

    assert [c.url for c in captures] == [*recorder.ARCHIVED_ARRIVAL_PAIR, *linked]
    assert [c.name for c in captures][2] == "EP212026_015adv_earliest_reasonable_toa_34.kmz"
    assert captures[0].notes == recorder.ARCHIVED_ARRIVAL_NOTE
    assert captures[2].notes == (
        "roster: EP212026 earliestArrivalTimeTSWindsGIS advNum 015, "
        "issuance 2026-10-20T15:00:00.000Z"
    )


def test_arrival_times_off_season_record_the_archived_pair_only(
    noaa: FakeNoaa, run: recorder.Recorder
) -> None:
    noaa.json(STORMS_URL, roster())
    for url in recorder.ARCHIVED_ARRIVAL_PAIR:
        noaa.answer(url, Reply(body=kmz_bytes(("doc.kml", KML))))

    captures = recorder.record_arrival_times(run)

    assert [c.url for c in captures] == list(recorder.ARCHIVED_ARRIVAL_PAIR)


@pytest.mark.parametrize(
    "link",
    [
        "https://example.org/EP212026_015adv_most_likely_toa_34.kmz",
        f"{ARRIVAL_ROOT}/EP212026_015adv_TRACK.kmz",
        f"{ARRIVAL_ROOT}/EP212026_015adv_most_likely_toa_34.kmz".replace("https", "http"),
    ],
)
def test_a_roster_link_outside_the_pattern_fails_before_any_kmz_is_fetched(
    noaa: FakeNoaa, run: recorder.Recorder, link: str
) -> None:
    storm = arrival_storm("ep212026", "015")
    as_object(storm["mostLikelyTimeTSWindsGIS"])["kmzFile"] = link
    noaa.json(STORMS_URL, {"activeStorms": [storm]})

    with pytest.raises(recorder.RecorderError, match="outside the arrival-time pattern"):
        recorder.record_arrival_times(run)

    assert noaa.urls() == [STORMS_URL]


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"not a zip", "not a readable zip archive"),
        (kmz_bytes(("../doc.kml", KML)), "absolute or parent-relative"),
        (kmz_bytes(("doc.kml", b"<!DOCTYPE kml [<!ENTITY a 'b'>]><kml/>")), "DTD or an entity"),
    ],
    ids=["not-zip", "traversal", "entity"],
)
def test_a_kmz_that_breaks_the_clients_limits_fails_the_source(
    noaa: FakeNoaa, run: recorder.Recorder, body: bytes, message: str
) -> None:
    noaa.json(STORMS_URL, roster())
    for url in recorder.ARCHIVED_ARRIVAL_PAIR:
        noaa.answer(url, Reply(body=body))

    with pytest.raises(recorder.RecorderError, match=message):
        recorder.record_arrival_times(run)
