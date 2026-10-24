# src/weatherbot/sources/arcgis.py
"""The ArcGIS REST client every NHC map service shares (``docs/DATA_SOURCES.md``).

A run reads each service's catalog (``<service>/MapServer?f=json``) once into a
``MapCatalog`` and resolves each layer it needs by exact name, or by group path where
names repeat (``StormSurgeRisk``). Layer ids shift between reads, so an id is used within
its run only and never stored. A query sends the register's shared parameters; a
truncated answer (``exceededTransferLimit``) is paged by ``objectid`` until a page arrives
complete. The ``/layers?f=json`` document (2.3 MB for the tropical service) is read by
``doctor`` and the tests only, never per fetch.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, cast
from urllib.parse import urlencode

from weatherbot.models import MapCatalog, MapLayer, SourceId
from weatherbot.sources.errors import SourceHttpError, SourceSchemaError
from weatherbot.sources.fields import as_mapping, as_sequence, model_errors, parse_document
from weatherbot.sources.http import Fetcher, FetchResult, SourceResult

MAP_ROOT: Final = "https://mapservices.weather.noaa.gov/tropical/rest/services/tropical"

# The register's shared query parameters ("Shared query parameters").
QUERY_PARAMETERS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "where": "1=1",
        "outFields": "*",
        "outSR": "4326",
        "f": "geojson",
        "geometryPrecision": "5",
    }
)
COUNT_PARAMETERS: Final[Mapping[str, str]] = MappingProxyType(
    {"where": "1=1", "returnCountOnly": "true", "f": "json"}
)
ATTRIBUTE_PARAMETERS: Final[Mapping[str, str]] = MappingProxyType(
    {"where": "1=1", "returnGeometry": "false", "f": "json"}
)
PAGE_ORDER: Final = "objectid"
MAX_PAGES: Final = 100
GROUP_SEPARATOR: Final = " / "
_ROOT_PARENT: Final = -1


@dataclass(frozen=True)
class MapService:
    """One ArcGIS map service in the register's ``tropical`` folder."""

    source_id: SourceId
    name: str

    @property
    def url(self) -> str:
        """The service's ``MapServer`` URL."""
        return f"{MAP_ROOT}/{self.name}/MapServer"


TROPICAL_WEATHER: Final = MapService("nhc-map-tropical-weather", "NHC_tropical_weather")
TROPICAL_SUMMARY: Final = MapService("nhc-map-tropical-summary", "NHC_tropical_weather_summary")
BREAKPOINTS: Final = MapService("nhc-map-breakpoints", "NHC_Breakpoints")
PEAK_SURGE: Final = MapService("nhc-map-peak-surge", "NHC_PeakStormSurge")
SURGE_RISK: Final = MapService("nhc-map-surge-risk", "StormSurgeRisk")
SERVICES: Final[Mapping[SourceId, MapService]] = MappingProxyType(
    {
        service.source_id: service
        for service in (TROPICAL_WEATHER, TROPICAL_SUMMARY, BREAKPOINTS, PEAK_SURGE, SURGE_RISK)
    }
)


def _refuse_error_object(document: Mapping[str, object], source_id: SourceId, what: str) -> None:
    error = document.get("error")
    if error is None:
        return
    code = cast("dict[str, object]", error).get("code") if isinstance(error, dict) else None
    status = code if isinstance(code, int) and not isinstance(code, bool) else 200
    message = f"{what} returned an ArcGIS error object (code {status})"
    raise SourceHttpError(source_id, message, status=status)


def parse_catalog(result: FetchResult, service: MapService) -> MapCatalog:
    """Parse a ``MapServer?f=json`` catalog into a ``MapCatalog``.

    Args:
        result: The catalog answer.
        service: The service it describes.

    Returns:
        The catalog, each layer with its group path from the service root.

    Raises:
        SourceSchemaError: The catalog lacks its layers or a layer's id, name, or parent.
        SourceHttpError: The answer is an ArcGIS error object.
    """
    source = service.source_id
    what = f"the {service.name} catalog"
    document = as_mapping(parse_document(result.body, source, what), source, what)
    _refuse_error_object(document, source, what)
    rows = [
        as_mapping(row, source, f"a layer of {what}")
        for row in as_sequence(document.get("layers"), source, f"{what}'s layers")
    ]
    by_id: dict[int, Mapping[str, object]] = {}
    for row in rows:
        layer_id = row.get("id")
        if isinstance(layer_id, bool) or not isinstance(layer_id, int):
            raise SourceSchemaError(source, f"a layer of {what} has no integer id")
        by_id[layer_id] = row
    layers: list[MapLayer] = []
    for layer_id, row in by_id.items():
        name, kind = row.get("name"), row.get("type")
        if not isinstance(name, str) or not isinstance(kind, str):
            raise SourceSchemaError(source, f"layer {layer_id} of {what} lacks a name or type")
        geometry = row.get("geometryType")
        with model_errors(source, f"layer {layer_id} of {what}"):
            layers.append(
                MapLayer(
                    id=layer_id,
                    name=name,
                    type=kind,
                    geometry_type=geometry if isinstance(geometry, str) else None,
                    group_path=_group_path(row, by_id, source, what),
                )
            )
    limit = document.get("maxRecordCount")
    with model_errors(source, what):
        return MapCatalog(
            service=f"tropical/{service.name}",
            read_at=result.fetched_at,
            layers=tuple(layers),
            max_record_count=limit
            if isinstance(limit, int) and not isinstance(limit, bool)
            else None,
            provenance=result.provenance(),
        )


