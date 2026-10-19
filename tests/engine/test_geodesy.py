# tests/engine/test_geodesy.py
"""The figure each CRS implies, its strict WKT reader, and geodesic distance and bearing."""

import math

import pytest
from engine_support import corpus_wkts, landmark
from pyproj import CRS, Transformer

from weatherbot.engine.geodesy import (
    WGS84_INVERSE_FLATTENING,
    WGS84_SEMI_MAJOR_M,
    distance_km,
    figure_of,
    initial_bearing_deg,
)
from weatherbot.engine.geometry import place
from weatherbot.models import WGS84, Crs

SPHERE_RADIUS_M = 6371200.0
WGS84_LANDMARKS_KM = 297.53
SPHERE_LANDMARKS_KM = 297.14


def sphere_wkt() -> str:
    """Return the corpus's one projection WKT."""
    (wkt,) = corpus_wkts()
    return wkt


def native(wkt: str) -> Crs:
    return Crs.native({"wkt": wkt, "datum": None})


def landmark_positions() -> tuple[tuple[float, float], tuple[float, float]]:
    miami, nassau = landmark("miami-dade"), landmark("nassau")
    return (miami.longitude, miami.latitude), (nassau.longitude, nassau.latitude)


def test_epsg_4326_is_the_wgs84_ellipsoid() -> None:
    figure = figure_of(WGS84)
    expected = CRS("EPSG:4326").get_geod()
    assert expected is not None

    assert (figure.name, figure.semi_major_m, figure.inverse_flattening) == (
        "WGS 84",
        WGS84_SEMI_MAJOR_M,
        WGS84_INVERSE_FLATTENING,
    )
    assert not figure.is_sphere
    assert (figure.geod.a, figure.geod.b, figure.geod.f) == pytest.approx(
        (expected.a, expected.b, expected.f), rel=1e-15
    )


def test_every_corpus_wkt_is_the_archive_sphere_as_pyproj_reads_it() -> None:
    wkts = corpus_wkts()
    assert wkts

    for wkt in wkts:
        figure = figure_of(native(wkt))
        assert figure.semi_major_m == SPHERE_RADIUS_M
        assert figure.inverse_flattening == 0.0
        assert figure.is_sphere
        assert figure.geod == CRS.from_wkt(wkt).get_geod()


@pytest.mark.parametrize("version", ["WKT2_2019", "WKT1_GDAL", "WKT1_ESRI"])
def test_pyproj_s_own_wkt_of_both_figures_parses(version: str) -> None:
    wgs84 = figure_of(native(CRS("EPSG:4326").to_wkt(version)))
    sphere = figure_of(native(CRS.from_wkt(sphere_wkt()).to_wkt(version)))

    assert (wgs84.semi_major_m, wgs84.inverse_flattening) == (
        WGS84_SEMI_MAJOR_M,
        pytest.approx(WGS84_INVERSE_FLATTENING, rel=1e-12),
    )
    assert (sphere.semi_major_m, sphere.inverse_flattening) == (SPHERE_RADIUS_M, 0.0)


def test_figures_are_cached_by_crs() -> None:
    assert figure_of(native(sphere_wkt())) is figure_of(native(sphere_wkt()))
    assert figure_of(WGS84) is figure_of(Crs(name="EPSG:4326"))


def refused(wkt: str) -> str:
    """Return the message with which the reader refuses a WKT."""
    with pytest.raises(ValueError, match=r"^WKT rule: ") as error:
        figure_of(native(wkt))
    return str(error.value)


@pytest.mark.parametrize("version", ["WKT1_GDAL", "WKT2_2019"])
def test_the_reader_refuses_a_projected_crs(version: str) -> None:
    assert "projected CRS" in refused(CRS("EPSG:3857").to_wkt(version))


SPHEROID = 'SPHEROID["Sphere",6371200.0,0.0]'
DEGREE = 'UNIT["Degree",0.0174532925199433]'


