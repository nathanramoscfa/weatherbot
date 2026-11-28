# scripts/check_dist.py
"""Verify built Weatherbot wheel and sdist artifacts against a strict allowlist.

Standard library only (plus ``scripts/check_personal_data.py``, which is also
standard library only). Checks that ``DIST`` contains exactly one wheel and one
sdist for ``--version V``, verifies every member path, wheel size, ``METADATA``
and ``PKG-INFO`` fields, forbids demonstration storm markers (``AL802026``,
``Hurricane Demo``), and scans every extracted member with
``check_personal_data.py``'s CI rules.

Usage::

    uv run python scripts/check_dist.py dist --version 2.0.0.dev0
"""

import argparse
import hashlib
import stat
import sys
import tarfile
import tempfile
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from email.parser import Parser
from pathlib import Path, PurePosixPath
from typing import Final

import check_personal_data as pii

PACKAGE_NAME: Final = "weatherbot"
MAX_WHEEL_BYTES: Final = 5 * 1024 * 1024
REQUIRED_WHEEL_MEMBERS: Final = frozenset(
    {
        "weatherbot/web/static/index.html",
        "weatherbot/web/static/licenses.json",
        "weatherbot/DISCLAIMER.md",
        "weatherbot/py.typed",
    }
)
MIGRATIONS_VERSIONS_PREFIX: Final = "weatherbot/services/persistence/migrations/versions/"
FORBIDDEN_WHEEL_DIRS: Final = frozenset({"__pycache__", "tests", "scripts", "frontend", "docs"})
FORBIDDEN_WHEEL_EXTENSIONS: Final = (".pyc", ".sqlite3", ".toml")
FORBIDDEN_SDIST_DIRS: Final = frozenset({"__pycache__"})
FORBIDDEN_SDIST_EXTENSIONS: Final = (".pyc", ".sqlite3")
REQUIRED_SDIST_TOP_LEVEL: Final = frozenset(
    {
        "PKG-INFO",
        "pyproject.toml",
        "pyproject.toml.orig",
        "README.md",
        "LICENSE",
        "DISCLAIMER.md",
        "src",
    }
)
SYNTHETIC_STORM_MARKERS: Final = ("AL802026", "Hurricane Demo")
REQUIRED_METADATA_FIELDS: Final[dict[str, str]] = {
    "Name": PACKAGE_NAME,
    "Requires-Python": ">=3.13",
    "License-Expression": "MIT",
    "Description-Content-Type": "text/markdown",
}


@dataclass(frozen=True)
class ArtifactDigest:
    """Size and SHA-256 of one validated distribution file."""

    filename: str
    size: int
    sha256: str


@dataclass(frozen=True)
class CheckResult:
    """Validation outcome for a distribution directory."""

    artifacts: tuple[ArtifactDigest, ...]
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """Whether every check passed."""
        return not self.errors


def _sha256_file(path: Path) -> ArtifactDigest:
    data = path.read_bytes()
    return ArtifactDigest(path.name, len(data), hashlib.sha256(data).hexdigest())


def _is_safe_member_path(name: str) -> bool:
    if not name or "\\" in name or ":" in name:
        return False
    posix = PurePosixPath(name)
    return not posix.is_absolute() and not any(part in {"", ".", ".."} for part in posix.parts)


def _is_text(data: bytes) -> bool:
    return b"\0" not in data[: pii.BINARY_SNIFF_BYTES]


def _write_extracted(root: Path, rel_posix: str, data: bytes) -> str:
    target = root.joinpath(*PurePosixPath(rel_posix).parts)
    if not target.resolve().is_relative_to(root.resolve()):
        message = f"unsafe extraction target: {rel_posix}"
        raise ValueError(message)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return rel_posix


def _check_text_payload(label: str, rel: str, data: bytes, errors: list[str]) -> None:
    if not _is_text(data):
        return
    text = data.decode("utf-8", errors="replace")
    errors.extend(
        f"{label}: {rel} contains synthetic storm marker {marker!r}"
        for marker in SYNTHETIC_STORM_MARKERS
        if marker in text
    )


def _is_compiled_frontend_asset(rel_posix: str) -> bool:
    """Return whether ``rel_posix`` is a Vite-minified third-party JS/CSS asset bundle.

    Minified ``assets/*.js`` bundles third-party libraries (Leaflet's Web Mercator pole
    latitude constant and ``lucide-react`` SVG icon arc path numbers) that match the
    generic R2 coordinate regex. Project frontend source under ``frontend/src/`` is
    already R2-scanned by ``check_personal_data.py --all``; compiled assets are still
    checked here for synthetic markers, R4, and (when ``--with-denylist`` is used) R1.
    """
    parts = PurePosixPath(rel_posix).parts
    if len(parts) < 5:  # noqa: PLR2004 - .../weatherbot/web/static/assets/<file>
        return False
    return parts[-5:-1] == ("weatherbot", "web", "static", "assets") and parts[-1].lower().endswith(
        (".js", ".css")
    )


