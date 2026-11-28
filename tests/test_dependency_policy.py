# tests/test_dependency_policy.py
"""What a clean install resolves is what CI tests (Phase 9 Decision 2).

Read from ``pyproject.toml`` and ``uv.lock`` with the standard library and ``packaging``:
``requires-python`` stays ``>=3.13`` with no upper bound (a cap would send pip on a newer
Python back to 1.0.0); every runtime requirement locked at 1.0 or later is capped below its
next major (below the next epoch for an epoch version, such as pywinrt's projections), while
a calendar-versioned one (``tzdata``) and every one below 1.0 keeps a floor only; the
classifiers name Python 3.13 to 3.15; and every compiled package in the lock's runtime
closure has a wheel for Python 3.13 and 3.15 on each platform its markers allow.
"""

import tomllib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.specifiers import Specifier
from packaging.tags import Tag, compatible_tags, cpython_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
PROJECT: Final = "weatherbot"
REQUIRES_PYTHON: Final = ">=3.13"
PYTHONS: Final = ((3, 13), (3, 15))
CLASSIFIER_PREFIX: Final = "Programming Language :: Python :: 3."
CALENDAR_VERSIONED: Final = frozenset({"tzdata"})
"""Requirements versioned by date, which keep a floor only."""
CALENDAR_YEAR_FLOOR: Final = 2000
FIRST_STABLE_MAJOR: Final = 1
MANYLINUX_X86_64: Final = (
    *(f"manylinux_2_{minor}_x86_64" for minor in range(40, 4, -1)),
    "manylinux2014_x86_64",
    "manylinux2010_x86_64",
    "manylinux1_x86_64",
)
"""The Linux platform tags a GitHub-hosted ``ubuntu-latest`` runner installs from PyPI."""

type Table = Mapping[str, object]


@dataclass(frozen=True)
class Platform:
    """A platform CI tests, as wheel tags and marker values name it."""

    name: str
    tags: tuple[str, ...]
    sys_platform: str
    platform_system: str
    platform_machine: str
    os_name: str


WINDOWS: Final = Platform("win_amd64", ("win_amd64",), "win32", "Windows", "AMD64", "nt")
LINUX: Final = Platform("manylinux x86_64", MANYLINUX_X86_64, "linux", "Linux", "x86_64", "posix")
PLATFORMS: Final = (WINDOWS, LINUX)


def _toml(relative: str) -> Table:
    return tomllib.loads((REPOSITORY_ROOT / relative).read_text(encoding="utf-8"))


def _table(value: object) -> Table:
    assert isinstance(value, dict)
    return cast("Table", value)


def _tables(value: object) -> list[Table]:
    assert isinstance(value, list)
    return [_table(item) for item in cast("list[object]", value)]


def _strings(value: object) -> list[str]:
    assert isinstance(value, list)
    items = cast("list[object]", value)
    assert all(isinstance(item, str) for item in items)
    return [str(item) for item in items]


def _project() -> Table:
    return _table(_toml("pyproject.toml")["project"])


def _runtime_requirements() -> list[Requirement]:
    return [Requirement(text) for text in _strings(_project()["dependencies"])]


def _locked_packages() -> dict[str, Table]:
    packages: dict[str, Table] = {}
    for package in _tables(_toml("uv.lock")["package"]):
        name = canonicalize_name(str(package["name"]))
        assert name not in packages, f"{name} is locked at more than one version"
        packages[name] = package
    return packages


def _locked_version(name: str) -> Version:
    return Version(str(_locked_packages()[canonicalize_name(name)]["version"]))


def _is_calendar(name: str, version: Version) -> bool:
    if canonicalize_name(name) not in CALENDAR_VERSIONED:
        return False
    assert version.major >= CALENDAR_YEAR_FLOOR, f"{name} {version} is no calendar version"
    return True


def _next_major(version: Version) -> Version:
    """The first version past ``version``'s major: the next epoch for an epoch version."""
    if version.epoch:
        return Version(f"{version.epoch + 1}!0")
    return Version(str(version.major + 1))


def _specifiers(requirement: Requirement) -> list[Specifier]:
    return sorted(requirement.specifier, key=str)


def test_requires_python_has_no_upper_bound() -> None:
    assert _project()["requires-python"] == REQUIRES_PYTHON


def test_stable_runtime_requirements_are_capped() -> None:
    checked: list[str] = []
    for requirement in _runtime_requirements():
        locked = _locked_version(requirement.name)
        if _is_calendar(requirement.name, locked):
            operators = [spec.operator for spec in _specifiers(requirement)]
            assert operators == [">="], f"{requirement} keeps its floor only"
            continue
        if locked.epoch == 0 and locked.major < FIRST_STABLE_MAJOR:
            continue
        upper = [spec for spec in requirement.specifier if spec.operator == "<"]
        floors = [spec for spec in requirement.specifier if spec.operator == ">="]
        assert len(floors) == 1, f"{requirement} needs one floor"
        assert [Version(spec.version) for spec in upper] == [_next_major(locked)], (
            f"{requirement} (locked {locked}) is capped below {_next_major(locked)}"
        )
        assert locked in requirement.specifier, f"{requirement} admits the locked {locked}"
        assert {spec.operator for spec in requirement.specifier} == {">=", "<"}, requirement
        checked.append(canonicalize_name(requirement.name))
    assert {"anthropic", "pydantic", "sqlalchemy", "winrt-runtime"} <= set(checked)


