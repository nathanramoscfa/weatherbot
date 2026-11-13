# scripts/verify_phase07.py
"""Verify Phase 7 (Depth) against docs/roadmap/phase07-roadmap.md.

Modes (mutually exclusive; no flag runs ``--fast`` and ``--py``):
  --fast      65 static file, AST, OpenAPI, fixture, and workflow checks (< 30 s, no network).
  --py        Ruff, Pyright (host + Linux), import-linter, offline pytest with >=90%
              branch coverage on engine, policy, AI context, and AI validate, schema/OpenAPI/
              fixture checks, and wheel smoke.
  --node      Frontend npm ci, audit signatures, api:check, lint, typecheck, Vitest,
              build, and licenses:check.
  --ui        Playwright Chromium browser smoke (all e2e specs including Phase 7).
  --live      Live source, monitor, OSM tile, and ntfy pytest suite (``pytest -m live``).
  --security  Secret, SAST, dependency, personal-data, npm audit, ESLint, and secret-shape scans.
  --all       --py + --node + --ui + --live + --security (all except --post).
  --post      Full V1-V10 post-implementation matrix (42 rows, 107 checks total).
"""

import argparse
import ast
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
PHASE_6_TAG: Final = "v2.0.0-phase-6"
PHASE_7_TAG: Final = "v2.0.0-phase-7"
CI_WORKFLOW: Final = ".github/workflows/ci.yml"
PHASE_WORKFLOW: Final = ".github/workflows/phase-verify.yml"
PRE_COMMIT_CONFIG: Final = ".pre-commit-config.yaml"
ROADMAP: Final = "docs/roadmap/ROADMAP.md"
PHASE_ROADMAP: Final = "docs/roadmap/phase07-roadmap.md"
QA_FINDINGS: Final = "docs/phase07-qa-findings.md"
OPENAPI_SPEC: Final = "docs/api/openapi.json"
SERVICES: Final = "src/weatherbot/services"
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
EXPECTED_STATIC_CHECKS: Final = 65
EXPECTED_POST_ROWS: Final = 42
EXPECTED_V_DISTRIBUTION: Final = (3, 5, 5, 4, 4, 4, 4, 4, 5, 4)
EXPECTED_PHASE_06_POST_TOTAL: Final = "79"
EXPECTED_EDITABLE_COUNT: Final = 12
EXPECTED_MIGRATION_COLUMNS: Final = 4
EXPECTED_MIGRATION_INDEXES: Final = 4
EXPECTED_PHASE_MATRIX_PREFIX: Final = ("01", "02", "03", "04", "05", "06", "07")
MIN_OPERATOR_LOCATIONS: Final = 2

PHASE_7_SECRET_SCAN_PREFIXES: Final = (
    "src/weatherbot",
    "frontend/src",
    "frontend/e2e",
    "tests/fixtures/ai",
    "tests/fixtures/recorded",
    "docs/AI.md",
    "docs/NOTIFICATIONS.md",
    "docs/phase07-qa-findings.md",
)
ANTHROPIC_KEY_PREFIX: Final = "sk" + "-" + "ant" + "-"
NTFY_TOKEN_SHAPE: Final = re.compile(r"\btk_[a-z0-9]{20,}\b")
STYLE_ATTR_RE: Final = re.compile(r"\bstyle=(?:\{|\"|')")

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
    """One row of the Phase 7 V1-V10 post-implementation verification matrix."""

    item_id: str
    section: str
    description: str
    evidence: tuple[Evidence, ...]


@dataclass
class Suite:
    """Collected command and test outcomes for evaluating the V1-V10 matrix."""

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


def json_file(relative: str, root: Path = REPO_ROOT) -> dict[str, object]:
    """Load a JSON object from a repository-relative path."""
    return object_of(json.loads(read(relative, root=root)))


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


def files_exist(*relatives: str, root: Path = REPO_ROOT) -> bool:
    """Whether every repository-relative path exists as a regular file and is tracked."""
    tracked_set = tracked(root=root)
    return all((root / rel).is_file() and rel in tracked_set for rel in relatives)


def contains(relative: str, *needles: str, root: Path = REPO_ROOT) -> bool:
    """Whether a file contains every needle."""
    text = read(relative, root=root)
    return all(needle in text for needle in needles)


@cache
def tagged(relative: str, root: Path = REPO_ROOT, *, tag: str = PHASE_6_TAG) -> str:
    """Read a repository-relative file as a milestone git tag recorded it."""
    return git("show", f"{tag}:{relative}", root=root)


@cache
def tagged_tree(prefix: str, root: Path = REPO_ROOT, *, tag: str = PHASE_6_TAG) -> frozenset[str]:
    """Return tracked file paths under ``prefix`` at ``tag``."""
    output = git("ls-tree", "-r", "--name-only", tag, "--", prefix, root=root)
    return frozenset(output.splitlines()) if output else frozenset()


def syntax(relative: str, root: Path = REPO_ROOT) -> ast.Module:
    """Parse a repository-relative Python file into an AST."""
    return ast.parse(read(relative, root=root), filename=relative)


def class_node(tree: ast.Module, name: str) -> ast.ClassDef:
    """Find a top-level class definition by name."""
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise LookupError(name)


def class_fields(relative: str, class_name: str, root: Path = REPO_ROOT) -> list[str]:
    """Return annotated field names defined directly on ``class_name`` in ``relative``."""
    cls = class_node(syntax(relative, root=root), class_name)
    return [
        item.target.id
        for item in cls.body
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
    ]


def class_methods(relative: str, class_name: str, root: Path = REPO_ROOT) -> set[str]:
    """Return method names defined directly on ``class_name`` in ``relative``."""
    cls = class_node(syntax(relative, root=root), class_name)
    return {
        item.name for item in cls.body if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
    }


