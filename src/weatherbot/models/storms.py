# src/weatherbot/models/storms.py
"""Storms and their advisory products: the roster, cones, tracks, watches, and wind radii.

Units appear in a field name only where an official statement gives them (recorded in
``docs/DATA_SOURCES.md``): NHC's Tropical Cyclone Status JSON File Reference for the
roster, and the field metadata of the archived forecast packages for the map layers.
"""

from typing import Annotated, Final, Literal, Self

from pydantic import Field, model_validator

from weatherbot.models.advisory_number import AdvisoryNumber
from weatherbot.models.base import DomainModel
from weatherbot.models.codes import StormClassification, WatchWarningType
from weatherbot.models.geometry import Geometry, require_geometry
from weatherbot.models.provenance import Provenance
from weatherbot.models.times import UtcDatetime, parse_nhc_local_time

type AtcfId = Annotated[str, Field(pattern=r"^(AL|EP|CP)\d{6}$")]
"""An ATCF storm id, ``BBNNYYYY`` in upper case: basin, storm number, and year."""

type StormSlot = Literal[
    "AT1", "AT2", "AT3", "AT4", "AT5",
    "EP1", "EP2", "EP3", "EP4", "EP5",
    "CP1", "CP2", "CP3", "CP4", "CP5",
]  # fmt: skip
"""A map-service slot: the roster's ``binNumber`` and the NWS API's TCP location."""

# NHC writes 9999 where a forecast point has no pressure, direction, or speed. A parser
# maps it to None; a model refuses to store the sentinel as a value.
MISSING_VALUE: Final = 9999


class RosterProduct(DomainModel):
    """One of the roster's product objects: its advisory, issuance, and link."""

    advisory: AdvisoryNumber | None = None
    issued_at: UtcDatetime
    url: str | None = Field(default=None, pattern=r"^https://\S+$")


class StormSummary(DomainModel):
    """One storm in ``CurrentStorms.json``.

    Units come from NHC's Tropical Cyclone Status JSON File Reference: ``intensity`` in
    knots, ``pressure`` in millibars, ``movementDir`` in degrees from true north, and
    ``movementSpeed`` in miles per hour.
    """

    atcf_id: AtcfId
    slot: StormSlot
    name: str = Field(min_length=1)
    classification: StormClassification
    intensity_kt: int | None = Field(ge=0)
    pressure_mb: int | None = Field(ge=0)
    latitude: float = Field(ge=-90.0, le=90.0, description="The center, latitudeNumeric.")
    longitude: float = Field(ge=-180.0, le=180.0, description="The center, longitudeNumeric.")
    movement_dir_deg: float | None = Field(ge=0.0, le=360.0)
    movement_speed_mph: float | None = Field(ge=0.0)
    last_update: UtcDatetime
    public_advisory: RosterProduct
    track_cone: RosterProduct | None = None
    earliest_arrival_kmz: RosterProduct | None = None
    most_likely_arrival_kmz: RosterProduct | None = None
    wind_speed_probabilities_issued_at: UtcDatetime | None = None
    has_storm_surge_watch_warning: bool = Field(description="stormSurgeWatchWarningGIS non-null.")
    has_potential_storm_surge_flooding: bool = Field(
        description="potentialStormSurgeFloodingGIS non-null."
    )
    has_peak_surge: bool = Field(description="peakSurgeKML non-null.")

    @model_validator(mode="after")
    def _slot_matches_basin(self) -> Self:
        if self.slot[:2] != {"AL": "AT", "EP": "EP", "CP": "CP"}[self.atcf_id[:2]]:
            message = "a storm's slot must belong to its ATCF basin"
            raise ValueError(message)
        if self.public_advisory.advisory is None:
            message = "the public advisory names its advisory number"
            raise ValueError(message)
        return self


class Advisory(DomainModel):
    """An advisory of one storm, as a product's ``advisnum`` and ``advdate`` state it.

    ``issued_at`` is ``None`` only when the local text names a zone outside the table in
    ``weatherbot.models.times``: the text is kept, and no instant is guessed.
    """

    atcf_id: AtcfId
    number: AdvisoryNumber
    issued_at: UtcDatetime | None
    local_text: str = Field(min_length=1, description="NHC's local issuance text, advdate.")

    @model_validator(mode="after")
    def _instant_follows_text(self) -> Self:
        if parse_nhc_local_time(self.local_text) != self.issued_at:
            message = "issued_at must be the instant local_text names"
            raise ValueError(message)
        return self


