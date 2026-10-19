# tests/test_architecture.py
"""Tests that keep the layer architecture honest.

The import-linter contracts in ``pyproject.toml`` forbid the engine from importing any
other layer and fix the direction of every other import, with ``weatherbot.models`` as the
lowest layer. The AST scans here add what those contracts cannot see: neither the engine
nor the models may import an I/O library, so the engine stays a pure function of its
inputs and the models stay plain data; and the engine reads no clock, randomness,
filesystem, environment, or logger, and takes only ``Geod`` from ``pyproj``, so the same
snapshot and location always give the same assessment.
"""

import ast
import tomllib
from pathlib import Path

import pytest
from importlinter.cli import lint_imports

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIRECTORY = REPOSITORY_ROOT / "src" / "weatherbot" / "engine"
MODELS_DIRECTORY = REPOSITORY_ROOT / "src" / "weatherbot" / "models"
# The packages the I/O ban covers: the pure engine and the shared models below it.
IO_FREE_DIRECTORIES = (ENGINE_DIRECTORY, MODELS_DIRECTORY)

# Top-level modules the engine and the models must never import: network, process,
# database, web, model, and scheduler libraries.
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


# What the engine alone must never use, beyond the I/O ban: the filesystem, the
# environment, processes, the clock, randomness, and logging.
DETERMINISM_BANNED_IMPORTS = frozenset(
    {
        "io",
        "logging",
        "os",
        "pathlib",
        "random",
        "secrets",
        "shutil",
        "subprocess",
        "tempfile",
        "time",
    }
)
# Calls that read the clock, draw a random id, or touch a file or the terminal, by the
# name called (``datetime.now()``, ``date.today()``, ``uuid.uuid4()``, ``open(...)``).
DETERMINISM_BANNED_CALLS = frozenset(
    {"now", "utcnow", "today", "uuid1", "uuid4", "open", "input", "print"}
)
# pyproj only as ``from pyproj import Geod``: no Transformer, no CRS database, no network.
PYPROJ_ALLOWED = ("pyproj", ("Geod",))


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


def nondeterminism(source: str) -> list[str]:
    """Return what ``source`` uses that the engine must not, in source order.

    Args:
        source: Python source text.

    Returns:
        One entry per banned import (``import time``), per ``pyproj`` import other than
        ``from pyproj import Geod`` (``pyproj``), and per banned call (``call now``).
    """
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in DETERMINISM_BANNED_IMPORTS or root == PYPROJ_ALLOWED[0]:
                    found.append(f"import {root}")
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            root = node.module.split(".")[0]
            names = tuple(alias.name for alias in node.names)
            aliased = any(alias.asname for alias in node.names)
            if root in DETERMINISM_BANNED_IMPORTS:
                found.append(f"import {root}")
            elif root == PYPROJ_ALLOWED[0] and ((node.module, names) != PYPROJ_ALLOWED or aliased):
                found.append(f"import {node.module}")
        elif isinstance(node, ast.Call):
            called = node.func
            name = (
                called.id
                if isinstance(called, ast.Name)
                else called.attr
                if isinstance(called, ast.Attribute)
                else None
            )
            if name in DETERMINISM_BANNED_CALLS:
                found.append(f"call {name}")
    return found


def test_import_contracts_are_kept() -> None:
    exit_code = lint_imports(
        config_filename=str(REPOSITORY_ROOT / "pyproject.toml"),
        no_cache=True,
        no_logo=True,
    )

    assert exit_code == 0


@pytest.mark.parametrize("directory", IO_FREE_DIRECTORIES, ids=lambda path: path.name)
def test_engine_and_models_import_no_io_library(directory: Path) -> None:
    files = sorted(directory.rglob("*.py"))
    assert files, f"the {directory.name} package must exist"

    violations = {
        path.relative_to(REPOSITORY_ROOT).as_posix(): found
        for path in files
        if (found := banned_imports(path.read_text(encoding="utf-8")))
    }

    assert not violations


def test_the_engine_reads_no_clock_randomness_filesystem_environment_or_logger() -> None:
    files = sorted(ENGINE_DIRECTORY.rglob("*.py"))
    assert len(files) > 1, "the engine's modules must exist"

    violations = {
        path.relative_to(REPOSITORY_ROOT).as_posix(): found
        for path in files
        if (found := nondeterminism(path.read_text(encoding="utf-8")))
    }

    assert not violations


def test_the_engine_takes_geod_from_pyproj() -> None:
    sources = [path.read_text(encoding="utf-8") for path in ENGINE_DIRECTORY.rglob("*.py")]

    assert any("from pyproj import Geod" in source for source in sources)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import time", ["import time"]),
        ("import os.path", ["import os"]),
        ("from pathlib import Path", ["import pathlib"]),
        ("import logging, random", ["import logging", "import random"]),
        ("from secrets import token_hex", ["import secrets"]),
        (
            "import io, shutil, subprocess, tempfile",
            ["import io", "import shutil", "import subprocess", "import tempfile"],
        ),
        ("from datetime import datetime\ndatetime.now()", ["call now"]),
        ("import datetime\ndatetime.datetime.utcnow()", ["call utcnow"]),
        ("from datetime import date\ndate.today()", ["call today"]),
        ("import uuid\nuuid.uuid4()\nuuid.uuid1()", ["call uuid4", "call uuid1"]),
        ("from uuid import uuid4\nuuid4()", ["call uuid4"]),
        ("open('x')", ["call open"]),
        ("input()\nprint()", ["call input", "call print"]),
        ("import pyproj", ["import pyproj"]),
        ("from pyproj import Transformer", ["import pyproj"]),
        ("from pyproj import Geod, CRS", ["import pyproj"]),
        ("from pyproj import Geod as G", ["import pyproj"]),
        ("from pyproj.geod import Geod", ["import pyproj.geod"]),
        ("from pyproj import Geod", []),
        ("from datetime import UTC, datetime\ndatetime(2026, 1, 1, tzinfo=UTC)", []),
        ("import math\nfrom functools import cache", []),
        ("from . import time", []),
        ("handlers[0]()", []),
    ],
)
def test_the_determinism_scan_catches_clock_random_file_and_pyproj_use(
    source: str, expected: list[str]
) -> None:
    assert nondeterminism(source) == expected


def test_models_are_the_lowest_layer() -> None:
    contracts = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    layered = next(
        contract
        for contract in contracts["tool"]["importlinter"]["contracts"]
        if contract["type"] == "layers"
    )

    assert layered["layers"][-1] == "weatherbot.models"


def test_only_the_services_may_import_the_database_libraries() -> None:
    linter = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    settings = linter["tool"]["importlinter"]
    database = next(
        contract
        for contract in settings["contracts"]
        if contract["type"] == "forbidden" and "sqlalchemy" in contract["forbidden_modules"]
    )

    assert settings["include_external_packages"] is True
    assert set(database["forbidden_modules"]) == {"sqlalchemy", "alembic"}
    assert set(database["source_modules"]) == {
        "weatherbot.models",
        "weatherbot.sources",
        "weatherbot.engine",
        "weatherbot.cli",
        "weatherbot.web",
    }
    assert database["allow_indirect_imports"] is True


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
