# tests/services/test_locations.py
"""The locations service: its checks on names and points, and the evacuation toggle.

A bad name or point is refused without repeating a value.
"""

import math
from collections.abc import Iterator
from datetime import timedelta

import pytest
from snapshot_support import LANDMARK_NAME, landmark_location
from source_support import NOW

from check_personal_data import load_landmarks, synthetic_coordinates
from weatherbot.services.config import AppPaths
from weatherbot.services.locations import LocationError, LocationService, check_name, check_point
from weatherbot.services.persistence.database import Database, open_database
from weatherbot.services.persistence.repositories import LocationRepository


@pytest.mark.parametrize("name", ["", " ", "x" * 65, "line\nbreak", "tab\tbed"])
def test_a_bad_name_is_refused(name: str) -> None:
    with pytest.raises(LocationError, match="1 to 64 printable characters"):
        check_name(name)


@pytest.mark.parametrize("name", ["A", "x" * 64, "Parliament Square, Nassau"])
def test_a_good_name_is_kept(name: str) -> None:
    assert check_name(name) == name


def test_a_bad_point_is_refused_and_the_message_never_repeats_it() -> None:
    lat, lon = (float(value) for value in synthetic_coordinates(load_landmarks(), (), seed=8))
    cases = [
        (lat + 180, lon),
        (lat, lon + 360),
        (math.nan, lon),
        (lat, math.inf),
    ]
    for case in cases:
        with pytest.raises(LocationError) as refused:
            check_point(*case)
        message = str(refused.value)
        assert all(f"{value:.4f}" not in message for value in case if math.isfinite(value))
        assert all(str(value) not in message for value in case)


def test_a_good_point_becomes_a_latlon() -> None:
    lat, lon = (float(value) for value in synthetic_coordinates(load_landmarks(), (), seed=8))

    point = check_point(lat, lon)

    assert (point.latitude, point.longitude) == (lat, lon)
    assert str(lat) not in repr(point)


# The evacuation-order toggle ---------------------------------------------------------------


@pytest.fixture
def database() -> Iterator[Database]:
    with open_database(AppPaths.resolve()) as opened:
        LocationRepository(opened.engine).add(landmark_location())
        yield opened


def _service(database: Database, minutes: int) -> LocationService:
    stamp = NOW + timedelta(minutes=minutes)
    return LocationService(database.engine, now=lambda: stamp)


def test_the_toggle_is_set_with_its_instant_and_kept_when_set_again(database: Database) -> None:
    on, changed = _service(database, 0).set_evacuation_order(LANDMARK_NAME, on=True)
    again, unchanged = _service(database, 5).set_evacuation_order(LANDMARK_NAME, on=True)
    off, cleared = _service(database, 10).set_evacuation_order(LANDMARK_NAME, on=False)

    assert (on.evacuation_order_in_effect, on.evacuation_order_set_at, changed) == (True, NOW, True)
    assert (again, unchanged) == (on, False)
    assert off.evacuation_order_in_effect is False
    assert off.evacuation_order_set_at == NOW + timedelta(minutes=10)
    assert cleared is True
    assert _service(database, 0).get(LANDMARK_NAME) == off


def test_the_toggle_of_an_unknown_location_is_a_location_error(database: Database) -> None:
    with pytest.raises(LocationError, match="no location is named 'Nowhere'"):
        _service(database, 0).set_evacuation_order("Nowhere", on=True)
