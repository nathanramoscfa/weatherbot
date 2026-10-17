# tests/sources/test_http.py
"""Tests of the HTTP layer's controls: identity, pacing, retries, size, redirects, 304s, privacy.

Every request is answered by respx; no test opens a socket. The coordinates in the privacy
tests come from ``synthetic_coordinates()`` at run time, never from a literal.
"""

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from datetime import timedelta
from email.utils import format_datetime
from pathlib import Path

import httpx
import pytest
import respx
from source_support import NOW, FakeClock, Quiet

from check_personal_data import load_landmarks, synthetic_coordinates
from weatherbot.sources import USER_AGENT
from weatherbot.sources.errors import (
    DocumentedProblem,
    RedirectRefused,
    ResponseTooLarge,
    SourceError,
    SourceHttpError,
    SourceUnavailable,
)
from weatherbot.sources.http import (
    HOST_INTERVALS,
    HostPacer,
    MemoryValidatorStore,
    RedactingFilter,
    open_client,
    redact_url,
    retry_after_seconds,
)

pytestmark = pytest.mark.anyio

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "weatherbot"
ROSTER = "https://www.nhc.noaa.gov/CurrentStorms.json"
OTHER = "https://mapservices.weather.noaa.gov/tropical/rest/services/tropical/x/MapServer?f=json"
NWS_HOST = "api.weather.gov"
OK = 200
NOT_FOUND = 404
NOT_MODIFIED = 304
TWO_CALLS = 2
ATTEMPTS = 4
DELAY = 7.0
LATER = 5.0


@pytest.fixture
def coordinates() -> tuple[str, str]:
    return synthetic_coordinates(load_landmarks(), ())


async def test_the_client_identifies_itself_and_refuses_redirects() -> None:
    async with open_client() as client:
        assert client.headers["user-agent"] == USER_AGENT
        assert client.follow_redirects is False
        assert client.timeout == httpx.Timeout(30.0, connect=10.0)


async def test_every_request_carries_the_user_agent() -> None:
    quiet = Quiet()
    with respx.mock(assert_all_called=True) as router:
        route = router.get(ROSTER).mock(return_value=httpx.Response(200, json={}))
        other = router.get(OTHER).mock(return_value=httpx.Response(200, json={}))
        async with open_client() as client:
            fetcher = quiet.fetcher(client)
            await fetcher.get(ROSTER, source_id="nhc-current-storms")
            await fetcher.get(OTHER, source_id="nhc-map-tropical-weather")
    for answered in (route, other):
        assert answered.call_count == 1
        assert answered.calls.last.request.headers["user-agent"] == USER_AGENT


async def test_no_source_module_disables_tls_or_follows_a_redirect() -> None:
    for path in SOURCE_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"verify\s*=\s*False", text), path.name
        assert not re.search(r"follow_redirects\s*=\s*True", text), path.name


async def test_concurrent_requests_to_one_host_leave_one_interval_apart() -> None:
    clock = FakeClock()
    pacer = HostPacer(clock=clock, sleep=clock.sleep)
    departures: dict[str, list[float]] = {}

    async def send(host: str) -> None:
        await pacer.wait(host)
        departures.setdefault(host, []).append(clock())

    await asyncio.gather(send(NWS_HOST), send(NWS_HOST), send("www.nhc.noaa.gov"))

    first, second = departures[NWS_HOST]
    assert second - first == pytest.approx(HOST_INTERVALS[NWS_HOST])
    # The other host never waited: the only sleep is the second NWS request's.
    assert clock.sleeps == [pytest.approx(HOST_INTERVALS[NWS_HOST])]


async def test_the_fetcher_paces_its_requests_per_host() -> None:
    quiet = Quiet()
    sent: list[tuple[str, float]] = []

    def record(request: httpx.Request) -> httpx.Response:
        sent.append((request.url.host, quiet.clock()))
        return httpx.Response(200, json={})

    with respx.mock as router:
        router.get(url__regex=r"https://(api\.weather\.gov|www\.nhc\.noaa\.gov)/.*").mock(
            side_effect=record
        )
        async with open_client() as client:
            fetcher = quiet.fetcher(client)
            await asyncio.gather(
                fetcher.get(f"https://{NWS_HOST}/a", source_id="nws-zones"),
                fetcher.get(f"https://{NWS_HOST}/b", source_id="nws-zones"),
                fetcher.get(ROSTER, source_id="nhc-current-storms"),
            )
    nws = [moment for host, moment in sent if host == NWS_HOST]
    assert nws[1] - nws[0] == pytest.approx(HOST_INTERVALS[NWS_HOST])
    assert quiet.clock.sleeps == [pytest.approx(HOST_INTERVALS[NWS_HOST])]


