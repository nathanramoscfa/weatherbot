# src/weatherbot/services/doctor.py
"""``doctor``: the local surfaces' health check, and one light probe per register source.

Offline, it reports the configuration and data paths, whether the settings load, the
database file and its Alembic revision against the head, how many locations are stored
(never a coordinate), and the heartbeats under the staleness rule: the ``heartbeat`` check
is skipped until some heartbeat promises a cadence (a fresh install, or a machine where no
scheduled monitor has run) and whenever the database did not open, passes when none is
stale, and fails when one is. The ``toast`` check judges the stored toast deliveries: it is
skipped off Windows, with the toast off, before any toast delivery is stored, and when the
database did not open, so a fresh install still exits 0; it fails when the latest toast
failed, was disabled, or was unavailable, or when the identity is missing although a toast
was delivered before. Online, it sends one light, location-free probe per register
source (the five map-service catalogs, the roster, the active storms' arrival-time KMZ,
one TWO list for ``api.weather.gov``, the outlook graphics conditionally, the three feeds,
and both WMS capabilities documents) and resolves every register layer name in this
run's catalogs: each ``{slot}`` layer over all fifteen slots, the ``StormSurgeRisk``
group paths, and the overlay layers. Nominatim is never probed (its usage policy), and
the basemap tiles and the GIS archive are display-only and replay-only; the report says
so. It also lists the Source-drift warnings stored with the latest snapshot.

Any failed check, probe, or layer makes the report failed, which the command turns into
exit status 1.
"""

import asyncio
import functools
import os
import shutil
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal
from uuid import UUID

from weatherbot.models import MapCatalog, SourceId, StormSummary
from weatherbot.services.config import DATA_DIR_VARIABLE
from weatherbot.services.health import Staleness, staleness
from weatherbot.services.network import Network
from weatherbot.services.notifications import NotificationService, StoredDelivery
from weatherbot.services.persistence.database import (
    Database,
    current_revision,
    head_revision,
)
from weatherbot.services.persistence.raw_cache import RawResponseCache
from weatherbot.services.persistence.repositories import (
    DriftWarning,
    HeartbeatRepository,
    LocationRepository,
    SnapshotRepository,
)
from weatherbot.services.register import MAP_LAYERS, NOT_PROBED, SHARED_HOST, expand
from weatherbot.services.tasks import (
    HEALTHY_TASK_RESULTS,
    ON_WINDOWS,
    TASK_NAMES,
    ScheduledTask,
    SubprocessRunner,
    TaskSchedulerError,
    is_checkout_interpreter,
    run_subprocess,
)
from weatherbot.services.tasks import (
    query as query_tasks,
)
from weatherbot.services.toast import APP_ID, MISSING_IDENTITY, TOAST_OFF, delivery_failed
from weatherbot.sources import (
    arcgis,
    catalogs,
    nhc_arrival_times,
    nhc_current_storms,
    nhc_gis_rss,
    nhc_outlook_graphics,
    nhc_text_products,
)
from weatherbot.sources.errors import SourceError, SourceSchemaError
from weatherbot.sources.http import Fetcher, MemoryValidatorStore, ValidatorStore

type CheckStatus = Literal["pass", "fail", "skip"]

TEXT_PROBE: Final[SourceId] = "nhc-text-products"
TWO_PROBE_BASIN: Final = "AT"
REGISTER_ORDER: Final[tuple[SourceId, ...]] = (
    "nhc-current-storms",
    "nhc-arrival-times",
    "nhc-map-tropical-weather",
    "nhc-map-tropical-summary",
    "nhc-map-breakpoints",
    "nhc-map-peak-surge",
    "nhc-map-surge-risk",
    "nhc-gis-rss",
    "nhc-gis-archive",
    "nhc-text-products",
    "nhc-outlook-graphics",
    "nws-points",
    "nws-alerts-point",
    "nws-alerts-zone",
    "nws-zones",
    "basemap-osm-tiles",
    "overlay-radar",
    "overlay-satellite",
    "geocode-nominatim",
)
"""Every register source, in the register's order: ``doctor`` reports each once."""
MAX_MISSING_SHOWN: Final = 5


@dataclass(frozen=True)
class Check:
    """One local check."""

    name: str
    status: CheckStatus
    detail: str


@dataclass(frozen=True)
class SourceProbe:
    """What one register source's probe found, or why it was not probed."""

    source_id: SourceId
    status: CheckStatus
    detail: str


