# tests/engine/test_changes.py
"""``diff``: every kind of change event, the initial events, the refusals, and Irma's replay.

The synthetic assessments are live snapshots around the Miami-Dade landmark, built at run
time; the replay is every committed Irma advisory at the same landmark, in order.
"""

import re
from datetime import datetime, timedelta
from typing import get_args

import pytest
from engine_support import (
    IRMA,
    MIAMI_DADE,
    SYNTHETIC_AT,
    landmark_location,
    landmark_xy,
    line,
    offset,
    square,
    synthetic_alert,
    synthetic_segment,
    synthetic_snapshot,
    synthetic_storm,
    synthetic_summary,
)
from pydantic import ValidationError
from scenarios import rebuilt, replay_miami_dade, replay_snapshots

from weatherbot.engine import assess, diff
from weatherbot.models import (
    CHANGE_KINDS,
    AlertLevel,
    Assessment,
    ChangeEvent,
    Geometry,
    NwsAlert,
    SourceId,
    StormProducts,
    Thresholds,
)
from weatherbot.models.assessment import ChangeKind

LOCATION = landmark_location()
ALONGSIDE = line(offset(MIAMI_DADE, 0.1, -1.0), offset(MIAMI_DADE, 0.1, 1.0))
OVER = square(landmark_xy(MIAMI_DADE), 1.0)
AWAY = square(offset(MIAMI_DADE, 5.0), 1.0)
DECIMAL_COORDINATE = re.compile(r"\d+\.\d{3,}")


def assessed(
    *,
    hours: int = 0,
    storms: tuple[StormProducts, ...] = (),
    alerts: tuple[NwsAlert, ...] = (),
    failed: tuple[SourceId, ...] = (),
) -> Assessment:
    """Assess the Miami-Dade landmark against a synthetic snapshot ``hours`` after the first."""
    at = SYNTHETIC_AT + timedelta(hours=hours)
    snapshot = synthetic_snapshot(
        storms=storms,
        alerts={LOCATION.name: alerts},
        failed=failed,
        at=at,
    )
    return assess(snapshot, LOCATION, Thresholds())


def storm(
    *,
    cone: Geometry | None = None,
    codes: tuple[str, ...] = (),
    advisory: str = "1",
    hours: int = 0,
) -> StormProducts:
    at = SYNTHETIC_AT + timedelta(hours=hours)
    return synthetic_storm(
        cone=cone,
        segments=[synthetic_segment(code, ALONGSIDE, at) for code in codes],
        summary=synthetic_summary(at, advisory),
        at=at,
    )


def alert(event: str, ident: str, references: tuple[str, ...] = ()) -> NwsAlert:
    return rebuilt(synthetic_alert(event), id=f"urn:oid:synthetic.{ident}", references=references)


def kinds(events: tuple[ChangeEvent, ...]) -> list[str]:
    return [event.kind for event in events]


# The event vocabulary ---------------------------------------------------------------------


def test_there_are_exactly_seven_kinds_of_event_in_emission_order() -> None:
    assert get_args(ChangeKind.__value__) == CHANGE_KINDS
    assert len(CHANGE_KINDS) == 7  # noqa: PLR2004 - the documented seven


