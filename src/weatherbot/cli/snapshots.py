# src/weatherbot/cli/snapshots.py
"""``weatherbot fetch``, ``storms``, and ``alerts``: the official picture, from a snapshot.

``fetch`` fetches and stores a snapshot and prints what every source answered. ``storms``
and ``alerts`` fetch one too, or with ``--no-fetch`` read the latest stored one and say
how old it is. Each exits 1 when the snapshot is partial or failed. Nothing here decides
what a product means for a location: matching a watch-warning segment or a county alert
to a place is Phase 3's.
"""

import asyncio
from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import typer

from weatherbot.cli.documents import (
    AlertEntry,
    AlertLocationEntry,
    AlertsData,
    AlertsDocument,
    ArrivalProductEntry,
    DriftWarningEntry,
    FetchCounts,
    FetchData,
    FetchDocument,
    FoundByEntry,
    OutlookEntry,
    SegmentEntry,
    SnapshotInfo,
    StormEntry,
    StormProductsEntry,
    StormsData,
    StormsDocument,
    WindProbabilityEntry,
)
from weatherbot.cli.runtime import (
    EXIT_FAILED,
    EXIT_OK,
    EXIT_USAGE,
    Context,
    Output,
    context_of,
    fail,
    open_session,
)
from weatherbot.models import Location, NwsAlert, Snapshot, StormProducts
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.locations import LocationService
from weatherbot.services.persistence.database import Database
from weatherbot.services.persistence.repositories import DriftWarning
from weatherbot.services.snapshots import SnapshotService

JsonOption = Annotated[bool, typer.Option("--json", help="Print one JSON document.")]
NoFetchOption = Annotated[
    bool, typer.Option("--no-fetch", help="Read the latest stored snapshot instead of fetching.")
]
PHASE_3_NOTE: Final = (
    "Matching a watch-warning segment to this location is Phase 3's work: Weatherbot does "
    "not decide here whether a segment applies."
)
ADD_HINT: Final = "add one with: weatherbot locations add NAME --lat LAT --lon LON"


def utc(instant: datetime) -> str:
    """Format an instant in UTC for a terminal: ``2026-10-12 21:00 UTC``.

    Args:
        instant: An aware instant.

    Returns:
        The text.
    """
    return f"{instant:%Y-%m-%d %H:%M} UTC"


def _age(seconds: float) -> str:
    minutes = round(seconds / 60)
    if minutes < 120:  # noqa: PLR2004 - two hours, in minutes
        return f"{minutes} min"
    return f"{minutes / 60:.1f} h"


def snapshot_info(snapshot: Snapshot, now: datetime) -> SnapshotInfo:
    """Describe a snapshot for a document.

    Args:
        snapshot: The snapshot.
        now: The document's time.

    Returns:
        Its id, times, status, age, and outcomes.
    """
    return SnapshotInfo(
        snapshot_id=snapshot.snapshot_id,
        started_at=snapshot.started_at,
        completed_at=snapshot.completed_at,
        status=snapshot.status,
        age_seconds=max((now - snapshot.completed_at).total_seconds(), 0.0),
        source_outcomes=snapshot.source_outcomes,
    )


def _exit_code(snapshot: Snapshot) -> int:
    return EXIT_OK if snapshot.status == "complete" else EXIT_FAILED


def _print_header(output: Output, info: SnapshotInfo, *, stored: bool) -> None:
    age = f", {_age(info.age_seconds)} old" if stored else ""
    output.line(
        f"Snapshot {info.snapshot_id} at {utc(info.completed_at)}: {info.status}{age}.",
        style="bold",
    )
    for outcome in info.source_outcomes:
        if outcome.status == "failed":
            output.line(f"  {outcome.source_id} failed ({outcome.error_kind}); its part is empty.")