@dataclass(frozen=True)
class LayerDiscovery:
    """How many of a service's register layers this run's catalog resolved."""

    source_id: SourceId
    expected: int
    resolved: int
    missing: tuple[str, ...]

    @property
    def status(self) -> CheckStatus:
        """``pass`` when every layer resolved."""
        return "pass" if not self.missing else "fail"


@dataclass(frozen=True)
class DatabaseState:
    """The database as ``doctor`` opened it."""

    revision: str | None
    head: str
    created: bool
    backup_path: Path | None


@dataclass(frozen=True)
class DoctorReport:
    """Everything ``doctor`` found."""

    checks: tuple[Check, ...]
    database: DatabaseState | None
    locations: int | None
    probes: tuple[SourceProbe, ...]
    layers: tuple[LayerDiscovery, ...]
    drift_snapshot_id: UUID | None
    drift_warnings: tuple[DriftWarning, ...]
    heartbeats: tuple[Staleness, ...] = ()
    tasks: tuple[ScheduledTask, ...] = ()

    @property
    def failed(self) -> bool:
        """Whether any check, probe, or layer discovery failed."""
        rows = [*self.checks, *self.probes, *self.layers]
        return any(row.status == "fail" for row in rows)


def local_checks(
    *,
    settings_problem: str | None,
    settings_file_exists: bool,
    database: Database | None,
    database_problem: str | None,
    created: bool,
) -> tuple[tuple[Check, ...], DatabaseState | None, int | None]:
    """Check the settings and the database, and count the locations.

    Args:
        settings_problem: Why the settings did not load, if they did not.
        settings_file_exists: Whether ``weatherbot.toml`` exists.
        database: The open database, unless opening it failed.
        database_problem: Why the database did not open, if it did not.
        created: Whether opening it created it.

    Returns:
        The checks, the database's state, and the number of stored locations.
    """
    checks: list[Check] = []
    if settings_problem is not None:
        checks.append(Check("settings", "fail", settings_problem))
    else:
        detail = "weatherbot.toml read" if settings_file_exists else "no weatherbot.toml: defaults"
        checks.append(Check("settings", "pass", detail))
    head = head_revision()
    if database is None:
        checks.append(Check("database", "fail", database_problem or "the database did not open"))
        checks.append(Check("migrations", "skip", "the database did not open"))
        return tuple(checks), None, None
    revision = current_revision(database.engine)
    state = DatabaseState(
        revision=revision, head=head, created=created, backup_path=database.backup_path
    )
    opened = "created" if created else "opened"
    checks.append(Check("database", "pass", f"{opened}; SQLite in WAL mode"))
    if revision == head:
        upgraded = (
            f"; upgraded after a backup to {database.backup_path.name}"
            if database.backup_path
            else ""
        )
        checks.append(Check("migrations", "pass", f"at revision {revision}, the head{upgraded}"))
    else:
        checks.append(Check("migrations", "fail", f"at revision {revision}, head {head}"))
    count = len(LocationRepository(database.engine).list())
    checks.append(Check("locations", "pass", f"{count} stored"))
    return tuple(checks), state, count


DATABASE_CLOSED: Final = "the database did not open"
SEND_ANOTHER: Final = "weatherbot notify test sends another"


def toast_check(
    latest: StoredDelivery | None, *, identity: bool | None, toast_on: bool, delivered_before: bool
) -> Check:
    """Judge the toast from its stored deliveries; the detail never holds a notification's text.

    Skipped off Windows, while ``[notifications] toast`` is off, and until a toast delivery
    is stored (a fresh install). Fails when the latest toast delivery failed, was disabled,
    or was unavailable, and when the identity is missing although a toast was delivered.

    Args:
        latest: The newest stored toast delivery.
        identity: Whether the identity is registered; ``None`` off Windows.
        toast_on: ``[notifications] toast``.
        delivered_before: Whether any toast was ever delivered.

    Returns:
        The ``toast`` check.
    """
    if identity is None:
        return Check("toast", "skip", "not Windows: there is no toast channel")
    if not toast_on:
        return Check("toast", "skip", TOAST_OFF)
    if latest is None:
        return Check("toast", "skip", "no toast delivery is stored")
    if delivery_failed(latest.result, windows=True, toast_on=True):
        reason = f" ({latest.detail})" if latest.detail else ""
        return Check("toast", "fail", f"the latest toast {latest.result}{reason}; {SEND_ANOTHER}")
    if not identity and delivered_before:
        detail = f"the identity {APP_ID} is missing, although a toast was delivered before"
        return Check("toast", "fail", f"{detail}; {MISSING_IDENTITY}")
    return Check("toast", "pass", f"the latest toast {latest.result}")


