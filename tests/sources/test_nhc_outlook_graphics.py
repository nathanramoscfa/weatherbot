# tests/sources/test_nhc_outlook_graphics.py
"""Tests of the outlook-map client: every recorded map, conditional requests, and PNG checks."""

import httpx
import pytest
import respx
from fixture_support import CaptureDirectory, capture_directories
from source_support import NOW, Quiet, recorded_result

from weatherbot.models import Provenance
from weatherbot.sources import nhc_outlook_graphics as graphics
from weatherbot.sources.errors import SourceSchemaError

HARVESTED_MAPS = 6
NOT_MODIFIED = 304
CAPTURES = [
    (directory, item)
    for directory in capture_directories()
    if directory.source == graphics.SOURCE
    for item in directory.entries
]


def _label(capture: tuple[CaptureDirectory, dict[str, object]]) -> str:
    return f"{capture[0].day}/{capture[1]['file']}"


@pytest.mark.parametrize("capture", CAPTURES, ids=[_label(c) for c in CAPTURES])
def test_every_recorded_and_harvested_map_parses_to_its_recorded_size(
    capture: tuple[CaptureDirectory, dict[str, object]],
) -> None:
    directory, item = capture
    result = recorded_result(directory, item)

    graphic = graphics.parse_outlook_graphic(result.body, result.provenance())

    assert f"PNG {graphic.width_px}x{graphic.height_px}" in str(item["notes"])
    assert str(item["file"]) == f"two_{graphic.basin}_{graphic.horizon}.png"


def test_the_recorded_set_holds_the_six_live_maps_and_the_harvested_ones() -> None:
    live = {str(item["file"]) for directory, item in CAPTURES if directory.is_live()}
    harvested = [item for directory, item in CAPTURES if not directory.is_live()]
    assert live == {url.rsplit("/", 1)[1] for url in graphics.GRAPHIC_URLS}
    assert len(harvested) == HARVESTED_MAPS


def test_the_six_urls_never_name_the_epac_files() -> None:
    assert len(graphics.GRAPHIC_URLS) == len(graphics.BASINS) * len(graphics.HORIZONS)
    assert not any("two_epac" in url for url in graphics.GRAPHIC_URLS)


def _provenance(url: str) -> Provenance:
    return Provenance(
        source_id="nhc-outlook-graphics", url=url, status=200, fetched_at=NOW, sha256="0" * 64
    )


@pytest.mark.parametrize(
    ("body", "url", "message"),
    [
        (b"GIF89a" + bytes(30), graphics.GRAPHIC_URLS[0], "not a PNG"),
        (graphics.PNG_SIGNATURE + bytes(4) + b"IHDR" + bytes(8), graphics.GRAPHIC_URLS[0], "zero"),
        (graphics.PNG_SIGNATURE, "https://www.nhc.noaa.gov/xgtwo/two_epac_2d0.png", "six"),
    ],
    ids=["not-png", "zero-size", "epac-url"],
)
def test_a_bad_png_or_url_is_a_schema_error(body: bytes, url: str, message: str) -> None:
    with pytest.raises(SourceSchemaError, match=message):
        graphics.parse_outlook_graphic(body, _provenance(url))


def _live_map(name: str) -> tuple[bytes, dict[str, str]]:
    directory, item = next((d, i) for d, i in CAPTURES if d.is_live() and i["file"] == name)
    result = recorded_result(directory, item)
    return result.body, dict(result.headers)


@pytest.mark.anyio
async def test_a_304_reuses_the_stored_body() -> None:
    body, headers = _live_map("two_atl_7d0.png")
    etag = headers["etag"]
    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if request.headers.get("if-none-match") == etag:
            return httpx.Response(304, headers={"etag": etag})
        content_type = {"content-type": "image/png"}
        return httpx.Response(200, content=body, headers={**content_type, "etag": etag})

    with respx.mock(assert_all_called=False) as router:
        router.route(host="www.nhc.noaa.gov").mock(side_effect=answer)
        async with httpx.AsyncClient() as client:
            fetcher = Quiet().fetcher(client)
            first = await graphics.fetch_outlook_graphics(fetcher)
            second = await graphics.fetch_outlook_graphics(fetcher)

    assert all(not r.not_modified for r in first.responses)
    assert all(r.not_modified and r.status == NOT_MODIFIED for r in second.responses)
    assert all(r.body == body for r in second.responses)
    assert [g.provenance.not_modified for g in second.records] == [True] * len(second.records)
    assert second.records[1].width_px == first.records[1].width_px
    assert all(request.headers.get("if-none-match") == etag for request in sent[6:])
