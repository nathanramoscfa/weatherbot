# scripts/verify_phase06.py
"""Verify Phase 6 (Claude layer) against docs/roadmap/phase06-roadmap.md.

Modes (mutually exclusive; no flag runs ``--fast`` and ``--py``):
  --fast      51 static file, AST, OpenAPI, fixture, and workflow checks (< 30 s, no network).
  --py        Ruff, Pyright (host + Linux), import-linter, offline pytest with >=90%
              branch coverage on engine, policy, AI context, and AI validate, schema/OpenAPI/
              fixture checks, and wheel smoke.
  --node      Frontend npm ci, audit signatures, api:check, lint, typecheck, Vitest,
              build, and licenses:check.
  --ui        Playwright Chromium browser smoke (dashboard, map, screens, and ai specs).
  --live      Live source, monitor, and web SSE pytest suite (``pytest -m live``; no AI).
  --ai        Live AI evaluation (``scripts/eval_ai.py --live``; spends ~$0.40, never in CI).
  --security  Secret, SAST, dependency, personal-data, npm audit, ESLint, and key-shape scans.
  --all       --py + --node + --ui + --live + --security (all except --ai and --post).
  --post      Full V1-V7 post-implementation matrix (28 rows, 79 checks total).
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
PHASE_5_TAG: Final = "v2.0.0-phase-5"
PHASE_6_TAG: Final = "v2.0.0-phase-6"
CI_WORKFLOW: Final = ".github/workflows/ci.yml"
PHASE_WORKFLOW: Final = ".github/workflows/phase-verify.yml"
PRE_COMMIT_CONFIG: Final = ".pre-commit-config.yaml"
ROADMAP: Final = "docs/roadmap/ROADMAP.md"
PHASE_ROADMAP: Final = "docs/roadmap/phase06-roadmap.md"
QA_FINDINGS: Final = "docs/phase06-qa-findings.md"
AI_DOC: Final = "docs/AI.md"
OPENAPI_SPEC: Final = "docs/api/openapi.json"
SERVICES: Final = "src/weatherbot/services"
AI_SERVICES: Final = f"{SERVICES}/ai"
WEB: Final = "src/weatherbot/web"
CLI: Final = "src/weatherbot/cli"
VERSIONS: Final = f"{SERVICES}/persistence/migrations/versions"
FRONTEND: Final = "frontend"
AI_FIXTURES_DIR: Final = "tests/fixtures/ai"
AI_FIXTURES_MANIFEST: Final = f"{AI_FIXTURES_DIR}/manifest.json"
AI_FIXTURES_BUDGET_BYTES: Final = 1_048_576
MODES: Final = (
    "--fast",
    "--py",
    "--node",
    "--ui",
    "--live",
    "--ai",
    "--security",
    "--all",
    "--post",
)
FAST_BUDGET_SECONDS: Final = 30.0
EXPECTED_STATIC_CHECKS: Final = 51
EXPECTED_POST_ROWS: Final = 28
EXPECTED_V_DISTRIBUTION: Final = (5, 4, 3, 4, 3, 5, 4)

AI_SETTINGS_FIELDS: Final = frozenset(
    {
        "enabled",
        "model",
        "summary_model",
        "daily_cap_usd",
        "change_summaries",
        "outlook_narration",
    }
)
AI_ENV_OVERRIDES: Final[dict[tuple[str, str], str]] = {
    ("ai", "enabled"): "WEATHERBOT_AI_ENABLED",
    ("ai", "model"): "WEATHERBOT_AI_MODEL",
    ("ai", "summary_model"): "WEATHERBOT_AI_SUMMARY_MODEL",
    ("ai", "daily_cap_usd"): "WEATHERBOT_AI_DAILY_CAP_USD",
    ("ai", "change_summaries"): "WEATHERBOT_AI_CHANGE_SUMMARIES",
    ("ai", "outlook_narration"): "WEATHERBOT_AI_OUTLOOK_NARRATION",
}
PRICED_MODELS: Final = frozenset(
    {
        "claude-sonnet-5-5",
        "claude-haiku-5-5",
        "claude-opus-5-5",
    }
)
EXPECTED_TOOL_NAMES: Final = (
    "list_locations",
    "get_assessment",
    "get_evidence",
    "get_alerts",
    "get_storms",
    "get_storm",
    "get_outlook",
    "get_ladder",
    "get_history",
)
AI_OPENAPI_PATHS: Final = (
    "/api/ai",
    "/api/ai/calls",
    "/api/ai/briefings",
    "/api/ai/summaries",
    "/api/ai/narrations",
    "/api/ai/chat",
    "/api/ai/pause",
    "/api/ai/allowance",
    "/api/outlook",
    "/api/outlook/{basin}/{horizon}",
)
AI_STREAM_MODELS: Final = (
    "BriefingStreamEvent",
    "ChatStreamEvent",
    "NarrationStreamEvent",
)
STEP_4_AI_FIXTURES: Final = (
    "ai.json",
    "ai-calls.json",
    "briefings.json",
    "summaries.json",
    "narrations.json",
    "outlook.json",
)
FORBIDDEN_ASYNC_ROUTE_NAMES: Final = frozenset(
    {
        "AssessmentRepository",
        "CycleRepository",
        "HeartbeatRepository",
        "LocationRepository",
        "SnapshotRepository",
        "OutputRepository",
        "Ledger",
        "ai_engine",
        "Session",
        "writing_session",
    }
)
PHASE_6_KEY_SCAN_PREFIXES: Final = (
    AI_SERVICES,
    WEB,
    CLI,
    f"{FRONTEND}/src",
    "tests/ai",
    AI_FIXTURES_DIR,
    AI_DOC,
)
KEY_PREFIX: Final = "sk" + "-" + "ant" + "-"

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
    """One row of the Phase 6 V1-V7 post-implementation verification matrix."""

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
    return defines_in(syntax(relative, root=root), *names)


def defines_in(tree: ast.Module, *names: str) -> bool:
    """Whether top-level statements in a parsed module define every name."""
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


def imported_roots(tree: ast.AST) -> set[str]:
    """Return top-level module names imported anywhere in ``tree``."""
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.add(node.module.split(".", 1)[0])
    return roots


def imported_modules(tree: ast.AST) -> set[str]:
    """Return full module names imported anywhere in ``tree``."""
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def phase_matrix(root: Path = REPO_ROOT) -> set[str]:
    """Read the flow-list ``phase`` matrix entries from ``.github/workflows/phase-verify.yml``."""
    text = read(PHASE_WORKFLOW, root=root)
    match = re.search(r"^\s*phase:\s*\[([^\]]+)\]", text, re.MULTILINE)
    if match is None:
        return set()
    return {item.strip().strip("\"'") for item in match[1].split(",") if item.strip()}


def _frozen_hashes(root: Path = REPO_ROOT) -> dict[str, str]:
    """Read ``FROZEN`` migration SHA-256 map from ``tests/services/test_database.py``."""
    tree = syntax("tests/services/test_database.py", root=root)
    return cast("dict[str, str]", ast.literal_eval(assigned(tree, "FROZEN")))


def _lf_sha256(relative: str, root: Path = REPO_ROOT) -> str:
    """Compute the LF-normalized SHA-256 hex digest of ``relative``."""
    return hashlib.sha256(read(relative, root=root).encode("utf-8")).hexdigest()


# Step 1 static checks (1-12) ---------------------------------------------------------------


def check_01_ai_dependencies(root: Path = REPO_ROOT) -> bool:
    """Check 1: pyproject.toml lists anthropic>=2.3.0 in dependencies and httpx2 only in dev."""
    deps = [str(item) for item in array_of(config("project", "dependencies", root=root))]
    dev_deps = [str(item) for item in array_of(config("dependency-groups", "dev", root=root))]
    plan_deps = [str(item) for item in array_of(config("dependency-groups", "planning", root=root))]
    return (
        "anthropic>=2.3.0" in deps
        and not any(dep.startswith("httpx2") for dep in deps)
        and any(dep.startswith("httpx2>=") for dep in dev_deps)
        and not any(dep.startswith("httpx2") for dep in plan_deps)
    )


def check_02_ai_import_contracts(root: Path = REPO_ROOT) -> bool:
    """Check 2: pyproject.toml has the two forbidden AI import-linter contracts."""
    contracts = [
        object_of(item) for item in array_of(config("tool", "importlinter", "contracts", root=root))
    ]
    by_name = {str(c.get("name", "")): c for c in contracts}
    only_ai = by_name.get("Only the AI service talks to Anthropic")
    never_fetches = by_name.get("The AI service never fetches or writes the official records")
    if only_ai is None or never_fetches is None:
        return False
    return (
        only_ai.get("type") == "forbidden"
        and array_of(only_ai.get("source_modules", []))
        == [
            "weatherbot.models",
            "weatherbot.sources",
            "weatherbot.engine",
            "weatherbot.web",
            "weatherbot.cli",
        ]
        and array_of(only_ai.get("forbidden_modules", [])) == ["anthropic", "httpx2"]
        and never_fetches.get("type") == "forbidden"
        and array_of(never_fetches.get("source_modules", [])) == ["weatherbot.services.ai"]
        and array_of(never_fetches.get("forbidden_modules", []))
        == [
            "weatherbot.sources",
            "httpx",
            "weatherbot.services.monitor",
            "weatherbot.services.schedule",
            "weatherbot.services.scheduler",
            "weatherbot.services.snapshots",
            "weatherbot.services.assessments",
            "weatherbot.services.locations",
            "weatherbot.services.notifications",
            "weatherbot.services.network",
        ]
    )


def check_03_ai_settings(root: Path = REPO_ROOT) -> bool:
    """Check 3: services/config.py defines AiSettings (6 fields) and 6 WEATHERBOT_AI_* overrides."""
    rel = f"{SERVICES}/config.py"
    if not files_exist(rel, root=root) or not defines(
        rel, "AiSettings", "ENVIRONMENT_OVERRIDES", root=root
    ):
        return False
    fields = class_fields(rel, "AiSettings", root=root)
    overrides = cast(
        "dict[tuple[str, str], str]",
        ast.literal_eval(assigned(syntax(rel, root=root), "ENVIRONMENT_OVERRIDES")),
    )
    ai_overrides = {k: v for k, v in overrides.items() if k[0] == "ai"}
    return fields == set(AI_SETTINGS_FIELDS) and ai_overrides == AI_ENV_OVERRIDES


def check_04_ai_pricing(root: Path = REPO_ROOT) -> bool:
    """Check 4: services/ai/pricing.py defines PRICES, PRICES_AS_OF, MAX_PROMPT_TOKENS, no SDK."""
    rel = f"{AI_SERVICES}/pricing.py"
    if not files_exist(rel, root=root) or not defines(
        rel,
        "PRICES",
        "PRICES_AS_OF",
        "MAX_PROMPT_TOKENS",
        "cost_micro_usd",
        "ceiling_micro_usd",
        root=root,
    ):
        return False
    tree = syntax(rel, root=root)
    prices_node = assigned(tree, "PRICES")
    if not isinstance(prices_node, ast.Dict):
        return False
    keys = {
        k.value
        for k in prices_node.keys
        if isinstance(k, ast.Constant) and isinstance(k.value, str)
    }
    return (
        keys == set(PRICED_MODELS)
        and ast.literal_eval(assigned(tree, "PRICES_AS_OF")) == "2026-10-30"
        and ast.literal_eval(assigned(tree, "MAX_PROMPT_TOKENS")) == 100_000  # noqa: PLR2004
        and imported_roots(tree).isdisjoint({"anthropic", "httpx2", "httpx"})
    )


def check_05_ai_guard(root: Path = REPO_ROOT) -> bool:
    """Check 5: services/ai/guard.py defines AI_TABLES={'ai_calls','ai_outputs'} and authorizer."""
    rel = f"{AI_SERVICES}/guard.py"
    if not files_exist(rel, root=root) or not defines(rel, "AI_TABLES", "ai_engine", root=root):
        return False
    tree = syntax(rel, root=root)
    tables = set(literal_strings(assigned(tree, "AI_TABLES")))
    calls_authorizer = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "set_authorizer"
        for node in ast.walk(tree)
    )
    return tables == {"ai_calls", "ai_outputs"} and calls_authorizer


def check_06_ai_ledger(root: Path = REPO_ROOT) -> bool:
    """Check 6: services/ai/ledger.py defines Ledger with reserve/settle/today + writing_session."""
    rel = f"{AI_SERVICES}/ledger.py"
    if not files_exist(rel, root=root) or not defines(rel, "Ledger", root=root):
        return False
    methods = class_methods(rel, "Ledger", root=root)
    tree = syntax(rel, root=root)
    calls_writing_session = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "writing_session"
        for node in ast.walk(tree)
    )
    return {"reserve", "settle", "today", "allow", "pause", "resume"} <= methods and (
        calls_writing_session
    )


def check_07_migration_0007(root: Path = REPO_ROOT) -> bool:
    """Check 7: 0007_ai_calls.py creates ai_calls with down_revision 0006 and FROZEN pins it."""
    rel = f"{VERSIONS}/0007_ai_calls.py"
    if not files_exist(rel, "tests/services/test_database.py", root=root):
        return False
    tree = syntax(rel, root=root)
    frozen = _frozen_hashes(root=root)
    return (
        ast.literal_eval(assigned(tree, "revision")) == "0007"
        and ast.literal_eval(assigned(tree, "down_revision")) == "0006"
        and contains(rel, '"ai_calls"', root=root)
        and frozen.get("0007_ai_calls.py") == _lf_sha256(rel, root=root)
    )


def check_08_runtime_and_conftest_ai(root: Path = REPO_ROOT) -> bool:
    """Check 8: Runtime defines make_claude; tests/conftest.py clears ANTHROPIC_ and sets dir."""
    runtime_rel = f"{CLI}/runtime.py"
    conftest_rel = "tests/conftest.py"
    if not files_exist(runtime_rel, conftest_rel, root=root):
        return False
    return (
        "make_claude" in class_fields(runtime_rel, "Runtime", root=root)
        and "ai_service" in class_methods(runtime_rel, "Context", root=root)
        and contains(conftest_rel, '"ANTHROPIC_"', '"ANTHROPIC_CONFIG_DIR"', root=root)
    )


def check_09_doctor_and_health_ai(root: Path = REPO_ROOT) -> bool:
    """Check 9: services/doctor.py calls Check('ai', ...) in AST and HealthResponse has ai."""
    doc_rel = f"{SERVICES}/doctor.py"
    schemas_rel = f"{WEB}/schemas.py"
    if not files_exist(doc_rel, schemas_rel, root=root) or not defines(
        doc_rel, "ai_check", root=root
    ):
        return False
    tree = syntax(doc_rel, root=root)
    calls_check_ai = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Check"
        and bool(node.args)
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "ai"
        for node in ast.walk(tree)
    )
    return calls_check_ai and "ai" in class_fields(schemas_rel, "HealthResponse", root=root)


def check_10_logs_redaction_and_silent_libs(root: Path = REPO_ROOT) -> bool:
    """Check 10: services/logs.py silences anthropic/httpx2/httpcore2 and defines redaction."""
    rel = f"{SERVICES}/logs.py"
    if not files_exist(rel, root=root) or not defines(
        rel, "SILENT_LIBRARIES", "SecretFilter", "redact_secrets", root=root
    ):
        return False
    tree = syntax(rel, root=root)
    silent = tuple(cast("tuple[str, ...]", ast.literal_eval(assigned(tree, "SILENT_LIBRARIES"))))
    return silent == ("anthropic", "httpx2", "httpcore2")


def _module_level_sdk_imports(tree: ast.Module) -> set[str]:
    roots: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.add(node.module.split(".", 1)[0])
    return roots & {"anthropic", "httpx2"}


def check_11_no_sdk_import_outside_ai(root: Path = REPO_ROOT) -> bool:
    """Check 11: no package module outside services/ai/ imports anthropic or httpx2."""
    py_files = [p for p in tracked("src/weatherbot", root=root) if p.endswith(".py")]
    if not py_files:
        return False
    allowed_top_level = {f"{AI_SERVICES}/client.py", f"{AI_SERVICES}/caller.py"}
    for rel in py_files:
        tree = syntax(rel, root=root)
        if not rel.startswith(f"{AI_SERVICES}/"):
            if not imported_roots(tree).isdisjoint({"anthropic", "httpx2"}):
                return False
        elif rel not in allowed_top_level and _module_level_sdk_imports(tree):
            return False
    return True


def check_12_step1_tests_and_manifest(root: Path = REPO_ROOT) -> bool:
    """Check 12: Step 1 tests, record_ai_fixtures.py, and manifest.json tracked."""
    return files_exist(
        "scripts/record_ai_fixtures.py",
        AI_FIXTURES_MANIFEST,
        "tests/ai/ai_support.py",
        "tests/ai/test_ai_settings.py",
        "tests/ai/test_ai_pricing.py",
        "tests/ai/test_ai_guard.py",
        "tests/ai/test_ai_ledger.py",
        "tests/ai/test_ai_caller.py",
        "tests/ai/test_ai_client.py",
        "tests/ai/test_ai_imports.py",
        "tests/ai/test_ai_redaction.py",
        "tests/ai/test_ai_fixtures.py",
        "tests/services/test_doctor_ai.py",
        "tests/web/test_api_health_ai.py",
        root=root,
    )


# Step 2 static checks (13-21) --------------------------------------------------------------


def check_13_prompts_no_season_data(root: Path = REPO_ROOT) -> bool:
    """Check 13: services/ai/prompts.py defines system_prompt/prompt_version and no year/storm."""
    rel = f"{AI_SERVICES}/prompts.py"
    if not files_exist(rel, root=root) or not defines(
        rel, "system_prompt", "prompt_version", root=root
    ):
        return False
    tree = syntax(rel, root=root)
    strings = "\n".join(literal_strings(tree))
    storm_names = ("Dorian", "Ian", "Irma", "Lane", "Maria", "Michael", "Otis", "Simon")
    has_year = bool(re.search(r"\b(?:19|20)\d{2}\b", strings))
    has_storm = any(
        re.search(rf"\b{re.escape(name)}\b", strings, re.IGNORECASE) for name in storm_names
    )
    return not has_year and not has_storm


def _is_allowed_pure_import(module: str, allowed_exact: set[str]) -> bool:
    """Return True when ``module`` is in ``sys.stdlib_module_names`` or ``allowed_exact``."""
    return module in allowed_exact or module.split(".", 1)[0] in sys.stdlib_module_names


def check_14_context_and_validate_pure_imports(root: Path = REPO_ROOT) -> bool:
    """Check 14: context.py and validate.py import only models, stdlib, pydantic, and AI schemas."""
    ctx_rel = f"{AI_SERVICES}/context.py"
    val_rel = f"{AI_SERVICES}/validate.py"
    if not files_exist(ctx_rel, val_rel, root=root):
        return False
    base_allowed = {
        "pydantic",
        "weatherbot.models",
        "weatherbot.services.ai.schemas",
    }
    ctx_mods = imported_modules(syntax(ctx_rel, root=root))
    val_mods = imported_modules(syntax(val_rel, root=root))
    val_allowed = base_allowed | {"weatherbot.services.ai.context"}
    return all(_is_allowed_pure_import(m, base_allowed) for m in ctx_mods) and all(
        _is_allowed_pure_import(m, val_allowed) for m in val_mods
    )


def check_15_ai_schemas_fields_no_level(root: Path = REPO_ROOT) -> bool:
    """Check 15: Briefing has the 5 section fields and no AI schema declares a field named level."""
    rel = f"{AI_SERVICES}/schemas.py"
    if not files_exist(rel, root=root) or not defines(
        rel, "Briefing", "ChangeSummary", "OutlookNarration", root=root
    ):
        return False
    briefing_fields = class_fields(rel, "Briefing", root=root)
    if briefing_fields != {"situation", "what_it_means_here", "timeline", "actions", "sources"}:
        return False
    tree = syntax(rel, root=root)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and "level" in class_fields(rel, node.name, root=root):
            return False
    return True


def check_16_migration_0008(root: Path = REPO_ROOT) -> bool:
    """Check 16: 0008_ai_outputs.py creates ai_outputs with down_revision 0007 and FROZEN pins."""
    rel = f"{VERSIONS}/0008_ai_outputs.py"
    if not files_exist(rel, "tests/services/test_database.py", root=root):
        return False
    tree = syntax(rel, root=root)
    frozen = _frozen_hashes(root=root)
    return (
        ast.literal_eval(assigned(tree, "revision")) == "0008"
        and ast.literal_eval(assigned(tree, "down_revision")) == "0007"
        and contains(rel, '"ai_outputs"', root=root)
        and frozen.get("0008_ai_outputs.py") == _lf_sha256(rel, root=root)
    )


def _documents_keys(root: Path = REPO_ROOT) -> set[str]:
    tree = syntax(f"{CLI}/documents.py", root=root)
    docs_node = assigned(tree, "DOCUMENTS")
    if not isinstance(docs_node, ast.Dict):
        return set()
    return {
        k.value for k in docs_node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)
    }


def check_17_cli_brief_and_schema(root: Path = REPO_ROOT) -> bool:
    """Check 17: cli/__init__.py registers brief and brief.schema.json is in DOCUMENTS."""
    init_rel = f"{CLI}/__init__.py"
    brief_rel = f"{CLI}/brief.py"
    schema_rel = "docs/schema/brief.schema.json"
    if not files_exist(init_rel, brief_rel, schema_rel, f"{CLI}/documents.py", root=root):
        return False
    return contains(init_rel, 'app.command("brief")', root=root) and "brief" in _documents_keys(
        root=root
    )


def check_18_eval_cases_and_script(root: Path = REPO_ROOT) -> bool:
    """Check 18: tests/ai/eval/ is tracked with its cases and scripts/eval_ai.py offers --live."""
    return files_exist(
        "tests/ai/eval/cases.py",
        "tests/ai/eval/grading.py",
        "scripts/eval_ai.py",
        root=root,
    ) and contains("scripts/eval_ai.py", '"--live"', root=root)


def check_19_ai_fixtures_budget_and_headers(root: Path = REPO_ROOT) -> bool:
    """Check 19: tests/fixtures/ai/ stays <= 1 MiB, manifest lists all files, no auth headers."""
    if not files_exist(AI_FIXTURES_MANIFEST, root=root):
        return False
    raw_manifest = json.loads(read(AI_FIXTURES_MANIFEST, root=root))
    recordings = [object_of(item) for item in array_of(raw_manifest)]
    manifest_files = {
        f"{item.get('case', '')}.sse"
        if item.get("kind") == "stream"
        else f"{item.get('case', '')}.json"
        for item in recordings
    }
    tracked_fixtures = {
        Path(p).name for p in tracked(AI_FIXTURES_DIR, root=root) if p != AI_FIXTURES_MANIFEST
    }
    if not manifest_files or manifest_files != tracked_fixtures:
        return False
    total_bytes = 0
    forbidden_headers = ("authorization", "x-api-key", "anthropic-organization-id")
    for path in tracked(AI_FIXTURES_DIR, root=root):
        raw = read(path, root=root)
        total_bytes += len(raw.encode("utf-8"))
        lowered = raw.lower()
        if any(h in lowered for h in forbidden_headers) or KEY_PREFIX in raw:
            return False
    return total_bytes <= AI_FIXTURES_BUDGET_BYTES


def check_20_ai_doc_sections(root: Path = REPO_ROOT) -> bool:
    """Check 20: docs/AI.md holds 'What leaves the machine', 'The cap', and 'Measured cost'."""
    return files_exist(AI_DOC, root=root) and contains(
        AI_DOC,
        "## What leaves the machine",
        "## The ledger and the daily cap",
        "### Measured cost",
        root=root,
    )


def check_21_step2_tests_tracked(root: Path = REPO_ROOT) -> bool:
    """Check 21: Step 2 tests are tracked, tests/ai/test_ai_eval.py among them."""
    return files_exist(
        "tests/ai/test_ai_prompts.py",
        "tests/ai/test_ai_context.py",
        "tests/ai/test_ai_validators.py",
        "tests/ai/test_ai_outputs.py",
        "tests/ai/test_ai_briefing.py",
        "tests/ai/test_ai_summaries.py",
        "tests/ai/test_ai_eval.py",
        "tests/cli/test_brief_command.py",
        root=root,
    )


# Step 3 static checks (22-27) --------------------------------------------------------------


def check_22_tool_names_exact(root: Path = REPO_ROOT) -> bool:
    """Check 22: services/ai/tools.py's TOOL_NAMES is the exact 9-tool tuple."""
    rel = f"{AI_SERVICES}/tools.py"
    if not files_exist(rel, root=root) or not defines(rel, "TOOL_NAMES", root=root):
        return False
    names = tuple(
        cast("tuple[str, ...]", ast.literal_eval(assigned(syntax(rel, root=root), "TOOL_NAMES")))
    )
    return names == EXPECTED_TOOL_NAMES


