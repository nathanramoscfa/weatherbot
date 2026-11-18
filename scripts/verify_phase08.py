# scripts/verify_phase08.py
"""Verify Phase 8 (UI/UX Redesign and Visual Dogfooding) against docs/roadmap/phase08-roadmap.md.

Modes (mutually exclusive; no flag runs ``--fast`` and ``--py``):
  --fast      60 static file, AST, OpenAPI, fixture, and workflow checks (< 30 s, no network).
  --py        Ruff, Pyright (host + Linux), import-linter, offline pytest with >=90%
              branch coverage on engine, policy, AI context, and AI validate, schema/OpenAPI/
              fixture checks, and wheel smoke.
  --node      Frontend npm ci, audit signatures, api:check, lint, typecheck, Vitest,
              build, and licenses:check.
  --ui        Playwright Chromium browser smoke (default e2e run; excludes @dogfood and @idle).
  --live      Live source, monitor, and OSM tile pytest suite (``pytest -m live``, landmarks only).
  --security  Secret, SAST, dependency, personal-data, npm audit, ESLint, and secret-shape scans.
  --all       --py + --node + --ui + --live + --security (all except --post).
  --post      Full V1-V10 post-implementation matrix (38 rows, 98 checks total).
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
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Final, Literal, cast

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
REPOSITORY: Final = "nathanramoscfa/weatherbot"
PHASE_7_TAG: Final = "v2.0.0-phase-7"
PHASE_8_TAG: Final = "v2.0.0-phase-8"
CI_WORKFLOW: Final = ".github/workflows/ci.yml"
PHASE_WORKFLOW: Final = ".github/workflows/phase-verify.yml"
PRE_COMMIT_CONFIG: Final = ".pre-commit-config.yaml"
ROADMAP: Final = "docs/roadmap/ROADMAP.md"
PHASE_ROADMAP: Final = "docs/roadmap/phase08-roadmap.md"
QA_FINDINGS: Final = "docs/phase08-qa-findings.md"
DOGFOOD_DOC: Final = "docs/phase08-dogfood.md"
DESIGN_DOC: Final = "docs/DESIGN.md"
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
EXPECTED_STATIC_CHECKS: Final = 60
EXPECTED_POST_ROWS: Final = 38
EXPECTED_V_DISTRIBUTION: Final = (5, 4, 5, 4, 3, 3, 3, 4, 3, 4)
EXPECTED_PHASE_07_POST_TOTAL: Final = "107"
NESTED_SWEEP_TIMEOUT_SECONDS: Final = 14400
EXPECTED_PHASE_MATRIX_PREFIX: Final = ("01", "02", "03", "04", "05", "06", "07", "08")
EXPECTED_DOGFOOD_RENDERS: Final = 240
EXPECTED_SCENARIO_NAMES: Final = ("quiet", "outlook", "cone", "watch", "landfall")
EXPECTED_SCENARIOS: Final[dict[str, dict[str, dict[str, int | str]]]] = {
    "quiet": {
        "simulated Miami-Dade": {"level": 1, "rule": "all_clear"},
        "Parliament Square": {"level": 1, "rule": "all_clear"},
    },
    "outlook": {
        "simulated Miami-Dade": {"level": 2, "rule": "development_region"},
        "Parliament Square": {"level": 2, "rule": "development_region"},
    },
    "cone": {
        "simulated Miami-Dade": {"level": 3, "rule": "hurricane_cone"},
        "Parliament Square": {"level": 2, "rule": "storm_cone"},
    },
    "watch": {
        "simulated Miami-Dade": {"level": 4, "rule": "hurricane_watch"},
        "Parliament Square": {"level": 3, "rule": "tropical_storm_watch"},
    },
    "landfall": {
        "simulated Miami-Dade": {"level": 5, "rule": "hurricane_warning"},
        "Parliament Square": {"level": 4, "rule": "tropical_storm_warning"},
    },
}

PHASE_8_SECRET_SCAN_PREFIXES: Final = (
    "src/weatherbot",
    "scripts",
    "frontend/src",
    "frontend/e2e",
    "tests/fixtures/ai",
    "docs/DESIGN.md",
    "docs/phase08-dogfood.md",
    "docs/phase08-qa-findings.md",
)
ANTHROPIC_KEY_PREFIX: Final = "sk" + "-" + "ant" + "-"
NTFY_TOKEN_SHAPE: Final = re.compile(r"\btk_[a-z0-9]{20,}\b")
THREE_DECIMAL_PAIR_RE: Final = re.compile(r"-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}")
FORBIDDEN_TEXT_SIZE_RE: Final = re.compile(r"\btext-xs\b|\btext-\[(?:length:)?[0-9.]")
NAV_ITEM_LINE_RE: Final = re.compile(
    r'^\s*\{\s*to:\s*"([^"]+)",\s*label:\s*"([^"]+)",\s*icon:\s*\w+,'
    r"\s*end:\s*(?:true|false)\s*\},?$",
    re.MULTILINE,
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
    """One row of the Phase 8 V1-V10 post-implementation verification matrix."""

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
def tagged(relative: str, root: Path = REPO_ROOT, *, tag: str = PHASE_7_TAG) -> str:
    """Read a repository-relative file as a milestone git tag recorded it."""
    return git("show", f"{tag}:{relative}", root=root)


def syntax(relative: str, root: Path = REPO_ROOT) -> ast.Module:
    """Parse a repository-relative Python file into an AST."""
    return ast.parse(read(relative, root=root), filename=relative)


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


def _no_secret_shape_in_phase08_paths() -> bool:
    """Return True when no Anthropic key or ntfy token shape appears in Phase 8 tracked files."""
    text_exts = (
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".json",
        ".sse",
        ".md",
        ".css",
        ".xml",
        ".toml",
        ".yml",
        ".yaml",
        ".txt",
    )
    for prefix in PHASE_8_SECRET_SCAN_PREFIXES:
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
# 60 Static Checks (Steps 1 through 10)
# ---------------------------------------------------------------------------


def check_01_demo_storm_and_scenarios_tracked() -> bool:
    """Check 1: demo_storm.py and demo_scenarios.py are tracked and SCENARIOS names all 5."""
    if not files_exist("scripts/demo_storm.py", "scripts/demo_scenarios.py"):
        return False
    scenarios = object_of(
        ast.literal_eval(assigned(syntax("scripts/demo_scenarios.py"), "SCENARIOS"))
    )
    return tuple(scenarios.keys()) == EXPECTED_SCENARIO_NAMES


def check_02_scenarios_match_decision_2_table() -> bool:
    """Check 2: SCENARIOS in scripts/demo_scenarios.py equals Decision 2's table by AST."""
    scenarios = ast.literal_eval(assigned(syntax("scripts/demo_scenarios.py"), "SCENARIOS"))
    return scenarios == EXPECTED_SCENARIOS


def check_03_serve_demo_scenario_flag_and_top_level_definitions() -> bool:
    """Check 3: serve_demo.py holds --scenario beside --switch-file and keeps top-level symbols."""
    tree = syntax("scripts/serve_demo.py")
    classes = {n.name for n in tree.body if isinstance(n, ast.ClassDef)}
    funcs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    return (
        contains(
            "scripts/serve_demo.py",
            '"--scenario"',
            '"--switch-file"',
            '"quiet"',
            '"outlook"',
            '"cone"',
            '"watch"',
            '"landfall"',
        )
        and "DemoReplay" in classes
        and {"request_kind", "chat_round", "demo_claude"} <= funcs
    )


def check_04_two_decimal_synthetic_geometry_and_no_src_synthetic() -> bool:
    """Check 4: demo_storm/demo_scenarios use <=2 decimals, label synthetic, and src/ has none."""
    for rel in ("scripts/demo_storm.py", "scripts/demo_scenarios.py"):
        if THREE_DECIMAL_PAIR_RE.search(read(rel)):
            return False
    decimals_const = ast.literal_eval(assigned(syntax("scripts/demo_storm.py"), "_DECIMALS"))
    src_has_synthetic = any(
        "synthetic" in read(rel).lower() for rel in sorted(tracked("src")) if rel.endswith(".py")
    )
    return (
        decimals_const == 2  # noqa: PLR2004 - R2 two-decimal bound
        and contains(
            "scripts/demo_storm.py",
            "SYNTHETIC_NOTE",
            "synthetic demonstration",
            '"synthetic": True',
        )
        and contains("scripts/demo_scenarios.py", '"synthetic": True', "synthetic demonstration")
        and not src_has_synthetic
    )


