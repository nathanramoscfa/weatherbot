# src/weatherbot/sources/nhc_map.py
"""Parsers and fetch functions for the NHC map services (``docs/DATA_SOURCES.md``).

The summary service (``nhc-map-tropical-summary``) holds every active storm's products in
one layer per product, told apart by ``binnumber``; the slot service
(``nhc-map-tropical-weather``) holds the same products per slot (``EP5 Forecast Cone``).
The same parsers read both. A storm product's features are split by ``binnumber`` and
joined to the roster's storm in that slot; a feature whose slot, basin, storm number, or
storm id disagrees with the roster is skipped with a Source-drift warning.

An ``Advisory`` takes its number from ``advisnum``, its local text from ``advdate``, and
its ``issued_at`` from the roster's issuance for that product (``trackCone`` for the
cone's advisory, the arrival-time objects for the arrival lines). When the roster's
product names another advisory, the local text dates it; when the text and the roster
differ by more than an hour, the roster's value is kept and the difference logged as
Source drift.

Every parser reads fields by name, through ``FIELDS_READ``: the register's "Fields v2 uses"
for each typed layer, which the field-coverage contract test keeps equal to the register.
Display layers are kept as received (``DisplayLayer``). Geometry is ``EPSG:4326``: every
query asks for ``outSR=4326``.
"""

import asyncio
import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from datetime import timedelta
from types import MappingProxyType
from typing import Final, Literal, cast

from weatherbot.models import (
    WGS84,
    Advisory,
    AdvisoryNumber,
    ArrivalTimeLine,
    ArrivalTimeProduct,
    Breakpoint,
    ConeGeometry,
    DisplayLayer,
    DomainModel,
    ForecastTrack,
    Geometry,
    MapCatalog,
    OutlookArea,
    OutlookRisk,
    Provenance,
    RosterProduct,
    SourceId,
    StormProducts,
    StormSlot,
    StormSummary,
    TrackPoint,
    WatchWarningSegment,
    WatchWarningType,
    WindProbabilityBand,
    WindProbabilityProduct,
    WindRadii,
    from_epoch_ms,
    parse_nhc_local_time,
    parse_percent,
    parse_synoptic_time,
    resolve_track_valid_time,
)
from weatherbot.sources.arcgis import (
    SERVICES,
    TROPICAL_SUMMARY,
    TROPICAL_WEATHER,
    LayerQuery,
    attributes,
    query,
    resolve,
)
from weatherbot.sources.drift import warn_drift
from weatherbot.sources.errors import SourceSchemaError
from weatherbot.sources.fields import Fields, as_mapping, model_errors
from weatherbot.sources.http import Fetcher, FetchResult, SourceResult

# Storm products, named as the summary service names them; the slot service prefixes the
# slot (``EP5 Forecast Cone``).
FORECAST_POINTS: Final = "Forecast Points"
FORECAST_TRACK: Final = "Forecast Track"
FORECAST_CONE: Final = "Forecast Cone"
WATCH_WARNING: Final = "Watch-Warning"
FORECAST_WIND_RADII: Final = "Forecast Wind Radii"
ADVISORY_WIND_FIELD: Final = "Advisory Wind Field"
EARLIEST_ARRIVAL: Final = "Earliest Reasonable Arrival Time"
MOST_LIKELY_ARRIVAL: Final = "Most Likely Arrival Time"
STORM_LAYERS: Final = (
    FORECAST_CONE,
    FORECAST_POINTS,
    FORECAST_TRACK,
    WATCH_WARNING,
    FORECAST_WIND_RADII,
    ADVISORY_WIND_FIELD,
    EARLIEST_ARRIVAL,
    MOST_LIKELY_ARRIVAL,
)
STORM_DISPLAY_LAYERS: Final = ("Past Points", "Past Track", "Past Cumulative Wind Swath")
OUTLOOK_KINDS: Final[
    Mapping[
        str,
        Literal[
            "two_day_location", "seven_day_location", "development_region", "development_motion"
        ],
    ]
] = MappingProxyType(
    {
        "Two-Day: Current Location": "two_day_location",
        "Seven-Day: Current Location": "seven_day_location",
        "Seven-Day: Development Motion": "development_motion",
        "Seven-Day: Potential Development Region": "development_region",
    }
)
WIND_PROBABILITY_THRESHOLDS: Final[Mapping[str, Literal[34, 50, 64]]] = MappingProxyType(
    {
        "Probabilistic Winds 34 kts": 34,
        "Probabilistic Winds 50 kts": 50,
        "Probabilistic Winds 64 kts": 64,
    }
)
BREAKPOINT_LAYER: Final = "Watch_Warning_Breakpoints"
PEAK_SURGE_LAYERS: Final = ("Points", "Lines", "Polygons")
DISPLAY_LAYERS: Final = frozenset({*STORM_DISPLAY_LAYERS, *PEAK_SURGE_LAYERS})
"""Layers kept as received; the field-coverage test checks their register fields."""

