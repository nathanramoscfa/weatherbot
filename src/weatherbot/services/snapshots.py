# src/weatherbot/services/snapshots.py
"""The snapshot service: fetch every source once, record each outcome, and store it all.

``SnapshotService.fetch_snapshot(locations)`` runs inside one HTTP client. The roster
comes first, because it names the active storms and their slots; then, concurrently, with
the fetcher pacing each host: the summary service's storm, display, outlook, and
probabilistic-wind layers; the peak-surge layers; each active storm's arrival-time KMZ
pair; the TCPs and the three TWO lists; the three GIS RSS feeds; the six outlook
graphics; the breakpoints; and every US location's point and zone alerts. A location
outside NWS coverage makes no NWS request. The surge-risk and overlay catalogs are
``doctor``'s.

Every source the run asks for gets one ``SourceOutcome``: ``ok``, ``not_modified`` (every
answer was a 304 served from the store), ``failed`` with the error's kind, or
``skipped`` with the reason. A failed source leaves its part of the snapshot empty, and
nothing from an earlier snapshot fills it: the ``Snapshot`` model refuses a record whose
source did not answer. The alerts are one part fed by two sources, so they are kept only
when both answered. A ``kmz`` arrival-time product supersedes the ``map_layer`` product of
the same storm, advisory, and kind; the map-layer product stays when no KMZ product
replaces it, as when the KMZ fetch failed.

The snapshot, its raw responses, and the run's Source-drift warnings are stored in one
transaction, and the raw-response cache is the fetcher's validator store, so the next
run's requests are conditional. Log records name sources, counts, and outcomes, never a
coordinate.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final
from uuid import UUID, uuid4

from sqlalchemy import Engine

from weatherbot.models import (
    ArrivalTimeProduct,
    Breakpoint,
    DisplayLayer,
    GisFeedItem,
    Location,
    NwsAlert,
    OutlookArea,
    OutlookGraphic,
    Snapshot,
    SourceId,
    SourceOutcome,
    StormProducts,
    StormSummary,
    TextProduct,
    WindProbabilityProduct,
)
from weatherbot.services.logs import collect_drift
from weatherbot.services.network import Network, product_key
from weatherbot.services.persistence.raw_cache import CachedFetch, RawResponseCache
from weatherbot.services.persistence.repositories import DriftWarning, SnapshotRepository
from weatherbot.sources import (
    arcgis,
    nhc_arrival_times,
    nhc_current_storms,
    nhc_gis_rss,
    nhc_map,
    nhc_outlook_graphics,
    nhc_text_products,
    nws,
)
from weatherbot.sources.errors import SourceError
from weatherbot.sources.http import Fetcher, FetchResult, SourceResult

LOGGER: Final = logging.getLogger("weatherbot.services.snapshots")

ROSTER: Final[SourceId] = "nhc-current-storms"
ARRIVALS: Final[SourceId] = "nhc-arrival-times"
SUMMARY: Final[SourceId] = "nhc-map-tropical-summary"
BREAKPOINTS: Final[SourceId] = "nhc-map-breakpoints"
PEAK_SURGE: Final[SourceId] = "nhc-map-peak-surge"
FEEDS: Final[SourceId] = "nhc-gis-rss"
TEXT: Final[SourceId] = "nhc-text-products"
GRAPHICS: Final[SourceId] = "nhc-outlook-graphics"
ALERT_SOURCES: Final[tuple[SourceId, ...]] = (nws.ALERTS_POINT, nws.ALERTS_ZONE)
SNAPSHOT_SOURCES: Final[tuple[SourceId, ...]] = (
    ROSTER,
    ARRIVALS,
    SUMMARY,
    BREAKPOINTS,
    PEAK_SURGE,
    FEEDS,
    TEXT,
    GRAPHICS,
    *ALERT_SOURCES,
)
"""Every source a snapshot asks for, in the order its outcomes are listed."""

NO_STORM: Final = "no active storm"
ROSTER_FAILED: Final = "the storm roster failed"
NO_ARRIVAL_LINK: Final = "the roster links no arrival-time product"
NO_US_LOCATION: Final = "no location inside NWS coverage"
NOTHING_ASKED: Final = "nothing was requested"


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class _Ledger:
    """What each source answered in a run: its answers, its first error, or why skipped."""

    responses: dict[SourceId, list[CachedFetch]] = field(
        default_factory=dict[SourceId, list[CachedFetch]]
    )
    errors: dict[SourceId, SourceError] = field(default_factory=dict[SourceId, SourceError])
    skipped: dict[SourceId, str] = field(default_factory=dict[SourceId, str])

    def answered(self, results: Iterable[FetchResult], key: Callable[[FetchResult], str]) -> None:
        for result in results:
            cached = CachedFetch(result, product_key=key(result))
            self.responses.setdefault(result.source_id, []).append(cached)

    def failed(self, error: SourceError) -> None:
        self.errors.setdefault(error.source_id, error)

    def skip(self, source_id: SourceId, reason: str) -> None:
        self.skipped.setdefault(source_id, reason)

    def ok(self, source_id: SourceId) -> bool:
        """Whether the source answered: no error, and not skipped."""
        return source_id not in self.errors and source_id not in self.skipped

    def outcome(self, source_id: SourceId) -> SourceOutcome:
        error = self.errors.get(source_id)
        if error is not None:
            return SourceOutcome(source_id=source_id, status="failed", error_kind=error.kind)
        answers = self.responses.get(source_id, [])
        if answers:
            fresh = any(not cached.result.not_modified for cached in answers)
            return SourceOutcome(source_id=source_id, status="ok" if fresh else "not_modified")
        reason = self.skipped.get(source_id, NOTHING_ASKED)
        return SourceOutcome(source_id=source_id, status="skipped", reason=reason)

    def all_responses(self) -> tuple[CachedFetch, ...]:
        return tuple(
            cached for source in SNAPSHOT_SOURCES for cached in self.responses.get(source, [])
        )


@dataclass
class _Summary:
    storms: tuple[StormProducts, ...] = ()
    display: tuple[DisplayLayer, ...] = ()
    outlook: tuple[OutlookArea, ...] = ()
    winds: tuple[WindProbabilityProduct, ...] = ()


@dataclass
class _Parts:
    """Each source's records, kept only when its outcome lets the snapshot hold them."""

    summary: _Summary = field(default_factory=_Summary)
    arrivals: tuple[ArrivalTimeProduct, ...] = ()
    breakpoints: tuple[Breakpoint, ...] = ()
    surge: tuple[DisplayLayer, ...] = ()
    feeds: tuple[GisFeedItem, ...] = ()
    texts: tuple[TextProduct, ...] = ()
    graphics: tuple[OutlookGraphic, ...] = ()
    alerts: dict[str, tuple[NwsAlert, ...]] = field(default_factory=dict[str, tuple[NwsAlert, ...]])


