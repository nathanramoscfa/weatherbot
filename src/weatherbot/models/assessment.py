# src/weatherbot/models/assessment.py
"""An assessment: the level a snapshot sets for a location, and everything behind it.

Evidence holds names, codes, instants, and distances, never a coordinate. It cites each
product through a ``Citation``, a provenance that drops the request URL of any source
whose URLs carry a location: an NWS point query's URL holds the location's coordinates.
An assessment names every input it lacked; its level then reads as a floor.

A storm threat and the change events say what each storm means for the location and
what changed since the previous assessment. A threat's distances, bearing, and instants
locate the location as surely as its coordinates do, so they stay out of every ``repr``.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from weatherbot.models.advisory_number import AdvisoryNumber
from weatherbot.models.base import DomainModel
from weatherbot.models.ladder import RULE_LEVELS, AlertLevel, RuleId, Thresholds
from weatherbot.models.provenance import Provenance, SourceId
from weatherbot.models.storms import AtcfId
from weatherbot.models.times import UtcDatetime

LOCATED_SOURCES: Final[frozenset[SourceId]] = frozenset(
    {"nws-points", "nws-alerts-point", "geocode-nominatim"}
)
"""The sources whose request URLs carry a location's coordinates."""

TRACK_FALLBACK_LABEL: Final = "track closest approach, not a wind arrival"
"""The label of an arrival read from the forecast track because no product exists."""

type WindThreshold = Literal[34, 50, 64]
type EvidenceTest = Literal[
    "point_query", "zone_list", "segment_distance", "point_in_polygon", "band", "toggle"
]
type ProductKind = Literal[
    "nws_alert",
    "watch_warning_segment",
    "cone",
    "wind_probability",
    "development_region",
    "evacuation_toggle",
]
type MissingInput = Literal[
    "nws_alerts",
    "source",
    "cone",
    "forecast_points",
    "wind_probabilities",
    "outlook_areas",
    "arrival_times",
]
type ArrivalKind = Literal["earliest_reasonable", "most_likely"]
type ArrivalOrigin = Literal["kmz", "map_layer", "track"]
type ArrivalOutcome = Literal["before", "between", "after", "outside", "unresolved", "track"]
type ChangeKind = Literal[
    "level_changed",
    "advisory_issued",
    "official_added",
    "official_changed",
    "official_removed",
    "cone_entered",
    "cone_left",
]
type Direction = Literal["up", "down", "initial"]

CHANGE_KINDS: Final[tuple[ChangeKind, ...]] = (
    "level_changed",
    "advisory_issued",
    "official_added",
    "official_changed",
    "official_removed",
    "cone_entered",
    "cone_left",
)
"""The seven kinds of change event, in the order ``diff`` emits them."""


class BreakpointSpan(DomainModel):
    """The stretch of coast a location sits on, named from NHC's breakpoint catalogue.

    Either the two catalogue breakpoints, in catalogue order, between which the
    location's coast falls (one when its nearest breakpoint has no neighbour in the same
    country), or the one ``country (region)`` entry that holds it. The span names a
    coast; it never decides whether a watch or warning covers the location.
    """

    names: tuple[str, ...] = Field(min_length=1, max_length=2)
    country: str
    is_region: bool = Field(description="Whether the span is a country (region) entry.")
    catalog_loaded_at: UtcDatetime | None = Field(
        default=None,
        description="The catalogue's idp_filedate; None for one stored before it was read.",
    )

    @model_validator(mode="after")
    def _region_is_one_name(self) -> Self:
        if self.is_region and len(self.names) != 1:
            message = "a region span names its one region"
            raise ValueError(message)
        return self


class Citation(DomainModel):
    """The response a piece of evidence cites: a ``Provenance`` that cannot locate anyone.

    ``url`` is the request URL, except for a source in ``LOCATED_SOURCES``, whose URL
    holds a location's coordinates; that response is still identified by its source,
    fetch instant, and SHA-256.
    """

    source_id: SourceId
    url: str | None = Field(pattern=r"^https?://\S+$")
    status: int = Field(ge=100, le=599)
    fetched_at: UtcDatetime
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    issued_at: UtcDatetime | None = None
    advisory: AdvisoryNumber | None = None

    @classmethod
    def of(cls, provenance: Provenance) -> Self:
        """Cite a provenance, dropping its URL when the URL can carry a location.

        Args:
            provenance: The response's provenance.

        Returns:
            The citation.
        """
        located = provenance.source_id in LOCATED_SOURCES
        return cls(
            source_id=provenance.source_id,
            url=None if located else provenance.url,
            status=provenance.status,
            fetched_at=provenance.fetched_at,
            sha256=provenance.sha256,
            issued_at=provenance.issued_at,
            advisory=provenance.advisory,
        )

    @model_validator(mode="after")
    def _no_located_url(self) -> Self:
        if self.source_id in LOCATED_SOURCES and self.url is not None:
            message = "a citation keeps no URL of a source whose URLs carry a location"
            raise ValueError(message)
        return self


