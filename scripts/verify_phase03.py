# scripts/verify_phase03.py
"""Verify Phase 3 with 52 independent static checks and the 28-row V1-V7 matrix.

The six mutually exclusive modes are --fast (offline, standard library only),
--py, --live, --security, --all, and --post. With no flag, run --fast plus
--py. Each mode includes static checks. Subprocesses use argument lists, never
a shell. Failures print identifiers and exception types, never scanned content.
The post mode reads GitHub settings and the operator's database through
``doctor``; it never changes either, and never runs ``status`` or ``replay``
against the operator's stored locations. Build output, live and corpus tests,
the operations proof, and the replay budget use temporary directories.
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
PHASE_2_TAG = "v2.0.0-phase-2"
CI_WORKFLOW = ".github/workflows/ci.yml"
PHASE_WORKFLOW = ".github/workflows/phase-verify.yml"
CORPUS_WORKFLOW = ".github/workflows/replay-corpus.yml"
MODELS = "src/weatherbot/models"
ENGINE = "src/weatherbot/engine"
SERVICES = "src/weatherbot/services"
VERSIONS = f"{SERVICES}/persistence/migrations/versions"
CORPUS = "tests/fixtures/replay"
CORPUS_MANIFEST = f"{CORPUS}/corpus-manifest.json"
GOLDENS = "tests/golden/replay"
LANDMARKS = "scripts/public_landmarks.toml"
MODES = ("fast", "py", "live", "security", "all", "post")
JSON_SCHEMA_2020_12 = "https://json-schema.org/draft/2020-12/schema"
MAX_SUBSET_BYTES = 10 * 1024 * 1024
REPLAY_BUDGET_S = 10.0
STORM_SURGE_ISSUE = 33
STORMS = ("AL052019", "AL092022", "AL112017", "AL142024")
# The landmark keys of scripts/public_landmarks.toml, and the names V6.5 stores them by.
LANDMARK_NAMES = {"miami-dade": "Miami-Dade County Hall", "nassau": "Parliament Square"}
WSP_THRESHOLDS = (34, 50, 64)
THRESHOLDS = (
    "coastal_reach_km",
    "segment_end_tolerance_km",
    "cone_horizon_h",
    "hurricane_wind_floor_pct",
    "tropical_storm_wind_floor_pct",
    "development_chance_floor_pct",
)
# The ladder's eleven rules in the documented order (docs/ALERT-LADDER.md).
RULE_ORDER = (
    "HURRICANE_WARNING",
    "TROPICAL_STORM_WARNING",
    "HURRICANE_WATCH",
    "EVACUATION_ORDER",
    "TROPICAL_STORM_WATCH",
    "HURRICANE_CONE",
    "HURRICANE_WIND_PROBABILITY",
    "STORM_CONE",
    "DEVELOPMENT_REGION",
    "TROPICAL_STORM_WIND_PROBABILITY",
    "ALL_CLEAR",
)
LADDER_EVENTS = frozenset(
    {"Hurricane Warning", "Tropical Storm Warning", "Hurricane Watch", "Tropical Storm Watch"}
)
CHANGE_KINDS = (
    "level_changed",
    "advisory_issued",
    "official_added",
    "official_changed",
    "official_removed",
    "cone_entered",
    "cone_left",
)
COORDINATE_NAMES = frozenset(
    {"latitude", "longitude", "lat", "lon", "point", "position", "coordinates"}
)
ASSESSMENT_TABLES = frozenset({"assessments", "assessment_evidence", "assessment_changes"})
SCHEMAS = ("locations", "fetch", "storms", "alerts", "doctor", "status", "replay")
GENERATED_BLOCKS = ("levels", "rules", "thresholds")
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


def requirement_names(value: object) -> set[str]:
    """Name each requirement by its distribution, never by a prefix (``typer-slim``)."""
    names: set[str] = set()
    for item in array_of(value):
        match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", str(item))
        if match is None:
            raise ValueError
        names.add(match[0].lower())
    return names


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


def call_strings(node: ast.expr) -> set[str]:
    """The string literals in the first argument of a call such as ``frozenset({...})``."""
    if not isinstance(node, ast.Call) or not node.args:
        raise TypeError
    return set(cast("set[str]", ast.literal_eval(node.args[0])))


def class_node(directory: str, name: str) -> ast.ClassDef:
    """The one class with this name in the tracked modules under ``directory``."""
    classes = [
        node
        for relative in sorted(tracked(directory))
        if relative.endswith(".py")
        for node in ast.walk(syntax(relative))
        if isinstance(node, ast.ClassDef) and node.name == name
    ]
    if len(classes) != 1:
        raise LookupError
    return classes[0]


def class_annotations(directory: str, name: str) -> dict[str, str]:
    """The annotated fields one class declares in its own body, with their annotations."""
    return {
        node.target.id: ast.unparse(node.annotation)
        for node in class_node(directory, name).body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }


def class_fields(directory: str, name: str) -> set[str]:
    """The annotated fields one class declares in its own body, found under ``directory``."""
    return set(class_annotations(directory, name))


def method(directory: str, cls: str, name: str) -> ast.FunctionDef:
    """One method of one class."""
    found = [
        node
        for node in class_node(directory, cls).body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    if len(found) != 1:
        raise LookupError
    return found[0]


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


def attributes_read(relative: str) -> set[str]:
    """Every attribute name one module reads (``alert.found_by`` gives ``found_by``)."""
    return {node.attr for node in ast.walk(syntax(relative)) if isinstance(node, ast.Attribute)}


def names_used(relative: str) -> set[str]:
    """Every name and attribute one module refers to, imported names included."""
    used: set[str] = set()
    for node in ast.walk(syntax(relative)):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            used |= {alias.name for alias in node.names}
    return used


def engine_modules() -> list[str]:
    """Every tracked Python module of the engine."""
    return sorted(name for name in tracked(ENGINE) if name.endswith(".py"))


def models_exports() -> set[str]:
    """The names ``weatherbot.models.__all__`` lists."""
    names = ast.literal_eval(assigned(syntax(f"{MODELS}/__init__.py"), "__all__"))
    return set(cast("list[str]", names))


def marked_corpus(relative: str) -> bool:
    """Whether a tracked test module carries the ``corpus`` marker."""
    return files_exist(relative) and any(
        isinstance(node, ast.Attribute)
        and node.attr == "corpus"
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "mark"
        for node in ast.walk(syntax(relative))
    )


def dependencies() -> bool:
    """Check 1: pyproj at run time; hypothesis and pytest-cov in the dev group."""
    return "pyproj" in requirement_names(config("project", "dependencies")) and {
        "hypothesis",
        "pytest-cov",
    } <= requirement_names(config("dependency-groups", "dev"))


def pyproj_geod_only() -> bool:
    """Check 3: no engine module imports from pyproj anything but ``Geod``."""
    importers = 0
    for relative in engine_modules():
        for node in ast.walk(syntax(relative)):
            if isinstance(node, ast.Import) and any(
                alias.name.split(".")[0] == "pyproj" for alias in node.names
            ):
                return False
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "pyproj":
                if node.module != "pyproj" or [(a.name, a.asname) for a in node.names] != [
                    ("Geod", None)
                ]:
                    return False
                importers += 1
    return importers >= 1


def determinism_scan() -> bool:
    """Check 4: the architecture test bans the clock, random, files, environment, logging."""
    relative = "tests/test_architecture.py"
    tree = syntax(relative)
    imports = call_strings(assigned(tree, "DETERMINISM_BANNED_IMPORTS"))
    calls = call_strings(assigned(tree, "DETERMINISM_BANNED_CALLS"))
    return (
        defines(relative, "PYPROJ_ALLOWED", "nondeterminism")
        and {"time", "random", "os", "pathlib", "logging"} <= imports
        and {"now", "today", "open"} <= calls
    )


def coverage_floor() -> bool:
    """Check 5: the ``test`` job's engine branch-coverage floor, with its data file in temp."""
    text = job(CI_WORKFLOW, "test")
    return all(
        token in text
        for token in (
            "COVERAGE_FILE: ${{ runner.temp }}/.coverage",
            "--cov=weatherbot.engine",
            "--cov-branch",
            "--cov-fail-under=90",
        )
    )


