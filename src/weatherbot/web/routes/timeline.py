# src/weatherbot/web/routes/timeline.py
"""``GET /api/timeline``: merged chronological feed of assessments and notifications."""

import sys
from datetime import UTC, datetime
from http import HTTPStatus
from typing import TYPE_CHECKING, Annotated, Final, Literal, cast

from fastapi import APIRouter, HTTPException, Query, Request

from weatherbot.models import AlertLevel, Location
from weatherbot.services.assessments import RULE_TRIGGERS
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.notifications import NotificationService, StoredNotification
from weatherbot.services.persistence.repositories import (
    AssessmentRepository,
    LocationRepository,
    StoredAssessment,
)
from weatherbot.web.routes.alerts import local_iso, named_zone
from weatherbot.web.routes.assessments import change_responses
from weatherbot.web.routes.notifications import notification_to_response
from weatherbot.web.schemas import (
    ThreatLevelResponse,
    TimelineEntryResponse,
    TimelineResponse,
)

if TYPE_CHECKING:
    from weatherbot.web.app import WebState

router = APIRouter()

DEFAULT_TIMELINE_LIMIT: Final = 50
MAX_TIMELINE_LIMIT: Final = 500
type _CursorKind = Literal["assessment", "notification"]


def _encode_cursor(occurred_at: datetime, kind: _CursorKind, entry_id: int) -> str:
    utc_str = occurred_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return f"{utc_str}|{kind}|{entry_id}"


def _parse_before(raw: str) -> tuple[datetime, _CursorKind, int]:
    parts = raw.split("|")
    if len(parts) != 3:  # noqa: PLR2004 - cursor has three pipe-delimited components
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail="invalid timeline cursor: before",
        )
    raw_iso, raw_kind, raw_id = parts
    if raw_kind not in ("assessment", "notification"):
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail="invalid timeline cursor: before",
        )
    try:
        occurred_at = datetime.fromisoformat(raw_iso)
        entry_id = int(raw_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail="invalid timeline cursor: before",
        ) from exc
    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None or entry_id < 1:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail="invalid timeline cursor: before",
        )
    return occurred_at.astimezone(UTC), raw_kind, entry_id


def _entry_sort_key(entry: TimelineEntryResponse) -> tuple[datetime, int, int]:
    return (entry.occurred_at, 1 if entry.kind == "notification" else 0, entry.id)


def _assessment_timeline_entry(
    location: Location, stored: StoredAssessment
) -> TimelineEntryResponse:
    assessment = stored.assessment
    level = assessment.level
    time_zone = location.nws.time_zone if location.nws is not None else None
    zone = named_zone(time_zone)
    return TimelineEntryResponse(
        kind="assessment",
        id=stored.id,
        occurred_at=assessment.as_of,
        occurred_at_local=local_iso(assessment.as_of, zone),
        location=location.name,
        time_zone=time_zone,
        level=ThreatLevelResponse(
            number=int(level),
            label=level.label,
            actions=level.actions,
        ),
        rule=str(assessment.rule),
        rule_trigger=RULE_TRIGGERS[assessment.rule],
        complete=assessment.complete,
        snapshot_id=assessment.snapshot_id,
        stored_at=stored.stored_at,
        changes=change_responses(stored.changes),
    )


def _notification_timeline_entry(item: StoredNotification) -> TimelineEntryResponse:
    converted = notification_to_response(item)
    level_response: ThreatLevelResponse | None = None
    if item.level is not None:
        alert_level = AlertLevel(int(item.level))
        level_response = ThreatLevelResponse(
            number=int(alert_level),
            label=alert_level.label,
            actions=alert_level.actions,
        )
    return TimelineEntryResponse(
        kind="notification",
        id=converted.id,
        occurred_at=converted.created_at,
        occurred_at_local=converted.created_at_local,
        location=converted.location,
        time_zone=converted.time_zone,
        level=level_response,
        notification_kind=converted.kind,
        escalation=converted.escalation,
        title=converted.title,
        body=converted.body,
        decisions=converted.decisions,
        deliveries=converted.deliveries,
    )


@router.get("/api/timeline")
def get_timeline(
    request: Request,
    location: Annotated[
        str | None,
        Query(description="Optional stored location name to filter timeline entries."),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_TIMELINE_LIMIT,
            description="Maximum number of timeline entries to return, newest first.",
        ),
    ] = DEFAULT_TIMELINE_LIMIT,
    before: Annotated[
        str | None,
        Query(
            description=(
                "Optional opaque cursor from a previous TimelineResponse.next_before to read "
                "entries strictly after that cursor in newest-first order."
            ),
        ),
    ] = None,
) -> TimelineResponse:
    """Return a merged newest-first feed of stored assessments and notifications."""
    state = cast("WebState", request.app.state.web)
    engine = state.database.engine

    cursor: tuple[datetime, _CursorKind, int] | None = (
        _parse_before(before) if before is not None else None
    )

    locations = LocationRepository(engine, now=state.clock).list()
    by_name = {loc.name: loc for loc in locations}
    if location is not None and location not in by_name:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="unknown location query parameter: location",
        )

    assessment_before: tuple[datetime, int] | datetime | None = None
    notification_before: tuple[datetime, int] | datetime | None = None
    cursor_sort_key: tuple[datetime, int, int] | None = None
    if cursor is not None:
        cursor_at, cursor_kind, cursor_id = cursor
        cursor_sort_key = (cursor_at, 1 if cursor_kind == "notification" else 0, cursor_id)
        if cursor_kind == "assessment":
            assessment_before = (cursor_at, cursor_id)
            notification_before = cursor_at
        else:
            assessment_before = (cursor_at, sys.maxsize)
            notification_before = (cursor_at, cursor_id)

    page_limit = limit + 1
    target_locations = (by_name[location],) if location is not None else locations
    assessment_repo = AssessmentRepository(engine, now=state.clock)
    entries: list[TimelineEntryResponse] = [
        _assessment_timeline_entry(loc, stored)
        for loc in target_locations
        for stored in assessment_repo.history(loc.name, page_limit, before=assessment_before)
    ]

    notification_service = NotificationService(
        engine,
        settings=state.settings,
        now=state.clock,
    )
    fetch_limit = (
        page_limit
        if location is None
        else min(MAX_TIMELINE_LIMIT + 1, page_limit * max(len(locations), 2))
    )
    for item in notification_service.recent(limit=fetch_limit, before=notification_before):
        if location is not None and item.location_name != location:
            continue
        entries.append(_notification_timeline_entry(item))

    if cursor_sort_key is not None:
        entries = [entry for entry in entries if _entry_sort_key(entry) < cursor_sort_key]

    # Order newest first; on identical timestamps, notifications placed at the cycle
    # instant appear alongside (just ahead of) the assessment that triggered them.
    entries.sort(key=_entry_sort_key, reverse=True)

    has_more = len(entries) > limit
    page = tuple(entries[:limit])
    next_before = (
        _encode_cursor(page[-1].occurred_at, page[-1].kind, page[-1].id)
        if has_more and page
        else None
    )

    return TimelineResponse(
        location=location,
        limit=limit,
        entries=page,
        next_before=next_before,
        notice=NOTICE,
    )