@pytest.mark.parametrize(
    "fields",
    [
        {"kind": "level_changed", "level": AlertLevel.ALL_CLEAR, "detail": "x"},
        {"kind": "official_added", "codes": ("HWR",), "detail": "x"},
        {"kind": "cone_left", "storm_name": "Synthetic", "detail": "x"},
        {
            "kind": "advisory_issued",
            "atcf_id": "CP012026",
            "storm_name": "Synthetic",
            "advisory": "1",
            "level": AlertLevel.ALL_CLEAR,
            "detail": "x",
        },
    ],
    ids=["level-without-direction", "official-without-product", "cone-without-storm", "extra"],
)
def test_an_event_sets_exactly_the_fields_of_its_kind(fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ChangeEvent.model_validate(fields)


# The initial events -----------------------------------------------------------------------


def test_the_first_assessment_gives_the_initial_events_in_order() -> None:
    outside = synthetic_alert("Hurricane Watch", queries=("FLC086",), zones=("FLZ069",))
    first = assessed(
        storms=(storm(cone=OVER, codes=("TWR",)),),
        alerts=(alert("Hurricane Warning", "warning"), outside),
    )

    events = diff(None, first)

    assert kinds(events) == [
        "level_changed",
        "advisory_issued",
        "official_added",
        "official_added",
        "cone_entered",
    ]
    level, advisory, warning, segment, cone = events
    assert (level.previous_level, level.level, level.direction) == (
        None,
        AlertLevel.HURRICANE_WARNING,
        "initial",
    )
    assert (advisory.previous_advisory, str(advisory.advisory), advisory.in_cone) == (
        None,
        "1",
        True,
    )
    assert (warning.product, warning.alert_id) == ("nws_alert", "urn:oid:synthetic.warning")
    assert (segment.product, segment.codes) == ("watch_warning_segment", ("TWR",))
    assert cone.atcf_id == "CP012026"


def test_an_unchanged_location_has_no_events() -> None:
    first = assessed(
        storms=(storm(cone=OVER, codes=("HWA",)),), alerts=(alert("Hurricane Watch", "a"),)
    )
    again = assessed(
        hours=1,
        storms=(storm(cone=OVER, codes=("HWA",), hours=1),),
        alerts=(alert("Hurricane Watch", "a"),),
    )

    assert diff(first, again) == ()
    assert diff(first, first) == ()


# The level --------------------------------------------------------------------------------


def test_the_level_moves_up_and_down() -> None:
    calm = assessed()
    coned = assessed(hours=1, storms=(storm(cone=OVER, hours=1),))
    calm_again = assessed(hours=2)

    (up,) = [event for event in diff(calm, coned) if event.kind == "level_changed"]
    (down,) = [event for event in diff(coned, calm_again) if event.kind == "level_changed"]

    assert (up.previous_level, up.level, up.direction) == (
        AlertLevel.ALL_CLEAR,
        AlertLevel.TROPICAL_STORM_THREAT,
        "up",
    )
    assert (down.level, down.direction, down.rule) == (AlertLevel.ALL_CLEAR, "down", "all_clear")


# Advisories -------------------------------------------------------------------------------


def test_a_new_advisory_is_an_event_with_whether_its_cone_covers_the_location() -> None:
    first = assessed(storms=(storm(cone=AWAY),))
    second = assessed(hours=3, storms=(storm(cone=AWAY, advisory="1A", hours=3),))

    (event,) = diff(first, second)

    assert event.kind == "advisory_issued"
    assert (str(event.previous_advisory), str(event.advisory), event.in_cone) == ("1", "1A", False)


# Official products ------------------------------------------------------------------------


def test_an_alert_replaced_through_its_references_is_one_change() -> None:
    watch = alert("Tropical Storm Warning", "first")
    upgrade = alert("Hurricane Warning", "second", references=("urn:oid:synthetic.first",))

    events = diff(assessed(alerts=(watch,)), assessed(hours=1, alerts=(upgrade,)))
    (change,) = [event for event in events if event.kind.startswith("official")]

    assert change.kind == "official_changed"
    assert (change.previous_alert_id, change.alert_id) == (
        "urn:oid:synthetic.first",
        "urn:oid:synthetic.second",
    )
    assert (change.previous_codes, change.codes) == (
        ("Tropical Storm Warning",),
        ("Hurricane Warning",),
    )


def test_an_alert_that_appears_or_stops_covering_is_added_or_removed() -> None:
    old = alert("Hurricane Watch", "old")
    expired = rebuilt(old, expires=SYNTHETIC_AT + timedelta(minutes=30))
    new = alert("Tropical Storm Warning", "new")

    events = diff(assessed(alerts=(expired,)), assessed(hours=1, alerts=(expired, new)))

    assert [(event.kind, event.alert_id) for event in events if event.product] == [
        ("official_added", "urn:oid:synthetic.new"),
        ("official_removed", "urn:oid:synthetic.old"),
    ]


def test_only_a_covering_alert_makes_an_event() -> None:
    outside = synthetic_alert("Hurricane Warning", queries=("FLC086",), zones=("FLZ069",))

    events = diff(assessed(), assessed(hours=1, alerts=(outside,)))

    assert events == ()


def test_a_segment_s_code_moving_from_hwa_to_hwr_is_one_change() -> None:
    watch = assessed(storms=(storm(codes=("HWA",)),))
    warning = assessed(hours=6, storms=(storm(codes=("HWR",), advisory="2", hours=6),))

    events = diff(watch, warning)
    (change,) = [event for event in events if event.product]

    assert change.kind == "official_changed"
    # The event names the segments' own advisory, which the synthetic segments state as 1.
    assert (change.previous_codes, change.codes, str(change.advisory)) == (("HWA",), ("HWR",), "1")
    assert "Hurricane Watch (HWA)" in change.detail
    assert "Hurricane Warning (HWR)" in change.detail
    assert kinds(events) == ["level_changed", "advisory_issued", "official_changed"]


def test_a_segment_code_added_beside_another_or_withdrawn_is_added_or_removed() -> None:
    watch = assessed(storms=(storm(codes=("TWA",)),))
    both = assessed(hours=6, storms=(storm(codes=("TWA", "HWA"), hours=6),))
    none = assessed(hours=12, storms=(storm(hours=12),))

    added = [(e.kind, e.codes) for e in diff(watch, both) if e.product]
    removed = [(e.kind, e.codes) for e in diff(both, none) if e.product]

    assert added == [("official_added", ("HWA",))]
    assert removed == [("official_removed", ("HWA",)), ("official_removed", ("TWA",))]


# Cones ------------------------------------------------------------------------------------


def test_a_cone_entered_then_left() -> None:
    away = assessed(storms=(storm(cone=AWAY),))
    over = assessed(hours=6, storms=(storm(cone=OVER, hours=6),))
    away_again = assessed(hours=12, storms=(storm(cone=AWAY, hours=12),))

    entered = [event.kind for event in diff(away, over) if event.kind.startswith("cone")]
    left = [event.kind for event in diff(over, away_again) if event.kind.startswith("cone")]

    assert (entered, left) == (["cone_entered"], ["cone_left"])


def test_a_storm_no_longer_listed_leaves_the_cone_unless_the_roster_failed() -> None:
    over = assessed(storms=(storm(cone=OVER),))

    gone = diff(over, assessed(hours=6))
    unknown = diff(over, assessed(hours=6, failed=("nhc-current-storms",)))

    (left,) = [event for event in gone if event.kind == "cone_left"]
    assert "no longer listed" in left.detail
    assert not [event for event in unknown if event.kind == "cone_left"]


def test_a_cone_that_could_not_be_read_enters_or_leaves_nothing() -> None:
    over = assessed(storms=(storm(cone=OVER),))
    unread = assessed(hours=6, storms=(storm(hours=6),))

    assert not [event for event in diff(over, unread) if event.kind.startswith("cone")]


# Refusals ---------------------------------------------------------------------------------


def test_two_locations_are_refused() -> None:
    other = assess(synthetic_snapshot(), landmark_location("nassau"), Thresholds())

    with pytest.raises(ValueError, match="one location"):
        diff(other, assessed())


def test_a_current_assessment_older_than_the_previous_is_refused() -> None:
    with pytest.raises(ValueError, match="older"):
        diff(assessed(hours=1), assessed())


# The replay -------------------------------------------------------------------------------


def test_irma_at_the_miami_dade_landmark_enters_the_cone_once_and_leaves_it_once() -> None:
    location = replay_miami_dade()
    previous: Assessment | None = None
    events: list[ChangeEvent] = []
    advisories: list[datetime] = []
    for snapshot in replay_snapshots(IRMA).values():
        current = assess(snapshot, location, Thresholds())
        events.extend(diff(previous, current))
        advisories.append(current.as_of)
        previous = current

    cones = [(event.kind, str(event.advisory)) for event in events if event.kind.startswith("cone")]

    assert cones == [("cone_entered", "22"), ("cone_left", "40")]
    assert sum(event.kind == "advisory_issued" for event in events) == len(advisories)
    assert advisories == sorted(advisories)
    assert not [event.detail for event in events if DECIMAL_COORDINATE.search(event.detail)]


def test_a_segment_code_outside_the_ladder_is_named_by_its_code() -> None:
    events = diff(assessed(), assessed(hours=6, storms=(storm(codes=("XYZ",), hours=6),)))

    (added,) = [event for event in events if event.product]
    assert (added.kind, added.codes) == ("official_added", ("XYZ",))
    assert "code XYZ" in added.detail