async def test_a_503_is_retried_after_a_jittered_backoff() -> None:
    quiet = Quiet()
    with respx.mock as router:
        route = router.get(ROSTER).mock(
            side_effect=[httpx.Response(503), httpx.Response(200, json={"activeStorms": []})]
        )
        async with open_client() as client:
            result = await quiet.fetcher(client).get(ROSTER, source_id="nhc-current-storms")
    assert result.status == OK
    assert route.call_count == TWO_CALLS
    # Full jitter: the seeded fraction (one half) of the 1-second ceiling.
    assert quiet.backoff.sleeps == [0.5]


async def test_a_429_waits_for_its_retry_after() -> None:
    quiet = Quiet()
    with respx.mock as router:
        router.get(ROSTER).mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "3"}),
                httpx.Response(200, json={}),
            ]
        )
        async with open_client() as client:
            await quiet.fetcher(client).get(ROSTER, source_id="nhc-current-storms")
    assert quiet.backoff.sleeps == [3.0]


async def test_retry_after_reads_seconds_and_http_dates() -> None:
    assert retry_after_seconds(f"{DELAY:.0f}", NOW) == DELAY
    assert (
        retry_after_seconds(format_datetime(NOW + timedelta(seconds=LATER), usegmt=True), NOW)
        == LATER
    )
    assert retry_after_seconds(format_datetime(NOW - timedelta(seconds=5), usegmt=True), NOW) == 0.0
    assert retry_after_seconds("soon", NOW) is None
    assert retry_after_seconds(None, NOW) is None


async def test_a_retry_after_beyond_sixty_seconds_is_not_waited_for() -> None:
    quiet = Quiet()
    with respx.mock as router:
        route = router.get(ROSTER).mock(
            return_value=httpx.Response(503, headers={"Retry-After": "120"})
        )
        async with open_client() as client:
            with pytest.raises(SourceUnavailable, match="over the 60 s limit"):
                await quiet.fetcher(client).get(ROSTER, source_id="nhc-current-storms")
    assert route.call_count == 1
    assert quiet.backoff.sleeps == []


async def test_attempts_are_bounded_with_exponential_backoff() -> None:
    quiet = Quiet()
    with respx.mock as router:
        route = router.get(ROSTER).mock(side_effect=httpx.ConnectError("refused"))
        async with open_client() as client:
            with pytest.raises(SourceUnavailable, match="after 4 attempts") as raised:
                await quiet.fetcher(client).get(ROSTER, source_id="nhc-current-storms")
    assert route.call_count == ATTEMPTS
    assert quiet.backoff.sleeps == [0.5, 1.0, 2.0]
    assert raised.value.kind == "unavailable"
    assert raised.value.source_id == "nhc-current-storms"


async def test_a_404_is_not_retried() -> None:
    quiet = Quiet()
    with respx.mock as router:
        route = router.get(ROSTER).mock(return_value=httpx.Response(404))
        async with open_client() as client:
            with pytest.raises(SourceHttpError) as raised:
                await quiet.fetcher(client).get(ROSTER, source_id="nhc-current-storms")
    assert route.call_count == 1
    assert raised.value.status == NOT_FOUND
    assert quiet.backoff.sleeps == []