def phase_two_check_31() -> bool:
    """Check 6: Phase 2's check 31 reads its tag and compares blob ids."""
    relative = "scripts/verify_phase02.py"
    tree = syntax(relative)
    checks = assigned(tree, "STATIC_CHECKS")
    if not isinstance(checks, ast.Tuple):
        return False
    entry = checks.elts[30]
    if not isinstance(entry, ast.Tuple) or len(entry.elts) != 2:  # noqa: PLR2004 - (label, check)
        return False
    label, check = entry.elts
    names_tag = isinstance(label, ast.JoinedStr) and any(
        isinstance(part, ast.FormattedValue)
        and isinstance(part.value, ast.Name)
        and part.value.id == "PHASE_2_TAG"
        for part in label.values
    )
    return (
        string_constants(tree).get("PHASE_2_TAG") == PHASE_2_TAG
        and names_tag
        and isinstance(check, ast.Name)
        and check.id == "no_later_tables"
        and contains(relative, '"hash-object"')
    )


def throwaway_repository_tests() -> bool:
    """Check 7: Phase 2's verifier tests build throwaway repositories for check 31."""
    relative = "tests/test_phase02_verification.py"
    tree = syntax(relative)
    tests = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_check_31_")
    ]
    return files_exist(relative) and defines(relative, "Repository") and len(tests) >= 5  # noqa: PLR2004


def engine_tests_and_profile() -> bool:
    """Check 8: the engine tests are tracked under unique basenames; one derandomized profile."""
    engine_tests = (
        "test_geodesy.py",
        "test_engine_geometry.py",
        "test_tracks.py",
        "test_engine_properties.py",
        "engine_support.py",
    )
    basenames = [
        Path(name).name
        for name in tracked("tests")
        if Path(name).name.startswith("test_") and name.endswith(".py")
    ]
    tree = syntax("tests/conftest.py")
    registered = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "register_profile"
    ]
    keywords = (
        {k.arg: ast.literal_eval(k.value) for k in registered[0].keywords}
        if len(registered) == 1
        else {}
    )
    return (
        files_exist(*(f"tests/engine/{name}" for name in engine_tests))
        and len(basenames) == len(set(basenames))
        and string_constants(tree).get("HYPOTHESIS_PROFILE") == "weatherbot"
        and keywords == {"derandomize": True, "database": None, "deadline": None}
        and contains("tests/conftest.py", "settings.load_profile(HYPOTHESIS_PROFILE)")
    )


def replay_models() -> bool:
    """Check 9: the snapshot's origin, the storm's summary and archive record, exported."""
    return (
        "origin" in class_fields(MODELS, "Snapshot")
        and {"summary", "archived"} <= class_fields(MODELS, "StormProducts")
        and "ArchiveStorm" in models_exports()
    )


def sha256_before_parsing() -> bool:
    """Check 12: the reader and its error; ``_read`` checks SHA-256 and refuses a mismatch."""
    relative = f"{SERVICES}/replay.py"
    body = method(SERVICES, "ReplayCorpus", "_read")
    hashes = any(
        isinstance(node, ast.Attribute)
        and node.attr == "sha256"
        and isinstance(node.value, ast.Name)
        and node.value.id == "hashlib"
        for node in ast.walk(body)
    )
    refuses = any(
        isinstance(node, ast.Raise)
        and isinstance(node.exc, ast.Call)
        and isinstance(node.exc.func, ast.Name)
        and node.exc.func.id == "ReplayError"
        for node in ast.walk(body)
    )
    return defines(relative, "ReplayCorpus", "ReplayError") and hashes and refuses