_OUTLOOK_FIELDS: Final = frozenset(
    {"basin", "prob2day", "risk2day", "prob7day", "risk7day", "idp_source", "idp_filedate"}
)
_ARRIVAL_FIELDS: Final = frozenset({"arrival_time", "folderpath", "idp_subset", "binnumber"})
_RADII_FIELDS: Final = frozenset(
    {"radii", "validtime", "synoptime", "ne", "se", "sw", "nw", "advnum", "stormid", "binnumber"}
)
FIELDS_READ: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        **dict.fromkeys(OUTLOOK_KINDS, _OUTLOOK_FIELDS),
        FORECAST_POINTS: frozenset(
            {
                "stormname",
                "stormtype",
                "tcdvlp",
                "basin",
                "binnumber",
                "stormnum",
                "advisnum",
                "advdate",
                "tau",
                "validtime",
                "fldatelbl",
                "maxwind",
                "gust",
                "mslp",
                "tcdir",
                "tcspd",
                "ssnum",
                "dvlbl",
            }
        ),
        FORECAST_TRACK: frozenset({"advisnum", "advdate", "binnumber"}),
        FORECAST_CONE: frozenset(
            {
                "stormname",
                "stormtype",
                "basin",
                "stormnum",
                "advisnum",
                "advdate",
                "fcstprd",
                "binnumber",
                "idp_source",
            }
        ),
        WATCH_WARNING: frozenset({"tcww", "stormname", "advisnum", "advdate", "binnumber"}),
        FORECAST_WIND_RADII: _RADII_FIELDS | {"tau"},
        ADVISORY_WIND_FIELD: _RADII_FIELDS,
        EARLIEST_ARRIVAL: _ARRIVAL_FIELDS,
        MOST_LIKELY_ARRIVAL: _ARRIVAL_FIELDS,
        **dict.fromkeys(WIND_PROBABILITY_THRESHOLDS, frozenset({"percentage", "idp_source"})),
        BREAKPOINT_LAYER: frozenset(
            {"objectid", "name", "lat", "lon", "state", "country", "idp_filedate"}
        ),
    }
)
"""The fields each typed layer's parser reads, by the layer's name without its slot."""

CONE_ADVISORY_FIELDS: Final = ("binnumber", "advisnum")
CONE_ADVISORIES_READ: Final = frozenset(CONE_ADVISORY_FIELDS)
"""The cone-layer attributes the window watch reads without geometry."""

ISSUANCE_TOLERANCE: Final = timedelta(hours=1)
_SLOT_NAME: Final = re.compile(r"^(?:AT|EP|CP)[1-5]$")
_SLOT_LAYER: Final = re.compile(r"(?P<slot>(?:AT|EP|CP)[1-5]) (?P<name>.+)")
_FOLDER_ADVISORY: Final = re.compile(
    r"(?P<atcf>(?:AL|EP|CP)\d{6})_Adv(?P<number>\d{1,3}[A-Za-z]?)\s*$", re.IGNORECASE
)
_RADII_THRESHOLDS: Final = (34, 50, 64)


def base_layer_name(layer: str) -> str:
    """Return a layer's name without its slot: ``EP5 Forecast Cone`` → ``Forecast Cone``.

    Args:
        layer: A layer name of either tropical service.

    Returns:
        The name the summary service uses.
    """
    match = _SLOT_LAYER.fullmatch(layer)
    if match and match["name"] in (*STORM_LAYERS, *STORM_DISPLAY_LAYERS):
        return match["name"]
    return layer


def _features(
    collection: Mapping[str, object], layer: str, source: SourceId
) -> Iterator[tuple[Mapping[str, object], Fields]]:
    """Yield each feature with its properties, read through the layer's declared fields."""
    declared = FIELDS_READ[base_layer_name(layer)]
    for index, item in enumerate(cast("Sequence[object]", collection.get("features", ()))):
        feature = as_mapping(item, source, f"{layer} feature {index}")
        properties = as_mapping(
            feature.get("properties"), source, f"{layer} feature {index}'s properties"
        )
        yield (
            feature,
            Fields(properties, declared, source_id=source, where=f"{layer} feature {index}"),
        )


def _geometry(feature: Mapping[str, object], fields: Fields) -> Geometry:
    value = feature.get("geometry")
    if not isinstance(value, dict):
        message = f"{fields.where} has no geometry"
        raise SourceSchemaError(fields.source_id, message)
    with model_errors(fields.source_id, f"{fields.where}'s geometry"):
        return Geometry.from_geojson(cast("dict[str, object]", value), WGS84)


def _storm_of(fields: Fields, storms: Sequence[StormSummary], layer: str) -> StormSummary | None:
    """Join a feature to the roster's storm in its ``binnumber`` slot."""
    slot = fields.text("binnumber")
    storm = next((storm for storm in storms if storm.slot == slot), None)
    if storm is None:
        warn_drift(
            fields.source_id, f"{layer} holds a feature for slot {slot}, which the roster lacks"
        )
    return storm


def _same_storm(
    storm: StormSummary, fields: Fields, *, basin: str, number: int, layer: str
) -> bool:
    if storm.atcf_id[:2] == basin.upper() and int(storm.atcf_id[2:4]) == number:
        return True
    warn_drift(
        fields.source_id,
        f"{layer} names storm {basin.upper()}{number:02d} in slot {storm.slot}, "
        f"where the roster lists {storm.atcf_id}",
    )
    return False


def _check_name(storm: StormSummary, fields: Fields, layer: str) -> None:
    name = fields.text("stormname")
    if storm.name.lower() not in name.lower():
        warn_drift(
            fields.source_id,
            f"{layer} names the storm {name!r}; the roster's {storm.atcf_id} is {storm.name!r}",
        )


