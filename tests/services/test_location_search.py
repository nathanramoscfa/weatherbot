# tests/services/test_location_search.py
"""Tests for ``LocationService.search`` and ``SearchCache``."""

from datetime import timedelta

import httpx
import pytest
import respx
from cli_support import quiet_fetcher
from source_support import NOW, entry, recorded
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from weatherbot.services.config import AppPaths
from weatherbot.services.locations import (
    SEARCH_CACHE_MAX_ENTRIES,
    LocationError,
    LocationService,
    SearchCache,
    check_query,
)
from weatherbot.services.network import Network
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.tables import (
    LocationRow,
    OutcomeResponseRow,
    RawResponseRow,
    ResponseBodyRow,
)
from weatherbot.sources import nominatim

pytestmark = pytest.mark.anyio

JSON = {"content-type": "application/json; charset=utf-8"}


def _search_body(name: str = "search-nassau.json") -> bytes:
    directory = recorded("geocode-nominatim")
    return directory.payload(entry(directory, name))


@pytest.mark.parametrize(
    "bad_query",
    ["", "  ", "zz", "z\nz", "x" * 201],
)
def test_check_query_refuses_short_long_or_non_printable_text_without_echoing_it(
    bad_query: str,
) -> None:
    with pytest.raises(LocationError, match="3 to 200 printable characters") as exc_info:
        check_query(bad_query)
    if bad_query.strip():
        assert bad_query.strip() not in str(exc_info.value)


def test_search_cache_bounds_entries_and_expires_after_ttl() -> None:
    clock = [0.0]
    cache = SearchCache(max_entries=2, ttl_seconds=86400.0, monotonic=lambda: clock[0])
    assert cache.get("Nassau") is None

    cache.put("Nassau", ())
    cache.put("Miami", ())
    clock[0] = 3600.0
    assert cache.get("  nassau ") == ()

    # Touching Nassau makes Miami the oldest entry when a third is inserted
    clock[0] = 7200.0
    cache.put("Key West", ())
    assert cache.get("Nassau") == ()
    assert cache.get("Miami") is None

    # Expires at 24h from when Nassau was first stored (t=0.0)
    clock[0] = 86401.0
    assert cache.get("Nassau") is None
    expected_max = 64
    assert expected_max == SEARCH_CACHE_MAX_ENTRIES


async def test_search_repeats_within_a_day_use_memory_cache_and_write_no_database_rows() -> None:
    paths = AppPaths.resolve()
    cache = SearchCache()
    current_time = NOW

    with open_database(paths, now=lambda: current_time) as database:
        service = LocationService(
            database.engine,
            paths=paths,
            network=Network(make_fetcher=quiet_fetcher),
            now=lambda: current_time,
            search_cache=cache,
        )
        with respx.mock(assert_all_called=True) as router:
            route = router.get(nominatim.search_url("Nassau, Bahamas")).mock(
                return_value=httpx.Response(200, content=_search_body(), headers=JSON)
            )
            first = await service.search("Nassau, Bahamas")
            current_time = NOW + timedelta(hours=12)
            second = await service.search("  nassau, bahamas  ")

        assert route.call_count == 1
        assert first == second
        assert len(first) >= 1
        assert first[0].country_code == "bs"

        with Session(database.engine) as session:
            assert session.scalar(select(func.count()).select_from(RawResponseRow)) == 0
            assert session.scalar(select(func.count()).select_from(ResponseBodyRow)) == 0
            assert session.scalar(select(func.count()).select_from(OutcomeResponseRow)) == 0
            assert session.scalar(select(func.count()).select_from(LocationRow)) == 0
