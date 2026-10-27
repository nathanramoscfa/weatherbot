# tests/web/test_api_fixtures.py
"""Tests for ``scripts/export_api_fixtures.py`` and ``frontend/src/test/fixtures/``."""

import json
from pathlib import Path

import check_personal_data
import export_api_fixtures


def test_committed_api_fixtures_match_export_script() -> None:
    assert export_api_fixtures.is_stale() is False
    assert export_api_fixtures.main(["--check"]) == 0


def test_export_api_fixtures_check_detects_stale_and_writes_clean(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    del monkeypatch
    assert export_api_fixtures.is_stale(tmp_path) is True
    written = export_api_fixtures.write_fixtures(tmp_path)
    assert len(written) == len(export_api_fixtures.ROUTE_FIXTURES)
    assert export_api_fixtures.is_stale(tmp_path) is False

    health_path = tmp_path / "health.json"
    health_path.write_text("{}", encoding="utf-8", newline="\n")
    assert export_api_fixtures.is_stale(tmp_path) is True


def test_committed_api_fixtures_pass_personal_data_and_placeholder_rules() -> None:
    allowlist = check_personal_data.Allowlist.from_landmarks(check_personal_data.load_landmarks())
    scanner = check_personal_data.Scanner(
        root=export_api_fixtures.REPO_ROOT,
        allowlist=allowlist,
        denylist=None,
    )
    fixture_paths = [
        (export_api_fixtures.FIXTURES_DIR / filename)
        .relative_to(export_api_fixtures.REPO_ROOT)
        .as_posix()
        for filename, _ in export_api_fixtures.ROUTE_FIXTURES
    ]
    assert scanner.scan(fixture_paths) == []

    settings_doc = json.loads(
        (export_api_fixtures.FIXTURES_DIR / "settings.json").read_text(encoding="utf-8")
    )
    assert settings_doc["settings_file"] == export_api_fixtures.PLACEHOLDER_SETTINGS_FILE

    assessments_doc = json.loads(
        (export_api_fixtures.FIXTURES_DIR / "assessments.json").read_text(encoding="utf-8")
    )
    assert assessments_doc["snapshot"]["snapshot_id"].startswith("00000000-0000-4000-8000-")