@dataclass(frozen=True)
class FetchedSnapshot:
    """A stored snapshot and the Source-drift warnings its fetch logged."""

    snapshot: Snapshot
    drift_warnings: tuple[DriftWarning, ...]


def merge_arrivals(
    storm: StormProducts, kmz: Sequence[ArrivalTimeProduct]
) -> tuple[ArrivalTimeProduct, ...]:
    """Apply the supersession rule to one storm: a KMZ product replaces its map layer.

    Args:
        storm: The storm's products from the map service, with map-layer arrival times.
        kmz: Every arrival-time product the KMZ fetch parsed, of any storm.

    Returns:
        The storm's KMZ products, then the map-layer products no KMZ product replaces.
    """
    mine = [product for product in kmz if product.atcf_id == storm.summary.atcf_id]
    return nhc_arrival_times.prefer_kmz((*mine, *storm.arrival_times))


def _with_arrivals(storm: StormProducts, arrivals: tuple[ArrivalTimeProduct, ...]) -> StormProducts:
    return StormProducts(
        summary=storm.summary,
        cone=storm.cone,
        track_points=storm.track_points,
        track=storm.track,
        watch_warnings=storm.watch_warnings,
        wind_radii=storm.wind_radii,
        arrival_times=arrivals,
    )


class _Run:
    """One fetch: the fetcher, the ledger, and the guarded calls of each source."""

    def __init__(self, fetcher: Fetcher) -> None:
        self.fetcher = fetcher
        self.ledger = _Ledger()

    async def guard[T](
        self,
        work: Awaitable[SourceResult[T]],
        key: Callable[[FetchResult], str] = product_key,
    ) -> T | None:
        """Await one fetch function; record its answers, or its source's failure."""
        result: SourceResult[T] | None = None
        failure: SourceError | None = None
        try:
            result = await work
        except* SourceError as group:
            failure = _first_error(group)
        if failure is not None:
            self.ledger.failed(failure)
            return None
        if result is None:  # unreachable: a result is set whenever nothing was raised
            return None
        self.ledger.answered(result.responses, key)
        return result.records

    async def summary(self, storms: Sequence[StormSummary], parts: _Parts) -> None:
        catalog = await self.guard(arcgis.fetch_catalog(self.fetcher, arcgis.TROPICAL_SUMMARY))
        if catalog is None:
            return
        products = await self.guard(nhc_map.fetch_storm_products(self.fetcher, catalog, storms))
        display = await self.guard(
            nhc_map.fetch_storm_display_layers(self.fetcher, catalog, storms)
        )
        outlook = await self.guard(nhc_map.fetch_outlook(self.fetcher, catalog))
        winds = await self.guard(nhc_map.fetch_wind_probabilities(self.fetcher, catalog, storms))
        if products is None or display is None or outlook is None or winds is None:
            return
        parts.summary = _Summary(storms=products, display=display, outlook=outlook, winds=winds)

    async def arrivals(self, storms: Sequence[StormSummary] | None, parts: _Parts) -> None:
        if not storms:
            self.ledger.skip(ARRIVALS, ROSTER_FAILED if storms is None else NO_STORM)
            return
        products = await self.guard(nhc_arrival_times.fetch_arrival_times(self.fetcher, storms))
        if products is not None and not self.ledger.responses.get(ARRIVALS):
            self.ledger.skip(ARRIVALS, NO_ARRIVAL_LINK)
        parts.arrivals = products or ()

    async def breakpoints(self, parts: _Parts) -> None:
        catalog = await self.guard(arcgis.fetch_catalog(self.fetcher, arcgis.BREAKPOINTS))
        if catalog is not None:
            parts.breakpoints = (
                await self.guard(nhc_map.fetch_breakpoints(self.fetcher, catalog)) or ()
            )

    async def surge(self, parts: _Parts) -> None:
        catalog = await self.guard(arcgis.fetch_catalog(self.fetcher, arcgis.PEAK_SURGE))
        if catalog is not None:
            parts.surge = await self.guard(nhc_map.fetch_peak_surge(self.fetcher, catalog)) or ()

    async def texts(self, storms: Sequence[StormSummary] | None, parts: _Parts) -> None:
        tcps = await self.guard(nhc_text_products.fetch_tcps(self.fetcher, storms or ()))
        twos = await self.guard(nhc_text_products.fetch_twos(self.fetcher))
        if tcps is not None and twos is not None:
            parts.texts = (*tcps, *twos)

    async def feeds(self, parts: _Parts) -> None:
        parts.feeds = await self.guard(nhc_gis_rss.fetch_gis_feeds(self.fetcher)) or ()

    async def graphics(self, parts: _Parts) -> None:
        parts.graphics = (
            await self.guard(nhc_outlook_graphics.fetch_outlook_graphics(self.fetcher)) or ()
        )

    async def alerts(self, location: Location, parts: _Parts) -> None:
        def key(result: FetchResult) -> str:
            # A point query's redacted key is the same for every location: name it.
            if result.source_id == nws.ALERTS_POINT:
                return f"{product_key(result)}<{location.name}>"
            return product_key(result)

        alerts = await self.guard(nws.fetch_alerts(self.fetcher, location), key)
        if alerts is not None:
            parts.alerts[location.name] = alerts


