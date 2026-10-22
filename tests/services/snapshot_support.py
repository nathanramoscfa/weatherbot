# tests/services/snapshot_support.py
"""A ``Snapshot`` built from the recorded fixtures through the Step 2-4 parsers.

Every recorded answer is served by respx, and the real fetch functions parse it: the
roster, the summary service's storm, display, outlook, and wind-probability layers, the
breakpoints, the peak surge, the archived Dorian arrival-time KMZ pair, the TCP and TWO
lists, the GIS feeds, the outlook graphics, and the Miami-Dade landmark's point and
alerts. ``with_second_storm`` gives Dorian every kind of storm product as well.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import httpx
import respx
from fixture_support import latest_live
from source_support import NOW, Quiet, serve

from check_personal_data import load_landmarks
from weatherbot.models import (
    Advisory,
    AdvisoryNumber,
    ConeGeometry,
    ForecastTrack,
    LatLon,
    Location,
    NwsCoverage,
    RosterProduct,
    Snapshot,
    SourceId,
    SourceOutcome,
    StormClassification,
    StormProducts,
    StormSummary,
    TrackPoint,
    WatchWarningSegment,
    WindRadii,
)
from weatherbot.services.persistence.raw_cache import CachedFetch
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
from weatherbot.sources.http import FetchResult, SourceResult

SNAPSHOT_ID = UUID("8f0c4d1e-5b7a-4c2e-9d3f-1a2b3c4d5e6f")
LANDMARK_NAME = "Miami-Dade County Hall"
SERVED: tuple[SourceId, ...] = (
    "nhc-current-storms",
    "nhc-arrival-times",
    "nhc-map-tropical-summary",
    "nhc-map-breakpoints",
    "nhc-map-peak-surge",
    "nhc-gis-rss",
    "nhc-text-products",
    "nhc-outlook-graphics",
    "nws-points",
    "nws-alerts-point",
    "nws-alerts-zone",
)
ARCHIVE = "https://www.nhc.noaa.gov/storm_graphics/api/AL052019_036adv_{kind}_toa_34.kmz"
DORIAN_PUBLISHED = datetime(2019, 9, 2, 9, tzinfo=UTC)  # 500 AM EDT Mon Sep 02 2019


def landmark_point(key: str = "miami-dade") -> tuple[float, float]:
    """A landmark's coordinates, from scripts/public_landmarks.toml."""
    found = next(item for item in load_landmarks() if item.key == key)
    return float(found.lat), float(found.lon)


def landmark_location(coverage: NwsCoverage | None = None) -> Location:
    """The Miami-Dade landmark as a location."""
    lat, lon = landmark_point()
    return Location(name=LANDMARK_NAME, point=LatLon(latitude=lat, longitude=lon), nws=coverage)


def dorian() -> StormSummary:
    """A roster entry that links the archived Dorian 036 arrival-time pair.

    Its center is the Nassau landmark: tests hold no other coordinate.
    """
    latitude, longitude = landmark_point("nassau")

    def product(url: str) -> RosterProduct:
        return RosterProduct(
            advisory=AdvisoryNumber.parse("036"), issued_at=DORIAN_PUBLISHED, url=url
        )

    return StormSummary(
        atcf_id="AL052019",
        slot="AT5",
        name="Dorian",
        classification=StormClassification.parse("HU"),
        intensity_kt=145,
        pressure_mb=913,
        latitude=latitude,
        longitude=longitude,
        movement_dir_deg=None,
        movement_speed_mph=None,
        last_update=DORIAN_PUBLISHED,
        public_advisory=product("https://www.nhc.noaa.gov/text/MIATCPAT5.shtml"),
        earliest_arrival_kmz=product(ARCHIVE.format(kind="earliest_reasonable")),
        most_likely_arrival_kmz=product(ARCHIVE.format(kind="most_likely")),
        has_storm_surge_watch_warning=False,
        has_potential_storm_surge_flooding=False,
        has_peak_surge=False,
    )


def _relabelled[R: (ConeGeometry, ForecastTrack, TrackPoint, WatchWarningSegment, WindRadii)](
    record: R, atcf_id: str
) -> R:
    """A storm product as another storm's: the same fields under another ATCF id."""
    update: dict[str, object] = {"atcf_id": atcf_id}
    if isinstance(record.advisory, Advisory):
        update["advisory"] = record.advisory.model_copy(update={"atcf_id": atcf_id})
    return record.model_copy(update=update)