class Evidence(DomainModel):
    """One match of the deciding rule: the product, the test that fired, and what it found.

    ``issued_at`` is the product's issuance: an alert's ``sent``, an advisory's issuance,
    an outlook's file date, or a probability product's synoptic time. ``distance_km``,
    ``at_end``, ``closest_approach_at``, and ``lead_h`` are set where the test measured
    them; ``lead_h`` counts from the assessment's instant, and an approach already past
    counts as now. ``crs`` names the CRS of the geometry tested. ``detail`` is a plain
    sentence with no coordinate.
    """

    rule: RuleId
    product: ProductKind
    citation: Citation | None = Field(default=None, description="None only for the toggle.")
    code: str | None = Field(
        default=None, description="The NWS event, the NHC tcww code, or the band label."
    )
    atcf_id: AtcfId | None = None
    storm_name: str | None = None
    advisory: AdvisoryNumber | None = None
    issued_at: UtcDatetime | None = None
    test: EvidenceTest
    distance_km: float | None = Field(default=None, ge=0.0)
    at_end: bool | None = None
    crs: str | None = Field(default=None, description="EPSG:4326, or native with its datum.")
    closest_approach_at: UtcDatetime | None = None
    lead_h: float | None = Field(default=None, ge=0.0)
    breakpoints: tuple[str, ...] = Field(
        default=(), description="A segment's ends, named from the catalogue when known."
    )
    chance_pct: int | None = Field(
        default=None, ge=0, le=100, description="A region's chance or a band's lower bound."
    )
    threshold_kt: WindThreshold | None = None
    detail: str = Field(min_length=1)

    @model_validator(mode="after")
    def _toggle_cites_nothing(self) -> Self:
        toggle = self.product == "evacuation_toggle"
        if toggle != (self.test == "toggle") or toggle != (self.citation is None):
            message = "the toggle, and only the toggle, is tested as a toggle and cites nothing"
            raise ValueError(message)
        return self

    @property
    def source_id(self) -> SourceId | None:
        """The cited product's source, or ``None`` for the toggle."""
        return self.citation.source_id if self.citation is not None else None


class OfficialProduct(DomainModel):
    """An NWS alert or a covering NHC watch-warning segment the engine considered.

    ``covers`` says whether the product is in effect for the location, and ``reason``
    says why or why not. ``rule`` is the rule a covering product triggers, or ``None``
    when it sets no level: an event or code outside the ladder. ``references`` names the
    alerts an alert updates, by id, so ``diff`` can tell a replacement from a new alert.
    """

    kind: Literal["nws_alert", "watch_warning_segment"]
    citation: Citation
    code: str = Field(description="The NWS event, or the NHC tcww code as received.")
    alert_id: str | None = None
    references: tuple[str, ...] = Field(
        default=(), description="The ids of the alerts an alert updates."
    )
    issuer: str | None = Field(default=None, description="An alert's senderName.")
    atcf_id: AtcfId | None = None
    storm_name: str | None = None
    advisory: AdvisoryNumber | None = None
    issued_at: UtcDatetime | None = None
    expires_at: UtcDatetime | None = None
    found_by: tuple[str, ...] = Field(
        default=(), description="An alert's queries: point, or zone and its id."
    )
    zones: tuple[str, ...] = Field(default=(), description="The UGC zones an alert names.")
    distance_km: float | None = Field(default=None, ge=0.0)
    at_end: bool | None = None
    crs: str | None = None
    breakpoints: tuple[str, ...] = ()
    covers: bool
    rule: RuleId | None = None
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.rule is not None and not self.covers:
            message = "only a covering product triggers a rule"
            raise ValueError(message)
        alert = self.kind == "nws_alert"
        if alert != (self.alert_id is not None) or alert == (self.atcf_id is not None):
            message = "an alert names its id, and a segment names its storm"
            raise ValueError(message)
        if self.references and not alert:
            message = "only an alert references the alerts it updates"
            raise ValueError(message)
        return self


