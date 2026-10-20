# src/weatherbot/engine/cones.py
"""Each storm's cone at a location: usable or not, covering or not, and how close it comes.

A cone is repaired before it is tested, and a cone with no area left is an unavailable
input. For a covering cone the forecast points give the closest approach, the lead from
the snapshot's instant (an approach already past counts as now), and whether a forecast
point at or before that approach is a hurricane.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from weatherbot.engine.geodesy import figure_of
from weatherbot.engine.geometry import Approach, closest_approach, covers, place, repair
from weatherbot.models import ConeGeometry, Location, StormProducts, UnavailableInput

HURRICANE_WIND_KT: Final = 64
"""The sustained wind, in knots, at which a storm is a hurricane."""

_SECONDS_PER_HOUR: Final = 3600.0


@dataclass(frozen=True, slots=True)
class ConeReading:
    """One storm's usable cone, tested at a location.

    ``approach``, ``lead_h``, and ``hurricane`` are measured only for a covering cone
    whose storm has forecast points; ``lead_h`` counts from the snapshot's instant.
    """

    storm: StormProducts
    cone: ConeGeometry
    note: str | None
    covers: bool
    approach: Approach | None
    lead_h: float | None
    hurricane: bool


def _measure(
    storm: StormProducts, location: Location, as_of: datetime
) -> tuple[Approach, float, bool]:
    points = storm.track_points
    crs = points[0].position.crs
    approach = closest_approach(points, place(location.point, crs), figure_of(crs))
    lead_h = max(0.0, (approach.instant - as_of).total_seconds() / _SECONDS_PER_HOUR)
    hurricane = any(
        point.max_wind_kt is not None
        and point.max_wind_kt >= HURRICANE_WIND_KT
        and point.valid_at <= approach.instant
        for point in points
    )
    return approach, lead_h, hurricane


def read_cones(
    storms: Sequence[StormProducts],
    location: Location,
    as_of: datetime,
    *,
    cones_failed: bool,
) -> tuple[tuple[ConeReading, ...], tuple[UnavailableInput, ...]]:
    """Read every storm's cone at a location.

    Args:
        storms: The snapshot's storms.
        location: The location.
        as_of: The snapshot's instant.
        cones_failed: Whether the source that carries the cones failed; its failure is
            already an unavailable input, so a storm without a cone is not listed again.

    Returns:
        The readings of the usable cones, and the inputs that were unavailable.
    """
    readings: list[ConeReading] = []
    unavailable: list[UnavailableInput] = []
    for storm in storms:
        cone = storm.cone
        if cone is None:
            if not cones_failed:
                unavailable.append(
                    UnavailableInput(
                        kind="cone",
                        atcf_id=storm.atcf_id,
                        storm_name=storm.name,
                        reason=f"the snapshot holds no cone for {storm.name}",
                    )
                )
            continue
        repaired = repair(cone.geometry)
        if repaired.shape is None:
            unavailable.append(
                UnavailableInput(
                    kind="cone",
                    atcf_id=storm.atcf_id,
                    storm_name=storm.name,
                    reason=f"the cone of {storm.name} is unusable: {repaired.note}",
                )
            )
            continue
        inside = covers(repaired.shape, place(location.point, repaired.shape.crs))
        approach, lead_h, hurricane = None, None, False
        if inside and storm.track_points:
            approach, lead_h, hurricane = _measure(storm, location, as_of)
        elif inside:
            unavailable.append(
                UnavailableInput(
                    kind="forecast_points",
                    atcf_id=storm.atcf_id,
                    storm_name=storm.name,
                    reason=(
                        f"the snapshot holds no forecast points for {storm.name}, so its "
                        "closest approach and intensity were not read"
                    ),
                )
            )
        readings.append(
            ConeReading(
                storm=storm,
                cone=cone,
                note=repaired.note,
                covers=inside,
                approach=approach,
                lead_h=lead_h,
                hurricane=hurricane,
            )
        )
    return tuple(readings), tuple(unavailable)