class _Advisories:
    """Builds each storm's advisory once per layer, so a drift is warned once."""

    def __init__(self, source: SourceId, layer: str) -> None:
        self._source: SourceId = source
        self._layer = layer
        self._built: dict[tuple[str, str, str], Advisory] = {}

    def of(self, storm: StormSummary, fields: Fields, anchor: RosterProduct | None) -> Advisory:
        number_text, text = fields.code("advisnum"), fields.text("advdate")
        key = (storm.atcf_id, number_text, text)
        if key not in self._built:
            self._built[key] = self._build(storm, number_text, text, anchor)
        return self._built[key]

    def _build(
        self, storm: StormSummary, number_text: str, text: str, anchor: RosterProduct | None
    ) -> Advisory:
        where = f"{self._layer} advisory of {storm.atcf_id}"
        with model_errors(self._source, where):
            number = AdvisoryNumber.parse(number_text)
            named = parse_nhc_local_time(text)
        if anchor is not None and anchor.advisory == number:
            if named is None or abs(named - anchor.issued_at) > ISSUANCE_TOLERANCE:
                warn_drift(
                    self._source,
                    f"{self._layer}: {storm.atcf_id} advisory {number}'s advdate "
                    f"{text!r} is more than an hour from the roster's issuance "
                    f"{anchor.issued_at:%Y-%m-%dT%H:%MZ}; the roster's is kept",
                )
            with model_errors(self._source, where):
                return Advisory(
                    atcf_id=storm.atcf_id,
                    number=number,
                    issued_at=anchor.issued_at,
                    local_text=text,
                    issued_at_source="roster",
                )
        if anchor is not None:
            warn_drift(
                self._source,
                f"{self._layer}: {storm.atcf_id} is at advisory {number}, the roster's "
                f"product at {anchor.advisory}; the layer's advdate dates it",
            )
        with model_errors(self._source, where):
            return Advisory(atcf_id=storm.atcf_id, number=number, issued_at=named, local_text=text)


def parse_cones(
    layer: str,
    collection: Mapping[str, object],
    provenance: Provenance,
    storms: Sequence[StormSummary],
) -> tuple[ConeGeometry, ...]:
    """Parse ``Forecast Cone`` (either service) into one cone per storm and advisory.

    Args:
        layer: The layer name as queried.
        collection: The FeatureCollection.
        provenance: The answer's provenance.
        storms: The roster's storms.

    Returns:
        The cones.
    """
    source = provenance.source_id
    advisories = _Advisories(source, layer)
    cones: list[ConeGeometry] = []
    for feature, fields in _features(collection, layer, source):
        storm = _storm_of(fields, storms, layer)
        basin, number = fields.text("basin"), fields.integer("stormnum")
        stamp, _kind = fields.text("idp_source"), fields.text("stormtype")
        if storm is None or not _same_storm(storm, fields, basin=basin, number=number, layer=layer):
            continue
        _check_name(storm, fields, layer)
        if not stamp.lower().startswith(storm.atcf_id.lower()):
            warn_drift(source, f"{layer}: idp_source does not name {storm.atcf_id}; skipped")
            continue
        advisory = advisories.of(storm, fields, storm.track_cone)
        with model_errors(source, fields.where):
            cones.append(
                ConeGeometry(
                    atcf_id=storm.atcf_id,
                    advisory=advisory,
                    provenance=provenance,
                    forecast_period_h=fields.integer("fcstprd"),
                    geometry=_geometry(feature, fields),
                )
            )
    return tuple(cones)


def parse_track_points(
    layer: str,
    collection: Mapping[str, object],
    provenance: Provenance,
    storms: Sequence[StormSummary],
) -> tuple[TrackPoint, ...]:
    """Parse ``Forecast Points``, timing each point against its advisory's issuance.

    Args:
        layer: The layer name as queried.
        collection: The FeatureCollection.
        provenance: The answer's provenance.
        storms: The roster's storms.

    Returns:
        The forecast points, in the layer's order.

    Raises:
        SourceSchemaError: A point's advisory has no instant to time it against.
    """
    source = provenance.source_id
    advisories = _Advisories(source, layer)
    points: list[TrackPoint] = []
    for feature, fields in _features(collection, layer, source):
        storm = _storm_of(fields, storms, layer)
        basin, number = fields.text("basin"), fields.integer("stormnum")
        if storm is None or not _same_storm(storm, fields, basin=basin, number=number, layer=layer):
            continue
        _check_name(storm, fields, layer)
        advisory = advisories.of(storm, fields, storm.track_cone)
        if advisory.issued_at is None:
            message = f"{fields.where}: the advisory has no instant to time the point against"
            raise SourceSchemaError(source, message)
        with model_errors(source, fields.where):
            points.append(
                TrackPoint(
                    atcf_id=storm.atcf_id,
                    advisory=advisory,
                    provenance=provenance,
                    tau_h=fields.integer("tau"),
                    valid_at=resolve_track_valid_time(fields.text("validtime"), advisory.issued_at),
                    valid_local_text=fields.optional_text("fldatelbl"),
                    position=_geometry(feature, fields),
                    max_wind_kt=fields.optional_integer("maxwind"),
                    gust_kt=fields.optional_integer("gust"),
                    mslp_mb=fields.optional_integer("mslp", sentinel=True),
                    direction_deg=fields.optional_integer("tcdir", sentinel=True),
                    speed_kt=fields.optional_integer("tcspd", sentinel=True),
                    development=fields.text("tcdvlp"),
                    storm_type=fields.text("stormtype"),
                    saffir_simpson=fields.optional_integer("ssnum"),
                    label=fields.text("dvlbl"),
                )
            )
    return tuple(points)


