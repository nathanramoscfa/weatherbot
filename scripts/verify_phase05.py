# scripts/verify_phase05.py
"""Verify Phase 5 (Web app MVP) against docs/roadmap/phase05-roadmap.md.

Modes (mutually exclusive; no flag runs ``--fast`` and ``--py``):
  --fast      53 static file, AST, OpenAPI, fixture, and workflow checks (< 30 s, no network).
  --py        Ruff, Pyright (host + Linux), import-linter, offline pytest with >=90%
              branch coverage on engine and policy, OpenAPI/fixture checks, and wheel smoke.
  --node      Frontend npm ci, audit signatures, api:check, lint, typecheck, Vitest,
              build, and licenses:check.
  --ui        Playwright Chromium browser smoke (dashboard, map, and screenshots specs).
  --live      Live source, monitor, and web SSE pytest suite (``pytest -m live``).
  --security  Secret, SAST, dependency, personal-data, npm audit, and frontend ESLint scans.
  --all       --py + --node + --ui + --live + --security.
  --post      Full V1-V8 post-implementation matrix (32 rows, 85 checks total).
"""

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess  # nosec B404 - fixed argument lists only, never a shell
import sys
import tempfile
import time
import tomllib
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Final, Literal, cast

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
REPOSITORY: Final = "nathanramoscfa/weatherbot"
PHASE_4_TAG: Final = "v2.0.0-phase-4"
PHASE_5_TAG: Final = "v2.0.0-phase-5"
CI_WORKFLOW: Final = ".github/workflows/ci.yml"
PHASE_WORKFLOW: Final = ".github/workflows/phase-verify.yml"
DEPENDABOT_CONFIG: Final = ".github/dependabot.yml"
PRE_COMMIT_CONFIG: Final = ".pre-commit-config.yaml"
ROADMAP: Final = "docs/roadmap/ROADMAP.md"
PHASE_ROADMAP: Final = "docs/roadmap/phase05-roadmap.md"
QA_FINDINGS: Final = "docs/phase05-qa-findings.md"
DATA_SOURCES: Final = "docs/DATA_SOURCES.md"
OPENAPI_SPEC: Final = "docs/api/openapi.json"
SERVICES: Final = "src/weatherbot/services"
WEB: Final = "src/weatherbot/web"
CLI: Final = "src/weatherbot/cli"
VERSIONS: Final = f"{SERVICES}/persistence/migrations/versions"
FRONTEND: Final = "frontend"
MODES: Final = (
    "--fast",
    "--py",
    "--node",
    "--ui",
    "--live",
    "--security",
    "--all",
    "--post",
)
FAST_BUDGET_SECONDS: Final = 30.0

EVENT_KINDS: Final = (
    "hello",
    "cycle",
    "snapshot",
    "assessment",
    "alert",
    "notification",
    "location",
    "health",
)
QUERY_KEYS: Final = (
    "health",
    "locations",
    "assessments",
    "storms",
    "alerts",
    "timeline",
    "notifications",
    "settings",
    "map",
)
READ_ROUTE_MODULES: Final = (
    "locations",
    "assessments",
    "storms",
    "alerts",
    "timeline",
    "notifications",
    "settings",
    "disclaimer",
    "map",
    "replay",
)
STEP_2_READ_PATHS: Final = (
    "/api/locations",
    "/api/assessments",
    "/api/storms",
    "/api/alerts",
    "/api/timeline",
    "/api/notifications",
    "/api/settings",
    "/api/disclaimer",
    "/api/map",
    "/api/replay",
    "/api/replay/{atcf_id}/{advisory}",
)
FORBIDDEN_EVENT_FIELDS: Final = frozenset(
    {
        "lat",
        "lon",
        "latitude",
        "longitude",
        "coordinates",
        "geometry",
        "distance_km",
        "bearing_deg",
    }
)
ALLOWED_LICENSES: Final = (
    "MIT",
    "ISC",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "Apache-2.0",
    "0BSD",
)
API_FIXTURE_FILES: Final = (
    "alerts.json",
    "assessments.json",
    "disclaimer.json",
    "health.json",
    "locations.json",
    "map.json",
    "notifications.json",
    "replay-advisory.json",
    "replay.json",
    "settings.json",
    "storms.json",
    "timeline.json",
)
PAGE_NAMES: Final = (
    "Dashboard",
    "Storms",
    "Alerts",
    "Timeline",
    "Settings",
)

type Status = Literal["PASS", "FAIL", "SKIP"]
type Check = tuple[str, Callable[[], bool]]
type Evidence = str | Select


@dataclass(frozen=True)
class Outcome:
    """One check or verification-row result."""

    item_id: str
    description: str
    status: Status
    detail: str = ""


@dataclass(frozen=True)
class Select:
    """Selects JUnit test cases whose ``classname.name`` starts with any prefix."""

    prefixes: tuple[str, ...]

    def __init__(self, *prefixes: str) -> None:
        """Store one or more test-case prefixes."""
        object.__setattr__(self, "prefixes", prefixes)


@dataclass(frozen=True)
class VRow:
    """One row of the Phase 5 V1-V8 post-implementation verification matrix."""

    item_id: str
    section: str
    description: str
    evidence: tuple[Evidence, ...]


@dataclass
class Suite:
    """Collected command and test outcomes for evaluating the V1-V8 matrix."""

    commands: dict[str, Status] = field(default_factory=dict[str, Status])
    tests: dict[str, Status] = field(default_factory=dict[str, Status])


def heading(title: str) -> None:
    """Print a section header."""
    print(f"\n=== {title} ===", flush=True)


def report(outcome: Outcome) -> Outcome:
    """Print one outcome line and return the outcome."""
    suffix = f" ({outcome.detail})" if outcome.detail else ""
    print(f"[{outcome.status}] {outcome.item_id}: {outcome.description}{suffix}", flush=True)
    return outcome


def read(relative: str, root: Path = REPO_ROOT) -> str:
    """Read a repository-relative UTF-8 text file."""
    return (root / relative).read_text(encoding="utf-8")


def files_exist(*relatives: str, root: Path = REPO_ROOT) -> bool:
    """Whether every repository-relative path exists as a regular file and is tracked."""
    tracked_set = tracked(root=root)
    return all((root / rel).is_file() and rel in tracked_set for rel in relatives)


def contains(relative: str, *needles: str, root: Path = REPO_ROOT) -> bool:
    """Whether a file contains every needle."""
    text = read(relative, root=root)
    return all(needle in text for needle in needles)


def json_file(relative: str, root: Path = REPO_ROOT) -> dict[str, object]:
    """Load a JSON object from a repository-relative path."""
    loaded: object = json.loads(read(relative, root=root))
    if not isinstance(loaded, dict):
        raise TypeError(relative)
    return cast("dict[str, object]", loaded)


def object_of(value: object) -> dict[str, object]:
    """Narrow a JSON/TOML value to a dict."""
    if not isinstance(value, dict):
        raise TypeError
    return cast("dict[str, object]", value)


def array_of(value: object) -> list[object]:
    """Narrow a JSON/TOML value to a list."""
    if not isinstance(value, list):
        raise TypeError
    return cast("list[object]", value)


def toml_value(text: str, keys: Sequence[str]) -> object:
    """Read a nested key path from TOML text."""
    current: object = tomllib.loads(text)
    for key in keys:
        current = object_of(current)[key]
    return current


def config(*keys: str, root: Path = REPO_ROOT) -> object:
    """Read a nested key path from ``pyproject.toml``."""
    return toml_value(read("pyproject.toml", root=root), keys)