def subset_windows() -> bool:
    """Check 13: windowed 34-, 50-, and 64-kt products at every synoptic time; recorded_on."""
    manifest = json_file(CORPUS_MANIFEST)
    subset = {
        (str(object_of(e)["file"]), str(object_of(e)["product"]))
        for e in array_of(manifest["subset"])
    }
    storms = object_of(manifest["storms"])
    expected = {
        (f"{storm}/wsp/{synoptic}/wsp-{kt}kt.geojson.gz", f"wsp-{kt}kt")
        for storm in STORMS
        for synoptic in array_of(object_of(storms[storm])["synoptic_times"])
        for kt in WSP_THRESHOLDS
    }
    recorded_on = str(manifest["recorded_on"])
    return (
        bool(expected)
        and expected <= subset
        and date.fromisoformat(recorded_on).isoformat() == recorded_on
    )


def subset_budget() -> bool:
    """Check 14: the committed subset stays under 10 MiB; NOTICE documents the windows."""
    entries = [object_of(e) for e in array_of(json_file(CORPUS_MANIFEST)["subset"])]
    size = sum((REPO_ROOT / CORPUS / str(e["file"])).stat().st_size for e in entries)
    return 0 < size < MAX_SUBSET_BYTES and bool(
        re.search(r"^## Wind-speed-probability windows$", read(f"{CORPUS}/NOTICE.md"), re.MULTILINE)
    )


def corpus_workflow_paths() -> bool:
    """Check 16: both path filters name the replay inputs; the cache keys on the manifest."""
    text = read(CORPUS_WORKFLOW)
    blocks = re.findall(r"^    paths:\n((?:      - .*\n)+)", text, re.MULTILINE)
    required = {
        "src/weatherbot/models/**",
        "src/weatherbot/sources/nhc_gis_archive.py",
        "src/weatherbot/services/replay.py",
        "src/weatherbot/engine/**",
    }
    filters = [{line.strip()[2:] for line in block.splitlines()} for block in blocks]
    return (
        len(filters) == 2  # noqa: PLR2004 - push and pull_request
        and all(required <= paths for paths in filters)
        and f"key: replay-corpus-${{{{ hashFiles('{CORPUS_MANIFEST}') }}}}" in text
    )


def replay_never_stored() -> bool:
    """Check 17: ``SnapshotRepository.save`` refuses a snapshot whose origin is not live."""
    relative = f"{SERVICES}/persistence/repositories.py"
    segment = ast.get_source_segment(
        read(relative), method(f"{SERVICES}/persistence", "SnapshotRepository", "save")
    )
    return segment is not None and 'snapshot.origin != "live"' in segment and "raise" in segment


def ladder_models() -> bool:
    """Check 18: the ladder and assessment models, and the six thresholds."""
    return (
        defines(f"{MODELS}/ladder.py", "AlertLevel", "RuleId", "Thresholds")
        and defines(
            f"{MODELS}/assessment.py",
            "Assessment",
            "Evidence",
            "OfficialProduct",
            "LocationWindProbability",
            "UnavailableInput",
            "BreakpointSpan",
        )
        and set(THRESHOLDS) <= class_fields(MODELS, "Thresholds")
    )


def rule_order() -> bool:
    """Check 19: ``RuleId`` and ``RULES`` list the eleven rules in the documented order."""
    members = [
        cast("ast.Name", node.targets[0]).id
        for node in class_node(MODELS, "RuleId").body
        if isinstance(node, ast.Assign)
    ]
    rules = assigned(syntax(f"{ENGINE}/rules.py"), "RULES")
    if not isinstance(rules, ast.Tuple):
        return False
    listed = [
        node.args[0].attr
        for node in rules.elts
        if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Attribute)
    ]
    return members == list(RULE_ORDER) and listed == list(RULE_ORDER)


def issue_10_inputs() -> bool:
    """Check 21: the four ladder events, and issue #10's inputs read."""
    relative = f"{ENGINE}/official.py"
    events = assigned(syntax(relative), "LADDER_EVENTS")
    keys = {
        cast("str", key.value)
        for node in ast.walk(events)
        if isinstance(node, ast.Dict)
        for key in node.keys
        if isinstance(key, ast.Constant)
    }
    return keys == set(LADDER_EVENTS) and {"found_by", "affected_zone_ids", "geocode_ugc"} <= (
        attributes_read(relative)
    )


def engine_table() -> bool:
    """Check 24: ``[engine]`` holds the six thresholds, each with its environment override."""
    relative = f"{SERVICES}/config.py"
    overrides = assigned(syntax(relative), "ENVIRONMENT_OVERRIDES")
    pairs = {
        cast("tuple[str, str]", ast.literal_eval(key)): ast.literal_eval(value)
        for node in ast.walk(overrides)
        if isinstance(node, ast.Dict)
        for key, value in zip(node.keys, node.values, strict=True)
        if key is not None
    }
    return (
        "engine" in class_fields(SERVICES, "Settings")
        and set(THRESHOLDS) <= class_fields(SERVICES, "EngineSettings")
        and all(
            pairs.get(("engine", name)) == f"WEATHERBOT_ENGINE_{name.upper()}"
            for name in THRESHOLDS
        )
    )


def no_coordinate_fields() -> bool:
    """Check 25: no evidence, assessment, or citation field is a coordinate."""
    return all(
        (fields := class_fields(MODELS, name)) and not fields & COORDINATE_NAMES
        for name in ("Evidence", "Assessment", "Citation")
    )


