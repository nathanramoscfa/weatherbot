# tests/cli/test_status.py
"""``weatherbot status`` assesses and stores every location, and prints each part.

Offline, against the recorded answers, for both public landmarks. Each test runs in its
own temporary data directory; every ``--json`` document is validated against its
committed schema before it is read.
"""

from datetime import timedelta

import httpx
import pytest
from cli_support import (
    MIAMI,
    NASSAU,
    SUMMARY_CATALOG,
    add_landmark,
    county_statement,
    history,
    parse,
    recorded_services,
    run,
    runtime,
)
from source_support import NOW
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from weatherbot.cli.documents import StatusDocument
from weatherbot.models import Thresholds
from weatherbot.services.config import AppPaths
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.tables import (
    AssessmentChangeRow,
    AssessmentEvidenceRow,
    AssessmentRow,
)

UNAVAILABLE = 503
USAGE = 2
LATER = NOW + timedelta(minutes=20)


def _counts() -> tuple[int, ...]:
    with open_database(AppPaths.resolve()) as database, Session(database.engine) as session:
        return tuple(
            session.scalar(select(func.count()).select_from(table)) or 0  # pyright: ignore[reportArgumentType] - a mapped class
            for table in (AssessmentRow, AssessmentEvidenceRow, AssessmentChangeRow)
        )


def _section(stdout: str, name: str) -> str:
    """One location's part of the output: from its heading to the next blank line."""
    start = stdout.index(f"\n{name}: ")
    end = stdout.find("\n\n", start + 1)
    return stdout[start : end if end != -1 else None]


def test_status_prints_every_part_for_both_landmarks() -> None:
    with recorded_services(overrides=county_statement()):
        add_landmark(MIAMI, "miami-dade")
        add_landmark(NASSAU, "nassau")
        result = run(["status"])

    assert result.exit_code == 0, result.stderr
    assert ": complete." in result.stdout
    miami = _section(result.stdout, MIAMI)
    assert f"\n{MIAMI}: level 1, All Clear" in miami
    assert "  Decided by all_clear: No other rule matches." in miami
    assert "  Actions: Normal activities" in miami
    assert "  Evidence: none; no rule matched." in miami
    # Issue #10: the point query's alert covers it; the county's other zones are context.
    assert (
        "  Official products that cover it:\n    - Rip Current Statement from NWS Miami FL" in miami
    )
    assert "the point query returned it" in miami
    assert "  County-zone alerts outside its zones (context; they set no level):" in miami
    assert "Coastal Flood Statement from NWS Miami FL" in miami
    assert "zones FLZ069, FLZ075, FLZ174" in miami
    assert "34 kt, synoptic time 2026-10-12 18:00 UTC: below every band" in miami
    assert (
        "  Storm Simon (EP202026), advisory 22A of 2026-10-13 00:00 UTC (2026-10-12 20:00 EDT):"
        in miami
    )
    assert "Category 2 (Hurricane); the location is outside its cone." in miami
    assert "    From its center: " in miami
    assert " km, bearing " in miami
    assert "    Closest approach: " in miami
    assert "Earliest-reasonable arrival of tropical-storm-force winds: unresolved:" in miami
    assert "Most-likely arrival: unresolved:" in miami
    assert "  Changes since the previous assessment:" in miami
    assert "The first assessment is at level 1 (All Clear), by the rule all_clear." in miami
    assert "Breakpoint span: Ocean Reef to Miami-Dade/Broward County Line (United States)" in miami
    assert "  Evacuation-order toggle: off." in miami
    nassau = _section(result.stdout, NASSAU)
    assert f"\n{NASSAU}: level 1, All Clear" in nassau
    assert "  Official products that cover it: none." in nassau
    # Outside NWS coverage, the instants print in UTC alone.
    assert "advisory 22A of 2026-10-13 00:00 UTC:" in nassau
    assert "  Breakpoint span: Bahamas (NW)" in nassau
    assert result.stdout.rstrip().endswith(NOTICE)


def test_status_json_holds_each_location_and_validates_against_its_schema() -> None:
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        add_landmark(NASSAU, "nassau")
        document = parse(run(["status", "--json"]), StatusDocument)

    assert document.snapshot.status == "complete"
    assert document.disclaimer == NOTICE
    miami, nassau = document.data.locations
    assert (miami.name, nassau.name) == (MIAMI, NASSAU)
    assert (miami.level, miami.level_name, miami.rule) == (1, "All Clear", "all_clear")
    assert miami.complete
    assert miami.time_zone == "America/New_York"
    assert miami.ruleset == Thresholds().fingerprint()
    assert [p.code for p in miami.official] == ["Rip Current Statement"]
    (simon,) = miami.threats
    assert (simon.atcf_id, simon.category, simon.in_cone) == ("EP202026", 2, False)
    assert simon.distance_km is not None
    assert simon.bearing_deg is not None
    assert simon.distance_km == round(simon.distance_km, 1)
    assert [change.kind for change in miami.changes] == [
        "level_changed",
        "advisory_issued",
        "official_added",
    ]
    assert miami.breakpoint_span is not None
    assert nassau.breakpoint_span is not None
    assert nassau.breakpoint_span.is_region
    assert not nassau.inside_nws_coverage
    assert not miami.stored_before


