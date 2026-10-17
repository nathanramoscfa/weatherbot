# src/weatherbot/sources/catalogs.py
"""The display catalogs ``doctor`` checks: storm-surge risk and the two WMS overlays.

``nhc-map-surge-risk`` is the ``StormSurgeRisk`` ArcGIS service. v2 draws its
``Atlantic / US East and Gulf Coast / Category {n} / Image`` rasters, so the client reads
the catalog once and resolves the five images by group path, because names repeat in
every region. ``overlay-radar`` and ``overlay-satellite`` are nowCOAST WMS 1.3.0 services;
their ``GetCapabilities`` documents, parsed with ``defusedxml``, must name the layers the
map loads, each with a ``time`` dimension whose default is the latest image. No tile and
no image is fetched here.
"""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from urllib.parse import urlencode

from weatherbot.models import (
    MapCatalog,
    MapLayer,
    OverlayCatalog,
    OverlayLayer,
    Provenance,
    SourceId,
)
from weatherbot.sources.arcgis import SURGE_RISK, fetch_catalog, resolve
from weatherbot.sources.errors import SourceSchemaError
from weatherbot.sources.fields import model_errors
from weatherbot.sources.http import Fetcher, SourceResult
from weatherbot.sources.markup import XmlElement, children, local_name, parse_xml, text_of

SURGE_RISK_CATEGORIES: Final = range(1, 6)
SURGE_RISK_IMAGE: Final = "Atlantic / US East and Gulf Coast / Category {n} / Image"

WMS_NAMESPACE: Final = "http://www.opengis.net/wms"
WMS_VERSION: Final = "1.3.0"
NOWCOAST_ROOT: Final = "https://nowcoast.noaa.gov/geoserver"
MAX_CAPABILITIES_BYTES: Final = 2 * 1024 * 1024


@dataclass(frozen=True)
class OverlayService:
    """A nowCOAST WMS workspace and the layers the map loads from it."""

    source_id: SourceId
    workspace: str
    layers: tuple[str, ...]

    @property
    def url(self) -> str:
        """The ``GetCapabilities`` URL (the recorder's parameters, in its order)."""
        query = urlencode({"service": "WMS", "version": WMS_VERSION, "request": "GetCapabilities"})
        return f"{NOWCOAST_ROOT}/{self.workspace}/ows?{query}"


RADAR: Final = OverlayService("overlay-radar", "weather_radar", ("conus_base_reflectivity_mosaic",))
SATELLITE: Final = OverlayService(
    "overlay-satellite", "satellite", ("goes_longwave_imagery", "goes_visible_imagery")
)
OVERLAYS: Final = (RADAR, SATELLITE)


def surge_risk_images(catalog: MapCatalog) -> Mapping[int, MapLayer]:
    """Resolve the US East and Gulf Coast surge-risk image of each category, by group path.

    Args:
        catalog: This run's ``StormSurgeRisk`` catalog.

    Returns:
        The image layer per category, 1 to 5; ids valid for this run only.

    Raises:
        SourceSchemaError: A category's image is missing or ambiguous.
    """
    return {n: resolve(catalog, SURGE_RISK_IMAGE.format(n=n)) for n in SURGE_RISK_CATEGORIES}


async def fetch_surge_risk_catalog(fetcher: Fetcher) -> SourceResult[MapCatalog]:
    """Read the ``StormSurgeRisk`` catalog and confirm the five images resolve.

    Args:
        fetcher: The run's fetcher.

    Returns:
        The catalog and its answer.
    """
    result = await fetch_catalog(fetcher, SURGE_RISK)
    surge_risk_images(result.records)
    return result


def _time_default(layer: XmlElement) -> datetime | None:
    for dimension in children(layer, "Dimension", WMS_NAMESPACE):
        if dimension.get("name") == "time":
            default = dimension.get("default")
            try:
                return datetime.fromisoformat(default) if default else None
            except ValueError:
                return None
    return None


def parse_capabilities(
    body: bytes, provenance: Provenance, service: OverlayService
) -> OverlayCatalog:
    """Parse a WMS 1.3.0 ``GetCapabilities`` document into an ``OverlayCatalog``.

    Args:
        body: The document.
        provenance: The answer's provenance.
        service: The workspace and the layers the map loads.

    Returns:
        Every named layer with its ``time`` default.

    Raises:
        SourceSchemaError: The document is not WMS 1.3.0 capabilities, declares a DTD, or
            lacks a layer the map loads or that layer's ``time`` default.
    """
    source = provenance.source_id
    what = f"the {service.workspace} capabilities"
    root = parse_xml(body, source, what)
    if local_name(root) != "WMS_Capabilities" or root.get("version") != WMS_VERSION:
        raise SourceSchemaError(source, f"{what} are not WMS {WMS_VERSION} capabilities")
    layers: dict[str, OverlayLayer] = {}
    for layer in root.iter(f"{{{WMS_NAMESPACE}}}Layer"):
        names = children(layer, "Name", WMS_NAMESPACE)
        if len(names) == 1 and text_of(names[0]):
            name = text_of(names[0])
            with model_errors(source, f"{what}, layer {name!r}"):
                layers.setdefault(name, OverlayLayer(name=name, time_default=_time_default(layer)))
    for name in service.layers:
        if name not in layers or layers[name].time_default is None:
            message = f"{what} lack the layer {name!r} or its time default"
            raise SourceSchemaError(source, message)
    with model_errors(source, what):
        return OverlayCatalog(
            service=f"nowcoast/{service.workspace}",
            layers=tuple(layers.values()),
            provenance=provenance,
        )


async def fetch_overlay_catalogs(fetcher: Fetcher) -> SourceResult[tuple[OverlayCatalog, ...]]:
    """Fetch and parse both overlay capabilities documents.

    Args:
        fetcher: The run's fetcher.

    Returns:
        The radar, then the satellite catalog, and the answers.
    """
    async with asyncio.TaskGroup() as group:
        tasks = [
            group.create_task(
                fetcher.get(
                    service.url, source_id=service.source_id, max_bytes=MAX_CAPABILITIES_BYTES
                )
            )
            for service in OVERLAYS
        ]
    results = tuple(task.result() for task in tasks)
    catalogs = tuple(
        parse_capabilities(result.body, result.provenance(), service)
        for result, service in zip(results, OVERLAYS, strict=True)
    )
    return SourceResult(catalogs, results)
