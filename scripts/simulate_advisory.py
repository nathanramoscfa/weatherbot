# scripts/simulate_advisory.py
"""Simulate a new NHC advisory and Hurricane Warning during ``serve`` in a temp data dir.

Starts the ``serve`` monitor schedule in a temporary data directory with both public
landmarks stored, every HTTP request answered by recorded fixtures through ``respx`` (all
other requests refused), the roster watch at its 1-minute minimum, and the real toast
channel (or an injected fake toast in automated tests). Waits for the ``startup`` cycle to
finish, switches the roster to the next advisory and the Miami-Dade landmark's forecast-zone
alerts to a synthetic ``Hurricane Warning`` built from ``register_alert``'s shape, and
verifies that a level-5 escalation notification for ``"simulated Miami-Dade"`` is stored
within one scheduler interval with a toast delivery reading ``delivered``.
"""

import asyncio
import json
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final, cast

import httpx
from sqlalchemy import Engine

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
for _support_dir in (
    REPO_ROOT / "scripts",
    REPO_ROOT / "tests" / "contract",
    REPO_ROOT / "tests" / "sources",
    REPO_ROOT / "tests" / "cli",
):
    _dir_str = str(_support_dir)
    if _dir_str not in sys.path:
        sys.path.insert(0, _dir_str)

from cli_support import (  # noqa: E402
    ROSTER_URL,
    directory,
    quiet_fetcher,
    recorded_services,
)
from fixture_support import register_alert  # noqa: E402
from source_support import NOW, entry  # noqa: E402

from ladder_data import public_landmarks  # noqa: E402
from weatherbot.models import AlertLevel, Location  # noqa: E402
from weatherbot.services.config import AppPaths, MonitorSettings, NotificationSettings, Settings  # noqa: E402
from weatherbot.services.monitor import CycleResult  # noqa: E402
from weatherbot.services.notifications import (  # noqa: E402
    Channel,
    DeliveryResult,
    LogChannel,
    NotificationService,
    StoredNotification,
)
from weatherbot.services.persistence.database import open_database  # noqa: E402
from weatherbot.services.persistence.repositories import LocationRepository  # noqa: E402
from weatherbot.services.schedule import run_monitor  # noqa: E402
from weatherbot.services.scheduler import RandomSource  # noqa: E402
from weatherbot.services.toast import toast_channel  # noqa: E402

SIMULATED_MIAMI: Final = "simulated Miami-Dade"
FORECAST_ZONE_ID: Final = "FLZ173"
FORECAST_ZONE_URL: Final = f"https://api.weather.gov/zones/forecast/{FORECAST_ZONE_ID}"
FORECAST_ALERTS_URL: Final = f"https://api.weather.gov/alerts/active/zone/{FORECAST_ZONE_ID}"
MAX_INTERVAL_S: Final = 120.0
"""One 60-second roster interval plus 60 seconds for jitter, the cycle, and toast wait."""


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """Outcome of one simulated advisory run."""

    notification: StoredNotification
    toast_result: DeliveryResult
    elapsed_s: float


def _next_advisory_roster() -> bytes:
    """Return the recorded roster JSON with the active storm's advisory advanced to 023."""
    capture = directory("nhc-current-storms")
    (item,) = capture.entries
    document = cast("dict[str, object]", json.loads(capture.payload(item)))
    storms = cast("list[dict[str, object]]", document["activeStorms"])
    first = storms[0]
    for key in ("publicAdvisory", "trackCone"):
        product = first.get(key)
        if isinstance(product, dict):
            product["advNum"] = "023"
    return json.dumps(document).encode("utf-8")


def _hurricane_warning_response(now: datetime) -> httpx.Response:
    """Return a recorded forecast-zone alert response holding one Hurricane Warning."""
    capture = directory("nws-alerts-zone")
    document = cast(
        "dict[str, object]",
        json.loads(capture.payload(entry(capture, "alerts-zone-FLZ173.geojson"))),
    )
    feature = register_alert(now)
    alert_id = "urn:oid:2.49.0.1.840.0.simulated.flz173.hw.1"
    feature["id"] = f"https://api.weather.gov/alerts/{alert_id}"
    props = cast("dict[str, object]", feature["properties"])
    props["id"] = alert_id
    props["event"] = "Hurricane Warning"
    props["headline"] = "Hurricane Warning issued by NWS Miami FL"
    props["affectedZones"] = [FORECAST_ZONE_URL]
    geocode = cast("dict[str, object]", props["geocode"])
    geocode["UGC"] = ["FLZ173"]
    document["features"] = [feature]
    return httpx.Response(
        200,
        content=json.dumps(document).encode("utf-8"),
        headers={"content-type": "application/geo+json"},
    )


