# src/weatherbot/web/routes/health.py
"""``GET /api/health``: process, database, scheduler, heartbeat, UI, and AI status.

The ``ai`` block comes from ``AiService.state()``, computed without a request: the state,
the reason, and today's spend against the cap, never the credential. With no AI service
(the demonstration server, the OpenAPI export), it reads ``off`` with the reason
``disabled``.
"""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

from fastapi import APIRouter, Request

from weatherbot import __version__
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.health import staleness
from weatherbot.services.persistence.database import current_revision, head_revision
from weatherbot.services.persistence.repositories import HeartbeatRepository
from weatherbot.services.schedule import PRODUCT_HOURS
from weatherbot.web.schemas import (
    AiHealth,
    DatabaseHealth,
    HealthResponse,
    HeartbeatHealth,
    SchedulerHealth,
    UiHealth,
)

if TYPE_CHECKING:
    from weatherbot.web.app import WebState
    from weatherbot.web.static_files import StaticBundle

router = APIRouter()


def next_product_hour(now: datetime) -> datetime:
    """Return the next UTC instant among ``PRODUCT_HOURS`` strictly after ``now``."""
    utc_now = now.astimezone(UTC)
    base_day = utc_now.replace(hour=0, minute=0, second=0, microsecond=0)
    for hour in PRODUCT_HOURS:
        candidate = base_day.replace(hour=hour)
        if candidate > utc_now:
            return candidate
    return base_day + timedelta(days=1)


def ai_health(state: "WebState") -> AiHealth:
    """Read the AI's state for the health document, without a request."""
    if state.ai is None:
        return AiHealth(state="off", reason="disabled", spent_micro_usd=0, cap_micro_usd=0)
    current = state.ai.state()
    today = current.today
    return AiHealth(
        state=current.state,
        reason=current.reason,
        spent_micro_usd=today.spent_micro_usd + today.reserved_micro_usd,
        cap_micro_usd=today.limit_micro_usd,
    )


@router.get("/api/health")
def get_health(request: Request) -> HealthResponse:
    """Return process, database, scheduler, heartbeat, and built-UI health."""
    state = cast("WebState", request.app.state.web)
    bundle = cast("StaticBundle", request.app.state.static_bundle)
    now = state.clock().astimezone(UTC)

    revision = current_revision(state.database.engine)
    head = head_revision()
    database = DatabaseHealth(
        revision=revision,
        head=head,
        current=revision == head,
    )

    rows = HeartbeatRepository(state.database.engine, now=state.clock).rows()
    evaluated = staleness(rows, now=now)
    heartbeats = [
        HeartbeatHealth(
            kind=item.kind,
            name=item.name,
            last_success_at=item.last_success_at,
            age_s=item.age_s,
            consecutive_failures=row.consecutive_failures,
            expected_every_s=item.expected_every_s,
            stale=item.stale,
        )
        for row, item in zip(rows, evaluated, strict=True)
    ]

    serve_item = next(
        (item for item in evaluated if item.kind == "runner" and item.name == "serve"),
        None,
    )
    scheduler = (
        SchedulerHealth(
            last_success_at=serve_item.last_success_at,
            expected_every_s=serve_item.expected_every_s,
            stale=serve_item.stale,
        )
        if serve_item is not None
        else SchedulerHealth(
            last_success_at=None,
            expected_every_s=None,
            stale=False,
        )
    )

    return HealthResponse(
        version=__version__,
        started_at=state.started_at.astimezone(UTC),
        now=now,
        database=database,
        scheduler=scheduler,
        heartbeats=heartbeats,
        stale=any(item.stale for item in heartbeats),
        next_product_at=next_product_hour(now),
        ui=UiHealth(present=bundle.present, index_sha256=bundle.index_sha256),
        corpus=state.corpus is not None,
        ai=ai_health(state),
        notice=NOTICE,
    )
