# src/weatherbot/web/routes/notifications.py
"""``GET /api/notifications``: recent stored notifications with decisions and deliveries."""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Annotated, Final, cast

from fastapi import APIRouter, Query, Request

from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.notifications import NotificationService, StoredNotification
from weatherbot.web.routes.alerts import local_iso, named_zone
from weatherbot.web.schemas import (
    NotificationDecisionResponse,
    NotificationDeliveryResponse,
    NotificationItemResponse,
    NotificationsResponse,
)

if TYPE_CHECKING:
    from weatherbot.web.app import WebState

router = APIRouter()

DEFAULT_NOTIFICATIONS_LIMIT: Final = 20
MAX_NOTIFICATIONS_LIMIT: Final = 500


def notification_to_response(item: StoredNotification) -> NotificationItemResponse:
    """Convert a ``StoredNotification`` into a ``NotificationItemResponse``."""
    zone = named_zone(item.location_time_zone)
    return NotificationItemResponse(
        id=item.id,
        location=item.location_name,
        time_zone=item.location_time_zone,
        assessment_id=item.assessment_id,
        cycle_id=item.cycle_id,
        kind=item.kind,
        level=int(item.level) if item.level is not None else None,
        escalation=item.escalation,
        title=item.title,
        body=item.body,
        created_at=item.created_at,
        created_at_local=local_iso(item.created_at, zone),
        deliveries=tuple(
            NotificationDeliveryResponse(
                id=d.id,
                channel=d.channel,
                attempted_at=d.attempted_at,
                result=d.result,
                detail=d.detail,
            )
            for d in item.deliveries
        ),
        decisions=tuple(
            NotificationDecisionResponse(
                id=dec.id,
                location=dec.location_name,
                assessment_id=dec.assessment_id,
                change_position=dec.change_position,
                trigger=dec.trigger,
                event_key=dec.event_key,
                decision=dec.decision,
                level_after=int(dec.level_after) if dec.level_after is not None else None,
                notification_id=dec.notification_id,
                decided_at=dec.decided_at,
            )
            for dec in item.decisions
        ),
    )


def notifications_to_responses(
    items: Sequence[StoredNotification],
) -> tuple[NotificationItemResponse, ...]:
    """Convert a sequence of ``StoredNotification`` items into response models."""
    return tuple(notification_to_response(item) for item in items)


@router.get("/api/notifications")
def get_notifications(
    request: Request,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_NOTIFICATIONS_LIMIT,
            description="Maximum number of notifications to return, newest first.",
        ),
    ] = DEFAULT_NOTIFICATIONS_LIMIT,
) -> NotificationsResponse:
    """Return the newest stored notifications with their policy decisions and deliveries."""
    state = cast("WebState", request.app.state.web)
    service = NotificationService(
        state.database.engine,
        settings=state.settings,
        now=state.clock,
    )
    stored = service.recent(limit=limit)
    return NotificationsResponse(
        limit=limit,
        notifications=notifications_to_responses(stored),
        notice=NOTICE,
    )
