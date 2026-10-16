# src/weatherbot/models/arrivals.py
"""Arrival times of tropical-storm-force winds (issue #11)."""

from datetime import datetime
from typing import Final, Literal, Self

from pydantic import Field, model_validator

from weatherbot.models.base import DomainModel
from weatherbot.models.geometry import Geometry, require_geometry
from weatherbot.models.storms import AdvisoryRecord
from weatherbot.models.times import UtcDatetime, parse_nhc_local_time, resolve_arrival_label

MAP_LAYER_REASON: Final = "the map layer carries no date or time zone"
NO_PUBLICATION_REASON: Final = "the product states no publication time"

type Origin = Literal["kmz", "map_layer"]


def expected_time(
    label: str,
    *,
    origin: Origin,
    published_at: datetime | None,
    time_zone: str | None,
    withheld_reason: str | None = None,
) -> tuple[datetime | None, str | None]:
    """Return the instant and the unresolved reason a labelled line must carry.

    Args:
        label: The line's label.
        origin: The product's origin.
        published_at: The product's publication.
        time_zone: The product's zone abbreviation.
        withheld_reason: Why a ``kmz`` product resolves no line, when it does not.

    Returns:
        ``(valid_at, unresolved_reason)``: exactly one of them is ``None``.
    """
    if origin == "map_layer":
        return (None, MAP_LAYER_REASON)
    if withheld_reason is not None:
        return (None, withheld_reason)
    if published_at is None:
        return (None, NO_PUBLICATION_REASON)
    resolution = resolve_arrival_label(label, published_at, time_zone)
    return (resolution.valid_at, resolution.reason)


class ArrivalTimeLine(DomainModel):
    """One arrival-time contour.

    The outer contour (the "Wind Speed Probability 5% contour") has no label and no time.
    A labelled line has an instant, or the reason it has none.
    """

    label: str | None = Field(description="Such as Tue 8 am, as received.")
    is_outer_contour: bool
    valid_at: UtcDatetime | None
    unresolved_reason: str | None
    geometry: Geometry

    @classmethod
    def resolve(  # noqa: PLR0913 - a line plus its product's four timing inputs, keyword-only
        cls,
        label: str | None,
        geometry: Geometry,
        *,
        origin: Origin,
        published_at: datetime | None = None,
        time_zone: str | None = None,
        withheld_reason: str | None = None,
    ) -> Self:
        """Build a line the way its product's origin requires.

        A blank label (the layers write one space) marks the outer contour. A ``kmz`` line
        is resolved by ``resolve_arrival_label``; a ``map_layer`` line keeps its label only.

        Args:
            label: The label as received, or ``None``.
            geometry: The line.
            origin: The product's origin.
            published_at: The product's publication, for a ``kmz`` line.
            time_zone: The product's zone abbreviation, for a ``kmz`` line.
            withheld_reason: The product's ``withheld_reason``, when it has one.

        Returns:
            The line.
        """
        text = label if label and label.strip() else None
        valid_at, reason = (
            expected_time(
                text,
                origin=origin,
                published_at=published_at,
                time_zone=time_zone,
                withheld_reason=withheld_reason,
            )
            if text is not None
            else (None, None)
        )
        return cls(
            label=text,
            is_outer_contour=text is None,
            valid_at=valid_at,
            unresolved_reason=reason,
            geometry=geometry,
        )

    @model_validator(mode="after")
    def _instant_or_reason(self) -> Self:
        require_geometry(self.geometry, ("LineString", "MultiLineString"), "an arrival line")
        if self.is_outer_contour != (self.label is None):
            message = "only the outer contour, and every outer contour, has no label"
            raise ValueError(message)
        if self.label is None and (self.valid_at or self.unresolved_reason):
            message = "the outer contour has no time"
            raise ValueError(message)
        if self.label is not None and (self.valid_at is None) == (self.unresolved_reason is None):
            message = "a labelled line has an instant or an unresolved reason, not both"
            raise ValueError(message)
        return self


class ArrivalTimeProduct(AdvisoryRecord):
    """The earliest-reasonable or most-likely arrival times of one full advisory.

    Issue #11 chose option (b): times come from the arrival-time KMZ the roster links,
    whose ``ExtendedData`` states ``timezone``, ``advisoryNum``, and ``pubAdvTime``. The
    map layers label each line only with a weekday and a clock time, with no date and no
    zone, and the slot's ``advdate`` is the wrong anchor: the recorded capture held a slot
    whose cone was an intermediate advisory while its arrival lines belonged to the
    preceding full advisory, three hours earlier, because arrival products come only with
    full advisories (``docs/roadmap/phase02-roadmap.md``, Overview, "Design rationale",
    and the recorded fixtures under ``tests/fixtures/recorded/``). A ``kmz`` product resolves
    every labelled line through ``resolve_arrival_label``, unless ``withheld_reason`` says
    why it resolves none (the KMZ disagrees with the roster); a ``map_layer`` product is
    the label-only fallback for display (option c) and never carries a zone or an instant.
    """

    kind: Literal["earliest_reasonable", "most_likely"]
    time_zone: str | None = Field(description="The KMZ's timezone abbreviation.")
    published_at: UtcDatetime | None = Field(description="From pubAdvTime.")
    published_local_text: str | None = Field(description="pubAdvTime, as received.")
    origin: Origin
    lines: tuple[ArrivalTimeLine, ...]
    withheld_reason: str | None = Field(
        default=None, description="Why a kmz product resolves no line, when it resolves none."
    )

    @model_validator(mode="after")
    def _resolved_by_the_rule(self) -> Self:
        if self.advisory.number.is_intermediate:
            message = "arrival-time products come only with full advisories"
            raise ValueError(message)
        if self.origin == "map_layer" and (
            self.time_zone or self.published_at or self.published_local_text or self.withheld_reason
        ):
            message = "a map-layer arrival product carries no zone or publication time"
            raise ValueError(message)
        text = self.published_local_text
        if (parse_nhc_local_time(text) if text else None) != self.published_at:
            message = "published_at must be the instant published_local_text names"
            raise ValueError(message)
        for line in self.lines:
            if line.label is not None and (line.valid_at, line.unresolved_reason) != expected_time(
                line.label,
                origin=self.origin,
                published_at=self.published_at,
                time_zone=self.time_zone,
                withheld_reason=self.withheld_reason,
            ):
                message = "every labelled line must be resolved by resolve_arrival_label"
                raise ValueError(message)
        return self
