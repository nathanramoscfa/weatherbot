# scripts/set_version.py
"""Set or verify Weatherbot's single version everywhere it appears in the repository.

The version lives in ``pyproject.toml`` and accepts only three PEP 440 shapes:
``X.Y.Z`` (release), ``X.Y.ZrcN`` (release candidate), and ``X.Y.Z.devN`` (development).

Setting a version updates ``pyproject.toml``'s ``Development Status`` classifier, runs
``uv version <version> --no-sync`` (updating ``pyproject.toml`` and ``uv.lock``),
regenerates ``docs/api/openapi.json``, ``frontend/src/api/schema.d.ts``, and the API test
fixtures, rewrites ``docs/DATA_SOURCES.md``'s ``## User-Agent`` block, and rewrites every
``blob/<ref>/`` and ``raw/<ref>/`` repository link in ``README.md`` to ``v<version>`` for
a candidate or release and to ``main`` for a development version (leaving the ``tree/v1.0.0``
link to version 1 untouched).

``--check`` verifies every copy agrees with ``pyproject.toml`` without writing anything.

Usage::

    uv run python scripts/set_version.py 2.0.0rc1
    uv run python scripts/set_version.py --check
"""

import argparse
import json
import os
import re
import shutil
import subprocess  # fixed argument lists for uv/npm/python, never a shell  # nosec B404
import sys
import tomllib
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final, Literal, cast

from packaging.version import InvalidVersion, Version

type VersionKind = Literal["dev", "rc", "release"]
type CommandRunner = Callable[[Sequence[str], Path], None]

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
REPOSITORY_URL: Final = "https://github.com/nathanramoscfa/weatherbot"
PACKAGE_NAME: Final = "weatherbot"

ALLOWED_VERSION_RE: Final = re.compile(
    r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:rc(?:0|[1-9]\d*)|\.dev(?:0|[1-9]\d*))?$"
)
DEV_STATUS_PREFIX: Final = "Development Status :: "
CLASSIFIER_BY_KIND: Final[dict[VersionKind, str]] = {
    "dev": "Development Status :: 2 - Pre-Alpha",
    "rc": "Development Status :: 4 - Beta",
    "release": "Development Status :: 5 - Production/Stable",
}
DEV_STATUS_LINE_RE: Final = re.compile(r'(?m)^([ \t]*)"Development Status :: [^"]+"(,?)$')
USER_AGENT_BLOCK_RE: Final = re.compile(
    r"(## User-Agent\b.*?```text\n)(weatherbot/[^\n]+)(\n```)",
    re.DOTALL,
)
README_REF_LINK_RE: Final = re.compile(
    r"(https://github\.com/nathanramoscfa/weatherbot/(?:blob|raw)/)([^/\s)\"'>]+)(/)"
)


def classify_version(raw: str) -> tuple[Version, VersionKind]:
    """Parse ``raw`` and enforce the three allowed PEP 440 release shapes.

    Args:
        raw: Version string (``X.Y.Z``, ``X.Y.ZrcN``, or ``X.Y.Z.devN``).

    Returns:
        The parsed PEP 440 ``Version`` and its kind (``dev``, ``rc``, or ``release``).

    Raises:
        ValueError: If ``raw`` is not a canonical version of one of the three shapes.
    """
    if not ALLOWED_VERSION_RE.fullmatch(raw):
        message = f"unsupported version {raw!r}: expected X.Y.Z, X.Y.ZrcN, or X.Y.Z.devN"
        raise ValueError(message)
    try:
        parsed = Version(raw)
    except InvalidVersion as error:
        message = f"invalid PEP 440 version {raw!r}"
        raise ValueError(message) from error
    if (
        str(parsed) != raw
        or parsed.epoch != 0
        or len(parsed.release) != 3  # noqa: PLR2004 - major.minor.patch
        or parsed.local is not None
        or parsed.post is not None
    ):
        message = f"non-canonical version {raw!r}"
        raise ValueError(message)
    if parsed.dev is not None and parsed.pre is None:
        return parsed, "dev"
    if parsed.pre is not None and parsed.pre[0] == "rc" and parsed.dev is None:
        return parsed, "rc"
    if not parsed.is_prerelease and not parsed.is_devrelease:
        return parsed, "release"
    message = f"unsupported version shape {raw!r}"
    raise ValueError(message)


def expected_classifier(version: str) -> str:
    """Return the required ``Development Status`` classifier for ``version``."""
    _, kind = classify_version(version)
    return CLASSIFIER_BY_KIND[kind]


def expected_readme_ref(version: str) -> str:
    """Return the Git ref README ``blob/`` and ``raw/`` links must point at for ``version``."""
    _, kind = classify_version(version)
    return "main" if kind == "dev" else f"v{version}"


