# src/weatherbot/services/locations.py
"""The locations service: add a location once, list and remove them, and set the toggle.

``LocationService.add(name, lat, lon, polygon=None)`` checks the name and the coordinates
before any request, asks NWS ``/points`` whether the NWS covers the point, fetches the
county or forecast zone's shape when ``polygon`` asks for one (US locations only),
reverse-geocodes the point through Nominatim once, and stores the location with that
result. Nothing re-geocodes a stored location, and nothing else sends a location's
coordinates anywhere but ``api.weather.gov``. ``set_evacuation_order`` turns the
operator's evacuation-order toggle on or off and records when; removing a location
removes its alert observations and its assessments with it.

A location's coordinates are the operator's. No error message, log record, or ``repr``
here repeats them; they leave the machine only in the NWS and Nominatim request URLs.
"""

import logging
import math
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Final, Literal

from sqlalchemy import Engine

from weatherbot.models import LatLon, Location
from weatherbot.services.network import Network, product_key
from weatherbot.services.persistence.raw_cache import RawResponseCache
from weatherbot.services.persistence.repositories import LocationExistsError, LocationRepository
from weatherbot.sources import nominatim, nws
from weatherbot.sources.http import FetchResult

LOGGER: Final = logging.getLogger("weatherbot.services.locations")

type PolygonKind = Literal["county", "forecast"]
NAME_LENGTH: Final = range(1, 65)
MAX_LATITUDE: Final = 90.0
MAX_LONGITUDE: Final = 180.0


class LocationError(Exception):
    """A location cannot be added or removed as asked. The message repeats no coordinate."""


def _now() -> datetime:
    return datetime.now(UTC)


def check_name(name: str) -> str:
    """Check a location name: 1 to 64 printable characters, not only spaces.

    Args:
        name: The name.

    Returns:
        The name.

    Raises:
        LocationError: The name is empty, too long, or not printable.
    """
    if len(name) not in NAME_LENGTH or not name.isprintable() or not name.strip():
        message = "a location name is 1 to 64 printable characters"
        raise LocationError(message)
    return name


def check_point(lat: float, lon: float) -> LatLon:
    """Check a point: finite, latitude -90 to 90, longitude -180 to 180.

    Args:
        lat: Degrees north.
        lon: Degrees east.

    Returns:
        The point.

    Raises:
        LocationError: A value is not finite or out of range; the message never repeats it.
    """
    if not (math.isfinite(lat) and -MAX_LATITUDE <= lat <= MAX_LATITUDE):
        message = "the latitude must be a number from -90 to 90"
        raise LocationError(message)
    if not (math.isfinite(lon) and -MAX_LONGITUDE <= lon <= MAX_LONGITUDE):
        message = "the longitude must be a number from -180 to 180"
        raise LocationError(message)
    return LatLon(latitude=lat, longitude=lon)


class LocationService:
    """The watched locations, added once with their coverage and geocoding."""

    def __init__(
        self,
        engine: Engine,
        *,
        network: Network | None = None,
        now: Callable[[], datetime] = _now,
    ) -> None:
        """Create the service on an open database.

        Args:
            engine: The database.
            network: The timeout and the fetcher factory.
            now: The clock.
        """
        self._engine = engine
        self._network = network or Network()
        self._now = now
        self._repository = LocationRepository(engine, now=now)

    async def add(
        self, name: str, lat: float, lon: float, polygon: PolygonKind | None = None
    ) -> Location:
        """Add a location: check it, look up its NWS coverage, geocode it once, store it.

        Args:
            name: Its name, unique.
            lat: Degrees north.
            lon: Degrees east.
            polygon: ``county`` or ``forecast`` to store that NWS zone's shape.

        Returns:
            The stored location.

        Raises:
            LocationError: The name or the point is wrong, the name is taken, or a polygon
                was asked for a location outside NWS coverage.
        """
        check_name(name)
        point = check_point(lat, lon)
        if self._repository.get(name) is not None:
            message = f"a location named {name!r} already exists"
            raise LocationError(message)
        cache = RawResponseCache(self._engine)
        answers: list[FetchResult] = []
        async with self._network.fetcher(cache) as fetcher:
            covered = await nws.lookup_point(fetcher, point.latitude, point.longitude)
            answers.extend(covered.responses)
            coverage = (
                covered.records if not isinstance(covered.records, nws.OutsideNwsCoverage) else None
            )
            if polygon is not None and coverage is None:
                message = "the NWS does not cover this location, so it has no zone polygon"
                raise LocationError(message)
            shape = None
            if polygon is not None and coverage is not None:
                zone_id = coverage.county_zone if polygon == "county" else coverage.forecast_zone
                zone = await nws.fetch_zone(fetcher, polygon, zone_id)
                answers.extend(zone.responses)
                shape = zone.records.geometry
            geocoded = await nominatim.reverse_geocode(fetcher, point.latitude, point.longitude)
            answers.extend(geocoded.responses)
        place = geocoded.records
        location = Location(
            name=name,
            point=point,
            polygon=shape,
            country_code=place.country_code.upper() if place and place.country_code else None,
            display_name=place.display_name if place else None,
            nws=coverage,
            geocoding=geocoded.responses[0].provenance() if geocoded.responses else None,
        )
        try:
            self._repository.add(location)
        except LocationExistsError:
            message = f"a location named {name!r} already exists"
            raise LocationError(message) from None
        for answer in answers:
            cache.save_fetch(answer, answer.source_id, _key(answer, name))
        LOGGER.info(
            "added location %r: %s NWS coverage, %s polygon, %s",
            name,
            "inside" if coverage else "outside",
            polygon or "no",
            "geocoded" if place else "no place found by reverse geocoding",
        )
        return location

    def list(self) -> tuple[Location, ...]:
        """Return every stored location, by name.

        Returns:
            The locations.
        """
        return self._repository.list()

    def get(self, name: str) -> Location | None:
        """Return the location of a name.

        Args:
            name: The name.

        Returns:
            The location, or ``None``.
        """
        return self._repository.get(name)

    def set_evacuation_order(self, name: str, *, on: bool) -> tuple[Location, bool]:
        """Turn a location's evacuation-order toggle on or off.

        The toggle holds the location at level 4 or above while it is on. Setting it to
        the state it is already in changes nothing, so its instant stays the one it was
        set at.

        Args:
            name: The location's name.
            on: Whether the toggle is on.

        Returns:
            The location, and whether the toggle changed.

        Raises:
            LocationError: No location has that name.
        """
        location = self._repository.get(name)
        if location is None:
            message = f"no location is named {name!r}"
            raise LocationError(message)
        if location.evacuation_order_in_effect == on:
            return location, False
        updated = self._repository.set_evacuation_order(name, on=on, at=self._now())
        if updated is None:  # removed by another process since it was read
            message = f"no location is named {name!r}"
            raise LocationError(message)
        LOGGER.info("location %r: evacuation-order toggle %s", name, "on" if on else "off")
        return updated, True

    def remove(self, name: str) -> None:
        """Remove a location, its alert observations, and its assessments.

        Args:
            name: The name.

        Raises:
            LocationError: No location has that name.
        """
        if not self._repository.remove(name):
            message = f"no location is named {name!r}"
            raise LocationError(message)
        LOGGER.info("removed location %r", name)


def _key(answer: FetchResult, name: str) -> str:
    # The point and reverse-geocoding paths are the same for every location once the
    # coordinates are redacted: name the location instead.
    if answer.source_id in {nws.POINTS, "geocode-nominatim"}:
        return f"{product_key(answer)}<{name}>"
    return product_key(answer)