def heartbeat_check(
    judged: Sequence[Staleness],
    *,
    serve_installed: bool = False,
    data_dir_overridden: bool = False,
) -> Check:
    r"""Judge the heartbeats: skip with no cadence promised, else pass or fail on staleness.

    On the default data directory (when ``data_dir_overridden`` is ``False``), also fails
    when the ``serve`` task is installed and the ``serve`` runner row is stale or absent.

    Args:
        judged: The staleness rule's judgements.
        serve_installed: Whether ``\Weatherbot\serve`` is installed in Task Scheduler.
        data_dir_overridden: Whether ``WEATHERBOT_DATA_DIR`` overrides the default data directory.

    Returns:
        The ``heartbeat`` check.
    """
    if not data_dir_overridden and serve_installed:
        serve_row = next(
            (item for item in judged if item.kind == "runner" and item.name == "serve"),
            None,
        )
        if serve_row is None:
            return Check(
                "heartbeat",
                "fail",
                "the serve task is installed, but the serve runner heartbeat is absent",
            )
        if serve_row.expected_every_s is None or serve_row.stale:
            stale = [
                item.name for item in judged if item.expected_every_s is not None and item.stale
            ]
            if "serve" not in stale:
                stale = ["serve", *stale]
            return Check("heartbeat", "fail", f"stale: {', '.join(stale)}")
    promised = [item for item in judged if item.expected_every_s is not None]
    if not promised:
        return Check("heartbeat", "skip", "no heartbeat promises a cadence: no scheduler has run")
    stale = [item.name for item in promised if item.stale]
    if stale:
        return Check("heartbeat", "fail", f"stale: {', '.join(stale)}")
    return Check("heartbeat", "pass", f"{len(promised)} with a cadence, none stale")


def _task_problems(
    name: str,
    task: ScheduledTask | None,
    interpreter_exists: Callable[[Path], bool],
) -> list[str]:
    if task is None:
        return [f"{name}: not installed"]
    problems: list[str] = []
    if not task.enabled or task.state.lower() == "disabled":
        problems.append(f"{name}: disabled ({task.state})")
    if task.logon_type != "InteractiveToken":
        problems.append(
            f"{name}: logon type is {task.logon_type or 'unset'}, expected InteractiveToken"
        )
    if task.run_level != "LeastPrivilege":
        problems.append(
            f"{name}: run level is {task.run_level or 'unset'}, expected LeastPrivilege"
        )
    if not task.command or not interpreter_exists(Path(task.command)):
        problems.append(f"{name}: interpreter does not exist")
    if (
        task.state.lower() != "running"
        and task.last_task_result is not None
        and task.last_task_result not in HEALTHY_TASK_RESULTS
    ):
        problems.append(f"{name}: last result 0x{task.last_task_result:x}")
    return problems


def tasks_check(
    tasks: Sequence[ScheduledTask],
    *,
    data_dir_overridden: bool = False,
    windows: bool = True,
    interpreter_exists: Callable[[Path], bool] = Path.is_file,
    query_error: str | None = None,
) -> Check:
    r"""Judge the ``\Weatherbot\`` scheduled tasks.

    Skipped off Windows, under a ``WEATHERBOT_DATA_DIR`` override, and when neither task is
    installed. Passes when both ``serve`` and ``check`` are enabled, use ``InteractiveToken``
    and ``LeastPrivilege``, point at an interpreter that exists, and last returned 0,
    ``0x41301`` (running), or ``0x41303`` (has not run); fails naming the task and reason
    otherwise.
    """
    if data_dir_overridden:
        return Check("tasks", "skip", f"{DATA_DIR_VARIABLE} is set: machine checks are skipped")
    if not windows:
        return Check("tasks", "skip", "not Windows: there is no Task Scheduler")
    if query_error is not None:
        return Check("tasks", "fail", f"Task Scheduler query failed ({query_error})")
    by_name = {task.name: task for task in tasks}
    if not any(name in by_name for name in TASK_NAMES):
        return Check("tasks", "skip", "no Weatherbot task is installed")
    problems: list[str] = []
    for name in TASK_NAMES:
        problems.extend(_task_problems(name, by_name.get(name), interpreter_exists))
    if problems:
        return Check("tasks", "fail", "; ".join(problems))
    return Check(
        "tasks",
        "pass",
        f"serve ({by_name['serve'].state}) and check ({by_name['check'].state}) enabled",
    )