def issue_10_scenarios() -> bool:
    """Check 26: the shared scenarios register issue #10's two recorded cases."""
    relative = "tests/engine/scenarios.py"
    scenarios = assigned(syntax(relative), "SCENARIOS")
    names = {
        cast("str", node.args[0].value)
        for node in ast.walk(scenarios)
        if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant)
    }
    issue_10 = {name for name in names if name.startswith("issue-10-")}
    return (
        files_exist(relative)
        and any("rip-current" in name for name in issue_10)
        and any("county-statement" in name for name in issue_10)
    )


def threat_functions() -> bool:
    """Check 28: the threat, arrival, and change functions, and the engine's public API."""
    exported = ast.literal_eval(assigned(syntax(f"{ENGINE}/__init__.py"), "__all__"))
    return (
        defines(f"{ENGINE}/threats.py", "threats_for")
        and defines(f"{ENGINE}/arrivals.py", "read_arrival")
        and defines(f"{ENGINE}/changes.py", "diff")
        and {"assess", "RULES", "diff"} <= set(cast("list[str]", exported))
    )


def no_label_parsing() -> bool:
    """Check 30: no engine module refers to a label or local-time parser (issue #11)."""
    banned = {"resolve_arrival_label", "parse_nhc_local_time"}
    modules = engine_modules()
    return bool(modules) and not any(names_used(relative) & banned for relative in modules)


def change_kinds() -> bool:
    """Check 32: ``CHANGE_KINDS`` is exactly the seven documented kinds, in order."""
    kinds = ast.literal_eval(assigned(syntax(f"{MODELS}/assessment.py"), "CHANGE_KINDS"))
    return tuple(cast("tuple[str, ...]", kinds)) == CHANGE_KINDS


def golden_files() -> list[str]:
    """The eight golden file names, storm by landmark."""
    return [f"{GOLDENS}/{storm}-{landmark}.json" for storm in STORMS for landmark in LANDMARK_NAMES]


def eight_goldens() -> bool:
    """Check 33: exactly the eight goldens, each approved with its ruleset and timeline."""
    names = golden_files()
    if tracked(GOLDENS) != set(names) or not files_exist(*names):
        return False
    for relative in names:
        golden = json_file(relative)
        approval = object_of(golden["approval"])
        if not (
            re.fullmatch(r"[0-9a-f]{64}", str(golden["ruleset"]))
            and array_of(golden["timeline"])
            and re.fullmatch(r"[0-9a-f]{64}", str(approval["timeline_sha256"]))
            and date.fromisoformat(str(approval["date"]))
        ):
            return False
    return True


def ladder_document() -> bool:
    """Check 36: the three generated blocks, in order and closed, and the disclaimer link."""
    text = read("docs/ALERT-LADDER.md")
    blocks = [
        re.search(
            rf"^<!-- ladder:{name} -->\n.*?^<!-- /ladder:{name} -->$",
            text,
            re.MULTILINE | re.DOTALL,
        )
        for name in GENERATED_BLOCKS
    ]
    starts = [block.start() for block in blocks if block is not None]
    return (
        len(starts) == len(GENERATED_BLOCKS)
        and starts == sorted(starts)
        and ("](../DISCLAIMER.md)" in text)
    )


def calibrated_thresholds() -> bool:
    """Check 38: every threshold records both interval ends and evidence; none provisional."""
    tree = syntax(f"{MODELS}/ladder.py")
    comprehension = cast("ast.Call", assigned(tree, "CALIBRATION")).args[0]
    if not isinstance(comprehension, ast.DictComp):
        return False
    source = cast("ast.Attribute", cast("ast.Call", comprehension.generators[0].iter).func).value
    rows = cast("dict[str, dict[str, object]]", ast.literal_eval(source))
    evidence = cast(
        "dict[str, str]",
        ast.literal_eval(cast("ast.Call", assigned(tree, "CALIBRATION_EVIDENCE")).args[0]),
    )
    fields = class_fields(MODELS, "Thresholds")

    def bounded(row: Mapping[str, object], end: str) -> bool:
        return row[end] is not None or bool(row[f"{end}_open_reason"])

    return (
        set(rows) == set(evidence) == fields == set(THRESHOLDS)
        and all(bounded(row, "lower") and bounded(row, "upper") for row in rows.values())
        and all(text.strip() for text in evidence.values())
        and not any("provisional" in text.lower() for text in evidence.values())
    )


def keys_of(value: object) -> Iterator[str]:
    """Every object key in a JSON document."""
    if isinstance(value, dict):
        for key, item in cast("dict[str, object]", value).items():
            yield key
            yield from keys_of(item)
    elif isinstance(value, list):
        for item in cast("list[object]", value):
            yield from keys_of(item)


def goldens_without_coordinates() -> bool:
    """Check 39: no golden holds a coordinate key."""
    names = golden_files()
    return bool(names) and not any(
        key.lower() in COORDINATE_NAMES
        for relative in names
        for key in keys_of(json_file(relative))
    )