def check_05_playwright_config_scenario_ports_and_spec() -> bool:
    """Check 5: playwright.config.ts holds 8802 and 8806 beside 8799..8801 and scenarios.spec.ts."""
    return contains(
        "frontend/playwright.config.ts",
        '"8799"',
        '"8800"',
        '"8801"',
        '"8802"',
        '"8806"',
    ) and files_exist("frontend/e2e/scenarios.spec.ts")


def check_06_scenario_tests_recorder_and_manifest_entries() -> bool:
    """Check 6: scenario tests, record_ai_fixtures --scenario, and 12 manifest entries exist."""
    if not files_exist(
        "tests/scripts/test_demo_scenarios.py",
        "tests/scripts/test_demo_storm.py",
        "tests/fixtures/ai/manifest.json",
    ):
        return False
    if not contains("scripts/record_ai_fixtures.py", '"--scenario"', "def scenario_cases("):
        return False
    entries = [
        object_of(item) for item in array_of(json.loads(read("tests/fixtures/ai/manifest.json")))
    ]
    by_case = {str(item["case"]): str(item["kind"]) for item in entries}
    expected_streams = {
        f"scenario-{scenario}-{place}"
        for scenario in EXPECTED_SCENARIO_NAMES
        for place in ("miami-dade", "nassau")
    }
    expected_parses = {
        "scenario-landfall-miami-dade-summary",
        "scenario-landfall-nassau-summary",
    }
    return all(
        by_case.get(case) == "stream" and files_exist(f"tests/fixtures/ai/{case}.sse")
        for case in expected_streams
    ) and all(
        by_case.get(case) == "parse" and files_exist(f"tests/fixtures/ai/{case}.json")
        for case in expected_parses
    )


def check_07_verify_phase07_check_59_reads_tagged_readme() -> bool:
    """Check 7: verify_phase07.py Check 59 reads tagged('README.md', tag=PHASE_7_TAG) with tests."""
    p7_tree = syntax("scripts/verify_phase07.py")
    check_fn = next(
        (
            n
            for n in p7_tree.body
            if isinstance(n, ast.FunctionDef)
            and n.name == "check_59_readme_status_names_phase_07_complete"
        ),
        None,
    )
    if check_fn is None:
        return False
    has_tagged_call = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "tagged"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "README.md"
        for node in ast.walk(check_fn)
    )
    test_funcs = {
        n.name
        for n in syntax("tests/test_phase07_verification.py").body
        if isinstance(n, ast.FunctionDef)
    }
    return (
        has_tagged_call
        and contains(
            "scripts/verify_phase07.py",
            'PHASE_7_TAG: Final = "v2.0.0-phase-7"',
            'tagged("README.md", tag=PHASE_7_TAG)',
        )
        and {
            "test_the_live_status_no_longer_moves_check_59",
            "test_the_tagged_status_still_decides_check_59",
        }
        <= test_funcs
    )


def check_08_index_css_theme_type_tokens() -> bool:
    """Check 8: index.css @theme sets --text-sm, --text-base, and --text-caption tokens."""
    return contains(
        "frontend/src/index.css",
        "@theme",
        "--text-caption: 0.8125rem;",
        "--text-sm: 0.9375rem;",
        "--text-base: 1.0625rem;",
    )


def check_09_no_text_xs_or_arbitrary_font_size_in_frontend_src() -> bool:
    """Check 9: No tracked .ts or .tsx under frontend/src holds text-xs or text-[<length>]."""
    return not any(
        FORBIDDEN_TEXT_SIZE_RE.search(read(rel))
        for rel in sorted(tracked("frontend/src"))
        if rel.endswith((".ts", ".tsx"))
    )


def check_10_eslint_config_no_restricted_syntax_type_rule() -> bool:
    """Check 10: frontend/eslint.config.js holds the no-restricted-syntax type rule."""
    return contains(
        "frontend/eslint.config.js",
        '"no-restricted-syntax"',
        "text-xs",
    )


def check_11_ui_primitives_and_native_disclosure_tracked() -> bool:
    """Check 11: frontend/src/ui/ primitives and tests are tracked; Disclosure renders <details."""
    primitives = (
        "Button",
        "Callout",
        "Card",
        "Chip",
        "Disclosure",
        "PageHeader",
        "SectionHeading",
        "StatTile",
    )
    expected_files = [
        *(f"frontend/src/ui/{name}.tsx" for name in primitives),
        *(f"frontend/src/ui/{name}.test.tsx" for name in primitives),
        "frontend/src/ui/threat.ts",
    ]
    disclosure = read("frontend/src/ui/Disclosure.tsx")
    return (
        files_exist(*expected_files)
        and "<details" in disclosure
        and "<summary" in disclosure
        and "radix-ui" not in disclosure
    )


def check_12_nav_items_icons_order_and_aria_describedby() -> bool:
    """Check 12: NAV_ITEMS holds 8 one-line objects with icon after label and aria-describedby."""
    text = read("frontend/src/app/AppShell.tsx")
    matches = NAV_ITEM_LINE_RE.findall(text)
    expected = [
        ("/", "Dashboard"),
        ("/map", "Map"),
        ("/replay", "Replay"),
        ("/storms", "Storms"),
        ("/alerts", "Alerts"),
        ("/timeline", "Timeline"),
        ("/ask", "Ask"),
        ("/settings", "Settings"),
    ]
    return (
        matches == expected
        and "aria-describedby" in text
        and files_exist("frontend/src/app/navStatus.ts", "frontend/src/app/navStatus.test.ts")
    )


def check_13_design_doc_sections_tracked() -> bool:
    """Check 13: docs/DESIGN.md is tracked with token, primitive, type, gate, and CSP sections."""
    return files_exist(DESIGN_DOC) and contains(
        DESIGN_DOC,
        "## Tokens",
        "## Type rules",
        "## Primitives",
        "## Navigation",
        "## Vocabulary",
        "## The readability gate",
        "## Accessibility",
        "## CSP rules",
    )


def check_14_readability_audit_and_spec_tracked() -> bool:
    """Check 14: readability.ts exports auditReadability and readability.spec.ts is wired."""
    return (
        files_exist("frontend/e2e/readability.ts", "frontend/e2e/readability.spec.ts")
        and contains(
            "frontend/e2e/readability.ts",
            "export async function auditReadability",
            "export function readabilityKit",
        )
        and contains(
            "frontend/e2e/readability.spec.ts",
            "width: 1440, height: 900",
            "width: 1280, height: 800",
            "width: 360, height: 740",
            '"8802"',
            '"8806"',
        )
    )


def check_15_readability_contrast_unit_test_tracked() -> bool:
    """Check 15: frontend/e2e/readability.unit.spec.ts is tracked and tests contrastRatio."""
    return files_exist("frontend/e2e/readability.unit.spec.ts") and contains(
        "frontend/e2e/readability.unit.spec.ts",
        "contrastRatio",
        "relativeLuminance",
    )


def check_16_dogfood_doc_carried_findings_table_tracked() -> bool:
    """Check 16: docs/phase08-dogfood.md is tracked with its carried-findings table."""
    return files_exist(DOGFOOD_DOC) and contains(
        DOGFOOD_DOC,
        "## Carried from Steps 2 to 7",
        "| Key | What looks wrong | Step that owns the page |",
    )


def check_17_ladder_service_sync_route_and_web_layering() -> bool:
    """Check 17: services/ladder.py defines ladder_reference, sync /api/ladder, no engine in web."""
    svc_funcs = {
        n.name
        for n in syntax("src/weatherbot/services/ladder.py").body
        if isinstance(n, ast.FunctionDef)
    }
    route_tree = syntax("src/weatherbot/web/routes/ladder.py")
    route_sync = {n.name for n in route_tree.body if isinstance(n, ast.FunctionDef)}
    route_async = {n.name for n in route_tree.body if isinstance(n, ast.AsyncFunctionDef)}
    web_imports_engine = any(
        m == "weatherbot.engine" or m.startswith("weatherbot.engine.")
        for rel in sorted(tracked("src/weatherbot/web"))
        if rel.endswith(".py")
        for m in imported_modules(syntax(rel))
    )
    return (
        "ladder_reference" in svc_funcs
        and "get_ladder" in route_sync
        and "get_ladder" not in route_async
        and contains("src/weatherbot/web/routes/ladder.py", '@router.get("/api/ladder")')
        and contains("src/weatherbot/web/app.py", "ladder_router")
        and not web_imports_engine
    )