def _snapshot(
    context: Context, output: Output, database: Database, *, no_fetch: bool
) -> tuple[Snapshot, tuple[DriftWarning, ...]]:
    service = SnapshotService(database.engine, network=context.network, now=context.runtime.now)
    if no_fetch:
        snapshot = service.latest()
        if snapshot is None:
            fail(output, "no snapshot is stored yet; run weatherbot fetch first")
        return snapshot, ()
    locations = LocationService(database.engine).list()
    fetched = asyncio.run(service.fetch_snapshot(locations))
    return fetched.snapshot, fetched.drift_warnings


# fetch -------------------------------------------------------------------------------------


def _counts(snapshot: Snapshot) -> FetchCounts:
    return FetchCounts(
        storms=len(snapshot.storms),
        outlook_areas=len(snapshot.outlook_areas),
        wind_probability_products=len(snapshot.wind_probabilities),
        text_products=len(snapshot.text_products),
        gis_feed_items=len(snapshot.gis_feed_items),
        outlook_graphics=len(snapshot.outlook_graphics),
        breakpoints=len(snapshot.breakpoints),
        display_layers=len(snapshot.display_layers),
    )


def drift_entries(warnings: Sequence[DriftWarning]) -> tuple[DriftWarningEntry, ...]:
    """Turn the stored drift warnings into document entries.

    Args:
        warnings: The warnings.

    Returns:
        The entries.
    """
    return tuple(DriftWarningEntry(source_id=w.source_id, message=w.message) for w in warnings)


def fetch(ctx: typer.Context, *, json_output: JsonOption = False) -> None:
    """Fetch every official source once, store the snapshot, and print each outcome."""
    context = context_of(ctx)
    output = Output(context.runtime, json_mode=json_output)
    with open_session(context, output) as database:
        snapshot, warnings = _snapshot(context, output, database, no_fetch=False)
    now = context.runtime.now()
    info = snapshot_info(snapshot, now)
    if json_output:
        output.document(
            FetchDocument(
                generated_at=now,
                disclaimer=NOTICE,
                snapshot=info,
                data=FetchData(
                    counts=_counts(snapshot),
                    alerts={name: len(alerts) for name, alerts in snapshot.alerts.items()},
                    drift_warnings=drift_entries(warnings),
                ),
            )
        )
        raise typer.Exit(_exit_code(snapshot))
    _print_header(output, info, stored=False)
    output.table(
        "Source outcomes",
        ("Source", "Outcome", "Detail"),
        [(o.source_id, o.status, o.error_kind or o.reason or "") for o in snapshot.source_outcomes],
    )
    counts = _counts(snapshot)
    output.line(
        f"Stored {counts.storms} storms, {counts.outlook_areas} outlook areas, "
        f"{counts.wind_probability_products} wind-probability products, "
        f"{counts.text_products} text products, and alerts for {len(snapshot.alerts)} "
        "locations."
    )
    for warning in warnings:
        output.line(f"Source drift: {warning.message}", style="yellow")
    output.notice()
    raise typer.Exit(_exit_code(snapshot))


# storms ------------------------------------------------------------------------------------


def _products(storm: StormProducts) -> StormProductsEntry:
    return StormProductsEntry(
        cone=storm.cone is not None,
        track=storm.track is not None,
        track_points=len(storm.track_points),
        watch_warning_segments=len(storm.watch_warnings),
        wind_radii=len(storm.wind_radii),
        arrival_times=tuple(
            ArrivalProductEntry(
                kind=product.kind,
                origin=product.origin,
                advisory=str(product.advisory.number),
                published_at=product.published_at,
                time_zone=product.time_zone,
                lines=len(product.lines),
                withheld_reason=product.withheld_reason,
            )
            for product in storm.arrival_times
        ),
    )


