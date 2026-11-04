# tests/cli/test_location_nassau.py
"""The Nassau profile: added via ``--place`` and assessed against replayed Dorian advisory 26."""

import json

import httpx
import respx
from cli_support import CORPUS, directory, recorded_services, run
from source_support import entry

from weatherbot.cli.runtime import EXIT_OK
from weatherbot.engine import assess
from weatherbot.models import AlertLevel, RuleId, Thresholds
from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import LocationRepository
from weatherbot.services.replay import ReplayCorpus
from weatherbot.sources.nominatim import reverse_url, search_url
from weatherbot.sources.nws import points_url


def test_nassau_added_by_place_reads_outside_nws_and_dorian_advisory_26_reads_level_5_hwr() -> None:
    geocode = directory("geocode-nominatim")
    points = directory("nws-points")
    search_item = entry(geocode, "search-nassau.json")
    search_payload = geocode.payload(search_item)
    candidates: object = json.loads(search_payload)
    assert isinstance(candidates, list)
    assert candidates
    first: object = candidates[0]  # pyright: ignore[reportUnknownVariableType] - JSON array
    assert isinstance(first, dict)
    lat = float(str(first["lat"]))  # pyright: ignore[reportUnknownArgumentType] - JSON object
    lon = float(str(first["lon"]))  # pyright: ignore[reportUnknownArgumentType] - JSON object

    points_item = entry(points, "points-nassau.json")
    reverse_item = entry(geocode, "reverse-nassau.json")

    with respx.mock(assert_all_called=True) as router:
        router.get(search_url("Nassau, Bahamas")).mock(
            return_value=httpx.Response(
                200,
                content=search_payload,
                headers={"content-type": "application/json; charset=utf-8"},
            )
        )
        router.get(points_url(lat, lon)).mock(
            return_value=httpx.Response(
                404,
                content=points.payload(points_item),
                headers={"content-type": "application/problem+json"},
            )
        )
        router.get(reverse_url(lat, lon)).mock(
            return_value=httpx.Response(
                200,
                content=geocode.payload(reverse_item),
                headers={"content-type": "application/json; charset=utf-8"},
            )
        )
        ran = run(["locations", "add", "Nassau", "--place", "Nassau, Bahamas"])

    assert ran.exit_code == EXIT_OK

    paths = AppPaths.resolve()
    with open_database(paths) as database:
        location = LocationRepository(database.engine).get("Nassau")

    assert location is not None
    assert location.nws is None
    assert location.country_code == "BS"

    corpus = ReplayCorpus.open(CORPUS)
    snapshot = corpus.snapshot("AL052019", "026")
    assessment = assess(snapshot, location, Thresholds())

    assert assessment.level == AlertLevel.HURRICANE_WARNING
    assert int(assessment.level) == int(AlertLevel.HURRICANE_WARNING)
    assert assessment.rule == RuleId.HURRICANE_WARNING
    assert any(
        ev.product == "watch_warning_segment" and ev.code == "HWR" for ev in assessment.evidence
    )
    # Replay snapshots hold no breakpoint catalogue, so evidence names the segment only
    for product in assessment.official:
        assert product.breakpoints == ()


def test_nassau_added_under_recorded_services_helper() -> None:
    with recorded_services():
        ran = run(["locations", "add", "Nassau", "--place", "Nassau, Bahamas"])
    assert ran.exit_code == EXIT_OK
