# src/weatherbot/sources/nhc_outlook_graphics.py
"""The six NHC outlook maps (register source ``nhc-outlook-graphics``).

``two_{atl,pac,cpac}_{2d0,7d0}.png`` under ``https://www.nhc.noaa.gov/xgtwo/``; the brief's
``two_epac_*`` names answer 404 and are never requested. NHC sends an ``ETag`` and a
``Last-Modified`` and honors a conditional request, so each map is fetched conditionally:
a 304 reuses the stored body. The client checks the PNG signature and reads the size from
the ``IHDR`` chunk, because the maps change size over time; the bytes stay in the
``FetchResult`` for the raw-response cache.
"""

import asyncio
import re
import struct
from typing import Final, Literal

from weatherbot.models import OutlookGraphic, Provenance, SourceId
from weatherbot.sources.errors import SourceSchemaError
from weatherbot.sources.fields import model_errors
from weatherbot.sources.http import Fetcher, SourceResult

SOURCE: Final[SourceId] = "nhc-outlook-graphics"
GRAPHICS_ROOT: Final = "https://www.nhc.noaa.gov/xgtwo"

type Basin = Literal["atl", "pac", "cpac"]
type Horizon = Literal["2d0", "7d0"]
BASINS: Final[tuple[Basin, ...]] = ("atl", "pac", "cpac")
HORIZONS: Final[tuple[Horizon, ...]] = ("2d0", "7d0")

PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
_IHDR_END: Final = 24
MAX_GRAPHIC_BYTES: Final = 2 * 1024 * 1024
_FILE: Final = re.compile(r"/xgtwo/two_(?P<basin>atl|pac|cpac)_(?P<horizon>2d0|7d0)\.png$")


def graphic_url(basin: Basin, horizon: Horizon) -> str:
    """Return a map's URL.

    Args:
        basin: ``atl``, ``pac`` (the Eastern Pacific), or ``cpac``.
        horizon: ``2d0`` or ``7d0``.

    Returns:
        The URL.
    """
    return f"{GRAPHICS_ROOT}/two_{basin}_{horizon}.png"


GRAPHIC_URLS: Final = tuple(graphic_url(basin, horizon) for basin in BASINS for horizon in HORIZONS)


def png_size(body: bytes, source_id: SourceId = SOURCE) -> tuple[int, int]:
    """Return the width and height a PNG's ``IHDR`` chunk states.

    Args:
        body: The PNG bytes.
        source_id: The register id, for errors.

    Returns:
        The width and height in pixels.

    Raises:
        SourceSchemaError: The bytes lack the signature or an ``IHDR`` chunk first, or state
            a zero dimension.
    """
    if len(body) < _IHDR_END or not body.startswith(PNG_SIGNATURE) or body[12:16] != b"IHDR":
        raise SourceSchemaError(source_id, "the outlook map is not a PNG")
    width, height = struct.unpack(">II", body[16:_IHDR_END])
    if width == 0 or height == 0:
        raise SourceSchemaError(source_id, "the outlook map states a zero dimension")
    return width, height


def parse_outlook_graphic(body: bytes, provenance: Provenance) -> OutlookGraphic:
    """Check a map's PNG and record its size; the basin and horizon come from its URL.

    Args:
        body: The PNG bytes (the stored body after a 304).
        provenance: The answer's provenance.

    Returns:
        The graphic.

    Raises:
        SourceSchemaError: The URL is not one of the six maps, or the bytes are not a PNG.
    """
    source = provenance.source_id
    found = _FILE.search(provenance.url)
    if found is None:
        raise SourceSchemaError(source, "the URL is not one of the six outlook maps")
    width, height = png_size(body, source)
    with model_errors(source, "the outlook map"):
        return OutlookGraphic.model_validate(
            {
                "basin": found["basin"],
                "horizon": found["horizon"],
                "width_px": width,
                "height_px": height,
                "provenance": provenance,
            }
        )


async def fetch_outlook_graphics(fetcher: Fetcher) -> SourceResult[tuple[OutlookGraphic, ...]]:
    """Fetch the six maps, each conditionally when the store holds its validators.

    Args:
        fetcher: The run's fetcher.

    Returns:
        The six graphics, Atlantic, Eastern Pacific, then Central Pacific, and the answers.
    """
    async with asyncio.TaskGroup() as group:
        tasks = [
            group.create_task(fetcher.get(url, source_id=SOURCE, max_bytes=MAX_GRAPHIC_BYTES))
            for url in GRAPHIC_URLS
        ]
    results = tuple(task.result() for task in tasks)
    graphics = tuple(parse_outlook_graphic(r.body, r.provenance()) for r in results)
    return SourceResult(graphics, results)
