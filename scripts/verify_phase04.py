# scripts/verify_phase04.py
"""Verify Phase 4 (Monitoring and notifications) against docs/roadmap/phase04-roadmap.md.

Modes (mutually exclusive; default ``--fast``):
  --fast      51 static file, AST, schema, golden, and config checks (< 30 s, no network).
  --py        Ruff, Pyright (host + Linux), import-linter, offline pytest with >=90%
              branch coverage on engine and policy, and package smoke.
  --live      Live source and monitor pytest suite (``pytest -m live``).
  --security  Secret, SAST, dependency, and personal-data scans.
  --all       --py + --live + --security.
  --post      Full V1-V7 post-implementation matrix (29 rows, 80 checks total).
"""

import argparse
import ast
import importlib
import json
import os
import re
import shutil
import sqlite3
import subprocess  # nosec B404 - fixed argument lists only, never a shell
import sys
import tempfile
import time
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Final, Literal, cast

from defusedxml import ElementTree

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
REPOSITORY: Final = "nathanramoscfa/weatherbot"
CI_WORKFLOW: Final = ".github/workflows/ci.yml"
PHASE_WORKFLOW: Final = ".github/workflows/phase-verify.yml"
ROADMAP: Final = "docs/roadmap/ROADMAP.md"
PHASE_ROADMAP: Final = "docs/roadmap/phase04-roadmap.md"
QA_FINDINGS: Final = "docs/phase04-qa-findings.md"
ALERT_LADDER: Final = "docs/ALERT-LADDER.md"
SERVICES: Final = "src/weatherbot/services"
SOURCES: Final = "src/weatherbot/sources"
CLI: Final = "src/weatherbot/cli"
VERSIONS: Final = f"{SERVICES}/persistence/migrations/versions"
NOTIFICATION_GOLDENS_DIR: Final = "tests/golden/notifications"
JSON_SCHEMA_2020_12: Final = "https://json-schema.org/draft/2020-12/schema"
MODES: Final = ("--fast", "--py", "--live", "--security", "--all", "--post")
FAST_BUDGET_SECONDS: Final = 30.0

PHASE_04_SCHEMAS: Final = (
    "check",
    "config",
    "config-path",
    "notifications",
    "notify-setup",
    "notify-test",
    "install-task",
    "uninstall-task",
)
ALL_PHASE_04_SCHEMAS: Final = (
    "locations",
    "fetch",
    "storms",
    "alerts",
    "doctor",
    "status",
    "replay",
    *PHASE_04_SCHEMAS,
)
CYCLE_TRIGGERS: Final = (
    "manual",
    "window",
    "roster",
    "alerts",
    "confirm",
    "retry",
    "startup",
    "resume",
    "fallback",
)
DECISION_KINDS: Final = (
    "escalation",
    "sent",
    "repeat",
    "quiet_hours",
    "held",
    "withdrawn",
    "informational",
)
NOTIFICATION_KINDS: Final = (
    "location",
    "degraded",
    "recovered",
    "stale_monitor",
    "test",
)
WINRT_PACKAGES: Final = (
    "winrt-runtime",
    "winrt-windows-foundation",
    "winrt-windows-foundation-collections",
    "winrt-windows-data-xml-dom",
    "winrt-windows-ui-notifications",
)
IRMA_NOTIFICATION_GOLDENS: Final = (
    "AL112017-miami-dade.json",
    "AL112017-nassau.json",
)
HEALTHY_SERVE_RESULTS: Final = frozenset({0, 0x41301})

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
    """One row of the Phase 4 V1-V7 post-implementation verification matrix."""

    item_id: str
    section: str
    description: str
    evidence: tuple[Evidence, ...]


@dataclass
class Suite:
    """Collected command and test outcomes for evaluating the V1-V7 matrix."""

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


def tracked(prefix: str = "", *, root: Path = REPO_ROOT) -> set[str]:
    """Return tracked repository-relative paths under ``prefix``."""
    args = ["ls-files", "--", prefix] if prefix else ["ls-files"]
    output = git(*args, root=root)
    return set(output.splitlines()) if output else set()


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


def class_methods(relative: str, class_name: str, root: Path = REPO_ROOT) -> set[str]:
    """Return method names defined directly on ``class_name`` in ``relative``."""
    cls = class_node(syntax(relative, root=root), class_name)
    return {
        item.name for item in cls.body if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
    }


def class_fields(relative: str, class_name: str, root: Path = REPO_ROOT) -> list[str]:
    """Return annotated field names defined directly on ``class_name``."""
    cls = class_node(syntax(relative, root=root), class_name)
    return [
        item.target.id
        for item in cls.body
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
    ]


def literal_strings(tree: ast.AST) -> set[str]:
    """Return every string constant inside ``tree``."""
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def job(workflow_path: str, job_name: str, root: Path = REPO_ROOT) -> str:
    """Extract one YAML job block from a workflow file."""
    text = read(workflow_path, root=root)
    pattern = rf"^  {re.escape(job_name)}:\n((?:    .*\n|\n)+)"
    match = re.search(pattern, text, re.MULTILINE)
    return match[1] if match else ""


def phase_matrix(root: Path = REPO_ROOT) -> set[str]:
    """Read the flow-form phase matrix as strings from ``phase-verify.yml``."""
    match = re.search(
        r"^\s+phase:\s*\[([^]]+)\]", job(PHASE_WORKFLOW, "verify", root=root), re.MULTILINE
    )
    if match is None:
        raise ValueError
    return {part.strip().strip("\"'") for part in match[1].split(",")}