def parse_tracks(
    layer: str,
    collection: Mapping[str, object],
    provenance: Provenance,
    storms: Sequence[StormSummary],
) -> tuple[ForecastTrack, ...]:
    """Parse ``Forecast Track`` into one track line per storm and advisory.

    Args:
        layer: The layer name as queried.
        collection: The FeatureCollection.
        provenance: The answer's provenance.
        storms: The roster's storms.

    Returns:
        The tracks.
    """
    source = provenance.source_id
    advisories = _Advisories(source, layer)
    tracks: list[ForecastTrack] = []
    for feature, fields in _features(collection, layer, source):
        storm = _storm_of(fields, storms, layer)
        if storm is None:
            continue
        advisory = advisories.of(storm, fields, storm.track_cone)
        with model_errors(source, fields.where):
            tracks.append(
                ForecastTrack(
                    atcf_id=storm.atcf_id,
                    advisory=advisory,
                    provenance=provenance,
                    geometry=_geometry(feature, fields),
                )
            )
    return tuple(tracks)


def parse_watch_warnings(
    layer: str,
    collection: Mapping[str, object],
    provenance: Provenance,
    storms: Sequence[StormSummary],
) -> tuple[WatchWarningSegment, ...]:
    """Parse ``Watch-Warning`` into coastal segments, unknown ``tcww`` codes kept.

    Args:
        layer: The layer name as queried.
        collection: The FeatureCollection.
        provenance: The answer's provenance.
        storms: The roster's storms.

    Returns:
        The segments.
    """
    source = provenance.source_id
    advisories = _Advisories(source, layer)
    segments: list[WatchWarningSegment] = []
    for feature, fields in _features(collection, layer, source):
        storm = _storm_of(fields, storms, layer)
        code = fields.text("tcww")
        if storm is None:
            continue
        _check_name(storm, fields, layer)
        advisory = advisories.of(storm, fields, storm.track_cone)
        with model_errors(source, fields.where):
            segments.append(
                WatchWarningSegment(
                    atcf_id=storm.atcf_id,
                    advisory=advisory,
                    provenance=provenance,
                    tcww=WatchWarningType.parse(code),
                    geometry=_geometry(feature, fields),
                )
            )
    return tuple(segments)


def parse_wind_radii(
    layer: str,
    collection: Mapping[str, object],
    provenance: Provenance,
    storms: Sequence[StormSummary],
) -> tuple[WindRadii, ...]:
    """Parse ``Forecast Wind Radii`` or ``Advisory Wind Field`` (tau 0).

    ``AT1 Advisory Wind Field`` lacks ``idp_source``; no parser reads it.

    Args:
        layer: The layer name as queried.
        collection: The FeatureCollection.
        provenance: The answer's provenance.
        storms: The roster's storms.

    Returns:
        The radii polygons.
    """
    source = provenance.source_id
    is_field = base_layer_name(layer) == ADVISORY_WIND_FIELD
    radii: list[WindRadii] = []
    for feature, fields in _features(collection, layer, source):
        storm = _storm_of(fields, storms, layer)
        storm_id = fields.text("stormid").upper()
        if storm is None:
            continue
        if storm_id != storm.atcf_id:
            warn_drift(source, f"{layer} names {storm_id} in slot {storm.slot}; skipped")
            continue
        threshold = fields.integer("radii")
        if threshold not in _RADII_THRESHOLDS:
            message = f"{fields.where}: 'radii' is not 34, 50, or 64"
            raise SourceSchemaError(source, message)
        with model_errors(source, fields.where):
            radii.append(
                WindRadii.model_validate(
                    {
                        "atcf_id": storm.atcf_id,
                        "advisory": AdvisoryNumber.parse(fields.code("advnum")),
                        "provenance": provenance,
                        "threshold_kt": threshold,
                        "tau_h": 0 if is_field else fields.integer("tau"),
                        "valid_at": parse_synoptic_time(fields.code("validtime")),
                        "synoptic_at": parse_synoptic_time(fields.code("synoptime")),
                        "ne_extent_nmi": fields.integer("ne"),
                        "se_extent_nmi": fields.integer("se"),
                        "sw_extent_nmi": fields.integer("sw"),
                        "nw_extent_nmi": fields.integer("nw"),
                        "is_advisory_field": is_field,
                        "geometry": _geometry(feature, fields),
                    }
                )
            )
    return tuple(radii)