def _scan_extracted(
    label: str,
    root: Path,
    paths: Sequence[str],
    errors: list[str],
    *,
    denylist: Sequence[str] | None = None,
) -> None:
    allowlist = pii.Allowlist.from_landmarks(pii.load_landmarks())
    compiled_denylist = pii.denylist_pattern(denylist) if denylist else None
    scanner = pii.Scanner(root=root, allowlist=allowlist, denylist=compiled_denylist)
    for finding in scanner.scan(paths):
        if finding.rule == "R2" and _is_compiled_frontend_asset(finding.path):
            continue
        errors.append(f"{label}: personal-data finding {finding}")


def _check_metadata(
    label: str,
    raw_text: str,
    expected: dict[str, str],
    errors: list[str],
) -> None:
    parsed = Parser().parsestr(raw_text)
    for field, want in expected.items():
        actual = parsed.get(field)
        if actual != want:
            errors.append(f"{label}: {field} is {actual!r}, expected {want!r}")


def _validate_wheel_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    allowed_prefixes: tuple[str, ...],
    extract_root: Path,
    errors: list[str],
) -> tuple[str, str] | None:
    name = info.filename
    if not _is_safe_member_path(name):
        errors.append(f"wheel: unsafe member path {name!r}")
        return None
    mode = (info.external_attr >> 16) & 0o170000
    if mode == stat.S_IFLNK:
        errors.append(f"wheel: symlink member not allowed: {name!r}")
        return None
    if not name.startswith(allowed_prefixes):
        errors.append(f"wheel: unlisted top-level member {name!r}")
    parts = PurePosixPath(name).parts
    if any(part in FORBIDDEN_WHEEL_DIRS for part in parts):
        errors.append(f"wheel: forbidden directory member {name!r}")
    if name.lower().endswith(FORBIDDEN_WHEEL_EXTENSIONS) or pii.is_env_file(name):
        errors.append(f"wheel: forbidden file {name!r}")
    data = archive.read(info)
    _check_text_payload("wheel", name, data, errors)
    return name, _write_extracted(extract_root, name, data)


def _check_wheel(
    wheel_path: Path,
    version: str,
    extract_root: Path,
    errors: list[str],
    *,
    denylist: Sequence[str] | None = None,
) -> None:
    size = wheel_path.stat().st_size
    if size >= MAX_WHEEL_BYTES:
        errors.append(f"wheel: size {size} bytes reaches or exceeds {MAX_WHEEL_BYTES} bytes")

    dist_info = f"{PACKAGE_NAME}-{version}.dist-info"
    allowed_prefixes = (f"{PACKAGE_NAME}/", f"{dist_info}/")
    metadata_member = f"{dist_info}/METADATA"

    try:
        with zipfile.ZipFile(wheel_path) as archive:
            names: set[str] = set()
            extracted: list[str] = []
            for info in archive.infolist():
                if info.is_dir():
                    continue
                item = _validate_wheel_member(archive, info, allowed_prefixes, extract_root, errors)
                if item is not None:
                    names.add(item[0])
                    extracted.append(item[1])
    except zipfile.BadZipFile:
        errors.append(f"wheel: invalid zip archive {wheel_path.name}")
        return

    errors.extend(
        f"wheel: missing required member {required!r}"
        for required in sorted(REQUIRED_WHEEL_MEMBERS)
        if required not in names
    )

    has_migration = any(
        name.startswith(MIGRATIONS_VERSIONS_PREFIX)
        and name.endswith(".py")
        and not name.endswith("/__init__.py")
        for name in names
    )
    if not has_migration:
        errors.append("wheel: missing Alembic migration versions")

    if metadata_member not in names:
        errors.append(f"wheel: missing {metadata_member!r}")
    else:
        raw_meta = (extract_root / metadata_member).read_text(encoding="utf-8")
        _check_metadata(
            "wheel METADATA",
            raw_meta,
            {**REQUIRED_METADATA_FIELDS, "Version": version},
            errors,
        )

    _scan_extracted("wheel", extract_root, extracted, errors, denylist=denylist)


def _validate_sdist_member(
    archive: tarfile.TarFile,
    member: tarfile.TarInfo,
    prefix: str,
    extract_root: Path,
    errors: list[str],
) -> tuple[str | None, str | None]:
    raw_name = member.name.rstrip("/")
    if not _is_safe_member_path(raw_name):
        errors.append(f"sdist: unsafe member path {member.name!r}")
        return None, None
    if not (member.isreg() or member.isdir()):
        errors.append(f"sdist: non-regular member not allowed: {member.name!r}")
        return None, None
    parts = PurePosixPath(raw_name).parts
    if parts[0] != prefix:
        errors.append(f"sdist: member outside {prefix}/: {member.name!r}")
        return None, None
    top_entry = parts[1] if len(parts) >= 2 else None  # noqa: PLR2004 - <prefix>/<top-level>
    if member.isdir():
        return top_entry, None
    if any(part in FORBIDDEN_SDIST_DIRS for part in parts[1:]):
        errors.append(f"sdist: forbidden directory member {member.name!r}")
    if raw_name.lower().endswith(FORBIDDEN_SDIST_EXTENSIONS) or pii.is_env_file(raw_name):
        errors.append(f"sdist: forbidden file {member.name!r}")
    stream = archive.extractfile(member)
    if stream is None:
        errors.append(f"sdist: cannot read member {member.name!r}")
        return top_entry, None
    data = stream.read()
    _check_text_payload("sdist", raw_name, data, errors)
    return top_entry, _write_extracted(extract_root, raw_name, data)


