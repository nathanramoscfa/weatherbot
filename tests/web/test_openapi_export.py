# tests/web/test_openapi_export.py
"""``scripts/export_openapi.py`` writes and checks ``docs/api/openapi.json``."""

import json
from pathlib import Path
from typing import cast

import pytest
from fixture_support import REPOSITORY_ROOT

import export_openapi

OPENAPI_FILE = REPOSITORY_ROOT / "docs" / "api" / "openapi.json"


def test_committed_openapi_schema_matches_fresh_export(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert not export_openapi.is_stale()
    assert export_openapi.main(["--check"]) == 0
    assert "OK docs/api/openapi.json is current" in capsys.readouterr().out

    doc = cast(
        "dict[str, object]",
        json.loads(OPENAPI_FILE.read_text(encoding="utf-8")),
    )
    assert str(doc["openapi"]).startswith("3.1.")
    paths = cast("dict[str, object]", doc["paths"])
    assert "/api/health" in paths
    assert "/docs" not in paths
    assert "/redoc" not in paths
    assert "/" not in paths


def test_export_openapi_writes_and_detects_stale_copy(tmp_path: Path) -> None:
    target = tmp_path / "openapi.json"
    written = export_openapi.write(target)
    assert written == target
    assert not export_openapi.is_stale(target)

    target.write_text("{}\n", encoding="utf-8")
    assert export_openapi.is_stale(target)
