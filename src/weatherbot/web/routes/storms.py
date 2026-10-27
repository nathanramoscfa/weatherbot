# src/weatherbot/web/routes/storms.py
"""``GET /api/storms``: active tropical cyclones and outlook areas from the latest snapshot."""

from datetime import UTC
from typing import TYPE_CHECKING, cast

from fastapi import APIRouter, Request

from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.persistence.repositories import SnapshotRepository
from weatherbot.web.map_layers import get_cached_snapshot_bundle
from weatherbot.web.schemas import StormsResponse

if TYPE_CHECKING:
    from weatherbot.web.app import WebState

router = APIRouter()


@router.get("/api/storms")
def get_storms(request: Request) -> StormsResponse:
    """Return the latest snapshot's active storms, outlook areas, and wind probabilities."""
    state = cast("WebState", request.app.state.web)
    now = state.clock().astimezone(UTC)
    bundle = get_cached_snapshot_bundle(SnapshotRepository(state.database.engine))
    if bundle is None:
        return StormsResponse(
            snapshot=None,
            storms=(),
            outlook=(),
            wind_probabilities=(),
            notice=NOTICE,
        )
    return StormsResponse(
        snapshot=bundle.summary(now),
        storms=bundle.storm_summaries,
        outlook=bundle.outlook_summaries,
        wind_probabilities=bundle.wind_probability_summaries,
        notice=NOTICE,
    )