def assigned(tree: ast.AST, name: str) -> ast.expr:
    """Return the value expression assigned to ``name`` in ``tree``."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
            and node.value is not None
        ) or (isinstance(node, ast.TypeAlias) and node.name.id == name):
            return cast("ast.expr", node.value)
    raise LookupError(name)


def imported_modules(tree: ast.AST) -> set[str]:
    """Return imported module names in ``tree``."""
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def markdown_section(text: str, heading_line: str) -> str:
    """Extract the body under a Markdown heading until the next peer or parent heading."""
    lines = text.splitlines()
    level = len(heading_line) - len(heading_line.lstrip("#"))
    prefix = "#" * level + " "
    collecting = False
    collected: list[str] = []
    for line in lines:
        if line.strip() == heading_line:
            collecting = True
            continue
        if collecting and line.startswith((prefix, "## ")):
            break
        if collecting:
            collected.append(line)
    return "\n".join(collected)


def _no_secret_shape_in_phase07_paths() -> bool:
    """Return True when no Anthropic key or ntfy token shape appears in Phase 7 tracked files."""
    text_exts = (".py", ".ts", ".tsx", ".json", ".md", ".xml", ".toml", ".yml", ".yaml", ".txt")
    for prefix in PHASE_7_SECRET_SCAN_PREFIXES:
        for rel in sorted(tracked(prefix)):
            if not rel.endswith(text_exts):
                continue
            path = REPO_ROOT / rel
            if not path.is_file():
                continue
            text = read(rel)
            if ANTHROPIC_KEY_PREFIX in text or NTFY_TOKEN_SHAPE.search(text):
                return False
    return True


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


# ---------------------------------------------------------------------------
# 65 Static Checks (Steps 1 through 10)
# ---------------------------------------------------------------------------


def check_01_pyproject_pytest_xdist_in_dev_only() -> bool:
    """Check 1: pyproject.toml places pytest-xdist in dev only and keeps addopts serial."""
    data = tomllib.loads(read("pyproject.toml"))
    runtime = [str(x) for x in array_of(object_of(data["project"])["dependencies"])]
    groups = object_of(data["dependency-groups"])
    dev = [str(x) for x in array_of(groups["dev"])]
    planning = [str(x) for x in array_of(groups["planning"])]
    pytest_cfg = object_of(object_of(object_of(data["tool"])["pytest"])["ini_options"])
    addopts = str(pytest_cfg.get("addopts", ""))
    return (
        any(item.startswith("pytest-xdist>=") for item in dev)
        and not any("pytest-xdist" in item or "execnet" in item for item in [*runtime, *planning])
        and " -n " not in f" {addopts} "
        and "numprocesses" not in addopts
    )


def check_02_ci_yml_runs_pytest_xdist_with_coverage_floors() -> bool:
    """Check 2: ci.yml runs pytest -n auto with all four 90% branch-coverage floors."""
    return contains(
        CI_WORKFLOW,
        "-n auto",
        "--cov=weatherbot.engine",
        "--cov=weatherbot.services.policy",
        "--cov=weatherbot.services.ai.context",
        "--cov=weatherbot.services.ai.validate",
        "--cov-branch",
        "--cov-fail-under=90",
    )


def check_03_verify_phase06_check_44_reads_tagged_readme() -> bool:
    """Check 3: scripts/verify_phase06.py Check 44 reads tagged('README.md', tag=PHASE_6_TAG)."""
    return contains(
        "scripts/verify_phase06.py",
        'PHASE_6_TAG: Final = "v2.0.0-phase-6"',
        'tagged("README.md", tag=PHASE_6_TAG)',
    )


def check_04_test_ci_budget_tracked() -> bool:
    """Check 4: tests/test_ci_budget.py is tracked."""
    return files_exist("tests/test_ci_budget.py")


def check_05_nws_coverage_county_zone_optional_and_cwa_pattern() -> bool:
    """Check 5: NwsCoverage county_zone is str | None = None and cwa pattern allows alphanumeric."""
    return "county_zone" in class_fields(
        "src/weatherbot/models/location.py", "NwsCoverage"
    ) and contains(
        "src/weatherbot/models/location.py",
        "county_zone: str | None = Field(default=None",
        'cwa: str = Field(pattern=r"^[A-Z0-9]{3}$"',
    )


def check_06_nws_source_optional_county_and_alert_guard() -> bool:
    """Check 6: sources/nws.py defines OPTIONAL_POINT_FIELDS={'county'} and guards county_zone."""
    return contains(
        "src/weatherbot/sources/nws.py",
        'OPTIONAL_POINT_FIELDS: Final = frozenset({"county"})',
        "county_zone is not None",
    )


def check_07_location_row_constraint_and_no_batch_alter_after_0008() -> bool:
    """Check 7: LocationRow keeps nws_coverage_whole and post-0008 migrations avoid batch_alter."""
    if not contains("src/weatherbot/services/persistence/tables.py", 'name="nws_coverage_whole"'):
        return False
    post_0008 = [
        rel
        for rel in sorted(tracked(VERSIONS))
        if Path(rel).name[:4].isdigit() and int(Path(rel).name[:4]) > int("0008")
    ]
    if not post_0008:
        return False
    for rel in post_0008:
        tree = syntax(rel)
        if any(
            isinstance(node, ast.Attribute) and node.attr == "batch_alter_table"
            for node in ast.walk(tree)
        ):
            return False
    return True


def check_08_http_redacts_q_query_parameter() -> bool:
    """Check 8: sources/http.py redacts query parameter q in COORDINATE_PARAMETERS and regex."""
    tree = syntax("src/weatherbot/sources/http.py")
    params = {
        elt.value
        for elt in ast.walk(assigned(tree, "COORDINATE_PARAMETERS"))
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
    }
    return "q" in params and contains(
        "src/weatherbot/sources/http.py",
        "(point|lat|lon|latitude|longitude|q)=",
    )


def check_09_nominatim_search_and_data_sources_doc() -> bool:
    """Check 9: nominatim.py defines search/parse_search and DATA_SOURCES.md documents it."""
    tree = syntax("src/weatherbot/sources/nominatim.py")
    async_names = {n.name for n in tree.body if isinstance(n, ast.AsyncFunctionDef)}
    sync_names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    return (
        "search" in async_names
        and "parse_search" in sync_names
        and contains("src/weatherbot/sources/nominatim.py", "SEARCH_FIELDS_READ")
        and contains(
            "docs/DATA_SOURCES.md",
            "https://nominatim.openstreetmap.org/search?q={q}&format=jsonv2&addressdetails=1&limit=5",
        )
    )


def check_10_location_search_and_remove_routes_and_openapi() -> bool:
    """Check 10: actions.py and openapi.json declare POST /api/locations/search and /remove."""
    paths = object_of(json_file(OPENAPI_SPEC)["paths"])
    return (
        contains(
            "src/weatherbot/web/routes/actions.py",
            '"/api/locations/search"',
            '"/api/locations/remove"',
        )
        and "post" in object_of(paths.get("/api/locations/search", {}))
        and "post" in object_of(paths.get("/api/locations/remove", {}))
    )


def check_11_cli_locations_add_place_and_pick_options() -> bool:
    """Check 11: cli/locations.py add defines --place and --pick with allow_from_autoenv=False."""
    return contains(
        "src/weatherbot/cli/locations.py",
        '"--place"',
        '"--pick"',
        '"--lat"',
        '"--lon"',
        "allow_from_autoenv=False",
    )


def check_12_frontend_location_manager_tracked() -> bool:
    """Check 12: frontend/src/settings/LocationManager.tsx and test are tracked."""
    return files_exist(
        "frontend/src/settings/LocationManager.tsx",
        "frontend/src/settings/LocationManager.test.tsx",
    )


def check_13_step_2_tests_and_fixtures_tracked() -> bool:
    """Check 13: Step 2 unit, web, CLI, e2e tests and Nominatim search fixtures are tracked."""
    return files_exist(
        "tests/sources/test_nws_no_county.py",
        "tests/sources/test_nominatim_search.py",
        "tests/services/test_location_no_county.py",
        "tests/services/test_location_search.py",
        "tests/services/test_location_remove.py",
        "tests/web/test_location_writes.py",
        "tests/cli/test_locations_place.py",
        "tests/cli/test_location_nassau.py",
        "frontend/e2e/locations.spec.ts",
        "tests/fixtures/recorded/geocode-nominatim/2026-11-04/search-miami.json",
        "tests/fixtures/recorded/geocode-nominatim/2026-11-04/search-nassau.json",
        "tests/fixtures/recorded/geocode-nominatim/2026-11-04/search-none.json",
    )


def check_14_ntfy_channel_and_redirect_guard() -> bool:
    """Check 14: services/ntfy.py defines NtfyChannel/ntfy_channel with follow_redirects=False."""
    tree = syntax("src/weatherbot/services/ntfy.py")
    classes = {n.name for n in tree.body if isinstance(n, ast.ClassDef)}
    funcs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    topic_fstrings = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.JoinedStr) and "topic" in ast.unparse(node)
    ]
    return (
        "NtfyChannel" in classes
        and "ntfy_channel" in funcs
        and contains("src/weatherbot/services/ntfy.py", "follow_redirects=False")
        and not topic_fstrings
    )


def check_15_notifications_channels_results_and_kinds() -> bool:
    """Check 15: notifications.py includes ntfy channel, muted result, and recovered kind."""
    return contains(
        "src/weatherbot/services/notifications.py",
        '"ntfy"',
        '"muted"',
        '"recovered"',
    )


def check_16_config_ntfy_settings_and_no_secret_fields() -> bool:
    """Check 16: NotificationSettings has ntfy/ntfy_server and no _Section has topic/token."""
    tree = syntax("src/weatherbot/services/config.py")
    fields = class_fields("src/weatherbot/services/config.py", "NotificationSettings")
    secret_fields = [
        f"{node.name}.{fname}"
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        for fname in class_fields("src/weatherbot/services/config.py", node.name)
        if "topic" in fname.lower() or "token" in fname.lower()
    ]
    return (
        "ntfy" in fields
        and "ntfy_server" in fields
        and not secret_fields
        and contains(
            "src/weatherbot/services/config.py",
            '"WEATHERBOT_NOTIFICATIONS_NTFY"',
            '"WEATHERBOT_NOTIFICATIONS_NTFY_SERVER"',
        )
    )


def check_17_runtime_make_ntfy_and_conftest_env_scrub() -> bool:
    """Check 17: Runtime defines make_ntfy and tests/conftest.py scrubs WEATHERBOT_* variables."""
    return "make_ntfy" in class_fields("src/weatherbot/cli/runtime.py", "Runtime") and contains(
        "tests/conftest.py", 'startswith("WEATHERBOT_")'
    )


def check_18_location_preferences_model() -> bool:
    """Check 18: models/location.py defines LocationPreferences and wires Location.preferences."""
    return class_fields("src/weatherbot/models/location.py", "LocationPreferences") == [
        "toast",
        "browser",
        "phone",
        "phone_min_level",
    ] and "preferences" in class_fields("src/weatherbot/models/location.py", "Location")


def check_19_migration_0009_location_preferences_frozen() -> bool:
    """Check 19: 0009_location_preferences.py uses 4 plain op.add_column calls and is in FROZEN."""
    rel = f"{VERSIONS}/0009_location_preferences.py"
    text = read(rel)
    tree = syntax(rel)
    has_batch = any(
        isinstance(node, ast.Attribute) and node.attr == "batch_alter_table"
        for node in ast.walk(tree)
    )
    return (
        'revision: str = "0009"' in text
        and 'down_revision: str | None = "0008"' in text
        and text.count("op.add_column(") == EXPECTED_MIGRATION_COLUMNS
        and not has_batch
        and contains("tests/services/test_database.py", '"0009_location_preferences.py"')
    )


def check_20_policy_and_goldens_unchanged_from_phase_6() -> bool:
    """Check 20: services/policy.py and tests/golden are unchanged from v2.0.0-phase-6."""
    golden_files = tracked("tests/golden")
    return (
        read("src/weatherbot/services/policy.py").strip()
        == tagged("src/weatherbot/services/policy.py", tag=PHASE_6_TAG)
        and golden_files == tagged_tree("tests/golden", tag=PHASE_6_TAG)
        and all(read(rel).strip() == tagged(rel, tag=PHASE_6_TAG) for rel in sorted(golden_files))
    )


def check_21_doctor_ntfy_check() -> bool:
    """Check 21: services/doctor.py defines ntfy_check and registers Check('ntfy', ...)."""
    tree = syntax("src/weatherbot/services/doctor.py")
    funcs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    return "ntfy_check" in funcs and contains("src/weatherbot/services/doctor.py", 'Check("ntfy"')


def check_22_logs_redact_ntfy_topic_and_token() -> bool:
    """Check 22: services/logs.py redacts _NTFY_TOKEN_SHAPE and WEATHERBOT_NTFY_TOPIC/TOKEN."""
    return contains(
        "src/weatherbot/services/logs.py",
        "_NTFY_TOKEN_SHAPE",
        "_SECRET_ENV_VARS",
        '"WEATHERBOT_NTFY_TOPIC"',
        '"WEATHERBOT_NTFY_TOKEN"',
    )


def check_23_notifications_doc_and_step_3_tests_tracked() -> bool:
    """Check 23: docs/NOTIFICATIONS.md sections and all Step 3 test/UI files are tracked."""
    return contains(
        "docs/NOTIFICATIONS.md",
        "## What leaves the machine",
        "## Runbook",
    ) and files_exist(
        "tests/services/test_ntfy.py",
        "tests/services/test_location_preferences.py",
        "tests/services/test_quiet_hours_phone.py",
        "tests/services/test_recovered_phone.py",
        "tests/services/test_doctor_ntfy.py",
        "tests/web/test_notification_channels.py",
        "tests/cli/test_notify_phone.py",
        "tests/live/test_ntfy_live.py",
        "frontend/src/settings/NotificationChannels.tsx",
        "frontend/src/settings/NotificationChannels.test.tsx",
    )


def check_24_tomlkit_dependency_and_import_confinement() -> bool:
    """Check 24: pyproject.toml lists tomlkit and only services/settings_file.py imports it."""
    data = tomllib.loads(read("pyproject.toml"))
    runtime = [str(x) for x in array_of(object_of(data["project"])["dependencies"])]
    importers = [
        rel
        for rel in sorted(tracked("src/weatherbot"))
        if rel.endswith(".py")
        and any(m == "tomlkit" or m.startswith("tomlkit.") for m in imported_modules(syntax(rel)))
    ]
    return any(d.startswith("tomlkit>=") for d in runtime) and importers == [
        "src/weatherbot/services/settings_file.py"
    ]


def check_25_settings_file_editable_allowlist() -> bool:
    """Check 25: services/settings_file.py EDITABLE has 12 allowlisted keys and no forbidden."""
    tree = syntax("src/weatherbot/services/settings_file.py")
    editable = assigned(tree, "EDITABLE")
    if not isinstance(editable, ast.Dict):
        return False
    pairs = [
        (k.elts[0].value, k.elts[1].value)
        for k in editable.keys
        if isinstance(k, ast.Tuple)
        and len(k.elts) == 2  # noqa: PLR2004 - (table, key) pair tuple
        and isinstance(k.elts[0], ast.Constant)
        and isinstance(k.elts[1], ast.Constant)
        and isinstance(k.elts[0].value, str)
        and isinstance(k.elts[1].value, str)
    ]
    forbidden_tables = {"web", "engine", "http", "logging", "monitor"}
    return len(pairs) == EXPECTED_EDITABLE_COUNT and not any(
        table in forbidden_tables or (table, key) == ("notifications", "ntfy_server")
        for table, key in pairs
    )


def check_26_put_api_settings_route_and_openapi() -> bool:
    """Check 26: routes/settings.py and openapi.json declare PUT /api/settings."""
    paths = object_of(json_file(OPENAPI_SPEC)["paths"])
    return contains(
        "src/weatherbot/web/routes/settings.py",
        '@router.put("/api/settings"',
    ) and "put" in object_of(paths.get("/api/settings", {}))


def check_27_retention_settings_and_env_override() -> bool:
    """Check 27: RetentionSettings(history_days=0) and WEATHERBOT_RETENTION_HISTORY_DAYS exist."""
    return "history_days" in class_fields(
        "src/weatherbot/services/config.py", "RetentionSettings"
    ) and contains(
        "src/weatherbot/services/config.py",
        '"WEATHERBOT_RETENTION_HISTORY_DAYS"',
    )


def check_28_retention_service_plan_run_backup_and_guards() -> bool:
    """Check 28: RetentionService defines plan/run with writing_session and backup_database."""
    rel = "src/weatherbot/services/retention.py"
    methods = class_methods(rel, "RetentionService")
    return (
        {"plan", "run"} <= methods
        and contains(rel, "writing_session", "backup_database")
        and "ai_engine" not in read(rel)
    )


def check_29_cli_prune_command_and_schema() -> bool:
    """Check 29: weatherbot prune CLI command, PruneDocument, and prune.schema.json are wired."""
    return (
        contains("src/weatherbot/cli/__init__.py", 'app.command("prune")(prune.prune)')
        and contains("src/weatherbot/cli/documents.py", '"prune": PruneDocument')
        and files_exist("docs/schema/prune.schema.json")
    )


def check_30_retention_web_routes_and_openapi() -> bool:
    """Check 30: routes/settings.py and openapi.json declare /api/retention and /run."""
    paths = object_of(json_file(OPENAPI_SPEC)["paths"])
    return (
        contains(
            "src/weatherbot/web/routes/settings.py", '"/api/retention"', '"/api/retention/run"'
        )
        and "get" in object_of(paths.get("/api/retention", {}))
        and "post" in object_of(paths.get("/api/retention/run", {}))
    )


def check_31_serve_runs_retention_worker_and_preserves_ai() -> bool:
    """Check 31: cli/serve.py runs RetentionWorker and preserves Phase 6 AI wiring."""
    return contains(
        "src/weatherbot/cli/serve.py",
        "RetentionWorker",
        "ChangeSummarizer",
        "ChangeSummaryService",
        "context.ai_service",
        "ai.close",
    )


def check_32_step_4_tests_and_migration_0010_frozen() -> bool:
    """Check 32: Step 4 test/UI files are tracked and 0010_retention_indexes.py has 4 indexes."""
    rel_0010 = f"{VERSIONS}/0010_retention_indexes.py"
    text_0010 = read(rel_0010)
    tree_0010 = syntax(rel_0010)
    forbidden = any(
        isinstance(node, ast.Attribute) and node.attr in {"create_table", "batch_alter_table"}
        for node in ast.walk(tree_0010)
    )
    return (
        files_exist(
            "tests/services/test_settings_file.py",
            "tests/services/test_live_settings.py",
            "tests/services/test_retention.py",
            "tests/services/test_retention_keeplist.py",
            "tests/services/test_retention_worker.py",
            "tests/services/test_foreign_key_indexes.py",
            "tests/web/test_settings_writes.py",
            "tests/web/test_retention_routes.py",
            "tests/cli/test_prune_command.py",
            "tests/cli/test_storage_growth.py",
            "frontend/src/settings/QuietHoursForm.tsx",
            "frontend/src/settings/QuietHoursForm.test.tsx",
            "frontend/src/settings/RetentionPanel.tsx",
            "frontend/src/settings/RetentionPanel.test.tsx",
        )
        and 'revision: str = "0010"' in text_0010
        and 'down_revision: str | None = "0009"' in text_0010
        and text_0010.count("op.create_index(") == EXPECTED_MIGRATION_INDEXES
        and not forbidden
        and contains("tests/services/test_database.py", '"0010_retention_indexes.py"')
    )


def check_33_map_depth_and_available_layers_schemas() -> bool:
    """Check 33: web/schemas.py defines MapDepthResponse, StormMapDepthResponse, and layers."""
    rel = "src/weatherbot/web/schemas.py"
    return (
        "available_layers" in class_fields(rel, "MapResponse")
        and {"wind_radii", "past_track", "past_points"}
        <= set(class_fields(rel, "StormMapDepthResponse"))
        and {"storms", "peak_surge"} <= set(class_fields(rel, "MapDepthResponse"))
    )


def check_34_map_depth_wind_prob_and_advisories_openapi() -> bool:
    """Check 34: openapi.json declares /api/map/depth, /wind-probabilities, and /advisories."""
    paths = object_of(json_file(OPENAPI_SPEC)["paths"])
    return all(
        "get" in object_of(paths.get(route, {}))
        for route in ("/api/map/depth", "/api/map/wind-probabilities", "/api/map/advisories")
    )


def check_35_csp_suffix_allows_nowcoast_and_osm_images() -> bool:
    """Check 35: web/guards.py CSP_SUFFIX allows nowcoast.noaa.gov in img-src."""
    current = read("src/weatherbot/web/guards.py")
    phase6 = tagged("src/weatherbot/web/guards.py", tag=PHASE_6_TAG)
    expected_img = "img-src 'self' data: https://tile.openstreetmap.org https://nowcoast.noaa.gov"
    directives = (
        "default-src 'self'",
        "base-uri 'none'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "form-action 'self'",
        "connect-src 'self'",
        "font-src 'self'",
    )
    return expected_img in current and all((d in current) == (d in phase6) for d in directives)


def check_36_frontend_map_layers_twelve_keys_and_defaults() -> bool:
    """Check 36: frontend/src/map/layers.ts declares 12 layers with 6 depth layers off."""
    return contains(
        "frontend/src/map/layers.ts",
        "cone: true",
        "track: true",
        "points: true",
        "watches_warnings: true",
        "outlook: true",
        "locations: true",
        "wind_radii: false",
        "past_track: false",
        "peak_surge: false",
        "wind_probabilities: false",
        "radar: false",
        "satellite: false",
    )


def check_37_wms_confinement_and_no_map_intervals() -> bool:
    """Check 37: tileLayer.wms is confined to useLeafletMap.ts and map/ has no setInterval."""
    wms_files = [
        rel
        for rel in sorted(tracked("frontend/src"))
        if rel.endswith((".ts", ".tsx")) and "tileLayer.wms" in read(rel)
    ]
    interval_files = [
        rel
        for rel in sorted(tracked("frontend/src/map"))
        if rel.endswith((".ts", ".tsx"))
        and not rel.endswith(".test.tsx")
        and "setInterval" in read(rel)
    ]
    return wms_files == ["frontend/src/map/useLeafletMap.ts"] and not interval_files


def check_38_advisory_slider_tracked() -> bool:
    """Check 38: frontend/src/map/AdvisorySlider.tsx and test are tracked."""
    return files_exist(
        "frontend/src/map/AdvisorySlider.tsx",
        "frontend/src/map/AdvisorySlider.test.tsx",
    )


def check_39_data_sources_overlays_and_osm_live_test() -> bool:
    """Check 39: DATA_SOURCES.md records nowCOAST and StormSurgeRisk, and OSM live test exists."""
    return contains(
        "docs/DATA_SOURCES.md",
        "overlay-radar",
        "overlay-satellite",
        "NOAA nowCOAST",
        "StormSurgeRisk",
    ) and files_exist("tests/live/test_osm_referer_live.py")


def check_40_step_5_tests_and_synthetic_surge_tracked() -> bool:
    """Check 40: layers.spec.ts, map depth/history/wind-prob tests, and synthetic_surge exist."""
    return files_exist(
        "frontend/e2e/layers.spec.ts",
        "tests/web/test_map_depth.py",
        "tests/web/test_wind_probability_route.py",
        "tests/web/test_map_history.py",
        "scripts/synthetic_surge.py",
    )


def check_41_charts_route_and_timeline_before_openapi() -> bool:
    """Check 41: openapi.json declares GET /api/charts and GET /api/timeline?before=."""
    paths = object_of(json_file(OPENAPI_SPEC)["paths"])
    timeline_get = object_of(object_of(paths.get("/api/timeline", {})).get("get", {}))
    params = [object_of(item).get("name") for item in array_of(timeline_get.get("parameters", []))]
    return "get" in object_of(paths.get("/api/charts", {})) and "before" in params


def check_42_frontend_charts_files_tracked() -> bool:
    """Check 42: All 10 frontend/src/charts/ source and test files are tracked."""
    return files_exist(
        "frontend/src/charts/scale.ts",
        "frontend/src/charts/scale.test.ts",
        "frontend/src/charts/LevelSparkline.tsx",
        "frontend/src/charts/LevelSparkline.test.tsx",
        "frontend/src/charts/ArrivalTimeline.tsx",
        "frontend/src/charts/ArrivalTimeline.test.tsx",
        "frontend/src/charts/LevelHistoryChart.tsx",
        "frontend/src/charts/LevelHistoryChart.test.tsx",
        "frontend/src/charts/WindProbabilityChart.tsx",
        "frontend/src/charts/WindProbabilityChart.test.tsx",
    )


def check_43_frontend_package_json_unchanged_from_phase_6() -> bool:
    """Check 43: frontend/package.json dependencies and devDependencies match v2.0.0-phase-6."""
    cur = json_file("frontend/package.json")
    base = object_of(json.loads(tagged("frontend/package.json", tag=PHASE_6_TAG)))
    return set(object_of(cur["dependencies"]).keys()) == set(
        object_of(base["dependencies"]).keys()
    ) and set(object_of(cur["devDependencies"]).keys()) == set(
        object_of(base["devDependencies"]).keys()
    )


def check_44_no_jsx_inline_style_attributes() -> bool:
    """Check 44: No tracked file under frontend/src/ uses a JSX style= attribute."""
    return not any(
        STYLE_ATTR_RE.search(read(rel))
        for rel in sorted(tracked("frontend/src"))
        if rel.endswith((".ts", ".tsx"))
    )


def check_45_query_keys_charts_and_events_query_keys_unchanged() -> bool:
    """Check 45: queryKeys.charts uses 'timeline' prefix and QUERY_KEYS matches v2.0.0-phase-6."""
    cur_keys = ast.literal_eval(assigned(syntax("src/weatherbot/services/events.py"), "QUERY_KEYS"))
    base_keys = ast.literal_eval(
        assigned(
            ast.parse(tagged("src/weatherbot/services/events.py", tag=PHASE_6_TAG)),
            "QUERY_KEYS",
        )
    )
    return (
        contains(
            "frontend/src/api/keys.ts",
            'invalidatableQueryKey("timeline", "charts", location)',
        )
        and cur_keys == base_keys
    )


def check_46_replay_timeline_and_assessment_routes_and_order() -> bool:
    """Check 46: routes/replay.py declares /timeline before /{advisory} and /assessment."""
    text = read("src/weatherbot/web/routes/replay.py")
    idx_timeline = text.find('"/api/replay/{atcf_id}/timeline"')
    idx_advisory = text.find('"/api/replay/{atcf_id}/{advisory}"')
    idx_assess = text.find('"/api/replay/{atcf_id}/{advisory}/assessment"')
    paths = object_of(json_file(OPENAPI_SPEC)["paths"])
    return (
        idx_timeline != -1
        and idx_advisory != -1
        and idx_assess != -1
        and idx_timeline < idx_advisory
        and "get" in object_of(paths.get("/api/replay/{atcf_id}/timeline", {}))
        and "get" in object_of(paths.get("/api/replay/{atcf_id}/{advisory}/assessment", {}))
    )


def check_47_replay_timelines_service_and_route_layering() -> bool:
    """Check 47: services/replay.py defines ReplayTimelines and routes/replay.py has no engine."""
    svc_tree = syntax("src/weatherbot/services/replay.py")
    classes = {n.name for n in svc_tree.body if isinstance(n, ast.ClassDef)}
    funcs = {n.name for n in svc_tree.body if isinstance(n, ast.FunctionDef)}
    cli_imports = imported_modules(syntax("src/weatherbot/cli/replay.py"))
    route_imports = imported_modules(syntax("src/weatherbot/web/routes/replay.py"))
    return (
        "ReplayTimelines" in classes
        and "replay_notes" in funcs
        and "weatherbot.services.replay" in cli_imports
        and not any(
            m == "weatherbot.engine" or m.startswith("weatherbot.engine.") for m in route_imports
        )
    )


def check_48_replay_nav_item_and_route() -> bool:
    """Check 48: AppShell.tsx lists /replay after /map and routes.tsx wires <Replay />."""
    nav_tos = re.findall(r'\{\s*to:\s*"([^"]+)"', read("frontend/src/app/AppShell.tsx"))
    return nav_tos == [
        "/",
        "/map",
        "/replay",
        "/storms",
        "/alerts",
        "/timeline",
        "/ask",
        "/settings",
    ] and contains("frontend/src/app/routes.tsx", 'path: "replay"', "<Replay />")


def check_49_shared_assessment_components_in_dashboard_and_replay() -> bool:
    """Check 49: frontend/src/assessment/ components are shared by Dashboard.tsx and Replay.tsx."""
    components = ("LevelSummary", "ThreatTable", "OfficialProductList", "EvidenceList")
    return (
        files_exist(
            "frontend/src/assessment/LevelSummary.tsx",
            "frontend/src/assessment/ThreatTable.tsx",
            "frontend/src/assessment/OfficialProductList.tsx",
            "frontend/src/assessment/EvidenceList.tsx",
            "frontend/src/assessment/assessment.test.tsx",
        )
        and contains("frontend/src/pages/Dashboard.tsx", *components)
        and contains("frontend/src/pages/Replay.tsx", *components)
    )


def check_50_changes_no_cone_sentence_and_replay_e2e() -> bool:
    """Check 50: engine/changes.py has full no-cone sentence (#44) and replay.spec.ts exists."""
    text = read("src/weatherbot/engine/changes.py")
    return (
        '", whose cone does not cover the location"' in text
        and 'does not"' not in text
        and files_exist("frontend/e2e/replay.spec.ts")
    )


def check_51_report_service_uses_briefing_context_and_bans_raw_fields() -> bool:
    """Check 51: services/report.py uses briefing_context and accesses no banned raw attribute."""
    tree = syntax("src/weatherbot/services/report.py")
    classes = {n.name for n in tree.body if isinstance(n, ast.ClassDef)}
    funcs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    called = {
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    banned_attrs = {"display_name", "distance_km", "issuer", "detail"}
    found_banned = {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr in banned_attrs
    }
    return (
        "ReportService" in classes
        and "render_report" in funcs
        and "briefing_context" in called
        and not found_banned
    )


def check_52_report_service_escapes_and_has_no_external_tags() -> bool:
    """Check 52: services/report.py calls html.escape and has no <script, <link, <img, or src=."""
    text = read("src/weatherbot/services/report.py")
    return "html.escape(" in text and not any(
        tok in text for tok in ("<script", "<link", "<img", "src=")
    )


def check_53_report_web_route_cli_command_and_openapi() -> bool:
    """Check 53: sync GET /api/report, weatherbot report CLI command, and OpenAPI path are wired."""
    tree = syntax("src/weatherbot/web/routes/report.py")
    sync_funcs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    async_funcs = {n.name for n in tree.body if isinstance(n, ast.AsyncFunctionDef)}
    paths = object_of(json_file(OPENAPI_SPEC)["paths"])
    return (
        "get_report" in sync_funcs
        and "get_report" not in async_funcs
        and contains("src/weatherbot/cli/__init__.py", 'app.command("report")(report.report)')
        and "get" in object_of(paths.get("/api/report", {}))
    )


def check_54_step_8_report_tests_tracked() -> bool:
    """Check 54: Step 8 report unit, web, CLI, and Playwright tests are tracked."""
    return files_exist(
        "tests/services/test_report_render.py",
        "tests/services/test_report_escape.py",
        "tests/services/test_report_privacy.py",
        "tests/web/test_api_report.py",
        "tests/cli/test_report_command.py",
        "frontend/e2e/report.spec.ts",
    )


def check_55_readme_commands_list_prune_report_and_place() -> bool:
    """Check 55: README.md ## Commands documents weatherbot prune, report, and --place."""
    commands = markdown_section(read("README.md"), "## Commands")
    return all(tok in commands for tok in ("weatherbot prune", "weatherbot report", "--place"))


def check_56_phase7_e2e_spec_and_nowcoast_guard() -> bool:
    """Check 56: frontend/e2e/phase7.spec.ts is tracked and guard.ts routes https://nowcoast.noaa.gov."""
    return files_exist("frontend/e2e/phase7.spec.ts") and contains(
        "frontend/e2e/guard.ts", "https://nowcoast.noaa.gov"
    )


def check_57_measure_idle_and_serve_demo_retention() -> bool:
    """Check 57: measure_idle.py and serve_demo.py wire --retention-days and 0.5% idle budget."""
    return contains(
        "scripts/measure_idle.py",
        "budget=<",
        "ai_state=",
        "change_summaries=on",
        "IDLE_BUDGET_PCT: Final = 0.5",
        "--retention-days",
    ) and contains("scripts/serve_demo.py", '"--retention-days"')


def check_58_phase7_alarms_test_tracked() -> bool:
    """Check 58: tests/services/test_phase7_alarms.py is tracked."""
    return files_exist("tests/services/test_phase7_alarms.py")


def check_59_readme_status_names_phase_07_complete() -> bool:
    """Check 59: README.md ## Status names Phase 7 complete and CHANGELOG.md documents Phase 7."""
    status = markdown_section(read("README.md"), "## Status")
    return (
        "Phase 7 (depth) are complete" in status
        and "Phase 8 (Release 2.0) is" in status
        and contains("CHANGELOG.md", "### Phase 7 — Depth")
    )


def check_60_verify_phase07_self_check() -> bool:
    """Check 60: verify_phase07.py self-check (65 static checks, 42 V1-V10 rows, 8 mode flags)."""
    rel = "scripts/verify_phase07.py"
    if not files_exist(rel):
        return False
    tree = syntax(rel)
    text = read(rel)
    v_dist = tuple(
        sum(1 for row in V_MATRIX if row.item_id.startswith(f"V{g}.")) for g in range(1, 11)
    )
    return (
        bool(tree.body)
        and len(STATIC_CHECKS) == EXPECTED_STATIC_CHECKS
        and len(V_MATRIX) == EXPECTED_POST_ROWS
        and v_dist == EXPECTED_V_DISTRIBUTION
        and all(f'"{mode}"' in text for mode in MODES)
    )


def check_61_test_phase07_verification_tracked() -> bool:
    """Check 61: tests/test_phase07_verification.py defines fast, workflow, and red-check tests."""
    rel = "tests/test_phase07_verification.py"
    if not files_exist(rel):
        return False
    tree = syntax(rel)
    funcs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    return {
        "test_fast_verification_passes_all_static_checks_within_thirty_seconds",
        "test_phase_verify_workflow_includes_phase_07",
        "test_a_changed_deliverable_turns_exactly_its_check_red",
    } <= funcs


def check_62_phase07_qa_findings_ledger() -> bool:
    """Check 62: docs/phase07-qa-findings.md records all PRs/steps, idle CPU, and pre-ship items."""
    return files_exist(QA_FINDINGS) and contains(
        QA_FINDINGS,
        "## PR #89 — Phase 7 Roadmap",
        "## Step 1",
        "## Step 2",
        "## Step 3",
        "## Step 4",
        "## Step 5",
        "## Step 6",
        "## Step 7",
        "## Step 8",
        "## Step 9",
        "## Step 10",
        "## 600-second idle CPU measurement",
        "window=600.1s server_cpu=0.3567%",
        "## Live smoke runs",
        "## Source-drift observations",
        "## Exact vs. growth-proof Phase 7 checks for Phase 8",
        "## Pre-ship items",
    )


def check_63_phase07_roadmap_and_project_roadmap() -> bool:
    """Check 63: docs/roadmap/phase07-roadmap.md (Steps 1-10) and ROADMAP.md Phase 7 exist."""
    p7 = read(PHASE_ROADMAP)
    return all(f"## Step {n} —" in p7 for n in range(1, 11)) and contains(
        ROADMAP, "### Phase 7 — Depth"
    )


def check_64_phase_verify_workflow_includes_07() -> bool:
    """Check 64: phase-verify.yml includes 01..07 and separate Node steps for 05, 06, and 07."""
    text = read(PHASE_WORKFLOW)
    m = re.search(r"phase:\s*\[([^\n\]]+)\]", text)
    if m is None:
        return False
    phases = tuple(
        item.strip().strip('"').strip("'") for item in m.group(1).split(",") if item.strip()
    )
    return phases[:7] == EXPECTED_PHASE_MATRIX_PREFIX and contains(
        PHASE_WORKFLOW,
        "- name: Set up Node\n        if: \"!cancelled() && matrix.phase == '05'\"",
        "- name: Install frontend dependencies\n"
        "        if: \"!cancelled() && matrix.phase == '05'\"",
        "- name: Set up Node (Phase 6)\n        if: \"!cancelled() && matrix.phase == '06'\"",
        "- name: Install frontend dependencies (Phase 6)\n"
        "        if: \"!cancelled() && matrix.phase == '06'\"",
        "- name: Set up Node (Phase 7)\n        if: \"!cancelled() && matrix.phase == '07'\"",
        "- name: Install frontend dependencies (Phase 7)\n"
        "        if: \"!cancelled() && matrix.phase == '07'\"",
    )


def check_65_security_gate_and_no_secret_shapes() -> bool:
    """Check 65: Security hooks/workflow are wired and no secret shape appears in tracked files."""
    return (
        contains(
            PRE_COMMIT_CONFIG,
            "id: gitleaks",
            "id: personal-data",
            "id: bandit",
            "id: pip-audit",
            "id: frontend-lint",
            "id: npm-audit",
        )
        and contains(PHASE_WORKFLOW, "scripts/verify_phase${{ matrix.phase }}.py --security")
        and _no_secret_shape_in_phase07_paths()
    )


STATIC_CHECKS: Final[tuple[Check, ...]] = (
    (
        "pyproject.toml places pytest-xdist in dev only and keeps addopts serial",
        check_01_pyproject_pytest_xdist_in_dev_only,
    ),
    (
        ".github/workflows/ci.yml runs pytest -n auto with 90% branch-coverage floors",
        check_02_ci_yml_runs_pytest_xdist_with_coverage_floors,
    ),
    (
        "scripts/verify_phase06.py Check 44 reads tagged('README.md', tag=PHASE_6_TAG)",
        check_03_verify_phase06_check_44_reads_tagged_readme,
    ),
    (
        "tests/test_ci_budget.py is tracked",
        check_04_test_ci_budget_tracked,
    ),
    (
        "NwsCoverage county_zone is optional and cwa pattern allows alphanumeric codes",
        check_05_nws_coverage_county_zone_optional_and_cwa_pattern,
    ),
    (
        "sources/nws.py declares OPTIONAL_POINT_FIELDS={'county'} and guards county_zone alerts",
        check_06_nws_source_optional_county_and_alert_guard,
    ),
    (
        "LocationRow keeps nws_coverage_whole and migrations after 0008 avoid batch_alter_table",
        check_07_location_row_constraint_and_no_batch_alter_after_0008,
    ),
    (
        "sources/http.py redacts query parameter q in COORDINATE_PARAMETERS and regex",
        check_08_http_redacts_q_query_parameter,
    ),
    (
        "sources/nominatim.py defines search/parse_search and DATA_SOURCES.md documents it",
        check_09_nominatim_search_and_data_sources_doc,
    ),
    (
        "routes/actions.py and openapi.json declare POST /api/locations/search and /remove",
        check_10_location_search_and_remove_routes_and_openapi,
    ),
    (
        "cli/locations.py add defines --place and --pick with allow_from_autoenv=False",
        check_11_cli_locations_add_place_and_pick_options,
    ),
    (
        "frontend/src/settings/LocationManager.tsx and test are tracked",
        check_12_frontend_location_manager_tracked,
    ),
    (
        "Step 2 unit, web, CLI, e2e tests and Nominatim search fixtures are tracked",
        check_13_step_2_tests_and_fixtures_tracked,
    ),
    (
        "services/ntfy.py defines NtfyChannel/ntfy_channel with follow_redirects=False",
        check_14_ntfy_channel_and_redirect_guard,
    ),
    (
        "services/notifications.py includes ntfy channel, muted result, and recovered kind",
        check_15_notifications_channels_results_and_kinds,
    ),
    (
        "NotificationSettings declares ntfy/ntfy_server and no _Section has topic/token fields",
        check_16_config_ntfy_settings_and_no_secret_fields,
    ),
    (
        "Runtime defines make_ntfy and tests/conftest.py scrubs WEATHERBOT_* variables",
        check_17_runtime_make_ntfy_and_conftest_env_scrub,
    ),
    (
        "models/location.py defines LocationPreferences and wires Location.preferences",
        check_18_location_preferences_model,
    ),
    (
        "0009_location_preferences.py uses plain op.add_column and is frozen in FROZEN",
        check_19_migration_0009_location_preferences_frozen,
    ),
    (
        "services/policy.py and tests/golden are unchanged from v2.0.0-phase-6",
        check_20_policy_and_goldens_unchanged_from_phase_6,
    ),
    (
        "services/doctor.py defines ntfy_check and registers Check('ntfy', ...)",
        check_21_doctor_ntfy_check,
    ),
    (
        "services/logs.py redacts _NTFY_TOKEN_SHAPE and WEATHERBOT_NTFY_TOPIC/TOKEN",
        check_22_logs_redact_ntfy_topic_and_token,
    ),
    (
        "docs/NOTIFICATIONS.md sections and all Step 3 test/UI files are tracked",
        check_23_notifications_doc_and_step_3_tests_tracked,
    ),
    (
        "pyproject.toml lists tomlkit and only services/settings_file.py imports it",
        check_24_tomlkit_dependency_and_import_confinement,
    ),
    (
        "services/settings_file.py EDITABLE has 12 allowlisted keys and excludes forbidden tables",
        check_25_settings_file_editable_allowlist,
    ),
    (
        "routes/settings.py and openapi.json declare PUT /api/settings",
        check_26_put_api_settings_route_and_openapi,
    ),
    (
        "RetentionSettings(history_days=0) and WEATHERBOT_RETENTION_HISTORY_DAYS are declared",
        check_27_retention_settings_and_env_override,
    ),
    (
        "RetentionService defines plan/run with writing_session and backup_database",
        check_28_retention_service_plan_run_backup_and_guards,
    ),
    (
        "weatherbot prune CLI command, PruneDocument, and prune.schema.json are wired",
        check_29_cli_prune_command_and_schema,
    ),
    (
        "routes/settings.py and openapi.json declare GET /api/retention and POST /retention/run",
        check_30_retention_web_routes_and_openapi,
    ),
    (
        "cli/serve.py runs RetentionWorker and preserves Phase 6 AI wiring",
        check_31_serve_runs_retention_worker_and_preserves_ai,
    ),
    (
        "Step 4 test/UI files are tracked and 0010_retention_indexes.py is frozen with 4 indexes",
        check_32_step_4_tests_and_migration_0010_frozen,
    ),
    (
        "web/schemas.py defines MapDepthResponse, StormMapDepthResponse, and available_layers",
        check_33_map_depth_and_available_layers_schemas,
    ),
    (
        "openapi.json declares /api/map/depth, /wind-probabilities, and /advisories",
        check_34_map_depth_wind_prob_and_advisories_openapi,
    ),
    (
        "web/guards.py CSP_SUFFIX allows nowcoast.noaa.gov in img-src and preserves directives",
        check_35_csp_suffix_allows_nowcoast_and_osm_images,
    ),
    (
        "frontend/src/map/layers.ts declares 12 layers with the 6 depth layers off by default",
        check_36_frontend_map_layers_twelve_keys_and_defaults,
    ),
    (
        "L.tileLayer.wms is confined to useLeafletMap.ts and frontend/src/map/ has no setInterval",
        check_37_wms_confinement_and_no_map_intervals,
    ),
    (
        "frontend/src/map/AdvisorySlider.tsx and test are tracked",
        check_38_advisory_slider_tracked,
    ),
    (
        "docs/DATA_SOURCES.md records nowCOAST overlays and test_osm_referer_live.py is tracked",
        check_39_data_sources_overlays_and_osm_live_test,
    ),
    (
        "layers.spec.ts, map depth/history/wind tests, and synthetic_surge.py are tracked",
        check_40_step_5_tests_and_synthetic_surge_tracked,
    ),
    (
        "openapi.json declares GET /api/charts and GET /api/timeline?before=",
        check_41_charts_route_and_timeline_before_openapi,
    ),
    (
        "All 10 frontend/src/charts/ source and test files are tracked",
        check_42_frontend_charts_files_tracked,
    ),
    (
        "frontend/package.json dependencies and devDependencies match v2.0.0-phase-6",
        check_43_frontend_package_json_unchanged_from_phase_6,
    ),
    (
        "No tracked file under frontend/src/ uses a JSX style= attribute",
        check_44_no_jsx_inline_style_attributes,
    ),
    (
        "queryKeys.charts uses 'timeline' prefix and events.py QUERY_KEYS matches v2.0.0-phase-6",
        check_45_query_keys_charts_and_events_query_keys_unchanged,
    ),
    (
        "routes/replay.py declares /timeline before /{advisory} and /{advisory}/assessment",
        check_46_replay_timeline_and_assessment_routes_and_order,
    ),
    (
        "services/replay.py defines ReplayTimelines/replay_notes and route imports no engine",
        check_47_replay_timelines_service_and_route_layering,
    ),
    (
        "AppShell.tsx lists /replay after /map and routes.tsx wires path 'replay' to <Replay />",
        check_48_replay_nav_item_and_route,
    ),
    (
        "frontend/src/assessment/ components are tracked and shared by Dashboard and Replay",
        check_49_shared_assessment_components_in_dashboard_and_replay,
    ),
    (
        "engine/changes.py has full no-cone sentence (#44) and replay.spec.ts is tracked",
        check_50_changes_no_cone_sentence_and_replay_e2e,
    ),
    (
        "services/report.py uses briefing_context and accesses no banned raw attribute",
        check_51_report_service_uses_briefing_context_and_bans_raw_fields,
    ),
    (
        "services/report.py calls html.escape and contains no <script, <link, <img, or src=",
        check_52_report_service_escapes_and_has_no_external_tags,
    ),
    (
        "sync GET /api/report, weatherbot report CLI command, and OpenAPI path are wired",
        check_53_report_web_route_cli_command_and_openapi,
    ),
    (
        "Step 8 report unit, web, CLI, and Playwright tests are tracked",
        check_54_step_8_report_tests_tracked,
    ),
    (
        "README.md ## Commands documents weatherbot prune, weatherbot report, and --place",
        check_55_readme_commands_list_prune_report_and_place,
    ),
    (
        "frontend/e2e/phase7.spec.ts is tracked and guard.ts routes https://nowcoast.noaa.gov",
        check_56_phase7_e2e_spec_and_nowcoast_guard,
    ),
    (
        "measure_idle.py and serve_demo.py wire --retention-days and 0.5% idle budget",
        check_57_measure_idle_and_serve_demo_retention,
    ),
    (
        "tests/services/test_phase7_alarms.py is tracked",
        check_58_phase7_alarms_test_tracked,
    ),
    (
        "README.md ## Status names Phase 7 complete and Phase 8 next, and CHANGELOG documents it",
        check_59_readme_status_names_phase_07_complete,
    ),
    (
        "scripts/verify_phase07.py self-check (65 static checks, 42 V1-V10 rows, 8 mode flags)",
        check_60_verify_phase07_self_check,
    ),
    (
        "tests/test_phase07_verification.py defines fast, workflow, and red-check isolation tests",
        check_61_test_phase07_verification_tracked,
    ),
    (
        "docs/phase07-qa-findings.md records all PRs/steps, idle CPU, smoke, and pre-ship items",
        check_62_phase07_qa_findings_ledger,
    ),
    (
        "docs/roadmap/phase07-roadmap.md (Steps 1-10) and ROADMAP.md Phase 7 exist",
        check_63_phase07_roadmap_and_project_roadmap,
    ),
    (
        ".github/workflows/phase-verify.yml includes 01..07 and separate Node steps for 05..07",
        check_64_phase_verify_workflow_includes_07,
    ),
    (
        "Security hooks/workflow are wired and no secret shape appears in tracked files",
        check_65_security_gate_and_no_secret_shapes,
    ),
)


# ---------------------------------------------------------------------------
# Subprocess, JUnit, and Suite Runners
# ---------------------------------------------------------------------------


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


def _user_registry_env_var(name: str) -> str | None:
    r"""Read an env var from HKCU\Environment on Windows when absent from os.environ."""
    if sys.platform != "win32":
        return None
    import winreg  # noqa: PLC0415

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _operator_secret_env() -> dict[str, str]:
    r"""Resolve operator secret vars from HKCU\Environment when absent from os.environ."""
    extra: dict[str, str] = {}
    for var in ("ANTHROPIC_API_KEY", "WEATHERBOT_NTFY_TOPIC", "WEATHERBOT_NTFY_TOKEN"):
        if not os.environ.get(var):
            val = _user_registry_env_var(var)
            if val:
                extra[var] = val
    return extra


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
    """Run Ruff, Pyright (host + Linux), import-linter, offline pytest, exporters, and smoke."""
    heading("Python quality, offline tests, coverage floors, and wheel smoke (--py)")
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
            "export_schemas_check",
            "scripts/export_schemas.py --check",
            ["uv", "run", "python", "scripts/export_schemas.py", "--check"],
        ),
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
    junit_dir = tmp_dir or Path(tempfile.mkdtemp(prefix="weatherbot-verify07-py-"))
    junit = junit_dir / "pytest.xml"
    coverage_file = junit_dir / "coverage.sqlite"
    cov_env = {"COVERAGE_FILE": str(coverage_file)}
    outcomes.append(
        run_command(
            "py.pytest",
            "pytest -n auto (offline, engine + policy + context + validate branch coverage >= 90%)",
            [
                "uv",
                "run",
                "pytest",
                "-n",
                "auto",
                f"--junitxml={junit}",
                "--cov=weatherbot.engine",
                "--cov=weatherbot.services.policy",
                "--cov=weatherbot.services.ai.context",
                "--cov=weatherbot.services.ai.validate",
                "--cov-branch",
                "--cov-fail-under=90",
            ],
            env=cov_env,
        )
    )
    for key, label, include in (
        (
            "coverage_policy",
            "coverage report on weatherbot.services.policy (>= 90% branch)",
            "*/services/policy.py",
        ),
        (
            "coverage_ai_context",
            "coverage report on weatherbot.services.ai.context (>= 90% branch)",
            "*/services/ai/context.py",
        ),
        (
            "coverage_ai_validate",
            "coverage report on weatherbot.services.ai.validate (>= 90% branch)",
            "*/services/ai/validate.py",
        ),
    ):
        outcomes.append(
            run_command(
                f"py.{key}",
                label,
                [
                    "uv",
                    "run",
                    "coverage",
                    "report",
                    f"--include={include}",
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
    junit_dir = tmp_dir or Path(tempfile.mkdtemp(prefix="weatherbot-verify07-node-"))
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
    """Run Playwright Chromium browser smoke (--ui, all Phase 7 specs included) with JUnit XML."""
    heading("Playwright Chromium browser smoke (--ui)")
    if not (REPO_ROOT / "src/weatherbot/web/static/index.html").is_file():
        run_command(
            "ui.build",
            "npm --prefix frontend run build",
            ["npm", "--prefix", FRONTEND, "run", "build"],
        )
    junit_dir = tmp_dir or Path(tempfile.mkdtemp(prefix="weatherbot-verify07-ui-"))
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
    """Run ``pytest -m live`` (landmarks, OSM tile Referer, and ntfy when configured)."""
    heading("Live service smoke tests (--live)")
    junit = (tmp_dir or Path(tempfile.mkdtemp(prefix="weatherbot-verify07-live-"))) / "live.xml"
    outcome = run_command(
        "live.pytest",
        "pytest -m live",
        ["uv", "run", "pytest", "-m", "live", f"--junitxml={junit}"],
        env=_operator_secret_env(),
    )
    return outcome, parse_junit(junit)


def security_suites() -> list[Outcome]:
    """Run gitleaks, bandit, pip-audit, check_personal_data, npm audit, ESLint, and secret scan."""
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
    secret_clean = _no_secret_shape_in_phase07_paths()
    results.append(
        report(
            Outcome(
                "sec.secret_shape_scan",
                "no Anthropic key or ntfy token shape under Phase 7 paths",
                "PASS" if secret_clean else "FAIL",
                "" if secret_clean else "secret shape found",
            )
        )
    )
    return results


# ---------------------------------------------------------------------------
# Post-Implementation Probes
# ---------------------------------------------------------------------------


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
    """Check phase-verify entries on main at HEAD or on the current branch's PR."""
    names = {f"phase-verify ({entry})" for entry in entries}
    if git("branch", "--show-current") != "main":
        result = capture(["gh", "pr", "checks", "--json", "name,bucket"])
        if result.returncode == 0 and result.stdout.strip():
            rows = [object_of(row) for row in array_of(json.loads(result.stdout))]
            by_name = {str(row["name"]): str(row["bucket"]) for row in rows}
            if rows:
                return all(by_name.get(name) == "pass" for name in names)
        prior_names = {f"phase-verify ({entry})" for entry in entries[:-1]}
        run = latest_run("phase-verify.yml")
        jobs = object_of(github_api(f"actions/runs/{run['id']}/jobs"))
        conclusions = {
            str(object_of(j)["name"]): object_of(j)["conclusion"] for j in array_of(jobs["jobs"])
        }
        print(
            f"  phase-verify main run {run['id']} (pre-PR branch fallback): "
            + ", ".join(f"{name}={conclusions.get(name)}" for name in sorted(prior_names))
        )
        return run["conclusion"] == "success" and all(
            conclusions.get(name) == "success" for name in prior_names
        )

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


def phase_six_post() -> bool:
    """Phase 6's own ``--post`` exits 0 with all 79 checks passing; only its totals print."""
    started = time.monotonic()
    result = capture(
        ["uv", "run", "python", "scripts/verify_phase06.py", "--post"],
        timeout=14400,
        env=_operator_secret_env(),
    )
    elapsed = time.monotonic() - started
    totals = dict(
        re.findall(r"^  (passed|failed|skipped|total)\s+(\d+)$", result.stdout, re.MULTILINE)
    )
    for line in result.stdout.splitlines():
        if line.startswith(("[FAIL]", "[SKIP]")) or "verify_phase0" in line:
            print(f"    {line}")
    print(
        f"  verify_phase06.py --post: {totals or 'no summary'} in {elapsed:.1f}s; "
        f"exit {result.returncode}"
    )
    return result.returncode == 0 and totals == {
        "passed": EXPECTED_PHASE_06_POST_TOTAL,
        "failed": "0",
        "skipped": "0",
        "total": EXPECTED_PHASE_06_POST_TOTAL,
    }


def _installed_tool_doctor(*, offline: bool = False) -> tuple[int, dict[str, object]]:
    """Run the installed standalone tool's ``weatherbot doctor [--offline] --json``."""
    from weatherbot.services import tasks as tasks_service  # noqa: PLC0415

    queried = tasks_service.query()
    by_name = {t.name: t for t in queried}
    local_exe = (
        Path.home()
        / ".local"
        / "bin"
        / ("weatherbot.exe" if sys.platform == "win32" else "weatherbot")
    )
    flags = ["doctor", *(["--offline"] if offline else []), "--json"]
    if local_exe.is_file():
        argv: list[str] = [str(local_exe), *flags]
    elif "serve" in by_name and by_name["serve"].command:
        python_exe = Path(by_name["serve"].command).with_name("python.exe")
        argv = [str(python_exe), "-m", "weatherbot", *flags]
    else:
        raise RuntimeError
    env = {**os.environ, **_operator_secret_env()}
    with tempfile.TemporaryDirectory(prefix="weatherbot-installed-doc07-") as tmp:
        result = subprocess.run(  # noqa: S603 - fixed tool path, no shell  # nosec B603
            argv,
            cwd=Path(tmp),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=120,
            env=env,
        )
    return result.returncode, object_of(json.loads(result.stdout)["data"])


def _fetch_operator_json(path: str) -> dict[str, object]:
    """Read ``http://127.0.0.1:8765{path}`` without environment proxies."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(
        f"http://127.0.0.1:8765{path}",
        headers={"Accept": "application/json"},
    )
    with opener.open(req, timeout=10) as response:
        raw = response.read().decode("utf-8")
    return object_of(json.loads(raw))


def operator_locations_at_head() -> bool:
    """V2.5: the operator's service holds watched locations at DB head."""
    health = _fetch_operator_json("/api/health")
    db = object_of(health.get("database", {}))
    locations_payload = _fetch_operator_json("/api/locations")
    loc_count = len(array_of(locations_payload.get("locations", [])))
    print(
        f"  /api/locations: count={loc_count}, db.revision={db.get('revision')}, "
        f"db.head={db.get('head')}, db.current={db.get('current')}"
    )
    return (
        db.get("current") is True
        and descends_from(str(db.get("head", "")), "0010")
        and loc_count >= MIN_OPERATOR_LOCATIONS
    )


def operator_doctor_and_ntfy_delivered() -> bool:
    """V3.5: operator doctor passes ntfy and /api/notifications/channels shows delivered."""
    channels_payload = _fetch_operator_json("/api/notifications/channels")
    channels = {
        str(object_of(ch)["name"]): object_of(ch)
        for ch in array_of(channels_payload.get("channels", []))
    }
    ntfy_ch = channels.get("ntfy", {})
    _, doc_data = _installed_tool_doctor(offline=True)
    checks = {
        str(object_of(c)["name"]): str(object_of(c)["status"])
        for c in array_of(doc_data.get("checks", []))
    }
    print(
        f"  /api/notifications/channels ntfy: state={ntfy_ch.get('state')}, "
        f"last_result={ntfy_ch.get('last_result')}; doctor ntfy={checks.get('ntfy')}"
    )
    return (
        ntfy_ch.get("state") == "on"
        and ntfy_ch.get("last_result") == "delivered"
        and checks.get("ntfy") == "pass"
    )


def operator_health_head_and_corpus() -> bool:
    """V9.5: the operator's /api/health reads head, built UI, and corpus=true."""
    health = _fetch_operator_json("/api/health")
    db = object_of(health.get("database", {}))
    ui = object_of(health.get("ui", {}))
    ai = object_of(health.get("ai", {}))
    print(
        f"  /api/health: revision={db.get('revision')}, head={db.get('head')}, "
        f"current={db.get('current')}, corpus={health.get('corpus')}, "
        f"ui.present={ui.get('present')}, ui.index_sha256={ui.get('index_sha256')}, "
        f"ai.state={ai.get('state')}"
    )
    return (
        db.get("current") is True
        and descends_from(str(db.get("head", "")), "0010")
        and health.get("corpus") is True
        and ui.get("present") is True
        and ai.get("state") == "ready"
    )


def measure_idle_probe() -> bool:
    """V9.3: scripts/measure_idle.py reports both shares < 0.5% with retention and AI ready."""
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
    return (
        result.returncode == 0
        and bool(lines)
        and "budget=<0.5%" in summary_line
        and "ai_state=ready" in summary_line
        and "change_summaries=on" in summary_line
    )


def fast_budget_probe() -> bool:
    """V10.1: scripts/verify_phase07.py --fast passes all 65 checks in under 30 seconds."""
    started = time.monotonic()
    result = capture(["uv", "run", "python", "scripts/verify_phase07.py", "--fast"], timeout=60)
    elapsed = time.monotonic() - started
    totals = dict(
        re.findall(r"^  (passed|failed|skipped|total)\s+(\d+)$", result.stdout, re.MULTILINE)
    )
    print(f"  verify_phase07.py --fast: {totals or 'no summary'} in {elapsed:.2f}s")
    return (
        result.returncode == 0
        and elapsed < FAST_BUDGET_SECONDS
        and totals
        == {
            "passed": str(EXPECTED_STATIC_CHECKS),
            "failed": "0",
            "skipped": "0",
            "total": str(EXPECTED_STATIC_CHECKS),
        }
    )


# ---------------------------------------------------------------------------
# 42 V1-V10 Post-Implementation Verification Matrix Rows
# ---------------------------------------------------------------------------


V_MATRIX: tuple[VRow, ...] = (
    # V1 — The test budget (3 rows)
    VRow(
        "V1.1",
        "V1 — The test budget",
        "Static checks 1-4 all PASS",
        ("static_01_04",),
    ),
    VRow(
        "V1.2",
        "V1 — The test budget",
        "test_ci_budget.py passes; a worker stays on loopback",
        (
            "ruff_check",
            "ruff_format",
            "pyright",
            "pyright_linux",
            "lint_imports",
            "pytest",
            "coverage_policy",
            "coverage_ai_context",
            "coverage_ai_validate",
            Select("tests.test_ci_budget"),
        ),
    ),
    VRow(
        "V1.3",
        "V1 — The test budget",
        "verify_phase06.py --post passes all 79 (and 5 to 1)",
        ("verify_phase06_post",),
    ),
    # V2 — Locations (5 rows)
    VRow(
        "V2.1",
        "V2 — Locations",
        "Static checks 5-13 all PASS",
        ("static_05_13",),
    ),
    VRow(
        "V2.2",
        "V2 — Locations",
        "No-county, search, place, and remove tests pass",
        (
            Select(
                "tests.sources.test_nws_no_county",
                "tests.sources.test_nominatim_search",
                "tests.services.test_location_no_county",
                "tests.services.test_location_search",
                "tests.services.test_location_remove",
                "tests.web.test_location_writes",
                "tests.cli.test_locations_place",
            ),
        ),
    ),
    VRow(
        "V2.3",
        "V2 — Locations",
        "Nassau reads the breakpoint path; contract tests pass",
        (
            "pytest_live",
            Select("tests.cli.test_location_nassau", "tests.live.test_live_nws"),
        ),
    ),
    VRow(
        "V2.4",
        "V2 — Locations",
        "locations.spec.ts: search, add, remove in the page",
        (
            "playwright_ui",
            Select("src/settings/LocationManager.test.tsx", "locations.spec.ts"),
        ),
    ),
    VRow(
        "V2.5",
        "V2 — Locations",
        "The operator's service holds a location, at head",
        ("operator_locations_at_head",),
    ),
    # V3 — The phone (5 rows)
    VRow(
        "V3.1",
        "V3 — The phone",
        "Static checks 14-23 all PASS",
        ("static_14_23",),
    ),
    VRow(
        "V3.2",
        "V3 — The phone",
        "Channel, preference, doctor, and redaction tests pass",
        (
            Select(
                "tests.services.test_ntfy",
                "tests.services.test_location_preferences",
                "tests.services.test_doctor_ntfy",
                "tests.web.test_notification_channels",
                "tests.cli.test_notify_phone",
                "src/settings/NotificationChannels.test.tsx",
            ),
        ),
    ),
    VRow(
        "V3.3",
        "V3 — The phone",
        "Quiet hours hold a repeat; an escalation reaches ntfy",
        (
            Select(
                "tests.services.test_quiet_hours_phone",
                "tests.services.test_recovered_phone",
            ),
        ),
    ),
    VRow(
        "V3.4",
        "V3 — The phone",
        "The policy and every notification golden are unchanged",
        (
            Select(
                "tests.services.test_policy",
                "tests.services.test_notification_goldens",
            ),
        ),
    ),
    VRow(
        "V3.5",
        "V3 — The phone",
        "The operator's doctor passes ntfy; a delivery landed",
        (
            "operator_doctor_and_ntfy_delivered",
            Select("tests.live.test_ntfy_live"),
        ),
    ),
    # V4 — Settings and retention (4 rows)
    VRow(
        "V4.1",
        "V4 — Settings and retention",
        "Static checks 24-32 all PASS",
        ("static_24_32",),
    ),
    VRow(
        "V4.2",
        "V4 — Settings and retention",
        "Settings write tests pass; every refusal holds",
        (
            Select(
                "tests.services.test_settings_file",
                "tests.services.test_live_settings",
                "tests.web.test_settings_writes",
                "src/settings/QuietHoursForm.test.tsx",
            ),
        ),
    ),
    VRow(
        "V4.3",
        "V4 — Settings and retention",
        "A prune equals its plan; policy state and diff hold",
        (
            Select(
                "tests.services.test_retention",
                "tests.services.test_retention_keeplist",
                "tests.services.test_foreign_key_indexes",
                "tests.cli.test_storage_growth",
            ),
        ),
    ),
    VRow(
        "V4.4",
        "V4 — Settings and retention",
        "Prune command, route, and worker tests pass",
        (
            "export_schemas_check",
            Select(
                "tests.services.test_retention_worker",
                "tests.web.test_retention_routes",
                "tests.cli.test_prune_command",
                "src/settings/RetentionPanel.test.tsx",
            ),
        ),
    ),
    # V5 — The map's depth (4 rows)
    VRow(
        "V5.1",
        "V5 — The map's depth",
        "Static checks 33-40 all PASS",
        ("static_33_40",),
    ),
    VRow(
        "V5.2",
        "V5 — The map's depth",
        "Layer, slider, and CSP route tests pass",
        (
            "export_openapi_check",
            "export_api_fixtures_check",
            Select(
                "tests.web.test_map_depth",
                "tests.web.test_wind_probability_route",
                "tests.web.test_map_history",
                "tests.live.test_osm_referer_live",
            ),
        ),
    ),
    VRow(
        "V5.3",
        "V5 — The map's depth",
        "--node exits 0: types, lint, Vitest, build, licences",
        (
            "node_ci",
            "node_audit_signatures",
            "node_api_check",
            "node_lint",
            "node_typecheck",
            "node_vitest",
            "node_build",
            "node_licenses_check",
            "smoke_installed_web",
            Select("src/map/AdvisorySlider.test.tsx"),
        ),
    ),
    VRow(
        "V5.4",
        "V5 — The map's depth",
        "layers.spec.ts: no overlay request before its toggle",
        (Select("layers.spec.ts"),),
    ),
    # V6 — Charts and history (4 rows)
    VRow(
        "V6.1",
        "V6 — Charts and history",
        "Static checks 41-45 all PASS",
        ("static_41_45",),
    ),
    VRow(
        "V6.2",
        "V6 — Charts and history",
        "Charts and timeline routes pass; neither holds a distance",
        (
            Select(
                "tests.web.test_charts_route",
                "tests.web.test_timeline_before",
            ),
        ),
    ),
    VRow(
        "V6.3",
        "V6 — Charts and history",
        "Chart scales and components pass; no style renders",
        (
            Select(
                "src/charts/scale.test.ts",
                "src/charts/LevelSparkline.test.tsx",
                "src/charts/ArrivalTimeline.test.tsx",
                "src/charts/LevelHistoryChart.test.tsx",
                "src/charts/WindProbabilityChart.test.tsx",
            ),
        ),
    ),
    VRow(
        "V6.4",
        "V6 — Charts and history",
        "charts.spec.ts: sparkline and wind chart, no CSP event",
        (Select("phase7.spec.ts", "screens.spec.ts"),),
    ),
    # V7 — Replay in the UI (4 rows)
    VRow(
        "V7.1",
        "V7 — Replay in the UI",
        "Static checks 46-50 all PASS",
        ("static_46_50",),
    ),
    VRow(
        "V7.2",
        "V7 — Replay in the UI",
        "Every scrubbed step equals its golden through the API",
        (
            Select(
                "tests.services.test_replay_timelines",
                "tests.web.test_replay_scrub",
                "tests.engine.test_changes",
                "tests.engine.test_golden_replays",
                "src/assessment/assessment.test.tsx",
            ),
        ),
    ),
    VRow(
        "V7.3",
        "V7 — Replay in the UI",
        "A whole scrub writes, publishes, and sends nothing",
        (Select("tests.web.test_replay_writes_nothing"),),
    ),
    VRow(
        "V7.4",
        "V7 — Replay in the UI",
        "replay.spec.ts: Dorian at Nassau reads 4, then 5",
        (Select("replay.spec.ts"),),
    ),
    # V8 — The report (4 rows)
    VRow(
        "V8.1",
        "V8 — The report",
        "Static checks 51-55 all PASS",
        ("static_51_55",),
    ),
    VRow(
        "V8.2",
        "V8 — The report",
        "The report renders every state; markup stays escaped",
        (
            Select(
                "tests.services.test_report_render",
                "tests.services.test_report_escape",
                "tests.web.test_api_report",
                "tests.cli.test_report_command",
            ),
        ),
    ),
    VRow(
        "V8.3",
        "V8 — The report",
        "The privacy scan finds nothing that locates the operator",
        (Select("tests.services.test_report_privacy"),),
    ),
    VRow(
        "V8.4",
        "V8 — The report",
        "report.spec.ts: opens offline, prints to PDF",
        (Select("report.spec.ts"),),
    ),
    # V9 — The whole phase on the operator's machine (5 rows)
    VRow(
        "V9.1",
        "V9 — The whole phase on the operator's machine",
        "Static checks 56-59 all PASS",
        ("static_56_59",),
    ),
    VRow(
        "V9.2",
        "V9 — The whole phase on the operator's machine",
        "phase7.spec.ts: the whole flow, the overlay's failure",
        (Select("phase7.spec.ts", "screens.spec.ts"),),
    ),
    VRow(
        "V9.3",
        "V9 — The whole phase on the operator's machine",
        "Server and tab each stay under 0.5% of a core idle",
        ("measure_idle_probe",),
    ),
    VRow(
        "V9.4",
        "V9 — The whole phase on the operator's machine",
        "Each alarm fires: ntfy, retention, and bad settings",
        (Select("tests.services.test_phase7_alarms"),),
    ),
    VRow(
        "V9.5",
        "V9 — The whole phase on the operator's machine",
        "The operator's /api/health reads head and corpus",
        ("operator_health_head_and_corpus",),
    ),
    # V10 — CI integration + security (4 rows)
    VRow(
        "V10.1",
        "V10 — CI integration + security",
        "verify_phase07.py --fast exits 0 on Ubuntu CI",
        (
            "verify_phase07_fast_budget",
            "phase_verify_ci",
            Select("tests.test_phase07_verification"),
        ),
    ),
    VRow(
        "V10.2",
        "V10 — CI integration + security",
        "phase-verify.yml's matrix includes '01' to '07'",
        ("static_64", "protection_requires_both"),
    ),
    VRow(
        "V10.3",
        "V10 — CI integration + security",
        "All 65 static checks in verify_phase07.py pass",
        ("static_01_65",),
    ),
    VRow(
        "V10.4",
        "V10 — CI integration + security",
        "--security exits 0 over both stacks",
        (
            "gitleaks",
            "bandit",
            "audit_deps",
            "personal_data_all",
            "personal_data_self_test",
            "npm_audit",
            "frontend_lint",
            "secret_shape_scan",
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
    """Evaluate all 42 rows of the V1-V10 post-implementation verification matrix."""
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
        ("static_01_04", 1, 4),
        ("static_05_13", 5, 13),
        ("static_14_23", 14, 23),
        ("static_24_32", 24, 32),
        ("static_33_40", 33, 40),
        ("static_41_45", 41, 45),
        ("static_46_50", 46, 50),
        ("static_51_55", 51, 55),
        ("static_56_59", 56, 59),
        ("static_64", 64, 64),
        ("static_01_65", 1, 65),
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
    """Run static checks, all suites, probes, and evaluate the 42-row V1-V10 matrix."""
    print(
        "Notice: --post starts the offline demonstration servers (scripts/serve_demo.py) and "
        "headless Chromium for the Playwright smoke and the 600 s idle CPU measurement, "
        "runs verify_phase06.py --post (79 checks, including its ~$0.40 live AI eval in a "
        "temporary directory), and reads the operator's running service only through "
        "GET /api/health, GET /api/locations (count only), GET /api/notifications/channels, "
        "and doctor --offline --json.",
        flush=True,
    )
    static_outcomes = run_static_checks()
    suite = Suite()
    _record_static_slices(static_outcomes, suite)

    with tempfile.TemporaryDirectory(prefix="weatherbot-post07-") as tmp:
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
        "sec.secret_shape_scan": "secret_shape_scan",
    }
    for out in sec_outcomes:
        if out.item_id in sec_map:
            suite.commands[sec_map[out.item_id]] = out.status

    heading("Post-implementation probes")
    run_probe(
        "phase_verify_ci",
        "phase-verify (01) through (07) CI checks",
        lambda: phase_entries_green(("01", "02", "03", "04", "05", "06", "07")),
        suite,
    )
    run_probe(
        "protection_requires_both",
        "main branch protection requires gate and phase-verify",
        protection_requires_both,
        suite,
    )
    run_probe(
        "verify_phase06_post",
        "verify_phase06.py --post (79 checks)",
        phase_six_post,
        suite,
    )
    run_probe(
        "operator_locations_at_head",
        "operator /api/locations count >= 2 at DB head",
        operator_locations_at_head,
        suite,
    )
    run_probe(
        "operator_doctor_and_ntfy_delivered",
        "operator doctor ntfy pass and /api/notifications/channels delivered",
        operator_doctor_and_ntfy_delivered,
        suite,
    )
    run_probe(
        "operator_health_head_and_corpus",
        "operator /api/health at DB head with corpus=true and AI ready",
        operator_health_head_and_corpus,
        suite,
    )
    run_probe(
        "measure_idle_probe",
        "scripts/measure_idle.py (600 s idle CPU < 0.5% with retention and ai_state=ready)",
        measure_idle_probe,
        suite,
    )
    run_probe(
        "verify_phase07_fast_budget",
        "scripts/verify_phase07.py --fast (< 30 s)",
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
    group.add_argument("--fast", action="store_true", help="Run the 65 static checks only.")
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
        help="Run --py, --node, --ui, --live, and --security (all except --post).",
    )
    group.add_argument(
        "--post", action="store_true", help="Run the full 107-check Phase 7 verification."
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for Phase 7 verification."""
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