def revision_record(relative: str, root: Path = REPO_ROOT) -> tuple[str, str | None, set[str]]:
    """Return ``(revision, down_revision, created_tables)`` for a migration file."""
    tree = syntax(relative, root=root)
    revision = cast("str", ast.literal_eval(assigned(tree, "revision")))
    parent = cast("str | None", ast.literal_eval(assigned(tree, "down_revision")))
    tables = {
        str(node.args[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_table"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    }
    return revision, parent, tables


# Step 1 static checks (1-6) ----------------------------------------------------------------


def check_01_revision_0004(root: Path = REPO_ROOT) -> bool:
    """Check 01: 0004_shared_geometry.py creates the shared geometry tables."""
    rel = f"{VERSIONS}/0004_shared_geometry.py"
    if not files_exist(rel, root=root):
        return False
    rev, parent, tables = revision_record(rel, root=root)
    return (
        rev == "0004"
        and parent == "0003"
        and tables == {"geometry_contents", "snapshot_provenances", "snapshot_geometries"}
    )


def check_02_snapshot_repository_shared_geometry(root: Path = REPO_ROOT) -> bool:
    """Check 02: SnapshotRepository keeps origin != 'live' and constructs no ProductGeometryRow."""
    rel = f"{SERVICES}/persistence/repositories.py"
    tree = syntax(rel, root=root)
    cls = class_node(tree, "SnapshotRepository")
    calls_product_geometry = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ProductGeometryRow"
        for node in ast.walk(cls)
    )
    text = read(rel, root=root)
    return (
        'snapshot.origin != "live"' in text
        and not calls_product_geometry
        and all(
            name in text
            for name in ("GeometryContentRow", "SnapshotProvenanceRow", "SnapshotGeometryRow")
        )
    )


def check_03_sha256_and_zlib(root: Path = REPO_ROOT) -> bool:
    """Check 03: repositories.py hashes content with hashlib.sha256 and compresses with zlib."""
    rel = f"{SERVICES}/persistence/repositories.py"
    return contains(
        rel,
        "import hashlib",
        "import zlib",
        "hashlib.sha256",
        "zlib.compress",
        "zlib.decompress",
        root=root,
    )


def check_04_frozen_revisions(root: Path = REPO_ROOT) -> bool:
    """Check 04: test_database.py FROZEN dict pins 0001, 0002, and 0003."""
    rel = "tests/services/test_database.py"
    frozen = object_of(ast.literal_eval(assigned(syntax(rel, root=root), "FROZEN")))
    return {"0001_baseline.py", "0002_drift_warnings.py", "0003_assessments.py"} <= set(frozen)


def check_05_storage_tests_and_budget(root: Path = REPO_ROOT) -> bool:
    """Check 05: test_geometry_storage.py and test_storage_growth.py (BUDGET = 128 * 1024)."""
    growth = "tests/cli/test_storage_growth.py"
    if not files_exist("tests/services/test_geometry_storage.py", growth, root=root):
        return False
    budget_expr = assigned(syntax(growth, root=root), "BUDGET")
    return (
        isinstance(budget_expr, ast.BinOp)
        and isinstance(budget_expr.op, ast.Mult)
        and ast.literal_eval(budget_expr.left) == 128  # noqa: PLR2004
        and ast.literal_eval(budget_expr.right) == 1024  # noqa: PLR2004
    )


def check_06_shared_geometry_tables_constant(root: Path = REPO_ROOT) -> bool:
    """Check 06: test_tables.py defines SHARED_GEOMETRY_TABLES."""
    rel = "tests/services/test_tables.py"
    if not files_exist(rel, root=root):
        return False
    val = ast.literal_eval(assigned(syntax(rel, root=root), "SHARED_GEOMETRY_TABLES"))
    return set(cast("set[str]", val)) == {
        "geometry_contents",
        "snapshot_provenances",
        "snapshot_geometries",
    }


# Step 2 static checks (7-15) ---------------------------------------------------------------


def check_07_revision_0005(root: Path = REPO_ROOT) -> bool:
    """Check 07: 0005_monitor.py creates heartbeats and monitor_cycles."""
    rel = f"{VERSIONS}/0005_monitor.py"
    if not files_exist(rel, root=root):
        return False
    rev, parent, tables = revision_record(rel, root=root)
    return rev == "0005" and parent == "0004" and tables == {"heartbeats", "monitor_cycles"}


def check_08_monitor_service_and_triggers(root: Path = REPO_ROOT) -> bool:
    """Check 08: services/monitor.py defines MonitorService.run_cycle, CycleResult, CycleTrigger."""
    rel = f"{SERVICES}/monitor.py"
    if not defines(rel, "MonitorService", "CycleResult", "CycleTrigger", root=root):
        return False
    if "run_cycle" not in class_methods(rel, "MonitorService", root=root):
        return False
    trigger_strings = literal_strings(assigned(syntax(rel, root=root), "CycleTrigger"))
    return trigger_strings == set(CYCLE_TRIGGERS)


def check_09_process_lock(root: Path = REPO_ROOT) -> bool:
    """Check 09: services/locks.py defines ProcessLock and LockBusyError using msvcrt/fcntl only."""
    rel = f"{SERVICES}/locks.py"
    if not defines(rel, "ProcessLock", "LockBusyError", root=root):
        return False
    tree = syntax(rel, root=root)
    if_nodes = [node for node in tree.body if isinstance(node, ast.If)]
    if len(if_nodes) != 1:
        return False
    branch = if_nodes[0]
    win_imports = [
        alias.name for n in branch.body if isinstance(n, ast.Import) for alias in n.names
    ]
    posix_imports = [
        alias.name for n in branch.orelse if isinstance(n, ast.Import) for alias in n.names
    ]
    return (
        win_imports == ["msvcrt"]
        and posix_imports == ["fcntl"]
        and contains(rel, 'sys.platform == "win32"', root=root)
    )


def check_10_begin_immediate_and_busy_timeout(root: Path = REPO_ROOT) -> bool:
    """Check 10: database.py begins writing transactions with BEGIN IMMEDIATE and 30 s timeout."""
    rel = f"{SERVICES}/persistence/database.py"
    if not defines(rel, "writing_session", "BUSY_TIMEOUT_MS", root=root):
        return False
    timeout = ast.literal_eval(assigned(syntax(rel, root=root), "BUSY_TIMEOUT_MS"))
    return timeout == 30_000 and contains(rel, '"BEGIN IMMEDIATE"', root=root)  # noqa: PLR2004


def check_11_health_staleness(root: Path = REPO_ROOT) -> bool:
    """Check 11: services/health.py defines Staleness and staleness with the two-cadence rule."""
    rel = f"{SERVICES}/health.py"
    if not defines(rel, "Staleness", "staleness", "STALE_AFTER_CADENCES", root=root):
        return False
    cadences = ast.literal_eval(assigned(syntax(rel, root=root), "STALE_AFTER_CADENCES"))
    return cadences == 2 and contains(rel, "STALE_AFTER_CADENCES * cadence", root=root)  # noqa: PLR2004


def check_12_cli_check_once_json(root: Path = REPO_ROOT) -> bool:
    """Check 12: cli/check.py defines check with --once and --json."""
    rel = f"{CLI}/check.py"
    return defines(rel, "check", root=root) and contains(
        rel, '"--once"', "json_output: JsonOption", root=root
    )


def check_13_cli_config_show_path(root: Path = REPO_ROOT) -> bool:
    """Check 13: cli/config.py defines show and path with --json."""
    rel = f"{CLI}/config.py"
    return defines(rel, "show", "path", root=root) and contains(
        rel, '@app.command("show")', '@app.command("path")', '"--json"', root=root
    )


def check_14_environment_overrides(root: Path = REPO_ROOT) -> bool:
    """Check 14: ENVIRONMENT_OVERRIDES covers all [monitor] and [notifications] keys."""
    rel = f"{SERVICES}/config.py"
    tree = syntax(rel, root=root)
    mon_fields = class_fields(rel, "MonitorSettings", root=root)
    notif_fields = class_fields(rel, "NotificationSettings", root=root)
    strings = literal_strings(assigned(tree, "ENVIRONMENT_OVERRIDES"))
    expected_mon = {f"WEATHERBOT_MONITOR_{key.upper()}" for key in mon_fields}
    expected_notif = {f"WEATHERBOT_NOTIFICATIONS_{key.upper()}" for key in notif_fields}
    return (
        len(mon_fields) >= 13  # noqa: PLR2004
        and len(notif_fields) >= 5  # noqa: PLR2004
        and expected_mon <= strings
        and expected_notif <= strings
    )


def _schemas_valid(names: Sequence[str], root: Path = REPO_ROOT) -> bool:
    docs_rel = f"{CLI}/documents.py"
    doc_keys = literal_strings(assigned(syntax(docs_rel, root=root), "DOCUMENTS"))
    for name in names:
        schema_rel = f"docs/schema/{name}.schema.json"
        if not files_exist(schema_rel, root=root):
            return False
        if name not in doc_keys:
            return False
        if json_file(schema_rel, root=root).get("$schema") != JSON_SCHEMA_2020_12:
            return False
    return True


def check_15_step2_schemas(root: Path = REPO_ROOT) -> bool:
    """Check 15: check, config, and config-path schemas are tracked and match export_schemas."""
    return _schemas_valid(("check", "config", "config-path"), root=root)


# Step 3 static checks (16-24) --------------------------------------------------------------


def check_16_revision_0006(root: Path = REPO_ROOT) -> bool:
    """Check 16: 0006_notifications.py creates notifications, deliveries, and decisions."""
    rel = f"{VERSIONS}/0006_notifications.py"
    if not files_exist(rel, root=root):
        return False
    rev, parent, tables = revision_record(rel, root=root)
    return (
        rev == "0006"
        and parent == "0005"
        and tables == {"notifications", "notification_deliveries", "notification_decisions"}
    )


def check_17_policy_definitions(root: Path = REPO_ROOT) -> bool:
    """Check 17: services/policy.py defines pure policy types, decide, and DECISION_KINDS."""
    rel = f"{SERVICES}/policy.py"
    required = (
        "decide",
        "PolicyState",
        "PolicySettings",
        "QuietHours",
        "PolicyDecision",
        "NotificationDraft",
        "Decided",
        "DECISION_KINDS",
    )
    if not defines(rel, *required, root=root):
        return False
    kinds = ast.literal_eval(assigned(syntax(rel, root=root), "DECISION_KINDS"))
    return tuple(cast("tuple[str, ...]", kinds)) == DECISION_KINDS


def check_18_policy_architecture_scan(root: Path = REPO_ROOT) -> bool:
    """Check 18: tests/test_architecture.py scans services/policy.py for purity and determinism."""
    rel = "tests/test_architecture.py"
    return defines(
        rel,
        "POLICY_MODULE",
        "POLICY_ALLOWED_IMPORTS",
        "test_the_notification_policy_is_pure_and_deterministic",
        root=root,
    ) and contains(
        rel,
        '"services" / "policy.py"',
        "banned_imports(source)",
        "nondeterminism(source)",
        root=root,
    )


def check_19_notification_service(root: Path = REPO_ROOT) -> bool:
    """Check 19: services/notifications.py defines NotificationService, Channel, and LogChannel."""
    rel = f"{SERVICES}/notifications.py"
    if not defines(
        rel, "NotificationService", "Channel", "LogChannel", "replay_notifications", root=root
    ):
        return False
    methods = class_methods(rel, "NotificationService", root=root)
    return {"decide_cycle", "send", "recent"} <= methods


def _valid_golden_doc(doc: dict[str, object]) -> bool:
    approval = doc.get("approval")
    timelines = doc.get("timelines")
    if not isinstance(approval, dict) or not isinstance(timelines, dict):
        return False
    approval_dict = cast("dict[str, object]", approval)
    timelines_dict = cast("dict[str, object]", timelines)
    if not array_of(timelines_dict.get("defaults")) or not array_of(timelines_dict.get("strict")):
        return False
    day_str = str(approval_dict.get("date", ""))
    try:
        valid_date = date.fromisoformat(day_str).isoformat() == day_str
    except ValueError:
        return False
    sha = str(approval_dict.get("timelines_sha256", ""))
    return valid_date and bool(re.fullmatch(r"[0-9a-f]{64}", sha))


def check_20_notification_goldens(root: Path = REPO_ROOT) -> bool:
    """Check 20: two approved Irma notification goldens and build_notification_goldens --check."""
    script_rel = "scripts/build_notification_goldens.py"
    expected = {f"{NOTIFICATION_GOLDENS_DIR}/{name}" for name in IRMA_NOTIFICATION_GOLDENS}
    return (
        files_exist(script_rel, *expected, root=root)
        and contains(script_rel, '"--check"', root=root)
        and tracked(NOTIFICATION_GOLDENS_DIR, root=root) == expected
        and all(_valid_golden_doc(json_file(rel, root=root)) for rel in sorted(expected))
    )


def check_21_cli_notify_log(root: Path = REPO_ROOT) -> bool:
    """Check 21: cli/notify.py defines log with --limit (default 20) and --json."""
    rel = f"{CLI}/notify.py"
    if not defines(rel, "log", "DEFAULT_LIMIT", root=root):
        return False
    limit = ast.literal_eval(assigned(syntax(rel, root=root), "DEFAULT_LIMIT"))
    return limit == 20 and contains(  # noqa: PLR2004
        rel, '@app.command("log")', '"--limit"', "json_output: JsonOption", root=root
    )


def check_22_notifications_schema(root: Path = REPO_ROOT) -> bool:
    """Check 22: docs/schema/notifications.schema.json is tracked and current."""
    return _schemas_valid(("notifications",), root=root)


def check_23_alert_ladder_notifications(root: Path = REPO_ROOT) -> bool:
    """Check 23: docs/ALERT-LADDER.md contains ## Notifications."""
    return files_exist(ALERT_LADDER, root=root) and contains(
        ALERT_LADDER, "## Notifications", "weatherbot.services.policy.decide", root=root
    )


def check_24_step3_tests_tracked(root: Path = REPO_ROOT) -> bool:
    """Check 24: Step 3 policy, notifications, replay, goldens, and notify_log tests tracked."""
    return files_exist(
        "tests/services/test_policy.py",
        "tests/services/test_notifications.py",
        "tests/services/test_notification_replay.py",
        "tests/services/test_notification_goldens.py",
        "tests/cli/test_notify_log.py",
        root=root,
    )


# Step 4 static checks (25-31) --------------------------------------------------------------


def check_25_pyproject_winrt_and_desktop_marker(root: Path = REPO_ROOT) -> bool:
    """Check 25: pyproject.toml declares win32 winrt packages and the desktop pytest marker."""
    deps = [str(item) for item in array_of(config("project", "dependencies", root=root))]
    for pkg in WINRT_PACKAGES:
        if not any(dep.startswith(pkg) and "sys_platform == 'win32'" in dep for dep in deps):
            return False
    markers = [
        str(m) for m in array_of(config("tool", "pytest", "ini_options", "markers", root=root))
    ]
    addopts = str(config("tool", "pytest", "ini_options", "addopts", root=root))
    return (
        any(m.startswith("desktop:") for m in markers)
        and "not live and not corpus and not desktop" in addopts
    )


def check_26_toast_service(root: Path = REPO_ROOT) -> bool:
    """Check 26: services/toast.py defines Weatherbot.Monitor toast channel and HKCU identity."""
    rel = f"{SERVICES}/toast.py"
    required = (
        "APP_ID",
        "ToastChannel",
        "NullChannel",
        "toast_channel",
        "toast_xml",
        "register_identity",
        "unregister_identity",
        "identity_registered",
    )
    if not defines(rel, *required, root=root):
        return False
    tree = syntax(rel, root=root)
    if ast.literal_eval(assigned(tree, "APP_ID")) != "Weatherbot.Monitor":
        return False
    for stmt in tree.body[1:]:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Attribute) and node.attr == "HKEY_LOCAL_MACHINE":
                return False
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and "HKEY_LOCAL_MACHINE" in node.value
            ):
                return False
    for node in tree.body:
        if isinstance(node, ast.Import | ast.ImportFrom):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            if any(name == "winreg" or name.startswith("winrt") for name in names):
                return False
    return contains(
        rel,
        'if sys.platform == "win32":',
        "HKEY_CURRENT_USER",
        "html.escape",
        "NOTICE",
        'placement="attribution"',
        root=root,
    )


