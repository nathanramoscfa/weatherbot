# src/weatherbot/cli/status.py
"""``weatherbot status``: each location's level, why, and what each storm means for it.

``status`` fetches a snapshot, or with ``--no-fetch`` reads the latest stored one and says
how old it is; assesses and stores every location through the assessment service; and
prints, for each location or the one named: the level's number and name, the deciding
rule and each piece of its evidence, the actions, "at least" with the missing inputs when
the assessment is incomplete, the official products that cover the location and the
county-zone alerts outside its zones, the wind-speed probabilities there, each storm's
threat, the changes since the previous stored assessment, the breakpoint span, and the
evacuation-order toggle. Instants print in UTC and in the location's NWS time zone. It
runs one monitor cycle (``MonitorService``), so it records the cycle and the heartbeats,
and a yellow banner above the locations names every heartbeat the staleness rule finds
stale; its document lists every heartbeat. It exits 1 on a partial or failed snapshot, as
``storms`` and ``alerts`` do.

The distances and bearings it prints locate the location: they go to the operator's own
terminal, and no log line holds them.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from types import MappingProxyType
from typing import Annotated, Final
from zoneinfo import ZoneInfo

import typer

from weatherbot.cli.documents import (
    ArrivalEntry,
    ChangeEntry,
    EvacuationOrderEntry,
    EvidenceEntry,
    OfficialEntry,
    StalenessEntry,
    StatusData,
    StatusDocument,
    StatusLocationEntry,
    ThreatEntry,
    UnavailableEntry,
    WindReadingEntry,
)
from weatherbot.cli.locations import span_text
from weatherbot.cli.runtime import EXIT_USAGE, Output, context_of, fail, open_session
from weatherbot.cli.snapshots import (
    ADD_HINT,
    JsonOption,
    NoFetchOption,
    exit_code,
    kilometres,
    named_zone,
    print_header,
    run_cycle,
    snapshot_info,
    when,
)
from weatherbot.models import (
    AlertLevel,
    ArrivalReading,
    ChangeEvent,
    Evidence,
    Location,
    LocationWindProbability,
    OfficialProduct,
    StormThreat,
    UnavailableInput,
)
from weatherbot.services.assessments import (
    RULE_TRIGGERS,
    AssessedLocation,
    is_county_context,
)
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.health import Staleness, duration_text, staleness
from weatherbot.services.locations import LocationService
from weatherbot.services.persistence.repositories import HeartbeatRepository

_PRODUCTS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "nws_alert": "NWS alert",
        "watch_warning_segment": "NHC watch-warning segment",
        "cone": "NHC cone",
        "wind_probability": "NHC wind-speed probabilities",
        "development_region": "NHC outlook development region",
        "evacuation_toggle": "the operator's evacuation-order toggle",
    }
)
_TESTS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "point_query": "the point query returned it",
        "zone_list": "its zone list names the location's zone",
        "segment_distance": "the segment's distance",
        "point_in_polygon": "the location is inside the shape",
        "band": "the band that holds the location",
        "toggle": "the toggle is on",
    }
)
_CONE: Final[Mapping[bool | None, str]] = MappingProxyType(
    {
        True: "the location is inside its cone",
        False: "the location is outside its cone",
        None: "the snapshot holds no usable cone for it",
    }
)
HELD_AT: Final = AlertLevel.WARNING_WATCH_EVACUATION


# The document -----------------------------------------------------------------------------


def _bearing(value: float | None) -> int | None:
    return round(value) % 360 if value is not None else None


def _hours(value: float | None) -> float | None:
    return round(value, 1) if value is not None else None


def _evidence(item: Evidence) -> EvidenceEntry:
    return EvidenceEntry(
        product=item.product,
        source_id=item.source_id,
        code=item.code,
        atcf_id=item.atcf_id,
        storm_name=item.storm_name,
        advisory=str(item.advisory) if item.advisory is not None else None,
        issued_at=item.issued_at,
        test=item.test,
        distance_km=kilometres(item.distance_km),
        at_end=item.at_end,
        crs=item.crs,
        closest_approach_at=item.closest_approach_at,
        lead_h=_hours(item.lead_h),
        detail=item.detail,
    )


def _official(product: OfficialProduct) -> OfficialEntry:
    return OfficialEntry(
        kind=product.kind,
        code=product.code,
        alert_id=product.alert_id,
        issuer=product.issuer,
        atcf_id=product.atcf_id,
        storm_name=product.storm_name,
        advisory=str(product.advisory) if product.advisory is not None else None,
        issued_at=product.issued_at,
        expires_at=product.expires_at,
        zones=product.zones,
        distance_km=kilometres(product.distance_km),
        breakpoints=product.breakpoints,
        covers=product.covers,
        rule=str(product.rule) if product.rule is not None else None,
        reason=product.reason,
    )


def _wind(reading: LocationWindProbability) -> WindReadingEntry:
    return WindReadingEntry(
        threshold_kt=reading.threshold_kt,
        synoptic_at=reading.synoptic_at,
        reading=reading.reading,
        label=reading.label,
        lower_pct=reading.lower_pct,
        upper_pct=reading.upper_pct,
    )


def _arrival(reading: ArrivalReading) -> ArrivalEntry:
    return ArrivalEntry(
        kind=reading.kind,
        origin=reading.origin,
        reading=reading.reading,
        advisory=str(reading.advisory) if reading.advisory is not None else None,
        start=reading.start,
        end=reading.end,
        approach_at=reading.approach_at,
        label=reading.label,
        reason=reading.reason,
    )


def _threat(threat: StormThreat) -> ThreatEntry:
    return ThreatEntry(
        atcf_id=threat.atcf_id,
        storm_name=threat.storm_name,
        advisory=str(threat.advisory) if threat.advisory is not None else None,
        issued_at=threat.issued_at,
        category=threat.category,
        development=threat.development,
        in_cone=threat.in_cone,
        distance_km=kilometres(threat.distance_km),
        bearing_deg=_bearing(threat.bearing_deg),
        closest_approach_at=threat.closest_approach_at,
        closest_approach_km=kilometres(threat.closest_approach_km),
        lead_h=_hours(threat.lead_h),
        hurricane_by_approach=threat.hurricane_by_approach,
        earliest_arrival=_arrival(threat.earliest_arrival),
        most_likely_arrival=_arrival(threat.most_likely_arrival),
    )


def _unavailable(item: UnavailableInput) -> UnavailableEntry:
    return UnavailableEntry(
        kind=item.kind,
        source_id=item.source_id,
        storm_name=item.storm_name,
        threshold_kt=item.threshold_kt,
        reason=item.reason,
    )


def change_entries(changes: Sequence[ChangeEvent]) -> tuple[ChangeEntry, ...]:
    """Describe change events for a document.

    Args:
        changes: The events, in ``diff``'s order.

    Returns:
        Their kinds and printable sentences.
    """
    return tuple(ChangeEntry(kind=event.kind, detail=event.detail) for event in changes)


def staleness_entries(judged: Sequence[Staleness]) -> tuple[StalenessEntry, ...]:
    """Describe the judged heartbeats for a document.

    Args:
        judged: The staleness rule's judgements.

    Returns:
        One entry per heartbeat.
    """
    return tuple(
        StalenessEntry(
            kind=item.kind,
            name=item.name,
            last_success_at=item.last_success_at,
            expected_every_s=item.expected_every_s,
            age_s=item.age_s,
            stale=item.stale,
        )
        for item in judged
    )


def stale_lines(entries: Sequence[StalenessEntry]) -> list[str]:
    """Say each stale heartbeat in a line, for a banner.

    Args:
        entries: The heartbeats.

    Returns:
        One line per stale heartbeat; none when nothing is stale.
    """
    lines: list[str] = []
    for entry in entries:
        if not entry.stale or entry.expected_every_s is None:
            continue
        cadence = duration_text(entry.expected_every_s)
        if entry.age_s is None:
            lines.append(f"Stale data: {entry.name} has never succeeded; expected every {cadence}.")
        else:
            age = duration_text(entry.age_s)
            lines.append(
                f"Stale data: {entry.name} last succeeded {age} ago; expected every {cadence}."
            )
    return lines


def _entry(result: AssessedLocation) -> StatusLocationEntry:
    location, stored = result.location, result.stored
    assessment = stored.assessment
    level = assessment.level
    return StatusLocationEntry(
        name=location.name,
        inside_nws_coverage=location.nws is not None,
        time_zone=location.nws.time_zone if location.nws else None,
        as_of=assessment.as_of,
        level=int(level),
        level_name=level.label,
        actions=level.actions,
        rule=str(assessment.rule),
        rule_trigger=RULE_TRIGGERS[assessment.rule],
        complete=assessment.complete,
        unavailable=tuple(_unavailable(item) for item in assessment.unavailable),
        evidence=tuple(_evidence(item) for item in assessment.evidence),
        official=tuple(
            _official(product)
            for product in assessment.official
            if product.covers or is_county_context(product)
        ),
        wind_probabilities=tuple(_wind(reading) for reading in assessment.wind_probabilities),
        threats=tuple(_threat(threat) for threat in assessment.threats),
        changes=change_entries(stored.changes),
        breakpoint_span=assessment.breakpoint_span,
        evacuation_order=EvacuationOrderEntry(
            on=location.evacuation_order_in_effect, set_at=location.evacuation_order_set_at
        ),
        ruleset=assessment.ruleset,
        stored_before=not result.created,
        toggle_changed=result.toggle_changed,
    )


# The terminal -----------------------------------------------------------------------------


def _at(instant: datetime | None, zone: ZoneInfo | None) -> str:
    return when(instant, zone) if instant is not None else "an unstated time"


def _evidence_facts(item: EvidenceEntry, zone: ZoneInfo | None) -> str:
    product = _PRODUCTS[item.product]
    if item.product == "evacuation_toggle":
        since = f", on since {_at(item.issued_at, zone)}" if item.issued_at else ""
        return f"{product}{since}"
    facts = [f"{product}, issued {_at(item.issued_at, zone)}", f"test: {_TESTS[item.test]}"]
    if item.distance_km is not None:
        end = ", at its end" if item.at_end else ""
        facts.append(f"{item.distance_km:.1f} km{end}")
    return "; ".join(facts)


def _official_text(product: OfficialEntry, zone: ZoneInfo | None) -> str:
    if product.kind == "nws_alert":
        until = f", until {_at(product.expires_at, zone)}" if product.expires_at else ""
        issued = f"{product.code} from {product.issuer or 'the NWS'}"
        if not product.covers:
            return f"{issued}{until}: zones {', '.join(product.zones) or '-'}"
        return f"{issued}, issued {_at(product.issued_at, zone)}{until}: {product.reason}"
    return (
        f"NHC {product.code} for {product.storm_name}, advisory {product.advisory}: "
        f"{product.reason}"
    )


def _wind_text(reading: WindReadingEntry) -> str:
    if reading.reading == "band":
        found = f"the {reading.label} band"
    elif reading.reading == "below_every_band":
        found = "below every band"
    else:
        found = "outside the product's coverage, so it says nothing here"
    return f"{reading.threshold_kt} kt, synoptic time {when(reading.synoptic_at, None)}: {found}"


def _arrival_text(reading: ArrivalEntry, zone: ZoneInfo | None) -> str:
    match reading.reading:
        case "before":
            found = f"before {_at(reading.end, zone)}"
        case "between":
            found = f"between {_at(reading.start, zone)} and {_at(reading.end, zone)}"
        case "after":
            found = f"after {_at(reading.start, zone)}"
        case "outside":
            found = "none within the product's 120 hours: outside its 5 percent contour"
        case "unresolved":
            found = f"unresolved: {reading.reason}"
        case _:
            return f"{_at(reading.approach_at, zone)} ({reading.label})"
    origin = "KMZ" if reading.origin == "kmz" else "map layer"
    return f"{found} (the {origin} product of advisory {reading.advisory})"


def _print_threat(output: Output, threat: ThreatEntry, zone: ZoneInfo | None) -> None:
    issued = f" of {_at(threat.issued_at, zone)}" if threat.issued_at else ""
    advisory = f", advisory {threat.advisory}{issued}" if threat.advisory else ""
    output.line(f"  Storm {threat.storm_name} ({threat.atcf_id}){advisory}:")
    if threat.category is not None:
        strength = f"Category {threat.category}"
    elif threat.development is not None:
        strength = "Below hurricane strength"
    else:
        strength = "Strength unknown"
    development = f" ({threat.development})" if threat.development else ""
    output.line(f"    {strength}{development}; {_CONE[threat.in_cone]}.")
    if threat.distance_km is None or threat.closest_approach_km is None:
        output.line(
            "    Center and closest approach unknown: the snapshot holds no forecast points."
        )
    else:
        output.line(
            f"    From its center: {threat.distance_km:.0f} km, bearing {threat.bearing_deg} deg."
        )
        hurricane = "a hurricane" if threat.hurricane_by_approach else "not a hurricane"
        output.line(
            f"    Closest approach: {threat.closest_approach_km:.0f} km at "
            f"{_at(threat.closest_approach_at, zone)}, {threat.lead_h:.0f} h after the "
            f"snapshot; {hurricane} by then."
        )
    output.line(
        "    Earliest-reasonable arrival of tropical-storm-force winds: "
        f"{_arrival_text(threat.earliest_arrival, zone)}."
    )
    output.line(f"    Most-likely arrival: {_arrival_text(threat.most_likely_arrival, zone)}.")


def _print_level(output: Output, entry: StatusLocationEntry) -> None:
    floor = "" if entry.complete else "at least "
    output.line(f"{entry.name}: {floor}level {entry.level}, {entry.level_name}", style="bold")
    if entry.toggle_changed:
        output.line(
            "  The evacuation-order toggle was set after this snapshot's assessment was "
            "stored, so this level did not read it. Run weatherbot status without "
            "--no-fetch to assess a new snapshot with it.",
            style="yellow",
        )
    output.line(f"  Decided by {entry.rule}: {entry.rule_trigger}")
    output.line(f"  Actions: {entry.actions}")
    if not entry.complete:
        output.line(
            "  At least: the level is a floor, because these inputs were unavailable:",
            style="yellow",
        )
        for item in entry.unavailable:
            output.line(f"    - {item.reason}")


def _print_official(output: Output, entry: StatusLocationEntry, zone: ZoneInfo | None) -> None:
    covering = [product for product in entry.official if product.covers]
    context = [product for product in entry.official if not product.covers]
    if not covering:
        output.line("  Official products that cover it: none.")
    else:
        output.line("  Official products that cover it:")
        for product in covering:
            output.line(f"    - {_official_text(product, zone)}")
    if context:
        output.line("  County-zone alerts outside its zones (context; they set no level):")
        for product in context:
            output.line(f"    - {_official_text(product, zone)}")


def _print_history(output: Output, entry: StatusLocationEntry, zone: ZoneInfo | None) -> None:
    """Print the changes since the previous assessment, the span, and the toggle."""
    earlier = " (stored by an earlier run over this snapshot)" if entry.stored_before else ""
    if entry.changes:
        output.line(f"  Changes since the previous assessment{earlier}:")
        for change in entry.changes:
            output.line(f"    - {change.detail}")
    else:
        output.line(f"  Changes since the previous assessment{earlier}: none.")
    output.line(f"  Breakpoint span: {span_text(entry.breakpoint_span)}")
    toggle = entry.evacuation_order
    since = f" since {_at(toggle.set_at, zone)}" if toggle.set_at else ""
    if toggle.on:
        held = f"level {int(HELD_AT)} ({HELD_AT.label})"
        output.line(
            f"  Evacuation-order toggle: on{since}; it holds the location at {held} or above."
        )
    else:
        output.line(f"  Evacuation-order toggle: off{since}.")


def _print_location(output: Output, entry: StatusLocationEntry) -> None:
    zone = named_zone(entry.time_zone)
    output.line()
    _print_level(output, entry)
    if entry.evidence:
        output.line("  Evidence:")
        for item in entry.evidence:
            output.line(f"    - {item.detail}")
            output.line(f"      {_evidence_facts(item, zone)}")
    else:
        output.line("  Evidence: none; no rule matched.")
    _print_official(output, entry, zone)
    if entry.wind_probabilities:
        output.line("  Wind-speed probabilities here:")
        for reading in entry.wind_probabilities:
            output.line(f"    - {_wind_text(reading)}")
    else:
        output.line("  Wind-speed probabilities here: the snapshot holds no product.")
    if not entry.threats:
        output.line("  Storms: none is active.")
    for threat in entry.threats:
        _print_threat(output, threat, zone)
    _print_history(output, entry, zone)


def _check_choice(output: Output, locations: Sequence[Location], name: str | None) -> None:
    if not locations:
        fail(output, f"no location is stored; {ADD_HINT}", EXIT_USAGE)
    if name is not None and all(location.name != name for location in locations):
        fail(output, f"no location is named {name!r}", EXIT_USAGE)


def status(
    ctx: typer.Context,
    *,
    location: Annotated[
        str | None,
        typer.Option("--location", help="Print this location only; every one is assessed."),
    ] = None,
    json_output: JsonOption = False,
    no_fetch: NoFetchOption = False,
) -> None:
    """Assess and store every location, and print each level, its evidence, and each storm."""
    context = context_of(ctx)
    output = Output(context.runtime, json_mode=json_output)
    with open_session(context, output) as database:
        locations = LocationService(database.engine).list()
        _check_choice(output, locations, location)
        snapshot, cycle = run_cycle(
            context, output, database, runner="status", no_fetch=no_fetch, assess=True
        )
        heartbeats = HeartbeatRepository(database.engine).rows()
    now = context.runtime.now()
    info = snapshot_info(snapshot, now)
    shown = [result for result in cycle.assessed if location in (None, result.location.name)]
    data = StatusData(
        locations=tuple(_entry(result) for result in shown),
        staleness=staleness_entries(staleness(heartbeats, now)),
    )
    code = exit_code(snapshot)
    if json_output:
        output.document(
            StatusDocument(generated_at=now, disclaimer=NOTICE, snapshot=info, data=data)
        )
        raise typer.Exit(code)
    print_header(output, info, stored=no_fetch)
    for line in stale_lines(data.staleness):
        output.line(line, style="yellow")
    for entry in data.locations:
        _print_location(output, entry)
    output.notice()
    raise typer.Exit(code)
