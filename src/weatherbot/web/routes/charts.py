# src/weatherbot/web/routes/charts.py
"""``GET /api/charts``: compact level and wind-probability series for one watched location."""

from http import HTTPStatus
from typing import TYPE_CHECKING, Annotated, Final, cast

from fastapi import APIRouter, HTTPException, Query, Request

from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.persistence.repositories import (
    AssessmentRepository,
    LocationRepository,
)
from weatherbot.web.routes.alerts import local_iso, named_zone
from weatherbot.web.routes.assessments import wind_reading_response
from weatherbot.web.schemas import ChartLevelPointResponse, ChartsResponse

if TYPE_CHECKING:
    from weatherbot.web.app import WebState

router = APIRouter()

DEFAULT_CHARTS_LIMIT: Final = 200
MAX_CHARTS_LIMIT: Final = 500


@router.get("/api/charts")
def get_charts(
    request: Request,
    location: Annotated[
        str,
        Query(
            min_length=1,
            description="Watched location name whose level and wind-probability series to read.",
        ),
    ],
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_CHARTS_LIMIT,
            description="Maximum number of stored assessments to inspect, newest first.",
        ),
    ] = DEFAULT_CHARTS_LIMIT,
) -> ChartsResponse:
    """Return compact threat-level and wind-probability series for one watched location."""
    state = cast("WebState", request.app.state.web)
    engine = state.database.engine

    locations = LocationRepository(engine, now=state.clock).list()
    by_name = {loc.name: loc for loc in locations}
    if location not in by_name:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="unknown location query parameter: location",
        )

    loc = by_name[location]
    time_zone = loc.nws.time_zone if loc.nws is not None else None
    zone = named_zone(time_zone)

    assessment_repo = AssessmentRepository(engine, now=state.clock)
    points = assessment_repo.level_points(loc.name, limit)
    wind = assessment_repo.wind_series(loc.name, limit)

    return ChartsResponse(
        location=loc.name,
        time_zone=time_zone,
        limit=limit,
        levels=tuple(
            ChartLevelPointResponse(
                id=point.id,
                as_of=point.as_of,
                as_of_local=local_iso(point.as_of, zone),
                level=int(point.level),
                label=point.level.label,
                rule=str(point.rule),
                complete=point.complete,
            )
            for point in points
        ),
        wind=tuple(wind_reading_response(item) for item in wind),
        notice=NOTICE,
    )
