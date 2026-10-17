# tests/sources/test_catalogs.py
"""Tests of the surge-risk and WMS overlay catalogs over their recorded captures."""

import httpx
import pytest
import respx
from source_support import Quiet, entry, recorded, recorded_result, serve

from weatherbot.models import MapCatalog, Provenance
from weatherbot.sources import catalogs
from weatherbot.sources.arcgis import SURGE_RISK, parse_catalog
from weatherbot.sources.errors import SourceSchemaError


def surge_risk_catalog() -> MapCatalog:
    directory = recorded("nhc-map-surge-risk")
    return parse_catalog(recorded_result(directory, entry(directory, "catalog.json")), SURGE_RISK)


def capabilities(service: catalogs.OverlayService) -> tuple[bytes, Provenance]:
    directory = recorded(service.source_id)
    result = recorded_result(directory, entry(directory, "capabilities.xml"))
    return result.body, result.provenance()


def test_the_five_us_east_and_gulf_images_resolve_by_group_path() -> None:
    images = catalogs.surge_risk_images(surge_risk_catalog())

    assert sorted(images) == list(catalogs.SURGE_RISK_CATEGORIES)
    for category, layer in images.items():
        assert layer.name == "Image"
        assert layer.group_path == ("Atlantic", "US East and Gulf Coast", f"Category {category}")


def test_a_missing_category_image_is_a_schema_error() -> None:
    catalog = surge_risk_catalog()
    kept = tuple(
        layer
        for layer in catalog.layers
        if not (layer.name == "Image" and layer.group_path[-1:] == ("Category 5",))
    )

    with pytest.raises(SourceSchemaError, match="Category 5 / Image"):
        catalogs.surge_risk_images(catalog.model_copy(update={"layers": kept}))


@pytest.mark.parametrize("service", catalogs.OVERLAYS, ids=lambda s: s.source_id)
def test_each_overlay_names_the_layers_the_map_loads_with_their_time_defaults(
    service: catalogs.OverlayService,
) -> None:
    catalog = catalogs.parse_capabilities(*capabilities(service), service)

    by_name = {layer.name: layer for layer in catalog.layers}
    for name in service.layers:
        default = by_name[name].time_default
        assert default is not None
        assert default.utcoffset() is not None
    assert catalog.service == f"nowcoast/{service.workspace}"


def test_a_missing_overlay_layer_is_a_schema_error() -> None:
    body, provenance = capabilities(catalogs.RADAR)
    renamed = body.replace(b"<Name>conus_base_reflectivity_mosaic</Name>", b"<Name>other</Name>")

    with pytest.raises(SourceSchemaError, match="conus_base_reflectivity_mosaic"):
        catalogs.parse_capabilities(renamed, provenance, catalogs.RADAR)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (b'version="1.3.0"', b'version="1.1.1"', "not WMS 1.3.0"),
        (b"<WMS_Capabilities", b'<!DOCTYPE x [<!ENTITY e "x">]><WMS_Capabilities', "DTD"),
    ],
    ids=["version", "entity"],
)
def test_capabilities_are_read_strictly(old: bytes, new: bytes, message: str) -> None:
    body, provenance = capabilities(catalogs.SATELLITE)

    with pytest.raises(SourceSchemaError, match=message):
        catalogs.parse_capabilities(body.replace(old, new, 1), provenance, catalogs.SATELLITE)


@pytest.mark.anyio
async def test_fetch_reads_both_overlays_and_the_surge_risk_catalog() -> None:
    with respx.mock(assert_all_called=False) as router:
        for source in ("overlay-radar", "overlay-satellite", "nhc-map-surge-risk"):
            serve(router, recorded(source))
        async with httpx.AsyncClient() as client:
            fetcher = Quiet().fetcher(client)
            overlays = await catalogs.fetch_overlay_catalogs(fetcher)
            surge = await catalogs.fetch_surge_risk_catalog(fetcher)

    assert [r.url for r in overlays.responses] == [s.url for s in catalogs.OVERLAYS]
    assert [c.provenance.source_id for c in overlays.records] == [
        "overlay-radar",
        "overlay-satellite",
    ]
    assert surge.records.provenance.source_id == "nhc-map-surge-risk"
