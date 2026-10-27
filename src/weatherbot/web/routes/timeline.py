# src/weatherbot/web/routes/timeline.py
"""``GET /api/timeline``: merged chronological feed of assessments and notifications."""

from http import HTTPStatus
from typing import TYPE_CHECKING, Annotated, Final, cast

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
) -> TimelineResponse:
    """Return a merged newest-first feed of stored assessments and notifications."""
    state = cast("WebState", request.app.state.web)
    engine = state.database.engine

    locations = LocationRepository(engine, now=state.clock).list()
    by_name = {loc.name: loc for loc in locations}
    if location is not None and location not in by_name:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="unknown location query parameter: location",
        )

    target_locations = (by_name[location],) if location is not None else locations
    assessment_repo = AssessmentRepository(engine, now=state.clock)
    entries: list[TimelineEntryResponse] = [
        _assessment_timeline_entry(loc, stored)
        for loc in target_locations
        for stored in assessment_repo.history(loc.name, limit)
    ]

    notification_service = NotificationService(
        engine,
        settings=state.settings,
        now=state.clock,
    )
    fetch_limit = (
        limit if location is None else min(MAX_TIMELINE_LIMIT, limit * max(len(locations), 2))
    )
    for item in notification_service.recent(limit=fetch_limit):
        if location is not None and item.location_name != location:
            continue
        entries.append(_notification_timeline_entry(item))

    # Order newest first; on identical timestamps, notifications placed at the cycle
    # instant appear alongside (just ahead of) the assessment that triggered them.
    entries.sort(
        key=lambda e: (e.occurred_at, 1 if e.kind == "notification" else 0, e.id),
        reverse=True,
    )

    return TimelineResponse(
        location=location,
        limit=limit,
        entries=tuple(entries[:limit]),
        notice=NOTICE,
    )
