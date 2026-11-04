# tests/services/test_location_no_county.py
"""Tests for adding and storing NWS marine-zone locations without a county."""

import json
from typing import Any, cast

import httpx
import pytest
import respx
from cli_support import quiet_fetcher
from source_support import NOW, entry, recorded
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from check_personal_data import load_landmarks
from weatherbot.services.config import AppPaths
from weatherbot.services.locations import LocationError, LocationService
from weatherbot.services.network import Network
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import LocationRepository
from weatherbot.services.persistence.tables import LocationRow
from weatherbot.sources import nominatim, nws

pytestmark = pytest.mark.anyio

GEOJSON = {"content-type": "application/geo+json"}
JSON = {"content-type": "application/json; charset=utf-8"}


def _miami_point() -> tuple[float, float, str, str]:
    found = next(item for item in load_landmarks() if item.key == "miami-dade")
    return float(found.lat), float(found.lon), str(found.lat), str(found.lon)


def _marine_points_payload() -> bytes:
    directory = recorded("nws-points")
    doc = cast(
        "dict[str, Any]",
        json.loads(directory.payload(entry(directory, "points-miami-dade.json"))),
    )
    props = cast("dict[str, Any]", doc["properties"])
    props.pop("county", None)
    props.pop("fireWeatherZone", None)
    props["forecastZone"] = "https://api.weather.gov/zones/forecast/AMZ630"
    props["cwa"] = "NH2"
    return json.dumps(doc).encode("utf-8")


def _marine_zone_payload() -> bytes:
    directory = recorded("nws-zones")
    doc = cast(
        "dict[str, Any]",
        json.loads(directory.payload(entry(directory, "zone-forecast-FLZ173.json"))),
    )
    props = cast("dict[str, Any]", doc["properties"])
    props["id"] = "AMZ630"
    props["type"] = "coastal"
    props["state"] = None
    return json.dumps(doc).encode("utf-8")


def _reverse_payload() -> bytes:
    directory = recorded("geocode-nominatim")
    return directory.payload(entry(directory, "reverse-miami-dade.json"))


async def test_no_county_location_round_trips_and_supports_forecast_polygon() -> None:
    lat, lon, lat_str, lon_str = _miami_point()
    paths = AppPaths.resolve()

    with open_database(paths, now=lambda: NOW) as database:
        service = LocationService(
            database.engine,
            paths=paths,
            network=Network(make_fetcher=quiet_fetcher),
            now=lambda: NOW,
        )

        # 1. Refuses polygon="county" when NWS names no county, without coordinates
        with respx.mock(assert_all_called=True) as router:
            router.get(nws.points_url(lat, lon)).mock(
                return_value=httpx.Response(200, content=_marine_points_payload(), headers=GEOJSON)
            )
            with pytest.raises(LocationError, match="names no county") as exc_info:
                await service.add("Marine County Attempt", lat, lon, polygon="county")
            assert lat_str not in str(exc_info.value)
            assert lon_str not in str(exc_info.value)

        # 2. Adds with polygon="forecast" on coastal zone AMZ630 (state: null)
        with respx.mock(assert_all_called=True) as router:
            router.get(nws.points_url(lat, lon)).mock(
                return_value=httpx.Response(200, content=_marine_points_payload(), headers=GEOJSON)
            )
            router.get(nws.zone_url("forecast", "AMZ630")).mock(
                return_value=httpx.Response(200, content=_marine_zone_payload(), headers=GEOJSON)
            )
            router.get(nominatim.reverse_url(lat, lon)).mock(
                return_value=httpx.Response(200, content=_reverse_payload(), headers=JSON)
            )
            added = await service.add("Marine Forecast", lat, lon, polygon="forecast")

        assert added.nws is not None
        assert added.nws.cwa == "NH2"
        assert added.nws.forecast_zone == "AMZ630"
        assert added.nws.county_zone is None
        assert added.polygon is not None

        # Underlying row stores "" in nws_county_zone so nws_coverage_whole holds
        with Session(database.engine) as session:
            row = session.scalar(select(LocationRow).where(LocationRow.name == "Marine Forecast"))
            assert row is not None
            assert row.nws_county_zone == ""

        # Round-trip reads "" back as None
        repo = LocationRepository(database.engine)
        fetched = repo.get("Marine Forecast")
        assert fetched is not None
        assert fetched.nws is not None
        assert fetched.nws.county_zone is None
        assert fetched == added


def test_nws_coverage_whole_check_still_rejects_partial_nulls() -> None:
    lat, lon, _, _ = _miami_point()
    paths = AppPaths.resolve()
    with open_database(paths, now=lambda: NOW) as database, Session(database.engine) as session:
        session.add(
            LocationRow(
                name="Partial",
                latitude=lat,
                longitude=lon,
                nws_cwa="MFL",
                nws_forecast_zone="AMZ630",
                nws_county_zone=None,
                nws_time_zone="America/New_York",
                nws_city="Miami",
                nws_state="FL",
                evacuation_order_in_effect=False,
                created_at=NOW,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
