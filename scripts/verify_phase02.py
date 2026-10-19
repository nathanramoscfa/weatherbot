# scripts/verify_phase02.py
"""Verify Phase 2 with 47 independent static checks and the 26-row V1-V7 matrix.

The six mutually exclusive modes are --fast (offline, standard library only),
--py, --live, --security, --all, and --post. With no flag, run --fast plus
--py. Each mode includes static checks. Subprocesses use argument lists, never
a shell. Failures print identifiers and exception types, never scanned content.
The post mode reads GitHub settings and the operator's database through
``doctor``; it never changes either. Build output, live tests, and the
operations proof use temporary directories.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import sqlite3
import subprocess  # fixed argument lists, never a shell  # nosec B404
import sys
import tempfile
import time
import tomllib
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

if TYPE_CHECKING:
    import io

REPO_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "nathanramoscfa/weatherbot"
PHASE_1_TAG = "v2.0.0-phase-1"
PHASE_2_TAG = "v2.0.0-phase-2"
REGISTER = "docs/DATA_SOURCES.md"
CI_WORKFLOW = ".github/workflows/ci.yml"
PHASE_WORKFLOW = ".github/workflows/phase-verify.yml"
LIVE_WORKFLOW = ".github/workflows/live-smoke.yml"
MODELS = "src/weatherbot/models"
SOURCES = "src/weatherbot/sources"
SERVICES = "src/weatherbot/services"
VERSIONS = f"{SERVICES}/persistence/migrations/versions"
RECORDER = "scripts/record_fixtures.py"
ARRIVALS = "tests/fixtures/recorded/nhc-arrival-times"
MODES = ("fast", "py", "live", "security", "all", "post")
JSON_SCHEMA_2020_12 = "https://json-schema.org/draft/2020-12/schema"
PUBLIC_MODELS = frozenset(
    {
        "Provenance",
        "Geometry",
        "Location",
        "StormSummary",
        "Advisory",
        "AdvisoryNumber",
        "ConeGeometry",
        "TrackPoint",
        "ForecastTrack",
        "WatchWarningSegment",
        "WindRadii",
        "ArrivalTimeProduct",
        "OutlookArea",
        "WindProbabilityProduct",
        "NwsAlert",
        "NwsZone",
        "GeocodeResult",
        "Breakpoint",
        "TextProduct",
        "GisFeedItem",
        "OutlookGraphic",
        "MapCatalog",
        "OverlayCatalog",
        "DisplayLayer",
        "Snapshot",
    }
)
TIME_FUNCTIONS = frozenset(
    {
        "parse_nhc_local_time",
        "resolve_track_valid_time",
        "parse_synoptic_time",
        "from_epoch_ms",
        "resolve_arrival_label",
    }
)
# The baseline revision's 17 tables; revision 0002 adds drift_warnings (Step 6).
BASELINE_TABLES = frozenset(
    {
        "locations",
        "snapshots",
        "source_outcomes",
        "outcome_responses",
        "raw_responses",
        "response_bodies",
        "storms",
        "storm_observations",
        "advisories",
        "product_geometries",
        "text_products",
        "text_product_observations",
        "feed_items",
        "feed_item_observations",
        "alerts",
        "alert_observations",
        "settings",
    }
)
# Later phases' tables arrive as revisions with the code that writes them.
LATER_TABLES = re.compile(r"assessment|evidence|notification|heartbeat|briefing|ledger")
ARCHIVED_PAIR = frozenset(
    f"AL052019_036adv_{kind}_toa_34.kmz" for kind in ("earliest_reasonable", "most_likely")
)
NWS_SOURCES = ("nws-points", "nws-alerts-point", "nws-alerts-zone", "nws-zones")
SCHEMAS = ("locations", "fetch", "storms", "alerts", "doctor")
type Status = Literal["PASS", "FAIL", "SKIP"]
type Check = tuple[str, Callable[[], bool]]


@dataclass(frozen=True)
class Outcome:
    """One static check, suite, or V-matrix row."""

    id: str
    description: str
    status: Status
    reason: str = ""


def heading(text: str) -> None:
    """Print the precedent's section heading."""
    print(f"\n== {text} ==", flush=True)


def report(outcome: Outcome) -> Outcome:
    """Print a result without repository contents or private settings."""
    suffix = f" - {outcome.reason}" if outcome.reason else ""
    print(f"[{outcome.status}] {outcome.id} {outcome.description}{suffix}", flush=True)
    return outcome


def read(relative: str, root: Path = REPO_ROOT) -> str:
    """Read a repository text file, anchored independently of the caller's cwd."""
    return (root / relative).read_text(encoding="utf-8")


def object_of(value: object) -> dict[str, object]:
    """Require a JSON or TOML object without echoing its content."""
    if not isinstance(value, dict):
        raise TypeError
    return cast("dict[str, object]", value)


def array_of(value: object) -> list[object]:
    """Require an array without echoing its content."""
    if not isinstance(value, list):
        raise TypeError
    return cast("list[object]", value)


def json_file(relative: str) -> dict[str, object]:
    """Read one JSON object."""
    return object_of(json.loads(read(relative)))


def config(*keys: str) -> object:
    """Read a ``pyproject.toml`` value; a missing table or key raises and fails its check."""
    value: object = tomllib.loads(read("pyproject.toml"))
    for key in keys:
        value = object_of(value)[key]
    return value