def _belongs_to_installation(found: Path, interpreter: Path) -> bool:
    if found.parent == interpreter.parent:
        return True
    try:
        if found.resolve().parent == interpreter.resolve().parent:
            return True
    except OSError:
        pass
    parts_lower = tuple(part.lower() for part in interpreter.parts)
    if "uv" in parts_lower and "tools" in parts_lower:
        local_bin = Path.home() / ".local" / "bin"
        tool_bin_env = os.environ.get("UV_TOOL_BIN_DIR", "").strip()
        allowed_bins = {local_bin}
        if tool_bin_env:
            allowed_bins.add(Path(tool_bin_env))
        if found.parent in allowed_bins:
            return True
        try:
            if found.resolve().parent in {p.resolve() for p in allowed_bins}:
                return True
        except OSError:
            pass
    return False


def path_check(
    *,
    data_dir_overridden: bool = False,
    interpreter: Path | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> Check:
    """Judge whether a bare ``weatherbot`` on ``PATH`` reaches the running installation.

    Skipped under a ``WEATHERBOT_DATA_DIR`` override and when ``interpreter`` belongs to a
    source checkout's environment. Passes when ``which("weatherbot")`` belongs to the
    running installation; fails naming the shadowing directory and the fix otherwise.
    """
    if data_dir_overridden:
        return Check("path", "skip", f"{DATA_DIR_VARIABLE} is set: machine checks are skipped")
    resolved_interpreter = Path(sys.executable) if interpreter is None else Path(interpreter)
    if is_checkout_interpreter(resolved_interpreter):
        return Check("path", "skip", "running from a source checkout environment")
    found = which("weatherbot")
    if found is None:
        return Check(
            "path",
            "fail",
            "weatherbot is not on PATH; put ~/.local/bin on PATH",
        )
    found_path = Path(found)
    if _belongs_to_installation(found_path, resolved_interpreter):
        return Check("path", "pass", f"PATH resolves weatherbot to {found_path.parent}")
    return Check(
        "path",
        "fail",
        f"PATH resolves weatherbot to {found_path.parent}; "
        "put ~/.local/bin earlier on PATH, or remove the other copy",
    )


async def _probe(source_id: SourceId, work: Callable[[], Awaitable[str]]) -> SourceProbe:
    detail: str | None = None
    failure: SourceError | None = None
    try:
        detail = await work()
    except* SourceError as group:
        leaf = group.exceptions[0]
        while isinstance(leaf, BaseExceptionGroup):
            leaf = leaf.exceptions[0]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType] - nested SourceError groups
        failure = leaf  # pyright: ignore[reportUnknownVariableType] - the leaf is a SourceError
    if failure is not None:
        return SourceProbe(source_id, "fail", f"{failure.kind}: {failure}")
    return SourceProbe(source_id, "pass", detail or "reachable")


def discover(source_id: SourceId, catalog: MapCatalog) -> LayerDiscovery:
    """Resolve every register layer of a service in this run's catalog.

    Args:
        source_id: The map service's register id.
        catalog: Its catalog, read in this run.

    Returns:
        How many names resolved, and the ones that did not.
    """
    names = [name for template in MAP_LAYERS[source_id] for name in expand(template)]
    missing: list[str] = []
    for name in names:
        try:
            arcgis.resolve(catalog, name)
        except SourceSchemaError:
            missing.append(name)
    return LayerDiscovery(source_id, len(names), len(names) - len(missing), tuple(missing))