def check_27_cli_notify_setup_and_test(root: Path = REPO_ROOT) -> bool:
    """Check 27: cli/notify.py defines setup (--remove, --json) and test (--json)."""
    rel = f"{CLI}/notify.py"
    return defines(rel, "setup", "send_test", root=root) and contains(
        rel,
        '@app.command("setup")',
        '"--remove"',
        '@app.command("test")',
        root=root,
    )


def check_28_doctor_toast_check(root: Path = REPO_ROOT) -> bool:
    """Check 28: services/doctor.py defines the toast check."""
    rel = f"{SERVICES}/doctor.py"
    return defines(rel, "toast_check", root=root) and contains(
        rel, 'Check("toast"', 'deliveries.latest_delivery("toast")', root=root
    )


def check_29_step4_schemas(root: Path = REPO_ROOT) -> bool:
    """Check 29: notify-setup and notify-test schemas are tracked and current."""
    return _schemas_valid(("notify-setup", "notify-test"), root=root)


def check_30_step4_tests_tracked(root: Path = REPO_ROOT) -> bool:
    """Check 30: Step 4 toast, doctor_toast, notify_commands, and toast_desktop tests tracked."""
    return files_exist(
        "tests/services/test_toast.py",
        "tests/services/test_doctor_toast.py",
        "tests/cli/test_notify_commands.py",
        "tests/desktop/test_toast_desktop.py",
        root=root,
    )


def check_31_ci_platforms_and_linux_toast(root: Path = REPO_ROOT) -> bool:
    """Check 31: ci.yml installs, typechecks, and tests on ubuntu-latest and windows-latest."""
    test_job = job(CI_WORKFLOW, "test", root=root)
    type_job = job(CI_WORKFLOW, "typecheck", root=root)
    pkg_job = job(CI_WORKFLOW, "package", root=root)
    return (
        "ubuntu-latest" in test_job
        and "windows-latest" in test_job
        and "ubuntu-latest" in type_job
        and "windows-latest" in type_job
        and "ubuntu-latest" in pkg_job
        and "windows-latest" in pkg_job
    )


# Step 5 static checks (32-39) --------------------------------------------------------------


def check_32_scheduler(root: Path = REPO_ROOT) -> bool:
    """Check 32: services/scheduler.py defines Job and Scheduler with 60 s max sleep."""
    rel = f"{SERVICES}/scheduler.py"
    if not defines(rel, "Job", "Scheduler", "MAX_SLEEP_S", "RESUME_GAP_S", root=root):
        return False
    tree = syntax(rel, root=root)
    max_sleep = ast.literal_eval(assigned(tree, "MAX_SLEEP_S"))
    resume_gap = ast.literal_eval(assigned(tree, "RESUME_GAP_S"))
    return (
        max_sleep == 60.0  # noqa: PLR2004
        and resume_gap == 60.0  # noqa: PLR2004
        and contains(rel, "clock:", "sleep:", "random:", "max_sleep_s:", "on_resume:", root=root)
    )


def check_33_cone_advisories(root: Path = REPO_ROOT) -> bool:
    """Check 33: sources/nhc_map.py defines fetch_cone_advisories and parse_cone_advisories."""
    rel = f"{SOURCES}/nhc_map.py"
    if not defines(
        rel, "CONE_ADVISORY_FIELDS", "parse_cone_advisories", "fetch_cone_advisories", root=root
    ):
        return False
    fields = ast.literal_eval(assigned(syntax(rel, root=root), "CONE_ADVISORY_FIELDS"))
    return tuple(cast("tuple[str, ...]", fields)) == ("binnumber", "advisnum") and contains(
        rel, "attributes(fetcher, service, layer, CONE_ADVISORY_FIELDS)", root=root
    )


def check_34_monitor_schedule(root: Path = REPO_ROOT) -> bool:
    """Check 34: services/schedule.py defines MonitorSchedule, watches, and run_heartbeat_task."""
    rel = f"{SERVICES}/schedule.py"
    required = (
        "MonitorSchedule",
        "PRODUCT_HOURS",
        "ROSTER_CACHE_TTL_S",
        "LADDER_SOURCES",
        "run_heartbeat_task",
    )
    if not defines(rel, *required, root=root):
        return False
    tree = syntax(rel, root=root)
    hours = ast.literal_eval(assigned(tree, "PRODUCT_HOURS"))
    ttl = ast.literal_eval(assigned(tree, "ROSTER_CACHE_TTL_S"))
    sources = ast.literal_eval(assigned(tree, "LADDER_SOURCES"))
    return (
        tuple(cast("tuple[int, ...]", hours)) == (0, 3, 6, 9, 12, 15, 18, 21)
        and ttl == 60.0  # noqa: PLR2004
        and tuple(cast("tuple[str, ...]", sources))
        == (
            "nhc-current-storms",
            "nhc-map-tropical-summary",
            "nws-alerts-point",
            "nws-alerts-zone",
        )
    )


def check_35_rotating_log_handler(root: Path = REPO_ROOT) -> bool:
    """Check 35: services/logs.py configures RotatingFileHandler (1 MiB, 5 backups) and pythonw."""
    rel = f"{SERVICES}/logs.py"
    if not defines(rel, "LOG_MAX_BYTES", "LOG_BACKUP_COUNT", "configure_logging", root=root):
        return False
    tree = syntax(rel, root=root)
    max_bytes = ast.literal_eval(assigned(tree, "LOG_MAX_BYTES"))
    backups = ast.literal_eval(assigned(tree, "LOG_BACKUP_COUNT"))
    return (
        max_bytes == 1_048_576  # noqa: PLR2004
        and backups == 5  # noqa: PLR2004
        and contains(
            rel,
            "RotatingFileHandler",
            'encoding="utf-8"',
            "RedactingFilter()",
            "sys.stderr is None",
            root=root,
        )
    )


