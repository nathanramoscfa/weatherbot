# src/weatherbot/engine/probabilities.py
"""The location's band of each wind-speed-probability product the snapshot holds.

The products belong to the snapshot, never to a storm (issue #12). A product's bands are
disjoint, so the location sits in at most one; a point on a shared boundary takes the
higher band. An extract, such as a replay landmark window, says nothing outside its
coverage: there the reading is ``outside_coverage`` and an unavailable input.

A live product exists for each threshold at which NHC drew any band, so a live snapshot
whose map source answered and holds no product at a threshold has no band anywhere. A
replay snapshot without the product is missing it: the corpus holds none for that
advisory.
"""

from dataclasses import dataclass
from typing import Final, Literal

from weatherbot.engine.geometry import covers, place, repair
from weatherbot.models import (
    Citation,
    Location,
    LocationWindProbability,
    Snapshot,
    UnavailableInput,
    WindProbabilityBand,
    WindProbabilityProduct,
)

RULE_THRESHOLDS: Final[tuple[Literal[34, 64], ...]] = (34, 64)
"""The thresholds the ladder's rules read: tropical-storm and hurricane force."""


@dataclass(frozen=True, slots=True)
class ProbabilityReading:
    """One product read at the location, and the band that covers it, if any."""

    product: WindProbabilityProduct
    reading: LocationWindProbability
    band: WindProbabilityBand | None


def _band_at(
    product: WindProbabilityProduct, location: Location
) -> tuple[WindProbabilityBand | None, list[str]]:
    """The highest band that covers the location, and the notes of bands left unusable."""
    unusable: list[str] = []
    for band in sorted(product.bands, key=lambda item: item.lower_pct, reverse=True):
        repaired = repair(band.geometry)
        if repaired.shape is None:
            unusable.append(f"the {band.label} band is unusable: {repaired.note}")
            continue
        if covers(repaired.shape, place(location.point, repaired.shape.crs)):
            return band, unusable
    return None, unusable


def _location_reading(
    product: WindProbabilityProduct,
    reading: Literal["band", "below_every_band", "outside_coverage"],
    crs: str | None,
    band: WindProbabilityBand | None = None,
) -> LocationWindProbability:
    return LocationWindProbability(
        threshold_kt=product.threshold_kt,
        synoptic_at=product.synoptic_at,
        reading=reading,
        label=band.label if band else None,
        lower_pct=band.lower_pct if band else None,
        upper_pct=band.upper_pct if band else None,
        crs=crs,
        citation=Citation.of(product.provenance),
    )


def _unavailable(product: WindProbabilityProduct, reason: str) -> UnavailableInput:
    return UnavailableInput(
        kind="wind_probabilities",
        source_id=product.provenance.source_id,
        threshold_kt=product.threshold_kt,
        reason=reason,
    )


def _read(
    product: WindProbabilityProduct, location: Location
) -> tuple[ProbabilityReading, list[UnavailableInput]]:
    coverage = product.coverage
    if coverage is not None and not covers(coverage, place(location.point, coverage.crs)):
        reading = _location_reading(product, "outside_coverage", coverage.crs.label)
        reason = (
            f"the {product.threshold_kt}-kt product is an extract that does not cover this location"
        )
        return ProbabilityReading(product, reading, None), [_unavailable(product, reason)]
    band, unusable = _band_at(product, location)
    shapes = [coverage] if coverage is not None else [item.geometry for item in product.bands]
    crs = shapes[0].crs.label if shapes else None
    if band is None:
        reading = _location_reading(product, "below_every_band", crs)
    else:
        reading = _location_reading(product, "band", crs, band)
    missing = [_unavailable(product, note) for note in unusable]
    return ProbabilityReading(product, reading, band), missing


def read_probabilities(
    snapshot: Snapshot, location: Location
) -> tuple[tuple[ProbabilityReading, ...], tuple[UnavailableInput, ...]]:
    """Read every wind-speed-probability product of a snapshot at a location.

    Args:
        snapshot: The snapshot; only its own products are read.
        location: The location.

    Returns:
        One reading per product, in threshold order, and the inputs that were
        unavailable: an extract that does not cover the location, a band left with no
        area by repair, and, in a replay snapshot with a storm, a threshold the rules
        read for which the corpus holds no product.
    """
    readings: list[ProbabilityReading] = []
    unavailable: list[UnavailableInput] = []
    products = sorted(snapshot.wind_probabilities, key=lambda item: item.threshold_kt)
    for product in products:
        reading, missing = _read(product, location)
        readings.append(reading)
        unavailable.extend(missing)
    if snapshot.origin == "replay" and snapshot.storms:
        held = {product.threshold_kt for product in products}
        unavailable.extend(
            UnavailableInput(
                kind="wind_probabilities",
                source_id="nhc-gis-archive",
                threshold_kt=threshold,
                reason=(
                    f"the corpus holds no {threshold}-kt wind-speed probability product "
                    "for this advisory"
                ),
            )
            for threshold in RULE_THRESHOLDS
            if threshold not in held
        )
    return tuple(readings), tuple(unavailable)
