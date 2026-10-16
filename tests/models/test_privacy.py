# tests/models/test_privacy.py
"""No ``repr`` or validation error of a model exposes a location's coordinates.

The coordinates come from ``synthetic_coordinates()`` at run time, never from a literal.
"""

import re

import pytest
from model_samples import location, provenance, summary
from pydantic import ValidationError

from check_personal_data import load_landmarks, synthetic_coordinates
from weatherbot.models import WGS84, Geometry, LatLon, Location, Provenance

DECIMAL_COORDINATE = re.compile(r"\d+\.\d{3,}")


@pytest.fixture
def coordinates() -> tuple[str, str]:
    """A synthetic latitude and longitude, far from every landmark."""
    return synthetic_coordinates(load_landmarks(), ())


def leaks(text: str, coordinates: tuple[str, str]) -> bool:
    lat, lon = coordinates
    renderings = {lat, lon, str(float(lat)), str(float(lon)), lat.lstrip("-"), lon.lstrip("-")}
    return any(value in text for value in renderings) or bool(DECIMAL_COORDINATE.search(text))


def synthetic_location(coordinates: tuple[str, str]) -> Location:
    lat, lon = (float(value) for value in coordinates)
    square = (
        (lon - 0.01, lat - 0.01),
        (lon + 0.01, lat - 0.01),
        (lon + 0.01, lat + 0.01),
        (lon - 0.01, lat - 0.01),
    )
    return location().model_copy(
        update={
            "point": LatLon(latitude=lat, longitude=lon),
            "polygon": Geometry(type="Polygon", coordinates=(square,), crs=WGS84),
            "geocoding": synthetic_provenance(coordinates),
        }
    )


def synthetic_provenance(coordinates: tuple[str, str]) -> Provenance:
    lat, lon = coordinates
    return provenance("nws-points").model_copy(
        update={"url": f"https://api.weather.gov/points/{lat},{lon}"}
    )


def test_the_synthetic_pair_would_be_caught_if_shown(coordinates: tuple[str, str]) -> None:
    lat, lon = coordinates
    assert leaks(f"{lat},{lon}", coordinates)
    assert leaks(repr(float(lat)), coordinates)


def test_a_location_repr_holds_no_coordinate(coordinates: tuple[str, str]) -> None:
    place = synthetic_location(coordinates)

    assert place.point.latitude == float(coordinates[0])
    for text in (repr(place), str(place), repr(place.point), repr(place.polygon)):
        assert not leaks(text, coordinates)


def test_a_provenance_repr_holds_no_url(coordinates: tuple[str, str]) -> None:
    record = synthetic_provenance(coordinates)

    assert coordinates[0] in record.url
    assert not leaks(repr(record), coordinates)
    assert not leaks(str(record), coordinates)
    assert "url" not in repr(record)


def test_a_validation_error_never_repeats_its_input(coordinates: tuple[str, str]) -> None:
    place = synthetic_location(coordinates)
    document = place.model_dump()

    with pytest.raises(ValidationError) as bad_name:
        Location.model_validate({**document, "name": "", "point": place.point})
    with pytest.raises(ValidationError) as bad_shape:
        Location.model_validate(
            {
                **document,
                "point": place.point,
                "polygon": Geometry(type="Point", coordinates=(0.0, 0.0), crs=WGS84),
            }
        )
    with pytest.raises(ValidationError) as bad_extra:
        Location.model_validate_json(place.model_dump_json()[:-1] + ', "extra": 1}')

    for error in (bad_name, bad_shape, bad_extra):
        assert not leaks(str(error.value), coordinates)


def test_the_storm_centre_is_official_data_and_not_hidden() -> None:
    # Only the operator's coordinates are private; a storm's position is NHC's product.
    assert "latitude=" in repr(summary())
