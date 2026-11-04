# src/weatherbot/cli/locations.py
"""``weatherbot locations add|list|remove|evacuation``: the places Weatherbot watches.

``add`` sends the point to ``api.weather.gov`` and, once, to Nominatim; ``list`` is the
only command that prints a location's coordinates, and ``list --json`` the only document
that holds them. ``list`` also shows each location's evacuation-order toggle and its
breakpoint span. ``evacuation NAME on|off`` sets the toggle, which holds the location at
level 4 or above until it is turned off.
"""

import asyncio
from typing import Annotated, Final, Literal

import typer

from weatherbot.cli.documents import LocationEntry, LocationsData, LocationsDocument
from weatherbot.cli.runtime import EXIT_USAGE, Output, context_of, fail, open_session
from weatherbot.cli.snapshots import location_zone, when
from weatherbot.models import AlertLevel, BreakpointSpan, Location
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.locations import (
    NOMINATIM_SEARCH_ATTRIBUTION,
    LocationBusyError,
    LocationError,
    LocationService,
)
from weatherbot.services.network import SourceError

app = typer.Typer(
    name="locations",
    help="Add, list, and remove the locations Weatherbot watches, and set their "
    "evacuation-order toggle.",
    no_args_is_help=True,
)

JsonOption = Annotated[bool, typer.Option("--json", help="Print one JSON document.")]


def _entry(location: Location) -> LocationEntry:
    return LocationEntry(
        name=location.name,
        latitude=location.point.latitude,
        longitude=location.point.longitude,
        country_code=location.country_code,
        display_name=location.display_name,
        nws=location.nws,
        has_polygon=location.polygon is not None,
        evacuation_order_in_effect=location.evacuation_order_in_effect,
        evacuation_order_set_at=location.evacuation_order_set_at,
        breakpoint_span=location.breakpoint_span,
    )


def span_text(span: BreakpointSpan | None) -> str:
    """Name a breakpoint span for a terminal.

    Args:
        span: The span, or ``None``.

    Returns:
        ``Ocean Reef to Miami-Dade/Broward County Line (United States)``, the region, or
        ``-`` when there is none yet.
    """
    if span is None:
        return "-"
    names = " to ".join(span.names)
    return names if span.is_region else f"{names} ({span.country})"


def toggle_text(location: Location) -> str:
    """Describe a location's evacuation-order toggle for a terminal, with its instant.

    Args:
        location: The location.

    Returns:
        ``on since …``, ``off since …``, or ``off`` when it was never set.
    """
    state = "on" if location.evacuation_order_in_effect else "off"
    at = location.evacuation_order_set_at
    return f"{state} since {when(at, location_zone(location))}" if at is not None else state


def _coverage(location: Location) -> str:
    if location.nws is None:
        return "outside NWS coverage"
    if location.nws.county_zone is None:
        return f"NWS {location.nws.cwa}, zone {location.nws.forecast_zone}"
    return (
        f"NWS {location.nws.cwa}, zones {location.nws.forecast_zone} and {location.nws.county_zone}"
    )


def _resolve_place_point(
    service: LocationService,
    output: Output,
    place: str,
    pick: int | None,
) -> tuple[float, float]:
    try:
        candidates = asyncio.run(service.search(place))
    except LocationError as error:
        fail(output, str(error), EXIT_USAGE)
    except SourceError as error:
        fail(output, f"the location was not added: {error}")
    if not candidates:
        fail(output, f"no place matched that search ({NOMINATIM_SEARCH_ATTRIBUTION})")
    if len(candidates) == 1:
        if pick is not None and pick != 1:
            fail(output, "--pick must be 1 when 1 candidate matched", EXIT_USAGE)
        chosen = candidates[0]
        return chosen.latitude, chosen.longitude
    if pick is None:
        for index, candidate in enumerate(candidates, start=1):
            output.line(f"  {index}. {candidate.display_name}")
        output.line(NOMINATIM_SEARCH_ATTRIBUTION)
        fail(
            output,
            f"choose a candidate with --pick 1..{len(candidates)}",
            EXIT_USAGE,
        )
    if pick < 1 or pick > len(candidates):
        fail(
            output,
            f"--pick must be between 1 and {len(candidates)}",
            EXIT_USAGE,
        )
    chosen = candidates[pick - 1]
    return chosen.latitude, chosen.longitude