def _is_strict_tool_def(elt: ast.expr) -> bool:
    if not isinstance(elt, ast.Dict):
        return False
    top = {
        k.value: v
        for k, v in zip(elt.keys, elt.values, strict=True)
        if isinstance(k, ast.Constant) and isinstance(k.value, str)
    }
    strict_node = top.get("strict")
    schema_node = top.get("input_schema")
    if not (
        isinstance(strict_node, ast.Constant)
        and strict_node.value is True
        and isinstance(schema_node, ast.Dict)
    ):
        return False
    schema_map = {
        k.value: v
        for k, v in zip(schema_node.keys, schema_node.values, strict=True)
        if isinstance(k, ast.Constant) and isinstance(k.value, str)
    }
    add_props = schema_map.get("additionalProperties")
    return isinstance(add_props, ast.Constant) and add_props.value is False


def check_23_tool_definitions_strict(root: Path = REPO_ROOT) -> bool:
    """Check 23: every tool in tools.py sets strict=True and additionalProperties=False."""
    rel = f"{AI_SERVICES}/tools.py"
    if not files_exist(rel, root=root) or not defines(rel, "TOOL_DEFINITIONS", root=root):
        return False
    defs_node = assigned(syntax(rel, root=root), "TOOL_DEFINITIONS")
    return (
        isinstance(defs_node, ast.Tuple)
        and len(defs_node.elts) == len(EXPECTED_TOOL_NAMES)
        and all(_is_strict_tool_def(elt) for elt in defs_node.elts)
    )