def git(*args: str, root: Path = REPO_ROOT) -> str:
    """Run ``git`` in ``root`` and return stripped stdout."""
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError
    result = subprocess.run(  # noqa: S603 - fixed git argv, no shell  # nosec B603
        [executable, *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=30,
    )
    return result.stdout.strip()


@cache
def tracked(prefix: str = "", *, root: Path = REPO_ROOT) -> frozenset[str]:
    """Return tracked repository-relative paths under ``prefix``."""
    args = ["ls-files", "--", prefix] if prefix else ["ls-files"]
    output = git(*args, root=root)
    return frozenset(output.splitlines()) if output else frozenset()


def tagged(relative: str, root: Path = REPO_ROOT, *, tag: str = PHASE_5_TAG) -> str:
    """Read a repository-relative file as a milestone git tag recorded it."""
    return git("show", f"{tag}:{relative}", root=root)


def syntax(relative: str, root: Path = REPO_ROOT) -> ast.Module:
    """Parse a repository-relative Python file into an AST."""
    return ast.parse(read(relative, root=root), filename=relative)


def defines(relative: str, *names: str, root: Path = REPO_ROOT) -> bool:
    """Whether top-level statements in ``relative`` define every name."""
    tree = syntax(relative, root=root)
    defined: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            defined.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defined.add(node.target.id)
        elif isinstance(node, ast.TypeAlias):
            defined.add(node.name.id)
    return set(names) <= defined


def assigned(tree: ast.AST, name: str) -> ast.expr:
    """Return the value expression assigned to ``name`` in ``tree``."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name and node.value is not None:
                return node.value
        elif isinstance(node, ast.TypeAlias) and node.name.id == name:
            return node.value
    raise LookupError(name)


def class_node(tree: ast.Module, name: str) -> ast.ClassDef:
    """Find a top-level class definition by name."""
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise LookupError(name)


def class_fields(relative: str, class_name: str, root: Path = REPO_ROOT) -> set[str]:
    """Return annotated field names defined directly on ``class_name`` in ``relative``."""
    cls = class_node(syntax(relative, root=root), class_name)
    return {
        item.target.id
        for item in cls.body
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
    }


def class_methods(relative: str, class_name: str, root: Path = REPO_ROOT) -> set[str]:
    """Return method names defined directly on ``class_name`` in ``relative``."""
    cls = class_node(syntax(relative, root=root), class_name)
    return {
        item.name for item in cls.body if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
    }


def literal_strings(node: ast.AST) -> tuple[str, ...]:
    """Extract all string constants inside an AST expression."""
    return tuple(
        item.value
        for item in ast.walk(node)
        if isinstance(item, ast.Constant) and isinstance(item.value, str)
    )


def phase_matrix(root: Path = REPO_ROOT) -> set[str]:
    """Read the flow-list ``phase`` matrix entries from ``.github/workflows/phase-verify.yml``."""
    text = read(PHASE_WORKFLOW, root=root)
    match = re.search(r"^\s*phase:\s*\[([^\]]+)\]", text, re.MULTILINE)
    if match is None:
        return set()
    return {item.strip().strip("\"'") for item in match[1].split(",") if item.strip()}


# Step 1 static checks (1-11) ---------------------------------------------------------------


def check_01_web_dependencies(root: Path = REPO_ROOT) -> bool:
    """Check 1: pyproject.toml lists fastapi, starlette, and uvicorn without uvicorn[standard]."""
    deps = [str(item) for item in array_of(config("project", "dependencies", root=root))]
    return (
        any(dep.startswith("fastapi>=") for dep in deps)
        and any(dep.startswith("starlette>=") for dep in deps)
        and any(dep.startswith("uvicorn>=") for dep in deps)
        and not any("uvicorn[standard]" in dep for dep in deps)
    )


def check_02_layers_contract(root: Path = REPO_ROOT) -> bool:
    """Check 2: layers contract puts weatherbot.cli above weatherbot.web as separate layers."""
    contracts = [
        object_of(item) for item in array_of(config("tool", "importlinter", "contracts", root=root))
    ]
    layers_contract = next(
        (
            c
            for c in contracts
            if c.get("type") == "layers" and c.get("name") == "Layers import downward only"
        ),
        None,
    )
    if layers_contract is None:
        return False
    layers = [str(item) for item in array_of(layers_contract.get("layers", []))]
    return layers == [
        "weatherbot.cli",
        "weatherbot.web",
        "weatherbot.services",
        "weatherbot.sources | weatherbot.engine",
        "weatherbot.models",
    ] and not any("weatherbot.cli" in layer and "weatherbot.web" in layer for layer in layers)


def check_03_web_app(root: Path = REPO_ROOT) -> bool:
    """Check 3: web/app.py defines create_app and WebState with docs/redoc off and openapi_url."""
    rel = f"{WEB}/app.py"
    if not files_exist(rel, root=root) or not defines(rel, "create_app", "WebState", root=root):
        return False
    tree = syntax(rel, root=root)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "FastAPI"
        ):
            kw = {
                item.arg: ast.literal_eval(item.value)
                for item in node.keywords
                if item.arg in {"docs_url", "redoc_url", "openapi_url"}
            }
            if kw == {
                "docs_url": None,
                "redoc_url": None,
                "openapi_url": "/api/openapi.json",
            }:
                return True
    return False


def _ast_references_forbidden_middleware(tree: ast.AST) -> bool:
    forbidden = {"CORSMiddleware", "BaseHTTPMiddleware"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in forbidden:
            return True
        if isinstance(node, ast.Attribute) and node.attr in forbidden:
            return True
        if isinstance(node, ast.alias) and (node.name in forbidden or node.asname in forbidden):
            return True
    return False


def check_04_web_guards(root: Path = REPO_ROOT) -> bool:
    """Check 4: web/guards.py mounts loopback hosts, CSP/Fetch guards, and no CORS/BaseHTTP."""
    rel = f"{WEB}/guards.py"
    if not files_exist(rel, root=root):
        return False
    tree = syntax(rel, root=root)
    hosts = tuple(cast("tuple[str, ...]", ast.literal_eval(assigned(tree, "ALLOWED_HOSTS"))))
    if hosts != ("127.0.0.1", "localhost", "[::1]"):
        return False
    needles = (
        "TrustedHostMiddleware",
        "sec-fetch-site",
        "frame-ancestors 'none'",
        "script-src 'self'",
        "https://tile.openstreetmap.org",
        "nosniff",
        "strict-origin-when-cross-origin",
        "no-store",
    )
    if not contains(rel, *needles, root=root):
        return False
    py_files = [p for p in tracked("src/weatherbot", root=root) if p.endswith(".py")]
    return not any(_ast_references_forbidden_middleware(syntax(p, root=root)) for p in py_files)


def _catches_system_exit(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            names = {item.id for item in ast.walk(node.type) if isinstance(item, ast.Name)}
            if "SystemExit" in names:
                return True
    return False


def check_05_web_server(root: Path = REPO_ROOT) -> bool:
    """Check 5: web/server.py defines WebServer, subclasses uvicorn.Server, catches SystemExit."""
    rel = f"{WEB}/server.py"
    if not files_exist(rel, root=root) or not defines(
        rel, "WebServer", "EmbeddedUvicornServer", root=root
    ):
        return False
    tree = syntax(rel, root=root)
    uvicorn_cls = class_node(tree, "EmbeddedUvicornServer")
    methods = class_methods(rel, "EmbeddedUvicornServer", root=root)
    subclasses_uvicorn = any(
        isinstance(base, ast.Attribute)
        and isinstance(base.value, ast.Name)
        and base.value.id == "uvicorn"
        and base.attr == "Server"
        for base in uvicorn_cls.bases
    )
    return (
        subclasses_uvicorn
        and "capture_signals" in methods
        and _catches_system_exit(tree)
        and contains(rel, "SO_EXCLUSIVEADDRUSE", "timeout_graceful_shutdown", root=root)
    )


def check_06_web_settings(root: Path = REPO_ROOT) -> bool:
    """Check 6: services/config.py defines WebSettings and overrides; conftest sets port 0."""
    cfg_rel = f"{SERVICES}/config.py"
    conftest_rel = "tests/conftest.py"
    if not files_exist(cfg_rel, conftest_rel, root=root) or not defines(
        cfg_rel, "WebSettings", "ENVIRONMENT_OVERRIDES", root=root
    ):
        return False
    fields = class_fields(cfg_rel, "WebSettings", root=root)
    overrides = cast(
        "dict[tuple[str, str], str]",
        ast.literal_eval(assigned(syntax(cfg_rel, root=root), "ENVIRONMENT_OVERRIDES")),
    )
    return (
        {"host", "port"} <= fields
        and overrides.get(("web", "host")) == "WEATHERBOT_WEB_HOST"
        and overrides.get(("web", "port")) == "WEATHERBOT_WEB_PORT"
        and contains(conftest_rel, '"WEATHERBOT_WEB_PORT", "0"', root=root)
    )


def check_07_cli_serve_web(root: Path = REPO_ROOT) -> bool:
    """Check 7: cli/serve.py keeps ProcessLock and run_monitor, uses WebServer, --open/--no-open."""
    serve_rel = f"{CLI}/serve.py"
    runtime_rel = f"{CLI}/runtime.py"
    if not files_exist(serve_rel, runtime_rel, root=root):
        return False
    return contains(
        serve_rel,
        "ProcessLock(paths.monitor_lock_path)",
        "run_monitor(",
        "WebServer",
        '"--open/--no-open"',
        root=root,
    ) and "open_browser" in class_fields(runtime_rel, "Runtime", root=root)


def check_08_doctor_web_check(root: Path = REPO_ROOT) -> bool:
    """Check 8: services/doctor.py calls Check('web', ...) in AST."""
    rel = f"{SERVICES}/doctor.py"
    if not files_exist(rel, root=root) or not defines(rel, "web_check", root=root):
        return False
    tree = syntax(rel, root=root)
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Check"
        and bool(node.args)
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "web"
        for node in ast.walk(tree)
    )


def check_09_openapi_export(root: Path = REPO_ROOT) -> bool:
    """Check 9: scripts/export_openapi.py has --check; openapi.json is 3.1 with /api/health."""
    script_rel = "scripts/export_openapi.py"
    if not files_exist(script_rel, OPENAPI_SPEC, root=root):
        return False
    spec = json_file(OPENAPI_SPEC, root=root)
    paths = object_of(spec.get("paths", {}))
    return (
        contains(script_rel, '"--check"', root=root)
        and str(spec.get("openapi", "")).startswith("3.1.")
        and "/api/health" in paths
        and "/docs" not in paths
        and "/redoc" not in paths
    )


def check_10_gitignore_and_phase04_tag(root: Path = REPO_ROOT) -> bool:
    """Check 10: .gitignore holds /src/weatherbot/web/static/ and verify_phase04 reads tag."""
    return contains(".gitignore", "/src/weatherbot/web/static/", root=root) and contains(
        "scripts/verify_phase04.py",
        'PHASE_4_TAG: Final = "v2.0.0-phase-4"',
        'tagged("README.md", root=root)',
        root=root,
    )


def check_11_step1_tests_tracked(root: Path = REPO_ROOT) -> bool:
    """Check 11: Step 1 web, serve-web, and doctor-web test files are tracked."""
    return files_exist(
        "tests/web/test_web_app.py",
        "tests/web/test_api_guards.py",
        "tests/web/test_built_interface.py",
        "tests/web/test_web_server.py",
        "tests/web/test_web_settings.py",
        "tests/web/test_openapi_export.py",
        "tests/cli/test_serve_web.py",
        "tests/services/test_doctor_web.py",
        root=root,
    )


# Step 2 static checks (12-18) --------------------------------------------------------------


def check_12_read_route_modules(root: Path = REPO_ROOT) -> bool:
    """Check 12: web/routes/ holds all 10 read modules and create_app includes each."""
    app_rel = f"{WEB}/app.py"
    route_files = [f"{WEB}/routes/{name}.py" for name in READ_ROUTE_MODULES]
    if not files_exist(app_rel, *route_files, root=root):
        return False
    expected_includes = tuple(f"app.include_router({name}_router)" for name in READ_ROUTE_MODULES)
    return contains(app_rel, *expected_includes, root=root)


def check_13_openapi_read_paths(root: Path = REPO_ROOT) -> bool:
    """Check 13: docs/api/openapi.json holds every read path of Step 2."""
    if not files_exist(OPENAPI_SPEC, root=root):
        return False
    paths = object_of(json_file(OPENAPI_SPEC, root=root).get("paths", {}))
    return set(STEP_2_READ_PATHS) <= set(paths)


def check_14_map_layers_and_cache(root: Path = REPO_ROOT) -> bool:
    """Check 14: web/map_layers.py defines layer builder, antimeridian unwrap, and 8-item cache."""
    rel = f"{WEB}/map_layers.py"
    required = (
        "MAX_SNAPSHOT_CACHE_SIZE",
        "SnapshotLayerCache",
        "build_map_response",
        "build_storm_map_layers",
        "unwrap_longitude",
    )
    if not files_exist(rel, root=root) or not defines(rel, *required, root=root):
        return False
    tree = syntax(rel, root=root)
    return ast.literal_eval(assigned(tree, "MAX_SNAPSHOT_CACHE_SIZE")) == 8  # noqa: PLR2004


def check_15_replay_corpus_methods(root: Path = REPO_ROOT) -> bool:
    """Check 15: ReplayCorpus defines advisories and snapshot in AST."""
    rel = f"{SERVICES}/replay.py"
    if not files_exist(rel, root=root):
        return False
    methods = class_methods(rel, "ReplayCorpus", root=root)
    return {"advisories", "snapshot"} <= methods


def check_16_serve_corpus_and_health(root: Path = REPO_ROOT) -> bool:
    """Check 16: serve offers --corpus and HealthResponse has corpus."""
    serve_rel = f"{CLI}/serve.py"
    schemas_rel = f"{WEB}/schemas.py"
    if not files_exist(serve_rel, schemas_rel, root=root):
        return False
    return contains(serve_rel, '"--corpus"', root=root) and "corpus" in class_fields(
        schemas_rel, "HealthResponse", root=root
    )


def _async_function_touches_repository(func: ast.AsyncFunctionDef) -> bool:
    repo_names = {
        "AssessmentRepository",
        "CycleRepository",
        "HeartbeatRepository",
        "LocationRepository",
        "SnapshotRepository",
    }
    return any(isinstance(node, ast.Name) and node.id in repo_names for node in ast.walk(func))


def check_17_no_async_db_routes(root: Path = REPO_ROOT) -> bool:
    """Check 17: no web/ module defines an async def route that reads a repository."""
    route_files = [
        p
        for p in tracked(f"{WEB}/routes", root=root)
        if p.endswith(".py") and not p.endswith("__init__.py")
    ]
    if not route_files:
        return False
    sync_only_routes = {f"{WEB}/routes/{name}.py" for name in (*READ_ROUTE_MODULES, "health")}
    for rel in route_files:
        tree = syntax(rel, root=root)
        for node in tree.body:
            if isinstance(node, ast.AsyncFunctionDef) and (
                rel in sync_only_routes or _async_function_touches_repository(node)
            ):
                return False
    return True


def check_18_step2_tests_tracked(root: Path = REPO_ROOT) -> bool:
    """Check 18: Step 2 read, CLI parity, privacy, map_layers, and replay_routes tests tracked."""
    return files_exist(
        "tests/web/test_api_reads.py",
        "tests/web/test_api_cli_parity.py",
        "tests/web/test_api_privacy.py",
        "tests/web/test_map_layers.py",
        "tests/web/test_replay_routes.py",
        root=root,
    )


# Step 3 static checks (19-25) --------------------------------------------------------------


def check_19_events_service(root: Path = REPO_ROOT) -> bool:
    """Check 19: services/events.py defines EventHub, CycleWatcher, BrowserChannel, EVENT_KINDS."""
    rel = f"{SERVICES}/events.py"
    required = ("EventHub", "CycleWatcher", "StalenessTimer", "BrowserChannel", "EVENT_KINDS")
    if not files_exist(rel, root=root) or not defines(rel, *required, root=root):
        return False
    tree = syntax(rel, root=root)
    kinds = tuple(cast("tuple[str, ...]", ast.literal_eval(assigned(tree, "EVENT_KINDS"))))
    return kinds == EVENT_KINDS


def check_20_browser_channel_and_setting(root: Path = REPO_ROOT) -> bool:
    """Check 20: CHANNEL_NAMES holds browser and NotificationSettings has browser override."""
    notif_rel = f"{SERVICES}/notifications.py"
    cfg_rel = f"{SERVICES}/config.py"
    if not files_exist(notif_rel, cfg_rel, root=root):
        return False
    channels = set(literal_strings(assigned(syntax(notif_rel, root=root), "CHANNEL_NAMES")))
    fields = class_fields(cfg_rel, "NotificationSettings", root=root)
    overrides = cast(
        "dict[tuple[str, str], str]",
        ast.literal_eval(assigned(syntax(cfg_rel, root=root), "ENVIRONMENT_OVERRIDES")),
    )
    return (
        {"log", "toast", "browser"} <= channels
        and "browser" in fields
        and overrides.get(("notifications", "browser")) == "WEATHERBOT_NOTIFICATIONS_BROWSER"
    )


def check_21_sse_route_and_openapi(root: Path = REPO_ROOT) -> bool:
    """Check 21: web/routes/events.py uses EventSourceResponse and OpenAPI holds StreamEvent."""
    rel = f"{WEB}/routes/events.py"
    if not files_exist(rel, OPENAPI_SPEC, root=root):
        return False
    spec = json_file(OPENAPI_SPEC, root=root)
    schemas = object_of(object_of(spec.get("components", {})).get("schemas", {}))
    query_key_schema = object_of(schemas.get("QueryKey", {}))
    enum_vals = {str(item) for item in array_of(query_key_schema.get("enum", []))}
    return (
        contains(rel, "EventSourceResponse", "AsyncIterable[StreamEvent]", root=root)
        and "StreamEvent" in schemas
        and set(QUERY_KEYS) <= enum_vals
    )


def check_22_action_routes(root: Path = REPO_ROOT) -> bool:
    """Check 22: web/routes/actions.py defines the four writes and triggers manual cycle."""
    rel = f"{WEB}/routes/actions.py"
    if not files_exist(rel, root=root) or not defines(rel, "MANUAL_TRIGGER", root=root):
        return False
    trigger = ast.literal_eval(assigned(syntax(rel, root=root), "MANUAL_TRIGGER"))
    return trigger == "manual" and contains(
        rel,
        '"/api/locations"',
        '"/api/locations/evacuation"',
        '"/api/cycles"',
        '"/api/notifications/test"',
        "start_manual_cycle",
        root=root,
    )


def check_23_serve_wires_hub(root: Path = REPO_ROOT) -> bool:
    """Check 23: cli/serve.py passes hub.cycle_listener and hub.close to WebServer."""
    rel = f"{CLI}/serve.py"
    if not files_exist(rel, root=root):
        return False
    return contains(rel, "hub.cycle_listener", "hub.close", root=root)


def check_24_step3_tests_tracked(root: Path = REPO_ROOT) -> bool:
    """Check 24: Step 3 event, channel, action, and live tests tracked and marked live."""
    live_rel = "tests/live/test_web_live.py"
    return files_exist(
        "tests/services/test_event_hub.py",
        "tests/services/test_cycle_watcher.py",
        "tests/services/test_staleness_timer.py",
        "tests/services/test_browser_channel.py",
        "tests/web/test_event_stream.py",
        "tests/web/test_api_actions.py",
        live_rel,
        root=root,
    ) and contains(live_rel, "pytest.mark.live", root=root)


def check_25_event_models_never_locate(root: Path = REPO_ROOT) -> bool:
    """Check 25: StreamEvent in web/schemas.py declares no coordinate or geometry field."""
    rel = f"{WEB}/schemas.py"
    if not files_exist(rel, root=root):
        return False
    fields = class_fields(rel, "StreamEvent", root=root)
    return bool(fields) and fields.isdisjoint(FORBIDDEN_EVENT_FIELDS)


# Step 4 static checks (26-35) --------------------------------------------------------------


def _is_exact_semver(version: str) -> bool:
    return bool(re.fullmatch(r"\d+\.\d+\.\d+", version))


def check_26_frontend_package_pins(root: Path = REPO_ROOT) -> bool:
    """Check 26: frontend/package.json private, node>=24.15, exact pins, TS 5, .nvmrc=24, lock."""
    pkg_rel = f"{FRONTEND}/package.json"
    nvmrc_rel = f"{FRONTEND}/.nvmrc"
    lock_rel = f"{FRONTEND}/package-lock.json"
    if not files_exist(pkg_rel, nvmrc_rel, lock_rel, root=root):
        return False
    pkg = json_file(pkg_rel, root=root)
    if pkg.get("private") is not True or read(nvmrc_rel, root=root).strip() != "24":
        return False
    engines = object_of(pkg.get("engines", {}))
    node_engine = str(engines.get("node", ""))
    match = re.fullmatch(r">=(\d+)\.(\d+)", node_engine)
    if match is None:
        return False
    major, minor = int(match[1]), int(match[2])
    if (major, minor) < (24, 15):
        return False
    deps = {
        **object_of(pkg.get("dependencies", {})),
        **object_of(pkg.get("devDependencies", {})),
    }
    required_exact = (
        "react",
        "react-dom",
        "typescript",
        "vite",
        "openapi-typescript",
        "eslint-plugin-security",
    )
    if not all(_is_exact_semver(str(deps.get(name, ""))) for name in required_exact):
        return False
    return str(deps.get("typescript", "")).startswith("5.")


def check_27_frontend_scripts(root: Path = REPO_ROOT) -> bool:
    """Check 27: package.json scripts include lint, api:check, licenses:check, audit, test."""
    pkg = json_file(f"{FRONTEND}/package.json", root=root)
    scripts = {str(k): str(v) for k, v in object_of(pkg.get("scripts", {})).items()}
    return (
        "--max-warnings 0" in scripts.get("lint", "")
        and "--check" in scripts.get("api:check", "")
        and "check-licenses.mjs" in scripts.get("licenses:check", "")
        and "--audit-level=high" in scripts.get("audit", "")
        and "vitest" in scripts.get("test", "")
    )


def check_28_vite_config(root: Path = REPO_ROOT) -> bool:
    """Check 28: vite.config.ts writes to web/static, licenses.json, nonce, and 127.0.0.1."""
    rel = f"{FRONTEND}/vite.config.ts"
    return files_exist(rel, root=root) and contains(
        rel,
        "../src/weatherbot/web/static",
        "licenses.json",
        "__CSP_NONCE__",
        "127.0.0.1",
        root=root,
    )


def check_29_eslint_config(root: Path = REPO_ROOT) -> bool:
    """Check 29: eslint.config.js loads eslint-plugin-security and typescript-eslint."""
    rel = f"{FRONTEND}/eslint.config.js"
    return files_exist(rel, root=root) and contains(
        rel,
        "eslint-plugin-security",
        "typescript-eslint",
        root=root,
    )


def check_30_frontend_api_and_no_vite_env(root: Path = REPO_ROOT) -> bool:
    """Check 30: schema.d.ts, keys.ts, and useEventStream.ts tracked; no import.meta.env.VITE_."""
    required = (
        f"{FRONTEND}/src/api/schema.d.ts",
        f"{FRONTEND}/src/api/keys.ts",
        f"{FRONTEND}/src/events/useEventStream.ts",
    )
    if not files_exist(*required, root=root):
        return False
    src_files = tracked(f"{FRONTEND}/src", root=root)
    return bool(src_files) and not any(
        "import.meta.env.VITE_" in read(path, root=root) for path in src_files
    )


def check_31_frontend_index_html(root: Path = REPO_ROOT) -> bool:
    """Check 31: index.html has no inline script/style, links /theme-init.js, has nonce meta."""
    rel = f"{FRONTEND}/index.html"
    if not files_exist(rel, root=root):
        return False
    text = read(rel, root=root)
    script_tags = re.findall(r"<script\b[^>]*>", text, re.IGNORECASE)
    has_inline_script = any("src=" not in tag for tag in script_tags)
    has_style_tag = bool(re.search(r"<style\b", text, re.IGNORECASE))
    return (
        bool(script_tags)
        and not has_inline_script
        and not has_style_tag
        and 'src="/theme-init.js"' in text
        and 'property="csp-nonce"' in text
        and 'nonce="__CSP_NONCE__"' in text
    )


def check_32_ci_frontend_security_package(root: Path = REPO_ROOT) -> bool:
    """Check 32: ci.yml has frontend in gate, npm audit in security, build+smoke in package."""
    if not files_exist(CI_WORKFLOW, "scripts/smoke_installed_web.py", root=root):
        return False
    text = read(CI_WORKFLOW, root=root)
    gate_needs = re.search(r"gate:.*?needs:\s*\[([^\]]+)\]", text, re.DOTALL)
    if gate_needs is None:
        return False
    needs = {item.strip() for item in gate_needs[1].split(",")}
    build_pos = text.find("npm --prefix frontend run build")
    uv_build_pos = text.find("uv build")
    smoke_pos = text.find("scripts/smoke_installed_web.py")
    return (
        "frontend" in needs
        and "npm --prefix frontend audit --audit-level=high" in text
        and build_pos != -1
        and uv_build_pos != -1
        and smoke_pos != -1
        and build_pos < uv_build_pos < smoke_pos
    )


def check_33_setup_node_sha_pinned(root: Path = REPO_ROOT) -> bool:
    """Check 33: actions/setup-node in ci.yml and phase-verify.yml is pinned to a 40-hex SHA."""
    pattern = re.compile(r"uses:\s*actions/setup-node@([^\s#]+)(\s+#\s*v\d+\.\d+\.\d+)?")
    sha_re = re.compile(r"^[0-9a-f]{40}$")
    total = 0
    for workflow in (CI_WORKFLOW, PHASE_WORKFLOW):
        text = read(workflow, root=root)
        matches = list(pattern.finditer(text))
        if not matches:
            return False
        for m in matches:
            if not sha_re.fullmatch(m[1]) or m[2] is None:
                return False
            total += 1
    return total >= 4  # noqa: PLR2004


def check_34_dependabot_and_precommit(root: Path = REPO_ROOT) -> bool:
    """Check 34: dependabot.yml has npm for /frontend and pre-commit has frontend hooks."""
    if not files_exist(DEPENDABOT_CONFIG, PRE_COMMIT_CONFIG, root=root):
        return False
    return contains(
        DEPENDABOT_CONFIG, "package-ecosystem: npm", "directory: /frontend", root=root
    ) and contains(PRE_COMMIT_CONFIG, "id: frontend-lint", "id: npm-audit", root=root)


def check_35_gitignore_and_license_allowlist(root: Path = REPO_ROOT) -> bool:
    """Check 35: .gitignore holds frontend outputs and check-licenses.mjs names 6 licences."""
    script_rel = f"{FRONTEND}/scripts/check-licenses.mjs"
    if not files_exist(".gitignore", script_rel, root=root):
        return False
    return contains(
        ".gitignore",
        "frontend/node_modules/",
        "/src/weatherbot/web/static/",
        root=root,
    ) and contains(script_rel, *ALLOWED_LICENSES, root=root)


# Step 5 static checks (36-39) --------------------------------------------------------------


def check_36_pages_and_tests_tracked(root: Path = REPO_ROOT) -> bool:
    """Check 36: frontend/src/pages/ tracks all 5 pages and their .test.tsx files."""
    files = [
        f"{FRONTEND}/src/pages/{name}{suffix}"
        for name in PAGE_NAMES
        for suffix in (".tsx", ".test.tsx")
    ]
    return files_exist(*files, root=root)


def check_37_no_dangerously_set_inner_html(root: Path = REPO_ROOT) -> bool:
    """Check 37: no file under frontend/src uses dangerouslySetInnerHTML."""
    src_files = tracked(f"{FRONTEND}/src", root=root)
    return bool(src_files) and not any(
        "dangerouslySetInnerHTML" in read(path, root=root) for path in src_files
    )


def check_38_api_fixtures_and_exporter(root: Path = REPO_ROOT) -> bool:
    """Check 38: scripts/export_api_fixtures.py has --check; 12 fixtures and test tracked."""
    script_rel = "scripts/export_api_fixtures.py"
    test_rel = "tests/web/test_api_fixtures.py"
    fixtures = [f"{FRONTEND}/src/test/fixtures/{name}" for name in API_FIXTURE_FILES]
    return files_exist(script_rel, test_rel, *fixtures, root=root) and contains(
        script_rel, '"--check"', root=root
    )


def check_39_browser_notification_caller(root: Path = REPO_ROOT) -> bool:
    """Check 39: new Notification( appears under frontend/src only in notifications/notify.ts."""
    notify_rel = f"{FRONTEND}/src/notifications/notify.ts"
    if not files_exist(notify_rel, root=root):
        return False
    non_test_files = [
        p
        for p in tracked(f"{FRONTEND}/src", root=root)
        if not p.endswith((".test.ts", ".test.tsx"))
    ]
    callers = [p for p in non_test_files if "new Notification(" in read(p, root=root)]
    return callers == [notify_rel] and contains(
        notify_rel,
        "readBrowserNotificationsEnabled()",
        'Notification.permission !== "granted"',
        'document.visibilityState !== "hidden"',
        root=root,
    )


# Step 6 static checks (40-43) --------------------------------------------------------------


def check_40_leaflet_pin_no_react_leaflet(root: Path = REPO_ROOT) -> bool:
    """Check 40: frontend/package.json pins leaflet at 1.x.x exact; no react-leaflet in pkg/lock."""
    pkg_rel = f"{FRONTEND}/package.json"
    lock_rel = f"{FRONTEND}/package-lock.json"
    if not files_exist(pkg_rel, lock_rel, root=root):
        return False
    pkg = json_file(pkg_rel, root=root)
    deps = object_of(pkg.get("dependencies", {}))
    leaflet_ver = str(deps.get("leaflet", ""))
    return (
        _is_exact_semver(leaflet_ver)
        and leaflet_ver.startswith("1.")
        and "react-leaflet" not in read(pkg_rel, root=root)
        and "react-leaflet" not in read(lock_rel, root=root)
    )


def check_41_map_files_and_osm_options(root: Path = REPO_ROOT) -> bool:
    """Check 41: useLeafletMap.ts and layers.ts tracked with tile URL, policy, attribution."""
    hook_rel = f"{FRONTEND}/src/map/useLeafletMap.ts"
    layers_rel = f"{FRONTEND}/src/map/layers.ts"
    map_rel = f"{FRONTEND}/src/map/MapView.tsx"
    if not files_exist(hook_rel, layers_rel, map_rel, root=root):
        return False
    combined = read(hook_rel, root=root) + "\n" + read(layers_rel, root=root)
    return (
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png" in combined
        and "strict-origin-when-cross-origin" in combined
        and "OpenStreetMap contributors" in combined
    )


def check_42_data_sources_osm_referrer_policy(root: Path = REPO_ROOT) -> bool:
    """Check 42: docs/DATA_SOURCES.md basemap entry names strict-origin-when-cross-origin."""
    return files_exist(DATA_SOURCES, root=root) and contains(
        DATA_SOURCES,
        "basemap-osm-tiles",
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "strict-origin-when-cross-origin",
        root=root,
    )


def check_43_map_tests_tracked(root: Path = REPO_ROOT) -> bool:
    """Check 43: frontend/src/map/layers.test.ts and MapView.test.tsx are tracked."""
    return files_exist(
        f"{FRONTEND}/src/map/layers.test.ts",
        f"{FRONTEND}/src/map/MapView.test.tsx",
        root=root,
    )


# Step 7 static checks (44-47) --------------------------------------------------------------


def check_44_demo_and_idle_scripts(root: Path = REPO_ROOT) -> bool:
    """Check 44: serve_demo.py and measure_idle.py tracked; psutil and types-psutil in dev group."""
    if not files_exist(
        "scripts/serve_demo.py",
        "scripts/measure_idle.py",
        "tests/scripts/test_serve_demo.py",
        "tests/scripts/test_measure_idle.py",
        root=root,
    ):
        return False
    dev_deps = [str(item) for item in array_of(config("dependency-groups", "dev", root=root))]
    return any(dep.startswith(("psutil>=", "psutil==")) for dep in dev_deps) and any(
        dep.startswith(("types-psutil>=", "types-psutil==")) for dep in dev_deps
    )


def check_45_playwright_specs_tracked(root: Path = REPO_ROOT) -> bool:
    """Check 45: playwright.config.ts and the four e2e specs tracked; idle.spec.ts tagged @idle."""
    idle_rel = f"{FRONTEND}/e2e/idle.spec.ts"
    return files_exist(
        f"{FRONTEND}/playwright.config.ts",
        f"{FRONTEND}/e2e/guard.ts",
        f"{FRONTEND}/e2e/dashboard.spec.ts",
        f"{FRONTEND}/e2e/map.spec.ts",
        f"{FRONTEND}/e2e/screens.spec.ts",
        idle_rel,
        root=root,
    ) and contains(idle_rel, "@idle", root=root)


def check_46_ci_browser_job(root: Path = REPO_ROOT) -> bool:
    """Check 46: ci.yml has browser job in gate.needs and upload-artifact pinned to 40-hex SHA."""
    if not files_exist(CI_WORKFLOW, root=root):
        return False
    text = read(CI_WORKFLOW, root=root)
    gate_needs = re.search(r"gate:.*?needs:\s*\[([^\]]+)\]", text, re.DOTALL)
    if gate_needs is None:
        return False
    needs = {item.strip() for item in gate_needs[1].split(",")}
    upload = re.search(r"uses:\s*actions/upload-artifact@([0-9a-f]{40})\s+#\s*v\d+\.\d+\.\d+", text)
    return "browser" in needs and "npm --prefix frontend run e2e" in text and upload is not None


def check_47_readme_phase05(root: Path = REPO_ROOT) -> bool:
    """Check 47: README.md has dashboard section, CLI commands, and Phase 5 complete Status."""
    if not files_exist("README.md", root=root):
        return False
    text = read("README.md", root=root)
    required = (
        "### The dashboard",
        "weatherbot status",
        "weatherbot replay",
        "weatherbot locations evacuation",
    )
    if not all(needle in text for needle in required):
        return False
    status_match = re.search(r"^## Status$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if status_match is None:
        return False
    status_block = status_match[1]
    return (
        "Phase 5" in status_block
        and "Phase 6" in status_block
        and "is in progress" not in status_block.split("Phase 5", 1)[1].split(";", 1)[0]
    )


# Step 8 self-checks (48-53) ----------------------------------------------------------------


def check_48_verifier_self_check(root: Path = REPO_ROOT) -> bool:
    """Check 48: scripts/verify_phase05.py is tracked, valid Python, 53 checks, 8 modes."""
    rel = "scripts/verify_phase05.py"
    if not files_exist(rel, root=root):
        return False
    syntax(rel, root=root)
    text = read(rel, root=root)
    return (
        len(STATIC_CHECKS) == 53  # noqa: PLR2004
        and len(V_MATRIX) == 32  # noqa: PLR2004
        and all(f'"{mode}"' in text for mode in MODES)
    )


def check_49_verification_test_tracked(root: Path = REPO_ROOT) -> bool:
    """Check 49: test_phase05_verification.py is tracked and covers fast, matrix, mutations."""
    rel = "tests/test_phase05_verification.py"
    return files_exist(rel, root=root) and contains(
        rel,
        "test_fast_verification_passes_all_static_checks_within_thirty_seconds",
        "test_phase_verify_workflow_includes_phase_05",
        "test_a_changed_deliverable_turns_exactly_its_check_red",
        root=root,
    )


def check_50_qa_findings_doc(root: Path = REPO_ROOT) -> bool:
    """Check 50: docs/phase05-qa-findings.md tracked with PR #56, Steps 1-8, and idle numbers."""
    if not files_exist(QA_FINDINGS, root=root):
        return False
    required = (
        "PR #56",
        "Step 1",
        "Step 2",
        "Step 3",
        "Step 4",
        "Step 5",
        "Step 6",
        "Step 7",
        "Step 8",
        "window=600.1s",
        "server_cpu=0.4843%",
        "tab_cpu=0.0020%",
        "## Source-drift observations",
        "## Live smoke runs",
        "## Pre-ship items",
    )
    return contains(QA_FINDINGS, *required, root=root)


def check_51_roadmaps_consistent(root: Path = REPO_ROOT) -> bool:
    """Check 51: phase05-roadmap.md exists with Steps 1-8 and ROADMAP.md holds Phase 5."""
    if not files_exist(ROADMAP, PHASE_ROADMAP, root=root):
        return False
    step_headers = tuple(f"## Step {n} —" for n in range(1, 9))
    return contains(ROADMAP, "### Phase 5 — Web app MVP", root=root) and contains(
        PHASE_ROADMAP, *step_headers, root=root
    )


def check_52_matrix_includes_05_and_node_setup(root: Path = REPO_ROOT) -> bool:
    """Check 52: phase-verify.yml includes 01..05 and runs setup-node + npm ci only for 05."""
    if not {"01", "02", "03", "04", "05"} <= phase_matrix(root=root):
        return False
    return contains(
        PHASE_WORKFLOW,
        "if: \"!cancelled() && matrix.phase == '05'\"",
        "node-version-file: frontend/.nvmrc",
        "run: npm --prefix frontend ci",
        root=root,
    )


def check_53_security_gate_wired(root: Path = REPO_ROOT) -> bool:
    """Check 53: security gate hooks and frontend hooks in pre-commit and phase-verify.yml."""
    return contains(
        PRE_COMMIT_CONFIG,
        "id: gitleaks",
        "id: bandit",
        "id: pip-audit",
        "id: personal-data",
        "id: frontend-lint",
        "id: npm-audit",
        root=root,
    ) and contains(
        PHASE_WORKFLOW,
        "uv run python scripts/verify_phase${{ matrix.phase }}.py --security",
        root=root,
    )


STATIC_CHECKS: tuple[Check, ...] = (
    # Step 1 — The web server inside serve (1-11)
    (
        "pyproject.toml lists fastapi, starlette, and uvicorn without uvicorn[standard]",
        check_01_web_dependencies,
    ),
    (
        "layers contract puts weatherbot.cli above weatherbot.web as separate layers",
        check_02_layers_contract,
    ),
    (
        "web/app.py defines create_app and WebState with docs/redoc off and /api/openapi.json",
        check_03_web_app,
    ),
    (
        "web/guards.py mounts loopback TrustedHostMiddleware, CSP/Fetch guards, no CORS/BaseHTTP",
        check_04_web_guards,
    ),
    (
        "web/server.py defines WebServer, subclasses uvicorn.Server, and catches SystemExit",
        check_05_web_server,
    ),
    (
        "services/config.py defines WebSettings and overrides; tests/conftest.py sets port 0",
        check_06_web_settings,
    ),
    (
        "cli/serve.py keeps ProcessLock and run_monitor, uses WebServer, offers --open/--no-open",
        check_07_cli_serve_web,
    ),
    (
        "services/doctor.py defines web_check calling Check('web', ...)",
        check_08_doctor_web_check,
    ),
    (
        "scripts/export_openapi.py offers --check and docs/api/openapi.json is OpenAPI 3.1",
        check_09_openapi_export,
    ),
    (
        ".gitignore holds /src/weatherbot/web/static/ and verify_phase04.py check 46 reads tag",
        check_10_gitignore_and_phase04_tag,
    ),
    (
        "Step 1 web, guards, built-interface, server, settings, openapi, serve, and doctor tests",
        check_11_step1_tests_tracked,
    ),
    # Step 2 — The read API and the map's geometry (12-18)
    (
        "web/routes/ holds all 10 read route modules and create_app includes each router",
        check_12_read_route_modules,
    ),
    (
        "docs/api/openapi.json holds every read path of Step 2",
        check_13_openapi_read_paths,
    ),
    (
        "web/map_layers.py defines layer builders, antimeridian unwrap, and 8-snapshot LRU cache",
        check_14_map_layers_and_cache,
    ),
    (
        "ReplayCorpus defines advisories and snapshot methods",
        check_15_replay_corpus_methods,
    ),
    (
        "cli/serve.py offers --corpus and HealthResponse declares corpus",
        check_16_serve_corpus_and_health,
    ),
    (
        "no web/ module defines an async def route that reads a repository or database",
        check_17_no_async_db_routes,
    ),
    (
        "Step 2 read, CLI-parity, privacy, map-layers, and replay-routes tests tracked",
        check_18_step2_tests_tracked,
    ),
    # Step 3 — The event stream, browser notifications, and the actions (19-25)
    (
        "services/events.py defines EventHub, CycleWatcher, BrowserChannel, and 8 EventKind names",
        check_19_events_service,
    ),
    (
        "CHANNEL_NAMES holds browser and NotificationSettings has browser with env override",
        check_20_browser_channel_and_setting,
    ),
    (
        "web/routes/events.py uses EventSourceResponse and OpenAPI holds StreamEvent + QueryKey",
        check_21_sse_route_and_openapi,
    ),
    (
        "web/routes/actions.py defines the four writes and starts cycles with trigger 'manual'",
        check_22_action_routes,
    ),
    (
        "cli/serve.py passes hub.cycle_listener to run_monitor and hub.close to WebServer",
        check_23_serve_wires_hub,
    ),
    (
        "Step 3 hub, watcher, timer, browser, stream, action, and live tests tracked",
        check_24_step3_tests_tracked,
    ),
    (
        "StreamEvent in web/schemas.py declares no coordinate, geometry, or distance field",
        check_25_event_models_never_locate,
    ),
    # Step 4 — The frontend chassis, its gate, and the wheel (26-35)
    (
        "frontend/package.json private, node>=24.15, exact version pins, TS 5, .nvmrc=24, lockfile",
        check_26_frontend_package_pins,
    ),
    (
        "frontend/package.json scripts include lint (--max-warnings 0), api:check, licenses, audit",
        check_27_frontend_scripts,
    ),
    (
        "frontend/vite.config.ts writes to ../src/weatherbot/web/static, licenses.json, and nonce",
        check_28_vite_config,
    ),
    (
        "frontend/eslint.config.js loads eslint-plugin-security and typescript-eslint",
        check_29_eslint_config,
    ),
    (
        "frontend/src/api/{schema.d.ts,keys.ts} and useEventStream.ts tracked; no VITE_ env use",
        check_30_frontend_api_and_no_vite_env,
    ),
    (
        "frontend/index.html has no inline script/style, links /theme-init.js, carries nonce meta",
        check_31_frontend_index_html,
    ),
    (
        "ci.yml has frontend in gate.needs, npm audit in security, and UI build + smoke in package",
        check_32_ci_frontend_security_package,
    ),
    (
        "every actions/setup-node use in ci.yml and phase-verify.yml is pinned to a 40-hex SHA",
        check_33_setup_node_sha_pinned,
    ),
    (
        ".github/dependabot.yml has npm for /frontend and pre-commit config has frontend hooks",
        check_34_dependabot_and_precommit,
    ),
    (
        ".gitignore holds frontend outputs and check-licenses.mjs names the 6 allowed licences",
        check_35_gitignore_and_license_allowlist,
    ),
    # Step 5 — The dashboard and the pages (36-39)
    (
        "frontend/src/pages/ tracks Dashboard, Storms, Alerts, Timeline, and Settings with tests",
        check_36_pages_and_tests_tracked,
    ),
    (
        "no file under frontend/src uses dangerouslySetInnerHTML",
        check_37_no_dangerously_set_inner_html,
    ),
    (
        "scripts/export_api_fixtures.py offers --check; 12 fixtures and test_api_fixtures tracked",
        check_38_api_fixtures_and_exporter,
    ),
    (
        "new Notification( appears under frontend/src only in notifications/notify.ts with guards",
        check_39_browser_notification_caller,
    ),
    # Step 6 — The map (40-43)
    (
        "frontend/package.json pins leaflet at 1.x.x exact; no react-leaflet in pkg or lock",
        check_40_leaflet_pin_no_react_leaflet,
    ),
    (
        "useLeafletMap.ts and layers.ts tracked with OSM tile URL, referrerPolicy, and attribution",
        check_41_map_files_and_osm_options,
    ),
    (
        "docs/DATA_SOURCES.md basemap entry names strict-origin-when-cross-origin",
        check_42_data_sources_osm_referrer_policy,
    ),
    (
        "frontend/src/map/layers.test.ts and MapView.test.tsx are tracked",
        check_43_map_tests_tracked,
    ),
    # Step 7 — The browser smoke, idle cost, and the operator's dashboard (44-47)
    (
        "scripts/serve_demo.py and measure_idle.py tracked; psutil and types-psutil in dev group",
        check_44_demo_and_idle_scripts,
    ),
    (
        "frontend/playwright.config.ts and 4 e2e specs tracked; idle.spec.ts tagged @idle",
        check_45_playwright_specs_tracked,
    ),
    (
        "ci.yml has browser job in gate.needs with actions/upload-artifact pinned to 40-hex SHA",
        check_46_ci_browser_job,
    ),
    (
        "README.md has dashboard section, CLI commands, and Status naming Phase 5 complete",
        check_47_readme_phase05,
    ),
    # Step 8 — QA & Verification Script self-checks (48-53)
    (
        "scripts/verify_phase05.py tracked, valid syntax, 53 static checks, 32 V-rows, and 8 modes",
        check_48_verifier_self_check,
    ),
    (
        "tests/test_phase05_verification.py tracked and covers --fast, matrix, and red checks",
        check_49_verification_test_tracked,
    ),
    (
        "docs/phase05-qa-findings.md tracked with PR #56, Steps 1-8, idle numbers, Pre-ship items",
        check_50_qa_findings_doc,
    ),
    (
        "phase05-roadmap.md Steps 1-8 and ROADMAP.md Phase 5 headers are consistent",
        check_51_roadmaps_consistent,
    ),
    (
        "phase-verify.yml includes 01..05 in matrix and sets up Node only for 05",
        check_52_matrix_includes_05_and_node_setup,
    ),
    (
        "security gate hooks and frontend hooks wired in pre-commit and --security in phase-verify",
        check_53_security_gate_wired,
    ),
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
    cwd: Path = REPO_ROOT,
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
            cwd=cwd,
            check=False,
            timeout=3600,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", **(env or {})},
        )
    except (OSError, subprocess.SubprocessError) as error:
        return report(Outcome(item_id, description, "FAIL", type(error).__name__))
    status: Status = "PASS" if result.returncode == 0 else "FAIL"
    detail = "" if status == "PASS" else f"exit {result.returncode}"
    return report(Outcome(item_id, description, status, detail))


def capture(
    argv: Sequence[str],
    *,
    cwd: Path = REPO_ROOT,
    timeout: int = 120,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a fixed command and capture its output; callers print only safe summaries."""
    executable = shutil.which(argv[0])
    if executable is None:
        raise RuntimeError
    return subprocess.run(  # noqa: S603 - fixed argv, no shell  # nosec B603
        [executable, *argv[1:]],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", **(env or {})},
    )


def parse_junit(path: Path) -> dict[str, Status]:
    """Read per-test outcomes from a pytest, Vitest, or Playwright JUnit XML file."""
    if not path.is_file():
        return {}
    from defusedxml import ElementTree  # noqa: PLC0415

    root = ElementTree.parse(path).getroot()
    if root is None:
        return {}
    outcomes: dict[str, Status] = {}
    for case in root.iter("testcase"):
        key = f"{case.attrib.get('classname', '')}.{case.attrib.get('name', '')}".strip(".")
        if case.find("failure") is not None or case.find("error") is not None:
            outcomes[key] = "FAIL"
        elif case.find("skipped") is not None:
            outcomes[key] = "SKIP"
        else:
            outcomes[key] = "PASS"
    return outcomes


def py_suites(tmp_dir: Path | None = None) -> tuple[list[Outcome], dict[str, Status]]:
    """Run Ruff, Pyright (host + Linux), import-linter, offline pytest, OpenAPI/fixtures, smoke."""
    heading("Python quality, offline tests, and wheel smoke (--py)")
    commands = (
        ("ruff_check", "ruff check", ["uv", "run", "ruff", "check"]),
        ("ruff_format", "ruff format --check", ["uv", "run", "ruff", "format", "--check"]),
        ("pyright", "pyright", ["uv", "run", "pyright"]),
        (
            "pyright_linux",
            "pyright --pythonplatform Linux",
            ["uv", "run", "pyright", "--pythonplatform", "Linux"],
        ),
        ("lint_imports", "lint-imports", ["uv", "run", "lint-imports"]),
        (
            "export_openapi_check",
            "scripts/export_openapi.py --check",
            ["uv", "run", "python", "scripts/export_openapi.py", "--check"],
        ),
        (
            "export_api_fixtures_check",
            "scripts/export_api_fixtures.py --check",
            ["uv", "run", "python", "scripts/export_api_fixtures.py", "--check"],
        ),
    )
    outcomes = [run_command(f"py.{key}", label, argv) for key, label, argv in commands]
    junit_dir = tmp_dir or Path(tempfile.mkdtemp(prefix="weatherbot-verify05-py-"))
    junit = junit_dir / "pytest.xml"
    coverage_file = junit_dir / "coverage.sqlite"
    cov_env = {"COVERAGE_FILE": str(coverage_file)}
    outcomes.append(
        run_command(
            "py.pytest",
            "pytest (offline, engine + policy branch coverage >= 90%)",
            [
                "uv",
                "run",
                "pytest",
                f"--junitxml={junit}",
                "--cov=weatherbot.engine",
                "--cov=weatherbot.services.policy",
                "--cov-branch",
                "--cov-fail-under=90",
            ],
            env=cov_env,
        )
    )
    outcomes.append(
        run_command(
            "py.coverage_policy",
            "coverage report on weatherbot.services.policy (>= 90% branch)",
            [
                "uv",
                "run",
                "coverage",
                "report",
                "--include=*/services/policy.py",
                "--fail-under=90",
            ],
            env=cov_env,
        )
    )
    if not (REPO_ROOT / "src/weatherbot/web/static/index.html").is_file():
        outcomes.append(
            run_command(
                "py.build_ui",
                "npm --prefix frontend run build",
                ["npm", "--prefix", FRONTEND, "run", "build"],
            )
        )
    outcomes.append(
        run_command(
            "py.smoke_installed_web",
            "scripts/smoke_installed_web.py",
            ["uv", "run", "python", "scripts/smoke_installed_web.py"],
        )
    )
    return outcomes, parse_junit(junit)


def node_suites(tmp_dir: Path | None = None) -> tuple[list[Outcome], dict[str, Status]]:
    """Run npm ci, audit signatures, api:check, lint, typecheck, Vitest, build, licenses:check."""
    heading("Frontend toolchain and Vitest suites (--node)")
    junit_dir = tmp_dir or Path(tempfile.mkdtemp(prefix="weatherbot-verify05-node-"))
    junit = junit_dir / "vitest.xml"
    commands = (
        ("node_ci", "npm --prefix frontend ci", ["npm", "--prefix", FRONTEND, "ci"]),
        (
            "node_audit_signatures",
            "npm --prefix frontend audit signatures",
            ["npm", "--prefix", FRONTEND, "audit", "signatures"],
        ),
        (
            "node_api_check",
            "npm --prefix frontend run api:check",
            ["npm", "--prefix", FRONTEND, "run", "api:check"],
        ),
        (
            "node_lint",
            "npm --prefix frontend run lint",
            ["npm", "--prefix", FRONTEND, "run", "lint"],
        ),
        (
            "node_typecheck",
            "npm --prefix frontend run typecheck",
            ["npm", "--prefix", FRONTEND, "run", "typecheck"],
        ),
        (
            "node_vitest",
            "npm --prefix frontend run test (with JUnit XML)",
            [
                "npm",
                "--prefix",
                FRONTEND,
                "run",
                "test",
                "--",
                "--reporter=default",
                "--reporter=junit",
                f"--outputFile={junit}",
            ],
        ),
        (
            "node_build",
            "npm --prefix frontend run build",
            ["npm", "--prefix", FRONTEND, "run", "build"],
        ),
        (
            "node_licenses_check",
            "npm --prefix frontend run licenses:check",
            ["npm", "--prefix", FRONTEND, "run", "licenses:check"],
        ),
    )
    outcomes = [run_command(f"node.{key}", label, argv) for key, label, argv in commands]
    return outcomes, parse_junit(junit)


def ui_suite(tmp_dir: Path | None = None) -> tuple[Outcome, dict[str, Status]]:
    """Run Playwright Chromium browser smoke (--ui) with JUnit XML."""
    heading("Playwright Chromium browser smoke (--ui)")
    if not (REPO_ROOT / "src/weatherbot/web/static/index.html").is_file():
        run_command(
            "ui.build",
            "npm --prefix frontend run build",
            ["npm", "--prefix", FRONTEND, "run", "build"],
        )
    junit_dir = tmp_dir or Path(tempfile.mkdtemp(prefix="weatherbot-verify05-ui-"))
    junit = junit_dir / "playwright.xml"
    outcome = run_command(
        "ui.playwright_ui",
        "npm --prefix frontend run e2e (Chromium, list + JUnit)",
        [
            "npm",
            "--prefix",
            FRONTEND,
            "run",
            "e2e",
            "--",
            "--reporter=list,junit",
        ],
        env={"PLAYWRIGHT_JUNIT_OUTPUT_NAME": str(junit)},
    )
    return outcome, parse_junit(junit)


def live_suite(tmp_dir: Path | None = None) -> tuple[Outcome, dict[str, Status]]:
    """Run ``pytest -m live``."""
    heading("Live service smoke tests (--live)")
    junit = (tmp_dir or Path(tempfile.mkdtemp(prefix="weatherbot-verify05-live-"))) / "live.xml"
    outcome = run_command(
        "live.pytest",
        "pytest -m live",
        ["uv", "run", "pytest", "-m", "live", f"--junitxml={junit}"],
    )
    return outcome, parse_junit(junit)


def security_suites() -> list[Outcome]:
    """Run gitleaks, bandit, pip-audit, check_personal_data, npm audit, and frontend ESLint."""
    heading("Security and privacy gates (--security)")
    results: list[Outcome] = []
    if shutil.which("gitleaks"):
        results.append(
            run_command(
                "sec.secrets",
                "redacted history scan",
                ["gitleaks", "git", "--no-banner", "--redact", "--verbose"],
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
    results.append(
        run_command(
            "sec.npm_audit",
            "npm --prefix frontend audit --audit-level=high",
            ["npm", "--prefix", FRONTEND, "audit", "--audit-level=high"],
        )
    )
    results.append(
        run_command(
            "sec.frontend_lint",
            "npm --prefix frontend run lint (--max-warnings 0)",
            ["npm", "--prefix", FRONTEND, "run", "lint"],
        )
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
    """``main`` requires both ``gate`` and ``phase-verify`` strictly."""
    checks = object_of(object_of(github_api("branches/main/protection"))["required_status_checks"])
    contexts = {str(item) for item in array_of(checks.get("contexts", []))}
    print(f"  branch protection contexts={sorted(contexts)}, strict={checks.get('strict')}")
    return {"gate", "phase-verify"} <= contexts and checks.get("strict") is True


def phase_entries_green(entries: Sequence[str]) -> bool:
    """On ``main``: the latest phase-verify run at HEAD; on a branch: its PR's checks."""
    names = {f"phase-verify ({entry})" for entry in entries}
    if git("branch", "--show-current") == "main":
        run = latest_run("phase-verify.yml")
        jobs = object_of(github_api(f"actions/runs/{run['id']}/jobs"))
        conclusions = {
            str(object_of(j)["name"]): object_of(j)["conclusion"] for j in array_of(jobs["jobs"])
        }
        print(
            f"  phase-verify run {run['id']} at {str(run['head_sha'])[:7]}: "
            + ", ".join(f"{name}={conclusions.get(name)}" for name in sorted(names))
        )
        return (
            run["conclusion"] == "success"
            and run["head_sha"] == git("rev-parse", "HEAD")
            and all(conclusions.get(name) == "success" for name in names)
        )
    result = capture(["gh", "pr", "checks", "--json", "name,bucket"])
    result.check_returncode()
    rows = [object_of(row) for row in array_of(json.loads(result.stdout))]
    by_name = {str(row["name"]): str(row["bucket"]) for row in rows}
    return bool(rows) and all(by_name.get(name) == "pass" for name in names)


def phase_four_post() -> bool:
    """Phase 4's own ``--post`` exits 0 with all 80 checks passing; only its totals print."""
    started = time.monotonic()
    result = capture(["uv", "run", "python", "scripts/verify_phase04.py", "--post"], timeout=10800)
    elapsed = time.monotonic() - started
    totals = dict(
        re.findall(r"^  (passed|failed|skipped|total)\s+(\d+)$", result.stdout, re.MULTILINE)
    )
    print(
        f"  verify_phase04.py --post: {totals or 'no summary'} in {elapsed:.1f}s; "
        f"exit {result.returncode}"
    )
    return result.returncode == 0 and totals == {
        "passed": "80",
        "failed": "0",
        "skipped": "0",
        "total": "80",
    }


def descends_from(head: str, ancestor: str) -> bool:
    """Whether the working tree's revision chain leads from ``head`` back to ``ancestor``."""
    parents: dict[str, str | None] = {}
    for relative in sorted(tracked(VERSIONS)):
        if relative.endswith(".py") and not relative.endswith("__init__.py"):
            tree = syntax(relative)
            parents[cast("str", ast.literal_eval(assigned(tree, "revision")))] = cast(
                "str | None", ast.literal_eval(assigned(tree, "down_revision"))
            )
    revision: str | None = head
    while revision is not None:
        if revision == ancestor:
            return True
        revision = parents.get(revision)
    return False


def _installed_tool_doctor() -> tuple[int, dict[str, object]]:
    """Run the installed standalone tool's ``weatherbot doctor --offline --json``."""
    from weatherbot.services import tasks as tasks_service  # noqa: PLC0415

    queried = tasks_service.query()
    by_name = {t.name: t for t in queried}
    local_exe = (
        Path.home()
        / ".local"
        / "bin"
        / ("weatherbot.exe" if sys.platform == "win32" else "weatherbot")
    )
    if local_exe.is_file():
        argv: list[str] = [str(local_exe), "doctor", "--offline", "--json"]
    elif "serve" in by_name and by_name["serve"].command:
        python_exe = Path(by_name["serve"].command).with_name("python.exe")
        argv = [str(python_exe), "-m", "weatherbot", "doctor", "--offline", "--json"]
    else:
        raise RuntimeError
    with tempfile.TemporaryDirectory(prefix="weatherbot-installed-doc05-") as tmp:
        result = subprocess.run(  # noqa: S603 - fixed tool path, no shell  # nosec B603
            argv,
            cwd=Path(tmp),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=60,
        )
    return result.returncode, object_of(json.loads(result.stdout)["data"])


def _fetch_operator_health() -> dict[str, object]:
    """Read ``http://127.0.0.1:8765/api/health`` without environment proxies."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(
        "http://127.0.0.1:8765/api/health",
        headers={"Accept": "application/json"},
    )
    with opener.open(req, timeout=10) as response:
        raw = response.read().decode("utf-8")
    return object_of(json.loads(raw))


def operator_health_and_doctor_web() -> bool:
    """V1.5: operator /api/health answers at DB head and installed doctor passes web."""
    health = _fetch_operator_health()
    version = str(health.get("version", ""))
    db = object_of(health.get("database", {}))
    scheduler = object_of(health.get("scheduler", {}))
    _, doc_data = _installed_tool_doctor()
    checks = {
        str(object_of(c)["name"]): str(object_of(c)["status"])
        for c in array_of(doc_data.get("checks", []))
    }
    print(
        f"  /api/health: version={version}, revision={db.get('revision')}, "
        f"head={db.get('head')}, current={db.get('current')}, stale={scheduler.get('stale')}; "
        f"doctor web={checks.get('web')}, migrations={checks.get('migrations')}"
    )
    return (
        bool(version)
        and db.get("current") is True
        and descends_from(str(db.get("head", "")), "0006")
        and scheduler.get("stale") is False
        and checks.get("web") == "pass"
        and checks.get("migrations") == "pass"
    )


def operator_ui_build_matches() -> bool:
    """V7.4: operator /api/health reports ui.present and the checkout build's index_sha256."""
    index_path = REPO_ROOT / "src/weatherbot/web/static/index.html"
    if not index_path.is_file():
        return False
    checkout_sha = hashlib.sha256(index_path.read_bytes()).hexdigest()[:12]
    health = _fetch_operator_health()
    ui = object_of(health.get("ui", {}))
    print(
        f"  /api/health ui: present={ui.get('present')}, "
        f"index_sha256={ui.get('index_sha256')}, checkout_sha256={checkout_sha}"
    )
    return ui.get("present") is True and ui.get("index_sha256") == checkout_sha


def measure_idle_probe() -> bool:
    """V7.3: scripts/measure_idle.py reports both shares < 0.5% of one core over 600 s."""
    result = capture(
        ["uv", "run", "python", "scripts/measure_idle.py"],
        timeout=1200,
    )
    lines = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip().startswith("idle measurement:")
    ]
    summary_line = lines[-1] if lines else "no idle measurement output"
    print(f"  {summary_line} (exit {result.returncode})")
    return result.returncode == 0 and bool(lines) and "budget=<0.5%" in summary_line


def fast_budget_probe() -> bool:
    """V8.1: scripts/verify_phase05.py --fast passes all 53 checks in under 30 seconds."""
    started = time.monotonic()
    result = capture(["uv", "run", "python", "scripts/verify_phase05.py", "--fast"], timeout=60)
    elapsed = time.monotonic() - started
    totals = dict(
        re.findall(r"^  (passed|failed|skipped|total)\s+(\d+)$", result.stdout, re.MULTILINE)
    )
    print(f"  verify_phase05.py --fast: {totals or 'no summary'} in {elapsed:.2f}s")
    return (
        result.returncode == 0
        and elapsed < FAST_BUDGET_SECONDS
        and totals
        == {
            "passed": "53",
            "failed": "0",
            "skipped": "0",
            "total": "53",
        }
    )


V_MATRIX: tuple[VRow, ...] = (
    # V1 — The web server inside serve (5 rows)
    VRow(
        "V1.1",
        "V1 — The web server inside serve",
        "Static checks 1-11 all PASS",
        ("static_01_11",),
    ),
    VRow(
        "V1.2",
        "V1 — The web server inside serve",
        "The guard, health, built-interface, settings, and doctor-web tests pass (--py)",
        (
            "ruff_check",
            "ruff_format",
            "pyright",
            "pyright_linux",
            "lint_imports",
            "pytest",
            "coverage_policy",
            Select(
                "tests.web.test_web_app",
                "tests.web.test_api_guards",
                "tests.web.test_built_interface",
                "tests.web.test_web_settings",
                "tests.web.test_api_errors",
                "tests.services.test_doctor_web",
                "tests.test_architecture",
            ),
        ),
    ),
    VRow(
        "V1.3",
        "V1 — The web server inside serve",
        "serve hosts the server on port 0, closes its socket on every path, and monitors on",
        (Select("tests.web.test_web_server", "tests.cli.test_serve_web"),),
    ),
    VRow(
        "V1.4",
        "V1 — The web server inside serve",
        "verify_phase04.py --post reports all 80 checks PASS (and Phases 3, 2, and 1)",
        ("verify_phase04_post",),
    ),
    VRow(
        "V1.5",
        "V1 — The web server inside serve",
        "On the operator's machine, /api/health answers at DB head and installed doctor passes web",
        ("operator_health_and_doctor_web",),
    ),
    # V2 — The read API and the map's geometry (4 rows)
    VRow(
        "V2.1",
        "V2 — The read API and the map's geometry",
        "Static checks 12-18 all PASS",
        ("static_12_18",),
    ),
    VRow(
        "V2.2",
        "V2 — The read API and the map's geometry",
        "The read-route, CLI-parity, and privacy tests pass",
        (
            Select(
                "tests.web.test_api_reads",
                "tests.web.test_api_cli_parity",
                "tests.web.test_api_privacy",
            ),
        ),
    ),
    VRow(
        "V2.3",
        "V2 — The read API and the map's geometry",
        "The map-layer and replay-route tests pass",
        (Select("tests.web.test_map_layers", "tests.web.test_replay_routes"),),
    ),
    VRow(
        "V2.4",
        "V2 — The read API and the map's geometry",
        "export_openapi.py --check passes",
        ("export_openapi_check", Select("tests.web.test_openapi_export")),
    ),
    # V3 — The event stream, browser notifications, and the actions (4 rows)
    VRow(
        "V3.1",
        "V3 — The event stream, browser notifications, and the actions",
        "Static checks 19-25 all PASS",
        ("static_19_25",),
    ),
    VRow(
        "V3.2",
        "V3 — The event stream, browser notifications, and the actions",
        "The hub, watcher, staleness-timer, and stream tests pass",
        (
            Select(
                "tests.services.test_event_hub",
                "tests.services.test_cycle_watcher",
                "tests.services.test_staleness_timer",
                "tests.web.test_event_stream",
            ),
        ),
    ),
    VRow(
        "V3.3",
        "V3 — The event stream, browser notifications, and the actions",
        "The browser-channel and action tests pass, the cross-site refusals included",
        (Select("tests.services.test_browser_channel", "tests.web.test_api_actions"),),
    ),
    VRow(
        "V3.4",
        "V3 — The event stream, browser notifications, and the actions",
        "The live check-now test passes (the live run)",
        ("pytest_live", Select("tests.live.test_web_live")),
    ),
    # V4 — The frontend chassis, its gate, and the wheel (4 rows)
    VRow(
        "V4.1",
        "V4 — The frontend chassis, its gate, and the wheel",
        "Static checks 26-35 all PASS",
        ("static_26_35",),
    ),
    VRow(
        "V4.2",
        "V4 — The frontend chassis, its gate, and the wheel",
        "The --node run exits 0: npm ci, audit signatures, api:check, lint, typecheck, build",
        (
            "node_ci",
            "node_audit_signatures",
            "node_api_check",
            "node_lint",
            "node_typecheck",
            "node_vitest",
            "node_build",
            "node_licenses_check",
            Select(
                "src/app/AppShell.test.tsx",
                "src/app/ThemeMenu.test.tsx",
                "src/api/keys.test.tsx",
                "src/api/client.test.tsx",
            ),
        ),
    ),
    VRow(
        "V4.3",
        "V4 — The frontend chassis, its gate, and the wheel",
        "npm audit --audit-level=high passes (--security)",
        ("npm_audit", "frontend_lint"),
    ),
    VRow(
        "V4.4",
        "V4 — The frontend chassis, its gate, and the wheel",
        "The wheel holds the interface and smoke_installed_web.py passes",
        ("smoke_installed_web",),
    ),
    # V5 — The dashboard and the pages (4 rows)
    VRow(
        "V5.1",
        "V5 — The dashboard and the pages",
        "Static checks 36-39 all PASS",
        ("static_36_39",),
    ),
    VRow(
        "V5.2",
        "V5 — The dashboard and the pages",
        "Every page's Vitest file passes, empty states included",
        (
            "export_api_fixtures_check",
            Select("tests.web.test_api_fixtures"),
            Select(
                "src/pages/Dashboard.test.tsx",
                "src/pages/Storms.test.tsx",
                "src/pages/Alerts.test.tsx",
                "src/pages/Timeline.test.tsx",
                "src/pages/Settings.test.tsx",
                "src/notifications/notify.test.ts",
            ),
        ),
    ),
    VRow(
        "V5.3",
        "V5 — The dashboard and the pages",
        "The event-subscription tests pass (exact keys on event; all 9 on reconnect hello)",
        (Select("src/events/useEventStream.test.tsx"),),
    ),
    VRow(
        "V5.4",
        "V5 — The dashboard and the pages",
        "The screenshots spec passes (desktop and phone-width in both themes)",
        ("playwright_ui", Select("screens.spec.ts")),
    ),
    # V6 — The map (3 rows)
    VRow(
        "V6.1",
        "V6 — The map",
        "Static checks 40-43 all PASS",
        ("static_40_43",),
    ),
    VRow(
        "V6.2",
        "V6 — The map",
        "The map's Vitest files pass (live and replay layers and markers)",
        (Select("src/map/layers.test.ts", "src/map/MapView.test.tsx"),),
    ),
    VRow(
        "V6.3",
        "V6 — The map",
        "The map spec passes with no policy violation",
        ("playwright_ui", Select("map.spec.ts")),
    ),
    # V7 — The browser smoke, idle cost, and the operator's dashboard (4 rows)
    VRow(
        "V7.1",
        "V7 — The browser smoke, idle cost, and the operator's dashboard",
        "Static checks 44-47 all PASS",
        ("static_44_47",),
    ),
    VRow(
        "V7.2",
        "V7 — The browser smoke, idle cost, and the operator's dashboard",
        "The dashboard spec passes: level-5 change without reload, and no coordinate in console",
        (
            "playwright_ui",
            Select("dashboard.spec.ts"),
            Select("tests.scripts.test_serve_demo", "tests.scripts.test_measure_idle"),
        ),
    ),
    VRow(
        "V7.3",
        "V7 — The browser smoke, idle cost, and the operator's dashboard",
        "scripts/measure_idle.py reports both shares under 0.5 percent of one core",
        ("measure_idle_probe",),
    ),
    VRow(
        "V7.4",
        "V7 — The browser smoke, idle cost, and the operator's dashboard",
        "The operator's /api/health reports ui.present and the checkout build's index_sha256",
        ("operator_ui_build_matches",),
    ),
    # V8 — CI integration + security (4 rows)
    VRow(
        "V8.1",
        "V8 — CI integration + security",
        "verify_phase05.py --fast exits 0 on Ubuntu CI and in < 30 s locally",
        (
            "verify_phase05_fast_budget",
            "phase_verify_ci",
            Select("tests.test_phase05_verification"),
        ),
    ),
    VRow(
        "V8.2",
        "V8 — CI integration + security",
        "phase-verify.yml's matrix includes '01' to '05' under required branch protection",
        ("static_52", "protection_requires_both"),
    ),
    VRow(
        "V8.3",
        "V8 — CI integration + security",
        "All 53 static checks in verify_phase05.py pass",
        ("static_01_53",),
    ),
    VRow(
        "V8.4",
        "V8 — CI integration + security",
        "verify_phase05.py --security exits 0 over both stacks",
        (
            "gitleaks",
            "bandit",
            "audit_deps",
            "personal_data_all",
            "personal_data_self_test",
            "npm_audit",
            "frontend_lint",
        ),
    ),
)


def evaluate_evidence(item: Evidence, suite: Suite) -> tuple[Status, str]:
    """Judge one piece of evidence in ``suite``; skipped or missing evidence never passes."""
    if isinstance(item, str):
        status = suite.commands.get(item)
        if status is None:
            return "FAIL", f"missing command {item}"
        return status, "" if status == "PASS" else f"{item} {status}"
    matched: dict[str, Status] = {}
    for prefix in item.prefixes:
        prefix_matches: dict[str, Status] = {
            name: outcome
            for name, outcome in suite.tests.items()
            if name == prefix or name.startswith(prefix + ".")
        }
        if not prefix_matches:
            return "FAIL", f"no tests matched {prefix}"
        matched.update(prefix_matches)
    failed = [name for name, outcome in matched.items() if outcome == "FAIL"]
    if failed:
        return "FAIL", f"{len(failed)} failed in {','.join(item.prefixes)}"
    skipped = [name for name, outcome in matched.items() if outcome == "SKIP"]
    if skipped:
        return "SKIP", f"{len(skipped)} skipped in {','.join(item.prefixes)}"
    return "PASS", f"{len(matched)} tests"


def post_matrix(suite: Suite) -> list[Outcome]:
    """Evaluate all 32 rows of the V1-V8 post-implementation verification matrix."""
    outcomes: list[Outcome] = []
    current_section = ""
    for row in V_MATRIX:
        if row.section != current_section:
            current_section = row.section
            heading(current_section)
        row_status: Status = "PASS"
        details: list[str] = []
        for item in row.evidence:
            st, det = evaluate_evidence(item, suite)
            if st == "FAIL":
                row_status = "FAIL"
            elif st == "SKIP" and row_status == "PASS":
                row_status = "SKIP"
            if det:
                details.append(det)
        outcomes.append(
            report(Outcome(row.item_id, row.description, row_status, "; ".join(details)))
        )
    return outcomes


def _record_static_slices(statics: Sequence[Outcome], suite: Suite) -> None:
    """Populate static-check range keys in ``suite.commands`` from ``statics``."""
    ranges = (
        ("static_01_11", 1, 11),
        ("static_12_18", 12, 18),
        ("static_19_25", 19, 25),
        ("static_26_35", 26, 35),
        ("static_36_39", 36, 39),
        ("static_40_43", 40, 43),
        ("static_44_47", 44, 47),
        ("static_52", 52, 52),
        ("static_01_53", 1, 53),
    )
    for key, start, end in ranges:
        slice_outcomes = statics[start - 1 : end]
        suite.commands[key] = (
            "PASS"
            if len(slice_outcomes) == (end - start + 1)
            and all(item.status == "PASS" for item in slice_outcomes)
            else "FAIL"
        )


def run_probe(name: str, label: str, fn: Callable[[], bool], suite: Suite) -> None:
    """Run one post-verification probe and record its status in ``suite.commands``."""
    print(f"\n--- Probe: {label} ---", flush=True)
    try:
        ok = fn()
    except Exception as error:  # noqa: BLE001 - probe failure recorded as FAIL
        print(f"  probe error: {type(error).__name__}", flush=True)
        ok = False
    suite.commands[name] = "PASS" if ok else "FAIL"


def run_post() -> list[Outcome]:
    """Run static checks, all suites, probes, and evaluate the 32-row V1-V8 matrix."""
    print(
        "Notice: --post starts the offline demonstration server (scripts/serve_demo.py) and "
        "headless Chromium for the Playwright smoke and the 600 s idle CPU measurement, "
        "runs verify_phase04.py --post (which shows Windows toasts and registers/deletes "
        "\\Weatherbot\\_verify_probe), and reads the operator's running service only through "
        "GET /api/health and doctor --offline --json.",
        flush=True,
    )
    static_outcomes = run_static_checks()
    suite = Suite()
    _record_static_slices(static_outcomes, suite)

    with tempfile.TemporaryDirectory(prefix="weatherbot-post05-") as tmp:
        tmp_path = Path(tmp)
        node_outcomes, node_tests = node_suites(tmp_path)
        for out in node_outcomes:
            suite.commands[out.item_id.removeprefix("node.")] = out.status
        suite.tests.update(node_tests)

        py_outcomes, py_tests = py_suites(tmp_path)
        for out in py_outcomes:
            suite.commands[out.item_id.removeprefix("py.")] = out.status
        suite.tests.update(py_tests)

        ui_out, ui_tests = ui_suite(tmp_path)
        suite.commands["playwright_ui"] = ui_out.status
        suite.tests.update(ui_tests)

        live_out, live_tests = live_suite(tmp_path)
        suite.commands["pytest_live"] = live_out.status
        suite.tests.update(live_tests)

    sec_outcomes = security_suites()
    sec_map = {
        "sec.secrets": "gitleaks",
        "sec.sast": "bandit",
        "sec.audit": "audit_deps",
        "sec.all": "personal_data_all",
        "sec.self-test": "personal_data_self_test",
        "sec.npm_audit": "npm_audit",
        "sec.frontend_lint": "frontend_lint",
    }
    for out in sec_outcomes:
        if out.item_id in sec_map:
            suite.commands[sec_map[out.item_id]] = out.status

    heading("Post-implementation probes")
    run_probe(
        "phase_verify_ci",
        "phase-verify (01) through (05) CI checks",
        lambda: phase_entries_green(("01", "02", "03", "04", "05")),
        suite,
    )
    run_probe(
        "protection_requires_both",
        "main branch protection requires gate and phase-verify",
        protection_requires_both,
        suite,
    )
    run_probe("verify_phase04_post", "verify_phase04.py --post (80 checks)", phase_four_post, suite)
    run_probe(
        "operator_health_and_doctor_web",
        "operator /api/health at DB head and installed doctor web check",
        operator_health_and_doctor_web,
        suite,
    )
    run_probe(
        "operator_ui_build_matches",
        "operator /api/health ui.present and index_sha256 match checkout build",
        operator_ui_build_matches,
        suite,
    )
    run_probe(
        "measure_idle_probe",
        "scripts/measure_idle.py (600 s idle CPU < 0.5% on server and tab)",
        measure_idle_probe,
        suite,
    )
    run_probe(
        "verify_phase05_fast_budget",
        "scripts/verify_phase05.py --fast (< 30 s)",
        fast_budget_probe,
        suite,
    )

    return [*static_outcomes, *post_matrix(suite)]


def summarize(outcomes: Sequence[Outcome]) -> int:
    """Print the final pass/fail/skip summary and return the process exit code."""
    passed = sum(1 for item in outcomes if item.status == "PASS")
    failed = sum(1 for item in outcomes if item.status == "FAIL")
    skipped = sum(1 for item in outcomes if item.status == "SKIP")
    heading("Summary")
    print(f"  passed   {passed}")
    print(f"  failed   {failed}")
    print(f"  skipped  {skipped}")
    print(f"  total    {len(outcomes)}", flush=True)
    return 0 if failed == 0 and skipped == 0 else 1


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments, enforcing mutually exclusive mode selection."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--fast", action="store_true", help="Run the 53 static checks only.")
    group.add_argument(
        "--py", action="store_true", help="Run static checks and Python quality/test/smoke suites."
    )
    group.add_argument(
        "--node", action="store_true", help="Run static checks and frontend/Vitest suites."
    )
    group.add_argument(
        "--ui", action="store_true", help="Run static checks and Playwright browser smoke."
    )
    group.add_argument(
        "--live", action="store_true", help="Run static checks and live smoke tests."
    )
    group.add_argument(
        "--security", action="store_true", help="Run static checks and security/privacy gates."
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Run --py, --node, --ui, --live, and --security.",
    )
    group.add_argument(
        "--post", action="store_true", help="Run the full 85-check Phase 5 verification."
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for Phase 5 verification."""
    args = parse_args(argv)
    if args.post:
        return summarize(run_post())
    default_mode = not any(
        (
            args.fast,
            args.py,
            args.node,
            args.ui,
            args.live,
            args.security,
            args.all,
            args.post,
        )
    )
    outcomes = run_static_checks()
    if args.py or args.all or default_mode:
        py_outcomes, _ = py_suites()
        outcomes.extend(py_outcomes)
    if args.node or args.all:
        node_outcomes, _ = node_suites()
        outcomes.extend(node_outcomes)
    if args.ui or args.all:
        ui_outcome, _ = ui_suite()
        outcomes.append(ui_outcome)
    if args.live or args.all:
        live_outcome, _ = live_suite()
        outcomes.append(live_outcome)
    if args.security or args.all:
        outcomes.extend(security_suites())
    return summarize(outcomes)


if __name__ == "__main__":
    raise SystemExit(main())