def _store_simulated_landmarks(engine: Engine, now: datetime) -> None:
    landmarks = public_landmarks()
    repo = LocationRepository(engine, now=lambda: now)
    for loc in landmarks.values():
        if loc.nws is not None:
            renamed = Location.model_validate(
                {**{k: getattr(loc, k) for k in Location.model_fields}, "name": SIMULATED_MIAMI}
            )
            repo.add(renamed)
        else:
            repo.add(loc)


async def run_simulation(
    work_dir: Path,
    *,
    toast: Channel | None = None,
    clock: Callable[[], datetime] | None = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    random: RandomSource | None = None,
) -> SimulationResult:
    """Run the ``serve`` scheduler through startup and one simulated advisory switch."""
    paths = AppPaths(
        config_dir=work_dir / "config",
        data_dir=work_dir / "data",
    )
    settings = Settings(
        monitor=MonitorSettings(
            roster_interval_minutes=1,
            roster_interval_relevant_minutes=1,
        ),
        notifications=NotificationSettings(toast=True),
    )
    start_wall = time.monotonic()
    active_clock: Callable[[], datetime] = clock or (
        lambda: NOW + timedelta(seconds=time.monotonic() - start_wall)
    )
    active_toast = toast if toast is not None else toast_channel(settings)
    channels: tuple[Channel, ...] = (LogChannel(), active_toast)

    stop = asyncio.Event()
    switched_wall: float | None = None
    switched_clock: datetime | None = None

    with recorded_services() as router, open_database(paths) as database:
        _store_simulated_landmarks(database.engine, active_clock())

        def _on_cycle(result: CycleResult) -> None:
            nonlocal switched_wall, switched_clock
            if result.trigger == "startup" and switched_wall is None:
                switched_wall = time.monotonic()
                switched_clock = active_clock()
                router.get(ROSTER_URL).mock(
                    return_value=httpx.Response(
                        200,
                        content=_next_advisory_roster(),
                        headers={"content-type": "application/json"},
                    )
                )
                router.get(FORECAST_ALERTS_URL).mock(
                    return_value=_hurricane_warning_response(active_clock())
                )
            elif switched_wall is not None and any(
                n.location_name == SIMULATED_MIAMI
                and n.level == AlertLevel.HURRICANE_WARNING
                and n.escalation
                for n in result.notifications
            ):
                stop.set()

        await run_monitor(
            database.engine,
            paths,
            settings=settings,
            runner="serve",
            stop=stop,
            clock=active_clock,
            sleep=sleep,
            random=random,
            make_fetcher=lambda client, store: quiet_fetcher(client, store, now=active_clock()),
            channels=channels,
            listeners=(_on_cycle,),
        )

        stored = NotificationService(database.engine, settings=settings, now=active_clock).recent(
            10
        )

    escalation = next(
        (
            n
            for n in stored
            if n.location_name == SIMULATED_MIAMI
            and n.level == AlertLevel.HURRICANE_WARNING
            and n.escalation
        ),
        None,
    )
    if escalation is None or switched_wall is None or switched_clock is None:
        message = "no level-5 escalation notification was stored for simulated Miami-Dade"
        raise RuntimeError(message)

    toast_delivery = next((d for d in escalation.deliveries if d.channel == "toast"), None)
    if toast_delivery is None or toast_delivery.result != "delivered":
        actual = toast_delivery.result if toast_delivery is not None else "missing"
        message = f"toast delivery did not read delivered (got {actual!r})"
        raise RuntimeError(message)

    clock_elapsed = (escalation.created_at - switched_clock).total_seconds()
    wall_elapsed = time.monotonic() - switched_wall
    elapsed_s = max(clock_elapsed, wall_elapsed)
    if elapsed_s > MAX_INTERVAL_S:
        message = (
            f"notification took {elapsed_s:.2f} s after the advisory switch, "
            f"over the {MAX_INTERVAL_S:.0f} s one-interval limit"
        )
        raise RuntimeError(message)

    return SimulationResult(
        notification=escalation,
        toast_result=toast_delivery.result,
        elapsed_s=elapsed_s,
    )


def main() -> int:
    """Run the simulation in a temporary directory and print the elapsed time and delivery."""
    with tempfile.TemporaryDirectory(prefix="weatherbot-sim-") as tmp:
        outcome = asyncio.run(run_simulation(Path(tmp)))
    sys.stdout.write(
        f"simulated advisory: location={outcome.notification.location_name!r} "
        f"level={int(outcome.notification.level or 0)} "
        f"escalation={outcome.notification.escalation} "
        f"toast={outcome.toast_result} "
        f"elapsed={outcome.elapsed_s:.2f}s\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