def check_24_chat_service_and_bounds(root: Path = REPO_ROOT) -> bool:
    """Check 24: services/ai/chat.py defines ChatService, MAX_TOOL_ROUNDS=6, MAX_CONVERSATIONS=8."""
    rel = f"{AI_SERVICES}/chat.py"
    if not files_exist(rel, root=root) or not defines(
        rel, "ChatService", "MAX_TOOL_ROUNDS", "MAX_CONVERSATIONS", root=root
    ):
        return False
    tree = syntax(rel, root=root)
    return (
        ast.literal_eval(assigned(tree, "MAX_TOOL_ROUNDS")) == 6  # noqa: PLR2004
        and ast.literal_eval(assigned(tree, "MAX_CONVERSATIONS")) == 8  # noqa: PLR2004
    )


def check_25_narration_service_and_default_off(root: Path = REPO_ROOT) -> bool:
    """Check 25: services/ai/narration.py defines NarrationService and outlook_narration=False."""
    narr_rel = f"{AI_SERVICES}/narration.py"
    cfg_rel = f"{SERVICES}/config.py"
    if not files_exist(narr_rel, cfg_rel, root=root) or not defines(
        narr_rel, "NarrationService", root=root
    ):
        return False
    cls = class_node(syntax(cfg_rel, root=root), "AiSettings")
    for item in cls.body:
        if (
            isinstance(item, ast.AnnAssign)
            and isinstance(item.target, ast.Name)
            and item.target.id == "outlook_narration"
            and item.value is not None
        ):
            return ast.literal_eval(item.value) is False
    return False


