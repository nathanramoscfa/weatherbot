# tests/models/test_times.py
"""The time functions on recorded examples (2026-10-12 capture and the replay corpus)."""

import gzip
import json
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from model_samples import (
    FULL_TEXT,
    INTERMEDIATE_TEXT,
    REPOSITORY_ROOT,
    TROPICAL,
    recorded_arrival_labels,
    recorded_features,
)

from weatherbot.models import (
    NHC_ZONE_OFFSETS,
    from_epoch_ms,
    parse_nhc_local_time,
    parse_synoptic_time,
    resolve_arrival_label,
    resolve_track_valid_time,
)

REPLAY_POINTS = REPOSITORY_ROOT / "tests/fixtures/replay/AL052019/056/points.geojson.gz"
PUBLISHED = datetime(2026, 10, 12, 21, tzinfo=UTC)  # 200 PM MST Mon Oct 12 2026


def properties(name: str) -> list[dict[str, object]]:
    return [cast("dict[str, object]", feature["properties"]) for feature in recorded_features(name)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (INTERMEDIATE_TEXT, datetime(2026, 10, 13, 0, tzinfo=UTC)),
        (FULL_TEXT, PUBLISHED),
        ("500 AM EDT Mon Sep 02 2019", datetime(2019, 9, 2, 9, tzinfo=UTC)),
        ("1100 PM AST Fri Sep 06 2019", datetime(2019, 9, 7, 3, tzinfo=UTC)),
        ("1200 PM HST Sun Aug 09 2026", datetime(2026, 8, 9, 22, tzinfo=UTC)),
        ("1200 AM UTC Sun Aug 09 2026", datetime(2026, 8, 9, 0, tzinfo=UTC)),
    ],
)
def test_nhc_local_time_parses(text: str, expected: datetime) -> None:
    assert parse_nhc_local_time(text) == expected


def test_every_recorded_advdate_parses() -> None:
    texts = {cast("str", p["advdate"]) for p in properties("query-ep5-forecast-points.geojson")}
    replay = json.loads(gzip.decompress(REPLAY_POINTS.read_bytes()))
    texts |= {feature["properties"]["ADVDATE"] for feature in replay["features"]}

    assert texts == {INTERMEDIATE_TEXT, "500 AM AST Sat Sep 07 2019"}
    assert all(parse_nhc_local_time(text) is not None for text in texts)


def test_the_zone_table_is_the_one_nhc_uses() -> None:
    hours = {name: offset / timedelta(hours=1) for name, offset in NHC_ZONE_OFFSETS.items()}

    assert hours == {
        "AST": -4, "EDT": -4, "EST": -5, "CDT": -5, "CST": -6, "MDT": -6,
        "MST": -7, "PDT": -7, "PST": -8, "HST": -10, "UTC": 0, "GMT": 0,
    }  # fmt: skip


@pytest.mark.parametrize("zone", ["CEST", "ChST", "SST", "XYZ"])
def test_an_abbreviation_outside_the_table_yields_no_instant(zone: str) -> None:
    assert parse_nhc_local_time(f"500 PM {zone} Mon Oct 12 2026") is None


@pytest.mark.parametrize(
    "text",
    ["500 PM MST Tue Oct 12 2026", "500 PM MST Mon Okt 12 2026", "5 PM MST Mon Oct 12 2026", ""],
)
def test_malformed_local_time_is_an_error(text: str) -> None:
    with pytest.raises(ValueError, match=r"NHC local time|month|weekday"):
        parse_nhc_local_time(text)


def test_every_recorded_validtime_resolves_against_its_advisory() -> None:
    anchor = parse_nhc_local_time(INTERMEDIATE_TEXT)
    assert anchor is not None
    points = properties("query-ep5-forecast-points.geojson")

    resolved = [resolve_track_valid_time(cast("str", p["validtime"]), anchor) for p in points]

    # tau 0 is the 21:00 position (12/2100, before the 00:00 anchor); later taus count
    # from the 18:00 synoptic time.
    synoptic = datetime(2026, 10, 12, 18, tzinfo=UTC)
    assert resolved[0] == datetime(2026, 10, 12, 21, tzinfo=UTC)
    assert resolved[1:] == [synoptic + timedelta(hours=cast("int", p["tau"])) for p in points[1:]]


def test_validtime_after_an_issuance_on_the_31st_lands_in_the_next_month() -> None:
    anchor = datetime(2026, 10, 31, 21, tzinfo=UTC)

    assert resolve_track_valid_time("01/1800", anchor) == datetime(2026, 11, 1, 18, tzinfo=UTC)
    assert resolve_track_valid_time("31/1800", anchor) == datetime(2026, 10, 31, 18, tzinfo=UTC)


@pytest.mark.parametrize("text", ["15/1200", "1/1200", "12-2100", "12/2500"])
def test_validtime_outside_the_window_or_malformed_is_an_error(text: str) -> None:
    with pytest.raises(ValueError, match=r"valid time|instants|hour"):
        resolve_track_valid_time(text, datetime(2026, 10, 1, 21, tzinfo=UTC))


def test_recorded_synoptic_stamps_parse() -> None:
    radii = properties("query-ep5-forecast-wind-radii.geojson")
    stamps = {
        cast("str", p["idp_source"]) for p in properties("query-probabilistic-winds-34-kts.geojson")
    }

    assert stamps == {"2026101218_wsp34knt120hr_5km"}
    assert parse_synoptic_time(stamps.pop()) == datetime(2026, 10, 12, 18, tzinfo=UTC)
    assert {parse_synoptic_time(cast("str", p["synoptime"])) for p in radii} == {
        datetime(2026, 10, 12, 18, tzinfo=UTC)
    }
    assert parse_synoptic_time(cast("str", radii[0]["validtime"])) == datetime(
        2026, 10, 13, 21, tzinfo=UTC
    )


