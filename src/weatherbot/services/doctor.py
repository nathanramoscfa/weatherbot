# src/weatherbot/services/doctor.py
"""``doctor``: the local surfaces' health check, and one light probe per register source.

Offline, it reports the configuration and data paths, whether the settings load, the
database file and its Alembic revision against the head, and how many locations are
stored, never a coordinate. Online, it sends one light, location-free probe per register
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
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal
from uuid import UUID

from weatherbot.models import MapCatalog, SourceId, StormSummary
from weatherbot.services.network import Network
from weatherbot.services.persistence.database import (
    Database,
    current_revision,
    head_revision,
)
from weatherbot.services.persistence.raw_cache import RawResponseCache
from weatherbot.services.persistence.repositories import (
    DriftWarning,
    LocationRepository,
    SnapshotRepository,
)
from weatherbot.services.register import MAP_LAYERS, NOT_PROBED, SHARED_HOST, expand
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
) -> DoctorReport:
    """Run every check, and every probe unless ``offline``.

    Args:
        settings_problem: Why the settings did not load, if they did not.
        settings_file_exists: Whether ``weatherbot.toml`` exists.
        database: The open database, unless opening it failed.
        database_problem: Why the database did not open, if it did not.
        created: Whether opening it created it.
        offline: Skip every probe.
        network: The timeout and the fetcher factory.

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
    drift_id: UUID | None = None
    warnings: tuple[DriftWarning, ...] = ()
    if database is not None:
        repository = SnapshotRepository(database.engine)
        drift_id = repository.latest_id()
        warnings = repository.drift_warnings(drift_id) if drift_id is not None else ()
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
