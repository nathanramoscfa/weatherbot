# src/weatherbot/web/routes/actions.py
"""Guarded write routes: locations, evacuation toggle, manual cycle, and test notification."""

import asyncio
import logging
from typing import TYPE_CHECKING, Final, cast

from fastapi import APIRouter, HTTPException, Request, status

from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.locations import (
    LocationError,
    LocationNameTakenError,
    LocationService,
)
from weatherbot.services.monitor import CycleTrigger
from weatherbot.services.network import SourceError
from weatherbot.services.notifications import (
    TEST_BODY,
    TEST_TITLE,
    NotificationService,
)
from weatherbot.web.routes.locations import location_to_response
from weatherbot.web.routes.notifications import notification_to_response
from weatherbot.web.schemas import (
    CreateLocationRequest,
    EvacuationUpdateResponse,
    LocationResponse,
    NotificationItemResponse,
    TestNotificationRequest,
    TriggerCycleRequest,
    TriggerCycleResponse,
    UpdateEvacuationRequest,
)

if TYPE_CHECKING:
    from weatherbot.web.app import WebState

LOGGER: Final = logging.getLogger("weatherbot.web.actions")

router = APIRouter()

MANUAL_TRIGGER: Final[CycleTrigger] = "manual"
CYCLE_COOLDOWN_S: Final = 60.0
TEST_NOTIFICATION_COOLDOWN_S: Final = 10.0


@router.post("/api/locations", status_code=status.HTTP_201_CREATED)
def create_location(
    request: Request,
    body: CreateLocationRequest,
) -> LocationResponse:
    """Validate and add a watched location via ``LocationService.add`` in a worker thread."""
    state = cast("WebState", request.app.state.web)
    service = LocationService(
        state.database.engine,
        network=state.network,
        now=state.clock,
    )
    try:
        location = asyncio.run(
            service.add(
                body.name,
                body.latitude,
                body.longitude,
                polygon=body.polygon,
            )
        )
    except LocationNameTakenError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except LocationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except SourceError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{error.source_id} did not answer ({error.kind})",
        ) from error

    state.hub.record_location_change(
        location.name,
        evacuation_order_in_effect=location.evacuation_order_in_effect,
        evacuation_order_set_at=location.evacuation_order_set_at,
    )
    return location_to_response(location)


@router.put("/api/locations/evacuation")
def update_evacuation(
    request: Request,
    body: UpdateEvacuationRequest,
) -> EvacuationUpdateResponse:
    """Turn a watched location's evacuation-order toggle on or off."""
    state = cast("WebState", request.app.state.web)
    service = LocationService(state.database.engine, now=state.clock)
    try:
        location, changed = service.set_evacuation_order(body.location, on=body.on)
    except LocationError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    state.hub.record_location_change(
        location.name,
        evacuation_order_in_effect=location.evacuation_order_in_effect,
        evacuation_order_set_at=location.evacuation_order_set_at,
    )
    return EvacuationUpdateResponse(
        location=location_to_response(location),
        changed=changed,
        notice=NOTICE,
    )


@router.post("/api/cycles", status_code=status.HTTP_202_ACCEPTED)
async def trigger_cycle(
    request: Request,
    _body: TriggerCycleRequest,
) -> TriggerCycleResponse:
    """Schedule a single-flight ``manual`` cycle on the server's event loop."""
    state = cast("WebState", request.app.state.web)
    if state.cycle_in_flight:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="a manual cycle is already running",
        )
    now = state.clock()
    if state.last_cycle_at is not None:
        elapsed = (now - state.last_cycle_at).total_seconds()
        if 0 <= elapsed < CYCLE_COOLDOWN_S:
            remaining = int(CYCLE_COOLDOWN_S - elapsed) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"wait {remaining} s before starting another manual cycle",
            )

    state.start_manual_cycle(now, trigger=MANUAL_TRIGGER)
    return TriggerCycleResponse(
        status="accepted",
        trigger=MANUAL_TRIGGER,
        started_at=now,
        notice=NOTICE,
    )


@router.post("/api/notifications/test")
async def send_test_notification(
    request: Request,
    _body: TestNotificationRequest,
) -> NotificationItemResponse:
    """Send a ``test`` notification through ``serve``'s channels on the server's loop."""
    state = cast("WebState", request.app.state.web)
    now = state.clock()
    if state.last_test_notification_at is not None:
        elapsed = (now - state.last_test_notification_at).total_seconds()
        if 0 <= elapsed < TEST_NOTIFICATION_COOLDOWN_S:
            remaining = int(TEST_NOTIFICATION_COOLDOWN_S - elapsed) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"wait {remaining} s before sending another test notification",
            )

    state.mark_test_notification(now)
    service = NotificationService(
        state.database.engine,
        settings=state.settings,
        now=state.clock,
        channels=state.channels,
    )
    sent = await service.send("test", title=TEST_TITLE, body=TEST_BODY)
    state.hub.publish(
        "notification",
        {
            "notification_id": sent.id,
            "notification_kind": sent.kind,
            "escalation": sent.escalation,
            "display": False,
        },
        ("notifications", "timeline"),
        deduplicate=True,
    )
    return notification_to_response(sent)