class LocationWindProbability(DomainModel):
    """A wind-speed-probability product read at the location.

    ``reading`` is the band whose shape covers the location, ``below_every_band`` when
    none does, or ``outside_coverage`` when the product is an extract that does not
    cover the location and so says nothing there.
    """

    threshold_kt: WindThreshold
    synoptic_at: UtcDatetime
    reading: Literal["band", "below_every_band", "outside_coverage"]
    label: str | None = None
    lower_pct: int | None = Field(default=None, ge=0, le=100)
    upper_pct: int | None = Field(default=None, ge=0, le=100)
    crs: str | None = Field(
        default=None, description="The CRS of the shapes tested; None when there were none."
    )
    citation: Citation

    @model_validator(mode="after")
    def _band_only_when_read(self) -> Self:
        values = (self.label, self.lower_pct, self.upper_pct)
        if (self.reading == "band") != all(value is not None for value in values) or (
            self.reading != "band" and any(value is not None for value in values)
        ):
            message = "a band reading names its band, and no other reading does"
            raise ValueError(message)
        return self


class UnavailableInput(DomainModel):
    """An input the rules lacked, and why; its presence makes the level a floor."""

    kind: MissingInput
    source_id: SourceId | None = None
    atcf_id: AtcfId | None = None
    storm_name: str | None = None
    threshold_kt: WindThreshold | None = None
    reason: str = Field(min_length=1)


# What each reading states: the fields it sets, of start, end, approach_at, and reason.
_READING_FIELDS: Final[Mapping[ArrivalOutcome, frozenset[str]]] = MappingProxyType(
    {
        "before": frozenset({"end"}),
        "between": frozenset({"start", "end"}),
        "after": frozenset({"start"}),
        "outside": frozenset(),
        "unresolved": frozenset({"reason"}),
        "track": frozenset({"approach_at"}),
    }
)


class ArrivalReading(DomainModel):
    """When tropical-storm-force winds arrive at the location, as one product says.

    ``reading`` is exactly one of: ``before`` the product's earliest labelled instant
    (``end``); ``between`` two labelled instants (``start``, ``end``); ``after`` its latest
    labelled instant (``start``), inside the 5 percent contour; ``outside`` that contour,
    so no arrival at that probability within the product's 120 hours; ``unresolved``, with
    the ``reason``; or ``track``, when the storm has no product of this kind: the forecast
    track's closest approach (``approach_at``), labelled ``TRACK_FALLBACK_LABEL`` because
    it is not a wind arrival. ``origin`` is the product's, or ``track`` for the fallback.
    The instants are times at the location, so they stay out of ``repr``.
    """

    kind: ArrivalKind
    origin: ArrivalOrigin
    reading: ArrivalOutcome
    advisory: AdvisoryNumber | None = Field(
        default=None, description="The product's advisory, or the forecast points'."
    )
    citation: Citation | None = Field(
        default=None, description="The product, or the forecast points for the fallback."
    )
    start: UtcDatetime | None = Field(default=None, repr=False)
    end: UtcDatetime | None = Field(default=None, repr=False)
    approach_at: UtcDatetime | None = Field(default=None, repr=False)
    label: str | None = Field(default=None, description="The fallback's label.")
    reason: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _one_reading(self) -> Self:
        names = ("start", "end", "approach_at", "reason")
        stated = frozenset(name for name in names if getattr(self, name))
        if stated != _READING_FIELDS[self.reading]:
            message = (
                f"a {self.reading} reading states exactly {sorted(_READING_FIELDS[self.reading])}"
            )
            raise ValueError(message)
        if self.start is not None and self.end is not None and self.start >= self.end:
            message = "an interval starts before it ends"
            raise ValueError(message)
        fallback = self.origin == "track"
        if fallback and self.reading not in {"track", "unresolved"}:
            message = "the track fallback reads the closest approach, or nothing"
            raise ValueError(message)
        track = self.reading == "track"
        if (
            (track and not fallback)
            or track != (self.label == TRACK_FALLBACK_LABEL)
            or (not track and self.label is not None)
        ):
            message = "a closest-approach reading, and only that reading, carries its label"
            raise ValueError(message)
        if self.origin == "map_layer" and self.reading != "unresolved":
            message = "a map-layer product carries no instant, so it reads nothing"
            raise ValueError(message)
        if self.citation is None and not fallback:
            message = "a product's reading cites the product"
            raise ValueError(message)
        return self