async def test_a_declared_problem_is_a_documented_problem_without_its_detail(
    coordinates: tuple[str, str],
) -> None:
    lat, lon = coordinates
    url = f"https://{NWS_HOST}/points/{lat},{lon}"
    problem = {
        "type": "https://api.weather.gov/problems/InvalidPoint",
        "title": "Invalid Point",
        "detail": f"Unable to provide data for requested point {lat},{lon}",
    }
    with respx.mock as router:
        router.get(url).mock(
            return_value=httpx.Response(
                404, json=problem, headers={"content-type": "application/problem+json"}
            )
        )
        async with open_client() as client:
            with pytest.raises(DocumentedProblem) as raised:
                await Quiet().fetcher(client).get(url, source_id="nws-points", problems=(404,))
    assert raised.value.problem_type == problem["type"]
    assert raised.value.title == "Invalid Point"
    assert lat not in str(raised.value)
    assert lon not in str(raised.value)


async def test_a_declared_problem_status_without_problem_json_is_an_http_error() -> None:
    with respx.mock as router:
        router.get(ROSTER).mock(return_value=httpx.Response(404, text="gone"))
        async with open_client() as client:
            with pytest.raises(SourceHttpError):
                await (
                    Quiet()
                    .fetcher(client)
                    .get(ROSTER, source_id="nhc-current-storms", problems=(404,))
                )


async def test_a_body_over_the_cap_is_refused() -> None:
    with respx.mock as router:
        router.get(ROSTER).mock(return_value=httpx.Response(200, content=b"x" * 1025))
        async with open_client() as client:
            with pytest.raises(ResponseTooLarge, match="1024 byte cap"):
                await (
                    Quiet()
                    .fetcher(client)
                    .get(ROSTER, source_id="nhc-current-storms", max_bytes=1024)
                )


async def test_a_streamed_body_without_a_length_stops_at_the_cap() -> None:
    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(10):
            yield b"x" * 512

    with respx.mock as router:
        router.get(ROSTER).mock(return_value=httpx.Response(200, content=chunks()))
        async with open_client() as client:
            with pytest.raises(ResponseTooLarge, match="more than the 1024 byte cap"):
                await (
                    Quiet()
                    .fetcher(client)
                    .get(ROSTER, source_id="nhc-current-storms", max_bytes=1024)
                )


async def test_a_redirect_is_refused_naming_only_its_host(coordinates: tuple[str, str]) -> None:
    lat, lon = coordinates
    target = f"https://elsewhere.example/points/{lat},{lon}?lat={lat}&lon={lon}"
    with respx.mock as router:
        route = router.get(ROSTER).mock(
            return_value=httpx.Response(302, headers={"location": target})
        )
        async with open_client() as client:
            with pytest.raises(RedirectRefused) as raised:
                await Quiet().fetcher(client).get(ROSTER, source_id="nhc-current-storms")
    assert route.call_count == 1
    assert raised.value.target_host == "elsewhere.example"
    assert "elsewhere.example" in str(raised.value)
    assert lat not in str(raised.value)
    assert lon not in str(raised.value)


async def test_a_304_reuses_the_stored_body_and_hash() -> None:
    quiet = Quiet()
    store = MemoryValidatorStore()
    validators = {"etag": '"v1"', "last-modified": "Mon, 12 Oct 2026 23:40:00 GMT"}

    def answer(request: httpx.Request) -> httpx.Response:
        if request.headers.get("if-none-match") == '"v1"':
            assert request.headers["if-modified-since"] == validators["last-modified"]
            return httpx.Response(304, headers={"etag": '"v1"'})
        return httpx.Response(200, content=b'{"activeStorms": []}', headers=validators)

    with respx.mock as router:
        route = router.get(ROSTER).mock(side_effect=answer)
        async with open_client() as client:
            fetcher = quiet.fetcher(client)
            fetcher.validators = store
            first = await fetcher.get(ROSTER, source_id="nhc-current-storms")
            second = await fetcher.get(ROSTER, source_id="nhc-current-storms")
    assert route.call_count == TWO_CALLS
    assert not first.not_modified
    assert second.not_modified
    assert second.status == NOT_MODIFIED
    assert second.body == first.body
    assert second.sha256 == first.sha256
    provenance = second.provenance()
    assert provenance.not_modified
    assert provenance.etag == '"v1"'


async def test_a_304_to_an_unconditional_request_is_an_error() -> None:
    with respx.mock as router:
        router.get(ROSTER).mock(return_value=httpx.Response(304))
        async with open_client() as client:
            with pytest.raises(SourceHttpError, match="unconditional"):
                await Quiet().fetcher(client).get(ROSTER, source_id="nhc-current-storms")


