# src/weatherbot/web/app.py
"""Application factory and shared state for the local FastAPI web application."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from starlette.responses import JSONResponse

from weatherbot import __version__
from weatherbot.services.config import AppPaths, SettingOrigin, Settings
from weatherbot.services.events import BrowserChannel, EventHub
from weatherbot.services.locations import SearchCache
from weatherbot.services.monitor import CycleResult, CycleTrigger
from weatherbot.services.network import Network
from weatherbot.services.notifications import Channel, LogChannel
from weatherbot.services.ntfy import ntfy_channel
from weatherbot.services.persistence.database import Database
from weatherbot.services.replay import ReplayCorpus, ReplayTimelines
from weatherbot.services.retention import RetentionService
from weatherbot.services.schedule import MonitorSchedule
from weatherbot.services.tasks import ON_WINDOWS
from weatherbot.services.toast import TOAST_OFF, NullChannel, system_identity
from weatherbot.web.guards import install_guards
from weatherbot.web.routes.actions import router as actions_router
from weatherbot.web.routes.ai import router as ai_router
from weatherbot.web.routes.alerts import router as alerts_router
from weatherbot.web.routes.assessments import router as assessments_router
from weatherbot.web.routes.charts import router as charts_router
from weatherbot.web.routes.disclaimer import router as disclaimer_router
from weatherbot.web.routes.events import router as events_router
from weatherbot.web.routes.health import router as health_router
from weatherbot.web.routes.locations import router as locations_router
from weatherbot.web.routes.map import router as map_router
from weatherbot.web.routes.notifications import router as notifications_router
from weatherbot.web.routes.outlook import router as outlook_router
from weatherbot.web.routes.replay import router as replay_router
from weatherbot.web.routes.report import router as report_router
from weatherbot.web.routes.settings import router as settings_router
from weatherbot.web.routes.storms import router as storms_router
from weatherbot.web.routes.timeline import router as timeline_router
from weatherbot.web.static_files import install_static_routes, load_static_bundle

if TYPE_CHECKING:
    from weatherbot.services.ai.chat import ChatService
    from weatherbot.services.ai.service import AiService

LOGGER: Final = logging.getLogger("weatherbot.web.app")
MAX_AI_STREAMS: Final = 4
"""At most this many AI streams run at once, server-wide; a fifth answers 429."""


@dataclass
class _ActionState:
    """Mutable rate-limit and single-flight bookkeeping for write endpoints."""

    cycle_in_flight: bool = False
    last_cycle_at: datetime | None = None
    last_test_notification_at: datetime | None = None
    last_search_at: datetime | None = None
    search_cache: SearchCache = field(default_factory=SearchCache)
    cycle_task: asyncio.Task[CycleResult | None] | None = None
    default_schedule: MonitorSchedule | None = None
    ai_streams: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(MAX_AI_STREAMS))
    chat: "ChatService | None" = None
    last_setting_origins: tuple[SettingOrigin, ...] | None = None
    retention_in_flight: bool = False
    replay_timelines: ReplayTimelines | None = None


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
    ai: "AiService | None" = None
    """The AI service ``serve`` built; ``None`` reads as AI off (``disabled``)."""
    environ: Mapping[str, str] | None = None
    windows: bool = ON_WINDOWS
    toast_registered: bool | None = None
    _actions: _ActionState = field(default_factory=_ActionState, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Populate default channels and network settings when omitted."""
        if not self.channels:
            default_channels: list[Channel] = [
                LogChannel(),
                NullChannel(TOAST_OFF if not self.settings.notifications.toast else "test"),
                BrowserChannel(self.hub, enabled=self.settings.notifications.browser),
            ]
            ntfy = ntfy_channel(self.settings, environ=self.environ)
            if ntfy is not None:
                default_channels.append(ntfy)
            object.__setattr__(self, "channels", tuple(default_channels))
        if self.network.timeout_seconds is None:
            object.__setattr__(
                self,
                "network",
                Network(
                    timeout_seconds=self.settings.http.timeout_seconds,
                    make_fetcher=self.network.make_fetcher,
                ),
            )

    def is_toast_registered(self) -> bool:
        """Whether the Windows toast AUMID is registered."""
        if self.toast_registered is not None:
            return self.toast_registered
        if not self.windows:
            return False
        return bool(system_identity().registered())

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
    def last_search_at(self) -> datetime | None:
        """UTC instant when the last forward search was requested via ``/api/locations/search``."""
        return self._actions.last_search_at

    @property
    def search_cache(self) -> SearchCache:
        """Shared in-memory Nominatim forward-search cache."""
        return self._actions.search_cache

    def mark_search(self, at: datetime) -> None:
        """Record when ``POST /api/locations/search`` last ran."""
        self._actions.last_search_at = at

    @property
    def replay_timelines(self) -> ReplayTimelines | None:
        """Return or construct the bounded replay-timeline cache when a corpus is configured."""
        if self.corpus is None:
            return None
        if self._actions.replay_timelines is None:
            self._actions.replay_timelines = ReplayTimelines(
                self.corpus,
                self.settings.engine.thresholds(),
            )
        return self._actions.replay_timelines

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

    @property
    def ai_streams(self) -> asyncio.Semaphore:
        """The slots of the AI streams running now, at most ``MAX_AI_STREAMS``."""
        return self._actions.ai_streams

    def chat_service(self, ai: "AiService") -> "ChatService":
        """Return the one chat service, whose conversations live in this server's memory."""
        if self._actions.chat is None:
            from weatherbot.services.ai.chat import ChatService  # noqa: PLC0415 - AI loads on demand

            self._actions.chat = ChatService(ai)
        return self._actions.chat

    @property
    def last_setting_origins(self) -> tuple[SettingOrigin, ...] | None:
        """Last successfully parsed setting origins, or ``None`` before the first read."""
        return self._actions.last_setting_origins

    def set_last_setting_origins(self, origins: tuple[SettingOrigin, ...]) -> None:
        """Record the latest successfully parsed setting origins."""
        self._actions.last_setting_origins = origins

    @property
    def retention_in_flight(self) -> bool:
        """Whether a manual retention prune from ``POST /api/retention/run`` is running."""
        return self._actions.retention_in_flight

    def mark_retention_in_flight(self, *, in_flight: bool) -> None:
        """Update the in-flight flag for ``POST /api/retention/run``."""
        self._actions.retention_in_flight = in_flight

    def run_retention_prune(self, cutoff: datetime) -> None:
        """Execute a background retention prune for ``cutoff`` and publish ``settings``."""
        try:
            service = RetentionService(
                self.database.engine,
                self.paths,
                now=self.clock,
            )
            service.run(cutoff)
        except Exception as error:  # noqa: BLE001 - background prune logs and clears flag
            LOGGER.warning("manual retention prune failed (%s)", type(error).__name__)
        finally:
            self._actions.retention_in_flight = False
            self.hub.publish("health", None, ("settings", "health"))

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
    app.include_router(charts_router)
    app.include_router(storms_router)
    app.include_router(alerts_router)
    app.include_router(timeline_router)
    app.include_router(notifications_router)
    app.include_router(settings_router)
    app.include_router(disclaimer_router)
    app.include_router(map_router)
    app.include_router(replay_router)
    app.include_router(report_router)
    app.include_router(events_router)
    app.include_router(actions_router)
    app.include_router(ai_router)
    app.include_router(outlook_router)
    install_static_routes(app, bundle)
    return app