def storm_entries(snapshot: Snapshot) -> tuple[StormEntry, ...]:
    """Describe the snapshot's storms.

    Args:
        snapshot: The snapshot.

    Returns:
        One entry per active storm, in the roster's order.
    """
    return tuple(
        StormEntry(
            atcf_id=s.summary.atcf_id,
            slot=s.summary.slot,
            name=s.summary.name,
            classification=s.summary.classification,
            intensity_kt=s.summary.intensity_kt,
            pressure_mb=s.summary.pressure_mb,
            movement_dir_deg=s.summary.movement_dir_deg,
            movement_speed_mph=s.summary.movement_speed_mph,
            advisory=str(s.summary.public_advisory.advisory),
            advisory_issued_at=s.summary.public_advisory.issued_at,
            last_update=s.summary.last_update,
            products=_products(s),
        )
        for s in snapshot.storms
    )


def _storms_data(snapshot: Snapshot) -> StormsData:
    return StormsData(
        storms=storm_entries(snapshot),
        outlook=tuple(
            OutlookEntry(
                basin=area.basin,
                kind=area.kind,
                chance_2day_pct=area.chance_2day_pct,
                chance_7day_pct=area.chance_7day_pct,
                risk_2day=area.risk_2day,
                risk_7day=area.risk_7day,
                issued_at=area.issued_at,
            )
            for area in snapshot.outlook_areas
        ),
        wind_probabilities=tuple(
            WindProbabilityEntry(
                threshold_kt=product.threshold_kt,
                synoptic_at=product.synoptic_at,
                bands=len(product.bands),
            )
            for product in snapshot.wind_probabilities
        ),
    )


def _optional(value: float | None, unit: str) -> str:
    return "-" if value is None else f"{value:.0f} {unit}"


def _movement(storm: StormEntry) -> str:
    if storm.movement_dir_deg is None or storm.movement_speed_mph is None:
        return "-"
    return f"{storm.movement_dir_deg:.0f} deg at {storm.movement_speed_mph:.0f} mph"


def _held(products: StormProductsEntry) -> str:
    held = [
        name for name, present in (("cone", products.cone), ("track", products.track)) if present
    ]
    if products.track_points:
        held.append(f"{products.track_points} track points")
    if products.watch_warning_segments:
        held.append(f"{products.watch_warning_segments} watch-warning segments")
    if products.wind_radii:
        held.append(f"{products.wind_radii} wind radii")
    held.extend(
        f"{arrival.kind.replace('_', ' ')} arrival times ({arrival.origin}, adv {arrival.advisory})"
        for arrival in products.arrival_times
    )
    return "; ".join(held) or "none"


def _chance(value: int | None) -> str:
    return "-" if value is None else f"{value}%"


def _print_storms(output: Output, data: StormsData) -> None:
    if not data.storms:
        output.line("No active storm: NHC lists no tropical cyclone right now.")
    else:
        output.table(
            "Active storms",
            ("ATCF id", "Name", "Class", "Wind", "Pressure", "Movement", "Advisory", "Products"),
            [
                (
                    storm.atcf_id,
                    storm.name,
                    storm.classification.raw,
                    _optional(storm.intensity_kt, "kt"),
                    _optional(storm.pressure_mb, "mb"),
                    _movement(storm),
                    f"{storm.advisory} at {utc(storm.advisory_issued_at)}",
                    _held(storm.products),
                )
                for storm in data.storms
            ],
        )
    basins = sorted({area.basin for area in data.outlook})
    if not basins:
        output.line("The outlook holds no area.")
    for basin in basins:
        output.table(
            f"Outlook: {basin}",
            ("Area", "2-day chance", "7-day chance", "Issued"),
            [
                (
                    area.kind.replace("_", " "),
                    _chance(area.chance_2day_pct),
                    _chance(area.chance_7day_pct),
                    utc(area.issued_at),
                )
                for area in data.outlook
                if area.basin == basin
            ],
        )
    if data.wind_probabilities:
        synoptic = sorted({utc(product.synoptic_at) for product in data.wind_probabilities})
        thresholds = ", ".join(f"{p.threshold_kt} kt" for p in data.wind_probabilities)
        output.line(
            f"Wind-speed probabilities ({thresholds}) of synoptic time {', '.join(synoptic)}."
        )
    else:
        output.line("The snapshot holds no wind-speed-probability product.")