def check_26_cli_ask_and_schema(root: Path = REPO_ROOT) -> bool:
    """Check 26: cli/__init__.py registers ask and docs/schema/ask.schema.json is in DOCUMENTS."""
    init_rel = f"{CLI}/__init__.py"
    ask_rel = f"{CLI}/ask.py"
    schema_rel = "docs/schema/ask.schema.json"
    if not files_exist(init_rel, ask_rel, schema_rel, f"{CLI}/documents.py", root=root):
        return False
    return contains(init_rel, 'app.command("ask")', root=root) and "ask" in _documents_keys(
        root=root
    )


def check_27_step3_tests_tracked(root: Path = REPO_ROOT) -> bool:
    """Check 27: Step 3 tests are tracked, tests/ai/test_ai_chat_injection.py among them."""
    return files_exist(
        "tests/ai/test_ai_tools.py",
        "tests/ai/test_ai_chat.py",
        "tests/ai/test_ai_chat_injection.py",
        "tests/ai/test_ai_narration.py",
        "tests/ai/test_ai_eval_conversations.py",
        "tests/ai/eval/chat_cases.py",
        "tests/cli/test_ask_command.py",
        root=root,
    )


# Step 4 static checks (28-35) --------------------------------------------------------------


def check_28_ai_and_outlook_routes(root: Path = REPO_ROOT) -> bool:
    """Check 28: web/routes/ai.py and outlook.py declare paths and create_app includes both."""
    ai_rel = f"{WEB}/routes/ai.py"
    outlook_rel = f"{WEB}/routes/outlook.py"
    app_rel = f"{WEB}/app.py"
    if not files_exist(ai_rel, outlook_rel, app_rel, root=root):
        return False
    return (
        contains(
            ai_rel,
            '"/api/ai"',
            '"/api/ai/calls"',
            '"/api/ai/briefings"',
            '"/api/ai/summaries"',
            '"/api/ai/narrations"',
            '"/api/ai/chat"',
            '"/api/ai/pause"',
            '"/api/ai/allowance"',
            root=root,
        )
        and contains(outlook_rel, '"/api/outlook"', '"/api/outlook/{basin}/{horizon}"', root=root)
        and contains(
            app_rel,
            "app.include_router(ai_router)",
            "app.include_router(outlook_router)",
            root=root,
        )
    )


def check_29_openapi_ai_and_outlook(root: Path = REPO_ROOT) -> bool:
    """Check 29: docs/api/openapi.json holds every AI/outlook path and the 3 AI stream models."""
    if not files_exist(OPENAPI_SPEC, root=root):
        return False
    spec = json_file(OPENAPI_SPEC, root=root)
    paths = object_of(spec.get("paths", {}))
    schemas = object_of(object_of(spec.get("components", {})).get("schemas", {}))
    return set(AI_OPENAPI_PATHS) <= set(paths) and set(AI_STREAM_MODELS) <= set(schemas)


def check_30_events_ai_kind_and_keys(root: Path = REPO_ROOT) -> bool:
    """Check 30: services/events.py EVENT_KINDS includes ai and QUERY_KEYS includes ai/briefings."""
    rel = f"{SERVICES}/events.py"
    if not files_exist(rel, root=root):
        return False
    tree = syntax(rel, root=root)
    kinds = set(cast("tuple[str, ...]", ast.literal_eval(assigned(tree, "EVENT_KINDS"))))
    keys = set(cast("tuple[str, ...]", ast.literal_eval(assigned(tree, "QUERY_KEYS"))))
    return "ai" in kinds and {"ai", "briefings"} <= keys


def check_31_phase05_check19_tagged(root: Path = REPO_ROOT) -> bool:
    """Check 31: scripts/verify_phase05.py check 19 reads v2.0.0-phase-5 via tagged()."""
    rel = "scripts/verify_phase05.py"
    return files_exist(rel, root=root) and contains(
        rel,
        'PHASE_5_TAG: Final = "v2.0.0-phase-5"',
        "def check_19_events_service",
        "tagged(rel, root=root)",
        root=root,
    )


def check_32_no_async_db_in_web_routes(root: Path = REPO_ROOT) -> bool:
    """Check 32: no module-level async def under web/routes/ names a repo, ai_engine, or Session."""
    route_files = [
        p
        for p in tracked(f"{WEB}/routes", root=root)
        if p.endswith(".py") and not p.endswith("__init__.py")
    ]
    if not route_files:
        return False
    for rel in route_files:
        tree = syntax(rel, root=root)
        for node in tree.body:
            if isinstance(node, ast.AsyncFunctionDef) and any(
                isinstance(sub, ast.Name) and sub.id in FORBIDDEN_ASYNC_ROUTE_NAMES
                for sub in ast.walk(node)
            ):
                return False
    return True


def check_33_cycle_watcher_ai_marks(root: Path = REPO_ROOT) -> bool:
    """Check 33: CycleWatcher in services/events.py reads AiCallRow and AiOutputRow."""
    rel = f"{SERVICES}/events.py"
    if not files_exist(rel, root=root):
        return False
    watcher = class_node(syntax(rel, root=root), "CycleWatcher")
    names = {node.id for node in ast.walk(watcher) if isinstance(node, ast.Name)}
    return {"AiCallRow", "AiOutputRow"} <= names


def check_34_serve_starts_summarizer(root: Path = REPO_ROOT) -> bool:
    """Check 34: cli/serve.py starts ChangeSummarizer and keeps Phase 5 check 7 and 23 calls."""
    rel = f"{CLI}/serve.py"
    if not files_exist(rel, root=root):
        return False
    return contains(
        rel,
        "ChangeSummarizer",
        "summarizer.prime",
        "hub.on_cycle(summarizer.wake)",
        "summarizer.run(stop)",
        "ProcessLock(paths.monitor_lock_path)",
        "run_monitor(",
        "WebServer",
        "hub.cycle_listener",
        "hub.close",
        root=root,
    )


def check_35_step4_tests_and_fixtures(root: Path = REPO_ROOT) -> bool:
    """Check 35: Step 4 tests and the six AI fixtures are tracked."""
    fixtures = [f"{FRONTEND}/src/test/fixtures/{name}" for name in STEP_4_AI_FIXTURES]
    return files_exist(
        "tests/web/test_api_ai_reads.py",
        "tests/web/test_api_ai_streams.py",
        "tests/web/test_api_ai_controls.py",
        "tests/web/test_api_ai_guards.py",
        "tests/web/test_api_outlook.py",
        "tests/ai/test_ai_summarizer.py",
        *fixtures,
        root=root,
    )


# Step 5 static checks (36-40) --------------------------------------------------------------


def check_36_frontend_ai_files_and_tests(root: Path = REPO_ROOT) -> bool:
    """Check 36: readEventStream, AiLabel, BriefingPanel, AiText, and Ask with tests tracked."""
    return files_exist(
        f"{FRONTEND}/src/ai/readEventStream.ts",
        f"{FRONTEND}/src/ai/readEventStream.test.ts",
        f"{FRONTEND}/src/ai/AiLabel.tsx",
        f"{FRONTEND}/src/ai/AiLabel.test.tsx",
        f"{FRONTEND}/src/ai/BriefingPanel.tsx",
        f"{FRONTEND}/src/ai/BriefingPanel.test.tsx",
        f"{FRONTEND}/src/ai/AiText.tsx",
        f"{FRONTEND}/src/ai/AiText.test.tsx",
        f"{FRONTEND}/src/pages/Ask.tsx",
        f"{FRONTEND}/src/pages/Ask.test.tsx",
        root=root,
    )


def check_37_frontend_keys_ai_and_briefings(root: Path = REPO_ROOT) -> bool:
    """Check 37: frontend/src/api/keys.ts lists ai and briefings."""
    rel = f"{FRONTEND}/src/api/keys.ts"
    return files_exist(rel, root=root) and contains(
        rel,
        'ai: () => invalidatableQueryKey("ai")',
        'briefings: () => invalidatableQueryKey("briefings")',
        root=root,
    )


def check_38_no_inner_html_in_frontend(root: Path = REPO_ROOT) -> bool:
    """Check 38: no file under frontend/src uses innerHTML or dangerouslySetInnerHTML."""
    src_files = tracked(f"{FRONTEND}/src", root=root)
    return bool(src_files) and not any(
        "innerHTML" in read(path, root=root) or "dangerouslySetInnerHTML" in read(path, root=root)
        for path in src_files
    )


