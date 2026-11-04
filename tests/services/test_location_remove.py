# tests/services/test_location_remove.py
"""Tests for ``LocationService.remove`` and ``LocationRepository.remove``."""

import hashlib
import threading
import time

import httpx
import pytest
import respx
from cli_support import quiet_fetcher
from source_support import NOW, entry, recorded
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from check_personal_data import load_landmarks
from weatherbot.models import SourceId
from weatherbot.services.config import AppPaths
from weatherbot.services.locations import (
    LocationBusyError,
    LocationError,
    LocationService,
)
from weatherbot.services.locks import ProcessLock
from weatherbot.services.network import Network
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.raw_cache import RawResponseCache
from weatherbot.services.persistence.tables import (
    AiCallRow,
    RawResponseRow,
    ResponseBodyRow,
)
from weatherbot.sources import nominatim, nws
from weatherbot.sources.http import FetchResult

pytestmark = pytest.mark.anyio

GEOJSON = {"content-type": "application/geo+json"}
JSON = {"content-type": "application/json; charset=utf-8"}


def _point(key: str) -> tuple[float, float]:
    found = next(item for item in load_landmarks() if item.key == key)
    return float(found.lat), float(found.lon)


def _payload(source: SourceId, name: str) -> bytes:
    directory = recorded(source)
    return directory.payload(entry(directory, name))


async def test_remove_deletes_location_raw_responses_and_unreferenced_bodies() -> None:
    paths = AppPaths.resolve()
    miami_lat, miami_lon = _point("miami-dade")
    nassau_lat, nassau_lon = _point("nassau")

    with open_database(paths, now=lambda: NOW) as database:
        service = LocationService(
            database.engine,
            paths=paths,
            network=Network(make_fetcher=quiet_fetcher),
            now=lambda: NOW,
        )
        with respx.mock(assert_all_called=True) as router:
            router.get(nws.points_url(miami_lat, miami_lon)).mock(
                return_value=httpx.Response(
                    200, content=_payload("nws-points", "points-miami-dade.json"), headers=GEOJSON
                )
            )
            router.get(nominatim.reverse_url(miami_lat, miami_lon)).mock(
                return_value=httpx.Response(
                    200,
                    content=_payload("geocode-nominatim", "reverse-miami-dade.json"),
                    headers=JSON,
                )
            )
            router.get(nws.points_url(nassau_lat, nassau_lon)).mock(
                return_value=httpx.Response(
                    404,
                    content=_payload("nws-points", "points-nassau.json"),
                    headers={"content-type": "application/problem+json"},
                )
            )
            router.get(nominatim.reverse_url(nassau_lat, nassau_lon)).mock(
                return_value=httpx.Response(
                    200,
                    content=_payload("geocode-nominatim", "reverse-nassau.json"),
                    headers=JSON,
                )
            )
            await service.add("Miami", miami_lat, miami_lon)
            await service.add("Nassau", nassau_lat, nassau_lon)

        # Save an alert response for Miami and a shared body also referenced by another key
        shared_bytes = b'{"shared": true}'
        shared_sha = hashlib.sha256(shared_bytes).hexdigest()
        cache = RawResponseCache(database.engine)
        for key in ("alerts <Miami>", "CurrentStorms.json"):
            cache.save_fetch(
                FetchResult(
                    source_id="nws-alerts-point" if "Miami" in key else "nhc-current-storms",
                    url="https://api.weather.gov/alerts/active",
                    status=200,
                    body=shared_bytes,
                    headers={"content-type": "application/json"},
                    fetched_at=NOW,
                    sha256=shared_sha,
                ),
                "nws-alerts-point" if "Miami" in key else "nhc-current-storms",
                key,
            )

        with Session(database.engine) as session:
            session.add(
                AiCallRow(
                    kind="briefing",
                    location_name="Miami",
                    model="claude-sonnet-5-5",
                    prompt_version="v1",
                    day="2026-10-12",
                    started_at=NOW,
                    finished_at=NOW,
                    status="ok",
                    input_tokens=100,
                    output_tokens=50,
                    ceiling_micro_usd=1000,
                    cost_micro_usd=500,
                    allowance_micro_usd=0,
                    prices_as_of="2026-10-12",
                )
            )
            session.commit()

        service.remove("Miami")

        assert service.get("Miami") is None
        assert service.get("Nassau") is not None

        with Session(database.engine) as session:
            keys = list(session.scalars(select(RawResponseRow.product_key)))
            assert not any(k.endswith("<Miami>") for k in keys)
            assert any(k.endswith("<Nassau>") for k in keys)
            # Shared body referenced by nhc-current-storms stays; Miami's unique bodies are gone
            remaining_shas = set(session.scalars(select(ResponseBodyRow.sha256)))
            assert shared_sha in remaining_shas
            miami_points_sha = hashlib.sha256(
                _payload("nws-points", "points-miami-dade.json")
            ).hexdigest()
            assert miami_points_sha not in remaining_shas
            # AI ledger row is retained so today's spend never drops
            assert session.scalar(select(func.count()).select_from(AiCallRow)) == 1

        with pytest.raises(LocationError):
            service.remove("Miami")


async def test_remove_waits_for_running_cycle_and_raises_location_busy_when_lock_held() -> None:
    paths = AppPaths.resolve()
    nassau_lat, nassau_lon = _point("nassau")

    with open_database(paths, now=lambda: NOW) as database:
        service = LocationService(
            database.engine,
            paths=paths,
            cycle_lock_wait_seconds=0.05,
            network=Network(make_fetcher=quiet_fetcher),
            now=lambda: NOW,
        )
        with respx.mock(assert_all_called=True) as router:
            router.get(nws.points_url(nassau_lat, nassau_lon)).mock(
                return_value=httpx.Response(
                    404,
                    content=_payload("nws-points", "points-nassau.json"),
                    headers={"content-type": "application/problem+json"},
                )
            )
            router.get(nominatim.reverse_url(nassau_lat, nassau_lon)).mock(
                return_value=httpx.Response(
                    200,
                    content=_payload("geocode-nominatim", "reverse-nassau.json"),
                    headers=JSON,
                )
            )
            await service.add("Nassau", nassau_lat, nassau_lon)

        # 1. When cycle.lock is held past cycle_lock_wait_seconds, raises LocationBusyError
        lock = ProcessLock(paths.cycle_lock_path)
        lock.acquire(0.0)
        try:
            with pytest.raises(LocationBusyError, match="another cycle is running"):
                service.remove("Nassau")
        finally:
            lock.release()
        assert service.get("Nassau") is not None

        # 2. When cycle.lock is released while remove waits, remove waits and then succeeds
        patient_service = LocationService(
            database.engine,
            paths=paths,
            cycle_lock_wait_seconds=2.0,
            network=Network(make_fetcher=quiet_fetcher),
            now=lambda: NOW,
        )
        acquired = threading.Event()
        released = threading.Event()

        def _hold_briefly() -> None:
            holder_lock = ProcessLock(paths.cycle_lock_path)
            holder_lock.acquire(0.0)
            try:
                acquired.set()
                time.sleep(0.15)
            finally:
                holder_lock.release()
            released.set()

        holder = threading.Thread(target=_hold_briefly)
        holder.start()
        acquired.wait(timeout=1.0)
        patient_service.remove("Nassau")
        holder.join(timeout=1.0)
        assert released.is_set()
        assert patient_service.get("Nassau") is None