def expected_user_agent(version: str) -> str:
    """Return the register's User-Agent string for ``version``."""
    classify_version(version)
    return f"{PACKAGE_NAME}/{version} (+{REPOSITORY_URL})"


def _run_subprocess(argv: Sequence[str], cwd: Path) -> None:
    """Execute one fixed command list in ``cwd`` without a shell."""
    executable = shutil.which(argv[0])
    if executable is None:
        message = f"executable not found on PATH: {argv[0]}"
        raise FileNotFoundError(message)
    env = os.environ.copy()
    if argv[0] == "uv" and len(argv) >= 2 and argv[1] == "version":  # noqa: PLR2004 - command prefix
        env.pop("UV_LOCKED", None)
    env.pop("VIRTUAL_ENV", None)
    env.pop("UV_PROJECT_ENVIRONMENT", None)
    completed = subprocess.run(  # noqa: S603 - fixed argument list, no shell  # nosec B603
        [executable, *argv[1:]],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        message = f"command failed ({completed.returncode}): {' '.join(argv)}\n{detail}"
        raise RuntimeError(message)


def _update_classifier(pyproject_path: Path, classifier: str) -> None:
    """Rewrite the single ``Development Status`` classifier line in ``pyproject.toml``."""
    text = pyproject_path.read_text(encoding="utf-8")
    updated, count = DEV_STATUS_LINE_RE.subn(rf'\1"{classifier}"\2', text)
    if count != 1:
        message = f"expected 1 Development Status classifier in pyproject.toml, found {count}"
        raise ValueError(message)
    if updated != text:
        pyproject_path.write_text(updated, encoding="utf-8", newline="\n")


def _update_register_user_agent(register_path: Path, user_agent: str) -> None:
    """Rewrite the ``## User-Agent`` code block in ``docs/DATA_SOURCES.md``."""
    text = register_path.read_text(encoding="utf-8")
    updated, count = USER_AGENT_BLOCK_RE.subn(rf"\g<1>{user_agent}\g<3>", text)
    if count != 1:
        message = f"expected 1 ## User-Agent block in docs/DATA_SOURCES.md, found {count}"
        raise ValueError(message)
    if updated != text:
        register_path.write_text(updated, encoding="utf-8", newline="\n")


def _update_readme_links(readme_path: Path, ref: str) -> None:
    """Rewrite every ``blob/<ref>/`` and ``raw/<ref>/`` repository link in ``README.md``."""
    text = readme_path.read_text(encoding="utf-8")
    updated = README_REF_LINK_RE.sub(rf"\g<1>{ref}\g<3>", text)
    if updated != text:
        readme_path.write_text(updated, encoding="utf-8", newline="\n")


def _tracked_candidates(root: Path) -> list[Path]:
    """Return every file path that ``set_version`` may modify."""
    candidates = [
        root / "pyproject.toml",
        root / "uv.lock",
        root / "docs" / "api" / "openapi.json",
        root / "frontend" / "src" / "api" / "schema.d.ts",
        root / "docs" / "DATA_SOURCES.md",
        root / "README.md",
    ]
    fixtures_dir = root / "frontend" / "src" / "test" / "fixtures"
    if fixtures_dir.is_dir():
        candidates.extend(sorted(fixtures_dir.glob("*.json")))
    return candidates


def _snapshot(root: Path) -> dict[Path, bytes | None]:
    return {
        path: path.read_bytes() if path.is_file() else None for path in _tracked_candidates(root)
    }


def set_version(
    version: str,
    *,
    root: Path = REPOSITORY_ROOT,
    runner: CommandRunner = _run_subprocess,
) -> list[str]:
    """Set Weatherbot's version across the repository and return changed relative POSIX paths.

    Args:
        version: Target version (``X.Y.Z``, ``X.Y.ZrcN``, or ``X.Y.Z.devN``).
        root: Repository root directory.
        runner: Subprocess runner (injectable for offline unit tests).

    Returns:
        Sorted repository-relative POSIX paths whose file contents changed.
    """
    classify_version(version)
    before = _snapshot(root)

    _update_classifier(root / "pyproject.toml", expected_classifier(version))
    runner(["uv", "version", version, "--no-sync"], root)
    runner(["uv", "run", "python", "scripts/export_openapi.py"], root)
    runner(["npm", "--prefix", "frontend", "run", "api:generate"], root)
    runner(["uv", "run", "python", "scripts/export_api_fixtures.py"], root)
    _update_register_user_agent(root / "docs" / "DATA_SOURCES.md", expected_user_agent(version))
    _update_readme_links(root / "README.md", expected_readme_ref(version))

    after = _snapshot(root)
    all_paths = sorted(set(before) | set(after))
    return [
        path.relative_to(root).as_posix()
        for path in all_paths
        if before.get(path) != after.get(path)
    ]


def _load_toml(path: Path) -> dict[str, object]:
    return cast("dict[str, object]", tomllib.loads(path.read_text(encoding="utf-8")))


def _locked_project_version(lock_path: Path) -> str | None:
    document = _load_toml(lock_path)
    packages = cast("list[dict[str, object]]", document.get("package", []))
    matches = [str(pkg["version"]) for pkg in packages if pkg.get("name") == PACKAGE_NAME]
    if len(matches) != 1:
        return None
    return matches[0]


def check_version_consistency(root: Path = REPOSITORY_ROOT) -> list[str]:
    """Return a list of version mismatches across the repository (empty when consistent).

    Args:
        root: Repository root directory.

    Returns:
        Human-readable mismatch descriptions; empty when every copy agrees.
    """
    issues: list[str] = []
    pyproject = _load_toml(root / "pyproject.toml")
    project = cast("dict[str, object]", pyproject["project"])
    version = str(project["version"])
    try:
        classify_version(version)
    except ValueError as error:
        return [f"pyproject.toml: {error}"]

    classifiers = [str(item) for item in cast("list[object]", project.get("classifiers", []))]
    dev_status = [item for item in classifiers if item.startswith(DEV_STATUS_PREFIX)]
    want_classifier = expected_classifier(version)
    if dev_status != [want_classifier]:
        issues.append(
            f"pyproject.toml classifiers: expected [{want_classifier!r}], got {dev_status!r}"
        )

    locked = _locked_project_version(root / "uv.lock")
    if locked != version:
        issues.append(f"uv.lock: weatherbot version {locked!r} != {version!r}")

    openapi = cast(
        "dict[str, object]",
        json.loads((root / "docs" / "api" / "openapi.json").read_text(encoding="utf-8")),
    )
    openapi_info = cast("dict[str, object]", openapi.get("info", {}))
    if openapi_info.get("version") != version:
        issues.append(
            f"docs/api/openapi.json: info.version {openapi_info.get('version')!r} != {version!r}"
        )

    health_path = root / "frontend" / "src" / "test" / "fixtures" / "health.json"
    health = cast("dict[str, object]", json.loads(health_path.read_text(encoding="utf-8")))
    if health.get("version") != version:
        issues.append(
            f"frontend/src/test/fixtures/health.json: version {health.get('version')!r} "
            f"!= {version!r}"
        )

    register_text = (root / "docs" / "DATA_SOURCES.md").read_text(encoding="utf-8")
    ua_match = USER_AGENT_BLOCK_RE.search(register_text)
    want_ua = expected_user_agent(version)
    if ua_match is None or ua_match.group(2) != want_ua:
        found_ua = None if ua_match is None else ua_match.group(2)
        issues.append(f"docs/DATA_SOURCES.md: User-Agent {found_ua!r} != {want_ua!r}")

    readme_text = (root / "README.md").read_text(encoding="utf-8")
    want_ref = expected_readme_ref(version)
    bad_refs = sorted(
        {
            match.group(2)
            for match in README_REF_LINK_RE.finditer(readme_text)
            if match.group(2) != want_ref
        }
    )
    if bad_refs:
        issues.append(
            f"README.md: repository blob/raw links use refs {bad_refs!r}, expected {want_ref!r}"
        )

    return issues


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for ``scripts/set_version.py``."""
    parser = argparse.ArgumentParser(
        description="Set or verify Weatherbot's single version across the repository."
    )
    parser.add_argument(
        "version",
        nargs="?",
        help="Target version (X.Y.Z, X.Y.ZrcN, or X.Y.Z.devN); omitted with --check.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify every version copy agrees with pyproject.toml without writing.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPOSITORY_ROOT,
        help="Repository root directory (defaults to this checkout).",
    )
    args = parser.parse_args(argv)

    if args.check:
        if args.version is not None:
            parser.error("--check does not accept a version argument")
        issues = check_version_consistency(args.root)
        if issues:
            for issue in issues:
                print(f"MISMATCH: {issue}", file=sys.stderr)
            return 1
        version = str(
            cast("dict[str, object]", _load_toml(args.root / "pyproject.toml")["project"])[
                "version"
            ]
        )
        print(f"OK version {version} is consistent")
        return 0

    if args.version is None:
        parser.error("provide a version argument or pass --check")

    try:
        changed = set_version(args.version, root=args.root)
    except (ValueError, RuntimeError, FileNotFoundError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for path in changed:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