def _group_path(
    row: Mapping[str, object],
    by_id: Mapping[int, Mapping[str, object]],
    source: SourceId,
    what: str,
) -> tuple[str, ...]:
    names: list[str] = []
    parent = row.get("parentLayerId")
    seen: set[int] = set()
    while parent != _ROOT_PARENT:
        if not isinstance(parent, int) or parent not in by_id or parent in seen:
            raise SourceSchemaError(source, f"a layer of {what} has an unknown parent")
        seen.add(parent)
        names.append(str(by_id[parent].get("name")))
        parent = by_id[parent].get("parentLayerId")
    return tuple(reversed(names))


async def fetch_catalog(fetcher: Fetcher, service: MapService) -> SourceResult[MapCatalog]:
    """Read a service's catalog; a run reads it once and resolves every layer from it.

    Args:
        fetcher: The run's fetcher.
        service: The service.

    Returns:
        The catalog and its answer.
    """
    result = await fetcher.get(f"{service.url}?f=json", source_id=service.source_id)
    return SourceResult(parse_catalog(result, service), (result,))


def resolve(catalog: MapCatalog, name: str) -> MapLayer:
    """Find the one layer with this exact name, or this group path from the service root.

    Args:
        catalog: The catalog read in this run.
        name: A layer name, or a group path whose parts are joined with `` / ``.

    Returns:
        The layer. Its id is valid for this run only.

    Raises:
        SourceSchemaError: No layer, or more than one, matches.
    """
    if GROUP_SEPARATOR in name:
        found = [
            layer
            for layer in catalog.layers
            if GROUP_SEPARATOR.join((*layer.group_path, layer.name)) == name
        ]
    else:
        found = [layer for layer in catalog.layers if layer.name == name]
    if len(found) != 1:
        message = f"{catalog.service}: {len(found)} layers match {name!r}, not exactly one"
        raise SourceSchemaError(catalog.provenance.source_id, message)
    return found[0]


@dataclass(frozen=True)
class QueryPage:
    """One answer of a layer query and the FeatureCollection it holds."""

    result: FetchResult
    collection: Mapping[str, object]

    @property
    def features(self) -> Sequence[Mapping[str, object]]:
        """The page's features."""
        return cast("Sequence[Mapping[str, object]]", self.collection["features"])


@dataclass(frozen=True)
class LayerQuery:
    """Every page of one layer query: one page unless the service truncated the answer."""

    layer: str
    pages: tuple[QueryPage, ...]

    @property
    def features(self) -> tuple[Mapping[str, object], ...]:
        """Every feature, in page order."""
        return tuple(feature for page in self.pages for feature in page.features)

    @property
    def responses(self) -> tuple[FetchResult, ...]:
        """Every page's answer."""
        return tuple(page.result for page in self.pages)


def feature_collection(result: FetchResult, layer: str) -> Mapping[str, object]:
    """Check a query answer: an ArcGIS error object or anything but a FeatureCollection fails.

    Args:
        result: The answer.
        layer: The layer name, for errors.

    Returns:
        The FeatureCollection, its features each a JSON object.

    Raises:
        SourceHttpError: The answer is an ArcGIS error object.
        SourceSchemaError: The answer is not a GeoJSON FeatureCollection.
    """
    source = result.source_id
    what = f"the query of {layer!r}"
    document = as_mapping(parse_document(result.body, source, what), source, what)
    _refuse_error_object(document, source, what)
    if document.get("type") != "FeatureCollection":
        raise SourceSchemaError(source, f"{what} is not a GeoJSON FeatureCollection")
    for feature in as_sequence(document.get("features"), source, f"{what}'s features"):
        as_mapping(feature, source, f"a feature of {what}")
    return document


def _query_url(service: MapService, layer_id: int, parameters: Mapping[str, str]) -> str:
    return f"{service.url}/{layer_id}/query?{urlencode(parameters, safe='*,')}"


