# tests/cli/test_documents.py
"""The committed JSON Schemas, the packaged disclaimer, and what both may hold."""

import json
import re
from pathlib import Path
from typing import cast

import pytest
from fixture_support import REPOSITORY_ROOT
from jsonschema import Draft202012Validator

import export_schemas
from weatherbot.cli.documents import DOCUMENTS, JSON_SCHEMA_DIALECT, SCHEMA_BASE_URL, json_schema
from weatherbot.services.disclaimer import ESSENTIALS, NOTICE, full_text

SCHEMAS = REPOSITORY_ROOT / "docs" / "schema"
DECIMAL = re.compile(r"(?<![\d.])-?\d+\.\d+(?![\d.])")


def test_the_committed_schemas_equal_a_fresh_export() -> None:
    assert export_schemas.stale() == []
    assert sorted(path.name for path in SCHEMAS.glob("*.json")) == sorted(
        f"{name}.schema.json" for name in DOCUMENTS
    )


@pytest.mark.parametrize("name", list(DOCUMENTS))
def test_each_schema_is_json_schema_2020_12_with_its_id(name: str) -> None:
    schema = cast(
        "dict[str, object]",
        json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8")),
    )

    assert schema["$schema"] == JSON_SCHEMA_DIALECT
    assert schema["$id"] == f"{SCHEMA_BASE_URL}/{name}.schema.json"
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("name", list(DOCUMENTS))
def test_no_schema_carries_an_example_or_a_coordinate(name: str) -> None:
    text = (SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8")

    assert '"example' not in text
    assert DECIMAL.findall(text) == []


def test_only_the_locations_document_has_a_place_for_coordinates() -> None:
    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            mapping = cast("dict[str, object]", value)
            return set(mapping).union(*(keys(item) for item in mapping.values()))
        if isinstance(value, list):
            return set[str]().union(*(keys(item) for item in cast("list[object]", value)))
        return set()

    holding = {name for name in DOCUMENTS if {"latitude", "longitude"} & keys(json_schema(name))}
    assert holding == {"locations"}


def test_the_exporter_writes_and_checks(tmp_path: Path) -> None:
    written = export_schemas.write(tmp_path)

    assert [path.name for path in written] == [f"{name}.schema.json" for name in DOCUMENTS]
    assert export_schemas.stale(tmp_path) == []
    written[0].write_text("{}\n", encoding="utf-8")
    assert export_schemas.stale(tmp_path) == [next(iter(DOCUMENTS))]


def test_the_check_mode_passes_on_the_committed_schemas(capsys: pytest.CaptureFixture[str]) -> None:
    assert export_schemas.main(["--check"]) == 0
    assert f"OK {len(DOCUMENTS)} schemas are current" in capsys.readouterr().out
    assert len(DOCUMENTS) == 13  # noqa: PLR2004 - Phase 2's five, status, replay, check, config, config-path, notifications, notify-setup, notify-test


def test_the_packaged_disclaimer_is_the_repositorys_byte_for_byte() -> None:
    repository = (REPOSITORY_ROOT / "DISCLAIMER.md").read_bytes()
    packaged = (REPOSITORY_ROOT / "src" / "weatherbot" / "DISCLAIMER.md").read_bytes()

    assert packaged == repository
    # Text mode reads either checkout's line endings (a Windows runner checks out CRLF).
    assert full_text() == (REPOSITORY_ROOT / "DISCLAIMER.md").read_text(encoding="utf-8")


def test_the_essentials_and_the_notice_say_what_the_disclaimer_says() -> None:
    text = full_text()
    essentials = " ".join(ESSENTIALS)

    assert "INFORMATIONAL PURPOSES ONLY" in text
    assert "informational only" in essentials
    assert "evacuation order" in essentials
    assert "evacuation orders" in text
    assert "DISCLAIMER.md" in NOTICE
    assert "never a substitute for official guidance" in NOTICE