def _check_sdist(
    sdist_path: Path,
    version: str,
    extract_root: Path,
    errors: list[str],
    *,
    denylist: Sequence[str] | None = None,
) -> None:
    prefix = f"{PACKAGE_NAME}-{version}"
    pkg_info_member = f"{prefix}/PKG-INFO"
    top_level: set[str] = set()
    extracted: list[str] = []

    try:
        with tarfile.open(sdist_path, "r:gz") as archive:
            for member in archive.getmembers():
                top_entry, rel = _validate_sdist_member(
                    archive, member, prefix, extract_root, errors
                )
                if top_entry is not None:
                    top_level.add(top_entry)
                if rel is not None:
                    extracted.append(rel)
    except (tarfile.TarError, OSError):
        errors.append(f"sdist: invalid tar.gz archive {sdist_path.name}")
        return

    missing_top = sorted(REQUIRED_SDIST_TOP_LEVEL - top_level)
    extra_top = sorted(top_level - REQUIRED_SDIST_TOP_LEVEL)
    if missing_top:
        errors.append(f"sdist: missing top-level entries {missing_top!r}")
    if extra_top:
        errors.append(f"sdist: unlisted top-level entries {extra_top!r}")

    pkg_info_path = extract_root / pkg_info_member
    if not pkg_info_path.is_file():
        errors.append(f"sdist: missing {pkg_info_member!r}")
    else:
        _check_metadata(
            "sdist PKG-INFO",
            pkg_info_path.read_text(encoding="utf-8"),
            {"Name": PACKAGE_NAME, "Version": version},
            errors,
        )

    _scan_extracted("sdist", extract_root, extracted, errors, denylist=denylist)


def check_dist(
    dist_dir: Path,
    version: str,
    *,
    denylist: Sequence[str] | None = None,
) -> CheckResult:
    """Validate every distribution file in ``dist_dir`` against the allowlist for ``version``."""
    errors: list[str] = []
    if not dist_dir.is_dir():
        return CheckResult((), (f"distribution directory does not exist: {dist_dir}",))

    expected_wheel = f"{PACKAGE_NAME}-{version}-py3-none-any.whl"
    expected_sdist = f"{PACKAGE_NAME}-{version}.tar.gz"
    expected_files = {expected_wheel, expected_sdist}

    entries = sorted(path.name for path in dist_dir.iterdir() if path.name != ".gitignore")
    missing = sorted(expected_files - set(entries))
    extra = sorted(set(entries) - expected_files)
    if missing:
        errors.append(f"dist: missing expected artifacts {missing!r}")
    if extra:
        errors.append(f"dist: unexpected artifacts {extra!r}")
    if errors:
        return CheckResult((), tuple(errors))

    wheel_path = dist_dir / expected_wheel
    sdist_path = dist_dir / expected_sdist
    if not wheel_path.is_file() or not sdist_path.is_file():
        return CheckResult((), ("dist: expected wheel and sdist to be regular files",))

    artifacts = (_sha256_file(wheel_path), _sha256_file(sdist_path))

    with tempfile.TemporaryDirectory(prefix="weatherbot-check-dist-") as tmp:
        tmp_path = Path(tmp)
        wheel_root = tmp_path / "wheel"
        sdist_root = tmp_path / "sdist"
        wheel_root.mkdir()
        sdist_root.mkdir()
        _check_wheel(wheel_path, version, wheel_root, errors, denylist=denylist)
        _check_sdist(sdist_path, version, sdist_root, errors, denylist=denylist)

    return CheckResult(artifacts, tuple(errors))


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for ``scripts/check_dist.py``."""
    parser = argparse.ArgumentParser(
        description="Verify Weatherbot wheel and sdist archives against the release allowlist."
    )
    parser.add_argument("dist", type=Path, help="Directory holding built wheel and sdist.")
    parser.add_argument("--version", required=True, help="Expected PEP 440 version.")
    parser.add_argument(
        "--with-denylist",
        action="store_true",
        help="Also scan every extracted member (minified assets included) with the local denylist.",
    )
    args = parser.parse_args(argv)

    denylist: list[str] | None = None
    if args.with_denylist:
        try:
            denylist = pii.read_denylist(pii.denylist_path())
        except pii.SetupError as error:
            print(f"FAIL: {error}", file=sys.stderr)
            return pii.EXIT_SETUP
        if not denylist:
            print(pii.SETUP_INSTRUCTIONS, file=sys.stderr)
            return pii.EXIT_SETUP

    result = check_dist(args.dist, args.version, denylist=denylist)
    for artifact in result.artifacts:
        print(f"{artifact.filename} {artifact.size} bytes sha256={artifact.sha256}")
    if not result.ok:
        for error in result.errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"OK dist allowlist clean for weatherbot {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