class StormThreat(DomainModel):
    """What one storm means for the location, read from the storm's own advisory products.

    ``advisory`` and ``issued_at`` are the storm's latest advisory: the roster's public
    advisory in a live snapshot, the cone's advisory in a replay. ``category`` is the
    Saffir-Simpson category NHC states for the advisory's tau-0 point (``ssnum`` 1 to 5),
    and ``None`` below hurricane strength; ``development`` is that point's ``tcdvlp``
    text, kept beside it because a post-tropical cyclone can carry a category too.
    ``in_cone`` reads the repaired cone and is ``None`` without a usable one. From the
    tau-0 center: the geodesic ``distance_km`` and initial ``bearing_deg`` to the
    location, on the figure of the points' CRS (``crs``). From the forecast points: the
    closest approach, its ``lead_h`` from the assessment's instant (an approach already
    past counts as now), and whether a point at or before it is a hurricane. Every value
    measured from the points is ``None`` when the storm has none. No field holds a
    wind-speed probability: those belong to the snapshot (issue #12).
    """

    atcf_id: AtcfId
    storm_name: str = Field(min_length=1)
    advisory: AdvisoryNumber | None = None
    issued_at: UtcDatetime | None = None
    category: int | None = Field(default=None, ge=1, le=5)
    development: str | None = None
    in_cone: bool | None = None
    crs: str | None = Field(default=None, description="The CRS of the forecast points.")
    distance_km: float | None = Field(default=None, ge=0.0, repr=False)
    bearing_deg: float | None = Field(default=None, ge=0.0, lt=360.0, repr=False)
    closest_approach_at: UtcDatetime | None = Field(default=None, repr=False)
    closest_approach_km: float | None = Field(default=None, ge=0.0, repr=False)
    lead_h: float | None = Field(default=None, ge=0.0, repr=False)
    hurricane_by_approach: bool | None = None
    earliest_arrival: ArrivalReading
    most_likely_arrival: ArrivalReading

    @model_validator(mode="after")
    def _measured_together(self) -> Self:
        measured = (
            self.development,
            self.crs,
            self.distance_km,
            self.bearing_deg,
            self.closest_approach_at,
            self.closest_approach_km,
            self.lead_h,
            self.hurricane_by_approach,
        )
        if len({value is None for value in measured}) > 1 or (
            self.category is not None and self.development is None
        ):
            message = "every value read from the forecast points is present, or none is"
            raise ValueError(message)
        if (self.earliest_arrival.kind, self.most_likely_arrival.kind) != (
            "earliest_reasonable",
            "most_likely",
        ):
            message = "a threat reads the earliest-reasonable and the most-likely arrival"
            raise ValueError(message)
        return self


type _Shape = tuple[frozenset[str], frozenset[str]]
type _Product = Literal["nws_alert", "watch_warning_segment"]


def _shape(required: str, optional: str = "") -> _Shape:
    return frozenset(required.split()), frozenset(optional.split())


# The fields each kind of event (and, for an official one, each product) sets: those it
# must set, and those it may.
_EVENT_SHAPES: Final[Mapping[tuple[ChangeKind, _Product | None], _Shape]] = MappingProxyType(
    {
        ("level_changed", None): _shape("level direction rule", "previous_level"),
        ("advisory_issued", None): _shape(
            "atcf_id storm_name advisory", "previous_advisory in_cone"
        ),
        ("official_added", "nws_alert"): _shape("product alert_id codes"),
        ("official_added", "watch_warning_segment"): _shape(
            "product atcf_id storm_name codes", "advisory"
        ),
        ("official_changed", "nws_alert"): _shape(
            "product previous_alert_id alert_id previous_codes codes"
        ),
        ("official_changed", "watch_warning_segment"): _shape(
            "product atcf_id storm_name previous_codes codes", "advisory"
        ),
        ("official_removed", "nws_alert"): _shape("product alert_id codes"),
        ("official_removed", "watch_warning_segment"): _shape(
            "product atcf_id storm_name codes", "advisory"
        ),
        ("cone_entered", None): _shape("atcf_id storm_name", "advisory"),
        ("cone_left", None): _shape("atcf_id storm_name", "advisory"),
    }
)
_EVENT_FIELDS: Final = frozenset(
    name for required, optional in _EVENT_SHAPES.values() for name in required | optional
)