def storms(
    ctx: typer.Context, *, json_output: JsonOption = False, no_fetch: NoFetchOption = False
) -> None:
    """Print the active storms, the outlook, and the wind-probability synoptic time."""
    context = context_of(ctx)
    output = Output(context.runtime, json_mode=json_output)
    with open_session(context, output) as database:
        snapshot, _ = _snapshot(context, output, database, no_fetch=no_fetch)
    now = context.runtime.now()
    info = snapshot_info(snapshot, now)
    data = _storms_data(snapshot)
    if json_output:
        output.document(
            StormsDocument(generated_at=now, disclaimer=NOTICE, snapshot=info, data=data)
        )
        raise typer.Exit(_exit_code(snapshot))
    _print_header(output, info, stored=no_fetch)
    _print_storms(output, data)
    output.notice()
    raise typer.Exit(_exit_code(snapshot))


# alerts ------------------------------------------------------------------------------------


def _local(instant: datetime, zone: ZoneInfo | None) -> str | None:
    return instant.astimezone(zone).isoformat() if zone is not None else None


def _zone(location: Location) -> ZoneInfo | None:
    return _named_zone(location.nws.time_zone if location.nws else None)


def alert_entries(alerts: Sequence[NwsAlert], zone: ZoneInfo | None) -> tuple[AlertEntry, ...]:
    """Describe a location's alerts.

    Args:
        alerts: The alerts.
        zone: The location's time zone, if known.

    Returns:
        The entries.
    """
    return tuple(
        AlertEntry(
            id=alert.id,
            event=alert.event,
            severity=alert.severity,
            urgency=alert.urgency,
            certainty=alert.certainty,
            headline=alert.headline,
            effective=alert.effective,
            expires=alert.expires,
            effective_local=_local(alert.effective, zone),
            expires_local=_local(alert.expires, zone),
            found_by=tuple(FoundByEntry(kind=q.kind, zone_id=q.zone_id) for q in alert.found_by),
            affected_zone_ids=alert.affected_zone_ids,
        )
        for alert in alerts
    )


def segment_entries(snapshot: Snapshot) -> tuple[SegmentEntry, ...]:
    """List every active storm's official watch-warning segments, verbatim.

    Args:
        snapshot: The snapshot.

    Returns:
        One entry per segment.
    """
    return tuple(
        SegmentEntry(
            atcf_id=storm.summary.atcf_id,
            storm_name=storm.summary.name,
            tcww=segment.tcww,
            advisory=str(segment.advisory.number),
        )
        for storm in snapshot.storms
        for segment in storm.watch_warnings
    )


def _pick(output: Output, locations: Sequence[Location], name: str | None) -> Location:
    if not locations:
        fail(output, f"no location is stored; {ADD_HINT}", EXIT_USAGE)
    if name is None:
        if len(locations) > 1:
            names = ", ".join(repr(location.name) for location in locations)
            fail(output, f"choose a location with --location: {names}", EXIT_USAGE)
        return locations[0]
    found = next((location for location in locations if location.name == name), None)
    if found is None:
        fail(output, f"no location is named {name!r}", EXIT_USAGE)
    return found


