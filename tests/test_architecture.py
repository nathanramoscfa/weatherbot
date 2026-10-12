# tests/test_architecture.py
"""Tests that keep the layer architecture honest.

The import-linter contracts in ``pyproject.toml`` forbid the engine from importing any
other layer and fix the direction of every other import. The AST scan here adds what
those contracts cannot see: the engine must also not import an I/O library, so it stays a
pure function of its inputs.
"""

import ast
from pathlib import Path

import pytest
from importlinter.cli import lint_imports

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIRECTORY = REPOSITORY_ROOT / "src" / "weatherbot" / "engine"

# Top-level modules the engine must never import: network, process, database, web,
# model, and scheduler libraries.
BANNED_ENGINE_IMPORTS = frozenset(
    {
        "alembic",
        "anthropic",
        "apscheduler",
        "fastapi",
        "httpx",
        "requests",
        "socket",
        "sqlalchemy",
        "sqlite3",
        "starlette",
        "urllib",
        "urllib3",
        "uvicorn",
    }
)


def banned_imports(source: str) -> list[str]:
    """Return the banned top-level modules that ``source`` imports, in source order.

    Args:
        source: Python source text.

    Returns:
        One entry per banned import statement, naming the top-level module.
    """
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue
        found.extend(
            root for name in names if (root := name.split(".")[0]) in BANNED_ENGINE_IMPORTS
        )
    return found


def test_import_contracts_are_kept() -> None:
    exit_code = lint_imports(
        config_filename=str(REPOSITORY_ROOT / "pyproject.toml"),
        no_cache=True,
        no_logo=True,
    )

    assert exit_code == 0


def test_engine_imports_no_io_library() -> None:
    engine_files = sorted(ENGINE_DIRECTORY.rglob("*.py"))
    assert engine_files, "the engine package must exist"

    violations = {
        path.relative_to(REPOSITORY_ROOT).as_posix(): found
        for path in engine_files
        if (found := banned_imports(path.read_text(encoding="utf-8")))
    }

    assert not violations


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import httpx", ["httpx"]),
        ("import httpx as client", ["httpx"]),
        ("from httpx import Client", ["httpx"]),
        ("import urllib.request", ["urllib"]),
        ("from urllib.parse import quote", ["urllib"]),
        ("import os, socket", ["socket"]),
        ("def f() -> None:\n    import sqlite3\n", ["sqlite3"]),
        ("import json\nfrom dataclasses import dataclass", []),
        ("from . import sibling", []),
        ("from .httpx import helper", []),
    ],
)
def test_the_scan_catches_banned_imports(source: str, expected: list[str]) -> None:
    assert banned_imports(source) == expected


def test_the_scan_catches_a_synthetic_engine_module(tmp_path: Path) -> None:
    module = tmp_path / "engine_module.py"
    module.write_text("import httpx\n", encoding="utf-8")

    assert banned_imports(module.read_text(encoding="utf-8")) == ["httpx"]
