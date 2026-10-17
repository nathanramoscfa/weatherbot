# tests/services/test_locations.py
"""The locations service's checks: names and points, refused without repeating a value."""

import math

import pytest

from check_personal_data import load_landmarks, synthetic_coordinates
from weatherbot.services.locations import LocationError, check_name, check_point


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