def _first_error(group: BaseExceptionGroup[SourceError]) -> SourceError:
    """The first ``SourceError`` of a group, however deeply task groups nested it."""
    first = group.exceptions[0]
    while isinstance(first, BaseExceptionGroup):
        first = first.exceptions[0]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType] - a nested group of SourceError
    return first  # pyright: ignore[reportUnknownVariableType] - the leaf is a SourceError


def assemble_snapshot(  # noqa: PLR0913 - one run's parts, keyword-only
    *,
    snapshot_id: UUID,
    started_at: datetime,
    completed_at: datetime,
    storms: Sequence[StormSummary] | None,
    parts: _Parts,
    ledger: _Ledger,
) -> Snapshot:
    """Build the snapshot from the parts whose sources answered.

    Returns:
        The snapshot, with one outcome per source in ``SNAPSHOT_SOURCES``.
    """
    ok = ledger.ok
    summary = parts.summary if ok(SUMMARY) else _Summary()
    kmz = parts.arrivals if ok(ARRIVALS) else ()
    mapped = {products.summary.atcf_id: products for products in summary.storms}
    storm_products = tuple(
        _with_arrivals(products, merge_arrivals(products, kmz))
        for storm in storms or ()
        for products in (mapped.get(storm.atcf_id) or StormProducts(summary=storm),)
    )
    alerts_ok = all(ok(source) for source in ALERT_SOURCES)
    return Snapshot(
        snapshot_id=snapshot_id,
        started_at=started_at,
        completed_at=completed_at,
        storms=storm_products,
        outlook_areas=summary.outlook,
        wind_probabilities=summary.winds,
        text_products=parts.texts if ok(TEXT) else (),
        gis_feed_items=parts.feeds if ok(FEEDS) else (),
        outlook_graphics=parts.graphics if ok(GRAPHICS) else (),
        breakpoints=parts.breakpoints if ok(BREAKPOINTS) else (),
        display_layers=(*summary.display, *(parts.surge if ok(PEAK_SURGE) else ())),
        alerts=dict(parts.alerts) if alerts_ok else {},
        source_outcomes=tuple(ledger.outcome(source) for source in SNAPSHOT_SOURCES),
    )