class _Prober:
    def __init__(self, fetcher: Fetcher) -> None:
        self.fetcher = fetcher
        self.storms: Sequence[StormSummary] | None = None
        self.layers: list[LayerDiscovery] = []

    async def roster(self) -> str:
        result = await nhc_current_storms.fetch_current_storms(self.fetcher)
        self.storms = result.records
        return f"{len(result.records)} active storms"

    async def catalog(self, service: arcgis.MapService) -> str:
        catalog = (await arcgis.fetch_catalog(self.fetcher, service)).records
        self.layers.append(discover(service.source_id, catalog))
        return f"catalog of {len(catalog.layers)} layers"

    async def two_list(self) -> str:
        url = nhc_text_products.list_url("TWO", TWO_PROBE_BASIN)
        result = await self.fetcher.get(url, source_id=TEXT_PROBE)
        nhc_text_products.newest_product_id(result.body, TEXT_PROBE, "the Atlantic TWO list")
        return "api.weather.gov answered the Atlantic TWO list"

    async def graphics(self) -> str:
        result = await nhc_outlook_graphics.fetch_outlook_graphics(self.fetcher)
        unchanged = sum(response.not_modified for response in result.responses)
        return f"{len(result.records)} graphics, {unchanged} not modified (conditional)"

    async def feeds(self) -> str:
        result = await nhc_gis_rss.fetch_gis_feeds(self.fetcher)
        return f"{len(result.records)} items in 3 feeds"

    async def overlay(self, service: catalogs.OverlayService) -> str:
        result = await self.fetcher.get(
            service.url, source_id=service.source_id, max_bytes=catalogs.MAX_CAPABILITIES_BYTES
        )
        catalogs.parse_capabilities(result.body, result.provenance(), service)
        return f"capabilities name the {len(service.layers)} layers the map loads"

    async def arrivals(self, storms: Sequence[StormSummary]) -> str:
        result = await nhc_arrival_times.fetch_arrival_times(self.fetcher, storms)
        return f"{len(result.records)} products of {len(storms)} active storms"


async def probe_sources(
    network: Network, validators: ValidatorStore
) -> tuple[tuple[SourceProbe, ...], tuple[LayerDiscovery, ...]]:
    """Probe every register source once, without a coordinate, and discover the layers.

    Args:
        network: The timeout and the fetcher factory.
        validators: The validator store, so the outlook graphics are conditional.

    Returns:
        One probe per register source, in register order, and the layer discoveries.
    """
    found: dict[SourceId, SourceProbe] = {}
    async with network.fetcher(validators) as fetcher:
        prober = _Prober(fetcher)
        jobs: dict[SourceId, Callable[[], Awaitable[str]]] = {
            "nhc-current-storms": prober.roster,
            "nhc-gis-rss": prober.feeds,
            "nhc-text-products": prober.two_list,
            "nhc-outlook-graphics": prober.graphics,
        }
        for service in arcgis.SERVICES.values():
            jobs[service.source_id] = functools.partial(prober.catalog, service)
        for overlay in catalogs.OVERLAYS:
            jobs[overlay.source_id] = functools.partial(prober.overlay, overlay)
        async with asyncio.TaskGroup() as group:
            tasks: dict[SourceId, asyncio.Task[SourceProbe]] = {
                source: group.create_task(_probe(source, job)) for source, job in jobs.items()
            }
        found.update({source: task.result() for source, task in tasks.items()})
        storms = prober.storms
        linked = [storm for storm in storms or () if nhc_arrival_times.arrival_links(storm)]
        if storms is None:
            found["nhc-arrival-times"] = SourceProbe(
                "nhc-arrival-times", "skip", "the roster probe failed"
            )
        elif not linked:
            found["nhc-arrival-times"] = SourceProbe(
                "nhc-arrival-times", "skip", "no active storm links an arrival-time product"
            )
        else:
            found["nhc-arrival-times"] = await _probe(
                "nhc-arrival-times", functools.partial(prober.arrivals, linked)
            )
    text = found[TEXT_PROBE]
    for source, through in SHARED_HOST.items():
        detail = f"api.weather.gov checked by the {through} probe; no location is sent"
        found[source] = SourceProbe(source, text.status, detail)
    for source, reason in NOT_PROBED.items():
        found[source] = SourceProbe(source, "skip", reason)
    order = {source: index for index, source in enumerate(arcgis.SERVICES)}
    layers = tuple(sorted(prober.layers, key=lambda layer: order[layer.source_id]))
    return tuple(found[source] for source in REGISTER_ORDER), layers