@app.command("add")
def add(  # noqa: PLR0913, PLR0917 - CLI command options for coordinate or place addition
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="A unique name, 1 to 64 printable characters.")],
    lat: Annotated[
        float | None,
        typer.Option("--lat", help="Latitude in degrees north.", allow_from_autoenv=False),
    ] = None,
    lon: Annotated[
        float | None,
        typer.Option("--lon", help="Longitude in degrees east.", allow_from_autoenv=False),
    ] = None,
    place: Annotated[
        str | None,
        typer.Option(
            "--place",
            help="Forward-geocode a place name through Nominatim instead of coordinates.",
            allow_from_autoenv=False,
        ),
    ] = None,
    pick: Annotated[
        int | None,
        typer.Option(
            "--pick",
            help="1-based candidate index when --place returns several.",
            allow_from_autoenv=False,
        ),
    ] = None,
    polygon: Annotated[
        Literal["county", "forecast"] | None,
        typer.Option(help="Store the location's NWS county or forecast zone shape (US only)."),
    ] = None,
) -> None:
    """Add a location: its NWS coverage is looked up and it is geocoded once."""
    context = context_of(ctx)
    output = Output(context.runtime)
    if place is not None and (lat is not None or lon is not None):
        fail(output, "pass either --lat and --lon or --place, not both", EXIT_USAGE)
    if place is None and (lat is None or lon is None):
        fail(output, "pass both --lat and --lon, or --place TEXT", EXIT_USAGE)
    if place is None and pick is not None:
        fail(output, "--pick is only used with --place", EXIT_USAGE)
    with open_session(context, output) as database:
        service = LocationService(
            database.engine,
            network=context.network,
            now=context.runtime.now,
            paths=context.paths,
            cycle_lock_wait_seconds=context.settings.monitor.cycle_lock_wait_seconds,
        )
        if place is not None:
            resolved_lat, resolved_lon = _resolve_place_point(service, output, place, pick)
        elif lat is None or lon is None:  # pragma: no cover - guarded above
            fail(output, "pass both --lat and --lon, or --place TEXT", EXIT_USAGE)
        else:
            resolved_lat, resolved_lon = lat, lon
        try:
            location = asyncio.run(service.add(name, resolved_lat, resolved_lon, polygon))
        except LocationError as error:
            fail(output, str(error), EXIT_USAGE)
        except SourceError as error:
            fail(output, f"the location was not added: {error}")
    place_label = location.display_name or "no place name (reverse geocoding found none)"
    output.line(f"Added {location.name!r}: {_coverage(location)}; {place_label}.")
    if place is not None:
        output.line(NOMINATIM_SEARCH_ATTRIBUTION)


@app.command("list")
def list_locations(ctx: typer.Context, *, json_output: JsonOption = False) -> None:
    """List the stored locations, with their coordinates."""
    context = context_of(ctx)
    output = Output(context.runtime, json_mode=json_output)
    with open_session(context, output) as database:
        locations = LocationService(database.engine).list()
    if json_output:
        output.document(
            LocationsDocument(
                generated_at=context.runtime.now(),
                disclaimer=NOTICE,
                data=LocationsData(locations=tuple(_entry(location) for location in locations)),
            )
        )
        return
    if not locations:
        output.line("No locations. Add one with: weatherbot locations add NAME --lat LAT --lon LON")
    else:
        output.table(
            "Locations",
            (
                "Name",
                "Latitude",
                "Longitude",
                "Country",
                "Coverage",
                "Place",
                "Breakpoint span",
                "Evacuation-order toggle",
            ),
            [
                (
                    location.name,
                    str(location.point.latitude),
                    str(location.point.longitude),
                    location.country_code or "-",
                    _coverage(location),
                    location.display_name or "-",
                    span_text(location.breakpoint_span),
                    toggle_text(location),
                )
                for location in locations
            ],
        )
    output.notice()


@app.command("remove")
def remove(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The location's name.")],
) -> None:
    """Remove a location, and the alert and assessment history stored for it."""
    context = context_of(ctx)
    output = Output(context.runtime)
    with open_session(context, output) as database:
        try:
            LocationService(
                database.engine,
                paths=context.paths,
                cycle_lock_wait_seconds=context.settings.monitor.cycle_lock_wait_seconds,
            ).remove(name)
        except LocationBusyError as error:
            fail(output, str(error))
        except LocationError as error:
            fail(output, str(error), EXIT_USAGE)
    output.line(f"Removed {name!r}.")


HOLDS: Final = AlertLevel.WARNING_WATCH_EVACUATION


@app.command("evacuation")
def evacuation(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The location's name.")],
    state: Annotated[
        Literal["on", "off"],
        typer.Argument(help="on while an official evacuation order is in effect; off after."),
    ],
) -> None:
    """Turn a location's evacuation-order toggle on or off; on holds it at level 4 or above."""
    context = context_of(ctx)
    output = Output(context.runtime)
    on = state == "on"
    with open_session(context, output) as database:
        service = LocationService(database.engine, now=context.runtime.now)
        try:
            location, changed = service.set_evacuation_order(name, on=on)
        except LocationError as error:
            fail(output, str(error), EXIT_USAGE)
    already = "" if changed else "already "
    output.line(
        f"The evacuation-order toggle of {location.name!r} is {already}{toggle_text(location)}."
    )
    level = f"level {int(HOLDS)} ({HOLDS.label})"
    if on:
        output.line(
            f"It holds {location.name!r} at {level} or above until you turn it off: "
            f"weatherbot locations evacuation {location.name!r} off"
        )
    else:
        output.line(f"{location.name!r} is no longer held at {level}: its level is the products'.")
    if changed:
        output.line("The next weatherbot status, which fetches a snapshot, assesses with it.")
    output.notice()
