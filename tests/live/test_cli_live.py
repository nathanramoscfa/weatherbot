# tests/live/test_cli_live.py
"""Every command against the live services, for both public landmarks.

Marked ``live`` and ``enable_socket``: it runs only with ``pytest -m live`` (and in
``.github/workflows/live-smoke.yml``). The isolation fixture pins the data directory under
the test's temporary directory, so the database it creates is thrown away; the only
coordinates sent are the two landmarks of ``scripts/public_landmarks.toml``, added through
``locations add`` (one Nominatim lookup each).
"""

import pytest
from cli_support import MIAMI, NASSAU, Ran, landmark, parse, run

from weatherbot.cli.documents import AlertsDocument, DoctorDocument, SnapshotInfo, StormsDocument
from weatherbot.cli.runtime import Runtime

pytestmark = [pytest.mark.live, pytest.mark.enable_socket]

LIVE = Runtime(terminal=False)
"""The real fetcher: the register's pacing, retries, and timeouts."""


def _failed(snapshot: SnapshotInfo) -> list[str]:
    return [f"{o.source_id}: {o.error_kind}" for o in snapshot.source_outcomes if o.error_kind]


def _complete(ran: Ran, snapshot: SnapshotInfo) -> None:
    assert ran.exit_code == 0, _failed(snapshot)
    assert snapshot.status == "complete"


def test_every_command_runs_against_the_live_services_for_both_landmarks() -> None:
    for name, key in ((MIAMI, "miami-dade"), (NASSAU, "nassau")):
        lat, lon = landmark(key)
        added = run(["locations", "add", name, "--lat", lat, "--lon", lon], LIVE)
        assert added.exit_code == 0, added.stderr

    fetched = run(["fetch"], LIVE)
    assert fetched.exit_code == 0, fetched.stdout + fetched.stderr

    ran = run(["storms", "--json"], LIVE)
    storms = parse(ran, StormsDocument)
    _complete(ran, storms.snapshot)

    ran = run(["alerts", "--location", MIAMI, "--json"], LIVE)
    miami = parse(ran, AlertsDocument)
    _complete(ran, miami.snapshot)
    assert miami.data.location.inside_nws_coverage is True
    assert miami.data.alerts is not None

    ran = run(["alerts", "--location", NASSAU, "--json"], LIVE)
    nassau = parse(ran, AlertsDocument)
    _complete(ran, nassau.snapshot)
    assert nassau.data.location.inside_nws_coverage is False
    assert nassau.data.alerts is None

    ran = run(["doctor", "--json"], LIVE)
    doctor = parse(ran, DoctorDocument)
    assert ran.exit_code == 0, [p for p in doctor.data.probes if p.status == "fail"]
    assert doctor.data.database is not None
    assert doctor.data.database.at_head is True
    assert all(layer.missing == () for layer in doctor.data.layers)
