# src/weatherbot/web/app.py
"""Application factory and shared state for the local FastAPI web application."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from starlette.responses import JSONResponse

from weatherbot import __version__
from weatherbot.services.config import AppPaths, SettingOrigin, Settings
from weatherbot.services.events import BrowserChannel, EventHub
from weatherbot.services.monitor import CycleResult, CycleTrigger
from weatherbot.services.network import Network
from weatherbot.services.notifications import Channel, LogChannel
from weatherbot.services.persistence.database import Database
from weatherbot.services.replay import ReplayCorpus
from weatherbot.services.schedule import MonitorSchedule
from weatherbot.services.toast import TOAST_OFF, NullChannel
from weatherbot.web.guards import install_guards
from weatherbot.web.routes.actions import router as actions_router
from weatherbot.web.routes.alerts import router as alerts_router
from weatherbot.web.routes.assessments import router as assessments_router
from weatherbot.web.routes.disclaimer import router as disclaimer_router
from weatherbot.web.routes.events import router as events_router
from weatherbot.web.routes.health import router as health_router
from weatherbot.web.routes.locations import router as locations_router
from weatherbot.web.routes.map import router as map_router
from weatherbot.web.routes.notifications import router as notifications_router
from weatherbot.web.routes.replay import router as replay_router
from weatherbot.web.routes.settings import router as settings_router
from weatherbot.web.routes.storms import router as storms_router
from weatherbot.web.routes.timeline import router as timeline_router
from weatherbot.web.static_files import install_static_routes, load_static_bundle

LOGGER: Final = logging.getLogger("weatherbot.web.app")


@dataclass
class _ActionState:
    """Mutable rate-limit and single-flight bookkeeping for write endpoints."""

    cycle_in_flight: bool = False
    last_cycle_at: datetime | None = None
    last_test_notification_at: datetime | None = None
    cycle_task: asyncio.Task[CycleResult | None] | None = None
    default_schedule: MonitorSchedule | None = None


@dataclass(frozen=True)
class WebState:
    """Shared dependencies for the local FastAPI application."""

    database: Database
    paths: AppPaths
    settings: Settings
    setting_origins: tuple[SettingOrigin, ...] = ()
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    static_dir: Path | None = None
    corpus: ReplayCorpus | None = None
    hub: EventHub = field(default_factory=EventHub)
    channels: tuple[Channel, ...] = ()
    network: Network = field(default_factory=Network)
    request_cycle: Callable[[], Awaitable[CycleResult]] | None = None
    _actions: _ActionState = field(default_factory=_ActionState, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Populate default channels and network settings when omitted."""
        if not self.channels:
            default_channels: tuple[Channel, ...] = (
                LogChannel(),
                NullChannel(TOAST_OFF if not self.settings.notifications.toast else "test"),
                BrowserChannel(self.hub, enabled=self.settings.notifications.browser),
            )
            object.__setattr__(self, "channels", default_channels)
        if self.network.timeout_seconds is None:
            object.__setattr__(
                self,
                "network",
                Network(
                    timeout_seconds=self.settings.http.timeout_seconds,
                    make_fetcher=self.network.make_fetcher,
                ),
            )

    @property
    def cycle_in_flight(self) -> bool:
        """Whether a manual cycle requested through ``POST /api/cycles`` is currently running."""
        return self._actions.cycle_in_flight

    @property
    def last_cycle_at(self) -> datetime | None:
        """UTC instant when the last manual cycle was started via ``POST /api/cycles``."""
        return self._actions.last_cycle_at

    @property
    def last_test_notification_at(self) -> datetime | None:
        """UTC instant when the last test notification was sent via ``/api/notifications/test``."""
        return self._actions.last_test_notification_at

    @property
    def cycle_task(self) -> asyncio.Task[CycleResult | None] | None:
        """The most recent background manual cycle task, if any."""
        return self._actions.cycle_task

    @property
    def schedule(self) -> MonitorSchedule:
        """Return or construct the fallback ``MonitorSchedule`` for ``request_cycle``."""
        if self._actions.default_schedule is None:
            self._actions.default_schedule = MonitorSchedule(
                self.database.engine,
                self.paths,
                settings=self.settings,
                runner="serve",
                clock=self.clock,
                make_fetcher=self.network.make_fetcher,
                channels=self.channels,
                listeners=(self.hub.cycle_listener,),
            )
        return self._actions.default_schedule

    def mark_test_notification(self, at: datetime) -> None:
        """Record when ``POST /api/notifications/test`` last ran."""
        self._actions.last_test_notification_at = at

    def start_manual_cycle(
        self,
        at: datetime,
        *,
        trigger: CycleTrigger = "manual",
    ) -> asyncio.Task[CycleResult | None]:
        """Start ``request_cycle`` as a single-flight background task on the running loop."""
        self._actions.cycle_in_flight = True
        self._actions.last_cycle_at = at

        async def _runner() -> CycleResult | None:
            try:
                if self.request_cycle is not None:
                    return await self.request_cycle()
                return await self.schedule.execute_cycle(trigger)
            except Exception as error:  # noqa: BLE001 - background cycle logs and releases lock
                LOGGER.warning(
                    "manual cycle failed (%s)",
                    type(error).__name__,
                )
                return None
            finally:
                self._actions.cycle_in_flight = False

        task = asyncio.create_task(_runner())
        self._actions.cycle_task = task
        return task


def _sanitize_validation_errors(errors: Sequence[object]) -> list[dict[str, object]]:
    """Keep only ``loc``, ``msg``, and ``type`` for each error; never echo ``input``."""
    cleaned: list[dict[str, object]] = []
    for item in errors:
        if isinstance(item, dict):
            entry = cast("dict[str, object]", item)
            loc_raw = entry.get("loc", ())
            if isinstance(loc_raw, (list, tuple)):
                loc_items = cast("Sequence[object]", loc_raw)
                loc: list[int | str] = [
                    part if isinstance(part, int) else str(part) for part in loc_items
                ]
            else:
                loc = []
            cleaned.append(
                {
                    "loc": loc,
                    "msg": str(entry.get("msg", "")),
                    "type": str(entry.get("type", "value_error")),
                }
            )
    return cleaned


def create_app(state: WebState) -> FastAPI:
    """Create the local-only FastAPI application with its guards, routes, and static bundle."""
    app = FastAPI(
        title="Weatherbot",
        version=__version__,
        openapi_url="/api/openapi.json",
        docs_url=None,
        redoc_url=None,
    )
    bundle = load_static_bundle(state.static_dir)
    app.state.web = state
    app.state.static_bundle = bundle

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": _sanitize_validation_errors(exc.errors())},
        )

    @app.exception_handler(ResponseValidationError)
    async def handle_response_validation_error(
        _request: Request, exc: ResponseValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"detail": _sanitize_validation_errors(exc.errors())},
        )

    install_guards(app)
    app.include_router(health_router)
    app.include_router(locations_router)
    app.include_router(assessments_router)
    app.include_router(storms_router)
    app.include_router(alerts_router)
    app.include_router(timeline_router)
    app.include_router(notifications_router)
    app.include_router(settings_router)
    app.include_router(disclaimer_router)
    app.include_router(map_router)
    app.include_router(replay_router)
    app.include_router(events_router)
    app.include_router(actions_router)
    install_static_routes(app, bundle)
    return app