def check_18_openapi_ladder_and_fixture_tracked() -> bool:
    """Check 18: openapi.json holds /api/ladder and LadderResponse, and ladder.json is tracked."""
    spec = json_file(OPENAPI_SPEC)
    paths = object_of(spec["paths"])
    schemas = object_of(object_of(spec["components"])["schemas"])
    return (
        "get" in object_of(paths.get("/api/ladder", {}))
        and "LadderResponse" in schemas
        and files_exist("frontend/src/test/fixtures/ladder.json")
    )


def check_19_query_keys_ladder_under_settings() -> bool:
    """Check 19: frontend/src/api/keys.ts holds invalidatableQueryKey('settings', 'ladder')."""
    return contains(
        "frontend/src/api/keys.ts",
        'invalidatableQueryKey("settings", "ladder")',
    )


def check_20_assessment_plain_english_components_and_tests_tracked() -> bool:
    """Check 20: assessment/ holds vocabulary, ThreatMeter, LocationHero, and WhyThisLevel."""
    return files_exist(
        "frontend/src/assessment/vocabulary.ts",
        "frontend/src/assessment/vocabulary.test.ts",
        "frontend/src/assessment/ThreatMeter.tsx",
        "frontend/src/assessment/ThreatMeter.test.tsx",
        "frontend/src/assessment/LocationHero.tsx",
        "frontend/src/assessment/LocationHero.test.tsx",
        "frontend/src/assessment/WhyThisLevel.tsx",
        "frontend/src/assessment/WhyThisLevel.test.tsx",
    )


def check_21_why_this_level_uses_native_disclosure_and_summary() -> bool:
    """Check 21: WhyThisLevel.tsx uses Disclosure and 'Why this level / Official provenance'."""
    return contains(
        "frontend/src/assessment/WhyThisLevel.tsx",
        "Disclosure",
        '"Why this level / Official provenance & controls"',
    )


def check_22_no_legacy_ladder_rules_or_untracked_products_in_frontend_src() -> bool:
    """Check 22: Settings.tsx has no LADDER_RULES and frontend/src has no removed product names."""
    if "LADDER_RULES" in read("frontend/src/pages/Settings.tsx"):
        return False
    forbidden = (
        "tropical_storm_cone",
        "Extreme Wind Warning",
        "Storm Surge Warning",
        "Storm Surge Watch",
    )
    for rel in sorted(tracked("frontend/src")):
        if not rel.endswith((".ts", ".tsx")):
            continue
        text = read(rel)
        if any(token in text for token in forbidden):
            return False
    return True


def check_23_threat_level_badge_has_no_old_fallback_names() -> bool:
    """Check 23: ThreatLevelBadge.tsx holds none of the old fallback level names."""
    text = read("frontend/src/app/ThreatLevelBadge.tsx")
    old_names = (
        "Storm Watch",
        "Awareness",
        "Hurricane Warning / Evacuation",
        "Tropical Storm Warning / Hurricane Watch",
    )
    return not any(name in text for name in old_names)


def check_24_step_3_tests_and_plain_english_spec_tracked() -> bool:
    """Check 24: test_ladder_reference, test_ladder_route, and plain-english.spec.ts exist."""
    return files_exist(
        "tests/services/test_ladder_reference.py",
        "tests/web/test_ladder_route.py",
        "frontend/e2e/plain-english.spec.ts",
    )


def check_25_dashboard_command_center_components_tracked() -> bool:
    """Check 25: frontend/src/dashboard/ holds all five command-center components and tests."""
    names = ("StatusBar", "ExportPopover", "LocationSwitcher", "FeaturedLocation", "MiniMap")
    return files_exist(
        *(f"frontend/src/dashboard/{name}.tsx" for name in names),
        *(f"frontend/src/dashboard/{name}.test.tsx" for name in names),
    )


def check_26_status_bar_countdown_uses_set_timeout_and_visibility_without_interval() -> bool:
    """Check 26: StatusBar countdown uses setTimeout and visibilitychange with no setInterval."""
    text = read("frontend/src/dashboard/StatusBar.tsx")
    has_interval = any(
        "setInterval" in read(rel)
        for rel in sorted(tracked("frontend/src/dashboard"))
        if rel.endswith((".ts", ".tsx")) and not rel.endswith(".test.tsx")
    )
    return (
        "setTimeout" in text
        and ("document.hidden" in text or "visibilitychange" in text)
        and not has_interval
    )


def check_27_export_popover_uses_radix_popover_and_report_controls() -> bool:
    """Check 27: ExportPopover.tsx uses radix-ui Popover and holds export-report-all and AI box."""
    return contains(
        "frontend/src/dashboard/ExportPopover.tsx",
        'from "radix-ui"',
        "Popover",
        '"export-report-all"',
        "Include the AI briefing",
    )


def check_28_mini_map_uses_leaflet_hook_without_own_tile_layer() -> bool:
    """Check 28: MiniMap.tsx calls useLeafletMap and adds no tileLayer of its own."""
    text = read("frontend/src/dashboard/MiniMap.tsx")
    return "useLeafletMap(" in text and "tileLayer" not in text


def check_29_dashboard_retains_live_region_and_heading() -> bool:
    """Check 29: Dashboard.tsx holds level-live-region and a Dashboard heading."""
    return contains(
        "frontend/src/pages/Dashboard.tsx",
        '"level-live-region"',
        "Dashboard",
    )


def check_30_command_center_spec_tracked() -> bool:
    """Check 30: frontend/e2e/command-center.spec.ts is tracked."""
    return files_exist("frontend/e2e/command-center.spec.ts")


def check_31_map_view_removes_legacy_replay_panel() -> bool:
    """Check 31: MapView.tsx and MapPanels.tsx hold none of the legacy replay-panel test IDs."""
    text = read("frontend/src/map/MapView.tsx") + "\n" + read("frontend/src/map/MapPanels.tsx")
    forbidden = (
        "replay-panel",
        "replay-storm-select",
        "replay-advisory-select",
        "replay-not-live-banner",
    )
    return not any(tok in text for tok in forbidden)


def check_32_map_hud_panels_layer_groups_and_single_advisory_slider_id() -> bool:
    """Check 32: Map panels hold aria-expanded, labels, 70vh, LAYER_GROUPS, and sole slider ID."""
    map_text = read("frontend/src/map/MapView.tsx") + "\n" + read("frontend/src/map/MapPanels.tsx")
    slider_files = [
        rel
        for rel in sorted(tracked("frontend/src"))
        if rel.endswith((".ts", ".tsx"))
        and not rel.endswith((".test.ts", ".test.tsx"))
        and "advisory-slider-panel" in read(rel)
    ]
    return (
        all(
            tok in map_text
            for tok in ("aria-expanded", "Map layer toggles", "Map legend", "min-h-[70vh]")
        )
        and contains("frontend/src/map/layers.ts", "LAYER_GROUPS")
        and slider_files == ["frontend/src/map/AdvisorySlider.tsx"]
    )


def check_33_map_spec_tracked_and_tests_live_canvas() -> bool:
    """Check 33: map.spec.ts is tracked, holds leaflet-map-container, and no replay select."""
    if not files_exist("frontend/e2e/map.spec.ts"):
        return False
    text = read("frontend/e2e/map.spec.ts")
    return "leaflet-map-container" in text and "replay-storm-select" not in text


def check_34_map_links_to_replay_route() -> bool:
    """Check 34: MapView.tsx or MapPanels.tsx links to /replay."""
    text = read("frontend/src/map/MapView.tsx") + "\n" + read("frontend/src/map/MapPanels.tsx")
    return 'to="/replay"' in text


