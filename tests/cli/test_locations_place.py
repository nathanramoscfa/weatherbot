# tests/cli/test_locations_place.py
"""Tests for ``weatherbot locations add NAME --place TEXT [--pick N]``."""

import json
import re

import httpx
from cli_support import directory, parse, recorded_services, run
from source_support import entry

from weatherbot.cli.documents import LocationsDocument
from weatherbot.cli.runtime import EXIT_FAILED, EXIT_OK, EXIT_USAGE
from weatherbot.services.locations import NOMINATIM_SEARCH_ATTRIBUTION
from weatherbot.sources.nominatim import search_url

DECIMAL_COORD = re.compile(r"-?\d{1,3}\.\d{3,}")


def test_locations_add_place_single_candidate_adds_and_prints_attribution() -> None:
    with recorded_services():
        ran = run(["locations", "add", "Nassau", "--place", "Nassau, Bahamas"])

    assert ran.exit_code == EXIT_OK
    assert "Added 'Nassau': outside NWS coverage" in ran.stdout
    assert NOMINATIM_SEARCH_ATTRIBUTION in ran.stdout
    assert not DECIMAL_COORD.search(ran.stdout)


def test_locations_add_place_multiple_candidates_lists_names_and_pick_selects() -> None:
    geocode = directory("geocode-nominatim")
    miami_items: object = json.loads(geocode.payload(entry(geocode, "search-miami.json")))
    nassau_items: object = json.loads(geocode.payload(entry(geocode, "search-nassau.json")))
    assert isinstance(miami_items, list)
    assert isinstance(nassau_items, list)
    two_candidates = json.dumps([miami_items[0], nassau_items[0]]).encode("utf-8")

    with recorded_services(
        overrides={
            search_url("Miami, Florida"): httpx.Response(
                200,
                content=two_candidates,
                headers={"content-type": "application/json; charset=utf-8"},
            )
        }
    ):
        listed = run(["locations", "add", "Home", "--place", "Miami, Florida"])
        assert listed.exit_code == EXIT_USAGE
        assert "1." in listed.stdout
        assert "2." in listed.stdout
        assert NOMINATIM_SEARCH_ATTRIBUTION in listed.stdout
        assert "--pick" in listed.stderr
        assert not DECIMAL_COORD.search(listed.stdout)
        assert not DECIMAL_COORD.search(listed.stderr)

        bad_pick = run(["locations", "add", "Home", "--place", "Miami, Florida", "--pick", "99"])
        assert bad_pick.exit_code == EXIT_USAGE

        picked = run(["locations", "add", "Home", "--place", "Miami, Florida", "--pick", "1"])
        assert picked.exit_code == EXIT_OK
        assert "Added 'Home': NWS MFL, zones FLZ173 and FLC086" in picked.stdout
        listed_json = run(["locations", "list", "--json"])
        doc = parse(listed_json, LocationsDocument)
        assert any(loc.name == "Home" for loc in doc.data.locations)


def test_locations_add_place_zero_candidates_exits_failed_and_refuses_mixed_flags() -> None:
    with recorded_services():
        none_found = run(
            ["locations", "add", "Nowhere", "--place", "weatherbot-nonexistent-place-query"]
        )
        assert none_found.exit_code == EXIT_FAILED
        assert "no place matched that search" in none_found.stderr
        assert "weatherbot-nonexistent-place-query" not in none_found.stderr

        both = run(
            [
                "locations",
                "add",
                "Mixed",
                "--place",
                "Nassau, Bahamas",
                "--lat",
                "25.0",
                "--lon",
                "-77.0",
            ]
        )
        assert both.exit_code == EXIT_USAGE

        neither = run(["locations", "add", "Empty"])
        assert neither.exit_code == EXIT_USAGE

        pick_without_place = run(
            ["locations", "add", "PickOnly", "--lat", "25.0", "--lon", "-77.0", "--pick", "1"]
        )
        assert pick_without_place.exit_code == EXIT_USAGE