async def test_only_allowlisted_headers_are_kept() -> None:
    with respx.mock as router:
        router.get(ROSTER).mock(
            return_value=httpx.Response(
                200, json={}, headers={"set-cookie": "session=1", "etag": '"e"'}
            )
        )
        async with open_client() as client:
            result = await Quiet().fetcher(client).get(ROSTER, source_id="nhc-current-storms")
    assert "set-cookie" not in result.headers
    assert result.headers["etag"] == '"e"'


def test_urls_are_redacted_in_every_form_request_coordinates_recognizes(
    coordinates: tuple[str, str],
) -> None:
    lat, lon = coordinates
    urls = [
        f"https://{NWS_HOST}/points/{lat},{lon}",
        f"https://{NWS_HOST}/points/{lat}%2C{lon}/forecast",
        f"https://{NWS_HOST}/alerts/active?point={lat},{lon}",
        f"https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat}&lon={lon}",
        f"https://example.invalid/q?latitude={lat}&longitude={lon}",
    ]
    for url in urls:
        shown = redact_url(url)
        assert lat not in shown
        assert lon not in shown
        assert "<redacted>" in shown
    assert redact_url(urls[3]).startswith("nominatim.openstreetmap.org/reverse?format=jsonv2&")


def test_the_redacting_filter_cleans_records_above_debug(coordinates: tuple[str, str]) -> None:
    lat, lon = coordinates
    message = f"looked up https://{NWS_HOST}/points/{lat},{lon} and {lat}, {lon}"
    info = logging.LogRecord("weatherbot", logging.INFO, __file__, 1, message, None, None)
    debug = logging.LogRecord("weatherbot", logging.DEBUG, __file__, 1, message, None, None)
    assert RedactingFilter().filter(info)
    assert RedactingFilter().filter(debug)
    assert lat not in info.getMessage()
    assert lon not in info.getMessage()
    assert debug.getMessage() == message


async def test_no_record_above_debug_and_no_error_carries_a_coordinate(
    coordinates: tuple[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    lat, lon = coordinates
    points = f"https://{NWS_HOST}/points/{lat},{lon}"
    alerts = f"https://{NWS_HOST}/alerts/active?point={lat},{lon}"
    reverse = f"https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat}&lon={lon}"
    problem = httpx.Response(
        404,
        json={"type": "about:blank", "title": f"No data at {lat},{lon}"},
        headers={"content-type": "application/problem+json"},
    )
    errors: list[SourceError] = []
    caplog.set_level(logging.DEBUG, logger="weatherbot.sources")
    with respx.mock as router:
        router.get(points).mock(side_effect=[problem, httpx.Response(302), httpx.Response(200)])
        router.get(alerts).mock(side_effect=[httpx.Response(503)] * 4 + [httpx.Response(400)])
        router.get(reverse).mock(
            side_effect=[httpx.Response(500), httpx.Response(200, content=b"x" * 2048)]
        )
        async with open_client() as client:
            fetcher = Quiet().fetcher(client)
            for _ in range(2):
                try:
                    await fetcher.get(points, source_id="nws-points", problems=(404,))
                except SourceError as error:
                    errors.append(error)
            for _ in range(2):
                try:
                    await fetcher.get(alerts, source_id="nws-alerts-point")
                except SourceError as error:
                    errors.append(error)
            try:
                await fetcher.get(reverse, source_id="geocode-nominatim", max_bytes=1024)
            except SourceError as error:
                errors.append(error)
            await fetcher.get(points, source_id="nws-points")

    assert {type(error) for error in errors} == {
        DocumentedProblem,
        RedirectRefused,
        SourceUnavailable,
        SourceHttpError,
        ResponseTooLarge,
    }
    for error in errors:
        assert lat not in str(error)
        assert lon not in str(error)
    above_debug = [record for record in caplog.records if record.levelno > logging.DEBUG]
    assert above_debug
    for record in above_debug:
        assert lat not in record.getMessage()
        assert lon not in record.getMessage()
    # Only DEBUG records name the full URL.
    assert any(points in record.getMessage() for record in caplog.records)