def check_39_no_new_frontend_dependencies(root: Path = REPO_ROOT) -> bool:
    """Check 39: frontend/package.json dependency and devDependency names equal v2.0.0-phase-5's."""
    rel = f"{FRONTEND}/package.json"
    if not files_exist(rel, root=root):
        return False
    current = json_file(rel, root=root)
    tagged_pkg = object_of(json.loads(tagged(rel, root=root, tag=PHASE_5_TAG)))
    return set(object_of(current.get("dependencies", {}))) == set(
        object_of(tagged_pkg.get("dependencies", {}))
    ) and set(object_of(current.get("devDependencies", {}))) == set(
        object_of(tagged_pkg.get("devDependencies", {}))
    )


def check_40_ask_nav_and_route(root: Path = REPO_ROOT) -> bool:
    """Check 40: AppShell.tsx NAV_ITEMS lists '/ask' between '/timeline' and '/settings'."""
    shell_rel = f"{FRONTEND}/src/app/AppShell.tsx"
    routes_rel = f"{FRONTEND}/src/app/routes.tsx"
    if not files_exist(shell_rel, routes_rel, root=root):
        return False
    shell_text = read(shell_rel, root=root)
    timeline_pos = shell_text.find('to: "/timeline"')
    ask_pos = shell_text.find('{ to: "/ask", label: "Ask"')
    settings_pos = shell_text.find('to: "/settings"')
    return (
        timeline_pos != -1
        and ask_pos != -1
        and settings_pos != -1
        and timeline_pos < ask_pos < settings_pos
        and contains(routes_rel, 'path: "ask"', "<Ask />", root=root)
    )


# Step 6 static checks (41-45) --------------------------------------------------------------


def check_41_serve_demo_ai_flags(root: Path = REPO_ROOT) -> bool:
    """Check 41: scripts/serve_demo.py offers --ai-replay, --ai-cap-usd, and --ai-fail-auth."""
    rel = "scripts/serve_demo.py"
    if not files_exist(rel, root=root) or not defines(
        rel, "DemoReplay", "request_kind", "chat_round", "demo_claude", root=root
    ):
        return False
    return contains(rel, '"--ai-replay"', '"--ai-cap-usd"', '"--ai-fail-auth"', root=root)


def check_42_e2e_ai_spec_tracked(root: Path = REPO_ROOT) -> bool:
    """Check 42: frontend/e2e/ai.spec.ts tracked; playwright.config.ts has 3 servers; guard.ts."""
    return (
        files_exist(
            f"{FRONTEND}/e2e/ai.spec.ts",
            f"{FRONTEND}/e2e/guard.ts",
            f"{FRONTEND}/playwright.config.ts",
            root=root,
        )
        and contains(f"{FRONTEND}/playwright.config.ts", "8799", "8800", "8801", root=root)
        and contains(f"{FRONTEND}/e2e/guard.ts", "recordAiText", "leaksAiText", root=root)
    )


def check_43_ai_doc_live_idle_runbook(root: Path = REPO_ROOT) -> bool:
    """Check 43: docs/AI.md holds the live eval distribution with a date, idle line, and runbook."""
    return files_exist(AI_DOC, root=root) and contains(
        AI_DOC,
        "Measured live on 2026-11-02",
        "over all 38 cases",
        "window=600.0s server_cpu=0.3099%",
        "## Runbook",
        "**The cap is reached during a storm.**",
        "**Authentication failed.**",
        "**Rotating the key.**",
        "**Turning AI off.**",
        root=root,
    )


