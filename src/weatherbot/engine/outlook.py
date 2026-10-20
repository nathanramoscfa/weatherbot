# src/weatherbot/engine/outlook.py
"""The tropical weather outlook's seven-day development regions at a location.

A live snapshot whose map source answered and holds no region has none to read: the
outlook is quiet. A replay snapshot holds no outlook at all, which is an unavailable
input.
"""

from dataclasses import dataclass

from weatherbot.engine.geometry import covers, place, repair
from weatherbot.models import Location, OutlookArea, Snapshot, UnavailableInput

DEVELOPMENT_REGION = "development_region"


@dataclass(frozen=True, slots=True)
class RegionReading:
    """One seven-day development region, whether it covers the location, and its chance."""

    area: OutlookArea
    covers: bool
    chance_7day_pct: int | None


def read_regions(
    snapshot: Snapshot, location: Location
) -> tuple[tuple[RegionReading, ...], tuple[UnavailableInput, ...]]:
    """Read every seven-day development region of a snapshot at a location.

    Args:
        snapshot: The snapshot.
        location: The location.

    Returns:
        One reading per usable region, and the inputs that were unavailable: the whole
        outlook in a replay snapshot, and a region left with no area by repair.
    """
    if snapshot.origin == "replay":
        missing = UnavailableInput(
            kind="outlook_areas", reason="a replay snapshot holds no tropical weather outlook"
        )
        return (), (missing,)
    readings: list[RegionReading] = []
    unavailable: list[UnavailableInput] = []
    for area in snapshot.outlook_areas:
        if area.kind != DEVELOPMENT_REGION:
            continue
        repaired = repair(area.geometry)
        if repaired.shape is None:
            unavailable.append(
                UnavailableInput(
                    kind="outlook_areas",
                    source_id=area.provenance.source_id,
                    reason=f"the {area.basin} development region is unusable: {repaired.note}",
                )
            )
            continue
        inside = covers(repaired.shape, place(location.point, repaired.shape.crs))
        readings.append(RegionReading(area, inside, area.chance_7day_pct))
    return tuple(readings), tuple(unavailable)