def parse_arrival_times(
    layer: str,
    collection: Mapping[str, object],
    provenance: Provenance,
    storms: Sequence[StormSummary],
) -> tuple[ArrivalTimeProduct, ...]:
    """Parse an arrival-time layer into label-only products (issue #11's fallback).

    The lines carry a weekday and a clock time with no date and no zone, so each line
    keeps its label only (``origin`` ``map_layer``); the KMZ (Step 3) resolves them. The
    advisory comes from ``folderpath`` and its issuance from the roster's arrival-time
    object; when the roster names another advisory, the storm's product is skipped with
    a Source-drift warning, because nothing else dates it.

    Args:
        layer: The layer name as queried.
        collection: The FeatureCollection.
        provenance: The answer's provenance.
        storms: The roster's storms.

    Returns:
        One product per storm.

    Raises:
        SourceSchemaError: A ``folderpath`` names no advisory, or a storm's lines name
            different advisories.
    """
    source = provenance.source_id
    kind: Literal["earliest_reasonable", "most_likely"] = (
        "earliest_reasonable" if base_layer_name(layer) == EARLIEST_ARRIVAL else "most_likely"
    )
    lines: dict[str, list[ArrivalTimeLine]] = {}
    numbers: dict[str, AdvisoryNumber] = {}
    for feature, fields in _features(collection, layer, source):
        storm = _storm_of(fields, storms, layer)
        label, folder = fields.optional_text("arrival_time"), fields.text("folderpath")
        subset = fields.text("idp_subset")
        if storm is None:
            continue
        found = _FOLDER_ADVISORY.search(folder)
        if found is None:
            message = f"{fields.where}: 'folderpath' names no storm and advisory"
            raise SourceSchemaError(source, message)
        if found["atcf"].upper() != storm.atcf_id or subset.upper() != storm.atcf_id:
            warn_drift(source, f"{layer} names another storm in slot {storm.slot}; skipped")
            continue
        with model_errors(source, fields.where):
            number = AdvisoryNumber.parse(found["number"])
            line = ArrivalTimeLine.resolve(label, _geometry(feature, fields), origin="map_layer")
        if numbers.setdefault(storm.atcf_id, number) != number:
            message = f"{layer}: {storm.atcf_id}'s lines name more than one advisory"
            raise SourceSchemaError(source, message)
        lines.setdefault(storm.atcf_id, []).append(line)
    products: list[ArrivalTimeProduct] = []
    for storm in storms:
        if storm.atcf_id not in lines:
            continue
        number = numbers[storm.atcf_id]
        anchor = (
            storm.earliest_arrival_kmz
            if kind == "earliest_reasonable"
            else storm.most_likely_arrival_kmz
        )
        if anchor is None or anchor.advisory != number:
            listed = anchor.advisory if anchor else "none"
            warn_drift(
                source,
                f"{layer}: {storm.atcf_id}'s lines are advisory {number}, the roster's "
                f"arrival-time product {listed}; nothing dates them, so they are skipped",
            )
            continue
        with model_errors(source, f"{layer} product of {storm.atcf_id}"):
            products.append(
                ArrivalTimeProduct(
                    atcf_id=storm.atcf_id,
                    advisory=Advisory(
                        atcf_id=storm.atcf_id,
                        number=number,
                        issued_at=anchor.issued_at,
                        local_text=None,
                        issued_at_source="roster",
                    ),
                    provenance=provenance,
                    kind=kind,
                    time_zone=None,
                    published_at=None,
                    published_local_text=None,
                    origin="map_layer",
                    lines=tuple(lines[storm.atcf_id]),
                )
            )
    return tuple(products)


def parse_outlook(
    layer: str,
    collection: Mapping[str, object],
    provenance: Provenance,
    storms: Sequence[StormSummary] = (),  # noqa: ARG001 - one signature for every parser
) -> tuple[OutlookArea, ...]:
    """Parse an outlook layer of either tropical service into ``OutlookArea`` values.

    Args:
        layer: The layer name.
        collection: The FeatureCollection.
        provenance: The answer's provenance.
        storms: Unused; outlook areas belong to no storm.

    Returns:
        The areas.
    """
    source = provenance.source_id
    kind = OUTLOOK_KINDS[layer]
    areas: list[OutlookArea] = []
    for feature, fields in _features(collection, layer, source):
        chances = [fields.optional_text(name) for name in ("prob2day", "prob7day")]
        risks = [fields.optional_text(name) for name in ("risk2day", "risk7day")]
        with model_errors(source, fields.where):
            two_day, seven_day = (parse_percent(text) if text else None for text in chances)
            risk_two, risk_seven = (OutlookRisk.parse(text) if text else None for text in risks)
            areas.append(
                OutlookArea(
                    kind=kind,
                    basin=fields.text("basin"),
                    chance_2day_pct=two_day,
                    chance_7day_pct=seven_day,
                    risk_2day=risk_two,
                    risk_7day=risk_seven,
                    outlook_stamp=fields.text("idp_source"),
                    issued_at=from_epoch_ms(fields.integer("idp_filedate")),
                    geometry=_geometry(feature, fields),
                    provenance=provenance,
                )
            )
    return tuple(areas)