@pytest.mark.parametrize(
    ("old", "new", "rule"),
    [
        (f'DATUM["D_Sphere",{SPHEROID}],', "", "exactly one spheroid"),
        (SPHEROID, f'{SPHEROID},SPHEROID["Other",6378137.0,0.0]', "exactly one spheroid"),
        (DEGREE, 'UNIT["Grad",0.0157079632679]', "the degree"),
        ('PRIMEM["Greenwich",0.0]', 'PRIMEM["Paris",2.33722917]', "Greenwich"),
        (f",{DEGREE}", "", "angular unit"),
        ("GEOGCS[", "GEOCCS[", "GEOGCS or GEOGCRS"),
        ("6371200.0,0.0]", "6371200.0]", "missing a number"),
        ('["Sphere",', "[1.0,", "a name, a positive axis"),
        (SPHEROID, "", "not well-formed"),
        ("433]]", "433]", "not well-formed"),
        ("433]]", "433]]]", "not well-formed"),
        ("GEOGCS[", "GEOGCS[=", "not well-formed"),
        (",PRIMEM", ",,PRIMEM", "not well-formed"),
        ('["GCS_Sphere"', "[GCS_Sphere GCS", "not well-formed"),
    ],
    ids=[
        "no-spheroid",
        "two-spheroids",
        "gradians",
        "paris-meridian",
        "no-angular-unit",
        "geocentric",
        "spheroid-without-flattening",
        "spheroid-without-name",
        "empty-datum",
        "unterminated",
        "trailing-bracket",
        "stray-character",
        "empty-argument",
        "two-words",
    ],
)
def test_the_reader_refuses_by_rule_and_never_echoes_the_wkt(old: str, new: str, rule: str) -> None:
    wkt = sphere_wkt()
    assert old in wkt

    message = refused(wkt.replace(old, new, 1))

    assert rule in message
    assert "6371200" not in message
    assert "Sphere" not in message


def test_a_spheroid_length_unit_other_than_the_metre_is_refused() -> None:
    wkt = (
        CRS("EPSG:4326")
        .to_wkt("WKT2_2019")
        .replace('LENGTHUNIT["metre",1]', 'LENGTHUNIT["foot",0.3048]')
    )

    assert "the metre" in refused(wkt)


def test_the_landmarks_are_farther_apart_on_wgs84_than_on_the_sphere() -> None:
    miami, nassau = landmark_positions()

    wgs84 = distance_km(miami, nassau, figure_of(WGS84))
    sphere = distance_km(miami, nassau, figure_of(native(sphere_wkt())))

    assert wgs84 == pytest.approx(WGS84_LANDMARKS_KM, abs=0.01)
    assert sphere == pytest.approx(SPHERE_LANDMARKS_KM, abs=0.01)


def test_bearings_lie_in_range_and_the_back_azimuth_is_reciprocal_on_the_sphere() -> None:
    miami, nassau = landmark_positions()
    sphere = figure_of(native(sphere_wkt()))

    out = initial_bearing_deg(miami, nassau, sphere)
    back = initial_bearing_deg(nassau, miami, sphere)
    _, arriving_back, _ = sphere.geod.inv(*miami, *nassau)

    assert 0.0 <= out < 360.0  # noqa: PLR2004 - a full turn
    assert 0.0 <= back < 360.0  # noqa: PLR2004 - a full turn
    # The bearing home from Nassau is the forward geodesic's direction at Nassau, reversed.
    assert back == pytest.approx(float(arriving_back) % 360.0, abs=1e-9)
    assert math.cos(math.radians(back - out)) < 0.0


def test_a_bearing_that_rounds_to_a_full_turn_reads_zero() -> None:
    miami, _ = landmark_positions()
    sphere = figure_of(native(sphere_wkt()))
    # One unit in the last place west of a meridian, 60 degrees north: the azimuth is a
    # negative number smaller than half a unit in the last place of a full turn.
    north = (math.nextafter(miami[0], -math.inf), miami[1] + 60.0)
    azimuth, _, _ = sphere.geod.inv(*miami, *north)
    assert float(azimuth) < 0.0
    assert float(azimuth) % 360.0 == 360.0  # noqa: PLR2004 - the rounding this guards

    assert initial_bearing_deg(miami, north, sphere) == 0.0


def test_proj_offers_only_a_ballpark_that_leaves_both_landmarks_unchanged() -> None:
    crs = native(sphere_wkt())
    transformer = Transformer.from_crs("EPSG:4326", CRS.from_wkt(sphere_wkt()), always_xy=True)

    assert "Ballpark geographic offset" in transformer.description
    assert transformer.accuracy == -1
    for key in ("miami-dade", "nassau"):
        point = landmark(key)
        expected = (point.longitude, point.latitude)
        assert transformer.transform(*expected) == expected
        assert place(point, crs) == expected
        assert place(point, WGS84) == expected


def test_place_refuses_a_projected_crs() -> None:
    with pytest.raises(ValueError, match="projected CRS"):
        place(landmark("nassau"), native(CRS("EPSG:3857").to_wkt("WKT1_GDAL")))