def capture(
    argv: Sequence[str],
    *,
    timeout: int = 60,
    cwd: Path = REPO_ROOT,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Capture bounded tool output; callers choose safe fields to display."""
    executable = shutil.which(argv[0])
    if executable is None:
        raise FileNotFoundError
    return subprocess.run(  # noqa: S603 - argument list, no shell  # nosec B603
        [executable, *argv[1:]],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", **(env or {})},
    )


def git(*args: str, root: Path = REPO_ROOT) -> str:
    """Read Git metadata, failing closed on an unsuccessful command."""
    result = capture(["git", *args], cwd=root)
    result.check_returncode()
    return result.stdout.strip()


@cache
def index_files() -> frozenset[str]:
    """Snapshot the index once per invocation, including staged implementation files."""
    return frozenset(git("ls-files", "-z").split("\0")) - {""}


def tracked(*paths: str) -> set[str]:
    """Select exact files or directory prefixes from this invocation's index."""
    return {
        name
        for name in index_files()
        if not paths
        or any(name == path or name.startswith(path.rstrip("/") + "/") for path in paths)
    }


def files_exist(*paths: str) -> bool:
    """Require files on disk and in the index."""
    return set(paths) <= tracked(*paths) and all((REPO_ROOT / p).is_file() for p in paths)


def contains(relative: str, *tokens: str) -> bool:
    """Require each literal in one file."""
    text = read(relative)
    return all(token in text for token in tokens)


def job(workflow: str, name: str) -> str:
    """Read one two-space-indented job in the repository's workflow format."""
    match = re.search(
        rf"^  {re.escape(name)}:\n.*?(?=^  [\w-]+:|\Z)", read(workflow), re.MULTILINE | re.DOTALL
    )
    if match is None:
        raise ValueError
    return match[0]


def top_level_block(workflow: str, key: str) -> list[str]:
    """Return the non-blank lines nested under one top-level workflow key."""
    match = re.search(rf"^{re.escape(key)}:\n((?:[ \t]+\S.*\n|\n)*)", read(workflow), re.MULTILINE)
    if match is None:
        raise ValueError
    return [line.strip() for line in match[1].splitlines() if line.strip()]


def requirement_names(value: object) -> set[str]:
    """Name each requirement by its distribution, never by a prefix (``typer-slim``)."""
    names: set[str] = set()
    for item in array_of(value):
        match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", str(item))
        if match is None:
            raise ValueError
        names.add(match[0].lower())
    return names


def runtime_dependencies() -> set[str]:
    """Name the ``[project] dependencies``."""
    return requirement_names(config("project", "dependencies"))


@cache
def syntax(relative: str) -> ast.Module:
    """Parse one Python file once per invocation."""
    return ast.parse(read(relative), filename=relative)


def assigned(tree: ast.Module, name: str) -> ast.expr:
    """Return the value of a module-level ``name = ...`` or ``name: T = ...``."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return node.value
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
            and node.value is not None
        ):
            return node.value
    raise LookupError


def string_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level names bound to a string literal."""
    found: dict[str, str] = {}
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            found.update({t.id: value.value for t in targets if isinstance(t, ast.Name)})
    return found


def literal_strings(node: ast.AST) -> Iterator[str]:
    """Every string literal under ``node``, the literal parts of f-strings included."""
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            yield child.value


def class_fields(directory: str, name: str) -> set[str]:
    """The annotated fields one class declares in its own body, found under ``directory``."""
    classes = [
        node
        for relative in sorted(tracked(directory))
        if relative.endswith(".py")
        for node in ast.walk(syntax(relative))
        if isinstance(node, ast.ClassDef) and node.name == name
    ]
    if len(classes) != 1:
        raise LookupError
    return {
        node.target.id
        for node in classes[0].body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }


def defines(relative: str, *names: str) -> bool:
    """Require module-level classes, functions, or bindings with these names."""
    tree = syntax(relative)
    found = {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
    }
    for node in tree.body:
        if isinstance(node, ast.Assign):
            found |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found.add(node.target.id)
    return set(names) <= found


def imports_from(relative: str, module: str) -> set[str]:
    """The names one file imports from ``module``."""
    return {
        alias.name
        for node in ast.walk(syntax(relative))
        if isinstance(node, ast.ImportFrom) and node.module == module
        for alias in node.names
    }


def package_modules() -> list[str]:
    """Every tracked Python module of the package."""
    return sorted(name for name in tracked("src/weatherbot") if name.endswith(".py"))


def public_models() -> bool:
    """Check 1: the package's ``__all__`` exports every shared model."""
    relative = f"{MODELS}/__init__.py"
    names = ast.literal_eval(assigned(syntax(relative), "__all__"))
    return files_exist(relative) and set(cast("list[str]", names)) >= PUBLIC_MODELS


def models_dependencies() -> bool:
    """Check 2: Pydantic and Shapely at run time; Shapely gone from the dev group."""
    return {"pydantic", "shapely"} <= runtime_dependencies() and "shapely" not in (
        requirement_names(config("dependency-groups", "dev"))
    )


def models_lowest_layer() -> bool:
    """Check 3: the layers contract ends with the models."""
    contracts = [object_of(c) for c in array_of(config("tool", "importlinter", "contracts"))]
    layered = [c for c in contracts if c.get("name") == "Layers import downward only"]
    return len(layered) == 1 and array_of(layered[0]["layers"])[-1] == "weatherbot.models"


def models_io_ban() -> bool:
    """Check 4: the architecture test's I/O ban covers ``src/weatherbot/models``."""
    text = read("tests/test_architecture.py")
    return bool(
        re.search(r'^MODELS_DIRECTORY = .*"weatherbot" / "models"$', text, re.MULTILINE)
        and re.search(r"^IO_FREE_DIRECTORIES = \([^)]*\bMODELS_DIRECTORY\b", text, re.MULTILINE)
    )


def wind_probabilities_unowned() -> bool:
    """Check 5: issue #12's product carries no storm field."""
    fields = class_fields(MODELS, "WindProbabilityProduct")
    return bool(fields) and not any("storm" in f or "atcf" in f for f in fields)


def arrival_fields() -> bool:
    """Check 6: issue #11's product carries its own zone, publication, and origin."""
    return {"time_zone", "published_at", "origin"} <= class_fields(
        MODELS, "ArrivalTimeProduct"
    ) and "valid_at" in class_fields(MODELS, "ArrivalTimeLine")


def http_layer() -> bool:
    """Check 9: the HTTP foundation and its refused redirects."""
    relative = f"{SOURCES}/http.py"
    return (
        files_exist(relative, f"{SOURCES}/errors.py")
        and defines(relative, "HOST_INTERVALS", "ValidatorStore", "Fetcher")
        and "follow_redirects=False" in read(relative)
    )


def one_user_agent() -> bool:
    """Check 10: one User-Agent, built from the version and imported by the recorder."""
    value = assigned(syntax(f"{SOURCES}/__init__.py"), "USER_AGENT")
    from_version = isinstance(value, ast.JoinedStr) and any(
        isinstance(part, ast.FormattedValue)
        and isinstance(part.value, ast.Name)
        and part.value.id == "__version__"
        for part in value.values
    )
    literal = any(
        re.search(r"weatherbot/\d|\(\+https://", text) for text in literal_strings(syntax(RECORDER))
    )
    return (
        from_version
        and "USER_AGENT" in imports_from(RECORDER, "weatherbot.sources")
        and not literal
    )


def arcgis_parameters() -> bool:
    """Check 12: the shared query parameters, imported by the recorder."""
    relative = f"{SOURCES}/arcgis.py"
    dictionaries = [
        node
        for node in ast.walk(assigned(syntax(relative), "QUERY_PARAMETERS"))
        if isinstance(node, ast.Dict)
    ]
    if len(dictionaries) != 1:
        return False
    parameters = {
        cast("ast.Constant", key).value: cast("ast.Constant", value).value
        for key, value in zip(dictionaries[0].keys, dictionaries[0].values, strict=True)
    }
    return (
        parameters.get("outSR") == "4326"
        and parameters.get("geometryPrecision") == "5"
        and "QUERY_PARAMETERS" in imports_from(RECORDER, "weatherbot.sources.arcgis")
    )


def live_smoke_dispatch_only() -> bool:
    """Check 15: dispatch-only, read-only, and runs the live marker."""
    return (
        top_level_block(LIVE_WORKFLOW, "on") == ["workflow_dispatch:"]
        and top_level_block(LIVE_WORKFLOW, "permissions") == ["contents: read"]
        and "pytest -m live" in read(LIVE_WORKFLOW)
    )


def no_tls_bypass() -> bool:
    """Check 16: no package module disables verification or follows a redirect."""
    modules = package_modules()
    return bool(modules) and not any(
        token in read(relative)
        for relative in modules
        for token in ("verify=False", "follow_redirects=True")
    )


def register_section(title: str) -> str:
    """One ``## `` section of the register."""
    parts = re.split(rf"^## {re.escape(title)}\n", read(REGISTER), maxsplit=1, flags=re.MULTILINE)
    if len(parts) != 2:  # noqa: PLR2004 - before and after the heading
        raise LookupError
    return re.split(r"^## ", parts[1], maxsplit=1, flags=re.MULTILINE)[0]


def roster_fields() -> bool:
    """Check 17: the roster's fields v2 uses name the product objects the clients read."""
    bullet = re.search(
        r"^- \*\*Fields v2 uses:\*\*(.*?)(?=^- |\Z)",
        register_section("NHC current storms"),
        re.MULTILINE | re.DOTALL,
    )
    if bullet is None:
        return False
    used = {name.split(".")[0] for name in re.findall(r"`([A-Za-z0-9.]+)`", bullet[1])}
    return {
        "trackCone",
        "windSpeedProbabilitiesGIS",
        "earliestArrivalTimeTSWindsGIS",
        "mostLikelyTimeTSWindsGIS",
    } <= used


def register_rows() -> dict[str, list[str]]:
    """Read the register table by source id."""
    section = register_section("Register")
    rows = [
        [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        for line in section.splitlines()
        if line.startswith("| `")
    ]
    return {row[0]: row for row in rows}


def arrival_register() -> bool:
    """Check 18: the arrival-time KMZ row and its section."""
    row = register_rows()["nhc-arrival-times"]
    return (
        row[4] == "required"
        and date.fromisoformat(row[7]).isoformat() == row[7]
        and bool(register_section("Arrival-time KMZ").strip())
    )


def archived_pair_recorded() -> bool:
    """Check 19: a dated arrival-time manifest holds the archived Dorian 036 pair."""
    for path in sorted((REPO_ROOT / ARRIVALS).glob("*/manifest.json")):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.parent.name):
            continue
        captures = array_of(json_file(path.relative_to(REPO_ROOT).as_posix())["captures"])
        urls = {str(object_of(entry)["url"]).rsplit("/", 1)[-1] for entry in captures}
        if urls >= ARCHIVED_PAIR:
            return True
    return False


def defused_xml_only() -> bool:
    """Check 20: ``defusedxml`` at run time and no standard-library XML parser imported."""
    banned = ("xml.etree", "xml.dom", "xml.sax", "lxml")
    imported: set[str] = set()
    for relative in package_modules():
        for node in ast.walk(syntax(relative)):
            if isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
                imported |= {f"{node.module}.{alias.name}" for alias in node.names}
    return "defusedxml" in runtime_dependencies() and not any(
        name == root or name.startswith(root + ".") for name in imported for root in banned
    )


def recorder_sources() -> bool:
    """Check 22: the recorder's ``SOURCES`` keys include the arrival-time source."""
    tree = syntax(RECORDER)
    value = assigned(tree, "SOURCES")
    if not isinstance(value, ast.Dict):
        return False
    names = string_constants(tree)
    keys = {
        key.value if isinstance(key, ast.Constant) else names.get(key.id)
        for key in value.keys
        if isinstance(key, ast.Constant | ast.Name)
    }
    return "nhc-arrival-times" in keys


def arrival_url_pattern() -> bool:
    """Check 23: the KMZ pattern is anchored on NHC's storm-graphics API (escaped form)."""
    value = assigned(syntax(f"{SOURCES}/nhc_arrival_times.py"), "ARRIVAL_KMZ_URL")
    return isinstance(value, ast.Call) and any(
        text.startswith(r"^https://www\.nhc\.noaa\.gov/storm_graphics/api/")
        for argument in value.args
        for text in literal_strings(argument)
    )


def point_strings_confined() -> bool:
    """Check 28: only the NWS client and the HTTP redaction hold ``/points/`` or ``point=``."""
    holders = {
        relative
        for relative in package_modules()
        if any("/points/" in text or "point=" in text for text in literal_strings(syntax(relative)))
    }
    allowed = {f"{SOURCES}/nws.py", f"{SOURCES}/http.py"}
    return f"{SOURCES}/nws.py" in holders and holders <= allowed


def is_revision(relative: str) -> bool:
    """Whether a path under the versions directory is a revision module."""
    return relative.endswith(".py") and not relative.endswith("__init__.py")


def revision_record(tree: ast.Module) -> tuple[str, str | None, set[str]]:
    """One revision module's id, its parent, and the tables it creates."""
    revision = ast.literal_eval(assigned(tree, "revision"))
    parent = ast.literal_eval(assigned(tree, "down_revision"))
    tables = {
        str(cast("ast.Constant", node.args[0]).value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_table"
    }
    return cast("str", revision), cast("str | None", parent), tables


def revisions() -> dict[str, tuple[str | None, set[str]]]:
    """Each migration revision's parent and the tables it creates, in the working tree."""
    found: dict[str, tuple[str | None, set[str]]] = {}
    for relative in sorted(tracked(VERSIONS)):
        if is_revision(relative):
            revision, parent, tables = revision_record(syntax(relative))
            found[revision] = (parent, tables)
    return found


def tagged(relative: str, root: Path = REPO_ROOT) -> str:
    """Read one file as Phase 2's tag recorded it; a missing tag or path raises."""
    return git("show", f"{PHASE_2_TAG}:{relative}", root=root)


def tagged_tree(prefix: str, root: Path = REPO_ROOT) -> set[str]:
    """List the files under ``prefix`` in Phase 2's tagged tree; a missing tag raises."""
    return set(
        git("ls-tree", "-r", "--name-only", PHASE_2_TAG, "--", prefix, root=root).splitlines()
    )


def migration_tables() -> bool:
    """Check 30: the 17-table baseline and revision 0002's ``drift_warnings``."""
    history = revisions()
    baselines = [tables for parent, tables in history.values() if parent is None]
    return (
        len(baselines) == 1
        and baselines[0] == set(BASELINE_TABLES)
        and history.get("0002") == ("0001", {"drift_warnings"})
    )


def no_later_tables(root: Path = REPO_ROOT) -> bool:
    """Check 31: Phase 2's revisions, read at its tag, create no later phase's table.

    Later phases add their tables in revisions of their own, so the check reads the
    revisions Phase 2 shipped, at ``v2.0.0-phase-2``, with the same AST reading as check
    30, and requires each to be unchanged in the working tree: the blob Git would store
    for the file today is the tagged blob, whatever line endings the checkout wrote.
    """
    shipped = sorted(name for name in tagged_tree(VERSIONS, root) if is_revision(name))
    for relative in shipped:
        _, _, tables = revision_record(ast.parse(tagged(relative, root), filename=relative))
        if any(LATER_TABLES.search(table) for table in tables):
            return False
        if git("hash-object", "--", relative, root=root) != git(
            "rev-parse", f"{PHASE_2_TAG}:{relative}", root=root
        ):
            return False
    return bool(shipped)


def isolation_fixture() -> bool:
    """Check 32: the autouse fixture isolates both directories and keeps two tool variables."""
    relative = "tests/conftest.py"
    keep = ast.literal_eval(cast("ast.Call", assigned(syntax(relative), "TOOL_VARIABLES")).args[0])
    return contains(
        relative,
        "@pytest.fixture(autouse=True)",
        'monkeypatch.setenv("WEATHERBOT_CONFIG_DIR"',
        'monkeypatch.setenv("WEATHERBOT_DATA_DIR"',
    ) and set(cast("set[str]", keep)) == {"WEATHERBOT_DENYLIST", "WEATHERBOT_CORPUS_CACHE"}


def database_contract() -> bool:
    """Check 33: external packages in the graph; the database libraries stay in services."""
    forbidden = [
        object_of(c)
        for c in array_of(config("tool", "importlinter", "contracts"))
        if object_of(c)["type"] == "forbidden"
        and {"sqlalchemy", "alembic"} <= set(array_of(object_of(c)["forbidden_modules"]))
    ]
    layers = {f"weatherbot.{name}" for name in ("models", "sources", "engine", "cli", "web")}
    return config("tool", "importlinter", "include_external_packages") is True and any(
        layers <= set(array_of(c["source_modules"])) for c in forbidden
    )


def commands_registered() -> bool:
    """Check 36: the root app and the ``locations`` group register every command."""
    root = read("src/weatherbot/cli/__init__.py")
    group = read("src/weatherbot/cli/locations.py")
    return (
        "app.add_typer(locations.app)" in root
        and all(
            f'app.command("{name}")' in root for name in ("fetch", "storms", "alerts", "doctor")
        )
        and 'name="locations"' in group
        and all(f'@app.command("{name}")' in group for name in ("add", "list", "remove"))
    )


def schemas_committed() -> bool:
    """Check 37: one valid 2020-12 schema per document."""
    return all(
        json_file(f"docs/schema/{name}.schema.json").get("$schema") == JSON_SCHEMA_2020_12
        and files_exist(f"docs/schema/{name}.schema.json")
        for name in SCHEMAS
    )


def disclaimer_packaged() -> bool:
    """Check 39: the packaged disclaimer is tracked and compared with the root copy."""
    text = read("tests/cli/test_documents.py")
    return (
        files_exist("src/weatherbot/DISCLAIMER.md", "DISCLAIMER.md")
        and '"src" / "weatherbot" / "DISCLAIMER.md"' in text
        and '(REPOSITORY_ROOT / "DISCLAIMER.md")' in text
    )


def gate_wired() -> bool:
    """Check 43: the four gate hooks, and ``--security`` in every phase entry."""
    ids = set(re.findall(r"^\s*- id: ([\w-]+)", read(".pre-commit-config.yaml"), re.MULTILINE))
    return {"gitleaks", "bandit", "pip-audit", "personal-data"} <= ids and (
        "scripts/verify_phase${{ matrix.phase }}.py --security" in job(PHASE_WORKFLOW, "verify")
    )


def phase_matrix() -> set[str]:
    """Read the flow-form phase matrix as strings."""
    match = re.search(r"^\s+phase:\s*\[([^]]+)\]", job(PHASE_WORKFLOW, "verify"), re.MULTILINE)
    if match is None:
        raise ValueError
    return {part.strip().strip("\"'") for part in match[1].split(",")}


def matrix_includes_02() -> bool:
    """Check 47: matrix entry 02 beside 01."""
    return {"01", "02"} <= phase_matrix()


STATIC_CHECKS: tuple[Check, ...] = (
    # Step 1 — domain models
    ("models package exports every shared model", public_models),
    ("pydantic and shapely at run time, shapely not in dev", models_dependencies),
    ("models are the lowest layer", models_lowest_layer),
    ("architecture test bans I/O in the models", models_io_ban),
    ("wind probabilities carry no storm field (issue #12)", wind_probabilities_unowned),
    ("arrival products carry zone, publication, origin (issue #11)", arrival_fields),
    ("time functions defined", lambda: defines(f"{MODELS}/times.py", *TIME_FUNCTIONS)),
    (
        f"Phase 1 checks 7, 9, 12 read {PHASE_1_TAG}",
        lambda: contains("scripts/verify_phase01.py", PHASE_1_TAG, "ls-tree"),
    ),
    # Step 2 — HTTP foundation and NHC map clients
    ("HTTP layer with refused redirects", http_layer),
    ("one User-Agent from the version, imported by the recorder", one_user_agent),
    ("httpx at run time", lambda: "httpx" in runtime_dependencies()),
    ("shared ArcGIS query parameters", arcgis_parameters),
    (
        "roster and map clients tracked",
        lambda: files_exist(f"{SOURCES}/nhc_current_storms.py", f"{SOURCES}/nhc_map.py"),
    ),
    (
        "field-coverage contract tracked",
        lambda: files_exist("tests/contract/test_field_coverage.py"),
    ),
    ("live smoke is dispatch-only and read-only", live_smoke_dispatch_only),
    ("no TLS bypass or followed redirect", no_tls_bypass),
    ("roster fields name the product objects", roster_fields),
    # Step 3 — NHC products
    ("arrival-time register row and section", arrival_register),
    ("archived Dorian 036 pair recorded", archived_pair_recorded),
    ("defusedxml only for XML", defused_xml_only),
    (
        "product clients tracked",
        lambda: files_exist(
            *(
                f"{SOURCES}/{name}.py"
                for name in (
                    "nhc_arrival_times",
                    "nhc_text_products",
                    "nhc_outlook_graphics",
                    "nhc_gis_rss",
                    "catalogs",
                    "markup",
                )
            )
        ),
    ),
    ("recorder records nhc-arrival-times", recorder_sources),
    ("arrival KMZ pattern anchored on NHC", arrival_url_pattern),
    (
        "Step 3 contract tests tracked",
        lambda: (
            files_exist(
                "tests/contract/test_product_captures.py",
                *(
                    f"tests/sources/test_{name}.py"
                    for name in (
                        "nhc_arrival_times",
                        "nhc_text_products",
                        "nhc_outlook_graphics",
                        "nhc_gis_rss",
                        "catalogs",
                    )
                ),
            )
            and contains(
                "tests/contract/test_product_captures.py",
                "corpus-manifest.json",
                "def test_the_archived_pair_is_the_replay_corpus_pinned_bytes",
            )
        ),
    ),
    # Step 4 — NWS and geocoding clients
    (
        "NWS and Nominatim clients, format_point",
        lambda: (
            files_exist(f"{SOURCES}/nws.py", f"{SOURCES}/nominatim.py")
            and defines(f"{SOURCES}/nws.py", "format_point")
        ),
    ),
    (
        "alerts keep issue #10's inputs",
        lambda: (
            {"found_by", "affected_zone_ids", "geocode_same", "geocode_ugc"}
            <= class_fields(MODELS, "NwsAlert")
        ),
    ),
    (
        "location-source contract tests tracked",
        lambda: (
            files_exist("tests/contract/test_nws_captures.py")
            and contains("tests/contract/test_nws_captures.py", *NWS_SOURCES, "geocode-nominatim")
        ),
    ),
    ("coordinates in URL strings only in the NWS client", point_strings_confined),
    # Step 5 — persistence and configuration
    (
        "sqlalchemy, alembic, platformdirs at run time",
        lambda: {"sqlalchemy", "alembic", "platformdirs"} <= runtime_dependencies(),
    ),
    ("baseline tables and revision 0002", migration_tables),
    (f"no later phase's table in the revisions at {PHASE_2_TAG}", no_later_tables),
    ("test isolation fixture", isolation_fixture),
    ("database contract keeps sqlalchemy in services", database_contract),
    (
        "database files ignored",
        lambda: {"*.sqlite3", "*.sqlite3-*"} <= set(read(".gitignore").splitlines()),
    ),
    (
        "wheel migration smoke in the package job",
        lambda: all(
            t in job(CI_WORKFLOW, "package") for t in ("WEATHERBOT_DATA_DIR", "open_database")
        ),
    ),
    # Step 6 — services and the first CLI commands
    ("commands registered", commands_registered),
    ("committed JSON Schemas", schemas_committed),
    ("schema exporter tracked", lambda: files_exist("scripts/export_schemas.py")),
    ("packaged disclaimer compared with the root copy", disclaimer_packaged),
    (
        "snapshot and locations services tracked",
        lambda: files_exist(f"{SERVICES}/snapshots.py", f"{SERVICES}/locations.py"),
    ),
    (
        "README Commands section",
        lambda: bool(re.search(r"^## Commands$", read("README.md"), re.MULTILINE)),
    ),
    (
        "live command tests under the live marker",
        lambda: (
            files_exist("tests/live/test_cli_live.py")
            and "pytest.mark.live" in read("tests/live/test_cli_live.py")
        ),
    ),
    ("security gate still wired", gate_wired),
    # Step 7 — self-checks
    (
        "tracked verifier declares all six modes",
        lambda: (
            files_exist("scripts/verify_phase02.py")
            and all(f'"{mode}"' in read("scripts/verify_phase02.py") for mode in MODES)
        ),
    ),
    ("QA findings document exists", (REPO_ROOT / "docs/phase02-qa-findings.md").is_file),
    ("phase roadmap exists", (REPO_ROOT / "docs/roadmap/phase02-roadmap.md").is_file),
    ("phase verification matrix includes 01 and 02", matrix_includes_02),
)


def run_static_checks() -> list[Outcome]:
    """Run every static check even when a preceding check fails."""
    heading(f"Static checks ({len(STATIC_CHECKS)})")
    outcomes: list[Outcome] = []
    for number, (description, check) in enumerate(STATIC_CHECKS, 1):
        reason = ""
        try:
            passed = check()
        except Exception as error:  # noqa: BLE001 - independent checks; no content in errors
            passed = False
            reason = type(error).__name__
        outcomes.append(
            report(Outcome(f"{number:02d}", description, "PASS" if passed else "FAIL", reason))
        )
    return outcomes


def run_command(
    item_id: str,
    description: str,
    argv: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
) -> Outcome:
    """Run a known gate tool, streaming its existing redacted output."""
    print(f"\n$ {' '.join(argv)}", flush=True)
    executable = shutil.which(argv[0])
    if executable is None:
        return report(Outcome(item_id, description, "FAIL", "tool unavailable"))
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell  # nosec B603
            [executable, *argv[1:]],
            cwd=REPO_ROOT,
            check=False,
            timeout=3600,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", **(env or {})},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return report(Outcome(item_id, description, "FAIL", type(error).__name__))
    return report(
        Outcome(
            item_id,
            description,
            "PASS" if result.returncode == 0 else "FAIL",
            "" if result.returncode == 0 else f"exit code {result.returncode}",
        )
    )


def aggregate(item_id: str, description: str, outcomes: Sequence[Outcome]) -> Outcome:
    """A sweep passes only if every constituent check actually passes."""
    failed = [o.id for o in outcomes if o.status == "FAIL"]
    skipped = [o.id for o in outcomes if o.status == "SKIP"]
    status: Status = "FAIL" if failed or not outcomes else "SKIP" if skipped else "PASS"
    return Outcome(item_id, description, status, ", ".join(failed or skipped))


@dataclass(frozen=True)
class PytestRun:
    """A pytest run's exit outcome and the status of each test, keyed by test id."""

    outcome: Outcome
    cases: Mapping[str, str]


def junit_cases(path: Path) -> dict[str, str]:
    """Read the statuses from the JUnit report pytest just wrote; a missing report is empty."""
    if not path.is_file():
        return {}
    # The report is pytest's own output in a temporary directory, never network data.
    from defusedxml import ElementTree  # noqa: PLC0415 - --py and later, never --fast

    cases: dict[str, str] = {}
    for case in ElementTree.parse(path).iter("testcase"):
        tags = {child.tag for child in case}
        status = (
            "failed"
            if tags & {"failure", "error"}
            else "skipped"
            if "skipped" in tags
            else "passed"
        )
        cases[f"{case.get('classname', '')}::{case.get('name', '')}"] = status
    return cases


def pytest_run(item_id: str, description: str, *arguments: str) -> PytestRun:
    """Run pytest once with a JUnit report, so V rows can select their evidence."""
    with tempfile.TemporaryDirectory(prefix="weatherbot-pytest-") as directory:
        junit = Path(directory) / "junit.xml"
        outcome = run_command(
            item_id,
            description,
            ["uv", "run", "pytest", *arguments, f"--junitxml={junit}"],
            # Belt and braces: the autouse fixture already moves every test into tmp_path.
            env={
                "WEATHERBOT_CONFIG_DIR": str(Path(directory) / "config"),
                "WEATHERBOT_DATA_DIR": str(Path(directory) / "data"),
            },
        )
        return PytestRun(outcome, junit_cases(junit))


@dataclass(frozen=True)
class Select:
    """Tests in one module or directory (dotted), optionally only those whose name has a part."""

    module: str
    name: str = ""

    def matches(self, test_id: str) -> bool:
        """Whether a ``classname::name`` test id falls under this selection."""
        classname, _, name = test_id.partition("::")
        return (classname == self.module or classname.startswith(self.module + ".")) and (
            self.name in name
        )


def evidence(item_id: str, run: PytestRun, selections: Sequence[Select]) -> Outcome:
    """Each selection must match at least one test; any failure fails, any skip is not a pass."""
    statuses: list[str] = []
    for selection in selections:
        chosen = [status for test, status in run.cases.items() if selection.matches(test)]
        if not chosen:
            return Outcome(item_id, "selected tests", "FAIL", f"nothing under {selection.module}")
        statuses.extend(chosen)
    failed = statuses.count("failed")
    skipped = statuses.count("skipped")
    status: Status = "FAIL" if failed else "SKIP" if skipped else "PASS"
    reason = f"{failed} failed" if failed else f"{skipped} skipped" if skipped else ""
    return Outcome(item_id, f"{len(statuses)} selected tests", status, reason)


def install_wheel(root: Path, results: list[Outcome]) -> Path | None:
    """Build the wheel and install it into a fresh environment; return its Python."""
    dist = root / "dist"
    environment = root / "smoke"
    results.append(
        run_command("pkg.build", "build distributions", ["uv", "build", "--out-dir", str(dist)])
    )
    wheels = list(dist.glob("*.whl"))
    if len(wheels) != 1:
        results.append(Outcome("pkg.wheel", "exactly one wheel", "FAIL", "expected one wheel"))
        return None
    results.append(run_command("pkg.venv", "fresh environment", ["uv", "venv", str(environment)]))
    results.append(
        run_command(
            "pkg.install",
            "install wheel",
            ["uv", "pip", "install", "--python", str(environment), str(wheels[0])],
        )
    )
    return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


# Run by the installed wheel's Python, outside the checkout: a new database at the head.
MIGRATION_SMOKE = """\
import sys
from pathlib import Path

import weatherbot
from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import current_revision, head_revision, open_database

assert Path(weatherbot.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
paths = AppPaths.resolve()
assert not paths.database_path.exists()
with open_database(paths) as database:
    assert current_revision(database.engine) == head_revision() == database.revision
    assert database.backup_path is None
"""


def package_smoke() -> Outcome:
    """Build and install the wheel; check its version and a new database at the head."""
    with tempfile.TemporaryDirectory(prefix="weatherbot-package-") as directory:
        root = Path(directory)
        results: list[Outcome] = []
        python = install_wheel(root, results)
        if python is None:
            return report(aggregate("py.package", "installed wheel and migrations", results))
        executable = python.parent / ("weatherbot.exe" if os.name == "nt" else "weatherbot")
        try:
            version = capture([str(executable), "--version"], cwd=root)
            passed = version.returncode == 0 and version.stdout.strip() == config(
                "project", "version"
            )
        except (OSError, subprocess.SubprocessError):
            passed = False
        results.append(
            Outcome("pkg.version", "version matches project", "PASS" if passed else "FAIL")
        )
        try:
            migrated = capture(
                [str(python), "-c", MIGRATION_SMOKE],
                cwd=root,
                timeout=120,
                env={
                    "WEATHERBOT_CONFIG_DIR": str(root / "config"),
                    "WEATHERBOT_DATA_DIR": str(root / "data"),
                },
            )
            passed = migrated.returncode == 0
        except (OSError, subprocess.SubprocessError):
            passed = False
        results.append(Outcome("pkg.migrate", "new database at head", "PASS" if passed else "FAIL"))
        return report(aggregate("py.package", "installed wheel and migrations", results))


@dataclass(frozen=True)
class PySuites:
    """The code-quality tools, the offline test run, and the package smoke."""

    tools: list[Outcome]
    tests: PytestRun
    package: Outcome

    def outcomes(self) -> list[Outcome]:
        """Every suite outcome, in run order."""
        return [*self.tools, self.tests.outcome, self.package]


def py_suites() -> PySuites:
    """Run the same Python suites as CI, plus the installed-wheel smoke."""
    heading("Python suites (--py)")
    commands = (
        ("lint", ["ruff", "check"]),
        ("format", ["ruff", "format", "--check"]),
        ("types", ["pyright"]),
        ("imports", ["lint-imports"]),
    )
    tools = [run_command(f"py.{name}", name, ["uv", "run", *args]) for name, args in commands]
    tests = pytest_run("py.tests", "offline tests (unit, model, contract, replay, command)")
    return PySuites(tools, tests, package_smoke())


def live_suite() -> PytestRun:
    """Run every live test against the real services, landmarks only."""
    heading("Live services (--live)")
    return pytest_run("live.tests", "live clients and commands, landmarks only", "-m", "live")


def security_suites() -> list[Outcome]:
    """Run the four-check gate without ever reading a private denylist ourselves."""
    heading("Security gate (--security)")
    results: list[Outcome] = []
    if shutil.which("gitleaks"):
        results.append(
            run_command(
                "sec.secrets",
                "redacted history scan",
                ["gitleaks", "git", "--redact", "--no-banner", "."],
            )
        )
    else:
        results.append(
            report(
                Outcome(
                    "sec.secrets",
                    "redacted history scan",
                    "FAIL" if os.environ.get("CI") else "SKIP",
                    "gitleaks not installed",
                )
            )
        )
    commands = (
        ("sast", ["bandit", "-c", "pyproject.toml", "-q", "-r", "src", "scripts"]),
        ("audit", ["python", "scripts/audit_deps.py"]),
    )
    results.extend(
        run_command(f"sec.{name}", name, ["uv", "run", *args]) for name, args in commands
    )
    ci = ["--ci"] if os.environ.get("CI") else []
    results.extend(
        run_command(
            f"sec.{mode[2:]}",
            "personal-data " + mode,
            ["uv", "run", "python", "scripts/check_personal_data.py", mode, *ci],
        )
        for mode in ("--all", "--self-test")
    )
    return results


def github_api(endpoint: str) -> object:
    """Read GitHub through gh's authentication; never expose its raw error output."""
    result = capture(["gh", "api", f"repos/{REPOSITORY}/{endpoint}"])
    result.check_returncode()
    return json.loads(result.stdout) if result.stdout.strip() else None


def latest_run(workflow: str) -> dict[str, object]:
    """Read the latest main run for a workflow, preserving its commit identity."""
    payload = object_of(github_api(f"actions/workflows/{workflow}/runs?branch=main&per_page=1"))
    runs = array_of(payload["workflow_runs"])
    if not runs:
        raise ValueError
    return object_of(runs[0])


def protection_requires_both() -> bool:
    """``main`` still requires the gate and the aggregate phase check, strictly."""
    checks = object_of(object_of(github_api("branches/main/protection"))["required_status_checks"])
    return {"gate", "phase-verify"} <= set(array_of(checks["contexts"])) and checks[
        "strict"
    ] is True


def phase_entry_green(entry: str) -> bool:
    """On ``main``: the latest phase run at HEAD; on a branch: its PR's checks, all green."""
    name = f"phase-verify ({entry})"
    if git("branch", "--show-current") == "main":
        run = latest_run("phase-verify.yml")
        jobs = object_of(github_api(f"actions/runs/{run['id']}/jobs"))
        conclusions = {
            object_of(j)["name"]: object_of(j)["conclusion"] for j in array_of(jobs["jobs"])
        }
        return (
            run["conclusion"] == "success"
            and run["head_sha"] == git("rev-parse", "HEAD")
            and conclusions.get(name) == "success"
        )
    result = capture(["gh", "pr", "checks", "--json", "name,bucket"])
    result.check_returncode()
    rows = [object_of(row) for row in array_of(json.loads(result.stdout))]
    return (
        bool(rows)
        and all(row["bucket"] == "pass" for row in rows)
        and any(row["name"] == name for row in rows)
    )


def issues_closed(*numbers: int) -> bool:
    """Every named issue is closed."""
    return all(object_of(github_api(f"issues/{n}"))["state"] == "closed" for n in numbers)


def phase_one_post() -> bool:
    """Phase 1's own ``--post`` exits 0 with all 75 checks passing; only its totals print."""
    result = capture(["uv", "run", "python", "scripts/verify_phase01.py", "--post"], timeout=3600)
    totals = dict(
        re.findall(r"^  (passed|failed|skipped|total)\s+(\d+)$", result.stdout, re.MULTILINE)
    )
    print(f"  verify_phase01.py --post: {totals or 'no summary'}; exit {result.returncode}")
    return result.returncode == 0 and totals == {
        "passed": "75",
        "failed": "0",
        "skipped": "0",
        "total": "75",
    }


def doctor(
    arguments: Sequence[str], *, cwd: Path, env: Mapping[str, str] | None = None
) -> tuple[int, dict[str, object]]:
    """Run this checkout's ``doctor --json``; return its exit status and the document's data."""
    result = capture(
        [sys.executable, "-m", "weatherbot", "doctor", "--json", *arguments],
        cwd=cwd,
        timeout=600,
        env=env,
    )
    return result.returncode, object_of(json.loads(result.stdout)["data"])


def operator_database_at_head() -> bool:
    """``doctor`` reports the operator's database at the head; only the revision prints."""
    with tempfile.TemporaryDirectory(prefix="weatherbot-doctor-") as directory:
        _, data = doctor([], cwd=Path(directory))
    database = object_of(data["database"])
    checks = {object_of(c)["name"]: object_of(c)["status"] for c in array_of(data["checks"])}
    print(f"  operator database: revision {database['revision']}, head {database['head']}")
    return database["at_head"] is True and checks.get("migrations") == "pass"


def doctor_alarm() -> bool:
    """The operations proof: a database stamped with an unknown revision FAILs and exits 1."""
    with tempfile.TemporaryDirectory(prefix="weatherbot-alarm-") as directory:
        root = Path(directory)
        env = {
            "WEATHERBOT_CONFIG_DIR": str(root / "config"),
            "WEATHERBOT_DATA_DIR": str(root / "data"),
        }
        created, _ = doctor(["--offline"], cwd=root, env=env)
        database = root / "data" / "weatherbot.sqlite3"
        with sqlite3.connect(database) as connection:
            connection.execute("UPDATE alembic_version SET version_num = 'unknown-revision'")
        connection.close()
        status, data = doctor(["--offline"], cwd=root, env=env)
    checks = {object_of(c)["name"]: object_of(c)["status"] for c in array_of(data["checks"])}
    print(f"  stamped database: doctor exit {status}, database check {checks.get('database')}")
    return (
        created == 0 and status == 1 and checks.get("database") == "fail" and data["failed"] is True
    )


def probe(item_id: str, description: str, check: Callable[[], bool]) -> Outcome:
    """Report a bounded independent post-check without leaking exception text."""
    try:
        passed = check()
        reason = "" if passed else "readback did not meet the criterion"
    except Exception as error:  # noqa: BLE001 - report each post-check independently
        passed = False
        reason = type(error).__name__
    return report(Outcome(item_id, description, "PASS" if passed else "FAIL", reason))


def post_matrix(statics: Sequence[Outcome]) -> list[Outcome]:
    """Run shared suites once and report exactly V1.1 through V7.4 (26 rows)."""
    py = py_suites()
    live = live_suite()
    security = security_suites()
    heading("GitHub, Phase 1, and the operator's machine (--post)")
    phase_01 = probe("post.phase-01", "phase-verify (01) green", lambda: phase_entry_green("01"))
    phase_02 = probe("post.phase-02", "phase-verify (02) green", lambda: phase_entry_green("02"))
    protection = probe(
        "post.protection", "main requires gate and phase-verify", protection_requires_both
    )
    smoke = probe(
        "post.live-smoke",
        "latest main live-smoke run green",
        lambda: latest_run("live-smoke.yml")["conclusion"] == "success",
    )
    issues = probe("post.issues", "issues #11 and #12 closed", lambda: issues_closed(11, 12))
    phase_one = probe("post.verify-01", "verify_phase01.py --post: 75 PASS", phase_one_post)
    operator = probe("post.doctor", "doctor: operator database at head", operator_database_at_head)
    alarm = probe("post.alarm", "doctor: unknown revision FAILs, exit 1", doctor_alarm)
    heading("Post-implementation verification (V1-V7)")
    outcomes: list[Outcome] = []

    def static_row(vid: str, first: int, last: int) -> None:
        outcomes.append(
            report(
                aggregate(vid, f"Static checks {first}-{last} all PASS", statics[first - 1 : last])
            )
        )

    def row(vid: str, description: str, constituents: Sequence[Outcome]) -> None:
        outcomes.append(report(aggregate(vid, description, constituents)))

    def tests(
        vid: str,
        description: str,
        run: PytestRun,
        *selections: Select,
        extra: Sequence[Outcome] = (),
    ) -> None:
        row(vid, description, [evidence(f"{vid}.tests", run, selections), *extra])

    static_row("V1.1", 1, 8)
    tests(
        "V1.2",
        "tests/models/ pass; lint, format, strict types, layer contracts clean",
        py.tests,
        Select("tests.models"),
        Select("tests.test_architecture"),
        extra=[*py.tools, py.tests.outcome],
    )
    tests(
        "V1.3",
        f"phase-verify (01) green; checks 7, 9, 12 read {PHASE_1_TAG}",
        py.tests,
        Select("tests.test_phase01_verification"),
        extra=[phase_01],
    )
    row("V1.4", "verify_phase01.py --post reports 75 PASS", [phase_one])
    static_row("V2.1", 9, 17)
    tests(
        "V2.2",
        "HTTP layer, roster and map contract tests, redaction included",
        py.tests,
        Select("tests.sources.test_http"),
        Select("tests.sources.test_arcgis"),
        Select("tests.sources.test_nhc_current_storms"),
        Select("tests.sources.test_nhc_map"),
        Select("tests.contract.test_recorded_fixtures"),
    )
    tests(
        "V2.3",
        "field-coverage contract",
        py.tests,
        Select("tests.contract.test_field_coverage"),
    )
    row("V2.4", "latest live-smoke.yml run on main green", [smoke])
    static_row("V3.1", 18, 24)
    tests(
        "V3.2",
        "Step 3 contract and hardening tests",
        py.tests,
        Select("tests.contract.test_product_captures"),
        Select("tests.sources.test_nhc_arrival_times"),
        Select("tests.sources.test_nhc_text_products"),
        Select("tests.sources.test_nhc_outlook_graphics"),
        Select("tests.sources.test_nhc_gis_rss"),
        Select("tests.sources.test_catalogs"),
    )
    tests(
        "V3.3",
        "archived pair matches corpus checksums; labels resolve",
        py.tests,
        Select("tests.contract.test_product_captures", "archived_pair_is_the_replay_corpus"),
        Select("tests.sources.test_nhc_arrival_times", "archived_pair_resolves_every_label"),
    )
    row("V3.4", "issues #11 and #12 closed", [issues])
    static_row("V4.1", 25, 28)
    tests(
        "V4.2",
        "location-source contract tests, FLC086-shaped merge included",
        py.tests,
        Select("tests.contract.test_nws_captures"),
        Select("tests.sources.test_nws"),
        Select("tests.sources.test_nominatim"),
    )
    tests(
        "V4.3",
        "coordinate-hygiene tests",
        py.tests,
        Select("tests.sources.test_http", "coordinate"),
        Select("tests.sources.test_nws", "carries_a_coordinate"),
        Select("tests.sources.test_nominatim", "carries_a_coordinate"),
        Select("tests.models.test_privacy"),
        Select("tests.cli.test_cli_privacy"),
    )
    static_row("V5.1", 29, 35)
    tests(
        "V5.2",
        "migration, backup, refusal, and round-trip tests",
        py.tests,
        Select("tests.services.test_database"),
        Select("tests.services.test_repositories", "saved_and_loaded_back_equal"),
    )
    row("V5.3", "installed wheel opens a new database at head", [py.package])
    row("V5.4", "doctor: operator database at head; unknown revision alarms", [operator, alarm])
    static_row("V6.1", 36, 43)
    tests(
        "V6.2",
        "command and schema tests",
        py.tests,
        Select("tests.cli"),
        Select("tests.test_cli"),
        Select("tests.services.test_snapshots"),
        Select("tests.services.test_locations"),
        Select("tests.contract.test_doctor_register"),
    )
    tests(
        "V6.3",
        "live command tests for both landmarks (whole live suite)",
        live,
        Select("tests.live.test_cli_live"),
        extra=[live.outcome],
    )
    tests(
        "V7.1",
        "verify_phase02.py --fast exits 0 on Ubuntu CI",
        py.tests,
        Select("tests.test_phase02_verification"),
        extra=[phase_02],
    )
    row("V7.2", "matrix includes 01 and 02 under the required aggregate", [statics[46], protection])
    static_row("V7.3", 1, 47)
    row("V7.4", "verify_phase02.py --security exits 0", security)
    return outcomes


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the six mutually exclusive modes; default to static plus Python."""
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    for mode in MODES:
        group.add_argument(f"--{mode}", action="store_true")
    return parser.parse_args(argv)


def summary(mode: str, outcomes: Sequence[Outcome], elapsed: float) -> int:
    """Print the precedent's final count table and fail on any failed check."""
    heading("Summary")
    counts = {
        status: sum(o.status == status for o in outcomes) for status in ("PASS", "FAIL", "SKIP")
    }
    for label, value in (
        ("mode", mode),
        ("passed", counts["PASS"]),
        ("failed", counts["FAIL"]),
        ("skipped", counts["SKIP"]),
        ("total", len(outcomes)),
        ("elapsed", f"{elapsed:.1f}s"),
    ):
        print(f"  {label:<8} {value}")
    failed = [o.id for o in outcomes if o.status == "FAIL"]
    print("\nFAILED: " + ", ".join(failed) if failed else "\nOK", flush=True)
    return int(bool(failed))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected mode, keeping static checks in every invocation."""
    if hasattr(sys.stdout, "reconfigure"):
        cast("io.TextIOWrapper[io.BufferedWriter]", sys.stdout).reconfigure(
            encoding="utf-8", errors="replace"
        )
    args = parse_args(argv)
    mode = next((name for name in MODES if getattr(args, name)), "default (fast + py)")
    started = time.perf_counter()
    statics = run_static_checks()
    outcomes = list(statics)
    if mode in ("py", "all", "default (fast + py)"):
        outcomes.extend(py_suites().outcomes())
    if mode in ("live", "all"):
        outcomes.append(live_suite().outcome)
    if mode in ("security", "all"):
        outcomes.extend(security_suites())
    if mode == "post":
        outcomes.extend(post_matrix(statics))
    return summary(mode, outcomes, time.perf_counter() - started)


if __name__ == "__main__":
    raise SystemExit(main())