async def query(
    fetcher: Fetcher,
    service: MapService,
    layer: MapLayer,
    *,
    page_size: int | None = None,
) -> LayerQuery:
    """Query a feature layer with the shared parameters, paging a truncated answer.

    A FeatureCollection with ``exceededTransferLimit: true`` is fetched again in pages
    ordered by ``objectid``, from offset 0, until a page arrives without the flag.

    Args:
        fetcher: The run's fetcher.
        service: The service.
        layer: The layer, resolved from this run's catalog.
        page_size: Features per page, the catalog's ``maxRecordCount``; when ``None``,
            the size of the truncated answer.

    Returns:
        The pages.

    Raises:
        SourceSchemaError: Paging did not finish within 100 pages.
    """
    source = service.source_id
    first = await fetcher.get(_query_url(service, layer.id, QUERY_PARAMETERS), source_id=source)
    collection = feature_collection(first, layer.name)
    if not collection.get("exceededTransferLimit"):
        return LayerQuery(layer.name, (QueryPage(first, collection),))
    size = page_size or len(cast("Sequence[object]", collection["features"]))
    if size <= 0:
        raise SourceSchemaError(source, f"{layer.name!r} is truncated with no features")
    pages: list[QueryPage] = []
    for number in range(MAX_PAGES):
        parameters = {
            **QUERY_PARAMETERS,
            "resultOffset": str(number * size),
            "resultRecordCount": str(size),
            "orderByFields": PAGE_ORDER,
        }
        result = await fetcher.get(_query_url(service, layer.id, parameters), source_id=source)
        page = feature_collection(result, layer.name)
        pages.append(QueryPage(result, page))
        if not page.get("exceededTransferLimit"):
            return LayerQuery(layer.name, tuple(pages))
    message = f"{layer.name!r} did not finish paging within {MAX_PAGES} pages"
    raise SourceSchemaError(source, message)


def parse_count(result: FetchResult, layer: str) -> int:
    """Parse a ``returnCountOnly`` answer.

    Args:
        result: The answer.
        layer: The layer name, for errors.

    Returns:
        The count.

    Raises:
        SourceHttpError: The answer is an ArcGIS error object.
        SourceSchemaError: The answer holds no count.
    """
    source = result.source_id
    what = f"the count of {layer!r}"
    document = as_mapping(parse_document(result.body, source, what), source, what)
    _refuse_error_object(document, source, what)
    value = document.get("count")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SourceSchemaError(source, f"{what} holds no count")
    return value


async def count(fetcher: Fetcher, service: MapService, layer: MapLayer) -> SourceResult[int]:
    """Count a layer's features with ``COUNT_PARAMETERS``.

    Args:
        fetcher: The run's fetcher.
        service: The service.
        layer: The layer, resolved from this run's catalog.

    Returns:
        The count and its answer.
    """
    result = await fetcher.get(
        _query_url(service, layer.id, COUNT_PARAMETERS), source_id=service.source_id
    )
    return SourceResult(parse_count(result, layer.name), (result,))


def parse_attributes(result: FetchResult, layer: str) -> tuple[Mapping[str, object], ...]:
    """Parse an attribute-only ``query`` answer (``f=json`` or a recorded ``FeatureCollection``).

    Args:
        result: The answer.
        layer: The layer name, for errors.

    Returns:
        Each feature's attribute mapping, in order.

    Raises:
        SourceHttpError: The answer is an ArcGIS error object.
        SourceSchemaError: The answer has no ``features`` array or a feature lacks attributes.
    """
    source = result.source_id
    what = f"the attributes of {layer!r}"
    document = as_mapping(parse_document(result.body, source, what), source, what)
    _refuse_error_object(document, source, what)
    rows: list[Mapping[str, object]] = []
    for index, item in enumerate(
        as_sequence(document.get("features"), source, f"{what}'s features")
    ):
        feature = as_mapping(item, source, f"feature {index} of {what}")
        raw = feature.get("attributes") if "attributes" in feature else feature.get("properties")
        rows.append(as_mapping(raw, source, f"feature {index} of {what}'s attributes"))
    return tuple(rows)


async def attributes(
    fetcher: Fetcher,
    service: MapService,
    layer: MapLayer,
    fields: Iterable[str],
) -> SourceResult[tuple[Mapping[str, object], ...]]:
    """Query a layer's named attribute fields without geometry (``ATTRIBUTE_PARAMETERS``).

    Args:
        fetcher: The run's fetcher.
        service: The service.
        layer: The layer, resolved from this run's catalog.
        fields: The ``outFields`` attribute names to request.

    Returns:
        The attribute rows and the answer.
    """
    parameters = {
        "where": ATTRIBUTE_PARAMETERS["where"],
        "outFields": ",".join(fields),
        "returnGeometry": ATTRIBUTE_PARAMETERS["returnGeometry"],
        "f": ATTRIBUTE_PARAMETERS["f"],
    }
    result = await fetcher.get(
        _query_url(service, layer.id, parameters), source_id=service.source_id
    )
    return SourceResult(parse_attributes(result, layer.name), (result,))