def parse_wind_probabilities(
    layer: str, collection: Mapping[str, object], provenance: Provenance
) -> WindProbabilityProduct | None:
    """Parse a ``Probabilistic Winds`` layer into the snapshot's product (issue #12).

    Args:
        layer: ``Probabilistic Winds 34 kts``, ``50 kts``, or ``64 kts``.
        collection: The FeatureCollection.
        provenance: The answer's provenance.

    Returns:
        The product, with ``synoptic_at`` from ``idp_source``; ``None`` for an empty layer.

    Raises:
        SourceSchemaError: The bands name more than one synoptic time, or another threshold.
    """
    source = provenance.source_id
    threshold = WIND_PROBABILITY_THRESHOLDS[layer]
    bands: list[WindProbabilityBand] = []
    stamps: set[str] = set()
    for feature, fields in _features(collection, layer, source):
        label = fields.text("percentage")
        stamps.add(fields.text("idp_source"))
        with model_errors(source, fields.where):
            bands.append(WindProbabilityBand.from_label(label, _geometry(feature, fields)))
    if not bands:
        return None
    if len(stamps) != 1:
        message = f"{layer}: the bands name {len(stamps)} synoptic times, not one"
        raise SourceSchemaError(source, message)
    stamp = stamps.pop()
    if f"wsp{threshold}knt" not in stamp.lower():
        message = f"{layer}: idp_source names another threshold"
        raise SourceSchemaError(source, message)
    with model_errors(source, layer):
        return WindProbabilityProduct(
            threshold_kt=threshold,
            synoptic_at=parse_synoptic_time(stamp),
            bands=tuple(bands),
            provenance=provenance,
        )


def check_wind_probability_issuance(
    products: Iterable[WindProbabilityProduct], storms: Iterable[StormSummary]
) -> None:
    """Warn of Source drift where a roster storm lists another wind-probability issuance.

    Args:
        products: The snapshot's wind-probability products.
        storms: The roster's storms.
    """
    for product in products:
        for storm in storms:
            listed = storm.wind_speed_probabilities_issued_at
            if listed is not None and listed != product.synoptic_at:
                warn_drift(
                    product.provenance.source_id,
                    f"Probabilistic Winds {product.threshold_kt} kts is for "
                    f"{product.synoptic_at:%Y-%m-%dT%H:%MZ}; the roster lists "
                    f"{listed:%Y-%m-%dT%H:%MZ} under {storm.atcf_id}",
                )


def parse_breakpoints(
    layer: str,
    collection: Mapping[str, object],
    provenance: Provenance,
    storms: Sequence[StormSummary] = (),  # noqa: ARG001 - one signature for every parser
) -> tuple[Breakpoint, ...]:
    """Parse ``Watch_Warning_Breakpoints``, positioned from ``lat`` and ``lon``.

    The features' geometry is null, so the position comes from the fields. ``objectid``
    orders the catalogue along the coast, and ``idp_filedate`` dates it.

    Args:
        layer: The layer name.
        collection: The FeatureCollection.
        provenance: The answer's provenance.
        storms: Unused; breakpoints belong to no storm.

    Returns:
        The breakpoints.
    """
    source = provenance.source_id
    breakpoints: list[Breakpoint] = []
    for _feature, fields in _features(collection, layer, source):
        latitude, longitude = fields.number("lat"), fields.number("lon")
        with model_errors(source, fields.where):
            breakpoints.append(
                Breakpoint(
                    name=fields.text("name"),
                    state=fields.optional_text("state"),
                    country=fields.text("country"),
                    position=Geometry(type="Point", coordinates=(longitude, latitude), crs=WGS84),
                    objectid=fields.integer("objectid"),
                    loaded_at=from_epoch_ms(fields.integer("idp_filedate")),
                    provenance=provenance,
                )
            )
    return tuple(breakpoints)


def parse_display_layer(
    layer: str, collection: Mapping[str, object], provenance: Provenance
) -> DisplayLayer:
    """Keep a display layer as the FeatureCollection received.

    Args:
        layer: The layer name.
        collection: The FeatureCollection.
        provenance: The answer's provenance.

    Returns:
        The display layer, empty or not.
    """
    with model_errors(provenance.source_id, layer):
        return DisplayLayer.model_validate(
            {
                "layer_name": layer,
                "feature_collection": dict(collection),
                "crs": WGS84,
                "provenance": provenance,
            }
        )


type StormParser = Callable[
    [str, Mapping[str, object], Provenance, Sequence[StormSummary]], tuple[DomainModel, ...]
]
STORM_PARSERS: Final[Mapping[str, StormParser]] = MappingProxyType(
    {
        FORECAST_CONE: parse_cones,
        FORECAST_POINTS: parse_track_points,
        FORECAST_TRACK: parse_tracks,
        WATCH_WARNING: parse_watch_warnings,
        FORECAST_WIND_RADII: parse_wind_radii,
        ADVISORY_WIND_FIELD: parse_wind_radii,
        EARLIEST_ARRIVAL: parse_arrival_times,
        MOST_LIKELY_ARRIVAL: parse_arrival_times,
    }
)


def parse_layer(
    layer: str,
    collection: Mapping[str, object],
    provenance: Provenance,
    storms: Sequence[StormSummary] = (),
) -> tuple[DomainModel, ...]:
    """Parse any layer v2 reads, by its name in either tropical service or the others.

    Args:
        layer: The layer name as queried.
        collection: The FeatureCollection.
        provenance: The answer's provenance.
        storms: The roster's storms, which storm products join.

    Returns:
        The records: none for an empty layer, except a display layer, which is kept.

    Raises:
        ValueError: v2 does not parse this layer (the register: not used, or ``doctor``'s).
    """
    base = base_layer_name(layer)
    if base in STORM_PARSERS:
        return STORM_PARSERS[base](layer, collection, provenance, storms)
    if base in OUTLOOK_KINDS:
        return parse_outlook(layer, collection, provenance)
    if base in WIND_PROBABILITY_THRESHOLDS:
        product = parse_wind_probabilities(layer, collection, provenance)
        return (product,) if product else ()
    if base == BREAKPOINT_LAYER:
        return parse_breakpoints(layer, collection, provenance)
    if base in DISPLAY_LAYERS:
        return (parse_display_layer(layer, collection, provenance),)
    message = f"v2 parses no layer named {layer!r}"
    raise ValueError(message)


