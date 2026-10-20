# src/weatherbot/models/assessment.py
"""An assessment: the level a snapshot sets for a location, and everything behind it.

Evidence holds names, codes, instants, and distances, never a coordinate. It cites each
product through a ``Citation``, a provenance that drops the request URL of any source
whose URLs carry a location: an NWS point query's URL holds the location's coordinates.
An assessment names every input it lacked; its level then reads as a floor.
"""

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
    "nws_alerts", "source", "cone", "forecast_points", "wind_probabilities", "outlook_areas"
]


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
    when it sets no level: an event or code outside the ladder.
    """

    kind: Literal["nws_alert", "watch_warning_segment"]
    citation: Citation
    code: str = Field(description="The NWS event, or the NHC tcww code as received.")
    alert_id: str | None = None
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


class Assessment(DomainModel):
    """The level one snapshot sets for one location, with its evidence.

    ``as_of`` is the snapshot's instant: a live snapshot's ``completed_at``, a replay
    snapshot's advisory issuance. ``evidence`` holds every match of the deciding
    ``rule``, and ``official`` every official product considered. ``complete`` is false
    whenever an input was unavailable, and the level then reads as "at least". ``ruleset``
    is ``thresholds``' fingerprint with the rule order the assessment ran.
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
        return self
