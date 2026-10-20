# src/weatherbot/engine/threats.py
"""One threat per storm: what each storm's own advisory products say about a location.

The advisory's tau-0 point gives the storm's center and category; the repaired cone says
whether it covers the location; the forecast points give the closest approach; and the
arrival-time products give when tropical-storm-force winds arrive, with the closest
approach as the labelled fallback where a storm has no product. A storm without forecast
points or a usable cone gets a threat with those parts unresolved, and the assessment
lists what was missing. No threat holds a wind-speed probability (issue #12).

The distance, bearing, approach, and arrivals locate the location, so nothing here logs
and no message carries them.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Final, cast

from weatherbot.engine.arrivals import (
    NO_CENTER,
    latest_product,
    read_arrival,
    track_fallback,
    unresolved,
)
from weatherbot.engine.cones import ConeReading, TrackReading, read_cones, read_track
from weatherbot.engine.geodesy import Position, distance_km, figure_of, initial_bearing_deg
from weatherbot.engine.geometry import place
from weatherbot.models import (
    WGS84,
    AdvisoryNumber,
    ArrivalReading,
    Location,
    Snapshot,
    SourceOutcome,
    StormProducts,
    StormThreat,
    TrackPoint,
    UnavailableInput,
)
from weatherbot.models.assessment import ArrivalKind

ARRIVAL_SOURCE: Final = "nhc-arrival-times"
KINDS: Final[tuple[ArrivalKind, ...]] = ("earliest_reasonable", "most_likely")
_KIND_WORDS: Final = {"earliest_reasonable": "earliest-reasonable", "most_likely": "most-likely"}


def _tau0(points: Sequence[TrackPoint]) -> TrackPoint:
    return min(points, key=lambda point: (point.valid_at, point.tau_h))


def _xy(point: TrackPoint) -> Position:
    coordinates = cast("Sequence[float]", point.position.coordinates)
    return (coordinates[0], coordinates[1])


def _advisory(storm: StormProducts) -> tuple[AdvisoryNumber | None, datetime | None]:
    """The storm's latest advisory: the roster's public advisory, else its products'."""
    if storm.summary is not None:
        public = storm.summary.public_advisory
        return public.advisory, public.issued_at
    records = (storm.cone, *storm.track_points, storm.track)
    record = next((item for item in records if item is not None), None)
    if record is None:
        return None, None
    return record.advisory.number, record.advisory.issued_at


def _arrival(
    storm: StormProducts,
    kind: ArrivalKind,
    center: Position | None,
    location: Location,
    track: TrackReading | None,
) -> ArrivalReading:
    product = latest_product(storm.arrival_times, kind)
    if product is None:
        return track_fallback(kind, track.approach if track else None, storm.track_points)
    if center is None:
        return unresolved(product, NO_CENTER)
    crs = next((line.geometry.crs for line in product.lines), WGS84)
    return read_arrival(product, center, place(location.point, crs), figure_of(crs))


def _threat(
    storm: StormProducts, location: Location, as_of: datetime, cone: ConeReading | None
) -> StormThreat:
    advisory, issued_at = _advisory(storm)
    measured: dict[str, object] = {}
    center: Position | None = None
    track: TrackReading | None = None
    if storm.track_points:
        first = _tau0(storm.track_points)
        crs = first.position.crs
        figure = figure_of(crs)
        center, here = _xy(first), place(location.point, crs)
        track = read_track(storm, location, as_of)
        ssnum = first.saffir_simpson
        measured = {
            "category": ssnum if ssnum is not None and ssnum >= 1 else None,
            "development": first.development,
            "crs": crs.label,
            "distance_km": distance_km(center, here, figure),
            "bearing_deg": initial_bearing_deg(center, here, figure),
            "closest_approach_at": track.approach.instant,
            "closest_approach_km": track.approach.distance_km,
            "lead_h": track.lead_h,
            "hurricane_by_approach": track.hurricane,
        }
    earliest, most_likely = (_arrival(storm, kind, center, location, track) for kind in KINDS)
    return StormThreat.model_validate(
        {
            "atcf_id": storm.atcf_id,
            "storm_name": storm.name,
            "advisory": advisory,
            "issued_at": issued_at,
            "in_cone": cone.covers if cone is not None else None,
            "earliest_arrival": earliest,
            "most_likely_arrival": most_likely,
            **measured,
        }
    )


def storm_threats(
    storms: Sequence[StormProducts],
    location: Location,
    as_of: datetime,
    cones: Sequence[ConeReading],
) -> tuple[StormThreat, ...]:
    """Build one threat per storm from cone readings already made.

    Args:
        storms: The snapshot's storms.
        location: The location.
        as_of: The snapshot's instant.
        cones: ``read_cones``' readings of the same storms.

    Returns:
        The threats, in the storms' order.
    """
    by_storm = {reading.storm.atcf_id: reading for reading in cones}
    return tuple(_threat(storm, location, as_of, by_storm.get(storm.atcf_id)) for storm in storms)


def threats_for(snapshot: Snapshot, location: Location, as_of: datetime) -> tuple[StormThreat, ...]:
    """Say what each storm of a snapshot means for a location.

    Args:
        snapshot: The snapshot.
        location: The location.
        as_of: The snapshot's instant, from which each approach's lead is counted.

    Returns:
        One threat per storm, in the snapshot's order.
    """
    cones, _ = read_cones(snapshot.storms, location, as_of, cones_failed=False)
    return storm_threats(snapshot.storms, location, as_of, cones)


def _arrival_outcome(snapshot: Snapshot) -> str:
    outcome: SourceOutcome | None = next(
        (item for item in snapshot.source_outcomes if item.source_id == ARRIVAL_SOURCE), None
    )
    if outcome is None:
        return f"{ARRIVAL_SOURCE} was not asked"
    if outcome.status == "failed":
        return f"{ARRIVAL_SOURCE} failed ({outcome.error_kind})"
    if outcome.status == "skipped":
        return str(outcome.reason)
    return "none was fetched for it"


def missing_inputs(
    snapshot: Snapshot, threats: Sequence[StormThreat], *, points_failed: bool
) -> tuple[UnavailableInput, ...]:
    """Name what each threat lacked: forecast points, and each missing arrival product.

    Args:
        snapshot: The snapshot the threats were built from.
        threats: Its threats, in the storms' order.
        points_failed: Whether the source that carries the forecast points failed; its
            failure is already an unavailable input, so a storm without points is not
            listed again.

    Returns:
        The unavailable inputs, storm by storm.
    """
    missing: list[UnavailableInput] = []
    why = _arrival_outcome(snapshot)
    for storm, threat in zip(snapshot.storms, threats, strict=True):
        name = storm.name
        if not storm.track_points and not points_failed:
            missing.append(
                UnavailableInput(
                    kind="forecast_points",
                    atcf_id=storm.atcf_id,
                    storm_name=name,
                    reason=(
                        f"the snapshot holds no forecast points for {name}, so its center, "
                        "closest approach, and intensity were not read"
                    ),
                )
            )
        missing.extend(
            UnavailableInput(
                kind="arrival_times",
                source_id=ARRIVAL_SOURCE,
                atcf_id=storm.atcf_id,
                storm_name=name,
                reason=(
                    f"the snapshot holds no {_KIND_WORDS[reading.kind]} arrival-time product "
                    f"for {name} ({why}), so that arrival "
                    + (
                        "reads the forecast track's closest approach"
                        if reading.reading == "track"
                        else "is unresolved"
                    )
                ),
            )
            for reading in (threat.earliest_arrival, threat.most_likely_arrival)
            if reading.origin == "track"
        )
    return tuple(missing)