class ChangeEvent(DomainModel):
    """One typed change between two assessments of a location, for Phase 4's policy.

    ``level_changed``: the level moved ``up`` or ``down``, or is the ``initial`` one.
    ``advisory_issued``: a storm has a new advisory, with whether its cone covers the
    location. ``official_added``, ``official_changed``, ``official_removed``: an official
    product that covers the location appeared, was replaced, or no longer covers it; an
    NWS alert by id (one whose ``references`` names a covering predecessor replaces it),
    an NHC storm's covering watch-warning segments by storm and code. ``cone_entered``,
    ``cone_left``: a storm's cone began or stopped covering the location. ``detail`` is a
    plain sentence with names and codes, never a coordinate or a distance.
    """

    kind: ChangeKind
    previous_level: AlertLevel | None = None
    level: AlertLevel | None = None
    direction: Direction | None = None
    rule: RuleId | None = Field(default=None, description="The rule that decides the level.")
    atcf_id: AtcfId | None = None
    storm_name: str | None = None
    previous_advisory: AdvisoryNumber | None = None
    advisory: AdvisoryNumber | None = None
    in_cone: bool | None = None
    product: _Product | None = None
    previous_alert_id: str | None = None
    alert_id: str | None = None
    previous_codes: tuple[str, ...] = ()
    codes: tuple[str, ...] = ()
    detail: str = Field(min_length=1)

    @model_validator(mode="after")
    def _fields_fit_the_kind(self) -> Self:
        shape = _EVENT_SHAPES.get((self.kind, self.product))
        if shape is None:
            message = "an official event names its product, and no other event does"
            raise ValueError(message)
        required, optional = shape
        stated = frozenset(n for n in _EVENT_FIELDS if getattr(self, n) not in (None, ()))
        if not required <= stated <= required | optional:
            message = f"a {self.kind} event sets {sorted(required)}, and may set {sorted(optional)}"
            raise ValueError(message)
        if self.kind == "level_changed" and self.direction != _direction(
            self.previous_level, self.level
        ):
            message = "a level change moves up or down from the previous level, or is initial"
            raise ValueError(message)
        if self.kind == "advisory_issued" and self.previous_advisory == self.advisory:
            message = "an advisory issued differs from the previous one"
            raise ValueError(message)
        if self.kind == "official_changed" and (self.previous_alert_id, self.previous_codes) == (
            self.alert_id,
            self.codes,
        ):
            message = "a changed product differs from its predecessor"
            raise ValueError(message)
        return self


def _direction(previous: AlertLevel | None, level: AlertLevel | None) -> Direction | None:
    """The direction from one level to another: ``None`` when they are equal."""
    if previous is None:
        return "initial"
    if level is None or level == previous:
        return None
    return "up" if level > previous else "down"


class Assessment(DomainModel):
    """The level one snapshot sets for one location, with its evidence.

    ``as_of`` is the snapshot's instant: a live snapshot's ``completed_at``, a replay
    snapshot's advisory issuance. ``evidence`` holds every match of the deciding
    ``rule``, ``official`` every official product considered, and ``threats`` one threat
    per storm, in the snapshot's order. ``complete`` is false whenever an input was
    unavailable, and the level then reads as "at least". ``ruleset`` is ``thresholds``'
    fingerprint with the rule order the assessment ran.
    """

    location_name: str = Field(min_length=1, max_length=64)
    snapshot_id: UUID
    origin: Literal["live", "replay"]
    as_of: UtcDatetime
    level: AlertLevel
    rule: RuleId
    evidence: tuple[Evidence, ...]
    official: tuple[OfficialProduct, ...]
    wind_probabilities: tuple[LocationWindProbability, ...]
    breakpoint_span: BreakpointSpan | None
    threats: tuple[StormThreat, ...]
    unavailable: tuple[UnavailableInput, ...]
    thresholds: Thresholds
    ruleset: str = Field(pattern=r"^[0-9a-f]{64}$")
    complete: bool

    @model_validator(mode="after")
    def _decided(self) -> Self:
        if self.level != RULE_LEVELS[self.rule]:
            message = "the level is the deciding rule's level"
            raise ValueError(message)
        if any(item.rule != self.rule for item in self.evidence) or (
            bool(self.evidence) == (self.rule == RuleId.ALL_CLEAR)
        ):
            message = "the evidence is the deciding rule's matches; all_clear has none"
            raise ValueError(message)
        if self.complete == bool(self.unavailable):
            message = "an assessment is complete exactly when no input was unavailable"
            raise ValueError(message)
        storms = [threat.atcf_id for threat in self.threats]
        if len(set(storms)) != len(storms):
            message = "an assessment holds one threat per storm"
            raise ValueError(message)
        return self
