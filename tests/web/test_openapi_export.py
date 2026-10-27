# tests/web/test_openapi_export.py
"""``scripts/export_openapi.py`` writes and checks ``docs/api/openapi.json``."""

import json
from pathlib import Path
from typing import cast

import pytest
from fixture_support import REPOSITORY_ROOT

import export_openapi
from weatherbot.services.events import EVENT_KINDS, QUERY_KEYS

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
    assert "/api/events" in paths
    assert "/api/locations" in paths
    assert "/api/locations/evacuation" in paths
    assert "/api/cycles" in paths
    assert "/api/notifications/test" in paths
    assert "/docs" not in paths
    assert "/redoc" not in paths
    assert "/" not in paths

    components = cast("dict[str, object]", doc["components"])
    schemas = cast("dict[str, object]", components["schemas"])
    assert "StreamEvent" in schemas
    assert "EventKind" in schemas
    assert "QueryKey" in schemas
    query_key_schema = cast("dict[str, object]", schemas["QueryKey"])
    assert tuple(cast("list[str]", query_key_schema["enum"])) == QUERY_KEYS
    event_kind_schema = cast("dict[str, object]", schemas["EventKind"])
    assert tuple(cast("list[str]", event_kind_schema["enum"])) == EVENT_KINDS


def test_export_openapi_writes_and_detects_stale_copy(tmp_path: Path) -> None:
    target = tmp_path / "openapi.json"
    written = export_openapi.write(target)
    assert written == target
    assert not export_openapi.is_stale(target)

    target.write_text("{}\n", encoding="utf-8")
    assert export_openapi.is_stale(target)