def check_36_cli_serve(root: Path = REPO_ROOT) -> bool:
    """Check 36: cli/serve.py defines serve acquiring monitor.lock and clearing heartbeat."""
    rel = f"{CLI}/serve.py"
    sched_rel = f"{SERVICES}/schedule.py"
    return (
        defines(rel, "serve", "run_monitor_loop", root=root)
        and contains(rel, "ProcessLock(paths.monitor_lock_path)", "run_monitor(", root=root)
        and contains(sched_rel, "clear_runner_heartbeat_cadence(engine, runner", root=root)
    )


def check_37_cli_check_loop(root: Path = REPO_ROOT) -> bool:
    """Check 37: cli/check.py runs scheduler without --once and refuses --json without --once."""
    rel = f"{CLI}/check.py"
    return contains(
        rel,
        'run_monitor_loop(ctx, runner="check")',
        'fail(output, "--json requires --once", EXIT_USAGE)',
        root=root,
    )


def check_38_simulate_advisory_script(root: Path = REPO_ROOT) -> bool:
    """Check 38: scripts/simulate_advisory.py uses 'simulated Miami-Dade' and recorded_services."""
    rel = "scripts/simulate_advisory.py"
    if not files_exist(rel, root=root) or not defines(rel, "SIMULATED_MIAMI", "main", root=root):
        return False
    sim_name = ast.literal_eval(assigned(syntax(rel, root=root), "SIMULATED_MIAMI"))
    return sim_name == "simulated Miami-Dade" and contains(
        rel, "TemporaryDirectory", "recorded_services()", root=root
    )


def check_39_step5_tests_tracked(root: Path = REPO_ROOT) -> bool:
    """Check 39: Step 5 scheduler, cone_advisories, schedule, log_file, serve, simulation tests."""
    return files_exist(
        "tests/services/test_scheduler.py",
        "tests/sources/test_cone_advisories.py",
        "tests/services/test_schedule.py",
        "tests/services/test_log_file.py",
        "tests/cli/test_serve_command.py",
        "tests/scripts/test_simulate_advisory.py",
        root=root,
    )


# Step 6 static checks (40-46) --------------------------------------------------------------


def _has_shell_true(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Call)
        and any(
            kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True
            for kw in node.keywords
        )
        for node in ast.walk(tree)
    )


def check_40_tasks_service(root: Path = REPO_ROOT) -> bool:
    r"""Check 40: services/tasks.py defines \Weatherbot\ tasks without shell=True."""
    rel = f"{SERVICES}/tasks.py"
    required = (
        "TASK_FOLDER",
        "TASK_NAMES",
        "CREATE_NO_WINDOW",
        "SERVE_TIME_LIMIT",
        "CHECK_TIME_LIMIT",
        "task_xml",
        "install",
        "uninstall",
        "run",
        "query",
    )
    if not defines(rel, *required, root=root):
        return False
    tree = syntax(rel, root=root)
    constants_ok = (
        ast.literal_eval(assigned(tree, "TASK_FOLDER")) == "\\Weatherbot\\"
        and tuple(cast("tuple[str, ...]", ast.literal_eval(assigned(tree, "TASK_NAMES"))))
        == ("serve", "check")
        and ast.literal_eval(assigned(tree, "CREATE_NO_WINDOW")) == 0x08000000  # noqa: PLR2004
        and ast.literal_eval(assigned(tree, "SERVE_TIME_LIMIT")) == "PT0S"
        and ast.literal_eval(assigned(tree, "CHECK_TIME_LIMIT")) == "PT30M"
    )
    return (
        constants_ok
        and not _has_shell_true(tree)
        and contains(
            rel,
            "<LogonType>InteractiveToken</LogonType>",
            "<RunLevel>LeastPrivilege</RunLevel>",
            "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>",
            "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>",
            "<StartWhenAvailable>",
            "System32",
            "schtasks.exe",
            "powershell.exe",
            root=root,
        )
    )


def check_41_cli_tasks_commands(root: Path = REPO_ROOT) -> bool:
    """Check 41: cli/tasks.py defines install_task and uninstall_task and registers them."""
    tasks_rel = f"{CLI}/tasks.py"
    init_rel = f"{CLI}/__init__.py"
    return (
        defines(tasks_rel, "install_task", "uninstall_task", root=root)
        and contains(tasks_rel, '"--allow-checkout"', "json_output: JsonOption", root=root)
        and contains(
            init_rel,
            'app.command("install-task")(tasks.install_task)',
            'app.command("uninstall-task")(tasks.uninstall_task)',
            root=root,
        )
    )


def check_42_fallback_supervision(root: Path = REPO_ROOT) -> bool:
    """Check 42: check --if-stale and run_fallback_check with 3-min wait, restart, and heartbeat."""
    check_rel = f"{CLI}/check.py"
    sched_rel = f"{SERVICES}/schedule.py"
    if not defines(
        sched_rel,
        "FALLBACK_WAIT_S",
        "FALLBACK_HEARTBEAT_CADENCE_S",
        "run_fallback_check",
        root=root,
    ):
        return False
    tree = syntax(sched_rel, root=root)
    wait_s = ast.literal_eval(assigned(tree, "FALLBACK_WAIT_S"))
    cadence_s = ast.literal_eval(assigned(tree, "FALLBACK_HEARTBEAT_CADENCE_S"))
    return (
        wait_s == 180.0  # noqa: PLR2004
        and cadence_s == 3600  # noqa: PLR2004
        and contains(check_rel, '"--if-stale"', '"--if-stale requires --once"', root=root)
        and contains(
            sched_rel,
            '"not_responding"',
            '"not_running"',
            'tasks_service.run("serve")',
            '"fallback"',
            root=root,
        )
    )


def check_43_stale_monitor_and_db_refused_toast(root: Path = REPO_ROOT) -> bool:
    """Check 43: NotificationKind includes stale_monitor and deliver_database_refused_toast."""
    notif_rel = f"{SERVICES}/notifications.py"
    docs_rel = f"{CLI}/documents.py"
    if not defines(notif_rel, "NOTIFICATION_KINDS", "deliver_database_refused_toast", root=root):
        return False
    kinds = ast.literal_eval(assigned(syntax(notif_rel, root=root), "NOTIFICATION_KINDS"))
    return tuple(cast("tuple[str, ...]", kinds)) == NOTIFICATION_KINDS and contains(
        docs_rel, '"stale_monitor"', root=root
    )


def check_44_doctor_tasks_and_path(root: Path = REPO_ROOT) -> bool:
    """Check 44: services/doctor.py defines tasks_check, path_check, and serve heartbeat check."""
    rel = f"{SERVICES}/doctor.py"
    return defines(rel, "tasks_check", "path_check", "heartbeat_check", root=root) and contains(
        rel,
        'Check("tasks"',
        'Check("path"',
        "serve_installed",
        root=root,
    )


def check_45_step6_schemas(root: Path = REPO_ROOT) -> bool:
    """Check 45: install-task and uninstall-task schemas are tracked and current."""
    return _schemas_valid(("install-task", "uninstall-task"), root=root)


