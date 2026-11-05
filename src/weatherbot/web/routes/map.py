# src/weatherbot/web/routes/map.py
"""Map routes: ``/api/map``, ``/depth``, ``/wind-probabilities``, and ``/advisories``."""

from http import HTTPStatus
from typing import TYPE_CHECKING, Annotated, Final, Literal, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BeforeValidator

from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.persistence.repositories import (
    AssessmentRepository,
    LocationRepository,
    SnapshotRepository,
)
from weatherbot.web.map_layers import (
    build_map_depth_response,
    build_map_response,
    build_wind_probability_response,
    get_cached_snapshot_bundle,
)
from weatherbot.web.schemas import (
    AdvisoryStepResponse,
    MapAdvisoriesResponse,
    MapDepthResponse,
    MapResponse,
    WindProbabilityResponse,
)

if TYPE_CHECKING:
    from weatherbot.web.app import WebState

router = APIRouter()

UNKNOWN_SNAPSHOT_DETAIL: Final = "unknown snapshot parameter: snapshot_id"
DEFAULT_ADVISORY_STEP_LIMIT: Final[int] = 96
MAX_ADVISORY_STEP_LIMIT: Final[int] = 200


def _coerce_threshold_kt(value: object) -> object:
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return value


type WindThresholdQuery = Annotated[Literal[34, 50, 64], BeforeValidator(_coerce_threshold_kt)]


@router.get("/api/map")
def get_map(
    request: Request,
    snapshot_id: UUID | None = None,
) -> MapResponse:
    """Return GeoJSON map layers for the requested (or latest) stored snapshot and locations."""
    state = cast("WebState", request.app.state.web)
    engine = state.database.engine
    snapshot_repo = SnapshotRepository(engine)

    bundle = get_cached_snapshot_bundle(snapshot_repo, snapshot_id=snapshot_id)
    if snapshot_id is not None and bundle is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=UNKNOWN_SNAPSHOT_DETAIL,
        )

    locations = LocationRepository(engine, now=state.clock).list()
    assessment_repo = AssessmentRepository(engine, now=state.clock)
    if snapshot_id is not None:
        assessments = assessment_repo.for_snapshot(snapshot_id)
    else:
        assessments = {loc.name: assessment_repo.latest(loc.name) for loc in locations}

    snapshot = bundle.snapshot if bundle is not None else None
    return build_map_response(
        snapshot,
        locations,
        assessments=assessments,
        is_historical_advisory=snapshot_id is not None,
    )


@router.get("/api/map/depth")
def get_map_depth(
    request: Request,
    snapshot_id: UUID | None = None,
) -> MapDepthResponse:
    """Return wind radii, past track, past points, and peak surge for the requested snapshot."""
    state = cast("WebState", request.app.state.web)
    engine = state.database.engine
    bundle = get_cached_snapshot_bundle(SnapshotRepository(engine), snapshot_id=snapshot_id)
    if snapshot_id is not None and bundle is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=UNKNOWN_SNAPSHOT_DETAIL,
        )
    if bundle is None:
        return build_map_depth_response(None)
    return bundle.depth()


@router.get("/api/map/wind-probabilities")
def get_map_wind_probabilities(
    request: Request,
    threshold_kt: WindThresholdQuery = 34,
    snapshot_id: UUID | None = None,
) -> WindProbabilityResponse:
    """Return cumulative 120-hour wind probability bands for one threshold and snapshot."""
    state = cast("WebState", request.app.state.web)
    engine = state.database.engine
    bundle = get_cached_snapshot_bundle(SnapshotRepository(engine), snapshot_id=snapshot_id)
    if snapshot_id is not None and bundle is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=UNKNOWN_SNAPSHOT_DETAIL,
        )
    if bundle is None:
        return build_wind_probability_response(None, threshold_kt)
    return bundle.wind_probabilities(threshold_kt)


@router.get("/api/map/advisories")
def get_map_advisories(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=MAX_ADVISORY_STEP_LIMIT)] = DEFAULT_ADVISORY_STEP_LIMIT,
) -> MapAdvisoriesResponse:
    """Return the newest stored snapshot per storm and advisory, newest first."""
    state = cast("WebState", request.app.state.web)
    engine = state.database.engine
    steps = SnapshotRepository(engine).advisory_steps(limit)
    return MapAdvisoriesResponse(
        limit=limit,
        steps=tuple(
            AdvisoryStepResponse(
                snapshot_id=step.snapshot_id,
                as_of=step.as_of,
                atcf_id=step.atcf_id,
                storm_name=step.storm_name,
                classification=step.classification,
                advisory=step.advisory,
                issued_at=step.issued_at,
            )
            for step in steps
        ),
        notice=NOTICE,
    )