class AdvisoryRecord(DomainModel):
    """The fields every advisory product carries: its storm, advisory, and provenance."""

    atcf_id: AtcfId
    advisory: Advisory
    provenance: Provenance

    @model_validator(mode="after")
    def _one_storm(self) -> Self:
        if self.advisory.atcf_id != self.atcf_id:
            message = "a record's advisory must belong to its storm"
            raise ValueError(message)
        return self


class ConeGeometry(AdvisoryRecord):
    """The forecast cone of one advisory."""

    forecast_period_h: int = Field(gt=0, description="fcstprd.")
    geometry: Geometry

    @model_validator(mode="after")
    def _areal(self) -> Self:
        require_geometry(self.geometry, ("Polygon", "MultiPolygon"), "a cone")
        return self


class TrackPoint(AdvisoryRecord):
    """One forecast point.

    Units come from the archived forecast packages' field metadata: ``MAXWIND``, ``GUST``,
    and ``TCSPD`` in knots, ``MSLP`` in millibars, ``TCDIR`` in degrees. Each value is
    ``None`` where NHC writes 9999.
    """

    tau_h: int = Field(ge=0)
    valid_at: UtcDatetime = Field(description="From validtime (DD/HHMM, UTC).")
    valid_local_text: str | None = Field(default=None, description="fldatelbl, as received.")
    position: Geometry
    max_wind_kt: int | None = Field(ge=0)
    gust_kt: int | None = Field(ge=0)
    mslp_mb: int | None = Field(ge=0)
    direction_deg: int | None = Field(ge=0, le=360)
    speed_kt: int | None = Field(ge=0)
    development: str = Field(description="tcdvlp, such as Hurricane.")
    storm_type: str = Field(description="stormtype, such as HU.")
    saffir_simpson: int | None = Field(ge=0, le=5, description="ssnum.")
    label: str = Field(description="dvlbl, such as H.")

    @model_validator(mode="after")
    def _point_without_sentinels(self) -> Self:
        require_geometry(self.position, ("Point",), "a track point")
        values = (self.max_wind_kt, self.gust_kt, self.mslp_mb, self.direction_deg, self.speed_kt)
        if MISSING_VALUE in values:
            message = "9999 means no value; store None"
            raise ValueError(message)
        return self


class ForecastTrack(AdvisoryRecord):
    """The forecast track line. A MultiLineString is allowed for a track split at 180°."""

    geometry: Geometry

    @model_validator(mode="after")
    def _linear(self) -> Self:
        require_geometry(self.geometry, ("LineString", "MultiLineString"), "a track")
        return self


class WatchWarningSegment(AdvisoryRecord):
    """A coastal watch or warning segment.

    The replay corpus keeps a one-vertex source line as a Point with its
    ``geometry_note``; a Point segment must carry that note.
    """

    tcww: WatchWarningType
    geometry: Geometry
    geometry_note: str | None = None

    @model_validator(mode="after")
    def _segment_or_noted_point(self) -> Self:
        require_geometry(
            self.geometry, ("LineString", "MultiLineString", "Point"), "a watch-warning segment"
        )
        if self.geometry.type == "Point" and not self.geometry_note:
            message = "a Point watch-warning segment must carry its geometry_note"
            raise ValueError(message)
        return self


class WindRadii(DomainModel):
    """A wind-radii polygon: forecast radii, or the advisory wind field at tau 0.

    Units come from the archived forecast packages' field metadata: ``RADII`` in knots,
    and ``NE``, ``SE``, ``SW``, ``NW`` in nautical miles. The layers carry ``advnum`` but no
    ``advdate``, so a record holds the advisory number alone.
    """

    atcf_id: AtcfId
    advisory: AdvisoryNumber
    provenance: Provenance
    threshold_kt: Literal[34, 50, 64] = Field(description="radii.")
    tau_h: int = Field(ge=0)
    valid_at: UtcDatetime
    synoptic_at: UtcDatetime
    ne_extent_nmi: int = Field(ge=0)
    se_extent_nmi: int = Field(ge=0)
    sw_extent_nmi: int = Field(ge=0)
    nw_extent_nmi: int = Field(ge=0)
    is_advisory_field: bool = Field(description="The Advisory Wind Field layer, not forecast.")
    geometry: Geometry

    @model_validator(mode="after")
    def _areal(self) -> Self:
        require_geometry(self.geometry, ("Polygon", "MultiPolygon"), "wind radii")
        if self.is_advisory_field and self.tau_h != 0:
            message = "the advisory wind field is at tau 0"
            raise ValueError(message)
        return self
