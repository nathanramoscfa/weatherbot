# tests/live/test_live_nws.py
"""Live smoke tests of the NWS and Nominatim clients, with the public landmarks only.

Marked ``live`` and ``enable_socket``: they run only with ``pytest -m live``
(``.github/workflows/live-smoke.yml`` on dispatch). Nominatim gets one request per
landmark, two in all, as its usage policy allows.
"""

import httpx
import pytest

from check_personal_data import load_landmarks
from weatherbot.models import LatLon, Location, NwsCoverage
from weatherbot.sources import nominatim, nws
from weatherbot.sources.http import Fetcher, open_client

pytestmark = [pytest.mark.live, pytest.mark.enable_socket, pytest.mark.anyio]


def point_of(key: str) -> tuple[float, float]:
    found = next(item for item in load_landmarks() if item.key == key)
    return float(found.lat), float(found.lon)


async def test_the_miami_dade_landmark_its_alerts_and_its_three_zones() -> None:
    lat, lon = point_of("miami-dade")
    async with open_client() as client:
        fetcher = Fetcher(client)
        coverage = (await nws.lookup_point(fetcher, lat, lon)).records
        assert isinstance(coverage, NwsCoverage)
        location = Location(
            name="Miami-Dade landmark", point=LatLon(latitude=lat, longitude=lon), nws=coverage
        )
        alerts = await nws.fetch_alerts(fetcher, location)
        # The register: the landmark's fire-weather zone shares its forecast zone's id.
        zones = [
            (await nws.fetch_zone(fetcher, "county", coverage.county_zone)).records,
            (await nws.fetch_zone(fetcher, "forecast", coverage.forecast_zone)).records,
            (await nws.fetch_zone(fetcher, "fire", coverage.forecast_zone)).records,
        ]
    assert (coverage.county_zone, coverage.cwa) == ("FLC086", "MFL")
    assert [r.source_id for r in alerts.responses] == [
        "nws-alerts-point",
        "nws-alerts-zone",
        "nws-alerts-zone",
    ]
    for alert in alerts.records:
        assert alert.found_by
    assert [zone.type for zone in zones] == ["county", "public", "fire"]
    assert all(zone.geometry.is_valid for zone in zones)


async def test_the_nassau_landmark_is_outside_coverage_and_asks_for_no_alert() -> None:
    lat, lon = point_of("nassau")
    requested: list[str] = []

    async def count(request: httpx.Request) -> None:
        requested.append(request.url.path)

    async with open_client() as client:
        client.event_hooks["request"].append(count)
        fetcher = Fetcher(client)
        coverage = (await nws.lookup_point(fetcher, lat, lon)).records
        location = Location(name="Nassau landmark", point=LatLon(latitude=lat, longitude=lon))
        alerts = await nws.fetch_alerts(fetcher, location)
    assert isinstance(coverage, nws.OutsideNwsCoverage)
    assert coverage.problem_type == nws.INVALID_POINT
    assert alerts.records == ()
    assert len(requested) == 1


async def test_one_reverse_lookup_per_landmark() -> None:
    async with open_client() as client:
        fetcher = Fetcher(client)
        places = [
            (await nominatim.reverse_geocode(fetcher, *point_of(key))).records
            for key in ("miami-dade", "nassau")
        ]
    assert [place.country_code if place else None for place in places] == ["us", "bs"]
    assert all(place and "OpenStreetMap" in place.licence for place in places)
