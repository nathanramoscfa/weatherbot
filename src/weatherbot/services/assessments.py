# src/weatherbot/services/assessments.py
"""The assessment service: every stored location assessed against a live snapshot, stored.

``AssessmentService.assess(snapshot, locations)`` takes, per location, its previous stored
assessment (the latest at or before the snapshot's instant), runs the engine's ``assess``
with the configured thresholds, compares the two with ``diff``, and stores the assessment
with its evidence and changes. When the snapshot's catalogue gives the location a
breakpoint span that the stored location lacks or states differently, the location
keeps the new span. The whole run is one transaction. An assessment already stored for
that snapshot, location, and ruleset is returned as stored, never stored again, so a
rerun over the same snapshot changes nothing, and history is never rewritten. When the
operator set the evacuation-order toggle after that assessment was stored, the result
says so: the stored level did not read the toggle, and the next fetched snapshot will. A
replay snapshot is refused: history is live only.

``official_products(snapshot, location, thresholds)`` says which official products cover
a location without storing anything, for ``weatherbot alerts``; ``is_county_context`` picks
out a county-zone alert outside the location's zones, shown beside the level and never
setting it (issue #10); ``RULE_TRIGGERS`` says each rule's trigger in words.

An assessment's distances, bearings, and instants locate the location as surely as its
coordinates do. Log records here name locations, levels, rules, and counts, never one of
those values.
"""

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Final

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from weatherbot.engine import RULES, assess, diff
from weatherbot.engine.breakpoints import segment_ends
from weatherbot.engine.official import OUTSIDE_ZONES
from weatherbot.models import (
    Breakpoint,
    Geometry,
    Location,
    OfficialProduct,
    RuleId,
    Snapshot,
    Thresholds,
)
from weatherbot.services.persistence.database import writing_session
from weatherbot.services.persistence.repositories import (
    AssessmentRepository,
    LocationRepository,
    StoredAssessment,
)

LOGGER: Final = logging.getLogger("weatherbot.services.assessments")

RULE_TRIGGERS: Final[Mapping[RuleId, str]] = MappingProxyType(
    {rule.id: rule.trigger for rule in RULES}
)
"""Each ladder rule's trigger, in words, as ``docs/ALERT-LADDER.md`` writes it."""


class AssessmentError(Exception):
    """A snapshot cannot be assessed into history as given."""


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class AssessedLocation:
    """One location's assessment of a run: the location as it now stands, and the record.

    ``created`` is false when the assessment was stored before, by an earlier run over the
    same snapshot with the same ruleset; its changes are then the ones stored with it, and
    ``toggle_changed`` says whether the operator set the location's evacuation-order
    toggle after it was stored, so that its level did not read the toggle as it now is.
    """

    location: Location
    stored: StoredAssessment
    created: bool
    toggle_changed: bool = False


def _with_span(location: Location, stored: StoredAssessment) -> Location:
    fields = {name: getattr(location, name) for name in Location.model_fields}
    return Location.model_validate(fields | {"breakpoint_span": stored.assessment.breakpoint_span})


class AssessmentService:
    """Assesses the stored locations against live snapshots, and keeps the history."""

    def __init__(
        self,
        engine: Engine,
        *,
        thresholds: Thresholds,
        now: Callable[[], datetime] = _now,
    ) -> None:
        """Create the service on an open database.

        Args:
            engine: The database.
            thresholds: The configured thresholds (``Settings.engine.thresholds()``).
            now: The clock, for when an assessment is stored.
        """
        self._engine = engine
        self._thresholds = thresholds
        self._ruleset = thresholds.fingerprint(rule.id for rule in RULES)
        self._assessments = AssessmentRepository(engine, now=now)
        self._locations = LocationRepository(engine, now=now)

    @property
    def assessments(self) -> AssessmentRepository:
        """The stored assessments."""
        return self._assessments

    def assess(
        self, snapshot: Snapshot, locations: Sequence[Location]
    ) -> tuple[AssessedLocation, ...]:
        """Assess every location against a stored live snapshot, and store the results.

        Args:
            snapshot: The snapshot, stored already.
            locations: The stored locations, in the order the results come back.

        Returns:
            One result per location.

        Raises:
            AssessmentError: The snapshot is a replay's.
        """
        if snapshot.origin != "live":
            message = "a replay snapshot is never assessed into history: history is live only"
            raise AssessmentError(message)
        with writing_session(self._engine) as session:
            results = [self._assess_one(session, snapshot, location) for location in locations]
        created = sum(result.created for result in results)
        LOGGER.info(
            "assessed %d locations against snapshot %s: %d stored, %d stored before",
            len(results),
            snapshot.snapshot_id,
            created,
            len(results) - created,
        )
        for result in results:
            assessment = result.stored.assessment
            LOGGER.info(
                "location %r: %slevel %d by %s",
                assessment.location_name,
                "" if assessment.complete else "at least ",
                int(assessment.level),
                assessment.rule,
            )
        return tuple(results)

    def _assess_one(
        self, session: Session, snapshot: Snapshot, location: Location
    ) -> AssessedLocation:
        found = self._assessments.find(
            location.name, snapshot.snapshot_id, self._ruleset, session=session
        )
        if found is not None:
            set_at = location.evacuation_order_set_at
            changed = set_at is not None and set_at > found.stored_at
            return AssessedLocation(location, found, created=False, toggle_changed=changed)
        previous = self._assessments.latest(
            location.name, at_or_before=snapshot.completed_at, session=session
        )
        current = assess(snapshot, location, self._thresholds)
        changes = diff(previous.assessment if previous is not None else None, current)
        stored = self._assessments.save(current, changes, session=session)
        span = current.breakpoint_span
        if span is not None and span != location.breakpoint_span:
            self._locations.set_breakpoint_span(location.name, span, session=session)
            location = _with_span(location, stored)
        return AssessedLocation(location, stored, created=True)


def official_products(
    snapshot: Snapshot, location: Location, thresholds: Thresholds
) -> tuple[OfficialProduct, ...]:
    """Say which official products cover a location, without storing anything.

    Args:
        snapshot: The snapshot.
        location: The location.
        thresholds: The coastal reach and the end tolerance the segments are read with.

    Returns:
        Every NWS alert the snapshot holds for the location, covering or not (issue #10),
        in the snapshot's order, then every NHC watch-warning segment that covers it.
    """
    return assess(snapshot, location, thresholds).official


def is_county_context(product: OfficialProduct) -> bool:
    """Whether a product is a county-zone alert outside the location's zones (issue #10).

    Such an alert is shown with the zones it does cover and never sets the level.

    Args:
        product: An official product of an assessment.

    Returns:
        Whether it is that context.
    """
    return product.kind == "nws_alert" and not product.covers and product.reason == OUTSIDE_ZONES


def segment_breakpoint_names(
    segment: Geometry, breakpoints: Sequence[Breakpoint]
) -> tuple[str, ...]:
    """Name a watch-warning segment's ends from the snapshot's breakpoint catalogue.

    Args:
        segment: The watch-warning segment geometry.
        breakpoints: The snapshot's coastal breakpoint catalogue.

    Returns:
        The catalogue breakpoint names at the segment's ends, in segment order.
    """
    return segment_ends(segment, breakpoints)
