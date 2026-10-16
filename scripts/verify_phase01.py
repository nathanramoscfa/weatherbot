# scripts/verify_phase01.py
"""Verify Phase 1 with 50 independent static checks and the 25-row V1-V7 matrix.

The six mutually exclusive modes are --fast (offline, standard library only),
--py, --corpus, --security, --all, and --post. With no flag, run --fast plus
--py. Each mode includes static checks. Subprocesses use argument lists, never
a shell. Failures print identifiers and exception types, never scanned content.
The post mode reads GitHub settings; it never changes them. Build and live-test
output goes to temporary directories, and the corpus cache remains ignored.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import re
import shutil
import subprocess  # fixed argument lists, never a shell  # nosec B404
import sys
import tempfile
import time
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path
from typing import Literal, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "nathanramoscfa/weatherbot"
RELEASE_COMMIT = "5de67aa1ad7883243af65d4f4f713d78ce02f791"
# Phase 1's milestone tag. Checks 7, 9, and 12 read the version, the skeleton, and the
# runtime dependency list Phase 1 shipped from this tag, so later phases may grow the
# package without turning those checks red.
PHASE_1_TAG = "v2.0.0-phase-1"
PHASE_1_VERSION = "2.0.0.dev0"
REGISTER = "docs/DATA_SOURCES.md"
ROADMAP = "docs/roadmap/ROADMAP.md"
CI_WORKFLOW = ".github/workflows/ci.yml"
PHASE_WORKFLOW = ".github/workflows/phase-verify.yml"
RECORDED = "tests/fixtures/recorded"
REPLAY = "tests/fixtures/replay"
CORPUS_MANIFEST = f"{REPLAY}/corpus-manifest.json"
MODES = ("fast", "py", "corpus", "security", "all", "post")
REGISTER_COLUMNS = 8
MIN_REGISTER_ROWS = 15
MIN_LANDMARKS = 2
STORMS = {"AL112017", "AL052019", "AL092022", "AL142024"}
HARVEST_DATES = (
    "2025-09-30",
    "2025-10-03",
    "2025-10-04",
    "2025-10-06",
    "2025-10-22",
    "2025-10-23",
)
SKELETON = {
    f"src/weatherbot/{name}"
    for name in (
        "__init__.py",
        "__main__.py",
        "py.typed",
        "cli/__init__.py",
        "engine/__init__.py",
        "services/__init__.py",
        "sources/__init__.py",
        "web/__init__.py",
    )
}
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


def toml_value(text: str, keys: Sequence[str]) -> object:
    """Read one value from TOML text; a missing table or key raises and fails its check."""
    value: object = tomllib.loads(text)
    for key in keys:
        value = object_of(value)[key]
    return value


def config(*keys: str, root: Path = REPO_ROOT) -> object:
    """Read a TOML configuration value; missing tables fail their own check."""
    return toml_value(read("pyproject.toml", root), keys)


def capture(
    argv: Sequence[str], *, timeout: int = 60, root: Path = REPO_ROOT
) -> subprocess.CompletedProcess[str]:
    """Capture bounded tool output; callers choose safe fields to display."""
    executable = shutil.which(argv[0])
    if executable is None:
        raise FileNotFoundError
    return subprocess.run(  # noqa: S603 - argument list, no shell  # nosec B603
        [executable, *argv[1:]],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


def git(*args: str, root: Path = REPO_ROOT) -> str:
    """Read Git metadata, failing closed on an unsuccessful command."""
    result = capture(["git", *args], root=root)
    result.check_returncode()
    return result.stdout.strip()


@cache
def index_files(root: Path = REPO_ROOT) -> frozenset[str]:
    """Snapshot the index once per invocation, including staged implementation files."""
    return frozenset(git("ls-files", "-z", root=root).split("\0")) - {""}


def tracked(*paths: str, root: Path = REPO_ROOT) -> set[str]:
    """Select exact files or directory prefixes from this invocation's index."""
    names = index_files(root)
    return {
        name
        for name in names
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


def register_rows() -> list[list[str]]:
    """Read only the register table, preserving its eight-cell schema."""
    section = read(REGISTER).split("## Register\n", 1)[1].split("\n## ", 1)[0]
    return [
        [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        for line in section.splitlines()
        if line.startswith("| `")
    ]


def register_valid() -> bool:
    """Require the source identities, unique kebab-case ids and real ISO dates."""
    rows = register_rows()
    ids = [row[0] for row in rows]
    for row in rows:
        if len(row) != REGISTER_COLUMNS or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+", row[0]):
            return False
        if date.fromisoformat(row[7]).isoformat() != row[7]:
            return False
    return (
        len(rows) >= MIN_REGISTER_ROWS
        and len(ids) == len(set(ids))
        and {
            "nhc-current-storms",
            "nhc-map-tropical-weather",
            "nws-points",
            "nws-alerts-point",
            "nws-alerts-zone",
        }
        <= set(ids)
    )


def user_agent_valid() -> bool:
    """Check the User-Agent itself; JSON-LD keys elsewhere legitimately contain @."""
    match = re.search(r"## User-Agent\s+.*?```text\n([^\n]+)\n```", read(REGISTER), re.DOTALL)
    return (
        match is not None
        and "github.com/nathanramoscfa/weatherbot" in match[1]
        and "@" not in match[1]
    )


def v1_removed() -> bool:
    """Check the complete deletion set from the scaffold commit, not a guessed list."""
    # PR #4 deleted these paths; new v2 files at reused paths were modifications.
    deleted = set(
        git(
            "diff-tree", "--no-commit-id", "--name-only", "--diff-filter=D", "-r", "f974aa0"
        ).splitlines()
    )
    return bool(deleted) and deleted.isdisjoint(tracked())


def reasoned_ignores() -> bool:
    """Check all Ruff ignore arrays, including per-file ignores, for inline reasons."""
    text = read("pyproject.toml")
    blocks = re.findall(
        r"(?:^ignore\s*=|^\"[^\"]+\"\s*=)\s*\[(.*?)\]", text, re.MULTILINE | re.DOTALL
    )
    entries = [
        line.strip()
        for block in blocks
        for line in block.splitlines()
        if re.match(r'\s*"[A-Z]+[0-9]+"', line)
    ]
    return (
        config("tool", "ruff", "lint", "select") == ["ALL"]
        and bool(entries)
        and all(re.search(r'"\s*,?\s*#\s*\S', line) for line in entries)
    )


def hooks_valid() -> bool:
    """Require every gate hook and the byte-preservation exclusions."""
    text = read(".pre-commit-config.yaml")
    ids = set(re.findall(r"^\s*- id: ([\w-]+)", text, re.MULTILINE))
    required = {
        "gitleaks",
        "bandit",
        "pip-audit",
        "personal-data",
        "ruff-check",
        "ruff-format",
        "pyright",
        "lint-imports",
        "check-added-large-files",
        "no-commit-to-branch",
    }
    for name in ("trailing-whitespace", "end-of-file-fixer"):
        block = re.search(rf"- id: {name}\n(.*?)(?=\s*- id:|\Z)", text, re.DOTALL)
        if block is None or "exclude: ^tests/fixtures/" not in block[1]:
            return False
    return (
        required <= ids
        and "--maxkb=5120" in text
        and "args: [--branch, main]" in text
        and contains(".gitattributes", "tests/fixtures/** -text")
    )


def hook_pins_valid() -> bool:
    """Require full commit hashes for every nonlocal hook repository."""
    repos = re.findall(
        r"- repo: (\S+)\n(.*?)(?=\n  - repo:|\Z)", read(".pre-commit-config.yaml"), re.DOTALL
    )
    return bool(repos) and all(
        name == "local" or re.search(r"^\s+rev: [0-9a-f]{40}(?:\s|$)", block, re.MULTILINE)
        for name, block in repos
    )


def landmarks_valid() -> bool:
    """Require tracked scanner inputs and at least two cited landmarks."""
    paths = (
        "scripts/check_personal_data.py",
        "scripts/audit_deps.py",
        "scripts/public_landmarks.toml",
    )
    landmarks = object_of(tomllib.loads(read(paths[2]))["landmarks"])
    return (
        files_exist(*paths)
        and len(landmarks) >= MIN_LANDMARKS
        and all(object_of(value).get("source") for value in landmarks.values())
    )


def workflow_pins_valid() -> bool:
    """Require a full SHA and a version comment on every action invocation."""
    workflows = list((REPO_ROOT / ".github/workflows").glob("*.yml"))
    return bool(workflows) and all(
        re.fullmatch(r"[^\s]+@[0-9a-f]{40}\s+#\s+.*v[0-9].*", line.strip())
        for path in workflows
        for line in re.findall(
            r"^\s*-?\s*uses:\s*(.+)$", path.read_text(encoding="utf-8"), re.MULTILINE
        )
    )


def workflow_permissions_valid() -> bool:
    """Require explicit permissions and refuse the privileged PR trigger."""
    return all(
        re.search(r"^permissions:", p.read_text(encoding="utf-8"), re.MULTILINE)
        and not re.search(r"^\s*pull_request_target:", p.read_text(encoding="utf-8"), re.MULTILINE)
        for p in (REPO_ROOT / ".github/workflows").glob("*.yml")
    )


def no_key_material() -> bool:
    """Scan tracked bytes and decompressed fixtures without displaying matches."""
    patterns = (
        rb"-{5}BEGIN (?:[A-Z]+ )?PRIVATE KEY-{5}",
        rb"AK" + rb"IA[A-Z0-9]{16}",
        rb"sk-" + rb"ant-[A-Za-z0-9_-]{20,}",
    )
    for name in tracked():
        body = (REPO_ROOT / name).read_bytes()
        bodies = [body]
        if body.startswith(b"\x1f\x8b"):
            # Bound decompression even if an untrusted PR changes a fixture.
            with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:
                expanded = stream.read(256 * 1024 * 1024 + 1)
            if len(expanded) > 256 * 1024 * 1024:
                return False
            bodies.append(expanded)
        if any(re.search(pattern, data) for data in bodies for pattern in patterns):
            return False
    return True


def captures_present() -> bool:
    """Require a dated manifest for every required register source."""
    required = [row[0] for row in register_rows() if row[4] == "required"]
    return bool(required) and all(
        any(
            re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.parent.name)
            for p in (REPO_ROOT / RECORDED / source).glob("*/manifest.json")
        )
        for source in required
    )


def harvest_present() -> bool:
    """Require provenance on each of the six harvested outlook captures."""
    return all(
        all(
            object_of(entry).get("harvested_from")
            for entry in array_of(
                json_file(f"{RECORDED}/nhc-outlook-graphics/{day}/manifest.json")["captures"]
            )
        )
        for day in HARVEST_DATES
    )


def headers_safe() -> bool:
    """Check manifest header keys case-insensitively and refuse tracked reports."""
    manifests = list((REPO_ROOT / RECORDED).glob("*/*/manifest.json"))
    return (
        bool(manifests)
        and not tracked("reports")
        and all(
            "set-cookie" not in {key.lower() for key in object_of(object_of(entry)["headers"])}
            for path in manifests
            for entry in array_of(json_file(path.relative_to(REPO_ROOT).as_posix())["captures"])
        )
    )


def matrix_includes_01() -> bool:
    """Read the flow-form phase matrix as strings; later phases may append entries."""
    match = re.search(r"^\s+phase:\s*\[([^]]+)\]", job(PHASE_WORKFLOW, "verify"), re.MULTILINE)
    return match is not None and "01" in {part.strip().strip("\"'") for part in match[1].split(",")}


def tagged(relative: str, root: Path = REPO_ROOT) -> str:
    """Read one file as Phase 1's tag recorded it; a missing tag or path raises."""
    return git("show", f"{PHASE_1_TAG}:{relative}", root=root)


def tagged_tree(prefix: str, root: Path = REPO_ROOT) -> set[str]:
    """List the files under ``prefix`` in Phase 1's tagged tree."""
    return set(
        git("ls-tree", "-r", "--name-only", PHASE_1_TAG, "--", prefix, root=root).splitlines()
    )


def is_typer(requirement: object) -> bool:
    """Match a ``typer`` requirement by distribution name, not by prefix (``typer-slim``)."""
    return re.match(r"typer(?![\w.-])", str(requirement)) is not None


def project_identity(root: Path = REPO_ROOT) -> bool:
    """Check 7: live identity and backend; Phase 1's version read from its tag."""
    return (
        config("project", "name", root=root) == "weatherbot"
        and config("project", "requires-python", root=root) == ">=3.13"
        and config("build-system", "build-backend", root=root) == "uv_build"
        and toml_value(tagged("pyproject.toml", root), ("project", "version")) == PHASE_1_VERSION
    )


def skeleton_kept(root: Path = REPO_ROOT) -> bool:
    """Check 9: the tag holds exactly the eight-file skeleton, and each file is still tracked."""
    still_tracked = tracked("src/weatherbot", root=root)
    return tagged_tree("src/weatherbot", root) == SKELETON and still_tracked >= SKELETON


def runtime_entry(root: Path = REPO_ROOT) -> bool:
    """Check 12: Typer was the only runtime dependency at the tag; the CLI entry stays live."""
    shipped = array_of(toml_value(tagged("pyproject.toml", root), ("project", "dependencies")))
    return (
        len(shipped) == 1
        and is_typer(shipped[0])
        and config("project", "scripts", "weatherbot", root=root) == "weatherbot.cli:app"
        and any(is_typer(item) for item in array_of(config("project", "dependencies", root=root)))
    )


STATIC_CHECKS: tuple[Check, ...] = (
    ("v1.0.0 is annotated", lambda: git("cat-file", "-t", "v1.0.0") == "tag"),
    (
        "v1.0.0 tags the proven release commit",
        lambda: git("rev-parse", "v1.0.0^{commit}") == RELEASE_COMMIT,
    ),
    (
        "changelog retires the installable v1 release",
        lambda: contains("CHANGELOG.md", "weatherbot==1.0.0", "v1.0.0", "retired"),
    ),
    (
        "release date and one Unreleased heading",
        lambda: (
            bool(re.search(r"^## \[1\.0\.0\].*2025-09-29", read("CHANGELOG.md"), re.MULTILINE))
            and len(re.findall(r"^## \[Unreleased\]", read("CHANGELOG.md"), re.MULTILINE)) == 1
        ),
    ),
    (
        "AGENTS names main as ledger",
        lambda: (
            contains("AGENTS.md", "`main`", "ledger") and "on `master`" not in read("AGENTS.md")
        ),
    ),
    (
        "project roadmap uses main and Phase 1 is underway",
        lambda: (
            not re.search(r"read\s+`master`\s+wherever", read(ROADMAP), re.IGNORECASE)
            and bool(
                re.search(
                    r"^\| 1\s*\|[^\n]*\b(?:In progress|Complete)\b", read(ROADMAP), re.MULTILINE
                )
            )
        ),
    ),
    (
        f"project identity, Python and uv backend; version at {PHASE_1_TAG}",
        project_identity,
    ),
    (
        "Python pin and tracked lock",
        lambda: read(".python-version").strip() == "3.13" and files_exist("uv.lock"),
    ),
    (f"exact eight-file v2 skeleton at {PHASE_1_TAG}, still tracked", skeleton_kept),
    ("all v1 deletions remain absent", v1_removed),
    (
        "dev and planning installed by default",
        lambda: (
            {"dev", "planning"} <= set(object_of(config("dependency-groups")))
            and all(
                any(
                    str(item).startswith(name)
                    for item in array_of(config("dependency-groups", "planning"))
                )
                for name in ("roadmodel", "pip")
            )
            and {"dev", "planning"} <= set(array_of(config("tool", "uv", "default-groups")))
        ),
    ),
    (f"Typer-only runtime at {PHASE_1_TAG}; live CLI entry point and typer", runtime_entry),
    (
        "engine and layer import contracts",
        lambda: (
            {"forbidden", "layers"}
            <= {object_of(c)["type"] for c in array_of(config("tool", "importlinter", "contracts"))}
            and contains("pyproject.toml", 'source_modules = ["weatherbot.engine"]')
        ),
    ),
    (
        "engine I/O import guard",
        lambda: (
            files_exist("tests/test_architecture.py")
            and contains(
                "tests/test_architecture.py",
                "BANNED_ENGINE_IMPORTS",
                '"httpx"',
                '"socket"',
                '"sqlite3"',
                '"anthropic"',
            )
        ),
    ),
    ("strict Ruff with reasoned ignores", reasoned_ignores),
    ("strict Pyright", lambda: config("tool", "pyright", "typeCheckingMode") == "strict"),
    (
        "socket, marker and temporary-cwd guards",
        lambda: (
            all(
                t in str(config("tool", "pytest", "ini_options", "addopts"))
                for t in ("--allow-hosts", "--strict-markers")
            )
            and all(
                any(
                    str(m).startswith(t + ":")
                    for m in array_of(config("tool", "pytest", "ini_options", "markers"))
                )
                for t in ("live", "corpus")
            )
            and contains("tests/conftest.py", "autouse=True", "monkeypatch.chdir(tmp_path)")
        ),
    ),
    (
        "private data and runtime paths ignored",
        lambda: all(
            t in read(".gitignore").splitlines()
            for t in (
                ".venv/",
                ".worktrees/",
                ".env",
                "/cache/",
                "/reports/",
                "/logs/",
                "/state/",
                "planning/user-context.md",
            )
        ),
    ),
    (
        "README disclaimer and v1 pointer",
        lambda: (
            contains("README.md", "DISCLAIMER.md", "v1.0.0")
            and "global coverage" not in read("README.md").lower()
        ),
    ),
    (
        "CI jobs and both operating systems",
        lambda: (
            all(job(CI_WORKFLOW, name) for name in ("lint", "typecheck", "test", "package", "gate"))
            and all(
                os_name in job(CI_WORKFLOW, "test")
                for os_name in ("ubuntu-latest", "windows-latest")
            )
        ),
    ),
    ("complete pre-commit gate and fixture exclusions", hooks_valid),
    ("hook repositories pinned to full SHAs", hook_pins_valid),
    ("tracked security scripts and cited landmarks", landmarks_valid),
    (
        "CI security tools feed gate",
        lambda: (
            all(
                t in job(CI_WORKFLOW, "security")
                for t in (
                    "gitleaks",
                    "bandit",
                    "audit_deps.py",
                    "check_personal_data.py --all --ci",
                )
            )
            and "security" in job(CI_WORKFLOW, "gate")
        ),
    ),
    ("all workflow actions pinned with version comments", workflow_pins_valid),
    ("workflow permissions and safe PR triggers", workflow_permissions_valid),
    (
        "Dependabot covers uv and actions",
        lambda: contains(
            ".github/dependabot.yml", "package-ecosystem: uv", "package-ecosystem: github-actions"
        ),
    ),
    (
        "private vulnerability reporting documented",
        lambda: files_exist("SECURITY.md") and "private" in read("SECURITY.md").lower(),
    ),
    ("no complete credential key shape in tracked bytes", no_key_material),
    (
        "no tracked environment file",
        lambda: (
            not any(
                Path(p).name == ".env"
                or Path(p).name.endswith(".env")
                or Path(p).name.startswith(".env.")
                for p in tracked()
            )
        ),
    ),
    (
        "exact source-register header",
        lambda: contains(
            REGISTER,
            "| Source id | Brief §5 source | Endpoint | Format | Fixture | Cadence "
            "| Terms | Verified |",
        ),
    ),
    ("register ids and verification dates", register_valid),
    ("User-Agent identifies repository without email", user_agent_valid),
    (
        "ATCF and storm scraping explicitly not used",
        lambda: all(
            t in read(REGISTER).split("## Not used", 1)[1]
            for t in ("ATCF", "NHC storm web pages", "No HTML scraping")
        ),
    ),
    (
        "per-basin layer answers present",
        lambda: contains(
            REGISTER,
            "| Storm | Arrival-time layers | Probabilistic winds 34/50/64 kt "
            "| Peak surge | Inundation | Checked |",
            "### Atlantic",
            "### Eastern Pacific",
            "### Central Pacific",
        ),
    ),
    (
        "tracked recorder defines SOURCES",
        lambda: (
            files_exist("scripts/record_fixtures.py")
            and bool(re.search(r"^SOURCES\b.*=", read("scripts/record_fixtures.py"), re.MULTILINE))
        ),
    ),
    ("every required source captured", captures_present),
    ("six harvested maps retain provenance", harvest_present),
    ("recorded data terms include ODbL", lambda: contains(f"{RECORDED}/NOTICE.md", "ODbL")),
    (
        "contract suites tracked",
        lambda: files_exist(
            *(
                f"tests/contract/{n}.py"
                for n in ("test_recorded_fixtures", "test_register", "test_fixture_budget")
            )
        ),
    ),
    ("no cookie headers or tracked reports", headers_safe),
    (
        "tracked replay pipeline with all commands",
        lambda: (
            files_exist("scripts/fetch_replay_corpus.py")
            and contains(
                "scripts/fetch_replay_corpus.py",
                'choices=("fetch", "verify", "convert", "manifest")',
            )
        ),
    ),
    (
        "corpus manifest covers four storms",
        lambda: set(object_of(json_file(CORPUS_MANIFEST)["storms"])) >= STORMS,
    ),
    (
        "committed subset for every storm",
        lambda: all(tracked(f"{REPLAY}/{storm}") for storm in STORMS),
    ),
    (
        "scheduled and dispatched corpus workflow with pinned cache",
        lambda: contains(
            ".github/workflows/replay-corpus.yml",
            "schedule:",
            "workflow_dispatch:",
            "simulate_failure:",
            "actions/cache@",
            "hashFiles('tests/fixtures/replay/corpus-manifest.json')",
        ),
    ),
    ("archive cache ignored", lambda: ".cache/" in read(".gitignore").splitlines()),
    (
        "tracked verifier declares all six modes",
        lambda: (
            files_exist("scripts/verify_phase01.py")
            and all(f'"{mode}"' in read("scripts/verify_phase01.py") for mode in MODES)
        ),
    ),
    ("QA findings document exists", (REPO_ROOT / "docs/phase01-qa-findings.md").is_file),
    ("phase roadmap exists", (REPO_ROOT / "docs/roadmap/phase01-roadmap.md").is_file),
    ("phase verification matrix includes 01", matrix_includes_01),
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


def run_command(item_id: str, description: str, argv: Sequence[str]) -> Outcome:
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
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
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


def package_smoke() -> Outcome:
    """Build and install the wheel in temporary directories on either platform."""
    with tempfile.TemporaryDirectory(prefix="weatherbot-package-") as directory:
        root = Path(directory)
        dist = root / "dist"
        environment = root / "smoke"
        results = [
            run_command("pkg.build", "build distributions", ["uv", "build", "--out-dir", str(dist)])
        ]
        wheels = list(dist.glob("*.whl"))
        if len(wheels) != 1:
            return report(
                Outcome("py.package", "installed wheel version", "FAIL", "expected one wheel")
            )
        results.append(
            run_command("pkg.venv", "fresh environment", ["uv", "venv", str(environment)])
        )
        results.append(
            run_command(
                "pkg.install",
                "install wheel",
                ["uv", "pip", "install", "--python", str(environment), str(wheels[0])],
            )
        )
        executable = environment / (
            "Scripts/weatherbot.exe" if os.name == "nt" else "bin/weatherbot"
        )
        try:
            version = capture([str(executable), "--version"])
            passed = version.returncode == 0 and version.stdout.strip() == config(
                "project", "version"
            )
        except (OSError, subprocess.SubprocessError):
            passed = False
        results.append(
            Outcome("pkg.version", "version matches project", "PASS" if passed else "FAIL")
        )
        return report(aggregate("py.package", "installed wheel version", results))


def py_suites() -> list[Outcome]:
    """Run the same Python suites as CI, plus the installed-wheel smoke."""
    heading("Python suites (--py)")
    commands = (
        ("lint", ["ruff", "check"]),
        ("format", ["ruff", "format", "--check"]),
        ("types", ["pyright"]),
        ("imports", ["lint-imports"]),
        ("tests", ["pytest"]),
    )
    return [run_command(f"py.{name}", name, ["uv", "run", *args]) for name, args in commands] + [
        package_smoke()
    ]


def corpus_suites() -> list[Outcome]:
    """Fetch missing pinned files, verify everything, and test byte-for-byte rebuilding."""
    heading("Full replay cache (--corpus)")
    cache = Path(os.environ.get("WEATHERBOT_CORPUS_CACHE", str(REPO_ROOT / ".cache/replay-corpus")))
    manifest = json_file(CORPUS_MANIFEST)
    missing = any(
        not (cache / str(object_of(entry)["file"])).is_file()
        for entry in array_of(manifest["files"])
    )
    results: list[Outcome] = []
    if missing:
        results.append(
            run_command(
                "corpus.fetch",
                "fetch cache misses",
                ["uv", "run", "python", "scripts/fetch_replay_corpus.py", "fetch"],
            )
        )
    results.append(
        run_command(
            "corpus.verify",
            "verify pinned archives",
            ["uv", "run", "python", "scripts/fetch_replay_corpus.py", "verify"],
        )
    )
    results.append(
        run_command("corpus.tests", "reconvert full cache", ["uv", "run", "pytest", "-m", "corpus"])
    )
    return results


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
    result = capture(
        ["gh", "api", f"repos/{REPOSITORY}/{endpoint}" if endpoint else f"repos/{REPOSITORY}"]
    )
    result.check_returncode()
    return json.loads(result.stdout) if result.stdout.strip() else None


def protection_valid(value: object, *, phase_required: bool = True) -> bool:
    """Verify every protection invariant, not just the two status names."""
    p = object_of(value)
    checks = object_of(p["required_status_checks"])
    reviews = object_of(p["required_pull_request_reviews"])
    contexts = set(array_of(checks["contexts"]))
    return (
        ({"gate", "phase-verify"} if phase_required else {"gate"}) <= contexts
        and checks["strict"] is True
        and all(
            object_of(p[key])["enabled"] is True
            for key in (
                "enforce_admins",
                "required_linear_history",
                "required_conversation_resolution",
            )
        )
        and all(
            object_of(p[key])["enabled"] is False
            for key in ("allow_force_pushes", "allow_deletions")
        )
        and reviews["required_approving_review_count"] == 0
        and not reviews.get("bypass_pull_request_allowances")
    )


def repository_settings() -> bool:
    """Verify squash-only protected main and automatic branch cleanup."""
    repo = object_of(github_api(""))
    return (
        repo["default_branch"] == "main"
        and all(repo[key] is True for key in ("allow_squash_merge", "delete_branch_on_merge"))
        and all(repo[key] is False for key in ("allow_merge_commit", "allow_rebase_merge"))
        and protection_valid(github_api("branches/main/protection"))
    )


def security_settings() -> bool:
    """Read security switches and the required checks; no writes are made."""
    github_api("vulnerability-alerts")  # Success is HTTP 204, with no JSON body.
    return (
        object_of(github_api("automated-security-fixes"))["enabled"] is True
        and object_of(github_api("private-vulnerability-reporting"))["enabled"] is True
        and protection_valid(github_api("branches/main/protection"))
    )


def latest_run(workflow: str) -> dict[str, object]:
    """Read the latest main run for a workflow, preserving its commit identity."""
    payload = object_of(github_api(f"actions/workflows/{workflow}/runs?branch=main&per_page=1"))
    runs = array_of(payload["workflow_runs"])
    if not runs:
        raise ValueError
    return object_of(runs[0])


def replay_health() -> bool:
    """Confirm recovery health and the exact alarm step of the recorded failed dispatch."""
    latest = latest_run("replay-corpus.yml")
    alarm = object_of(github_api("actions/runs/38799080064"))
    jobs = object_of(github_api("actions/runs/38799080064/jobs"))
    failed_steps = [
        object_of(step)["name"]
        for j in array_of(jobs["jobs"])
        for step in array_of(object_of(j)["steps"])
        if object_of(step)["conclusion"] == "failure"
    ]
    return (
        latest["conclusion"] == "success"
        and alarm["conclusion"] == "failure"
        and alarm["event"] == "workflow_dispatch"
        and failed_steps == ["Prove the failure alarm"]
    )


def updater_probe() -> bool:
    """Capture the local updater dry run and print only this project's plan lines."""
    updater = Path.home() / ".config/roadmodel/update_projects.py"
    result = capture(
        [sys.executable, str(updater), "--dry-run", "--local-only", str(REPO_ROOT)], timeout=300
    )
    lines = [
        line
        for line in result.stdout.splitlines()
        if re.match(r"\s*(?:\[weatherbot\]|weatherbot\s)", line)
    ]
    for line in lines:
        print(line.replace(str(REPO_ROOT), "<repo>"), flush=True)
    registry = Path.home() / ".config/roadmodel/projects.txt"
    normalized = str(REPO_ROOT).replace("\\", "/").lower()
    entries = [
        line.strip()
        for line in registry.read_text(encoding="utf-8-sig").splitlines()
        if normalized in line.replace("\\", "/").lower()
    ]
    return (
        result.returncode == 0
        and bool(lines)
        and any("venv:.venv" in line for line in lines)
        and len(entries) == 1
        and entries[0].replace("\\", "/").lower() == normalized
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


def ubuntu_verification() -> bool:
    """Use current PR checks, or the latest main phase run after branch retirement."""
    branch = git("branch", "--show-current")
    if branch == "main":
        run = latest_run("phase-verify.yml")
        return run["conclusion"] == "success" and run["head_sha"] == git("rev-parse", "HEAD")
    result = capture(["gh", "pr", "checks", "--json", "name,bucket"])
    result.check_returncode()
    rows = [object_of(row) for row in array_of(json.loads(result.stdout))]
    for row in rows:
        print(f"  {row['bucket']:<8} {row['name']}")
    return (
        bool(rows)
        and all(row["bucket"] == "pass" for row in rows)
        and any(row["name"] == "phase-verify (01)" for row in rows)
    )


def post_matrix(statics: Sequence[Outcome]) -> list[Outcome]:
    """Run shared suites once and report exactly V1.1 through V7.4 (25 rows)."""
    py = py_suites()
    security = security_suites()
    corpus = corpus_suites()
    heading("Post-implementation verification (V1-V7)")
    outcomes: list[Outcome] = []

    def static_row(vid: str, first: int, last: int) -> None:
        outcomes.append(
            report(
                aggregate(vid, f"Static checks {first}-{last} all PASS", statics[first - 1 : last])
            )
        )

    def suite_row(vid: str, description: str, suites: Sequence[Outcome]) -> None:
        outcomes.append(report(aggregate(vid, description, suites)))

    static_row("V1.1", 1, 6)
    outcomes.append(probe("V1.2", "main merge settings and protection", repository_settings))
    outcomes.append(
        probe(
            "V1.3",
            "remote v1 tag peels to release commit",
            lambda: (
                f"{RELEASE_COMMIT}\trefs/tags/v1.0.0^{{}}"
                in git("ls-remote", "--tags", "origin", "v1.0.0*")
            ),
        )
    )
    static_row("V2.1", 7, 20)
    suite_row("V2.2", "lint, types, contracts and offline tests", py[:-1])
    suite_row("V2.3", "installed wheel reports project version", py[-1:])
    outcomes.append(probe("V2.4", "updater resolves local .venv without override", updater_probe))
    static_row("V3.1", 21, 30)
    suite_row("V3.2", "four-check security gate", security)
    suite_row("V3.3", "personal-data regressions including redaction", [py[4]])
    settings = probe("post.security-settings", "GitHub security configuration", security_settings)
    suite_row(
        "V3.4", "required checks, security switches and local self-test", [settings, security[-1]]
    )
    static_row("V4.1", 31, 35)
    suite_row("V4.2", "register, recorder and catalog agreement", [py[4]])
    static_row("V5.1", 36, 41)
    suite_row("V5.2", "capture schemas, formats and checksums", [py[4]])
    suite_row("V5.3", "recorded and replay size budgets", [py[4]])
    live = run_command(
        "post.live",
        "live current-storms capture in tmp_path",
        ["uv", "run", "pytest", "-m", "live"],
    )
    suite_row("V5.4", "live recorder smoke", [live])
    static_row("V6.1", 42, 46)
    suite_row("V6.2", "subset geometry and advisory coverage", [py[4]])
    suite_row("V6.3", "full pinned cache and byte-identical conversion", corpus)
    outcomes.append(probe("V6.4", "main replay health and deliberate alarm proof", replay_health))
    ci = probe(
        "post.main-ci",
        "latest main CI green",
        lambda: latest_run("ci.yml")["conclusion"] == "success",
    )
    ubuntu = probe(
        "post.ubuntu", "Ubuntu phase workflow and current PR checks", ubuntu_verification
    )
    suite_row("V7.1", "fast verification exits 0 on Ubuntu CI", [ci, ubuntu])
    static_row("V7.2", 50, 50)
    static_row("V7.3", 1, 50)
    suite_row("V7.4", "security verification exits 0", security)
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
        outcomes.extend(py_suites())
    if mode in ("corpus", "all"):
        outcomes.extend(corpus_suites())
    if mode in ("security", "all"):
        outcomes.extend(security_suites())
    if mode == "post":
        outcomes.extend(post_matrix(statics))
    return summary(mode, outcomes, time.perf_counter() - started)


if __name__ == "__main__":
    raise SystemExit(main())
