# tests/contract/test_fixture_budget.py
"""Contract test: committed fixtures stay within the repository's size budget.

Every stored byte under ``tests/fixtures/recorded/`` counts (payloads, manifests, and the
notice). Step 6 adds the replay subset to ``BUDGETED_ROOTS``, so one budget covers all of
``tests/fixtures/``.
"""

from pathlib import Path

import pytest
from fixture_support import RECORDED_ROOT

import record_fixtures as recorder

MEBIBYTE = 1024 * 1024
MAX_TOTAL_BYTES = 25 * MEBIBYTE
MAX_FILE_BYTES = 5 * MEBIBYTE
REPLAY_ROOT = RECORDED_ROOT.parent / "replay"
BUDGETED_ROOTS = (RECORDED_ROOT, REPLAY_ROOT)


def stored_files() -> list[Path]:
    """List every file under the budgeted roots."""
    return [path for root in BUDGETED_ROOTS for path in root.rglob("*") if path.is_file()]


def test_the_stored_bytes_total_at_most_25_mib() -> None:
    files = stored_files()
    assert files, "no fixtures to budget"
    total = sum(path.stat().st_size for path in files)
    assert total <= MAX_TOTAL_BYTES, f"{total} stored bytes, over the {MAX_TOTAL_BYTES} byte budget"


@pytest.mark.parametrize("root", BUDGETED_ROOTS, ids=lambda root: root.name)
def test_every_stored_file_is_at_most_5_mib(root: Path) -> None:
    too_big = {
        path.relative_to(root).as_posix(): path.stat().st_size
        for path in root.rglob("*")
        if path.is_file() and path.stat().st_size > MAX_FILE_BYTES
    }
    assert not too_big, f"stored files over {MAX_FILE_BYTES} bytes: {too_big}"


def test_the_recorder_enforces_the_same_limits() -> None:
    assert recorder.MAX_STORED_BYTES == MAX_FILE_BYTES


def test_replay_stored_bytes_total_at_most_10_mib() -> None:
    files = [path for path in REPLAY_ROOT.rglob("*") if path.is_file()]
    assert files, "no replay corpus to budget"
    total = sum(path.stat().st_size for path in files)
    assert total <= 10 * MEBIBYTE, f"replay corpus stores {total} bytes"
