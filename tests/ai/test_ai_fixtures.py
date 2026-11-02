# tests/ai/test_ai_fixtures.py
"""``tests/fixtures/ai/``: no header, no key, under budget, and the manifest names every file."""

import json
import re

from ai_support import FIXTURES, HEADER_NAMES
from eval.chat_cases import CHAT_CASES, NARRATION_CASES

from record_ai_fixtures import BUDGET_BYTES, MANIFEST, all_cases

# Assembled at run time, so this file holds no key-shaped string for the scans.
KEY_SHAPE = re.compile(re.escape("sk" + "-" + "ant" + "-") + r"[A-Za-z0-9_\-]{8,}")
SHA256 = re.compile(r"[0-9a-f]{64}")


def _recordings() -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(FIXTURES.iterdir()) if path.is_file()}


def test_no_recording_carries_a_header_name_or_a_key() -> None:
    files = _recordings()
    assert files

    for name, body in files.items():
        text = body.decode("utf-8").lower()
        assert not [header for header in HEADER_NAMES if header in text], name
        assert not KEY_SHAPE.search(body.decode("utf-8")), name


def test_the_directory_stays_under_its_budget() -> None:
    assert sum(len(body) for body in _recordings().values()) <= BUDGET_BYTES


def test_the_manifest_names_every_recording_with_its_size() -> None:
    files = _recordings()
    cases = all_cases()
    manifest = json.loads(files.pop(MANIFEST))
    by_file = {
        f"{entry['case']}.{'sse' if entry['kind'] == 'stream' else 'json'}": entry
        for entry in manifest
    }

    assert set(by_file) == set(files)
    for name, entry in by_file.items():
        assert set(entry) == {"case", "kind", "model", "date", "request_sha256", "bytes"}
        assert entry["bytes"] == len(files[name])
        assert SHA256.fullmatch(entry["request_sha256"])
        assert entry["case"] in cases
        assert entry["kind"] == cases[entry["case"]].kind


def test_the_round_trips_were_recorded() -> None:
    assert {"round-trip.json", "round-trip-stream.sse"} <= set(_recordings())


def test_every_chat_and_narration_case_was_recorded_and_each_chat_holds_its_rounds() -> None:
    files = _recordings()

    for case in CHAT_CASES:
        rounds = json.loads(files[f"{case.name}.json"])["rounds"]
        assert len(rounds) >= 2, case.name  # noqa: PLR2004 - a lookup, then the answer
        assert all(text.startswith("event: message_start") for text in rounds)
    for case in NARRATION_CASES:
        assert files[f"{case.name}.sse"].startswith(b"event: message_start")
