# src/weatherbot/web/routes/notifications.py
"""``GET /api/notifications`` and ``GET /api/notifications/channels``."""

import os
from collections.abc import Sequence
from typing import TYPE_CHECKING, Annotated, Final, Literal, cast
from urllib.parse import urlsplit

from fastapi import APIRouter, Query, Request

from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.notifications import (
    NotificationService,
    StoredDelivery,
    StoredNotification,
)
from weatherbot.services.toast import APP_ID, MISSING_IDENTITY, TOAST_OFF
from weatherbot.web.routes.alerts import local_iso, named_zone
from weatherbot.web.schemas import (
    NotificationChannelsResponse,
    NotificationChannelStatusResponse,
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
type _NonMutedResult = Literal["delivered", "failed", "disabled", "unavailable"]


def _non_muted_result(delivery: StoredDelivery | None) -> _NonMutedResult | None:
    if delivery is None or delivery.result == "muted":
        return None
    return delivery.result


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


@router.get("/api/notifications/channels")
def get_notification_channels(request: Request) -> NotificationChannelsResponse:
    """Return the configured state and latest non-muted delivery of the four channels."""
    state = cast("WebState", request.app.state.web)
    service = NotificationService(
        state.database.engine,
        settings=state.settings,
        now=state.clock,
    )
    env = os.environ if state.environ is None else state.environ

    latest_log = service.latest_delivery("log")
    log_status = NotificationChannelStatusResponse(
        name="log",
        state="on",
        detail="Stored in SQLite (notifications and notification_deliveries).",
        last_result=_non_muted_result(latest_log),
        last_attempted_at=latest_log.attempted_at if latest_log is not None else None,
    )

    latest_toast = service.latest_delivery("toast")
    if not state.windows:
        toast_state: Literal["on", "off", "unconfigured"] = "off"
        toast_detail = "Not Windows: there is no toast channel."
    elif not state.settings.notifications.toast:
        toast_state = "off"
        toast_detail = TOAST_OFF
    elif not state.is_toast_registered():
        toast_state = "unconfigured"
        toast_detail = MISSING_IDENTITY
    else:
        toast_state = "on"
        toast_detail = f"Windows desktop toast ({APP_ID})."
    toast_status = NotificationChannelStatusResponse(
        name="toast",
        state=toast_state,
        detail=toast_detail,
        last_result=_non_muted_result(latest_toast),
        last_attempted_at=latest_toast.attempted_at if latest_toast is not None else None,
    )

    latest_browser = service.latest_delivery("browser")
    if state.settings.notifications.browser:
        browser_state: Literal["on", "off", "unconfigured"] = "on"
        browser_detail = "Server-sent event stream (/api/events); per-browser toggle below."
    else:
        browser_state = "off"
        browser_detail = "Turned off by [notifications] browser."
    browser_status = NotificationChannelStatusResponse(
        name="browser",
        state=browser_state,
        detail=browser_detail,
        last_result=_non_muted_result(latest_browser),
        last_attempted_at=latest_browser.attempted_at if latest_browser is not None else None,
    )

    latest_ntfy = service.latest_delivery("ntfy")
    if not state.settings.notifications.ntfy:
        ntfy_state: Literal["on", "off", "unconfigured"] = "off"
        ntfy_detail = "Turned off by [notifications] ntfy."
    else:
        topic = env.get("WEATHERBOT_NTFY_TOPIC", "").strip()
        if not topic:
            ntfy_state = "unconfigured"
            ntfy_detail = "Set WEATHERBOT_NTFY_TOPIC in the environment and restart serve."
        else:
            host = (
                urlsplit(state.settings.notifications.ntfy_server).hostname
                or state.settings.notifications.ntfy_server
            )
            token = bool(env.get("WEATHERBOT_NTFY_TOKEN", "").strip())
            ntfy_state = "on"
            ntfy_detail = f"Server {host} ({'bearer token set' if token else 'no bearer token'})."
    ntfy_status = NotificationChannelStatusResponse(
        name="ntfy",
        state=ntfy_state,
        detail=ntfy_detail,
        last_result=_non_muted_result(latest_ntfy),
        last_attempted_at=latest_ntfy.attempted_at if latest_ntfy is not None else None,
    )

    return NotificationChannelsResponse(
        channels=(log_status, toast_status, browser_status, ntfy_status),
        notice=NOTICE,
    )