# Fetching ------------------------------------------------------------------------------


def _layer_names(catalog: MapCatalog, base: str, storms: Sequence[StormSummary]) -> list[str]:
    if catalog.provenance.source_id == TROPICAL_WEATHER.source_id:
        return [f"{storm.slot} {base}" for storm in storms]
    return [base]


async def _query(fetcher: Fetcher, catalog: MapCatalog, name: str) -> LayerQuery:
    service = SERVICES[catalog.provenance.source_id]
    return await query(fetcher, service, resolve(catalog, name), page_size=catalog.max_record_count)


async def _query_all(
    fetcher: Fetcher, catalog: MapCatalog, names: Sequence[str]
) -> list[LayerQuery]:
    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(_query(fetcher, catalog, name)) for name in names]
    return [task.result() for task in tasks]


def _merged(result: LayerQuery) -> tuple[Mapping[str, object], FetchResult]:
    """One FeatureCollection of every page, with the first page's answer as provenance."""
    if len(result.pages) == 1:
        return result.pages[0].collection, result.pages[0].result
    return {"type": "FeatureCollection", "features": list(result.features)}, result.pages[0].result


def _responses(results: Iterable[LayerQuery]) -> tuple[FetchResult, ...]:
    return tuple(response for result in results for response in result.responses)


async def fetch_storm_products(
    fetcher: Fetcher, catalog: MapCatalog, storms: Sequence[StormSummary]
) -> SourceResult[tuple[StormProducts, ...]]:
    """Query every storm-product layer once and assemble each roster storm's products.

    Args:
        fetcher: The run's fetcher.
        catalog: This run's catalog of the summary service (or the slot service).
        storms: The roster's storms; none means no request.

    Returns:
        One ``StormProducts`` per roster storm, and the answers.

    Raises:
        SourceSchemaError: A storm has more than one cone or track.
    """
    if not storms:
        return SourceResult((), ())
    names = [(base, name) for base in STORM_LAYERS for name in _layer_names(catalog, base, storms)]
    results = await _query_all(fetcher, catalog, [name for _, name in names])
    records: list[DomainModel] = []
    for (base, name), result in zip(names, results, strict=True):
        for page in result.pages:
            records.extend(
                STORM_PARSERS[base](name, page.collection, page.result.provenance(), storms)
            )
    return SourceResult(assemble_storm_products(storms, records), _responses(results))


def assemble_storm_products(
    storms: Sequence[StormSummary], records: Iterable[DomainModel]
) -> tuple[StormProducts, ...]:
    """Group parsed storm records by storm, one ``StormProducts`` per roster storm.

    Args:
        storms: The roster's storms.
        records: Cones, points, tracks, segments, radii, and arrival products.

    Returns:
        The products, in the roster's order.

    Raises:
        SourceSchemaError: A storm has more than one cone or track.
    """
    grouped: dict[str, list[DomainModel]] = {storm.atcf_id: [] for storm in storms}
    for record in records:
        grouped[cast("ConeGeometry", record).atcf_id].append(record)
    assembled: list[StormProducts] = []
    for storm in storms:
        mine = grouped[storm.atcf_id]
        cones = [r for r in mine if isinstance(r, ConeGeometry)]
        tracks = [r for r in mine if isinstance(r, ForecastTrack)]
        for kind, found in (("cone", cones), ("track", tracks)):
            if len(found) > 1:
                source = found[0].provenance.source_id
                message = f"{storm.atcf_id} has {len(found)} forecast {kind}s, not one"
                raise SourceSchemaError(source, message)
        assembled.append(
            StormProducts(
                summary=storm,
                cone=cones[0] if cones else None,
                track_points=tuple(r for r in mine if isinstance(r, TrackPoint)),
                track=tracks[0] if tracks else None,
                watch_warnings=tuple(r for r in mine if isinstance(r, WatchWarningSegment)),
                wind_radii=tuple(r for r in mine if isinstance(r, WindRadii)),
                arrival_times=tuple(r for r in mine if isinstance(r, ArrivalTimeProduct)),
            )
        )
    return tuple(assembled)


async def fetch_storm_display_layers(
    fetcher: Fetcher, catalog: MapCatalog, storms: Sequence[StormSummary]
) -> SourceResult[tuple[DisplayLayer, ...]]:
    """Query the past points, past track, and wind swath, kept as received.

    Args:
        fetcher: The run's fetcher.
        catalog: This run's catalog of the summary service (or the slot service).
        storms: The roster's storms; none means no request.

    Returns:
        One display layer per layer queried, and the answers.
    """
    if not storms:
        return SourceResult((), ())
    names = [name for base in STORM_DISPLAY_LAYERS for name in _layer_names(catalog, base, storms)]
    results = await _query_all(fetcher, catalog, names)
    layers: list[DisplayLayer] = []
    for name, result in zip(names, results, strict=True):
        collection, answer = _merged(result)
        layers.append(parse_display_layer(name, collection, answer.provenance()))
    return SourceResult(tuple(layers), _responses(results))