def check_44_readme_status_phase06(root: Path = REPO_ROOT) -> bool:
    """Check 44: README.md's ## Status names Phase 6 complete and Phase 7 next."""
    if not files_exist("README.md", root=root):
        return False
    text = read("README.md", root=root)
    status_match = re.search(r"^## Status$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if status_match is None:
        return False
    status_block = status_match[1]
    return (
        "Phase 6" in status_block
        and "Phase 7" in status_block
        and "is in progress" not in status_block.split("Phase 6", 1)[1].split(";", 1)[0]
    )


def check_45_readme_commands_brief_and_ask(root: Path = REPO_ROOT) -> bool:
    """Check 45: README.md's ## Commands names weatherbot brief and weatherbot ask."""
    if not files_exist("README.md", root=root):
        return False
    text = read("README.md", root=root)
    cmd_match = re.search(r"^## Commands$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if cmd_match is None:
        return False
    cmd_block = cmd_match[1]
    return "weatherbot brief" in cmd_block and "weatherbot ask" in cmd_block


# Step 7 self-checks (46-51) ----------------------------------------------------------------


def check_46_verifier_self_check(root: Path = REPO_ROOT) -> bool:
    """Check 46: scripts/verify_phase06.py is tracked, valid, 51 checks, 28 V rows, 9 modes."""
    rel = "scripts/verify_phase06.py"
    if not files_exist(rel, root=root):
        return False
    syntax(rel, root=root)
    text = read(rel, root=root)
    return (
        len(STATIC_CHECKS) == EXPECTED_STATIC_CHECKS
        and len(V_MATRIX) == EXPECTED_POST_ROWS
        and all(f'"{mode}"' in text for mode in MODES)
    )


def check_47_verification_test_tracked(root: Path = REPO_ROOT) -> bool:
    """Check 47: tests/test_phase06_verification.py is tracked with its named tests."""
    rel = "tests/test_phase06_verification.py"
    return files_exist(rel, root=root) and contains(
        rel,
        "test_fast_verification_passes_all_static_checks_within_thirty_seconds",
        "test_phase_verify_workflow_includes_phase_06",
        "test_a_changed_deliverable_turns_exactly_its_check_red",
        root=root,
    )


def check_48_qa_findings_doc(root: Path = REPO_ROOT) -> bool:
    """Check 48: docs/phase06-qa-findings.md holds a section per step, cost, idle, live eval."""
    if not files_exist(QA_FINDINGS, root=root):
        return False
    required = (
        "PR #76",
        "Step 1",
        "Step 2",
        "Step 3",
        "Step 4",
        "Step 5",
        "Step 6",
        "Step 7",
        "## Measured cost",
        "window=600.0s",
        "server_cpu=0.3099%",
        "tab_cpu=0.0025%",
        "## Live eval",
        "## Source-drift and model-drift observations",
        "## Live smoke runs",
        "## Pre-ship items",
    )
    return contains(QA_FINDINGS, *required, root=root)


def check_49_roadmaps_consistent(root: Path = REPO_ROOT) -> bool:
    """Check 49: phase06-roadmap.md exists with Steps 1-7 and ROADMAP.md holds Phase 6."""
    if not files_exist(ROADMAP, PHASE_ROADMAP, root=root):
        return False
    step_headers = tuple(f"## Step {n} —" for n in range(1, 8))
    return contains(ROADMAP, "### Phase 6 — Claude layer", root=root) and contains(
        PHASE_ROADMAP, *step_headers, root=root
    )


def check_50_matrix_includes_06_and_node_setup(root: Path = REPO_ROOT) -> bool:
    """Check 50: phase-verify.yml includes 01..06, separate Node steps for 06, 05 untouched."""
    if not {"01", "02", "03", "04", "05", "06"} <= phase_matrix(root=root):
        return False
    return contains(
        PHASE_WORKFLOW,
        "if: \"!cancelled() && matrix.phase == '05'\"",
        "if: \"!cancelled() && matrix.phase == '06'\"",
        "node-version-file: frontend/.nvmrc",
        "run: npm --prefix frontend ci",
        root=root,
    )


def _no_key_shape_in_phase06_paths(root: Path = REPO_ROOT) -> bool:
    for prefix in PHASE_6_KEY_SCAN_PREFIXES:
        for path in tracked(prefix, root=root):
            if KEY_PREFIX in read(path, root=root):
                return False
    return True


def check_51_security_gate_and_no_key_shapes(root: Path = REPO_ROOT) -> bool:
    """Check 51: security gate and frontend hooks wired, --security in phase-verify, no key."""
    return (
        contains(
            PRE_COMMIT_CONFIG,
            "id: gitleaks",
            "id: bandit",
            "id: pip-audit",
            "id: personal-data",
            "id: frontend-lint",
            "id: npm-audit",
            root=root,
        )
        and contains(
            PHASE_WORKFLOW,
            "uv run python scripts/verify_phase${{ matrix.phase }}.py --security",
            root=root,
        )
        and _no_key_shape_in_phase06_paths(root=root)
    )


STATIC_CHECKS: tuple[Check, ...] = (
    # Step 1 — The Claude client, the ledger, and the cap (1-12)
    (
        "pyproject.toml lists anthropic>=2.3.0 in dependencies and httpx2 only in dev group",
        check_01_ai_dependencies,
    ),
    (
        "pyproject.toml holds both forbidden AI import-linter contracts with exact module lists",
        check_02_ai_import_contracts,
    ),
    (
        "services/config.py defines AiSettings (6 fields) and 6 WEATHERBOT_AI_* overrides",
        check_03_ai_settings,
    ),
    (
        "services/ai/pricing.py defines PRICES (3 models), PRICES_AS_OF, MAX_PROMPT_TOKENS, no SDK",
        check_04_ai_pricing,
    ),
    (
        "services/ai/guard.py defines AI_TABLES={'ai_calls','ai_outputs'} and calls set_authorizer",
        check_05_ai_guard,
    ),
    (
        "services/ai/ledger.py defines Ledger with reserve, settle, today and uses writing_session",
        check_06_ai_ledger,
    ),
    (
        "revision 0007_ai_calls.py creates ai_calls with down_revision 0006 and FROZEN pins it",
        check_07_migration_0007,
    ),
    (
        "Runtime defines make_claude; tests/conftest.py clears ANTHROPIC_ and sets config dir",
        check_08_runtime_and_conftest_ai,
    ),
    (
        "services/doctor.py calls Check('ai', ...) in AST and HealthResponse declares ai",
        check_09_doctor_and_health_ai,
    ),
    (
        "services/logs.py silences anthropic, httpx2, and httpcore2 and defines SecretFilter",
        check_10_logs_redaction_and_silent_libs,
    ),
    (
        "no package module outside services/ai/ imports anthropic or httpx2 (AST)",
        check_11_no_sdk_import_outside_ai,
    ),
    (
        "Step 1 AI tests, record_ai_fixtures.py, and tests/fixtures/ai/manifest.json tracked",
        check_12_step1_tests_and_manifest,
    ),
    # Step 2 — The briefing, the change summary, and the eval set (13-21)
    (
        "services/ai/prompts.py defines system_prompt and prompt_version with no year or storm",
        check_13_prompts_no_season_data,
    ),
    (
        "services/ai/context.py and validate.py import only models, stdlib, pydantic, and schemas",
        check_14_context_and_validate_pure_imports,
    ),
    (
        "Briefing has the 5 section fields and no AI schema in schemas.py declares level",
        check_15_ai_schemas_fields_no_level,
    ),
    (
        "revision 0008_ai_outputs.py creates ai_outputs with down_revision 0007 and FROZEN pins it",
        check_16_migration_0008,
    ),
    (
        "cli/__init__.py registers brief and docs/schema/brief.schema.json is tracked in DOCUMENTS",
        check_17_cli_brief_and_schema,
    ),
    (
        "tests/ai/eval/ is tracked with its cases and scripts/eval_ai.py offers --live",
        check_18_eval_cases_and_script,
    ),
    (
        "tests/fixtures/ai/ stays under 1 MiB, manifest lists every file, and no auth header names",
        check_19_ai_fixtures_budget_and_headers,
    ),
    (
        "docs/AI.md holds 'What leaves the machine', 'The cap', and 'Measured cost'",
        check_20_ai_doc_sections,
    ),
    (
        "Step 2 prompt, context, validator, output, briefing, summary, brief, and eval tests",
        check_21_step2_tests_tracked,
    ),
    # Step 3 — Grounded chat and the outlook narration (22-27)
    (
        "services/ai/tools.py's TOOL_NAMES is the exact 9-tool allowlist",
        check_22_tool_names_exact,
    ),
    (
        "every tool definition in tools.py sets strict=True and additionalProperties=False (AST)",
        check_23_tool_definitions_strict,
    ),
    (
        "services/ai/chat.py defines ChatService, MAX_TOOL_ROUNDS=6, and MAX_CONVERSATIONS=8",
        check_24_chat_service_and_bounds,
    ),
    (
        "services/ai/narration.py defines NarrationService and AiSettings.outlook_narration=False",
        check_25_narration_service_and_default_off,
    ),
    (
        "cli/__init__.py registers ask and docs/schema/ask.schema.json is tracked in DOCUMENTS",
        check_26_cli_ask_and_schema,
    ),
    (
        "Step 3 tool, chat, injection, narration, conversation-eval, and ask tests tracked",
        check_27_step3_tests_tracked,
    ),
    # Step 4 — The AI in the API (28-35)
    (
        "web/routes/ai.py and outlook.py declare their paths and create_app includes both routers",
        check_28_ai_and_outlook_routes,
    ),
    (
        "docs/api/openapi.json holds every AI and outlook path and the 3 AI stream models",
        check_29_openapi_ai_and_outlook,
    ),
    (
        "services/events.py's EVENT_KINDS includes ai and QUERY_KEYS includes ai and briefings",
        check_30_events_ai_kind_and_keys,
    ),
    (
        "scripts/verify_phase05.py check 19 reads v2.0.0-phase-5 via tagged()",
        check_31_phase05_check19_tagged,
    ),
    (
        "no module-level async def under web/routes/ names a repository, ai_engine, or Session",
        check_32_no_async_db_in_web_routes,
    ),
    (
        "CycleWatcher in services/events.py reads AiCallRow and AiOutputRow",
        check_33_cycle_watcher_ai_marks,
    ),
    (
        "cli/serve.py starts ChangeSummarizer and keeps Phase 5's check 7 and 23 calls",
        check_34_serve_starts_summarizer,
    ),
    (
        "Step 4 AI API/stream/control/guard/outlook/summarizer tests and 6 AI fixtures tracked",
        check_35_step4_tests_and_fixtures,
    ),
    # Step 5 — The AI in the page (36-40)
    (
        "frontend/src/ai/{readEventStream,AiLabel,BriefingPanel,AiText}, Ask.tsx, and tests",
        check_36_frontend_ai_files_and_tests,
    ),
    (
        "frontend/src/api/keys.ts lists ai and briefings query keys",
        check_37_frontend_keys_ai_and_briefings,
    ),
    (
        "no file under frontend/src uses innerHTML or dangerouslySetInnerHTML",
        check_38_no_inner_html_in_frontend,
    ),
    (
        "frontend/package.json dependency and devDependency names equal v2.0.0-phase-5's",
        check_39_no_new_frontend_dependencies,
    ),
    (
        "AppShell.tsx NAV_ITEMS lists '/ask' between '/timeline' and '/settings' and routes.tsx",
        check_40_ask_nav_and_route,
    ),
    # Step 6 — The live eval, the browser smoke, and the operator's AI (41-45)
    (
        "scripts/serve_demo.py offers --ai-replay, --ai-cap-usd, and --ai-fail-auth",
        check_41_serve_demo_ai_flags,
    ),
    (
        "frontend/e2e/ai.spec.ts tracked; playwright.config.ts has 3 demo servers; guard.ts",
        check_42_e2e_ai_spec_tracked,
    ),
    (
        "docs/AI.md holds the live eval distribution with a date, the idle line, and the runbook",
        check_43_ai_doc_live_idle_runbook,
    ),
    (
        "README.md's ## Status names Phase 6 complete and Phase 7 next",
        check_44_readme_status_phase06,
    ),
    (
        "README.md's ## Commands names weatherbot brief and weatherbot ask",
        check_45_readme_commands_brief_and_ask,
    ),
    # Step 7 — QA & Verification Script self-checks (46-51)
    (
        "scripts/verify_phase06.py tracked, valid syntax, 51 static checks, 28 V-rows, and 9 modes",
        check_46_verifier_self_check,
    ),
    (
        "tests/test_phase06_verification.py tracked and covers --fast, matrix, and red checks",
        check_47_verification_test_tracked,
    ),
    (
        "docs/phase06-qa-findings.md tracked with PR #76, Steps 1-7, cost, idle, live eval, items",
        check_48_qa_findings_doc,
    ),
    (
        "phase06-roadmap.md Steps 1-7 and ROADMAP.md Phase 6 headers are consistent",
        check_49_roadmaps_consistent,
    ),
    (
        "phase-verify.yml includes 01..06 in matrix, sets up Node for 06, and keeps 05 untouched",
        check_50_matrix_includes_06_and_node_setup,
    ),
    (
        "security gate hooks and frontend hooks wired, --security in phase-verify, no key shapes",
        check_51_security_gate_and_no_key_shapes,
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
    junit_dir = tmp_dir or Path(tempfile.mkdtemp(prefix="weatherbot-verify06-py-"))
    junit = junit_dir / "pytest.xml"
    coverage_file = junit_dir / "coverage.sqlite"
    cov_env = {"COVERAGE_FILE": str(coverage_file)}
    outcomes.append(
        run_command(
            "py.pytest",
            "pytest (offline, engine + policy + context + validate branch coverage >= 90%)",
            [
                "uv",
                "run",
                "pytest",
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
    junit_dir = tmp_dir or Path(tempfile.mkdtemp(prefix="weatherbot-verify06-node-"))
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
    """Run Playwright Chromium browser smoke (--ui, including ai.spec.ts) with JUnit XML."""
    heading("Playwright Chromium browser smoke (--ui)")
    if not (REPO_ROOT / "src/weatherbot/web/static/index.html").is_file():
        run_command(
            "ui.build",
            "npm --prefix frontend run build",
            ["npm", "--prefix", FRONTEND, "run", "build"],
        )
    junit_dir = tmp_dir or Path(tempfile.mkdtemp(prefix="weatherbot-verify06-ui-"))
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
    """Run ``pytest -m live`` (landmarks only; no AI request)."""
    heading("Live service smoke tests (--live)")
    junit = (tmp_dir or Path(tempfile.mkdtemp(prefix="weatherbot-verify06-live-"))) / "live.xml"
    outcome = run_command(
        "live.pytest",
        "pytest -m live",
        ["uv", "run", "pytest", "-m", "live", f"--junitxml={junit}"],
    )
    return outcome, parse_junit(junit)


def _user_registry_anthropic_key() -> str | None:
    r"""Read ANTHROPIC_API_KEY from HKCU\Environment on Windows when absent from os.environ."""
    if sys.platform != "win32":
        return None
    import winreg  # noqa: PLC0415

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, "ANTHROPIC_API_KEY")
    except OSError:
        return None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _operator_ai_env(tmp_dir: Path) -> dict[str, str]:
    """Build an isolated data/config environment with the operator's credential if present."""
    env: dict[str, str] = {
        "WEATHERBOT_DATA_DIR": str(tmp_dir / "data"),
        "WEATHERBOT_CONFIG_DIR": str(tmp_dir / "config"),
    }
    if not os.environ.get("ANTHROPIC_API_KEY"):
        reg_key = _user_registry_anthropic_key()
        if reg_key:
            env["ANTHROPIC_API_KEY"] = reg_key
    return env


def _has_operator_credential(extra_env: Mapping[str, str]) -> bool:
    """Whether an Anthropic credential is available without reading or printing its value."""
    from weatherbot.services.ai.client import credential_source, default_client  # noqa: PLC0415

    merged = {**os.environ, **extra_env}
    return credential_source(merged, default_client) != "none"


def ai_suite() -> Outcome:
    """Run ``scripts/eval_ai.py --live`` (spends ~$0.40; refuses in CI or without credential)."""
    heading("Live AI evaluation (--ai)")
    if os.environ.get("CI"):
        return report(
            Outcome(
                "ai.eval_ai_live",
                "scripts/eval_ai.py --live (~$0.40)",
                "FAIL",
                "refused in CI",
            )
        )
    with tempfile.TemporaryDirectory(prefix="weatherbot-verify06-ai-") as tmp:
        env = _operator_ai_env(Path(tmp))
        if not _has_operator_credential(env):
            return report(
                Outcome(
                    "ai.eval_ai_live",
                    "scripts/eval_ai.py --live (~$0.40)",
                    "FAIL",
                    "no Anthropic credential",
                )
            )
        print(
            "Estimate: scripts/eval_ai.py --live sends 38 cases to Claude Sonnet 5.5 "
            "(about $0.40 at list price) in a temporary data directory.",
            flush=True,
        )
        return run_command(
            "ai.eval_ai_live",
            "scripts/eval_ai.py --live (~$0.40)",
            ["uv", "run", "python", "scripts/eval_ai.py", "--live"],
            env=env,
        )


def security_suites() -> list[Outcome]:
    """Run gitleaks, bandit, pip-audit, check_personal_data, npm audit, ESLint, and key scan."""
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
    key_clean = _no_key_shape_in_phase06_paths()
    results.append(
        report(
            Outcome(
                "sec.key_shape_scan",
                "no Anthropic key shape under Phase 6 paths",
                "PASS" if key_clean else "FAIL",
                "" if key_clean else "key shape found",
            )
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


def phase_five_post() -> bool:
    """Phase 5's own ``--post`` exits 0 with all 85 checks passing; only its totals print."""
    started = time.monotonic()
    result = capture(["uv", "run", "python", "scripts/verify_phase05.py", "--post"], timeout=14400)
    elapsed = time.monotonic() - started
    totals = dict(
        re.findall(r"^  (passed|failed|skipped|total)\s+(\d+)$", result.stdout, re.MULTILINE)
    )
    print(
        f"  verify_phase05.py --post: {totals or 'no summary'} in {elapsed:.1f}s; "
        f"exit {result.returncode}"
    )
    return result.returncode == 0 and totals == {
        "passed": "85",
        "failed": "0",
        "skipped": "0",
        "total": "85",
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
    env = dict(os.environ)
    if not env.get("ANTHROPIC_API_KEY"):
        reg_key = _user_registry_anthropic_key()
        if reg_key:
            env["ANTHROPIC_API_KEY"] = reg_key
    with tempfile.TemporaryDirectory(prefix="weatherbot-installed-doc06-") as tmp:
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


def operator_health_and_doctor_ai() -> bool:
    """V1.5: operator /api/health reads AI ready at DB head and installed doctor passes ai."""
    health = _fetch_operator_json("/api/health")
    db = object_of(health.get("database", {}))
    ai = object_of(health.get("ai", {}))
    _, doc_data = _installed_tool_doctor(offline=False)
    checks = {
        str(object_of(c)["name"]): str(object_of(c)["status"])
        for c in array_of(doc_data.get("checks", []))
    }
    print(
        f"  /api/health: revision={db.get('revision')}, head={db.get('head')}, "
        f"current={db.get('current')}, ai.state={ai.get('state')}, "
        f"spent_micro_usd={ai.get('spent_micro_usd')}, cap_micro_usd={ai.get('cap_micro_usd')}; "
        f"doctor ai={checks.get('ai')}, web={checks.get('web')}, "
        f"migrations={checks.get('migrations')}"
    )
    return (
        db.get("current") is True
        and descends_from(str(db.get("head", "")), "0008")
        and ai.get("state") == "ready"
        and checks.get("ai") == "pass"
        and checks.get("web") == "pass"
        and checks.get("migrations") == "pass"
    )


def operator_settled_briefing() -> bool:
    """V6.5: operator's service settled a real briefing in /api/ai/calls."""
    calls_payload = _fetch_operator_json("/api/ai/calls")
    calls = [object_of(item) for item in array_of(calls_payload.get("calls", []))]
    settled = [
        row
        for row in calls
        if row.get("kind") == "briefing"
        and row.get("status") == "ok"
        and isinstance(row.get("cost_micro_usd"), int)
        and int(cast("int", row["cost_micro_usd"])) > 0
    ]
    if settled:
        latest = settled[0]
        print(
            f"  /api/ai/calls: settled briefing id={latest.get('id')}, "
            f"model={latest.get('model')}, status={latest.get('status')}, "
            f"cost_micro_usd={latest.get('cost_micro_usd')}"
        )
    else:
        print("  /api/ai/calls: no settled briefing row found")
    return bool(settled)


def measure_idle_probe() -> bool:
    """V6.3: scripts/measure_idle.py reports both shares < 0.5% with ai_state=ready."""
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
    """V7.1: scripts/verify_phase06.py --fast passes all 51 checks in under 30 seconds."""
    started = time.monotonic()
    result = capture(["uv", "run", "python", "scripts/verify_phase06.py", "--fast"], timeout=60)
    elapsed = time.monotonic() - started
    totals = dict(
        re.findall(r"^  (passed|failed|skipped|total)\s+(\d+)$", result.stdout, re.MULTILINE)
    )
    print(f"  verify_phase06.py --fast: {totals or 'no summary'} in {elapsed:.2f}s")
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


V_MATRIX: tuple[VRow, ...] = (
    # V1 — The Claude client, the ledger, and the cap (5 rows)
    VRow(
        "V1.1",
        "V1 — The Claude client, the ledger, and the cap",
        "Static checks 1-12 all PASS",
        ("static_01_12",),
    ),
    VRow(
        "V1.2",
        "V1 — The Claude client, the ledger, and the cap",
        "Settings, prices, ledger, guard, caller, client, and redaction tests pass (--py)",
        (
            "ruff_check",
            "ruff_format",
            "pyright",
            "pyright_linux",
            "lint_imports",
            "pytest",
            "coverage_policy",
            Select(
                "tests.ai.test_ai_settings",
                "tests.ai.test_ai_pricing",
                "tests.ai.test_ai_ledger",
                "tests.ai.test_ai_guard",
                "tests.ai.test_ai_caller",
                "tests.ai.test_ai_client",
                "tests.ai.test_ai_imports",
                "tests.ai.test_ai_redaction",
                "tests.ai.test_ai_fixtures",
                "tests.services.test_database",
                "tests.test_architecture",
            ),
        ),
    ),
    VRow(
        "V1.3",
        "V1 — The Claude client, the ledger, and the cap",
        "Doctor and health AI tests pass; a fresh doctor exits 0",
        (Select("tests.services.test_doctor_ai", "tests.web.test_api_health_ai"),),
    ),
    VRow(
        "V1.4",
        "V1 — The Claude client, the ledger, and the cap",
        "verify_phase05.py --post passes all 85 (and Phases 4, 3, 2, and 1)",
        ("verify_phase05_post",),
    ),
    VRow(
        "V1.5",
        "V1 — The Claude client, the ledger, and the cap",
        "The operator's /api/health reads AI ready; doctor passes",
        ("operator_health_and_doctor_ai",),
    ),
    # V2 — The briefing, the change summary, and the eval set (4 rows)
    VRow(
        "V2.1",
        "V2 — The briefing, the change summary, and the eval set",
        "Static checks 13-21 all PASS",
        ("static_13_21",),
    ),
    VRow(
        "V2.2",
        "V2 — The briefing, the change summary, and the eval set",
        "Prompt, context, validator, briefing, summary, and brief tests pass",
        (
            "export_schemas_check",
            Select(
                "tests.ai.test_ai_prompts",
                "tests.ai.test_ai_context",
                "tests.ai.test_ai_validators",
                "tests.ai.test_ai_outputs",
                "tests.ai.test_ai_briefing",
                "tests.ai.test_ai_summaries",
                "tests.cli.test_brief_command",
                "tests.cli.test_documents",
            ),
        ),
    ),
    VRow(
        "V2.3",
        "V2 — The briefing, the change summary, and the eval set",
        "The offline eval passes; every contradiction is rejected",
        (Select("tests.ai.test_ai_eval"),),
    ),
    VRow(
        "V2.4",
        "V2 — The briefing, the change summary, and the eval set",
        "context.py and validate.py each hold 90% branch coverage",
        ("coverage_ai_context", "coverage_ai_validate"),
    ),
    # V3 — Grounded chat and the outlook narration (3 rows)
    VRow(
        "V3.1",
        "V3 — Grounded chat and the outlook narration",
        "Static checks 22-27 all PASS",
        ("static_22_27",),
    ),
    VRow(
        "V3.2",
        "V3 — Grounded chat and the outlook narration",
        "Tool, chat, narration, and ask tests pass",
        (
            Select(
                "tests.ai.test_ai_tools",
                "tests.ai.test_ai_chat",
                "tests.ai.test_ai_narration",
                "tests.ai.test_ai_eval_conversations",
                "tests.cli.test_ask_command",
            ),
        ),
    ),
    VRow(
        "V3.3",
        "V3 — Grounded chat and the outlook narration",
        "Injection cases keep every tool call in the allowlist",
        (Select("tests.ai.test_ai_chat_injection"),),
    ),
    # V4 — The AI in the API (4 rows)
    VRow(
        "V4.1",
        "V4 — The AI in the API",
        "Static checks 28-35 all PASS",
        ("static_28_35",),
    ),
    VRow(
        "V4.2",
        "V4 — The AI in the API",
        "AI read, stream, control, outlook, and summarizer tests pass",
        (
            Select(
                "tests.web.test_api_ai_reads",
                "tests.web.test_api_ai_streams",
                "tests.web.test_api_ai_controls",
                "tests.web.test_api_outlook",
                "tests.ai.test_ai_summarizer",
                "tests.services.test_cycle_watcher",
                "tests.services.test_event_hub",
            ),
        ),
    ),
    VRow(
        "V4.3",
        "V4 — The AI in the API",
        "Cross-site AI writes are refused; a disconnect settles",
        (Select("tests.web.test_api_ai_guards", "tests.web.test_api_ai_streams"),),
    ),
    VRow(
        "V4.4",
        "V4 — The AI in the API",
        "The OpenAPI and fixture exporters' --check pass",
        (
            "export_openapi_check",
            "export_api_fixtures_check",
            Select("tests.web.test_openapi_export", "tests.web.test_api_fixtures"),
        ),
    ),
    # V5 — The AI in the page (3 rows)
    VRow(
        "V5.1",
        "V5 — The AI in the page",
        "Static checks 36-40 all PASS",
        ("static_36_40",),
    ),
    VRow(
        "V5.2",
        "V5 — The AI in the page",
        "--node exits 0: types, lint, Vitest, build, and licences",
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
            Select(
                "src/ai/AiLabel.test.tsx",
                "src/ai/AiStateBanner.test.tsx",
                "src/ai/readEventStream.test.ts",
                "src/ai/BriefingPanel.test.tsx",
                "src/pages/Ask.test.tsx",
                "src/pages/Dashboard.test.tsx",
                "src/pages/Timeline.test.tsx",
                "src/pages/Storms.test.tsx",
                "src/pages/Settings.test.tsx",
                "src/app/AppShell.test.tsx",
                "src/events/useEventStream.test.tsx",
            ),
        ),
    ),
    VRow(
        "V5.3",
        "V5 — The AI in the page",
        "Model text renders literally; no HTML path exists",
        (Select("src/ai/AiText.test.tsx"),),
    ),
    # V6 — The live eval, the browser smoke, and the operator's AI (5 rows)
    VRow(
        "V6.1",
        "V6 — The live eval, the browser smoke, and the operator's AI",
        "Static checks 41-45 all PASS",
        ("static_41_45",),
    ),
    VRow(
        "V6.2",
        "V6 — The live eval, the browser smoke, and the operator's AI",
        "The AI smoke: briefing, answer, pause, auth failure",
        (
            "playwright_ui",
            "pytest_live",
            Select("ai.spec.ts"),
            Select(
                "tests.scripts.test_serve_demo",
                "tests.scripts.test_measure_idle",
                "tests.services.test_doctor_ai",
            ),
        ),
    ),
    VRow(
        "V6.3",
        "V6 — The live eval, the browser smoke, and the operator's AI",
        "Server and tab each stay under 0.5% of a core idle",
        ("measure_idle_probe",),
    ),
    VRow(
        "V6.4",
        "V6 — The live eval, the browser smoke, and the operator's AI",
        "eval_ai.py --live passes every case; cost recorded",
        ("eval_ai_live",),
    ),
    VRow(
        "V6.5",
        "V6 — The live eval, the browser smoke, and the operator's AI",
        "The operator's service settled a real briefing",
        ("operator_settled_briefing",),
    ),
    # V7 — CI integration + security (4 rows)
    VRow(
        "V7.1",
        "V7 — CI integration + security",
        "verify_phase06.py --fast exits 0 on Ubuntu CI and in < 30 s locally",
        (
            "verify_phase06_fast_budget",
            "phase_verify_ci",
            Select("tests.test_phase06_verification"),
        ),
    ),
    VRow(
        "V7.2",
        "V7 — CI integration + security",
        "phase-verify.yml's matrix includes '01' to '06' under required branch protection",
        ("static_50", "protection_requires_both"),
    ),
    VRow(
        "V7.3",
        "V7 — CI integration + security",
        "All 51 static checks in verify_phase06.py pass",
        ("static_01_51",),
    ),
    VRow(
        "V7.4",
        "V7 — CI integration + security",
        "--security exits 0 over both stacks",
        (
            "gitleaks",
            "bandit",
            "audit_deps",
            "personal_data_all",
            "personal_data_self_test",
            "npm_audit",
            "frontend_lint",
            "key_shape_scan",
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
    """Evaluate all 28 rows of the V1-V7 post-implementation verification matrix."""
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
        ("static_01_12", 1, 12),
        ("static_13_21", 13, 21),
        ("static_22_27", 22, 27),
        ("static_28_35", 28, 35),
        ("static_36_40", 36, 40),
        ("static_41_45", 41, 45),
        ("static_50", 50, 50),
        ("static_01_51", 1, 51),
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
    """Run static checks, all suites, --ai, probes, and evaluate the 28-row V1-V7 matrix."""
    print(
        "Notice: --post starts the offline demonstration servers (scripts/serve_demo.py) and "
        "headless Chromium for the Playwright smoke and the 600 s idle CPU measurement, "
        "runs scripts/eval_ai.py --live (spending ~$0.40 at list price in a temporary directory), "
        "runs verify_phase05.py --post (85 checks), and reads the operator's running service "
        "only through GET /api/health, GET /api/ai/calls, and doctor --json.",
        flush=True,
    )
    static_outcomes = run_static_checks()
    suite = Suite()
    _record_static_slices(static_outcomes, suite)

    with tempfile.TemporaryDirectory(prefix="weatherbot-post06-") as tmp:
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
        "sec.key_shape_scan": "key_shape_scan",
    }
    for out in sec_outcomes:
        if out.item_id in sec_map:
            suite.commands[sec_map[out.item_id]] = out.status

    ai_out = ai_suite()
    suite.commands["eval_ai_live"] = ai_out.status

    heading("Post-implementation probes")
    run_probe(
        "phase_verify_ci",
        "phase-verify (01) through (06) CI checks",
        lambda: phase_entries_green(("01", "02", "03", "04", "05", "06")),
        suite,
    )
    run_probe(
        "protection_requires_both",
        "main branch protection requires gate and phase-verify",
        protection_requires_both,
        suite,
    )
    run_probe("verify_phase05_post", "verify_phase05.py --post (85 checks)", phase_five_post, suite)
    run_probe(
        "operator_health_and_doctor_ai",
        "operator /api/health AI ready at DB head and installed doctor ai check",
        operator_health_and_doctor_ai,
        suite,
    )
    run_probe(
        "operator_settled_briefing",
        "operator /api/ai/calls settled briefing row",
        operator_settled_briefing,
        suite,
    )
    run_probe(
        "measure_idle_probe",
        "scripts/measure_idle.py (600 s idle CPU < 0.5% with ai_state=ready)",
        measure_idle_probe,
        suite,
    )
    run_probe(
        "verify_phase06_fast_budget",
        "scripts/verify_phase06.py --fast (< 30 s)",
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
    group.add_argument("--fast", action="store_true", help="Run the 51 static checks only.")
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
        "--ai",
        action="store_true",
        help="Run static checks and scripts/eval_ai.py --live (spends ~$0.40).",
    )
    group.add_argument(
        "--security", action="store_true", help="Run static checks and security/privacy gates."
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Run --py, --node, --ui, --live, and --security (all except --ai and --post).",
    )
    group.add_argument(
        "--post", action="store_true", help="Run the full 79-check Phase 6 verification."
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for Phase 6 verification."""
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
            args.ai,
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
    if args.ai:
        outcomes.append(ai_suite())
    if args.security or args.all:
        outcomes.extend(security_suites())
    return summarize(outcomes)


if __name__ == "__main__":
    raise SystemExit(main())
