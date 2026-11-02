# src/weatherbot/web/routes/outlook.py
"""``GET /api/outlook`` and ``GET /api/outlook/{basin}/{horizon}``: NHC's official outlook maps.

The graphics come from the latest stored snapshot: its outlook graphics' basins, horizons,
sizes, and times, and each PNG read from the raw-response cache by the SHA-256 its
provenance records (``raw_cache.stored_png``), so the page's ``img-src 'self'`` holds and
nothing is downloaded. The image route takes no path: a basin or horizon it does not know,
a snapshot without that graphic, and a body that is missing, altered, or not a PNG all
answer 404. Both routes are plain functions, so FastAPI runs their reads in its pool.
"""

from http import HTTPStatus
from typing import TYPE_CHECKING, Final, cast

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.persistence.raw_cache import stored_png
from weatherbot.services.persistence.repositories import SnapshotRepository
from weatherbot.web.map_layers import get_cached_snapshot_bundle
from weatherbot.web.schemas import OutlookGraphicResponse, OutlookGraphicsResponse

if TYPE_CHECKING:
    from weatherbot.models import OutlookGraphic
    from weatherbot.web.app import WebState

router = APIRouter()

NO_GRAPHIC: Final = "the latest snapshot holds no stored outlook graphic for that basin and horizon"
PNG_RESPONSES: Final[dict[int | str, dict[str, object]]] = {
    200: {"content": {"image/png": {}}, "description": "The official PNG."},
    404: {"description": "No such stored graphic."},
}


@router.get("/api/outlook")
def get_outlook(request: Request) -> OutlookGraphicsResponse:
    """Return the official outlook graphics the latest snapshot stored."""
    state = cast("WebState", request.app.state.web)
    bundle = get_cached_snapshot_bundle(SnapshotRepository(state.database.engine))
    if bundle is None:
        return OutlookGraphicsResponse(snapshot_id=None, graphics=(), notice=NOTICE)
    return OutlookGraphicsResponse(
        snapshot_id=bundle.snapshot.snapshot_id,
        graphics=tuple(
            OutlookGraphicResponse(
                basin=graphic.basin,
                horizon=graphic.horizon,
                width_px=graphic.width_px,
                height_px=graphic.height_px,
                sha256=graphic.provenance.sha256,
                fetched_at=graphic.provenance.fetched_at,
                issued_at=graphic.provenance.issued_at,
            )
            for graphic in bundle.snapshot.outlook_graphics
        ),
        notice=NOTICE,
    )


@router.get(
    "/api/outlook/{basin}/{horizon}",
    response_class=Response,
    responses=PNG_RESPONSES,
)
def get_outlook_graphic(request: Request, basin: str, horizon: str) -> Response:
    """Return one official outlook graphic's PNG from the latest snapshot, or 404."""
    state = cast("WebState", request.app.state.web)
    bundle = get_cached_snapshot_bundle(SnapshotRepository(state.database.engine))
    graphics: tuple[OutlookGraphic, ...] = bundle.snapshot.outlook_graphics if bundle else ()
    graphic = next(
        (item for item in graphics if item.basin == basin and item.horizon == horizon), None
    )
    png = stored_png(state.database.engine, graphic.provenance.sha256) if graphic else None
    if png is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=NO_GRAPHIC)
    return Response(content=png, media_type="image/png")
