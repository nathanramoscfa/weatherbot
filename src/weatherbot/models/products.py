# src/weatherbot/models/products.py
"""Text products, feeds, graphics, breakpoints, service catalogs, and display layers."""

from typing import Literal, Self

from pydantic import Field, JsonValue, model_validator

from weatherbot.models.advisory_number import AdvisoryNumber
from weatherbot.models.base import DomainModel
from weatherbot.models.geometry import Crs, Geometry, require_geometry
from weatherbot.models.provenance import Provenance
from weatherbot.models.storms import AtcfId, StormSlot
from weatherbot.models.times import UtcDatetime

NO_STORMS_TITLE = "There are no tropical cyclones at this time."


class TextProduct(DomainModel):
    """A TCP (by slot) or a TWO (by basin) from the NWS API.

    A TCP's header names its storm's ATCF id and advisory, which a client matches, because
    later storms of a season reuse a slot. A TWO names neither.
    """

    product_id: str = Field(min_length=1)
    code: Literal["TCP", "TWO"]
    location: str = Field(description="A TCP's slot or a TWO's basin (AT, EP, CP).")
    wmo_collective_id: str
    issuing_office: str
    issued_at: UtcDatetime
    text: str = Field(repr=False)
    atcf_id: AtcfId | None
    advisory: AdvisoryNumber | None
    provenance: Provenance

    @model_validator(mode="after")
    def _storm_only_for_a_tcp(self) -> Self:
        if self.code == "TWO" and (self.atcf_id is not None or self.advisory is not None):
            message = "a TWO names no storm or advisory"
            raise ValueError(message)
        return self


class GisFeedItem(DomainModel):
    """One item of an NHC GIS RSS feed.

    The no-storm placeholder ("There are no tropical cyclones at this time.") is kept as an
    item, and its ``pubDate`` is not a time, so it has no ``published_at``.
    """

    feed: Literal["at", "ep", "cp"]
    guid: str
    title: str
    link: str
    published_at: UtcDatetime | None
    is_placeholder: bool
    atcf_id: AtcfId | None = Field(description="nhc:Cyclone's atcf, upper case.")
    slot: StormSlot | None = Field(description="nhc:Cyclone's wallet.")
    provenance: Provenance

    @model_validator(mode="after")
    def _placeholder_has_no_time(self) -> Self:
        if self.is_placeholder != (self.title.strip() == NO_STORMS_TITLE):
            message = "is_placeholder marks exactly the no-storm item"
            raise ValueError(message)
        if self.is_placeholder and (self.published_at or self.atcf_id or self.slot):
            message = "the placeholder item has no time and no storm"
            raise ValueError(message)
        return self


class OutlookGraphic(DomainModel):
    """One of the six outlook maps; its size changes over time, so it is recorded."""

    basin: Literal["atl", "pac", "cpac"]
    horizon: Literal["2d0", "7d0"]
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)
    provenance: Provenance


class Breakpoint(DomainModel):
    """A coastal watch-warning breakpoint.

    Its position comes from the layer's ``lat`` and ``lon`` fields, because the features'
    geometry is null.
    """

    name: str
    state: str | None
    country: str
    position: Geometry
    provenance: Provenance

    @model_validator(mode="after")
    def _point(self) -> Self:
        require_geometry(self.position, ("Point",), "a breakpoint")
        return self


class MapLayer(DomainModel):
    """One layer of a service catalog. Its id is valid only for the read that found it."""

    id: int = Field(ge=0)
    name: str
    type: str = Field(description="Feature Layer, Group Layer, and so on.")
    geometry_type: str | None
    group_path: tuple[str, ...] = Field(
        description="The names of its parent groups, outermost first."
    )


class MapCatalog(DomainModel):
    """An ArcGIS service catalog as read once: layer ids never outlive the read."""

    service: str = Field(description="Such as tropical/NHC_tropical_weather.")
    read_at: UtcDatetime
    layers: tuple[MapLayer, ...]
    provenance: Provenance


class OverlayLayer(DomainModel):
    """One WMS layer and its ``time`` dimension's default."""

    name: str
    time_default: UtcDatetime | None


class OverlayCatalog(DomainModel):
    """A WMS capabilities document: the layers the map may load."""

    service: str
    layers: tuple[OverlayLayer, ...]
    provenance: Provenance


class DisplayLayer(DomainModel):
    """A layer v2 shows but does not interpret, kept as the FeatureCollection received.

    Past points and track, the wind swath, and peak surge stay raw until a capture with
    features fixes their fields.
    """

    layer_name: str
    feature_collection: dict[str, JsonValue] = Field(repr=False)
    crs: Crs
    provenance: Provenance
