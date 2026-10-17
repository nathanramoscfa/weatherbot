# src/weatherbot/cli/locations.py
"""``weatherbot locations add|list|remove``: the places Weatherbot watches.

``add`` sends the point to ``api.weather.gov`` and, once, to Nominatim; ``list`` is the
only command that prints a location's coordinates, and ``list --json`` the only document
that holds them.
"""

import asyncio
from typing import Annotated, Literal

import typer

from weatherbot.cli.documents import LocationEntry, LocationsData, LocationsDocument
from weatherbot.cli.runtime import EXIT_USAGE, Output, context_of, fail, open_session
from weatherbot.models import Location
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.locations import LocationError, LocationService
from weatherbot.services.network import SourceError

app = typer.Typer(
    name="locations",
    help="Add, list, and remove the locations Weatherbot watches.",
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
    )


def _coverage(location: Location) -> str:
    if location.nws is None:
        return "outside NWS coverage"
    return (
        f"NWS {location.nws.cwa}, zones {location.nws.forecast_zone} and {location.nws.county_zone}"
    )


@app.command("add")
def add(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="A unique name, 1 to 64 printable characters.")],
    lat: Annotated[
        float, typer.Option("--lat", help="Latitude in degrees north.", allow_from_autoenv=False)
    ],
    lon: Annotated[
        float, typer.Option("--lon", help="Longitude in degrees east.", allow_from_autoenv=False)
    ],
    polygon: Annotated[
        Literal["county", "forecast"] | None,
        typer.Option(help="Store the location's NWS county or forecast zone shape (US only)."),
    ] = None,
) -> None:
    """Add a location: its NWS coverage is looked up and it is geocoded once."""
    context = context_of(ctx)
    output = Output(context.runtime)
    with open_session(context, output) as database:
        service = LocationService(database.engine, network=context.network, now=context.runtime.now)
        try:
            location = asyncio.run(service.add(name, lat, lon, polygon))
        except LocationError as error:
            fail(output, str(error), EXIT_USAGE)
        except SourceError as error:
            fail(output, f"the location was not added: {error}")
    place = location.display_name or "no place name (reverse geocoding found none)"
    output.line(f"Added {location.name!r}: {_coverage(location)}; {place}.")


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
            ("Name", "Latitude", "Longitude", "Country", "Coverage", "Place"),
            [
                (
                    location.name,
                    str(location.point.latitude),
                    str(location.point.longitude),
                    location.country_code or "-",
                    _coverage(location),
                    location.display_name or "-",
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
    """Remove a location and the alert history stored for it."""
    context = context_of(ctx)
    output = Output(context.runtime)
    with open_session(context, output) as database:
        try:
            LocationService(database.engine).remove(name)
        except LocationError as error:
            fail(output, str(error), EXIT_USAGE)
    output.line(f"Removed {name!r}.")
