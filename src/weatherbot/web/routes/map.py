# src/weatherbot/web/routes/map.py
"""``GET /api/map``: GeoJSON map layers for the latest stored snapshot and locations."""

from typing import TYPE_CHECKING, cast

from fastapi import APIRouter, Request

from weatherbot.services.persistence.repositories import (
    AssessmentRepository,
    LocationRepository,
    SnapshotRepository,
)
from weatherbot.web.map_layers import build_map_response, get_cached_snapshot_bundle
from weatherbot.web.schemas import MapResponse

if TYPE_CHECKING:
    from weatherbot.web.app import WebState

router = APIRouter()


@router.get("/api/map")
def get_map(request: Request) -> MapResponse:
    """Return GeoJSON map layers for the latest stored snapshot and watched locations."""
    state = cast("WebState", request.app.state.web)
    engine = state.database.engine

    locations = LocationRepository(engine, now=state.clock).list()
    assessment_repo = AssessmentRepository(engine, now=state.clock)
    assessments = {loc.name: assessment_repo.latest(loc.name) for loc in locations}

    bundle = get_cached_snapshot_bundle(SnapshotRepository(engine))
    snapshot = bundle.snapshot if bundle is not None else None

    return build_map_response(
        snapshot,
        locations,
        assessments=assessments,
    )
