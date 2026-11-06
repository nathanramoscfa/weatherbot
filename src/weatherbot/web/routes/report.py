# src/weatherbot/web/routes/report.py
"""``GET /api/report``: downloadable, self-contained HTML threat report."""

from datetime import UTC
from http import HTTPStatus
from typing import TYPE_CHECKING, Annotated, Final, cast

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from weatherbot.services.persistence.repositories import LocationNotFoundError
from weatherbot.services.report import (
    REPORT_HEADER_CSP,
    NoReportAssessmentError,
    ReportService,
    render_report,
)

if TYPE_CHECKING:
    from weatherbot.web.app import WebState

router = APIRouter()

UNKNOWN_LOCATION_DETAIL: Final = "Location not found."
NO_ASSESSMENT_DETAIL: Final = "No assessment is stored yet; run a check first."

REPORT_RESPONSES: Final[dict[int | str, dict[str, object]]] = {
    200: {
        "content": {"text/html": {"schema": {"type": "string"}}},
        "description": "Self-contained HTML threat report attachment.",
    },
    404: {"description": "The requested location is not stored."},
    409: {"description": "No stored assessment is available to build the report."},
}


@router.get(
    "/api/report",
    response_class=HTMLResponse,
    responses=REPORT_RESPONSES,
)
def get_report(
    request: Request,
    location: Annotated[
        str | None,
        Query(description="Export this stored location only; every location when omitted."),
    ] = None,
    *,
    briefing: Annotated[
        bool,
        Query(description="Include each location's latest unwithheld stored AI briefing."),
    ] = False,
) -> HTMLResponse:
    """Build and return the self-contained HTML threat report as a file download."""
    state = cast("WebState", request.app.state.web)
    service = ReportService(state.database.engine, now=state.clock)
    target = location or None
    try:
        data = service.build(target, with_briefing=briefing)
    except LocationNotFoundError:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=UNKNOWN_LOCATION_DETAIL,
        ) from None
    except NoReportAssessmentError:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=NO_ASSESSMENT_DETAIL,
        ) from None

    stamp = data.generated_at.astimezone(UTC).strftime("%Y%m%dT%H%MZ")
    headers = {
        "Content-Disposition": f'attachment; filename="weatherbot-report-{stamp}.html"',
        "Content-Security-Policy": REPORT_HEADER_CSP,
    }
    return HTMLResponse(
        content=render_report(data),
        media_type="text/html; charset=utf-8",
        headers=headers,
    )
