# src/weatherbot/web/routes/locations.py
"""``GET /api/locations``: stored watched locations with coordinates and zone polygons."""

from typing import TYPE_CHECKING, cast

from fastapi import APIRouter, Request

from weatherbot.models import Location
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.persistence.repositories import LocationRepository
from weatherbot.web.map_layers import geometry_to_response
from weatherbot.web.schemas import (
    LocationPreferencesResponse,
    LocationResponse,
    LocationsResponse,
)

if TYPE_CHECKING:
    from weatherbot.web.app import WebState

router = APIRouter()


def location_to_response(location: Location) -> LocationResponse:
    """Convert a domain ``Location`` into a ``LocationResponse``."""
    prefs = location.preferences
    return LocationResponse(
        name=location.name,
        latitude=location.point.latitude,
        longitude=location.point.longitude,
        country_code=location.country_code,
        display_name=location.display_name,
        nws=location.nws,
        has_polygon=location.polygon is not None,
        polygon=(geometry_to_response(location.polygon) if location.polygon is not None else None),
        evacuation_order_in_effect=location.evacuation_order_in_effect,
        evacuation_order_set_at=location.evacuation_order_set_at,
        breakpoint_span=location.breakpoint_span,
        preferences=LocationPreferencesResponse(
            toast=prefs.toast,
            browser=prefs.browser,
            phone=prefs.phone,
            phone_min_level=prefs.phone_min_level,
        ),
    )


to_location_response = location_to_response


@router.get("/api/locations")
def get_locations(request: Request) -> LocationsResponse:
    """Return every stored watched location in name order."""
    state = cast("WebState", request.app.state.web)
    locations = LocationRepository(state.database.engine, now=state.clock).list()
    return LocationsResponse(
        locations=tuple(location_to_response(loc) for loc in locations),
        notice=NOTICE,
    )