def check_35_map_directory_imports_no_radix_popover_or_dialog() -> bool:
    """Check 35: Nothing under frontend/src/map/ imports a Radix Popover or Dialog."""
    for rel in sorted(tracked("frontend/src/map")):
        if not rel.endswith((".ts", ".tsx")):
            continue
        text = read(rel)
        if "radix-ui" in text or "Popover" in text or "Dialog" in text:
            return False
    return True


def check_36_replay_page_uses_hero_disclosure_and_two_column_workbench() -> bool:
    """Check 36: Replay.tsx holds LocationHero, WhyThisLevel, and an xl:grid-cols-2 workbench."""
    return contains(
        "frontend/src/pages/Replay.tsx",
        "LocationHero",
        "WhyThisLevel",
        "xl:grid-cols-2",
    )


def check_37_replay_spec_asserts_1440x900_first_viewport_boxes() -> bool:
    """Check 37: replay.spec.ts holds a 1440x900 viewport and boundingBox() assertions."""
    return contains(
        "frontend/e2e/replay.spec.ts",
        "width: 1440, height: 900",
        "boundingBox()",
    )


def check_38_replay_unit_test_tracked() -> bool:
    """Check 38: frontend/src/pages/Replay.test.tsx is tracked."""
    return files_exist("frontend/src/pages/Replay.test.tsx")


def check_39_tabs_primitive_wai_aria_roles_and_no_radix() -> bool:
    """Check 39: Tabs.tsx holds WAI-ARIA tab roles, imports no Radix, and has Tabs.test.tsx."""
    if not files_exist("frontend/src/ui/Tabs.tsx", "frontend/src/ui/Tabs.test.tsx"):
        return False
    text = read("frontend/src/ui/Tabs.tsx")
    return (
        all(
            tok in text
            for tok in ('role="tablist"', 'role="tab"', 'role="tabpanel"', "aria-selected")
        )
        and "radix-ui" not in text
    )


def check_40_settings_page_five_hashes_router_sync_and_components() -> bool:
    """Check 40: Settings.tsx holds all 6 hashes, useLocation/useNavigate replace, and 4 panels."""
    text = read("frontend/src/pages/Settings.tsx")
    return (
        contains(
            "frontend/src/pages/Settings.tsx",
            '"#locations"',
            '"#notifications"',
            '"#ai"',
            '"#retention"',
            '"#about"',
            '"disclaimer"',
            "useLocation",
            "useNavigate",
            "replace: true",
            "LocationManager",
            "NotificationChannels",
            "QuietHoursForm",
            "RetentionPanel",
        )
        and "history.replaceState" not in text
    )


def check_41_ask_page_holds_starter_prompt_chips() -> bool:
    """Check 41: Ask.tsx holds the four starter prompt chips (ask-chip-1..4)."""
    return contains(
        "frontend/src/pages/Ask.tsx",
        '"ask-chip-1"',
        '"ask-chip-2"',
        '"ask-chip-3"',
        '"ask-chip-4"',
    )


def check_42_storms_alerts_and_timeline_use_disclosure() -> bool:
    """Check 42: Storms.tsx, Alerts.tsx, and Timeline.tsx use the Disclosure primitive."""
    return all(
        contains(rel, "Disclosure")
        for rel in (
            "frontend/src/pages/Storms.tsx",
            "frontend/src/pages/Alerts.tsx",
            "frontend/src/pages/Timeline.tsx",
        )
    )


def check_43_settings_tabs_e2e_spec_tracked() -> bool:
    """Check 43: frontend/e2e/settings-tabs.spec.ts is tracked."""
    return files_exist("frontend/e2e/settings-tabs.spec.ts")


def check_44_readability_spec_names_every_settings_hash() -> bool:
    """Check 44: readability.spec.ts names each of the five Settings tab hashes."""
    return contains(
        "frontend/e2e/readability.spec.ts",
        '"/settings#locations"',
        '"/settings#notifications"',
        '"/settings#ai"',
        '"/settings#retention"',
        '"/settings#about"',
    )


def check_45_dogfood_spec_tagged_and_covers_matrix() -> bool:
    """Check 45: dogfood.spec.ts is tracked, tagged @dogfood, and covers 5 scenarios & 2 sizes."""
    if not files_exist("frontend/e2e/dogfood.spec.ts", "frontend/e2e/dogfood-setup.ts"):
        return False
    text = read("frontend/e2e/dogfood.spec.ts")
    test_calls = re.findall(r"\btest\s*\(\s*[`\"']([^`\"']+)", text)
    return (
        bool(test_calls)
        and all("@dogfood" in title for title in test_calls)
        and contains(
            "frontend/e2e/dogfood.spec.ts",
            '"quiet"',
            '"outlook"',
            '"cone"',
            '"watch"',
            '"landfall"',
            "width: 1440, height: 900",
            "width: 390, height: 844",
            '"light"',
            '"dark"',
        )
    )


def check_46_playwright_config_dogfood_isolation_and_package_script() -> bool:
    """Check 46: playwright.config.ts excludes @dogfood by default and starts 8803..8805 for it."""
    scripts = object_of(json_file("frontend/package.json")["scripts"])
    return (
        contains(
            "frontend/playwright.config.ts",
            "/@idle|@dogfood/",
            "isDogfoodRun",
            '"8803"',
            '"8804"',
            '"8805"',
        )
        and "e2e:dogfood" in scripts
    )


def check_47_dogfood_ledger_rubric_clean_round_and_idle_receipt() -> bool:
    """Check 47: docs/phase08-dogfood.md holds rubric, round log, defects, 240 round, and idle."""
    return contains(
        DOGFOOD_DOC,
        "## Loop 1 rubric",
        "### Round log",
        "### Defects",
        "240 / 240",
        "0 / 0 / 0 / 0",
        "budget=<0.5%",
    )


def check_48_phase8_e2e_spec_tracked() -> bool:
    """Check 48: frontend/e2e/phase8.spec.ts is tracked."""
    return files_exist("frontend/e2e/phase8.spec.ts")


def check_49_no_extra_tracked_images_under_frontend() -> bool:
    """Check 49: No image is tracked under frontend/ except blank-tile.png and frontend/public/."""
    image_exts = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico")
    extra_images = [
        rel
        for rel in sorted(tracked("frontend"))
        if rel.lower().endswith(image_exts) and not rel.startswith("frontend/public/")
    ]
    return extra_images == ["frontend/e2e/blank-tile.png"]


def check_50_appshell_test_covers_stale_banner_and_reconnecting_chip() -> bool:
    """Check 50: AppShell.test.tsx covers the stale-monitor banner and Reconnecting… status chip."""
    return contains(
        "frontend/src/app/AppShell.test.tsx",
        "Stale monitor data:",
        "Reconnecting…",
    )


def check_51_dogfood_loop_2_round_and_dated_sign_off() -> bool:
    """Check 51: docs/phase08-dogfood.md Loop 2 section holds a round and dated sign-off."""
    loop2 = markdown_section(read(DOGFOOD_DOC), "## Loop 2 — operator dogfood")
    return (
        "### Loop 2 round log" in loop2
        and "| 1 | 2026-11-17 |" in loop2
        and bool(re.search(r"Operator sign-off \(\d{4}-\d{2}-\d{2}\):", loop2))
    )


def check_52_readme_status_names_phase_08_complete_and_changelog_documents_it() -> bool:
    """Check 52: README.md Status names Phase 8 complete and Phase 9 next, and CHANGELOG has it."""
    status = markdown_section(read("README.md"), "## Status")
    return (
        "Phase 8 (UI/UX redesign and visual\ndogfooding) are complete" in status
        and "Phase 9 (Release 2.0) is next" in status
        and contains("CHANGELOG.md", "### Phase 8 — UI/UX redesign and visual dogfooding")
    )


def check_53_roadmap_release_table_lists_v2_phase_8_tag() -> bool:
    """Check 53: docs/roadmap/ROADMAP.md Release & tagging table lists v2.0.0-phase-8."""
    section = markdown_section(read(ROADMAP), "#### Release & tagging")
    return "| `v2.0.0-phase-8`" in section


def check_54_readme_dashboard_section_names_phase_08_surfaces() -> bool:
    """Check 54: README.md ### The dashboard names switcher, map panels, workbench, and tabs."""
    dashboard = markdown_section(read("README.md"), "### The dashboard")
    return all(
        tok in dashboard
        for tok in ("LocationSwitcher", "MapPanels", "replay workbench", "Settings tabs")
    )


