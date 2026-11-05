# tests/live/test_osm_referer_live.py
"""Live OpenStreetMap single-tile check with loopback Referer and project User-Agent."""

from http import HTTPStatus

import httpx
import pytest

from weatherbot.sources import USER_AGENT

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SINGLE_TILE_URL = "https://tile.openstreetmap.org/3/2/3.png"
LOOPBACK_REFERER = "http://127.0.0.1:8765/"


@pytest.mark.live
@pytest.mark.enable_socket
def test_osm_single_tile_accepts_loopback_referer_and_project_user_agent() -> None:
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": LOOPBACK_REFERER,
    }
    with httpx.Client(timeout=15.0, headers=headers, follow_redirects=True) as client:
        response = client.get(SINGLE_TILE_URL)

    assert response.status_code == HTTPStatus.OK
    assert response.headers.get("content-type", "").startswith("image/png")
    assert response.content.startswith(PNG_SIGNATURE)