@pytest.mark.parametrize("text", ["gtwo_areas_202610122308", "20261012", "2026101299"])
def test_a_non_synoptic_stamp_is_an_error(text: str) -> None:
    with pytest.raises(ValueError, match="synoptic"):
        parse_synoptic_time(text)


def test_recorded_epoch_milliseconds_parse_exactly() -> None:
    cone = properties("query-ep5-forecast-cone.geojson")[0]

    assert from_epoch_ms(cast("int", cone["idp_filedate"])) == datetime(
        2026, 10, 13, 0, 2, 25, tzinfo=UTC
    )
    assert from_epoch_ms(cast("int", cone["idp_ingestdate"])) == datetime(
        2026, 10, 13, 0, 2, 35, tzinfo=UTC
    )
    assert from_epoch_ms(1) == datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=1)


@pytest.mark.parametrize("value", [True, 1.5, "1791849745000"])
def test_epoch_milliseconds_must_be_an_integer(value: object) -> None:
    with pytest.raises(TypeError):
        from_epoch_ms(value)  # pyright: ignore[reportArgumentType] - the wrong type is the test


def test_recorded_labels_resolve_against_their_publication() -> None:
    labels = recorded_arrival_labels("query-ep5-earliest-reasonable-arrival-time.geojson")
    published = parse_nhc_local_time(FULL_TEXT)
    assert published == PUBLISHED

    resolved = {
        label: resolve_arrival_label(label, PUBLISHED, "MST").valid_at
        for label in labels
        if label.strip()
    }

    assert resolved == {
        "Mon 8 pm": datetime(2026, 10, 13, 3, tzinfo=UTC),
        "Tue 8 am": datetime(2026, 10, 13, 15, tzinfo=UTC),
        "Tue 8 pm": datetime(2026, 10, 14, 3, tzinfo=UTC),
        "Wed 8 am": datetime(2026, 10, 14, 15, tzinfo=UTC),
        "Wed 8 pm": datetime(2026, 10, 15, 3, tzinfo=UTC),
        "Thu 8 am": datetime(2026, 10, 15, 15, tzinfo=UTC),
    }


def test_the_most_likely_labels_are_recorded_and_resolve() -> None:
    labels = recorded_arrival_labels("query-ep5-most-likely-arrival-time.geojson")

    assert all(
        resolve_arrival_label(label, PUBLISHED, "MST").valid_at is not None
        for label in labels
        if label.strip()
    )
    assert sum(not label.strip() for label in labels) == 1


@pytest.mark.parametrize("label", ["Sat 2 pm", "Sat 3 pm", "Sun 8 am"])
def test_a_label_120_hours_or_more_after_publication_stays_unresolved(label: str) -> None:
    resolution = resolve_arrival_label(label, PUBLISHED, "MST")

    assert resolution.valid_at is None
    assert resolution.reason is not None
    assert "horizon" in resolution.reason


def test_a_label_just_inside_the_horizon_resolves() -> None:
    resolution = resolve_arrival_label("Sat 1 pm", PUBLISHED, "MST")

    assert resolution.valid_at == PUBLISHED + timedelta(hours=119)


@pytest.mark.parametrize("zone", ["XYZ", "ChST", "", None])
def test_an_unknown_zone_stays_unresolved(zone: str | None) -> None:
    resolution = resolve_arrival_label("Tue 8 am", PUBLISHED, zone)

    assert resolution.valid_at is None
    assert resolution.reason is not None
    assert "time zone" in resolution.reason


def test_a_saturday_publication_resolves_monday_across_the_week_boundary() -> None:
    published = parse_nhc_local_time("1100 PM EDT Sat Oct 17 2026")
    assert published is not None

    resolution = resolve_arrival_label("Mon 2 am", published, "EDT")

    assert resolution.valid_at == datetime(2026, 10, 19, 6, tzinfo=UTC)


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("TUE 8 AM", datetime(2026, 10, 13, 15, tzinfo=UTC)),
        ("tue 8:30 am", datetime(2026, 10, 13, 15, 30, tzinfo=UTC)),
        ("Mon 2 pm", PUBLISHED),
        ("Tue 12 am", datetime(2026, 10, 13, 7, tzinfo=UTC)),
    ],
)
def test_labels_ignore_case_take_minutes_and_include_the_publication_instant(
    label: str, expected: datetime
) -> None:
    assert resolve_arrival_label(label, PUBLISHED, "MST").valid_at == expected


@pytest.mark.parametrize("label", ["Tuesday 8 am", "Tue 13 pm", "Tue 8", "8 am", " "])
def test_a_label_that_does_not_parse_stays_unresolved(label: str) -> None:
    resolution = resolve_arrival_label(label, PUBLISHED, "MST")

    assert resolution.valid_at is None
    assert resolution.reason is not None
    assert "does not parse" in resolution.reason


def test_the_recorded_slot_cone_and_arrival_lines_name_different_advisories() -> None:
    # The evidence behind issue #11's choice: the slot's advdate is the wrong anchor.
    cone = properties("query-ep5-forecast-cone.geojson")[0]
    lines = properties("query-ep5-earliest-reasonable-arrival-time.geojson")

    assert (cone["advisnum"], cone["advdate"]) == ("22A", INTERMEDIATE_TEXT)
    assert {line["idp_source"] for line in lines} == {"EP202026_022adv_earliest_reasonable_toa_34"}
    assert (TROPICAL / "query-ep5-earliest-reasonable-arrival-time.geojson").is_file()