def check_55_verify_phase08_self_check() -> bool:
    """Check 55: verify_phase08.py self-check (60 checks, 38 V rows, 8 modes, nested '107')."""
    rel = "scripts/verify_phase08.py"
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
        and EXPECTED_PHASE_07_POST_TOTAL == "107"
        and all(f'"{mode}"' in text for mode in MODES)
    )


def check_56_phase08_qa_findings_ledger() -> bool:
    """Check 56: docs/phase08-qa-findings.md exists with every required rollup section."""
    return files_exist(QA_FINDINGS) and contains(
        QA_FINDINGS,
        "## PR #110 — Phase 8 Roadmap",
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
        "## Dogfood summary",
        "## 600-second idle CPU measurement",
        "## Live and browser smoke runs",
        "## Nested post-verification sweep duration",
        "## Exact vs. growth-proof Phase 8 checks for Phase 9",
        "## Pre-ship items",
    )


def check_57_phase08_roadmap_and_project_roadmap() -> bool:
    """Check 57: docs/roadmap/phase08-roadmap.md (Steps 1-10) and ROADMAP.md Phase 8 exist."""
    if not files_exist(PHASE_ROADMAP, ROADMAP):
        return False
    p8 = read(PHASE_ROADMAP)
    return all(f"## Step {n} —" in p8 for n in range(1, 11)) and contains(
        ROADMAP, "### Phase 8 — UI/UX redesign and visual dogfooding"
    )


def check_58_phase_verify_workflow_includes_08() -> bool:
    """Check 58: phase-verify.yml includes 01..08 and separate Node steps for 05, 06, 07, and 08."""
    text = read(PHASE_WORKFLOW)
    m = re.search(r"phase:\s*\[([^\n\]]+)\]", text)
    if m is None:
        return False
    phases = tuple(
        item.strip().strip('"').strip("'") for item in m.group(1).split(",") if item.strip()
    )
    return phases[:8] == EXPECTED_PHASE_MATRIX_PREFIX and contains(
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
        "- name: Set up Node (Phase 8)\n        if: \"!cancelled() && matrix.phase == '08'\"",
        "- name: Install frontend dependencies (Phase 8)\n"
        "        if: \"!cancelled() && matrix.phase == '08'\"",
        "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0",
    )


def check_59_security_gate_and_no_secret_shapes() -> bool:
    """Check 59: Security hooks/workflow are wired and no secret shape appears in Phase 8 paths."""
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
        and _no_secret_shape_in_phase08_paths()
    )


def check_60_no_binary_files_under_frontend_src_or_web() -> bool:
    """Check 60: No binary file is tracked under frontend/src or src/weatherbot/web."""
    for prefix in ("frontend/src", "src/weatherbot/web"):
        for rel in sorted(tracked(prefix)):
            try:
                text = read(rel)
            except UnicodeDecodeError:
                return False
            if "\x00" in text:
                return False
    return True