def with_second_storm(snapshot: Snapshot) -> Snapshot:
    """The recorded snapshot with a second storm that holds every kind of storm product.

    The second storm is Dorian (``dorian()``, centered on the Nassau landmark) with the
    recorded storm's cone, track, points, segments, and radii as its own, beside its
    archived arrival-time pair. Positions restart for each storm, so the two storms'
    products share positions within the snapshot.
    """
    first, archived = snapshot.storms
    summary = dorian()
    atcf_id = summary.atcf_id
    assert first.cone is not None
    assert first.track is not None
    second = StormProducts(
        summary=summary,
        cone=_relabelled(first.cone, atcf_id),
        track=_relabelled(first.track, atcf_id),
        track_points=tuple(_relabelled(point, atcf_id) for point in first.track_points),
        watch_warnings=tuple(_relabelled(segment, atcf_id) for segment in first.watch_warnings),
        wind_radii=tuple(_relabelled(radii, atcf_id) for radii in first.wind_radii),
        arrival_times=archived.arrival_times,
    )
    return snapshot.model_copy(update={"storms": (first, second)})


@dataclass(frozen=True)
class RecordedSnapshot:
    """The snapshot, its location, and every answer behind it."""

    snapshot: Snapshot
    location: Location
    responses: tuple[CachedFetch, ...]


def _cached(results: Sequence[SourceResult[object]]) -> tuple[CachedFetch, ...]:
    return tuple(
        CachedFetch(answer, product_key=_product_key(answer))
        for result in results
        for answer in result.responses
    )


def _product_key(answer: FetchResult) -> str:
    # A test's product key: the path, enough to tell the answers of one source apart.
    return httpx.URL(answer.url).path


async def recorded_snapshot() -> RecordedSnapshot:
    """Fetch every served source from the recorded fixtures and assemble the snapshot."""
    lat, lon = landmark_point()
    with respx.mock(assert_all_called=False) as router:
        for source in SERVED:
            directory = latest_live(source)
            assert directory is not None, f"{source} has no live capture"
            serve(router, directory)
        async with httpx.AsyncClient() as client:
            fetcher = Quiet().fetcher(client)
            roster = await nhc_current_storms.fetch_current_storms(fetcher)
            storms = roster.records
            summary = await arcgis.fetch_catalog(fetcher, arcgis.TROPICAL_SUMMARY)
            products = await nhc_map.fetch_storm_products(fetcher, summary.records, storms)
            display = await nhc_map.fetch_storm_display_layers(fetcher, summary.records, storms)
            outlook = await nhc_map.fetch_outlook(fetcher, summary.records)
            winds = await nhc_map.fetch_wind_probabilities(fetcher, summary.records, storms)
            breakpoints_catalog = await arcgis.fetch_catalog(fetcher, arcgis.BREAKPOINTS)
            breakpoints = await nhc_map.fetch_breakpoints(fetcher, breakpoints_catalog.records)
            surge_catalog = await arcgis.fetch_catalog(fetcher, arcgis.PEAK_SURGE)
            surge = await nhc_map.fetch_peak_surge(fetcher, surge_catalog.records)
            arrivals = await nhc_arrival_times.fetch_arrival_times(fetcher, [dorian()])
            tcps = await nhc_text_products.fetch_tcps(fetcher, storms)
            twos = await nhc_text_products.fetch_twos(fetcher)
            feeds = await nhc_gis_rss.fetch_gis_feeds(fetcher)
            graphics = await nhc_outlook_graphics.fetch_outlook_graphics(fetcher)
            point = await nws.lookup_point(fetcher, lat, lon)
            assert isinstance(point.records, NwsCoverage)
            location = landmark_location(point.records)
            alerts = await nws.fetch_alerts(fetcher, location)
    results: list[SourceResult[object]] = [
        roster,
        summary,
        products,
        display,
        outlook,
        winds,
        breakpoints_catalog,
        breakpoints,
        surge_catalog,
        surge,
        arrivals,
        tcps,
        twos,
        feeds,
        graphics,
        point,
        alerts,
    ]  # pyright: ignore[reportAssignmentType] - SourceResult is covariant in use here
    snapshot = Snapshot(
        snapshot_id=SNAPSHOT_ID,
        started_at=NOW,
        completed_at=NOW,
        storms=(
            *products.records,
            StormProducts(summary=dorian(), arrival_times=arrivals.records),
        ),
        outlook_areas=outlook.records,
        wind_probabilities=winds.records,
        text_products=(*tcps.records, *twos.records),
        gis_feed_items=feeds.records,
        outlook_graphics=graphics.records,
        breakpoints=breakpoints.records,
        display_layers=(*display.records, *surge.records),
        alerts={location.name: alerts.records},
        source_outcomes=(
            *(SourceOutcome(source_id=s, status="ok") for s in SERVED),
            SourceOutcome(source_id="geocode-nominatim", status="skipped", reason="once, at setup"),
        ),
    )
    return RecordedSnapshot(snapshot, location, _cached(results))
