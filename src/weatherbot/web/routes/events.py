# src/weatherbot/web/routes/events.py
"""``GET /api/events``: server-sent event stream for open dashboard pages."""

from collections.abc import AsyncIterable
from typing import TYPE_CHECKING, Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.sse import EventSourceResponse

from weatherbot.services.events import HubEvent, SubscriberLimitError, Subscription
from weatherbot.web.schemas import StreamEvent

if TYPE_CHECKING:
    from weatherbot.web.app import WebState

router = APIRouter()


def hub_event_to_stream_event(event: HubEvent) -> StreamEvent:
    """Convert an internal ``HubEvent`` into a ``StreamEvent`` response model."""
    return StreamEvent(
        id=event.id,
        kind=event.kind,
        at=event.at,
        invalidate=event.invalidate,
        started_at=event.started_at,
        cycle_id=event.cycle_id,
        runner=str(event.runner) if event.runner is not None else None,
        trigger=str(event.trigger) if event.trigger is not None else None,
        status=str(event.status) if event.status is not None else None,
        snapshot_id=event.snapshot_id,
        location=event.location,
        assessment_id=event.assessment_id,
        level=event.level,
        complete=event.complete,
        notification_id=event.notification_id,
        notification_kind=event.notification_kind,
        escalation=event.escalation,
        title=event.title,
        body=event.body,
        display=event.display,
    )


def _open_subscription(request: Request) -> Subscription:
    state = cast("WebState", request.app.state.web)
    try:
        return state.hub.subscribe()
    except SubscriberLimitError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


@router.get("/api/events", response_class=EventSourceResponse)
async def stream_events(
    sub: Annotated[Subscription, Depends(_open_subscription)],
) -> AsyncIterable[StreamEvent]:
    """Stream ``hello`` followed by live ``StreamEvent`` payloads until closed."""
    try:
        yield hub_event_to_stream_event(sub.hello)
        async for event in sub:
            yield hub_event_to_stream_event(event)
    finally:
        sub.close()