def _log_outcomes(snapshot: Snapshot, ledger: _Ledger, warnings: Sequence[DriftWarning]) -> None:
    for outcome in snapshot.source_outcomes:
        detail = outcome.error_kind or outcome.reason or ""
        answers = len(ledger.responses.get(outcome.source_id, []))
        LOGGER.info(
            "%s: %s, %d answers%s",
            outcome.source_id,
            outcome.status,
            answers,
            f" ({detail})" if detail else "",
        )
    LOGGER.info(
        "snapshot %s: %s; %d storms, %d outlook areas, %d wind-probability products, "
        "%d alert lists, %d drift warnings",
        snapshot.snapshot_id,
        snapshot.status,
        len(snapshot.storms),
        len(snapshot.outlook_areas),
        len(snapshot.wind_probabilities),
        len(snapshot.alerts),
        len(warnings),
    )


class SnapshotService:
    """Fetches and stores snapshots, and reads the stored ones back."""

    def __init__(
        self,
        engine: Engine,
        *,
        network: Network | None = None,
        now: Callable[[], datetime] = _now,
    ) -> None:
        """Create the service on an open database.

        Args:
            engine: The database.
            network: The timeout and the fetcher factory.
            now: The clock.
        """
        self._engine = engine
        self._network = network or Network()
        self._now = now
        self._repository = SnapshotRepository(engine)

    async def fetch_snapshot(self, locations: Sequence[Location]) -> FetchedSnapshot:
        """Fetch every source once, store the snapshot, and return it.

        Args:
            locations: The stored locations whose alerts the snapshot holds.

        Returns:
            The stored snapshot and its Source-drift warnings.
        """
        started = self._now()
        cache = RawResponseCache(self._engine)
        us = [location for location in locations if location.nws is not None]
        with collect_drift() as drift:
            async with self._network.fetcher(cache) as fetcher:
                run = _Run(fetcher)
                parts = _Parts()
                storms = await run.guard(nhc_current_storms.fetch_current_storms(fetcher))
                async with asyncio.TaskGroup() as group:
                    group.create_task(run.summary(storms or (), parts))
                    group.create_task(run.arrivals(storms, parts))
                    group.create_task(run.breakpoints(parts))
                    group.create_task(run.surge(parts))
                    group.create_task(run.texts(storms, parts))
                    group.create_task(run.feeds(parts))
                    group.create_task(run.graphics(parts))
                    for location in us:
                        group.create_task(run.alerts(location, parts))
        if not us:
            for source in ALERT_SOURCES:
                run.ledger.skip(source, NO_US_LOCATION)
        snapshot = assemble_snapshot(
            snapshot_id=uuid4(),
            started_at=started,
            completed_at=self._now(),
            storms=storms,
            parts=parts,
            ledger=run.ledger,
        )
        warnings = tuple(drift.warnings)
        self._repository.save(snapshot, run.ledger.all_responses(), warnings)
        _log_outcomes(snapshot, run.ledger, warnings)
        return FetchedSnapshot(snapshot, warnings)

    def latest(self) -> Snapshot | None:
        """Return the stored snapshot that completed last.

        Returns:
            The snapshot, or ``None`` when none is stored.
        """
        return self._repository.latest()

    def latest_drift_warnings(self) -> tuple[UUID, tuple[DriftWarning, ...]] | None:
        """Return the latest snapshot's id and the Source-drift warnings stored with it.

        Returns:
            The id and the warnings, or ``None`` when no snapshot is stored.
        """
        snapshot_id = self._repository.latest_id()
        if snapshot_id is None:
            return None
        return snapshot_id, self._repository.drift_warnings(snapshot_id)