async def fetch_outlook(
    fetcher: Fetcher, catalog: MapCatalog
) -> SourceResult[tuple[OutlookArea, ...]]:
    """Query the four outlook layers of either tropical service.

    Args:
        fetcher: The run's fetcher.
        catalog: This run's catalog.

    Returns:
        The outlook areas and the answers.
    """
    results = await _query_all(fetcher, catalog, list(OUTLOOK_KINDS))
    areas = [
        area
        for name, result in zip(OUTLOOK_KINDS, results, strict=True)
        for page in result.pages
        for area in parse_outlook(name, page.collection, page.result.provenance())
    ]
    return SourceResult(tuple(areas), _responses(results))


async def fetch_wind_probabilities(
    fetcher: Fetcher, catalog: MapCatalog, storms: Sequence[StormSummary]
) -> SourceResult[tuple[WindProbabilityProduct, ...]]:
    """Query the three probabilistic-wind layers: the snapshot's products (issue #12).

    Args:
        fetcher: The run's fetcher.
        catalog: This run's catalog.
        storms: The roster's storms, whose listed issuance each product is checked against.

    Returns:
        One product per non-empty threshold, and the answers.
    """
    results = await _query_all(fetcher, catalog, list(WIND_PROBABILITY_THRESHOLDS))
    products: list[WindProbabilityProduct] = []
    for name, result in zip(WIND_PROBABILITY_THRESHOLDS, results, strict=True):
        collection, answer = _merged(result)
        product = parse_wind_probabilities(name, collection, answer.provenance())
        if product is not None:
            products.append(product)
    check_wind_probability_issuance(products, storms)
    return SourceResult(tuple(products), _responses(results))


async def fetch_breakpoints(
    fetcher: Fetcher, catalog: MapCatalog
) -> SourceResult[tuple[Breakpoint, ...]]:
    """Query ``Watch_Warning_Breakpoints`` (``StormSurge_Communication_Points`` is unused).

    Args:
        fetcher: The run's fetcher.
        catalog: This run's catalog of ``NHC_Breakpoints``.

    Returns:
        The breakpoints and the answers.
    """
    (result,) = await _query_all(fetcher, catalog, [BREAKPOINT_LAYER])
    breakpoints = [
        point
        for page in result.pages
        for point in parse_breakpoints(BREAKPOINT_LAYER, page.collection, page.result.provenance())
    ]
    return SourceResult(tuple(breakpoints), result.responses)


async def fetch_peak_surge(
    fetcher: Fetcher, catalog: MapCatalog
) -> SourceResult[tuple[DisplayLayer, ...]]:
    """Query the peak-surge ``Points``, ``Lines``, and ``Polygons``, kept as received.

    Args:
        fetcher: The run's fetcher.
        catalog: This run's catalog of ``NHC_PeakStormSurge``.

    Returns:
        Three display layers, empty or not, and the answers.
    """
    results = await _query_all(fetcher, catalog, list(PEAK_SURGE_LAYERS))
    layers: list[DisplayLayer] = []
    for name, result in zip(PEAK_SURGE_LAYERS, results, strict=True):
        collection, answer = _merged(result)
        layers.append(parse_display_layer(name, collection, answer.provenance()))
    return SourceResult(tuple(layers), _responses(results))


def parse_cone_advisories(
    rows: Sequence[Mapping[str, object]],
    source: SourceId = TROPICAL_SUMMARY.source_id,
) -> Mapping[StormSlot, AdvisoryNumber]:
    """Parse the summary service's cone-layer attributes into one advisory per slot.

    Args:
        rows: Each cone feature's attributes (``binnumber`` and ``advisnum``).
        source: The map service's source id, for errors.

    Returns:
        Each active slot's advisory number.

    Raises:
        SourceSchemaError: A feature lacks ``binnumber`` or ``advisnum``, names an invalid
            slot or advisory number, or two features in the same slot disagree.
    """
    advisories: dict[StormSlot, AdvisoryNumber] = {}
    for index, row in enumerate(rows):
        where = f"{FORECAST_CONE} attribute {index}"
        fields = Fields(row, CONE_ADVISORIES_READ, source_id=source, where=where)
        slot_text = fields.text("binnumber").strip().upper()
        if not _SLOT_NAME.fullmatch(slot_text):
            message = f"{where}: 'binnumber' {slot_text!r} is not a storm slot"
            raise SourceSchemaError(source, message)
        slot = cast("StormSlot", slot_text)
        with model_errors(source, where):
            number = AdvisoryNumber.parse(fields.code("advisnum"))
        if advisories.setdefault(slot, number) != number:
            message = f"{FORECAST_CONE}: slot {slot} names more than one advisory"
            raise SourceSchemaError(source, message)
    return MappingProxyType(advisories)


async def fetch_cone_advisories(
    fetcher: Fetcher, catalog: MapCatalog
) -> SourceResult[Mapping[StormSlot, AdvisoryNumber]]:
    """Query the summary service's ``Forecast Cone`` attributes without geometry.

    Args:
        fetcher: The run's fetcher.
        catalog: A catalog of ``NHC_tropical_weather_summary``.

    Returns:
        Each slot's advisory number and the answer.
    """
    source = catalog.provenance.source_id
    service = SERVICES[source]
    layer = resolve(catalog, FORECAST_CONE)
    result = await attributes(fetcher, service, layer, CONE_ADVISORY_FIELDS)
    return SourceResult(parse_cone_advisories(result.records, source), result.responses)
