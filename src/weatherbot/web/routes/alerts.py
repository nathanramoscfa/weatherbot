# src/weatherbot/web/routes/alerts.py
"""``GET /api/alerts``: per-location NWS alerts and NHC watch-warning segments."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Request

from weatherbot.models import Location, NwsAlert, OfficialProduct, Snapshot, Thresholds
from weatherbot.services.assessments import is_county_context, official_products
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.persistence.repositories import LocationRepository, SnapshotRepository
from weatherbot.web.map_layers import get_cached_snapshot_bundle
from weatherbot.web.routes.assessments import round_km
from weatherbot.web.schemas import (
    AlertFoundByResponse,
    AlertLocationMetadataResponse,
    AlertsResponse,
    LocationAlertResponse,
    LocationAlertsGroupResponse,
    WatchWarningSegmentResponse,
)

if TYPE_CHECKING:
    from weatherbot.web.app import WebState

router = APIRouter()


def named_zone(name: str | None) -> ZoneInfo | None:
    """Resolve an IANA time zone name if known on this machine."""
    try:
        return ZoneInfo(name) if name else None
    except (ZoneInfoNotFoundError, ValueError):
        return None


def local_iso(instant: datetime, zone: ZoneInfo | None) -> str | None:
    """Format an aware instant as ISO 8601 in ``zone``, or ``None`` when ``zone`` is absent."""
    return instant.astimezone(zone).isoformat() if zone is not None else None


def _alert_entries(
    alerts: Sequence[NwsAlert],
    zone: ZoneInfo | None,
    coverage: Sequence[OfficialProduct],
) -> tuple[LocationAlertResponse, ...]:
    by_id = {product.alert_id: product for product in coverage if product.kind == "nws_alert"}
    return tuple(
        LocationAlertResponse(
            id=alert.id,
            event=alert.event,
            severity=alert.severity,
            urgency=alert.urgency,
            certainty=alert.certainty,
            headline=alert.headline,
            effective=alert.effective,
            expires=alert.expires,
            effective_local=local_iso(alert.effective, zone),
            expires_local=local_iso(alert.expires, zone),
            sender_name=alert.sender_name,
            vtec=alert.vtec,
            found_by=tuple(
                AlertFoundByResponse(kind=q.kind, zone_id=q.zone_id) for q in alert.found_by
            ),
            affected_zone_ids=alert.affected_zone_ids,
            covers=product.covers,
            is_county_context=is_county_context(product),
            coverage=product.reason,
            rule=str(product.rule) if product.rule is not None else None,
        )
        for alert in alerts
        for product in (by_id[alert.id],)
    )


def _segment_entries(
    snapshot: Snapshot,
    coverage: Sequence[OfficialProduct],
    *,
    every: bool,
) -> tuple[WatchWarningSegmentResponse, ...]:
    covering = [product for product in coverage if product.kind == "watch_warning_segment"]
    first: list[WatchWarningSegmentResponse] = []
    rest: list[WatchWarningSegmentResponse] = []
    for storm in snapshot.storms:
        for segment in storm.watch_warnings:
            advisory = str(segment.advisory.number)
            key = (storm.atcf_id, segment.tcww.raw, advisory)
            match = next(
                (p for p in covering if (p.atcf_id, p.code, str(p.advisory)) == key),
                None,
            )
            if match is not None:
                covering.remove(match)
            entry = WatchWarningSegmentResponse(
                atcf_id=storm.atcf_id,
                storm_name=storm.name,
                tcww=segment.tcww,
                advisory=advisory,
                issued_at=segment.advisory.issued_at,
                covers=match is not None,
                distance_km=round_km(match.distance_km) if match is not None else None,
                at_end=match.at_end if match is not None else None,
                breakpoints=match.breakpoints if match is not None else (),
                coverage=match.reason if match is not None else None,
                rule=(str(match.rule) if match is not None and match.rule is not None else None),
            )
            (first if match is not None else rest).append(entry)
    return (*first, *rest) if every else tuple(first)


def _location_metadata(location: Location) -> AlertLocationMetadataResponse:
    nws = location.nws
    return AlertLocationMetadataResponse(
        name=location.name,
        inside_nws_coverage=nws is not None,
        time_zone=nws.time_zone if nws is not None else None,
        forecast_zone=nws.forecast_zone if nws is not None else None,
        county_zone=nws.county_zone if nws is not None else None,
    )


def _location_alerts_group(
    snapshot: Snapshot | None,
    location: Location,
    thresholds: Thresholds,
) -> LocationAlertsGroupResponse:
    metadata = _location_metadata(location)
    if snapshot is None:
        return LocationAlertsGroupResponse(
            location=metadata,
            alerts=None,
            watch_warnings=(),
            note="No snapshot is stored yet.",
        )
    coverage = official_products(snapshot, location, thresholds)
    if location.nws is None:
        return LocationAlertsGroupResponse(
            location=metadata,
            alerts=None,
            watch_warnings=_segment_entries(snapshot, coverage, every=True),
            note=(
                f"The NWS does not cover {location.name}; NHC's segments are its watches "
                "and warnings."
            ),
        )
    alerts = snapshot.alerts.get(location.name)
    note: str | None = None
    if alerts is None:
        note = (
            f"This snapshot holds no alert list for {location.name}: its alert sources "
            "failed, or the location was added after it."
        )
    zone = named_zone(location.nws.time_zone)
    return LocationAlertsGroupResponse(
        location=metadata,
        alerts=_alert_entries(alerts, zone, coverage) if alerts is not None else None,
        watch_warnings=_segment_entries(snapshot, coverage, every=False),
        note=note,
    )


@router.get("/api/alerts")
def get_alerts(request: Request) -> AlertsResponse:
    """Return active NWS alerts and NHC watch-warning segments for each stored location."""
    state = cast("WebState", request.app.state.web)
    engine = state.database.engine
    now = state.clock().astimezone(UTC)
    thresholds = state.settings.engine.thresholds()

    locations = LocationRepository(engine, now=state.clock).list()
    bundle = get_cached_snapshot_bundle(SnapshotRepository(engine))
    snapshot = bundle.snapshot if bundle is not None else None
    snapshot_summary = bundle.summary(now) if bundle is not None else None

    return AlertsResponse(
        snapshot=snapshot_summary,
        locations=tuple(_location_alerts_group(snapshot, loc, thresholds) for loc in locations),
        notice=NOTICE,
    )