def test_an_incomplete_assessment_reads_at_least_and_a_partial_snapshot_exits_1() -> None:
    failed = httpx.Response(UNAVAILABLE, headers={"content-type": "text/plain"})
    with recorded_services(overrides={SUMMARY_CATALOG: failed}):
        add_landmark(MIAMI, "miami-dade")
        result = run(["status"])
        document = parse(run(["status", "--json"], runtime(now=LATER)), StatusDocument)

    assert result.exit_code == 1
    assert ": partial." in result.stdout
    assert f"{MIAMI}: at least level 1, All Clear" in result.stdout
    assert (
        "  At least: the level is a floor, because these inputs were unavailable:" in result.stdout
    )
    assert "nhc-map-tropical-summary failed (unavailable)" in result.stdout
    (miami,) = document.data.locations
    assert not miami.complete
    assert {item.kind for item in miami.unavailable} == {"source"}


def test_a_rerun_with_no_fetch_stores_nothing_new() -> None:
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        add_landmark(NASSAU, "nassau")
        first = run(["status"])
    stored = _counts()
    again = run(["status", "--no-fetch"], runtime(now=LATER))
    document = parse(run(["status", "--no-fetch", "--json"], runtime(now=LATER)), StatusDocument)

    assert first.exit_code == 0
    assert again.exit_code == 0, again.stderr
    assert ": complete, 20 min old." in again.stdout
    assert "(stored by an earlier run over this snapshot)" in again.stdout
    assert _counts() == stored
    assert stored[0] == 2  # noqa: PLR2004 - one assessment per landmark
    assert all(entry.stored_before for entry in document.data.locations)
    assert len(history(MIAMI)) == 1


def test_a_later_snapshot_is_diffed_against_the_stored_one() -> None:
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        run(["status"])
        later = run(["status", "--json"], runtime(now=LATER))
    document = parse(later, StatusDocument)

    (miami,) = document.data.locations
    assert miami.changes == ()
    assert [stored.assessment.as_of for stored in history(MIAMI)] == [LATER, NOW]


def test_the_toggle_lifts_the_level_and_names_when_it_was_set() -> None:
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        run(["status"])
        run(["locations", "evacuation", MIAMI, "on"], runtime(now=NOW + timedelta(minutes=5)))
        stale = run(["status", "--no-fetch"], runtime(now=NOW + timedelta(minutes=6)))
        fresh = run(["status"], runtime(now=LATER))

    assert "this level did not read it" in stale.stdout
    assert f"{MIAMI}: level 1, All Clear" in stale.stdout
    assert f"{MIAMI}: level 4, Warning / Watch / Evacuation" in fresh.stdout
    assert (
        "Decided by evacuation_order: The operator's evacuation-order toggle is on." in fresh.stdout
    )
    assert "toggle is on for this location since 2026-10-13 01:35 UTC." in fresh.stdout
    assert "The level rose from 1 (All Clear) to level 4" in fresh.stdout
    assert (
        "Evacuation-order toggle: on since 2026-10-13 01:35 UTC (2026-10-12 21:35 EDT);"
        in fresh.stdout
    )
    assert (
        "it holds the location at level 4 (Warning / Watch / Evacuation) or above." in fresh.stdout
    )


def test_status_prints_the_one_location_named_and_assesses_every_one() -> None:
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        add_landmark(NASSAU, "nassau")
        result = run(["status", "--location", NASSAU])
        document = parse(
            run(["status", "--location", MIAMI, "--json"], runtime(now=LATER)), StatusDocument
        )

    assert result.exit_code == 0
    assert f"{NASSAU}: level 1" in result.stdout
    assert f"{MIAMI}: level" not in result.stdout
    assert [entry.name for entry in document.data.locations] == [MIAMI]
    assert len(history(NASSAU)) == 2  # noqa: PLR2004 - assessed by both runs


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["status"], "no location is stored"),
        (["status", "--location", "Nowhere"], "no location is named 'Nowhere'"),
    ],
)
def test_status_without_the_location_asked_for_is_a_usage_error(
    args: list[str], message: str
) -> None:
    if "--location" in args:
        with recorded_services():
            add_landmark(MIAMI, "miami-dade")

    result = run(args)

    assert result.exit_code == USAGE
    assert message in result.stderr


def test_status_renders_in_a_terminal() -> None:
    with recorded_services():
        add_landmark(NASSAU, "nassau")
        result = run(["status"], runtime(terminal=True, width=160))

    assert result.exit_code == 0
    assert f"{NASSAU}: level 1, All Clear" in result.stdout