def _alerts_data(snapshot: Snapshot, location: Location) -> AlertsData:
    zone = _zone(location)
    nws = location.nws
    entry = AlertLocationEntry(
        name=location.name,
        inside_nws_coverage=nws is not None,
        time_zone=nws.time_zone if nws else None,
        forecast_zone=nws.forecast_zone if nws else None,
        county_zone=nws.county_zone if nws else None,
    )
    if nws is None:
        return AlertsData(
            location=entry,
            alerts=None,
            watch_warnings=segment_entries(snapshot),
            note=f"The NWS does not cover {location.name}. {PHASE_3_NOTE}",
        )
    alerts = snapshot.alerts.get(location.name)
    note = None
    if alerts is None:
        note = (
            f"This snapshot holds no alert list for {location.name}: its alert sources "
            "failed, or the location was added after it."
        )
    return AlertsData(
        location=entry,
        alerts=alert_entries(alerts, zone) if alerts is not None else None,
        watch_warnings=(),
        note=note,
    )


def _when(instant: datetime, zone: ZoneInfo | None) -> str:
    if zone is None:
        return utc(instant)
    return f"{utc(instant)} ({instant.astimezone(zone):%Y-%m-%d %H:%M %Z})"


def _named_zone(name: str | None) -> ZoneInfo | None:
    try:
        return ZoneInfo(name) if name else None
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _print_alerts(output: Output, data: AlertsData) -> None:
    location = data.location
    if not location.inside_nws_coverage:
        output.line(f"{location.name} is outside NWS coverage: the NWS issues no alerts for it.")
        if data.watch_warnings:
            output.table(
                "Official watch-warning segments of the active storms",
                ("Storm", "ATCF id", "Code", "Meaning", "Advisory"),
                [
                    (
                        segment.storm_name,
                        segment.atcf_id,
                        segment.tcww.raw,
                        segment.tcww.code.name.replace("_", " ").title()
                        if segment.tcww.code
                        else "unrecognized code",
                        segment.advisory,
                    )
                    for segment in data.watch_warnings
                ],
            )
        else:
            output.line("No active storm has a watch-warning segment.")
        output.line(PHASE_3_NOTE)
        return
    zones = f"forecast zone {location.forecast_zone}, county {location.county_zone}"
    output.line(f"Alerts for {location.name} ({zones}, {location.time_zone}):", style="bold")
    if data.alerts is None:
        output.line(data.note or "No alert list.")
        return
    if not data.alerts:
        output.line("No active NWS alert.")
    zone = _named_zone(location.time_zone)
    for alert in data.alerts:
        output.line()
        output.line(alert.event, style="bold")
        output.line(f"  Severity {alert.severity.raw}, urgency {alert.urgency.raw}")
        if alert.headline:
            output.line(f"  {alert.headline}")
        output.line(f"  Effective {_when(alert.effective, zone)}")
        output.line(f"  Expires   {_when(alert.expires, zone)}")
        found = ", ".join(q.zone_id or "the point" for q in alert.found_by)
        output.line(f"  Found by  {found}")
        output.line(f"  Zones     {', '.join(alert.affected_zone_ids) or '-'}")


def alerts(
    ctx: typer.Context,
    *,
    location: Annotated[
        str | None,
        typer.Option("--location", help="The location's name; optional with one location."),
    ] = None,
    json_output: JsonOption = False,
    no_fetch: NoFetchOption = False,
) -> None:
    """Print a location's NWS alerts, or the storms' watch-warning segments outside the US."""
    context = context_of(ctx)
    output = Output(context.runtime, json_mode=json_output)
    with open_session(context, output) as database:
        chosen = _pick(output, LocationService(database.engine).list(), location)
        snapshot, _ = _snapshot(context, output, database, no_fetch=no_fetch)
    now = context.runtime.now()
    info = snapshot_info(snapshot, now)
    data = _alerts_data(snapshot, chosen)
    missing = chosen.nws is not None and data.alerts is None
    code = EXIT_FAILED if missing else _exit_code(snapshot)
    if json_output:
        output.document(
            AlertsDocument(generated_at=now, disclaimer=NOTICE, snapshot=info, data=data)
        )
        raise typer.Exit(code)
    _print_header(output, info, stored=no_fetch)
    _print_alerts(output, data)
    output.notice()
    raise typer.Exit(code)