def check_46_readme_phase04(root: Path = REPO_ROOT) -> bool:
    """Check 46: README.md documents Phase 4 commands and Status names Phase 4 complete."""
    if not files_exist("README.md", root=root):
        return False
    text = read("README.md", root=root)
    commands = (
        "uv tool install",
        "weatherbot notify setup",
        "weatherbot notify test",
        "weatherbot install-task",
        "weatherbot uninstall-task",
        "weatherbot serve",
        "weatherbot check",
        "weatherbot notify log",
        "weatherbot config show",
        "weatherbot config path",
    )
    if not all(cmd in text for cmd in commands):
        return False
    status_match = re.search(r"^## Status$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if status_match is None:
        return False
    status_block = status_match[1]
    return (
        "Phase 4" in status_block
        and "Phase 5" in status_block
        and "Phase 4 (monitoring and notifications) is in progress" not in status_block
    )


# Step 7 self-checks (47-51) ----------------------------------------------------------------


def check_47_verifier_self_check(root: Path = REPO_ROOT) -> bool:
    """Check 47: scripts/verify_phase04.py is tracked, valid Python, 51 checks, 6 modes."""
    rel = "scripts/verify_phase04.py"
    if not files_exist(rel, root=root):
        return False
    syntax(rel, root=root)
    text = read(rel, root=root)
    return len(STATIC_CHECKS) == 51 and all(f'"{mode}"' in text for mode in MODES)  # noqa: PLR2004


def check_48_verification_test_tracked(root: Path = REPO_ROOT) -> bool:
    """Check 48: tests/test_phase04_verification.py is tracked and covers fast and matrix."""
    rel = "tests/test_phase04_verification.py"
    return files_exist(rel, root=root) and contains(
        rel,
        "test_fast_verification_passes_all_static_checks_within_thirty_seconds",
        "test_phase_verify_workflow_includes_phase_04",
        "test_a_changed_deliverable_turns_exactly_its_check_red",
        root=root,
    )


def check_49_matrix_includes_04(root: Path = REPO_ROOT) -> bool:
    """Check 49: phase-verify.yml includes 01, 02, 03, and 04 in strategy.matrix.phase."""
    return {"01", "02", "03", "04"} <= phase_matrix(root=root)


def check_50_qa_findings_doc(root: Path = REPO_ROOT) -> bool:
    """Check 50: docs/phase04-qa-findings.md tracked with PR #40, Steps 1-7, and Pre-ship items."""
    if not files_exist(QA_FINDINGS, root=root):
        return False
    required = (
        "PR #40",
        "Step 1",
        "Step 2",
        "Step 3",
        "Step 4",
        "Step 5",
        "Step 6",
        "Step 7",
        "## Source-drift observations",
        "## Live smoke runs",
        "## Pre-ship items",
    )
    return contains(QA_FINDINGS, *required, root=root)


def check_51_roadmaps_consistent(root: Path = REPO_ROOT) -> bool:
    """Check 51: ROADMAP.md Phase 4 and phase04-roadmap.md Step 1-7 headers are consistent."""
    if not files_exist(ROADMAP, PHASE_ROADMAP, root=root):
        return False
    step_headers = tuple(f"## Step {n} —" for n in range(1, 8))
    return contains(ROADMAP, "### Phase 4 — Monitoring and notifications", root=root) and contains(
        PHASE_ROADMAP, *step_headers, root=root
    )


STATIC_CHECKS: tuple[Check, ...] = (
    # Step 1 — Shared geometry storage and migration 0004
    ("revision 0004 creates the shared geometry tables", check_01_revision_0004),
    (
        "SnapshotRepository refuses replay saves and constructs no ProductGeometryRow",
        check_02_snapshot_repository_shared_geometry,
    ),
    ("repositories hash geometry with sha256 and compress with zlib", check_03_sha256_and_zlib),
    ("test_database FROZEN pins merged revisions 0001 through 0003", check_04_frozen_revisions),
    (
        "shared-geometry and 128 KiB storage-growth tests tracked",
        check_05_storage_tests_and_budget,
    ),
    ("test_tables defines SHARED_GEOMETRY_TABLES", check_06_shared_geometry_tables_constant),
    # Step 2 — Heartbeats, monitor cycles, process locks, staleness, check --once, and config
    ("revision 0005 creates heartbeats and monitor_cycles", check_07_revision_0005),
    (
        "MonitorService defines run_cycle, CycleResult, and the nine CycleTrigger values",
        check_08_monitor_service_and_triggers,
    ),
    (
        "ProcessLock and LockBusyError import only msvcrt on win32 and fcntl elsewhere",
        check_09_process_lock,
    ),
    (
        "database writing_session begins BEGIN IMMEDIATE and sets 30 s busy_timeout",
        check_10_begin_immediate_and_busy_timeout,
    ),
    ("health defines Staleness and staleness with the two-cadence rule", check_11_health_staleness),
    ("cli/check.py defines check with --once and --json", check_12_cli_check_once_json),
    ("cli/config.py defines show and path with --json", check_13_cli_config_show_path),
    (
        "ENVIRONMENT_OVERRIDES covers every [monitor] and [notifications] key",
        check_14_environment_overrides,
    ),
    ("check, config, and config-path JSON schemas tracked and current", check_15_step2_schemas),
    # Step 3 — Pure notification policy, persistence, replay goldens, and notify log
    (
        "revision 0006 creates notifications, notification_deliveries, and notification_decisions",
        check_16_revision_0006,
    ),
    (
        "services/policy.py defines pure policy types, decide, and DECISION_KINDS",
        check_17_policy_definitions,
    ),
    (
        "test_architecture scans services/policy.py for banned imports and nondeterminism",
        check_18_policy_architecture_scan,
    ),
    (
        "services/notifications.py defines NotificationService, Channel, LogChannel, and replay",
        check_19_notification_service,
    ),
    (
        "two approved Irma notification goldens and build_notification_goldens --check",
        check_20_notification_goldens,
    ),
    ("cli/notify.py defines log with --limit default 20 and --json", check_21_cli_notify_log),
    ("notifications JSON schema tracked and current", check_22_notifications_schema),
    ("docs/ALERT-LADDER.md contains ## Notifications", check_23_alert_ladder_notifications),
    (
        "Step 3 policy, notification, replay, golden, and CLI tests tracked",
        check_24_step3_tests_tracked,
    ),
    # Step 4 — Windows toast channel, application identity, and notify setup|test
    (
        "pyproject.toml declares win32 winrt dependencies and desktop pytest marker",
        check_25_pyproject_winrt_and_desktop_marker,
    ),
    (
        "services/toast.py defines Weatherbot.Monitor toast channel and HKCU-only identity",
        check_26_toast_service,
    ),
    (
        "cli/notify.py defines setup (--remove, --json) and test (--json)",
        check_27_cli_notify_setup_and_test,
    ),
    ("services/doctor.py defines the toast check", check_28_doctor_toast_check),
    ("notify-setup and notify-test JSON schemas tracked and current", check_29_step4_schemas),
    ("Step 4 toast, doctor, CLI, and desktop tests tracked", check_30_step4_tests_tracked),
    (
        "ci.yml runs on ubuntu-latest and windows-latest and checks Linux types",
        check_31_ci_platforms_and_linux_toast,
    ),
    # Step 5 — Asyncio scheduler, watches, retries, degraded-data alarm, and serve/check
    (
        "services/scheduler.py defines Job and Scheduler with 60 s max sleep and on_resume",
        check_32_scheduler,
    ),
    (
        "sources/nhc_map.py defines fetch_cone_advisories and parse_cone_advisories",
        check_33_cone_advisories,
    ),
    (
        "services/schedule.py defines MonitorSchedule, watches, retries, and run_heartbeat_task",
        check_34_monitor_schedule,
    ),
    (
        "services/logs.py configures RotatingFileHandler (1 MiB, 5 backups) and pythonw stderr",
        check_35_rotating_log_handler,
    ),
    (
        "cli/serve.py defines serve with ProcessLock and clean-stop heartbeat clearing",
        check_36_cli_serve,
    ),
    (
        "cli/check.py runs scheduler without --once and refuses --json without --once",
        check_37_cli_check_loop,
    ),
    (
        "scripts/simulate_advisory.py tracked and uses simulated Miami-Dade with recorded_services",
        check_38_simulate_advisory_script,
    ),
    (
        "Step 5 scheduler, cone-advisories, schedule, log-file, serve, and simulation tests",
        check_39_step5_tests_tracked,
    ),
    # Step 6 — Windows Task Scheduler registration and fallback supervision
    (
        "services/tasks.py defines \\Weatherbot\\ tasks under System32 without shell=True",
        check_40_tasks_service,
    ),
    (
        "cli/tasks.py defines install-task and uninstall-task and cli/__init__.py registers them",
        check_41_cli_tasks_commands,
    ),
    (
        "check --if-stale and run_fallback_check with 3-min wait, restart, and fallback heartbeat",
        check_42_fallback_supervision,
    ),
    (
        "NotificationKind includes stale_monitor and deliver_database_refused_toast defined",
        check_43_stale_monitor_and_db_refused_toast,
    ),
    (
        "services/doctor.py defines tasks_check, path_check, and serve heartbeat check",
        check_44_doctor_tasks_and_path,
    ),
    ("install-task and uninstall-task JSON schemas tracked and current", check_45_step6_schemas),
    (
        "README.md documents Phase 4 commands and Status names Phase 4 complete and Phase 5 next",
        check_46_readme_phase04,
    ),
    # Step 7 — QA & Verification Script self-checks
    (
        "scripts/verify_phase04.py tracked, valid syntax, 51 static checks, and all six modes",
        check_47_verifier_self_check,
    ),
    (
        "tests/test_phase04_verification.py tracked and covers --fast, matrix, and red checks",
        check_48_verification_test_tracked,
    ),
    (
        "phase-verify.yml includes 01, 02, 03, and 04 in strategy.matrix.phase",
        check_49_matrix_includes_04,
    ),
    (
        "docs/phase04-qa-findings.md tracked with PR #40, Steps 1-7, and Pre-ship items",
        check_50_qa_findings_doc,
    ),
    (
        "ROADMAP.md Phase 4 acceptance criteria and phase04-roadmap.md Step 1-7 headers consistent",
        check_51_roadmaps_consistent,
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
    """Read per-test outcomes from a pytest JUnit XML file."""
    if not path.is_file():
        return {}
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


def package_smoke() -> Outcome:
    """Import the package, engine, monitor, policy, and toast modules."""
    try:
        with tempfile.TemporaryDirectory() as directory:
            result = capture([sys.executable, "-m", "weatherbot", "--version"], cwd=Path(directory))
        for module in (
            "weatherbot",
            "weatherbot.engine",
            "weatherbot.services.monitor",
            "weatherbot.services.policy",
            "weatherbot.services.toast",
        ):
            importlib.import_module(module)
        passed = result.returncode == 0 and bool(result.stdout.strip())
    except Exception as error:  # noqa: BLE001 - smoke failure reported as FAIL
        return report(
            Outcome("py.smoke", "package and Phase 4 module smoke", "FAIL", type(error).__name__)
        )
    return report(
        Outcome("py.smoke", "package and Phase 4 module smoke", "PASS" if passed else "FAIL")
    )


def py_suites(tmp_dir: Path | None = None) -> tuple[list[Outcome], dict[str, Status]]:
    """Run Ruff, Pyright (host + Linux), import-linter, offline pytest with coverage, and smoke."""
    heading("Python quality and offline test suites")
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
    )
    outcomes = [run_command(f"py.{key}", label, argv) for key, label, argv in commands]
    junit_dir = tmp_dir or Path(tempfile.mkdtemp(prefix="weatherbot-verify04-"))
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
    outcomes.append(package_smoke())
    return outcomes, parse_junit(junit)


def live_suite(tmp_dir: Path | None = None) -> tuple[Outcome, dict[str, Status]]:
    """Run ``pytest -m live``."""
    heading("Live service smoke tests")
    junit = (tmp_dir or Path(tempfile.mkdtemp(prefix="weatherbot-live04-"))) / "live.xml"
    outcome = run_command(
        "live.pytest",
        "pytest -m live",
        ["uv", "run", "pytest", "-m", "live", f"--junitxml={junit}"],
    )
    return outcome, parse_junit(junit)


def desktop_suite(tmp_dir: Path | None = None) -> tuple[Outcome, dict[str, Status]]:
    """Run ``pytest -m desktop`` on the operator's Windows 11 desktop."""
    heading("Desktop integration tests (toast and Task Scheduler)")
    junit = (tmp_dir or Path(tempfile.mkdtemp(prefix="weatherbot-desktop04-"))) / "desktop.xml"
    ini_override = (
        "--override-ini=addopts=-ra --strict-markers --strict-config --allow-hosts=127.0.0.1,::1"
    )
    outcome = run_command(
        "desktop.pytest",
        "pytest -m desktop",
        [
            "uv",
            "run",
            "pytest",
            "-m",
            "desktop",
            ini_override,
            f"--junitxml={junit}",
        ],
    )
    return outcome, parse_junit(junit)


def security_suites() -> list[Outcome]:
    """Run gitleaks, bandit, pip-audit, and check_personal_data."""
    heading("Security and privacy gates")
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


def ci_platforms_green() -> bool:
    """Verify ci.yml defines ubuntu-latest and windows-latest and passes on main/PR."""
    if not check_31_ci_platforms_and_linux_toast():
        return False
    if git("branch", "--show-current") == "main":
        run = latest_run("ci.yml")
        jobs = object_of(github_api(f"actions/runs/{run['id']}/jobs"))
        conclusions = {
            str(object_of(j)["name"]): object_of(j)["conclusion"] for j in array_of(jobs["jobs"])
        }
        sha_short = str(run["head_sha"])[:7]
        print(f"  ci.yml run {run['id']} at {sha_short}: conclusion={run['conclusion']}")
        return (
            run["conclusion"] == "success"
            and run["head_sha"] == git("rev-parse", "HEAD")
            and conclusions.get("test (ubuntu-latest)") == "success"
            and conclusions.get("test (windows-latest)") == "success"
        )
    result = capture(["gh", "pr", "checks", "--json", "name,bucket"])
    result.check_returncode()
    rows = [object_of(row) for row in array_of(json.loads(result.stdout))]
    by_name = {str(row["name"]): str(row["bucket"]) for row in rows}
    return (
        by_name.get("test (ubuntu-latest)") == "pass"
        and by_name.get("test (windows-latest)") == "pass"
    )


def phase_three_post() -> bool:
    """Phase 3's own ``--post`` exits 0 with all 80 checks passing; only its totals print."""
    result = capture(["uv", "run", "python", "scripts/verify_phase03.py", "--post"], timeout=9000)
    totals = dict(
        re.findall(r"^  (passed|failed|skipped|total)\s+(\d+)$", result.stdout, re.MULTILINE)
    )
    print(f"  verify_phase03.py --post: {totals or 'no summary'}; exit {result.returncode}")
    return result.returncode == 0 and totals == {
        "passed": "80",
        "failed": "0",
        "skipped": "0",
        "total": "80",
    }


def weatherbot(
    arguments: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    timeout: int = 600,
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
            parents[cast("str", ast.literal_eval(assigned(tree, "revision")))] = cast(
                "str | None", ast.literal_eval(assigned(tree, "down_revision"))
            )
    revision: str | None = head
    while revision is not None:
        if revision == ancestor:
            return True
        revision = parents.get(revision)
    return False


def doctor_db_and_alarm() -> bool:
    """V2.5: operator database at head >= 0006, fresh temp DB skip, and unknown-revision fail."""
    with tempfile.TemporaryDirectory(prefix="weatherbot-doctor04-") as directory:
        op_status, op_data = doctor([], cwd=Path(directory))
    op_db = object_of(op_data["database"])
    op_checks = {object_of(c)["name"]: object_of(c)["status"] for c in array_of(op_data["checks"])}
    print(
        f"  operator database: exit {op_status}, revision {op_db['revision']}, head {op_db['head']}"
    )
    op_ok = (
        op_db["at_head"] is True
        and op_checks.get("migrations") == "pass"
        and descends_from(str(op_db["head"]), "0006")
    )

    with tempfile.TemporaryDirectory(prefix="weatherbot-alarm04-") as directory:
        root = Path(directory)
        env = {
            "WEATHERBOT_CONFIG_DIR": str(root / "config"),
            "WEATHERBOT_DATA_DIR": str(root / "data"),
        }
        fresh_status, fresh_data = doctor(["--offline"], cwd=root, env=env)
        fresh_checks = {
            object_of(c)["name"]: object_of(c)["status"] for c in array_of(fresh_data["checks"])
        }
        fresh_ok = (
            fresh_status == 0
            and fresh_checks.get("heartbeat") == "skip"
            and fresh_checks.get("toast") == "skip"
            and fresh_checks.get("tasks") == "skip"
            and fresh_checks.get("path") == "skip"
        )
        db_file = root / "data" / "weatherbot.sqlite3"
        with sqlite3.connect(db_file) as connection:
            connection.execute("UPDATE alembic_version SET version_num = 'unknown-revision'")
        connection.close()
        stamped_status, stamped_data = doctor(["--offline"], cwd=root, env=env)
        stamped_checks = {
            object_of(c)["name"]: object_of(c)["status"] for c in array_of(stamped_data["checks"])
        }
        stamped_ok = (
            stamped_status == 1
            and stamped_checks.get("database") == "fail"
            and stamped_data["failed"] is True
        )
    print(
        f"  fresh temp DB: exit {fresh_status}; stamped DB: exit {stamped_status}, "
        f"database={stamped_checks.get('database')}"
    )
    return op_ok and fresh_ok and stamped_ok


def notification_goldens_check() -> bool:
    """V3.4: check_20_notification_goldens and build_notification_goldens.py --check."""
    result = capture(["uv", "run", "python", "scripts/build_notification_goldens.py", "--check"])
    print(f"  build_notification_goldens.py --check: exit {result.returncode}")
    return result.returncode == 0 and check_20_notification_goldens()


def simulate_advisory_probe() -> bool:
    """V5.4: scripts/simulate_advisory.py passes on the operator's machine."""
    result = capture(
        ["uv", "run", "python", "scripts/simulate_advisory.py"],
        timeout=240,
    )
    line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "no output"
    print(f"  {line} (exit {result.returncode})")
    return (
        result.returncode == 0
        and "simulated Miami-Dade" in line
        and "level=5" in line
        and "escalation=True" in line
        and "toast=delivered" in line
    )


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
    with tempfile.TemporaryDirectory(prefix="weatherbot-installed-doc-") as tmp:
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


def active_tasks_and_installed_doctor() -> bool:
    """V6.4: tasks.query() shows serve & check enabled, and installed doctor passes tasks."""
    from weatherbot.services import tasks as tasks_service  # noqa: PLC0415

    queried = tasks_service.query()
    by_name = {t.name: t for t in queried}
    if not {"serve", "check"} <= set(by_name):
        return False
    serve_task = by_name["serve"]
    check_task = by_name["check"]
    tasks_ok = (
        serve_task.enabled
        and check_task.enabled
        and serve_task.logon_type == "InteractiveToken"
        and check_task.logon_type == "InteractiveToken"
        and serve_task.run_level == "LeastPrivilege"
        and check_task.run_level == "LeastPrivilege"
        and (
            serve_task.state.lower() == "running"
            or serve_task.last_task_result in HEALTHY_SERVE_RESULTS
        )
    )
    _, data = _installed_tool_doctor()
    checks = {
        str(object_of(c)["name"]): (str(object_of(c)["status"]), str(object_of(c)["detail"]))
        for c in array_of(data["checks"])
    }
    tasks_check_status, _ = checks.get("tasks", ("fail", ""))
    path_status, path_detail = checks.get("path", ("fail", ""))
    path_ok = path_status == "pass" or (
        path_status == "fail"
        and "PATH resolves weatherbot to" in path_detail
        and contains(QA_FINDINGS, "PATH")
    )
    print(
        f"  tasks: serve={serve_task.state} (last={serve_task.last_task_result}), "
        f"check={check_task.state}; doctor tasks={tasks_check_status}, path={path_status}"
    )
    return tasks_ok and tasks_check_status == "pass" and path_ok


def active_serve_heartbeat() -> bool:
    """V6.5: installed copy's doctor --offline --json shows serve runner heartbeat fresh."""
    _, data = _installed_tool_doctor()
    heartbeats = [object_of(h) for h in array_of(data["heartbeats"])]
    serve_row = next(
        (h for h in heartbeats if h.get("kind") == "runner" and h.get("name") == "serve"),
        None,
    )
    if serve_row is None:
        return False
    checks = {
        str(object_of(c)["name"]): str(object_of(c)["status"]) for c in array_of(data["checks"])
    }
    print(
        f"  serve heartbeat: stale={serve_row.get('stale')}, "
        f"expected_every_s={serve_row.get('expected_every_s')}, "
        f"heartbeat_check={checks.get('heartbeat')}"
    )
    return (
        serve_row.get("stale") is False
        and serve_row.get("expected_every_s") is not None
        and checks.get("heartbeat") == "pass"
    )


def export_schemas_check() -> bool:
    """V7.1: export_schemas.py --check exits 0 and all 15 Phase 1-4 schemas are valid 2020-12."""
    result = capture(["uv", "run", "python", "scripts/export_schemas.py", "--check"])
    print(f"  export_schemas.py --check: exit {result.returncode}")
    return result.returncode == 0 and _schemas_valid(ALL_PHASE_04_SCHEMAS)


def fast_budget_probe() -> bool:
    """V7.4: scripts/verify_phase04.py --fast passes all 51 checks in under 30 seconds."""
    started = time.monotonic()
    result = capture(["uv", "run", "python", "scripts/verify_phase04.py", "--fast"], timeout=60)
    elapsed = time.monotonic() - started
    totals = dict(
        re.findall(r"^  (passed|failed|skipped|total)\s+(\d+)$", result.stdout, re.MULTILINE)
    )
    print(f"  verify_phase04.py --fast: {totals or 'no summary'} in {elapsed:.2f}s")
    return (
        result.returncode == 0
        and elapsed < FAST_BUDGET_SECONDS
        and totals
        == {
            "passed": "51",
            "failed": "0",
            "skipped": "0",
            "total": "51",
        }
    )


V_MATRIX: tuple[VRow, ...] = (
    # V1 — Lint, format, types, architecture, tests, and Phase 1-3 regression (4 rows)
    VRow(
        "V1.1",
        "V1 — Lint, format, types, architecture, tests, and Phase 1-3 regression",
        (
            "ruff check, ruff format --check, pyright (host + Linux), lint-imports, and "
            "test_architecture (including policy purity scan) pass"
        ),
        (
            "ruff_check",
            "ruff_format",
            "pyright",
            "pyright_linux",
            "lint_imports",
            Select("tests.test_architecture"),
        ),
    ),
    VRow(
        "V1.2",
        "V1 — Lint, format, types, architecture, tests, and Phase 1-3 regression",
        (
            "offline pytest, live pytest, and desktop pytest pass with >= 90% branch "
            "coverage on engine and policy"
        ),
        (
            "pytest",
            "pytest_live",
            "pytest_desktop",
            "coverage_policy",
            "package_smoke",
        ),
    ),
    VRow(
        "V1.3",
        "V1 — Lint, format, types, architecture, tests, and Phase 1-3 regression",
        (
            "phase-verify (01), (02), and (03) CI jobs pass at HEAD on main, and "
            "test_phase03_verification passes"
        ),
        (
            "phase_verify_ci",
            Select("tests.test_phase03_verification"),
        ),
    ),
    VRow(
        "V1.4",
        "V1 — Lint, format, types, architecture, tests, and Phase 1-3 regression",
        "scripts/verify_phase03.py --post passes all 80 checks with 0 failures and 0 skips",
        ("verify_phase03_post",),
    ),
    # V2 — Storage, migrations, concurrency, and doctor (5 rows)
    VRow(
        "V2.1",
        "V2 — Storage, migrations, concurrency, and doctor",
        (
            "twelve consecutive fetch runs deduplicate geometry_contents and stay within "
            "the 128 KiB SQLite growth budget"
        ),
        (
            Select("tests.services.test_geometry_storage"),
            Select("tests.cli.test_storage_growth"),
        ),
    ),
    VRow(
        "V2.2",
        "V2 — Storage, migrations, concurrency, and doctor",
        (
            "revisions 0001-0006 upgrade and downgrade cleanly, and upgrading a 0003 DB "
            "migrates geometry and preserves snapshots/assessments"
        ),
        (
            Select("tests.services.test_database"),
            Select("tests.services.test_tables"),
        ),
    ),
    VRow(
        "V2.3",
        "V2 — Storage, migrations, concurrency, and doctor",
        (
            "writing_session begins BEGIN IMMEDIATE with 30 s busy_timeout, concurrent "
            "status --no-fetch succeeds, and held cycle lock skips/exits 1"
        ),
        (
            Select("tests.services.test_locks"),
            Select("tests.services.test_monitor"),
            Select("tests.services.test_writing_transactions"),
            Select("tests.cli.test_check_command"),
        ),
    ),
    VRow(
        "V2.4",
        "V2 — Storage, migrations, concurrency, and doctor",
        (
            "monitor start delivers one database-free toast when open_database fails "
            "with UnknownRevisionError or MigrationFailedError"
        ),
        (Select("tests.services.test_database_refused"),),
    ),
    VRow(
        "V2.5",
        "V2 — Storage, migrations, concurrency, and doctor",
        (
            "doctor --json on the operator DB is at head descending from 0006, fresh temp "
            "DB skips machine checks, and unknown-revision DB fails"
        ),
        (
            "doctor_db_and_alarm",
            Select("tests.cli.test_doctor_heartbeat"),
            Select("tests.services.test_doctor_toast"),
            Select("tests.services.test_doctor_machine"),
        ),
    ),
    # V3 — Pure notification policy and historical replay goldens (4 rows)
    VRow(
        "V3.1",
        "V3 — Pure notification policy and historical replay goldens",
        (
            "escalations never suppress, incomplete drops hold up to max_holds=3 then "
            "send 'at least', and unconfirmed drops hold once and withdraw on rise"
        ),
        (Select("tests.services.test_policy"),),
    ),
    VRow(
        "V3.2",
        "V3 — Pure notification policy and historical replay goldens",
        (
            "keyed triggers obey cooldown_hours and quiet_hours (level <= 2 only), and "
            "each cycle emits at most one 4-line notification per location"
        ),
        (
            Select("tests.services.test_policy"),
            Select("tests.services.test_notifications"),
        ),
    ),
    VRow(
        "V3.3",
        "V3 — Pure notification policy and historical replay goldens",
        (
            "NotificationService.decide_cycle decides each new assessment once, "
            "reconstructs PolicyState from SQLite, and stores decisions/deliveries"
        ),
        (
            Select("tests.services.test_notifications"),
            Select("tests.cli.test_notify_log"),
        ),
    ),
    VRow(
        "V3.4",
        "V3 — Pure notification policy and historical replay goldens",
        (
            "two operator-approved Irma notification goldens match "
            "build_notification_goldens.py --check and test_notification_goldens"
        ),
        (
            "notification_goldens_check",
            Select("tests.services.test_notification_replay"),
            Select("tests.services.test_notification_goldens"),
        ),
    ),
    # V4 — Windows toast channel, application identity, and Linux compatibility (3 rows)
    VRow(
        "V4.1",
        "V4 — Windows toast channel, application identity, and Linux compatibility",
        (
            "notify setup writes only HKCU Weatherbot.Monitor, toast_xml escapes text "
            "and includes NOTICE, and ToastChannel maps Windows outcomes"
        ),
        (
            Select("tests.services.test_toast"),
            Select("tests.cli.test_notify_commands"),
        ),
    ),
    VRow(
        "V4.2",
        "V4 — Windows toast channel, application identity, and Linux compatibility",
        (
            "desktop toast suite passes on Windows 11: notify setup, notify test --json "
            "(delivered), and doctor --offline --json toast check"
        ),
        (Select("tests.desktop.test_toast_desktop"),),
    ),
    VRow(
        "V4.3",
        "V4 — Windows toast channel, application identity, and Linux compatibility",
        (
            "weatherbot.services.toast imports cleanly on Linux without winrt, pyright "
            "--pythonplatform Linux passes, and ci.yml passes on both OSes"
        ),
        (
            "pyright_linux",
            "ci_matrix_platforms",
            Select("tests.services.test_toast"),
        ),
    ),
    # V5 — Scheduler, watches, retries, degraded-data alarm, and simulated advisory (4 rows)
    VRow(
        "V5.1",
        "V5 — Scheduler, watches, retries, degraded-data alarm, and simulated advisory",
        (
            "Scheduler runs one job at a time on injected clock/sleep/random, sleeps "
            "<= 60 s, isolates errors, and runs on_resume after > 60 s wake gaps"
        ),
        (Select("tests.services.test_scheduler"),),
    ),
    VRow(
        "V5.2",
        "V5 — Scheduler, watches, retries, degraded-data alarm, and simulated advisory",
        (
            "MonitorSchedule runs advisory-window, roster, and NWS alert watches, "
            "confirmation cycles, and bounded exponential retries (5, 10, 20 min)"
        ),
        (
            Select("tests.sources.test_cone_advisories"),
            Select("tests.services.test_schedule"),
        ),
    ),
    VRow(
        "V5.3",
        "V5 — Scheduler, watches, retries, degraded-data alarm, and simulated advisory",
        (
            "degraded and recovered alarms, runner heartbeat task and clean-stop "
            "clearing, and 1 MiB rotating weatherbot.log (pythonw-safe)"
        ),
        (
            Select("tests.services.test_schedule"),
            Select("tests.services.test_log_file"),
            Select("tests.cli.test_serve_command"),
        ),
    ),
    VRow(
        "V5.4",
        "V5 — Scheduler, watches, retries, degraded-data alarm, and simulated advisory",
        (
            "scripts/simulate_advisory.py and test_simulate_advisory store a level-5 "
            "escalation for simulated Miami-Dade with toast delivered in <= 1 interval"
        ),
        (
            "simulate_advisory_probe",
            Select("tests.scripts.test_simulate_advisory"),
        ),
    ),
    # V6 — Windows Task Scheduler, fallback supervision, and active machine verification (5 rows)
    VRow(
        "V6.1",
        "V6 — Windows Task Scheduler, fallback supervision, and active machine verification",
        (
            "task_xml renders valid UTF-16 XML for serve and check (pythonw, "
            "InteractiveToken, LeastPrivilege), install-task refuses checkout, "
            "uninstall-task cleans up"
        ),
        (
            Select("tests.services.test_tasks"),
            Select("tests.cli.test_task_commands"),
        ),
    ),
    VRow(
        "V6.2",
        "V6 — Windows Task Scheduler, fallback supervision, and active machine verification",
        (
            "check --once --if-stale skips when fresh, waits 3 min on held stale lock, "
            "restarts serve when not running, and serve watches fallback heartbeat"
        ),
        (
            Select("tests.services.test_fallback"),
            Select("tests.cli.test_check_command"),
        ),
    ),
    VRow(
        "V6.3",
        "V6 — Windows Task Scheduler, fallback supervision, and active machine verification",
        (
            "desktop Task Scheduler suite registers, queries, and deletes "
            "\\Weatherbot\\_verify_probe without disturbing serve or check"
        ),
        (Select("tests.desktop.test_tasks_desktop"),),
    ),
    VRow(
        "V6.4",
        "V6 — Windows Task Scheduler, fallback supervision, and active machine verification",
        (
            "operator's \\Weatherbot\\serve and \\Weatherbot\\check are enabled with "
            "InteractiveToken/LeastPrivilege, and installed doctor passes tasks"
        ),
        ("active_tasks_and_installed_doctor",),
    ),
    VRow(
        "V6.5",
        "V6 — Windows Task Scheduler, fallback supervision, and active machine verification",
        (
            "installed copy's doctor --offline --json on the default data directory "
            "shows the serve runner heartbeat row present and fresh"
        ),
        ("active_serve_heartbeat",),
    ),
    # V7 — CLI JSON contracts, privacy, and security gates (4 rows)
    VRow(
        "V7.1",
        "V7 — CLI JSON contracts, privacy, and security gates",
        (
            "export_schemas.py --check exits 0, all 15 schemas under docs/schema/ are "
            "valid 2020-12, and every CLI --json output validates"
        ),
        (
            "export_schemas_check",
            Select("tests.cli.test_documents"),
        ),
    ),
    VRow(
        "V7.2",
        "V7 — CLI JSON contracts, privacy, and security gates",
        (
            "only locations list prints coordinates, logs and doctor details hold no "
            "coordinates or notification text, and check_personal_data passes"
        ),
        (
            "personal_data_all",
            "personal_data_self_test",
            Select("tests.cli.test_cli_privacy"),
            Select("tests.models.test_privacy"),
        ),
    ),
    VRow(
        "V7.3",
        "V7 — CLI JSON contracts, privacy, and security gates",
        "gitleaks, bandit, and audit_deps.py exit 0",
        (
            "gitleaks",
            "bandit",
            "audit_deps",
        ),
    ),
    VRow(
        "V7.4",
        "V7 — CLI JSON contracts, privacy, and security gates",
        (
            "scripts/verify_phase04.py --fast passes all 51 static checks in under "
            "30 seconds, and test_phase04_verification passes"
        ),
        (
            "verify_phase04_fast_budget",
            Select("tests.test_phase04_verification"),
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
    matched = {
        name: outcome
        for name, outcome in suite.tests.items()
        if any(name == p or name.startswith(p + ".") for p in item.prefixes)
    }
    if not matched:
        return "FAIL", f"no tests matched {','.join(item.prefixes)}"
    failed = [name for name, outcome in matched.items() if outcome == "FAIL"]
    if failed:
        return "FAIL", f"{len(failed)} failed in {','.join(item.prefixes)}"
    skipped = [name for name, outcome in matched.items() if outcome == "SKIP"]
    if skipped:
        return "SKIP", f"{len(skipped)} skipped in {','.join(item.prefixes)}"
    return "PASS", f"{len(matched)} tests"


def post_matrix(suite: Suite) -> list[Outcome]:
    """Evaluate all 29 rows of the V1-V7 post-implementation verification matrix."""
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
    """Run static checks, all suites, probes, and evaluate the 29-row V1-V7 matrix."""
    print(
        "Notice: --post runs the desktop suite and scripts/simulate_advisory.py, which each "
        "show one Windows toast notification, and tests/desktop/test_tasks_desktop.py "
        "registers and deletes one disabled probe task (\\Weatherbot\\_verify_probe).",
        flush=True,
    )
    static_outcomes = run_static_checks()
    suite = Suite()
    with tempfile.TemporaryDirectory(prefix="weatherbot-post04-") as tmp:
        tmp_path = Path(tmp)
        py_outcomes, py_tests = py_suites(tmp_path)
        for out in py_outcomes:
            suite.commands[out.item_id.removeprefix("py.")] = out.status
        suite.commands["package_smoke"] = suite.commands.get("smoke", "FAIL")
        suite.tests.update(py_tests)

        live_out, live_tests = live_suite(tmp_path)
        suite.commands["pytest_live"] = live_out.status
        suite.tests.update(live_tests)

        desktop_out, desktop_tests = desktop_suite(tmp_path)
        suite.commands["pytest_desktop"] = desktop_out.status
        suite.tests.update(desktop_tests)

    sec_outcomes = security_suites()
    sec_map = {
        "sec.secrets": "gitleaks",
        "sec.sast": "bandit",
        "sec.audit": "audit_deps",
        "sec.all": "personal_data_all",
        "sec.self-test": "personal_data_self_test",
    }
    for out in sec_outcomes:
        if out.item_id in sec_map:
            suite.commands[sec_map[out.item_id]] = out.status

    heading("Post-implementation probes")
    run_probe(
        "phase_verify_ci",
        "phase-verify (01), (02), and (03) CI checks",
        lambda: phase_entries_green(("01", "02", "03")),
        suite,
    )
    run_probe(
        "ci_matrix_platforms",
        "ci.yml ubuntu-latest and windows-latest checks",
        ci_platforms_green,
        suite,
    )
    run_probe("verify_phase03_post", "verify_phase03.py --post", phase_three_post, suite)
    run_probe(
        "doctor_db_and_alarm", "operator DB head + doctor alarm proof", doctor_db_and_alarm, suite
    )
    run_probe(
        "notification_goldens_check",
        "build_notification_goldens.py --check",
        notification_goldens_check,
        suite,
    )
    run_probe(
        "simulate_advisory_probe",
        "scripts/simulate_advisory.py",
        simulate_advisory_probe,
        suite,
    )
    run_probe(
        "active_tasks_and_installed_doctor",
        "active \\Weatherbot\\ tasks and installed doctor",
        active_tasks_and_installed_doctor,
        suite,
    )
    run_probe(
        "active_serve_heartbeat",
        "active serve runner heartbeat on default data directory",
        active_serve_heartbeat,
        suite,
    )
    run_probe(
        "export_schemas_check", "scripts/export_schemas.py --check", export_schemas_check, suite
    )
    run_probe(
        "verify_phase04_fast_budget",
        "scripts/verify_phase04.py --fast (< 30 s)",
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
    group.add_argument(
        "--fast", action="store_true", help="Run the 51 static checks only (default)."
    )
    group.add_argument(
        "--py", action="store_true", help="Run static checks and Python quality/test suites."
    )
    group.add_argument(
        "--live", action="store_true", help="Run static checks and live smoke tests."
    )
    group.add_argument(
        "--security", action="store_true", help="Run static checks and security/privacy gates."
    )
    group.add_argument("--all", action="store_true", help="Run --py, --live, and --security.")
    group.add_argument(
        "--post", action="store_true", help="Run the full 80-check Phase 4 verification."
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for Phase 4 verification."""
    args = parse_args(argv)
    if args.post:
        return summarize(run_post())
    outcomes = run_static_checks()
    if args.py or args.all:
        py_outcomes, _ = py_suites()
        outcomes.extend(py_outcomes)
    if args.live or args.all:
        live_outcome, _ = live_suite()
        outcomes.append(live_outcome)
    if args.security or args.all:
        outcomes.extend(security_suites())
    return summarize(outcomes)


if __name__ == "__main__":
    raise SystemExit(main())
