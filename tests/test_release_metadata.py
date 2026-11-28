# tests/test_release_metadata.py
"""Tests holding Weatherbot's single version, classifier, and metadata copies in sync."""

import json
import re
import tomllib
from collections.abc import Sequence
from importlib.metadata import version as installed_version
from pathlib import Path
from typing import cast

import pytest
from packaging.version import Version

import set_version as sv
import weatherbot
from weatherbot.sources import USER_AGENT

REPO_ROOT = Path(__file__).resolve().parents[1]


def _pyproject(root: Path = REPO_ROOT) -> dict[str, object]:
    return cast(
        "dict[str, object]",
        tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8")),
    )


def _locked_version(root: Path = REPO_ROOT) -> str:
    lock = cast(
        "dict[str, object]",
        tomllib.loads((root / "uv.lock").read_text(encoding="utf-8")),
    )
    packages = cast("list[dict[str, object]]", lock["package"])
    matches = [str(pkg["version"]) for pkg in packages if pkg.get("name") == "weatherbot"]
    assert len(matches) == 1
    return matches[0]


def test_every_version_copy_agrees_with_pyproject() -> None:
    project = cast("dict[str, object]", _pyproject()["project"])
    project_version = str(project["version"])
    parsed, _kind = sv.classify_version(project_version)
    assert isinstance(parsed, Version)

    assert _locked_version() == project_version
    assert weatherbot.__version__ == project_version
    assert installed_version("weatherbot") == project_version
    assert sv.expected_user_agent(project_version) == USER_AGENT

    openapi = cast(
        "dict[str, object]",
        json.loads((REPO_ROOT / "docs" / "api" / "openapi.json").read_text(encoding="utf-8")),
    )
    assert cast("dict[str, object]", openapi["info"])["version"] == project_version

    health = cast(
        "dict[str, object]",
        json.loads(
            (REPO_ROOT / "frontend" / "src" / "test" / "fixtures" / "health.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    assert health["version"] == project_version

    assert sv.check_version_consistency(REPO_ROOT) == []
    assert sv.main(["--check", "--root", str(REPO_ROOT)]) == 0


def test_development_status_classifier_matches_version_stage() -> None:
    project = cast("dict[str, object]", _pyproject()["project"])
    project_version = str(project["version"])
    _parsed, kind = sv.classify_version(project_version)
    classifiers = [str(item) for item in cast("list[object]", project["classifiers"])]
    dev_status = [item for item in classifiers if item.startswith(sv.DEV_STATUS_PREFIX)]
    assert dev_status == [sv.expected_classifier(project_version)]
    if kind == "rc":
        assert dev_status == ["Development Status :: 4 - Beta"]
    elif kind == "release":
        assert dev_status == ["Development Status :: 5 - Production/Stable"]


@pytest.mark.parametrize(
    ("raw", "expected_kind", "expected_status", "expected_ref"),
    [
        ("2.0.0.dev0", "dev", "Development Status :: 2 - Pre-Alpha", "main"),
        ("2.0.0rc1", "rc", "Development Status :: 4 - Beta", "v2.0.0rc1"),
        ("2.0.0", "release", "Development Status :: 5 - Production/Stable", "v2.0.0"),
        ("2.1.3", "release", "Development Status :: 5 - Production/Stable", "v2.1.3"),
    ],
)
def test_classify_version_accepts_the_three_release_shapes(
    raw: str,
    expected_kind: str,
    expected_status: str,
    expected_ref: str,
) -> None:
    parsed, kind = sv.classify_version(raw)
    assert str(parsed) == raw
    assert kind == expected_kind
    assert sv.expected_classifier(raw) == expected_status
    assert sv.expected_readme_ref(raw) == expected_ref


@pytest.mark.parametrize(
    "bad",
    [
        "v2.0.0",
        "2.0",
        "2.0.0.0",
        "2.0.0a1",
        "2.0.0b1",
        "2.0.0.post1",
        "2.0.0rc1.dev0",
        "1!2.0.0",
        "2.0.0+local",
        "2.0.0-rc1",
        "02.0.0",
        "not-a-version",
    ],
)
def test_classify_version_rejects_other_shapes(bad: str) -> None:
    with pytest.raises(ValueError, match="version"):
        sv.classify_version(bad)


def _seed_fake_repo(root: Path, initial_version: str = "2.0.0.dev0") -> dict[Path, bytes]:
    """Create a minimal repository copy for offline ``set_version`` round-trip tests."""
    (root / "docs" / "api").mkdir(parents=True)
    (root / "frontend" / "src" / "api").mkdir(parents=True)
    (root / "frontend" / "src" / "test" / "fixtures").mkdir(parents=True)

    pyproject = (
        "[project]\n"
        'name = "weatherbot"\n'
        f'version = "{initial_version}"\n'
        "classifiers = [\n"
        f'    "{sv.expected_classifier(initial_version)}",\n'
        '    "Programming Language :: Python :: 3.13",\n'
        "]\n"
    )
    uv_lock = f'version = 1\n\n[[package]]\nname = "weatherbot"\nversion = "{initial_version}"\n'
    openapi = (
        json.dumps(
            {"openapi": "3.1.0", "info": {"title": "Weatherbot", "version": initial_version}},
            indent=2,
        )
        + "\n"
    )
    schema_ts = "export interface paths {}\n"
    health = json.dumps({"version": initial_version}, indent=2) + "\n"
    register = (
        "# Data-source register\n\n"
        "## User-Agent\n\n"
        "Every request sends:\n\n"
        "```text\n"
        f"{sv.expected_user_agent(initial_version)}\n"
        "```\n"
    )
    ref = sv.expected_readme_ref(initial_version)
    readme = (
        "# Weatherbot\n\n"
        "Legacy [v1.0.0](https://github.com/nathanramoscfa/weatherbot/tree/v1.0.0).\n"
        f"Read [DISCLAIMER](https://github.com/nathanramoscfa/weatherbot/blob/{ref}/DISCLAIMER.md).\n"
        f"Image ![img](https://github.com/nathanramoscfa/weatherbot/raw/{ref}/docs/images/dash.png).\n"
    )

    files = {
        root / "pyproject.toml": pyproject,
        root / "uv.lock": uv_lock,
        root / "docs" / "api" / "openapi.json": openapi,
        root / "frontend" / "src" / "api" / "schema.d.ts": schema_ts,
        root / "frontend" / "src" / "test" / "fixtures" / "health.json": health,
        root / "docs" / "DATA_SOURCES.md": register,
        root / "README.md": readme,
    }
    for path, content in files.items():
        path.write_text(content, encoding="utf-8", newline="\n")
    return {path: path.read_bytes() for path in files}


def _fake_runner(recorded_commands: list[tuple[str, ...]]) -> sv.CommandRunner:
    """Return an offline command runner that simulates uv/npm/export scripts in ``cwd``."""

    def run(argv: Sequence[str], cwd: Path) -> None:
        recorded_commands.append(tuple(argv))
        if argv[:2] == ["uv", "version"]:
            target = argv[2]
            pyproject_path = cwd / "pyproject.toml"
            pyproject_text = pyproject_path.read_text(encoding="utf-8")
            pyproject_path.write_text(
                re.sub(r'(?m)^version = "[^"]+"$', f'version = "{target}"', pyproject_text),
                encoding="utf-8",
                newline="\n",
            )
            lock_path = cwd / "uv.lock"
            lock_text = lock_path.read_text(encoding="utf-8")
            lock_path.write_text(
                re.sub(
                    r'(?m)(name = "weatherbot"\nversion = )"[^"]+"',
                    rf'\g<1>"{target}"',
                    lock_text,
                ),
                encoding="utf-8",
                newline="\n",
            )
        elif argv[-1] == "scripts/export_openapi.py":
            version = str(cast("dict[str, object]", _pyproject(cwd)["project"])["version"])
            openapi_path = cwd / "docs" / "api" / "openapi.json"
            doc = cast("dict[str, object]", json.loads(openapi_path.read_text(encoding="utf-8")))
            cast("dict[str, object]", doc["info"])["version"] = version
            openapi_path.write_text(
                json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n"
            )
        elif argv[-1] == "scripts/export_api_fixtures.py":
            version = str(cast("dict[str, object]", _pyproject(cwd)["project"])["version"])
            health_path = cwd / "frontend" / "src" / "test" / "fixtures" / "health.json"
            doc = cast("dict[str, object]", json.loads(health_path.read_text(encoding="utf-8")))
            doc["version"] = version
            health_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
        elif argv[:4] == ["npm", "--prefix", "frontend", "run"]:
            pass
        else:
            msg = f"unexpected command: {argv!r}"
            raise AssertionError(msg)

    return run


def test_set_version_round_trips_offline_and_preserves_v1_tree_link(tmp_path: Path) -> None:
    original = _seed_fake_repo(tmp_path, "2.0.0.dev0")
    assert sv.check_version_consistency(tmp_path) == []

    commands: list[tuple[str, ...]] = []
    changed_rc = sv.set_version("2.0.0rc1", root=tmp_path, runner=_fake_runner(commands))
    assert commands == [
        ("uv", "version", "2.0.0rc1", "--no-sync"),
        ("uv", "run", "python", "scripts/export_openapi.py"),
        ("npm", "--prefix", "frontend", "run", "api:generate"),
        ("uv", "run", "python", "scripts/export_api_fixtures.py"),
    ]
    assert set(changed_rc) == {
        "README.md",
        "docs/DATA_SOURCES.md",
        "docs/api/openapi.json",
        "frontend/src/test/fixtures/health.json",
        "pyproject.toml",
        "uv.lock",
    }
    assert sv.check_version_consistency(tmp_path) == []

    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "https://github.com/nathanramoscfa/weatherbot/tree/v1.0.0" in readme
    assert "https://github.com/nathanramoscfa/weatherbot/blob/v2.0.0rc1/DISCLAIMER.md" in readme
    assert (
        "https://github.com/nathanramoscfa/weatherbot/raw/v2.0.0rc1/docs/images/dash.png" in readme
    )
    assert '"Development Status :: 4 - Beta"' in (tmp_path / "pyproject.toml").read_text(
        encoding="utf-8"
    )

    sv.set_version("2.0.0", root=tmp_path, runner=_fake_runner([]))
    assert sv.check_version_consistency(tmp_path) == []
    assert '"Development Status :: 5 - Production/Stable"' in (
        tmp_path / "pyproject.toml"
    ).read_text(encoding="utf-8")
    assert "blob/v2.0.0/DISCLAIMER.md" in (tmp_path / "README.md").read_text(encoding="utf-8")

    sv.set_version("2.0.0.dev0", root=tmp_path, runner=_fake_runner([]))
    assert sv.check_version_consistency(tmp_path) == []
    for path, expected_bytes in original.items():
        assert path.read_bytes() == expected_bytes, path.name


def test_check_detects_each_stale_copy(tmp_path: Path) -> None:
    _seed_fake_repo(tmp_path, "2.0.0")
    assert sv.check_version_consistency(tmp_path) == []

    health_path = tmp_path / "frontend" / "src" / "test" / "fixtures" / "health.json"
    health_path.write_text('{"version": "2.0.0rc1"}\n', encoding="utf-8", newline="\n")
    issues = sv.check_version_consistency(tmp_path)
    assert any("health.json" in item for item in issues)
    assert sv.main(["--check", "--root", str(tmp_path)]) == 1

    readme_path = tmp_path / "README.md"
    readme_path.write_text(
        readme_path.read_text(encoding="utf-8").replace("blob/v2.0.0/", "blob/main/"),
        encoding="utf-8",
        newline="\n",
    )
    issues = sv.check_version_consistency(tmp_path)
    assert any("README.md" in item for item in issues)

    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        pyproject_path.read_text(encoding="utf-8").replace(
            "5 - Production/Stable", "2 - Pre-Alpha"
        ),
        encoding="utf-8",
        newline="\n",
    )
    issues = sv.check_version_consistency(tmp_path)
    assert any("classifiers" in item for item in issues)