STATIC_CHECKS: Final[tuple[Check, ...]] = (
    (
        "scripts/demo_storm.py and demo_scenarios.py are tracked and SCENARIOS names all 5",
        check_01_demo_storm_and_scenarios_tracked,
    ),
    (
        "SCENARIOS in scripts/demo_scenarios.py matches Decision 2's table by AST",
        check_02_scenarios_match_decision_2_table,
    ),
    (
        "scripts/serve_demo.py holds --scenario beside --switch-file and keeps top-level symbols",
        check_03_serve_demo_scenario_flag_and_top_level_definitions,
    ),
    (
        "demo_storm.py and demo_scenarios.py use <=2 decimals, label synthetic, and src/ has none",
        check_04_two_decimal_synthetic_geometry_and_no_src_synthetic,
    ),
    (
        "frontend/playwright.config.ts holds 8802 and 8806 beside 8799..8801 and scenarios.spec.ts",
        check_05_playwright_config_scenario_ports_and_spec,
    ),
    (
        "Scenario tests, record_ai_fixtures.py --scenario, and 12 manifest recordings are tracked",
        check_06_scenario_tests_recorder_and_manifest_entries,
    ),
    (
        "scripts/verify_phase07.py Check 59 reads tagged('README.md', tag=PHASE_7_TAG) with tests",
        check_07_verify_phase07_check_59_reads_tagged_readme,
    ),
    (
        "frontend/src/index.css @theme sets --text-caption, --text-sm, and --text-base tokens",
        check_08_index_css_theme_type_tokens,
    ),
    (
        "No tracked .ts or .tsx under frontend/src holds text-xs or an arbitrary font size",
        check_09_no_text_xs_or_arbitrary_font_size_in_frontend_src,
    ),
    (
        "frontend/eslint.config.js holds the no-restricted-syntax type-scale rule",
        check_10_eslint_config_no_restricted_syntax_type_rule,
    ),
    (
        "frontend/src/ui/ primitives and tests are tracked and Disclosure renders <details>",
        check_11_ui_primitives_and_native_disclosure_tracked,
    ),
    (
        "NAV_ITEMS holds 8 one-line objects with icon after label and aria-describedby badges",
        check_12_nav_items_icons_order_and_aria_describedby,
    ),
    (
        "docs/DESIGN.md is tracked with token, type, primitive, vocabulary, gate, and CSP sections",
        check_13_design_doc_sections_tracked,
    ),
    (
        "frontend/e2e/readability.ts exports auditReadability and readability.spec.ts is wired",
        check_14_readability_audit_and_spec_tracked,
    ),
    (
        "frontend/e2e/readability.unit.spec.ts is tracked and tests WCAG contrast arithmetic",
        check_15_readability_contrast_unit_test_tracked,
    ),
    (
        "docs/phase08-dogfood.md is tracked with its carried-findings table",
        check_16_dogfood_doc_carried_findings_table_tracked,
    ),
    (
        "services/ladder.py defines ladder_reference, sync GET /api/ladder, web imports no engine",
        check_17_ladder_service_sync_route_and_web_layering,
    ),
    (
        "docs/api/openapi.json declares /api/ladder and LadderResponse, and ladder.json is tracked",
        check_18_openapi_ladder_and_fixture_tracked,
    ),
    (
        "frontend/src/api/keys.ts holds invalidatableQueryKey('settings', 'ladder')",
        check_19_query_keys_ladder_under_settings,
    ),
    (
        "frontend/src/assessment/ holds vocabulary, ThreatMeter, LocationHero, and WhyThisLevel",
        check_20_assessment_plain_english_components_and_tests_tracked,
    ),
    (
        "WhyThisLevel.tsx uses Disclosure with 'Why this level / Official provenance & controls'",
        check_21_why_this_level_uses_native_disclosure_and_summary,
    ),
    (
        "Settings.tsx has no LADDER_RULES and frontend/src has no removed rule or product names",
        check_22_no_legacy_ladder_rules_or_untracked_products_in_frontend_src,
    ),
    (
        "ThreatLevelBadge.tsx holds none of the old fallback level names",
        check_23_threat_level_badge_has_no_old_fallback_names,
    ),
    (
        "test_ladder_reference.py, test_ladder_route.py, and plain-english.spec.ts are tracked",
        check_24_step_3_tests_and_plain_english_spec_tracked,
    ),
    (
        "frontend/src/dashboard/ holds StatusBar, ExportPopover, LocationSwitcher, and MiniMap",
        check_25_dashboard_command_center_components_tracked,
    ),
    (
        "StatusBar countdown uses setTimeout and document.hidden with no setInterval",
        check_26_status_bar_countdown_uses_set_timeout_and_visibility_without_interval,
    ),
    (
        "ExportPopover.tsx uses radix-ui Popover and holds export-report-all and AI checkbox",
        check_27_export_popover_uses_radix_popover_and_report_controls,
    ),
    (
        "MiniMap.tsx calls useLeafletMap and adds no tile layer of its own",
        check_28_mini_map_uses_leaflet_hook_without_own_tile_layer,
    ),
    (
        "Dashboard.tsx holds level-live-region and a Dashboard heading",
        check_29_dashboard_retains_live_region_and_heading,
    ),
    (
        "frontend/e2e/command-center.spec.ts is tracked",
        check_30_command_center_spec_tracked,
    ),
    (
        "MapView.tsx and MapPanels.tsx hold none of the legacy replay-panel test IDs",
        check_31_map_view_removes_legacy_replay_panel,
    ),
    (
        "Map panels hold aria-expanded, labels, 70vh, LAYER_GROUPS, and sole advisory-slider-panel",
        check_32_map_hud_panels_layer_groups_and_single_advisory_slider_id,
    ),
    (
        "frontend/e2e/map.spec.ts is tracked, holds leaflet-map-container, and no replay select",
        check_33_map_spec_tracked_and_tests_live_canvas,
    ),
    (
        "MapView.tsx or MapPanels.tsx links to /replay",
        check_34_map_links_to_replay_route,
    ),
    (
        "Nothing under frontend/src/map/ imports a Radix Popover or Dialog",
        check_35_map_directory_imports_no_radix_popover_or_dialog,
    ),
    (
        "Replay.tsx holds LocationHero, WhyThisLevel, and an xl:grid-cols-2 two-column grid",
        check_36_replay_page_uses_hero_disclosure_and_two_column_workbench,
    ),
    (
        "replay.spec.ts holds a 1440x900 viewport and boundingBox() assertions",
        check_37_replay_spec_asserts_1440x900_first_viewport_boxes,
    ),
    (
        "frontend/src/pages/Replay.test.tsx is tracked",
        check_38_replay_unit_test_tracked,
    ),
    (
        "frontend/src/ui/Tabs.tsx holds WAI-ARIA tab roles, no Radix, and Tabs.test.tsx is tracked",
        check_39_tabs_primitive_wai_aria_roles_and_no_radix,
    ),
    (
        "Settings.tsx holds all 6 hashes, useLocation/useNavigate replace, and 4 settings panels",
        check_40_settings_page_five_hashes_router_sync_and_components,
    ),
    (
        "Ask.tsx holds the four starter prompt chips (ask-chip-1..4)",
        check_41_ask_page_holds_starter_prompt_chips,
    ),
    (
        "Storms.tsx, Alerts.tsx, and Timeline.tsx use the Disclosure primitive",
        check_42_storms_alerts_and_timeline_use_disclosure,
    ),
    (
        "frontend/e2e/settings-tabs.spec.ts is tracked",
        check_43_settings_tabs_e2e_spec_tracked,
    ),
    (
        "frontend/e2e/readability.spec.ts names each of the five Settings tab hashes",
        check_44_readability_spec_names_every_settings_hash,
    ),
    (
        "frontend/e2e/dogfood.spec.ts is tracked, tagged @dogfood, and covers 5 scenarios/2 sizes",
        check_45_dogfood_spec_tagged_and_covers_matrix,
    ),
    (
        "playwright.config.ts excludes @dogfood by default, starts 8803..8805, and has e2e:dogfood",
        check_46_playwright_config_dogfood_isolation_and_package_script,
    ),
    (
        "docs/phase08-dogfood.md holds the rubric, round log, defects, clean 240 round, and idle",
        check_47_dogfood_ledger_rubric_clean_round_and_idle_receipt,
    ),
    (
        "frontend/e2e/phase8.spec.ts is tracked",
        check_48_phase8_e2e_spec_tracked,
    ),
    (
        "No image is tracked under frontend/ except blank-tile.png and frontend/public/ assets",
        check_49_no_extra_tracked_images_under_frontend,
    ),
    (
        "AppShell.test.tsx covers the stale-monitor banner and Reconnecting… status chip",
        check_50_appshell_test_covers_stale_banner_and_reconnecting_chip,
    ),
    (
        "docs/phase08-dogfood.md Loop 2 section holds a round and a dated operator sign-off",
        check_51_dogfood_loop_2_round_and_dated_sign_off,
    ),
    (
        "README.md ## Status names Phase 8 complete and Phase 9 next, and CHANGELOG documents it",
        check_52_readme_status_names_phase_08_complete_and_changelog_documents_it,
    ),
    (
        "docs/roadmap/ROADMAP.md Release & tagging table lists v2.0.0-phase-8",
        check_53_roadmap_release_table_lists_v2_phase_8_tag,
    ),
    (
        "README.md ### The dashboard names the switcher, map panels, replay workbench, and tabs",
        check_54_readme_dashboard_section_names_phase_08_surfaces,
    ),
    (
        "scripts/verify_phase08.py self-check (60 static checks, 38 V rows, 8 modes, nested '107')",
        check_55_verify_phase08_self_check,
    ),
    (
        "docs/phase08-qa-findings.md exists with every required rollup section",
        check_56_phase08_qa_findings_ledger,
    ),
    (
        "docs/roadmap/phase08-roadmap.md (Steps 1-10) and ROADMAP.md Phase 8 exist",
        check_57_phase08_roadmap_and_project_roadmap,
    ),
    (
        ".github/workflows/phase-verify.yml includes 01..08 and separate Node steps for 05..08",
        check_58_phase_verify_workflow_includes_08,
    ),
    (
        "Security hooks/workflow are wired and no secret shape appears in Phase 8 paths",
        check_59_security_gate_and_no_secret_shapes,
    ),
    (
        "No binary file is tracked under frontend/src or src/weatherbot/web",
        check_60_no_binary_files_under_frontend_src_or_web,
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
    junit_dir = tmp_dir or Path(tempfile.mkdtemp(prefix="weatherbot-verify08-py-"))
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
    junit_dir = tmp_dir or Path(tempfile.mkdtemp(prefix="weatherbot-verify08-node-"))
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
    """Run Playwright Chromium browser smoke (--ui, default e2e run) with JUnit XML."""
    heading("Playwright Chromium browser smoke (--ui)")
    if not (REPO_ROOT / "src/weatherbot/web/static/index.html").is_file():
        run_command(
            "ui.build",
            "npm --prefix frontend run build",
            ["npm", "--prefix", FRONTEND, "run", "build"],
        )
    junit_dir = tmp_dir or Path(tempfile.mkdtemp(prefix="weatherbot-verify08-ui-"))
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
    """Run ``pytest -m live`` (landmarks only)."""
    heading("Live service smoke tests (--live)")
    junit = (tmp_dir or Path(tempfile.mkdtemp(prefix="weatherbot-verify08-live-"))) / "live.xml"
    outcome = run_command(
        "live.pytest",
        "pytest -m live",
        ["uv", "run", "pytest", "-m", "live", f"--junitxml={junit}"],
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
    # Issue #121 tracks unpatched picomatch <= 4.0.7 (GHSA-fc5q-39xc-vjpf) in
    # devDependencies (vite/vitest); --omit=dev audits production dependencies
    # until upstream releases a patched picomatch version.
    results.append(
        run_command(
            "sec.npm_audit",
            "npm --prefix frontend audit --audit-level=high --omit=dev",
            ["npm", "--prefix", FRONTEND, "audit", "--audit-level=high", "--omit=dev"],
        )
    )
    results.append(
        run_command(
            "sec.frontend_lint",
            "npm --prefix frontend run lint (--max-warnings 0)",
            ["npm", "--prefix", FRONTEND, "run", "lint"],
        )
    )
    secret_clean = _no_secret_shape_in_phase08_paths()
    results.append(
        report(
            Outcome(
                "sec.secret_shape_scan",
                "no Anthropic key or ntfy token shape under Phase 8 paths",
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


def verify_phase07_post() -> bool:
    """Phase 7's own ``--post`` exits 0 with all 107 checks passing; only its totals print."""
    started = time.monotonic()
    result = capture(
        ["uv", "run", "python", "scripts/verify_phase07.py", "--post"],
        timeout=NESTED_SWEEP_TIMEOUT_SECONDS,
        env=_operator_secret_env(),
    )
    elapsed = time.monotonic() - started
    totals = dict(
        re.findall(r"^  (passed|failed|skipped|total)\s+(\d+)$", result.stdout, re.MULTILINE)
    )
    for line in result.stdout.splitlines():
        if line.lstrip().startswith(("[FAIL]", "[SKIP]")) or "verify_phase0" in line:
            print(f"    {line}")
    print(
        f"  verify_phase07.py --post: {totals or 'no summary'} in {elapsed:.1f}s; "
        f"exit {result.returncode}"
    )
    return result.returncode == 0 and totals == {
        "passed": EXPECTED_PHASE_07_POST_TOTAL,
        "failed": "0",
        "skipped": "0",
        "total": EXPECTED_PHASE_07_POST_TOTAL,
    }


def dogfood_probe() -> bool:
    """V8.2: npm --prefix frontend run e2e:dogfood renders 240 views with zero audit findings."""
    started = time.monotonic()
    result = capture(
        ["npm", "--prefix", FRONTEND, "run", "e2e:dogfood"],
        timeout=1800,
    )
    elapsed = time.monotonic() - started
    audit_path = REPO_ROOT / "frontend/test-results/dogfood/audit.json"
    if not audit_path.is_file():
        print(f"  e2e:dogfood: missing audit.json in {elapsed:.1f}s (exit {result.returncode})")
        return False
    audit_doc = object_of(json.loads(audit_path.read_text(encoding="utf-8")))
    renders = [object_of(item) for item in array_of(audit_doc.get("renders", []))]
    finding_count = sum(len(array_of(r.get("findings", []))) for r in renders)
    print(
        f"  e2e:dogfood: renders={len(renders)}/{audit_doc.get('expected_renders')}, "
        f"findings={finding_count} in {elapsed:.1f}s (exit {result.returncode})"
    )
    return (
        result.returncode == 0
        and audit_doc.get("expected_renders") == EXPECTED_DOGFOOD_RENDERS
        and len(renders) == EXPECTED_DOGFOOD_RENDERS
        and finding_count == 0
    )


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
    with tempfile.TemporaryDirectory(prefix="weatherbot-installed-doc08-") as tmp:
        result = subprocess.run(  # noqa: S603 - fixed tool path, no shell  # nosec B603
            argv,
            cwd=Path(tmp),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=120,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
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


def operator_health_ui_build() -> bool:
    """V9.2: operator /api/health names the built index.html SHA-256 at DB head 0010."""
    index_path = REPO_ROOT / "src/weatherbot/web/static/index.html"
    if not index_path.is_file():
        return False
    expected_sha = hashlib.sha256(index_path.read_bytes()).hexdigest()[:12]
    health = _fetch_operator_json("/api/health")
    db = object_of(health.get("database", {}))
    ui = object_of(health.get("ui", {}))
    print(
        f"  /api/health: revision={db.get('revision')}, head={db.get('head')}, "
        f"current={db.get('current')}, ui.present={ui.get('present')}, "
        f"ui.index_sha256={ui.get('index_sha256')} (expected {expected_sha})"
    )
    return (
        db.get("current") is True
        and descends_from(str(db.get("head", "")), "0010")
        and ui.get("present") is True
        and ui.get("index_sha256") == expected_sha
    )


def operator_doctor_web() -> bool:
    """V9.3: operator's installed weatherbot doctor --offline --json passes web."""
    _, doc_data = _installed_tool_doctor(offline=True)
    checks = {
        str(object_of(c)["name"]): str(object_of(c)["status"])
        for c in array_of(doc_data.get("checks", []))
    }
    print(f"  doctor --offline: web={checks.get('web')}, migrations={checks.get('migrations')}")
    return checks.get("web") == "pass" and checks.get("migrations") == "pass"


def measure_idle_probe() -> bool:
    """V4.4: scripts/measure_idle.py reports both shares < 0.5% with retention and AI ready."""
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
    """V10.1: scripts/verify_phase08.py --fast passes all 60 checks in under 30 seconds."""
    started = time.monotonic()
    result = capture(["uv", "run", "python", "scripts/verify_phase08.py", "--fast"], timeout=60)
    elapsed = time.monotonic() - started
    totals = dict(
        re.findall(r"^  (passed|failed|skipped|total)\s+(\d+)$", result.stdout, re.MULTILINE)
    )
    print(f"  verify_phase08.py --fast: {totals or 'no summary'} in {elapsed:.2f}s")
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
# 38 V1-V10 Post-Implementation Verification Matrix Rows
# ---------------------------------------------------------------------------


V_MATRIX: tuple[VRow, ...] = (
    # V1 — Demonstration scenarios (5 rows)
    VRow(
        "V1.1",
        "V1 — Demonstration scenarios",
        "Static checks 1-7 all PASS",
        ("static_01_07",),
    ),
    VRow(
        "V1.2",
        "V1 — Demonstration scenarios",
        "Scenario tests: every level and rule, offline, two decimals",
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
            Select(
                "tests.scripts.test_demo_scenarios",
                "tests.scripts.test_demo_storm",
                "tests.scripts.test_record_ai_fixtures",
                "tests.ai.test_ai_fixtures",
            ),
        ),
    ),
    VRow(
        "V1.3",
        "V1 — Demonstration scenarios",
        "test_serve_demo.py: the default unchanged, the new flag",
        (Select("tests.scripts.test_serve_demo"),),
    ),
    VRow(
        "V1.4",
        "V1 — Demonstration scenarios",
        "scenarios.spec.ts renders the quiet and landfall servers",
        ("playwright_ui", Select("scenarios.spec.ts")),
    ),
    VRow(
        "V1.5",
        "V1 — Demonstration scenarios",
        "verify_phase07.py --post passes all 107 (and 6 to 1)",
        ("verify_phase07_post",),
    ),
    # V2 — The design system and readable type (4 rows)
    VRow(
        "V2.1",
        "V2 — The design system and readable type",
        "Static checks 8-16 all PASS",
        ("static_08_16",),
    ),
    VRow(
        "V2.2",
        "V2 — The design system and readable type",
        "The ui/ primitives' tests and AppShell.test.tsx pass",
        (
            Select(
                "src/ui/Button.test.tsx",
                "src/ui/Callout.test.tsx",
                "src/ui/Card.test.tsx",
                "src/ui/Chip.test.tsx",
                "src/ui/Disclosure.test.tsx",
                "src/ui/PageHeader.test.tsx",
                "src/ui/SectionHeading.test.tsx",
                "src/ui/StatTile.test.tsx",
                "src/app/AppShell.test.tsx",
                "src/app/navStatus.test.ts",
            ),
        ),
    ),
    VRow(
        "V2.3",
        "V2 — The design system and readable type",
        "readability.spec.ts: no finding on any render",
        (Select("readability.spec.ts", "readability.unit.spec.ts"),),
    ),
    VRow(
        "V2.4",
        "V2 — The design system and readable type",
        "--node exits 0: lint with the type rule, build, licences",
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
        ),
    ),
    # V3 — Plain English and one vocabulary (5 rows)
    VRow(
        "V3.1",
        "V3 — Plain English and one vocabulary",
        "Static checks 17-24 all PASS",
        ("static_17_24",),
    ),
    VRow(
        "V3.2",
        "V3 — Plain English and one vocabulary",
        "The ladder service and route tests pass; no location data",
        (
            Select(
                "tests.services.test_ladder_reference",
                "tests.web.test_ladder_route",
                "tests.web.test_api_privacy",
            ),
        ),
    ),
    VRow(
        "V3.3",
        "V3 — Plain English and one vocabulary",
        "The OpenAPI and fixture exporters' --check pass",
        (
            "export_schemas_check",
            "export_openapi_check",
            "export_api_fixtures_check",
            Select("tests.web.test_openapi_export", "tests.web.test_api_fixtures"),
        ),
    ),
    VRow(
        "V3.4",
        "V3 — Plain English and one vocabulary",
        "The assessment components' Vitest files pass",
        (
            Select(
                "src/assessment/vocabulary.test.ts",
                "src/assessment/ThreatMeter.test.tsx",
                "src/assessment/LocationHero.test.tsx",
                "src/assessment/WhyThisLevel.test.tsx",
                "src/assessment/assessment.test.tsx",
            ),
        ),
    ),
    VRow(
        "V3.5",
        "V3 — Plain English and one vocabulary",
        "plain-english.spec.ts and replay.spec.ts pass",
        (Select("plain-english.spec.ts", "replay.spec.ts"),),
    ),
    # V4 — The command-center dashboard (4 rows)
    VRow(
        "V4.1",
        "V4 — The command-center dashboard",
        "Static checks 25-30 all PASS",
        ("static_25_30",),
    ),
    VRow(
        "V4.2",
        "V4 — The command-center dashboard",
        "Dashboard.test.tsx and the dashboard components' tests",
        (
            Select(
                "src/pages/Dashboard.test.tsx",
                "src/dashboard/StatusBar.test.tsx",
                "src/dashboard/ExportPopover.test.tsx",
                "src/dashboard/LocationSwitcher.test.tsx",
                "src/dashboard/FeaturedLocation.test.tsx",
                "src/dashboard/MiniMap.test.tsx",
            ),
        ),
    ),
    VRow(
        "V4.3",
        "V4 — The command-center dashboard",
        "command-center, dashboard, report, ai specs pass",
        (
            Select(
                "command-center.spec.ts",
                "dashboard.spec.ts",
                "report.spec.ts",
                "ai.spec.ts",
                "charts.spec.ts",
            ),
        ),
    ),
    VRow(
        "V4.4",
        "V4 — The command-center dashboard",
        "Server and tab each stay under 0.5% of a core idle",
        ("measure_idle_probe",),
    ),
    # V5 — The immersive map (3 rows)
    VRow(
        "V5.1",
        "V5 — The immersive map",
        "Static checks 31-35 all PASS",
        ("static_31_35",),
    ),
    VRow(
        "V5.2",
        "V5 — The immersive map",
        "MapView.test.tsx and layers.test.ts pass",
        (
            Select(
                "src/map/MapView.test.tsx",
                "src/map/layers.test.ts",
                "src/map/AdvisorySlider.test.tsx",
            ),
        ),
    ),
    VRow(
        "V5.3",
        "V5 — The immersive map",
        "map.spec.ts and layers.spec.ts pass",
        (Select("map.spec.ts", "layers.spec.ts"),),
    ),
    # V6 — The replay workbench (3 rows)
    VRow(
        "V6.1",
        "V6 — The replay workbench",
        "Static checks 36-38 all PASS",
        ("static_36_38",),
    ),
    VRow(
        "V6.2",
        "V6 — The replay workbench",
        "Replay.test.tsx passes",
        (Select("src/pages/Replay.test.tsx", "src/charts/LevelHistoryChart.test.tsx"),),
    ),
    VRow(
        "V6.3",
        "V6 — The replay workbench",
        "replay.spec.ts: map, slider, headline in the first view",
        (Select("replay.spec.ts"),),
    ),
    # V7 — Sectioned settings and the secondary pages (3 rows)
    VRow(
        "V7.1",
        "V7 — Sectioned settings and the secondary pages",
        "Static checks 39-44 all PASS",
        ("static_39_44",),
    ),
    VRow(
        "V7.2",
        "V7 — Sectioned settings and the secondary pages",
        "Tabs, Settings, Ask, and the list pages' tests pass",
        (
            Select(
                "src/ui/Tabs.test.tsx",
                "src/pages/Settings.test.tsx",
                "src/pages/Ask.test.tsx",
                "src/pages/Storms.test.tsx",
                "src/pages/Alerts.test.tsx",
                "src/pages/Timeline.test.tsx",
                "src/settings/LocationManager.test.tsx",
                "src/settings/QuietHoursForm.test.tsx",
            ),
        ),
    ),
    VRow(
        "V7.3",
        "V7 — Sectioned settings and the secondary pages",
        "settings-tabs, phase7, and locations specs pass",
        (Select("settings-tabs.spec.ts", "phase7.spec.ts", "locations.spec.ts"),),
    ),
    # V8 — Loop 1: the AI visual dogfood (4 rows)
    VRow(
        "V8.1",
        "V8 — Loop 1: the AI visual dogfood",
        "Static checks 45-50 all PASS",
        ("static_45_50",),
    ),
    VRow(
        "V8.2",
        "V8 — Loop 1: the AI visual dogfood",
        "e2e:dogfood renders 240 views with no audit finding",
        ("dogfood_probe",),
    ),
    VRow(
        "V8.3",
        "V8 — Loop 1: the AI visual dogfood",
        "phase8.spec.ts walks the whole redesign cleanly",
        ("pytest_live", Select("phase8.spec.ts", "screens.spec.ts")),
    ),
    VRow(
        "V8.4",
        "V8 — Loop 1: the AI visual dogfood",
        "AppShell.test.tsx's stale and reconnecting cases pass",
        (Select("src/app/AppShell.test.tsx"),),
    ),
    # V9 — Loop 2: the operator's dogfood (3 rows)
    VRow(
        "V9.1",
        "V9 — Loop 2: the operator's dogfood",
        "Static checks 51-54 all PASS (the dated sign-off included)",
        ("static_51_54",),
    ),
    VRow(
        "V9.2",
        "V9 — Loop 2: the operator's dogfood",
        "The operator's /api/health names this build at the head",
        ("operator_health_ui_build",),
    ),
    VRow(
        "V9.3",
        "V9 — Loop 2: the operator's dogfood",
        "The operator's doctor --offline --json passes web",
        ("operator_doctor_web",),
    ),
    # V10 — CI integration + security (4 rows)
    VRow(
        "V10.1",
        "V10 — CI integration + security",
        "verify_phase08.py --fast exits 0 on Ubuntu CI",
        (
            "verify_phase08_fast_budget",
            "phase_verify_ci",
            Select("tests.test_phase08_verification"),
        ),
    ),
    VRow(
        "V10.2",
        "V10 — CI integration + security",
        "phase-verify.yml's matrix includes '01' to '08'",
        ("static_58", "protection_requires_both"),
    ),
    VRow(
        "V10.3",
        "V10 — CI integration + security",
        "All 60 static checks in verify_phase08.py pass",
        ("static_01_60",),
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
    """Evaluate all 38 rows of the V1-V10 post-implementation verification matrix."""
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
        ("static_01_07", 1, 7),
        ("static_08_16", 8, 16),
        ("static_17_24", 17, 24),
        ("static_25_30", 25, 30),
        ("static_31_35", 31, 35),
        ("static_36_38", 36, 38),
        ("static_39_44", 39, 44),
        ("static_45_50", 45, 50),
        ("static_51_54", 51, 54),
        ("static_58", 58, 58),
        ("static_01_60", 1, 60),
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
    """Run static checks, all suites, probes, and evaluate the 38-row V1-V10 matrix."""
    print(
        "Notice: --post starts the offline demonstration servers (scripts/serve_demo.py) and "
        "headless Chromium for the Playwright smoke, the 240-render dogfood readability audit, "
        "and the 600 s idle CPU measurement, runs verify_phase07.py --post (107 checks, nesting "
        "Phases 6 to 1 including Phase 6's ~$0.40 live AI eval in a temporary directory, with "
        "operator secrets passed only to that child process), and reads the operator's running "
        "service only through GET /api/health and doctor --offline --json.",
        flush=True,
    )
    static_outcomes = run_static_checks()
    suite = Suite()
    _record_static_slices(static_outcomes, suite)

    with tempfile.TemporaryDirectory(prefix="weatherbot-post08-") as tmp:
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
        "phase-verify (01) through (08) CI checks",
        lambda: phase_entries_green(("01", "02", "03", "04", "05", "06", "07", "08")),
        suite,
    )
    run_probe(
        "protection_requires_both",
        "main branch protection requires gate and phase-verify",
        protection_requires_both,
        suite,
    )
    run_probe(
        "verify_phase07_post",
        "verify_phase07.py --post (107 checks)",
        verify_phase07_post,
        suite,
    )
    run_probe(
        "dogfood_probe",
        "npm --prefix frontend run e2e:dogfood (240 renders, 0 audit findings)",
        dogfood_probe,
        suite,
    )
    run_probe(
        "operator_health_ui_build",
        "operator /api/health ui.index_sha256 matches built index.html at DB head 0010",
        operator_health_ui_build,
        suite,
    )
    run_probe(
        "operator_doctor_web",
        "operator doctor --offline --json passes web and migrations",
        operator_doctor_web,
        suite,
    )
    run_probe(
        "measure_idle_probe",
        "scripts/measure_idle.py (600 s idle CPU < 0.5% with retention and ai_state=ready)",
        measure_idle_probe,
        suite,
    )
    run_probe(
        "verify_phase08_fast_budget",
        "scripts/verify_phase08.py --fast (< 30 s)",
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
    group.add_argument("--fast", action="store_true", help="Run the 60 static checks only.")
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
        "--post", action="store_true", help="Run the full 98-check Phase 8 verification."
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for Phase 8 verification."""
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
