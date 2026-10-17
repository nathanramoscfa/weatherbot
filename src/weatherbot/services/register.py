# src/weatherbot/services/register.py
"""The register's map-service layers and source roles, for ``doctor``'s discovery.

``docs/DATA_SOURCES.md`` is not in the wheel, so the layer names ``doctor`` resolves live
here, exactly as each service's register table lists them, with ``{slot}`` for every
storm slot and ``{n}`` for each surge-risk category of its region; a contract test keeps
them equal to the register.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from weatherbot.models import SourceId

SLOTS: Final = tuple(f"{basin}{number}" for basin in ("AT", "EP", "CP") for number in range(1, 6))

_STORM_PRODUCTS: Final = (
    "Forecast Information",
    "Forecast Points",
    "Forecast Track",
    "Forecast Cone",
    "Watch-Warning",
    "Past Track Infomation",  # NOAA's spelling
    "Past Points",
    "Past Track",
    "Past Cumulative Wind Swath",
    "Past Wind Radii",
    "Wind Information",
    "Forecast Wind Radii",
    "Advisory Wind Field",
    "Arrival Time of TS Winds",
    "Earliest Reasonable Arrival Time",
    "Most Likely Arrival Time",
    "Inundation and Tidal Mask",
    "Inundation",
)
_OUTLOOK: Final = (
    "Graphical Tropical Weather Outlook",
    "Two-Day: Current Location",
    "Seven-Day Outlook",
    "Seven-Day: Current Location",
    "Seven-Day: Development Motion",
    "Seven-Day: Potential Development Region",
)
_PROBABILISTIC_WINDS: Final = (
    "Probabilistic Winds",
    "Probabilistic Winds 34 kts",
    "Probabilistic Winds 50 kts",
    "Probabilistic Winds 64 kts",
)
_MASKS: Final = ("Boundary_{}", "Footprint_{}", "Image_{}")
_PARTS: Final = ("Boundary", "Footprint", "Image")


def _slot_layers() -> tuple[str, ...]:
    masks = [mask.format("Inun_{slot}") for mask in _MASKS]
    tidal = [mask.format("TMask_{slot}") for mask in _MASKS]
    return (
        *_OUTLOOK,
        "{slot}",
        *(f"{{slot}} {name}" for name in _STORM_PRODUCTS),
        *masks,
        "{slot} Tidal Mask",
        *tidal,
        *_PROBABILISTIC_WINDS,
    )


def _summary_layers() -> tuple[str, ...]:
    return (
        *_OUTLOOK,
        *_STORM_PRODUCTS,
        *(mask.format("Inun") for mask in _MASKS),
        "Tidal Mask",
        *(mask.format("TMask") for mask in _MASKS),
        *_PROBABILISTIC_WINDS,
    )


SURGE_RISK_REGIONS: Final[Mapping[str, range]] = MappingProxyType(
    {
        "Atlantic / US East and Gulf Coast": range(1, 6),
        "Atlantic / Puerto Rico and USVI": range(1, 6),
        "Atlantic / Hispanola": range(1, 6),  # NOAA's spelling
        "Atlantic / Yucatan": range(1, 6),
        "Pacific / Hawaii (category 1-4)": range(1, 5),
        "Pacific / Southern California (category 1-2)": range(1, 3),
        "Pacific / Guam": range(1, 6),
        "Pacific / American Samoa": range(1, 6),
    }
)
"""Each surge-risk region and the categories its group holds (the register's notes)."""


def _surge_risk_layers() -> tuple[str, ...]:
    names: list[str] = []
    for ocean in ("Atlantic", "Pacific"):
        names.append(ocean)
        for region in (r for r in SURGE_RISK_REGIONS if r.startswith(f"{ocean} / ")):
            category = f"{region} / Category {{n}}"
            names.extend((region, category, *(f"{category} / {part}" for part in _PARTS)))
    return tuple(names)


MAP_LAYERS: Final[Mapping[SourceId, tuple[str, ...]]] = MappingProxyType(
    {
        "nhc-map-tropical-weather": _slot_layers(),
        "nhc-map-tropical-summary": _summary_layers(),
        "nhc-map-breakpoints": ("Watch_Warning_Breakpoints", "StormSurge_Communication_Points"),
        "nhc-map-peak-surge": ("Points", "Lines", "Polygons"),
        "nhc-map-surge-risk": _surge_risk_layers(),
    }
)
"""Every register layer of each map service, ``{slot}`` and ``{n}`` unexpanded."""


def expand(name: str) -> tuple[str, ...]:
    """Expand a register layer name over the slots, or over its region's categories.

    Args:
        name: A register layer name.

    Returns:
        The names to resolve in a catalog.
    """
    if "{slot}" in name:
        return tuple(name.replace("{slot}", slot) for slot in SLOTS)
    if "{n}" in name:
        region = name.split(" / Category {n}", 1)[0]
        return tuple(name.replace("{n}", str(n)) for n in SURGE_RISK_REGIONS[region])
    return (name,)


NOT_PROBED: Final[Mapping[SourceId, str]] = MappingProxyType(
    {
        "nhc-gis-archive": "replay-only: scripts/fetch_replay_corpus.py reads it, never a run",
        "basemap-osm-tiles": "display-only: the browser loads tiles; the tile policy "
        "forbids bulk requests",
        "geocode-nominatim": "not probed: Nominatim's usage policy allows requests for "
        "real lookups only, one per location at setup",
    }
)
"""The register sources ``doctor`` never requests, and why."""

SHARED_HOST: Final[Mapping[SourceId, str]] = MappingProxyType(
    {
        "nws-points": "nhc-text-products",
        "nws-alerts-point": "nhc-text-products",
        "nws-alerts-zone": "nhc-text-products",
        "nws-zones": "nhc-text-products",
    }
)
"""Sources whose every request names a location, by its point or its zones: ``doctor``
checks their host, ``api.weather.gov``, through the named source's location-free probe."""