def test_requirements_below_1_0_have_floors_only() -> None:
    below = [
        requirement
        for requirement in _runtime_requirements()
        if (version := _locked_version(requirement.name)).epoch == 0
        and version.major < FIRST_STABLE_MAJOR
    ]
    assert {canonicalize_name(requirement.name) for requirement in below} >= {"fastapi", "typer"}
    for requirement in below:
        operators = [spec.operator for spec in _specifiers(requirement)]
        assert operators == [">="], f"{requirement} below 1.0 keeps a floor only"


def test_classifiers_name_python_3_13_to_3_15() -> None:
    classifiers = _strings(_project()["classifiers"])
    minors = {
        classifier.removeprefix(CLASSIFIER_PREFIX)
        for classifier in classifiers
        if classifier.startswith(CLASSIFIER_PREFIX)
    }
    assert minors == {"13", "14", "15"}


def _environment(platform: Platform, python: tuple[int, int]) -> dict[str, str]:
    version = f"{python[0]}.{python[1]}"
    return {
        "implementation_name": "cpython",
        "implementation_version": f"{version}.0",
        "os_name": platform.os_name,
        "platform_machine": platform.platform_machine,
        "platform_python_implementation": "CPython",
        "platform_release": "",
        "platform_system": platform.platform_system,
        "platform_version": "",
        "python_full_version": f"{version}.0",
        "python_version": version,
        "sys_platform": platform.sys_platform,
        "extra": "",
    }


def _applies(entry: Table, environment: dict[str, str]) -> bool:
    marker = entry.get("marker")
    return marker is None or Marker(str(marker)).evaluate(environment)


def _dependency_entries(package: Table, extras: Sequence[str]) -> Iterator[Table]:
    yield from _tables(package.get("dependencies", []))
    optional = _table(package.get("optional-dependencies", {}))
    for extra in extras:
        yield from _tables(optional[extra])


def _runtime_closure(environment: dict[str, str]) -> set[str]:
    """Every locked package a clean install pulls in for ``environment``, the project aside."""
    packages = _locked_packages()
    reached: set[tuple[str, tuple[str, ...]]] = set()
    pending: list[tuple[str, tuple[str, ...]]] = [(PROJECT, ())]
    while pending:
        name, extras = pending.pop()
        if (name, extras) in reached:
            continue
        reached.add((name, extras))
        for entry in _dependency_entries(packages[name], extras):
            if _applies(entry, environment):
                extra = tuple(_strings(entry.get("extra", [])))
                pending.append((canonicalize_name(str(entry["name"])), extra))
    return {name for name, _ in reached} - {PROJECT}


def _wheel_tags(package: Table) -> list[frozenset[Tag]]:
    tags: list[frozenset[Tag]] = []
    for wheel in _tables(package.get("wheels", [])):
        filename = str(wheel["url"]).rsplit("/", 1)[-1]
        tags.append(parse_wheel_filename(filename)[3])
    return tags


def _supported(platform: Platform, python: tuple[int, int]) -> frozenset[Tag]:
    """The tags CPython ``python`` installs on ``platform``: its own ABI, ``abi3``, or pure."""
    return frozenset(
        (
            *cpython_tags(python, platforms=platform.tags),
            *compatible_tags(python, f"cp{python[0]}{python[1]}", platform.tags),
        )
    )


def _is_pure(tags: frozenset[Tag]) -> bool:
    return any(tag.abi == "none" and tag.platform == "any" for tag in tags)


def test_compiled_runtime_wheels_cover_3_13_and_3_15() -> None:
    packages = _locked_packages()
    missing: list[str] = []
    compiled: set[str] = set()
    for platform in PLATFORMS:
        for python in PYTHONS:
            supported = _supported(platform, python)
            for name in sorted(_runtime_closure(_environment(platform, python))):
                wheels = _wheel_tags(packages[name])
                assert wheels, f"{name} has no wheel in the lock"
                if any(_is_pure(tags) for tags in wheels):
                    continue
                compiled.add(name)
                if not any(tags & supported for tags in wheels):
                    missing.append(f"{name} on cp{python[0]}{python[1]} {platform.name}")
    assert missing == []
    assert {"pydantic-core", "shapely", "winrt-runtime"} <= compiled


def test_the_windows_only_runtime_reaches_windows_alone() -> None:
    windows = _runtime_closure(_environment(WINDOWS, PYTHONS[0]))
    linux = _runtime_closure(_environment(LINUX, PYTHONS[0]))
    assert "winrt-runtime" in windows
    assert not any(name.startswith("winrt-") for name in linux)
