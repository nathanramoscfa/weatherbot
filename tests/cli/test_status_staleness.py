# tests/cli/test_status_staleness.py
"""``status`` shows stale heartbeats in a banner and lists every heartbeat in its document.

A scheduled runner's cycle is recorded as Step 5's loops will record it, with the sources'
three-hour cadence; ``status --no-fetch`` then runs with the clock seven hours later, so the
sources last succeeded more than twice their cadence ago. After manual cycles alone, no row
promises a cadence and nothing is stale. Offline, against the recorded answers.
"""

from datetime import timedelta
from typing import Final

from cli_support import (
    MIAMI,
    add_landmark,
    parse,
    recorded_services,
    run,
    runtime,
    scheduled_cycle,
)
from source_support import NOW

from weatherbot.cli.documents import StatusDocument
from weatherbot.services.monitor import SCHEDULED_SOURCE_CADENCE_S
from weatherbot.services.snapshots import SNAPSHOT_SOURCES

SEVEN_HOURS_LATER: Final = NOW + timedelta(hours=7)
ROSTER_LINE: Final = "Stale data: nhc-current-storms last succeeded 7 h ago; expected every 3 h."


def test_status_shows_the_stale_sources_after_a_scheduled_cycle() -> None:
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        assert scheduled_cycle().status == "complete"
    later = runtime(now=SEVEN_HOURS_LATER)

    printed = run(["status", "--no-fetch"], later)
    document = parse(run(["status", "--no-fetch", "--json"], later), StatusDocument)

    assert printed.exit_code == 0, printed.stderr
    assert ROSTER_LINE in printed.stdout
    banner = [line for line in printed.stdout.splitlines() if line.startswith("Stale data: ")]
    assert len(banner) == len(SNAPSHOT_SOURCES)
    assert printed.stdout.index(ROSTER_LINE) < printed.stdout.index(f"\n{MIAMI}: ")
    rows = {(row.kind, row.name): row for row in document.data.staleness}
    roster = rows["source", "nhc-current-storms"]
    assert (roster.stale, roster.age_s, roster.expected_every_s) == (
        True,
        7 * 3600,
        SCHEDULED_SOURCE_CADENCE_S,
    )
    assert roster.last_success_at == NOW
    assert {name for kind, name in rows if kind == "runner"} == {"serve", "status"}
    assert not rows["runner", "serve"].stale
    assert not rows["runner", "status"].stale


def test_status_shows_no_banner_after_manual_cycles_alone() -> None:
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        assert run(["status"]).exit_code == 0
    later = runtime(now=SEVEN_HOURS_LATER)

    printed = run(["status", "--no-fetch"], later)
    document = parse(run(["status", "--no-fetch", "--json"], later), StatusDocument)

    assert printed.exit_code == 0, printed.stderr
    assert "Stale data" not in printed.stdout
    assert document.data.staleness
    assert all(not row.stale for row in document.data.staleness)
    assert all(row.expected_every_s is None for row in document.data.staleness)
    sources = [row for row in document.data.staleness if row.kind == "source"]
    assert {row.name for row in sources} == set(SNAPSHOT_SOURCES)
    assert all(row.age_s == 7 * 3600 for row in sources)