async def diagnose(  # noqa: PLR0913 - the local state, then the probe's inputs, keyword-only
    *,
    settings_problem: str | None,
    settings_file_exists: bool,
    database: Database | None,
    database_problem: str | None,
    created: bool,
    offline: bool,
    network: Network,
    now: datetime | None = None,
    identity: bool | None = None,
    toast_on: bool = True,
    data_dir_overridden: bool | None = None,
    windows: bool = ON_WINDOWS,
    tasks: Sequence[ScheduledTask] | None = None,
    tasks_query_error: str | None = None,
    task_runner: SubprocessRunner = run_subprocess,
    interpreter: Path | None = None,
    interpreter_exists: Callable[[Path], bool] = Path.is_file,
    which: Callable[[str], str | None] = shutil.which,
) -> DoctorReport:
    r"""Run every check, and every probe unless ``offline``.

    Args:
        settings_problem: Why the settings did not load, if they did not.
        settings_file_exists: Whether ``weatherbot.toml`` exists.
        database: The open database, unless opening it failed.
        database_problem: Why the database did not open, if it did not.
        created: Whether opening it created it.
        offline: Skip every probe.
        network: The timeout and the fetcher factory.
        now: The instant the heartbeats are judged at; the clock's when omitted.
        identity: Whether the toast identity is registered; ``None`` off Windows.
        toast_on: ``[notifications] toast``.
        data_dir_overridden: Whether ``WEATHERBOT_DATA_DIR`` overrides the default data directory.
        windows: Whether the platform is Windows.
        tasks: Pre-queried ``\Weatherbot\`` tasks; queried on Windows when ``None``.
        tasks_query_error: Error from querying Task Scheduler, if any.
        task_runner: Subprocess seam for querying Task Scheduler when ``tasks`` is ``None``.
        interpreter: Running interpreter path for the ``path`` check.
        interpreter_exists: Seam checking whether a task's interpreter exists.
        which: Seam resolving ``weatherbot`` on ``PATH``.

    Returns:
        The report.
    """
    checks, state, count = local_checks(
        settings_problem=settings_problem,
        settings_file_exists=settings_file_exists,
        database=database,
        database_problem=database_problem,
        created=created,
    )
    overridden = (
        bool(os.environ.get(DATA_DIR_VARIABLE, "").strip())
        if data_dir_overridden is None
        else data_dir_overridden
    )
    queried_tasks: tuple[ScheduledTask, ...] = ()
    query_error = tasks_query_error
    if tasks is not None:
        queried_tasks = tuple(tasks)
    elif not overridden and windows and query_error is None:
        try:
            queried_tasks = query_tasks(runner=task_runner)
        except TaskSchedulerError as error:
            query_error = str(error)
    serve_installed = any(task.name == "serve" for task in queried_tasks)
    t_check = tasks_check(
        queried_tasks,
        data_dir_overridden=overridden,
        windows=windows,
        interpreter_exists=interpreter_exists,
        query_error=query_error,
    )
    p_check = path_check(
        data_dir_overridden=overridden,
        interpreter=interpreter,
        which=which,
    )
    drift_id: UUID | None = None
    warnings: tuple[DriftWarning, ...] = ()
    judged: tuple[Staleness, ...] = ()
    if database is not None:
        repository = SnapshotRepository(database.engine)
        drift_id = repository.latest_id()
        warnings = repository.drift_warnings(drift_id) if drift_id is not None else ()
        rows = HeartbeatRepository(database.engine).rows()
        judged = staleness(rows, now or datetime.now(UTC))
        deliveries = NotificationService(database.engine)
        toast = toast_check(
            deliveries.latest_delivery("toast"),
            identity=identity,
            toast_on=toast_on,
            delivered_before=deliveries.delivered_before("toast"),
        )
        h_check = heartbeat_check(
            judged,
            serve_installed=serve_installed,
            data_dir_overridden=overridden,
        )
        checks = (*checks, h_check, toast, t_check, p_check)
    else:
        checks = (
            *checks,
            Check("heartbeat", "skip", DATABASE_CLOSED),
            Check("toast", "skip", DATABASE_CLOSED),
            t_check,
            p_check,
        )
    probes: tuple[SourceProbe, ...] = ()
    layers: tuple[LayerDiscovery, ...] = ()
    if not offline:
        validators: ValidatorStore = (
            RawResponseCache(database.engine) if database is not None else MemoryValidatorStore()
        )
        probes, layers = await probe_sources(network, validators)
    return DoctorReport(
        checks=checks,
        database=state,
        locations=count,
        probes=probes,
        layers=layers,
        drift_snapshot_id=drift_id,
        drift_warnings=warnings,
        heartbeats=judged,
        tasks=queried_tasks,
    )


def missing_summary(missing: Sequence[str]) -> str:
    """Name a few of a service's missing layers, for a terminal line.

    Args:
        missing: The layer names that did not resolve.

    Returns:
        Up to five names and how many more, or ``-`` when none is missing.
    """
    if not missing:
        return "-"
    shown = ", ".join(missing[:MAX_MISSING_SHOWN])
    more = len(missing) - MAX_MISSING_SHOWN
    return f"{shown} and {more} more" if more > 0 else shown