def revision_0003() -> bool:
    """Check 41: revision 0003 follows 0002 and creates the three assessment tables."""
    tree = syntax(f"{VERSIONS}/0003_assessments.py")
    tables = {
        str(cast("ast.Constant", node.args[0]).value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_table"
    }
    return (
        ast.literal_eval(assigned(tree, "revision")) == "0003"
        and ast.literal_eval(assigned(tree, "down_revision")) == "0002"
        and tables == set(ASSESSMENT_TABLES)
    )


def commands_registered() -> bool:
    """Check 43: the root app registers ``status`` and ``replay``; ``locations evacuation``."""
    root = read("src/weatherbot/cli/__init__.py")
    group = read("src/weatherbot/cli/locations.py")
    return (
        all(f'app.command("{name}")' in root for name in ("status", "replay"))
        and '@app.command("evacuation")' in group
    )


def schemas_committed() -> bool:
    """Check 44: the status and replay schemas beside the five Phase 2 schemas."""
    return all(
        files_exist(f"docs/schema/{name}.schema.json")
        and json_file(f"docs/schema/{name}.schema.json").get("$schema") == JSON_SCHEMA_2020_12
        for name in SCHEMAS
    )


def live_status_test() -> bool:
    """Check 46: the live command test runs ``status`` under the live marker."""
    relative = "tests/live/test_cli_live.py"
    return files_exist(relative) and contains(relative, "pytest.mark.live", 'run(["status"')


def readme_commands() -> bool:
    """Check 47: README's Commands section names the three Phase 3 commands."""
    match = re.search(r"^## Commands$(.*?)(?=^## |\Z)", read("README.md"), re.MULTILINE | re.DOTALL)
    return match is not None and all(
        f"weatherbot {command}" in match[1]
        for command in ("status", "replay", "locations evacuation")
    )


def gate_wired() -> bool:
    """Check 52: the four gate hooks, and ``--security`` in every phase entry."""
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


def matrix_includes_03() -> bool:
    """Check 51: matrix entry 03 beside 01 and 02."""
    return {"01", "02", "03"} <= phase_matrix()


STATIC_CHECKS: tuple[Check, ...] = (
    # Step 1 — geodesy and geometry
    ("pyproj at run time; hypothesis and pytest-cov in dev", dependencies),
    (
        "geodesy and geometry functions defined",
        lambda: (
            defines(f"{ENGINE}/geodesy.py", "figure_of", "distance_km", "initial_bearing_deg")
            and defines(
                f"{ENGINE}/geometry.py",
                "place",
                "covers",
                "intersects",
                "repair",
                "nearest_on_line",
                "closest_approach",
            )
        ),
    ),
    ("engine imports only Geod from pyproj", pyproj_geod_only),
    ("architecture test scans the engine for nondeterminism", determinism_scan),
    ("engine branch coverage floor in the CI test job", coverage_floor),
    (f"Phase 2 check 31 reads {PHASE_2_TAG}", phase_two_check_31),
    ("check 31 throwaway-repository tests", throwaway_repository_tests),
    ("engine tests tracked, unique basenames, derandomized profile", engine_tests_and_profile),
    # Step 2 — replay snapshots
    ("replay origin, storm summary and archive record", replay_models),
    (
        "wind-probability products carry their coverage",
        lambda: "coverage" in class_fields(MODELS, "WindProbabilityProduct"),
    ),
    (
        "archive parser FIELDS_READ and field contract",
        lambda: (
            defines("src/weatherbot/sources/nhc_gis_archive.py", "FIELDS_READ")
            and files_exist("tests/contract/test_archive_field_coverage.py")
        ),
    ),
    ("replay reader checks SHA-256 before parsing", sha256_before_parsing),
    ("windowed wind probabilities at every synoptic time", subset_windows),
    ("subset under 10 MiB; NOTICE documents the windows", subset_budget),
    (
        "corpus script keeps its choices and offers --full",
        lambda: contains(
            "scripts/fetch_replay_corpus.py",
            'choices=("fetch", "verify", "convert", "manifest")',
            '"--full"',
        ),
    ),
    ("replay-corpus paths and manifest-keyed cache", corpus_workflow_paths),
    ("snapshot repository refuses a replay", replay_never_stored),
    # Step 3 — ladder rules and evidence
    ("ladder and assessment models, six thresholds", ladder_models),
    ("eleven rules in the documented order", rule_order),
    (
        "breakpoint span typed BreakpointSpan | None",
        lambda: (
            class_annotations(MODELS, "Location").get("breakpoint_span") == "BreakpointSpan | None"
        ),
    ),
    ("ladder events and issue #10's inputs read", issue_10_inputs),
    (
        "segment reach, end tolerance, and at_end read",
        lambda: (
            {"coastal_reach_km", "segment_end_tolerance_km", "at_end"}
            <= attributes_read(f"{ENGINE}/official.py")
        ),
    ),
    (
        "probabilities read the snapshot's products and coverage",
        lambda: {"wind_probabilities", "coverage"} <= attributes_read(f"{ENGINE}/probabilities.py"),
    ),
    ("[engine] table with six overrides", engine_table),
    ("no coordinate field on evidence, assessment, citation", no_coordinate_fields),
    ("issue #10's recorded cases in the shared scenarios", issue_10_scenarios),
    # Step 4 — threats and change events
    (
        "threat, arrival, and change models; assessment threats",
        lambda: (
            defines(f"{MODELS}/assessment.py", "StormThreat", "ArrivalReading", "ChangeEvent")
            and "threats" in class_fields(MODELS, "Assessment")
        ),
    ),
    ("threat, arrival, and change functions exported", threat_functions),
    (
        "storm threats carry no wind probability (issue #12)",
        lambda: (
            not any(
                "probab" in name or name.startswith("wsp")
                for name in class_fields(MODELS, "StormThreat")
            )
        ),
    ),
    ("no label or local-time parsing in the engine (issue #11)", no_label_parsing),
    (
        "cached arrival test under the corpus marker",
        lambda: marked_corpus("tests/engine/test_cached_arrivals.py"),
    ),
    ("exactly the seven change kinds", change_kinds),
    # Step 5 — calibration, goldens, and the written ladder
    ("eight approved goldens", eight_goldens),
    (
        "calibration and golden scripts offer --check",
        lambda: (
            files_exist("scripts/calibrate_ladder.py", "scripts/build_goldens.py")
            and contains("scripts/calibrate_ladder.py", '"--check"')
            and contains("scripts/build_goldens.py", '"--check"')
        ),
    ),
    (
        "golden replay and mutation tests tracked",
        lambda: files_exist(
            "tests/engine/test_golden_replays.py", "tests/engine/test_golden_mutations.py"
        ),
    ),
    ("ladder document blocks and disclaimer link", ladder_document),
    (
        "ladder renderer --check and document test",
        lambda: (
            files_exist("scripts/export_ladder.py", "tests/engine/test_ladder_document.py")
            and contains("scripts/export_ladder.py", '"--check"')
        ),
    ),
    ("every threshold calibrated with evidence", calibrated_thresholds),
    ("no coordinate key in a golden", goldens_without_coordinates),
    (
        "full-products cross-check under the corpus marker",
        lambda: marked_corpus("tests/engine/test_golden_full_products.py"),
    ),
    # Step 6 — stored assessments and the commands
    ("revision 0003 creates the assessment tables", revision_0003),
    (
        "assessment repository and service",
        lambda: (
            defines(f"{SERVICES}/persistence/repositories.py", "AssessmentRepository")
            and defines(f"{SERVICES}/assessments.py", "AssessmentService")
        ),
    ),
    ("status, replay, and locations evacuation registered", commands_registered),
    ("status and replay schemas beside Phase 2's", schemas_committed),
    (
        "Phase 2's alerts note gone",
        lambda: "PHASE_3_NOTE" not in read("src/weatherbot/cli/snapshots.py"),
    ),
    ("live command test runs status", live_status_test),
    ("README Commands names the Phase 3 commands", readme_commands),
    # Step 7 — self-checks
    (
        "tracked verifier declares all six modes",
        lambda: (
            files_exist("scripts/verify_phase03.py")
            and all(f'"{mode}"' in read("scripts/verify_phase03.py") for mode in MODES)
        ),
    ),
    ("QA findings document exists", (REPO_ROOT / "docs/phase03-qa-findings.md").is_file),
    ("phase roadmap exists", (REPO_ROOT / "docs/roadmap/phase03-roadmap.md").is_file),
    ("phase verification matrix includes 01, 02, and 03", matrix_includes_03),
    ("security gate still wired", gate_wired),
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
    """Run pytest once with a JUnit report, so V rows can select their evidence.

    The coverage data file, when coverage runs, goes to the same temporary directory and
    never to the checkout.
    """
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
                "COVERAGE_FILE": str(Path(directory) / ".coverage"),
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


# Run by the installed wheel's Python, outside the checkout: a new database at the head,
# and the engine importable from the wheel.
WHEEL_SMOKE = """\
import sys
from pathlib import Path

import weatherbot
from weatherbot.engine import RULES, assess, diff
from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import current_revision, head_revision, open_database

assert Path(weatherbot.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
assert len(RULES) == 11 and callable(assess) and callable(diff)
paths = AppPaths.resolve()
assert not paths.database_path.exists()
with open_database(paths) as database:
    assert current_revision(database.engine) == head_revision() == database.revision
    assert database.backup_path is None
"""


def package_smoke() -> Outcome:
    """Build and install the wheel; check its version, its engine, and a new database."""
    with tempfile.TemporaryDirectory(prefix="weatherbot-package-") as directory:
        root = Path(directory)
        results: list[Outcome] = []
        python = install_wheel(root, results)
        if python is None:
            return report(aggregate("py.package", "installed wheel, engine, migrations", results))
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
                [str(python), "-c", WHEEL_SMOKE],
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
        results.append(
            Outcome(
                "pkg.smoke", "engine imports; new database at head", "PASS" if passed else "FAIL"
            )
        )
        return report(aggregate("py.package", "installed wheel, engine, migrations", results))


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
    """Run the same Python suites as CI, the engine coverage floor, and the wheel smoke."""
    heading("Python suites (--py)")
    commands = (
        ("lint", ["ruff", "check"]),
        ("format", ["ruff", "format", "--check"]),
        ("types", ["pyright"]),
        ("imports", ["lint-imports"]),
    )
    tools = [run_command(f"py.{name}", name, ["uv", "run", *args]) for name, args in commands]
    tests = pytest_run(
        "py.tests",
        "offline tests with the engine branch-coverage floor",
        "--cov=weatherbot.engine",
        "--cov-branch",
        "--cov-report=term-missing:skip-covered",
        "--cov-fail-under=90",
    )
    return PySuites(tools, tests, package_smoke())


def live_suite() -> PytestRun:
    """Run every live test against the real services, landmarks only."""
    heading("Live services (--live)")
    return pytest_run("live.tests", "live clients and commands, landmarks only", "-m", "live")


@dataclass(frozen=True)
class CorpusSuite:
    """The pinned cache's fetch and verification, and the one corpus test run."""

    preparation: list[Outcome]
    tests: PytestRun

    def outcomes(self) -> list[Outcome]:
        """Every suite outcome, in run order."""
        return [*self.preparation, self.tests.outcome]


def corpus_suite() -> CorpusSuite:
    """Fetch missing pinned files, verify everything, then run the corpus tests once."""
    heading("Cached replay corpus (--all)")
    cache = Path(os.environ.get("WEATHERBOT_CORPUS_CACHE", str(REPO_ROOT / ".cache/replay-corpus")))
    manifest = json_file(CORPUS_MANIFEST)
    missing = any(
        not (cache / str(object_of(entry)["file"])).is_file()
        for entry in array_of(manifest["files"])
    )
    preparation: list[Outcome] = []
    if missing:
        preparation.append(
            run_command(
                "corpus.fetch",
                "fetch cache misses",
                ["uv", "run", "python", "scripts/fetch_replay_corpus.py", "fetch"],
            )
        )
    preparation.append(
        run_command(
            "corpus.verify",
            "verify pinned archives",
            ["uv", "run", "python", "scripts/fetch_replay_corpus.py", "verify"],
        )
    )
    tests = pytest_run("corpus.tests", "cached corpus: arrivals, full products", "-m", "corpus")
    return CorpusSuite(preparation, tests)


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


def issues_decided() -> bool:
    """Issue #10 is closed with its decision comment; the storm-surge issue is tracked.

    The storm-surge issue is the operator's open question when Phase 3 closes. A later
    phase that decides it closes it with its decision comment, which this check accepts,
    so deciding the question never turns Phase 3's sweep red.
    """
    county = object_of(github_api("issues/10"))
    surge = object_of(github_api(f"issues/{STORM_SURGE_ISSUE}"))
    print(f"  issue #10 {county['state']}; issue #{STORM_SURGE_ISSUE} {surge['state']}")
    decided = cast("int", county["comments"]) >= 1
    surge_tracked = surge["state"] == "open" or cast("int", surge["comments"]) >= 1
    return county["state"] == "closed" and decided and surge_tracked


def phase_two_post() -> bool:
    """Phase 2's own ``--post`` exits 0 with all 73 checks passing; only its totals print."""
    result = capture(["uv", "run", "python", "scripts/verify_phase02.py", "--post"], timeout=5400)
    totals = dict(
        re.findall(r"^  (passed|failed|skipped|total)\s+(\d+)$", result.stdout, re.MULTILINE)
    )
    print(f"  verify_phase02.py --post: {totals or 'no summary'}; exit {result.returncode}")
    return result.returncode == 0 and totals == {
        "passed": "73",
        "failed": "0",
        "skipped": "0",
        "total": "73",
    }


def weatherbot(
    arguments: Sequence[str], *, cwd: Path, env: Mapping[str, str] | None = None, timeout: int = 600
) -> subprocess.CompletedProcess[str]:
    """Run this checkout's command line, capturing its output for the caller to judge."""
    return capture(
        [sys.executable, "-m", "weatherbot", *arguments], cwd=cwd, timeout=timeout, env=env
    )


def doctor(
    arguments: Sequence[str], *, cwd: Path, env: Mapping[str, str] | None = None
) -> tuple[int, dict[str, object]]:
    """Run this checkout's ``doctor --json``; return its exit status and the document's data."""
    result = weatherbot(["doctor", "--json", *arguments], cwd=cwd, env=env)
    return result.returncode, object_of(json.loads(result.stdout)["data"])


def descends_from(head: str, ancestor: str) -> bool:
    """Whether the working tree's revision chain leads from ``head`` back to ``ancestor``."""
    parents: dict[str, str | None] = {}
    for relative in sorted(tracked(VERSIONS)):
        if relative.endswith(".py") and not relative.endswith("__init__.py"):
            tree = syntax(relative)
            parents[ast.literal_eval(assigned(tree, "revision"))] = ast.literal_eval(
                assigned(tree, "down_revision")
            )
    revision: str | None = head
    while revision is not None:
        if revision == ancestor:
            return True
        revision = parents.get(revision)
    return False


def operator_database_at_head() -> bool:
    """``doctor`` reports the operator's database at a head that holds revision 0003.

    Only the revision and the head print. A later phase's revision grows the head, so the
    check asks for the head to descend from 0003, never to equal it.
    """
    with tempfile.TemporaryDirectory(prefix="weatherbot-doctor-") as directory:
        _, data = doctor([], cwd=Path(directory))
    database = object_of(data["database"])
    checks = {object_of(c)["name"]: object_of(c)["status"] for c in array_of(data["checks"])}
    print(f"  operator database: revision {database['revision']}, head {database['head']}")
    return (
        database["at_head"] is True
        and checks.get("migrations") == "pass"
        and descends_from(str(database["head"]), "0003")
    )


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


def replay_budget() -> bool:
    """Time each storm-landmark replay over the committed corpus in a temporary data directory.

    The two public landmarks are stored with ``locations add`` (one NWS and one Nominatim
    request each); the operator's database and locations are never opened. Only the storm,
    the landmark key, the exit status, and the time print.
    """
    landmarks = object_of(tomllib.loads(read(LANDMARKS))["landmarks"])
    corpus = str(REPO_ROOT / CORPUS)
    within = True
    with tempfile.TemporaryDirectory(prefix="weatherbot-replay-") as directory:
        root = Path(directory)
        env = {
            "WEATHERBOT_CONFIG_DIR": str(root / "config"),
            "WEATHERBOT_DATA_DIR": str(root / "data"),
        }
        for key, name in LANDMARK_NAMES.items():
            landmark = object_of(landmarks[key])
            added = weatherbot(
                ["locations", "add", name, f"--lat={landmark['lat']}", f"--lon={landmark['lon']}"],
                cwd=root,
                env=env,
                timeout=120,
            )
            print(f"  locations add {key}: exit {added.returncode}")
            if added.returncode != 0:
                return False
        for storm in STORMS:
            for key, name in LANDMARK_NAMES.items():
                started = time.perf_counter()
                ran = weatherbot(
                    ["replay", storm, "--location", name, "--corpus", corpus, "--json"],
                    cwd=root,
                    env=env,
                    timeout=120,
                )
                elapsed = time.perf_counter() - started
                print(f"  replay {storm} at {key}: exit {ran.returncode}, {elapsed:.1f}s")
                within = within and ran.returncode == 0 and elapsed < REPLAY_BUDGET_S
    return within


def probe(item_id: str, description: str, check: Callable[[], bool]) -> Outcome:
    """Report a bounded independent post-check without leaking exception text."""
    try:
        passed = check()
        reason = "" if passed else "readback did not meet the criterion"
    except Exception as error:  # noqa: BLE001 - report each post-check independently
        passed = False
        reason = type(error).__name__
    return report(Outcome(item_id, description, "PASS" if passed else "FAIL", reason))


def post_matrix(statics: Sequence[Outcome]) -> list[Outcome]:  # noqa: PLR0915 - a statement per row
    """Run shared suites once and report exactly V1.1 through V7.4 (28 rows)."""
    py = py_suites()
    live = live_suite()
    corpus = corpus_suite()
    security = security_suites()
    heading("GitHub, Phase 2, and the operator's machine (--post)")
    phase_02 = probe("post.phase-02", "phase-verify (02) green", lambda: phase_entry_green("02"))
    phase_03 = probe("post.phase-03", "phase-verify (03) green", lambda: phase_entry_green("03"))
    protection = probe(
        "post.protection", "main requires gate and phase-verify", protection_requires_both
    )
    replay_corpus = probe(
        "post.replay-corpus",
        "latest main replay-corpus run green",
        lambda: latest_run("replay-corpus.yml")["conclusion"] == "success",
    )
    issues = probe("post.issues", "issue #10 decided; storm-surge issue tracked", issues_decided)
    phase_two = probe("post.verify-02", "verify_phase02.py --post: 73 PASS", phase_two_post)
    operator = probe("post.doctor", "doctor: operator database at head", operator_database_at_head)
    alarm = probe("post.alarm", "doctor: unknown revision FAILs, exit 1", doctor_alarm)
    budget = probe("post.replay", "eight landmark replays under 10 s each", replay_budget)
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
        "geodesy, geometry, track, property tests; engine coverage floor; tools clean",
        py.tests,
        Select("tests.engine.test_geodesy"),
        Select("tests.engine.test_engine_geometry"),
        Select("tests.engine.test_tracks"),
        Select("tests.engine.test_engine_properties"),
        Select("tests.test_architecture"),
        extra=[*py.tools, py.tests.outcome],
    )
    tests(
        "V1.3",
        f"phase-verify (02) green; check 31 reads {PHASE_2_TAG}",
        py.tests,
        Select("tests.test_phase02_verification"),
        extra=[phase_02],
    )
    row("V1.4", "verify_phase02.py --post reports 73 PASS", [phase_two])
    static_row("V2.1", 9, 17)
    tests(
        "V2.2",
        "archive parser, field contract, and ReplayCorpus tests",
        py.tests,
        Select("tests.models.test_origin"),
        Select("tests.sources.test_nhc_gis_archive"),
        Select("tests.contract.test_archive_field_coverage"),
        Select("tests.services.test_replay"),
    )
    tests(
        "V2.3",
        "subset, window, and budget tests",
        py.tests,
        Select("tests.replay.test_corpus_subset"),
        Select("tests.scripts.test_fetch_replay_corpus"),
    )
    row("V2.4", "latest replay-corpus.yml run on main green", [replay_corpus])
    static_row("V3.1", 18, 26)
    tests(
        "V3.2",
        "rule, official, breakpoint, probability, outlook, assessment tests; scenarios",
        py.tests,
        Select("tests.engine.test_rules"),
        Select("tests.engine.test_official"),
        Select("tests.engine.test_breakpoints"),
        Select("tests.engine.test_probabilities"),
        Select("tests.engine.test_outlook"),
        Select("tests.engine.test_assess"),
        Select("tests.engine.test_assess", "scenario"),
        Select("tests.models.test_assessment"),
    )
    row("V3.3", "issue #10 closed with its decision; storm-surge issue tracked", [issues])
    static_row("V4.1", 27, 32)
    tests(
        "V4.2",
        "threat, arrival, and change tests; Dorian 036 anchors",
        py.tests,
        Select("tests.engine.test_threats"),
        Select("tests.engine.test_arrivals"),
        Select("tests.engine.test_arrivals", "dorian_036"),
        Select("tests.engine.test_changes"),
    )
    tests(
        "V4.3",
        "cached arrival readings at both landmarks (whole corpus run)",
        corpus.tests,
        Select("tests.engine.test_cached_arrivals"),
        extra=corpus.outcomes(),
    )
    static_row("V5.1", 33, 40)
    tests(
        "V5.2",
        "eight golden replays equal the engine, fingerprints and approvals",
        py.tests,
        Select("tests.engine.test_golden_replays"),
    )
    tests("V5.3", "mutation suite", py.tests, Select("tests.engine.test_golden_mutations"))
    tests(
        "V5.4",
        "ladder document equals the code; export, calibrate, goldens --check",
        py.tests,
        Select("tests.engine.test_ladder_document"),
        Select("tests.engine.test_golden_replays", "golden_check"),
    )
    tests(
        "V5.5",
        "goldens hold with the full probability products",
        corpus.tests,
        Select("tests.engine.test_golden_full_products"),
        extra=corpus.outcomes(),
    )
    static_row("V6.1", 41, 47)
    tests(
        "V6.2",
        "assessment service, migration, command, and schema tests",
        py.tests,
        Select("tests.services.test_assessments"),
        Select("tests.services.test_database", "0003"),
        Select("tests.cli.test_status"),
        Select("tests.cli.test_replay_command"),
        Select("tests.cli.test_cli_privacy", "status"),
        Select("tests.cli.test_documents"),
    )
    tests(
        "V6.3",
        "status against the live services for both landmarks (whole live suite)",
        live,
        Select("tests.live.test_cli_live"),
        extra=[live.outcome],
    )
    row("V6.4", "doctor: operator database at head; unknown revision alarms", [operator, alarm])
    row("V6.5", "each storm-landmark replay under 10 s", [budget])
    tests(
        "V7.1",
        "verify_phase03.py --fast exits 0 on Ubuntu CI",
        py.tests,
        Select("tests.test_phase03_verification"),
        extra=[phase_03],
    )
    row(
        "V7.2",
        "matrix includes 01, 02, and 03 under the required aggregate",
        [statics[50], protection],
    )
    static_row("V7.3", 1, 52)
    row("V7.4", "verify_phase03.py --security exits 0", security)
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
    if mode == "all":
        outcomes.extend(corpus_suite().outcomes())
    if mode in ("security", "all"):
        outcomes.extend(security_suites())
    if mode == "post":
        outcomes.extend(post_matrix(statics))
    return summary(mode, outcomes, time.perf_counter() - started)


if __name__ == "__main__":
    raise SystemExit(main())
