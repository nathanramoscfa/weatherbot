# src/weatherbot/models/outlook.py
"""The tropical weather outlook's areas and the wind-speed probabilities (issue #12)."""

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, Literal, Self

from pydantic import Field, model_validator

from weatherbot.models.base import DomainModel
from weatherbot.models.codes import OutlookRisk
from weatherbot.models.geometry import Geometry, GeometryType, require_geometry
from weatherbot.models.provenance import Provenance
from weatherbot.models.times import UtcDatetime

# The geometry each outlook layer draws.
_OUTLOOK_GEOMETRY: Final[Mapping[str, tuple[GeometryType, ...]]] = MappingProxyType(
    {
        "two_day_location": ("Point", "MultiPoint"),
        "seven_day_location": ("Point", "MultiPoint"),
        "development_region": ("Polygon", "MultiPolygon"),
        "development_motion": ("LineString", "MultiLineString"),
    }
)
_PERCENT: Final = re.compile(r"(?P<value>\d{1,3})%")
_MAX_PERCENT: Final = 100

# The bands NHC's probabilistic-wind layers use, as half-open ranges of percent; the top
# band includes 100. Any other label is a schema error.
WIND_PROBABILITY_BANDS: Final = MappingProxyType(
    {
        "<5%": (0, 5),
        "5-10%": (5, 10),
        "10-20%": (10, 20),
        "20-30%": (20, 30),
        "30-40%": (30, 40),
        "40-50%": (40, 50),
        "50-60%": (50, 60),
        "60-70%": (60, 70),
        "70-80%": (70, 80),
        "80-90%": (80, 90),
        ">90%": (90, 100),
    }
)


def parse_percent(text: str) -> int:
    """Parse an outlook chance such as ``20%``.

    Args:
        text: The ``prob2day`` or ``prob7day`` text.

    Returns:
        The percentage, 0 to 100.

    Raises:
        ValueError: The text is not a percentage.
    """
    match = _PERCENT.fullmatch(text.strip())
    if match is None or int(match["value"]) > _MAX_PERCENT:
        message = f"not a percentage: {text!r}"
        raise ValueError(message)
    return int(match["value"])


def parse_band_label(label: str) -> tuple[int, int]:
    """Return the ``[lower, upper)`` percent range of a band label (``>90%`` is [90, 100]).

    Args:
        label: The layer's ``percentage``, such as ``5-10%``.

    Returns:
        The lower and upper percent.

    Raises:
        ValueError: The label is not one of NHC's bands.
    """
    try:
        return WIND_PROBABILITY_BANDS[label]
    except KeyError:
        message = f"unknown wind-probability band {label!r}"
        raise ValueError(message) from None


class OutlookArea(DomainModel):
    """A disturbance marker, development region, or motion arrow in the outlook."""

    kind: Literal[
        "two_day_location", "seven_day_location", "development_region", "development_motion"
    ]
    basin: str = Field(description="The layer's text, such as Atlantic or Pacific.")
    chance_2day_pct: int | None = Field(ge=0, le=100, description="From prob2day.")
    chance_7day_pct: int | None = Field(ge=0, le=100, description="From prob7day.")
    risk_2day: OutlookRisk | None
    risk_7day: OutlookRisk | None
    outlook_stamp: str = Field(description="idp_source: gtwo_areas_ and a YYYYMMDDHHMM stamp.")
    issued_at: UtcDatetime = Field(description="From idp_filedate.")
    geometry: Geometry
    provenance: Provenance

    @model_validator(mode="after")
    def _geometry_fits_kind(self) -> Self:
        allowed = _OUTLOOK_GEOMETRY[self.kind]
        require_geometry(self.geometry, allowed, f"an outlook {self.kind}")
        return self


class WindProbabilityBand(DomainModel):
    """One band of a wind-speed-probability product.

    ``geometry_note`` says how the shape differs from the source's, as when a replay
    extract made an invalid source band valid before clipping it; ``None`` when the
    shape is the source's own.
    """

    lower_pct: int = Field(ge=0, le=100)
    upper_pct: int = Field(ge=0, le=100)
    label: str = Field(description="The layer's percentage, such as 5-10%.")
    geometry: Geometry
    geometry_note: str | None = None

    @classmethod
    def from_label(cls, label: str, geometry: Geometry, geometry_note: str | None = None) -> Self:
        """Build a band from its label.

        Args:
            label: The band label.
            geometry: The band's shape.
            geometry_note: How the shape differs from the source's, if it does.

        Returns:
            The band.
        """
        lower, upper = parse_band_label(label)
        return cls(
            lower_pct=lower,
            upper_pct=upper,
            label=label,
            geometry=geometry,
            geometry_note=geometry_note,
        )

    @model_validator(mode="after")
    def _known_band(self) -> Self:
        if parse_band_label(self.label) != (self.lower_pct, self.upper_pct):
            message = "lower_pct and upper_pct must be the label's band"
            raise ValueError(message)
        require_geometry(self.geometry, ("Polygon", "MultiPolygon"), "a wind-probability band")
        return self

    @property
    def upper_inclusive(self) -> bool:
        """Whether ``upper_pct`` belongs to the band: only the top band's 100 does."""
        return self.upper_pct == _MAX_PERCENT


class WindProbabilityProduct(DomainModel):
    """The probability of winds at one threshold within 120 hours, at one synoptic time.

    Issue #12 decided that wind-speed probabilities belong to the snapshot, not to a
    storm: the ``Probabilistic Winds`` layers carry a band and a synoptic time and no
    storm, NHC publishes one combined product per synoptic time, and no official field
    attributes a band to a storm. So this product has no storm field, and the snapshot
    holds one per threshold.

    ``coverage`` is ``None`` for a full product. An extract, such as the replay corpus's
    landmark windows, records the areal geometry it covers, in the product's CRS, and
    holds no band outside it: such a product says nothing about a point outside its
    coverage.
    """

    threshold_kt: Literal[34, 50, 64]
    synoptic_at: UtcDatetime = Field(description="From idp_source's leading stamp.")
    horizon_h: Literal[120] = 120
    resolution: Literal["5km"] = "5km"
    bands: tuple[WindProbabilityBand, ...]
    coverage: Geometry | None = Field(
        default=None, description="None: a full product. An extract: the area it covers."
    )
    provenance: Provenance

    @model_validator(mode="after")
    def _bands_inside_coverage(self) -> Self:
        coverage = self.coverage
        if coverage is None:
            return self
        require_geometry(coverage, ("Polygon", "MultiPolygon"), "a wind-probability coverage")
        if any(band.geometry.crs != coverage.crs for band in self.bands):
            message = "an extract's coverage is in its bands' CRS"
            raise ValueError(message)
        area = coverage.to_shapely()
        if any(not area.covers(band.geometry.to_shapely()) for band in self.bands):
            message = "every band of an extract lies inside its coverage"
            raise ValueError(message)
        return self
