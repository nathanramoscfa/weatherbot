# tests/scripts/test_check_dist.py
"""Tests for ``scripts/check_dist.py`` using small synthetic wheel and sdist archives."""

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

import check_dist as cd

VERSION = "2.0.0rc1"


def _valid_metadata(version: str = VERSION, **overrides: str) -> str:
    fields = {
        "Metadata-Version": "2.4",
        "Name": "weatherbot",
        "Version": version,
        "Requires-Python": ">=3.13",
        "License-Expression": "MIT",
        "Description-Content-Type": "text/markdown",
        **overrides,
    }
    headers = "\n".join(f"{key}: {value}" for key, value in fields.items())
    return f"{headers}\n\n# Weatherbot\n"


def _default_wheel_members(version: str = VERSION) -> dict[str, bytes]:
    dist_info = f"weatherbot-{version}.dist-info"
    return {
        "weatherbot/__init__.py": b'__version__ = "2.0.0rc1"\n',
        "weatherbot/py.typed": b"",
        "weatherbot/DISCLAIMER.md": b"Informational only.\n",
        "weatherbot/web/static/index.html": b"<!doctype html><div id='root'></div>\n",
        "weatherbot/web/static/licenses.json": b"[]\n",
        "weatherbot/services/persistence/migrations/env.py": b"# env\n",
        "weatherbot/services/persistence/migrations/versions/0001_baseline.py": b"# 0001\n",
        f"{dist_info}/METADATA": _valid_metadata(version).encode("utf-8"),
        f"{dist_info}/WHEEL": b"Wheel-Version: 1.0\n",
        f"{dist_info}/RECORD": b"",
    }


def _default_sdist_members(version: str = VERSION) -> dict[str, bytes]:
    prefix = f"weatherbot-{version}"
    return {
        f"{prefix}/PKG-INFO": _valid_metadata(version).encode("utf-8"),
        f"{prefix}/pyproject.toml": (
            f'[project]\nname = "weatherbot"\nversion = "{version}"\n'.encode()
        ),
        f"{prefix}/pyproject.toml.orig": b'[project]\nname = "weatherbot"\n',
        f"{prefix}/README.md": b"# Weatherbot\n",
        f"{prefix}/LICENSE": b"MIT License\n",
        f"{prefix}/DISCLAIMER.md": b"Informational only.\n",
        f"{prefix}/src/weatherbot/__init__.py": b'"""Weatherbot."""\n',
    }


def _write_wheel(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)


def _write_sdist(path: Path, members: dict[str, bytes]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))


def _build_valid_dist(
    dist_dir: Path,
    *,
    version: str = VERSION,
    wheel_members: dict[str, bytes] | None = None,
    sdist_members: dict[str, bytes] | None = None,
) -> Path:
    dist_dir.mkdir(parents=True, exist_ok=True)
    _write_wheel(
        dist_dir / f"weatherbot-{version}-py3-none-any.whl",
        wheel_members if wheel_members is not None else _default_wheel_members(version),
    )
    _write_sdist(
        dist_dir / f"weatherbot-{version}.tar.gz",
        sdist_members if sdist_members is not None else _default_sdist_members(version),
    )
    return dist_dir


def test_valid_dist_passes_and_prints_sizes_and_hashes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dist_dir = _build_valid_dist(tmp_path / "dist")
    # uv build writes a .gitignore inside dist/; allowlist ignores it while rejecting other extras.
    (dist_dir / ".gitignore").write_text("*\n", encoding="utf-8")
    result = cd.check_dist(dist_dir, VERSION)
    assert result.ok, result.errors
    assert len(result.artifacts) == 2  # noqa: PLR2004 - wheel + sdist
    assert cd.main([str(dist_dir), "--version", VERSION]) == 0
    stdout = capsys.readouterr().out
    assert f"weatherbot-{VERSION}-py3-none-any.whl" in stdout
    assert f"weatherbot-{VERSION}.tar.gz" in stdout
    assert "sha256=" in stdout


def test_fails_when_wheel_contains_tests(tmp_path: Path) -> None:
    members = _default_wheel_members()
    members["tests/test_smoke.py"] = b"assert True\n"
    dist_dir = _build_valid_dist(tmp_path / "dist", wheel_members=members)
    result = cd.check_dist(dist_dir, VERSION)
    assert not result.ok
    assert any("tests/test_smoke.py" in err for err in result.errors)


def test_fails_when_wheel_missing_index_html(tmp_path: Path) -> None:
    members = _default_wheel_members()
    del members["weatherbot/web/static/index.html"]
    dist_dir = _build_valid_dist(tmp_path / "dist", wheel_members=members)
    result = cd.check_dist(dist_dir, VERSION)
    assert not result.ok
    assert any("index.html" in err for err in result.errors)


def test_fails_when_second_wheel_present(tmp_path: Path) -> None:
    dist_dir = _build_valid_dist(tmp_path / "dist")
    _write_wheel(
        dist_dir / "weatherbot-2.0.0rc2-py3-none-any.whl", _default_wheel_members("2.0.0rc2")
    )
    result = cd.check_dist(dist_dir, VERSION)
    assert not result.ok
    assert any("unexpected artifacts" in err for err in result.errors)


def test_fails_on_version_mismatch_in_filename_or_metadata(tmp_path: Path) -> None:
    dist_dir = _build_valid_dist(tmp_path / "dist")
    wrong_cli = cd.check_dist(dist_dir, "2.0.0")
    assert not wrong_cli.ok
    assert any("missing expected artifacts" in err for err in wrong_cli.errors)

    members = _default_wheel_members()
    members[f"weatherbot-{VERSION}.dist-info/METADATA"] = _valid_metadata("2.0.0").encode("utf-8")
    dist_meta = _build_valid_dist(tmp_path / "dist-meta", wheel_members=members)
    wrong_meta = cd.check_dist(dist_meta, VERSION)
    assert not wrong_meta.ok
    assert any("Version" in err for err in wrong_meta.errors)


def test_fails_when_sdist_has_unlisted_top_level_path(tmp_path: Path) -> None:
    members = _default_sdist_members()
    members[f"weatherbot-{VERSION}/scripts/helper.py"] = b"print('hi')\n"
    dist_dir = _build_valid_dist(tmp_path / "dist", sdist_members=members)
    result = cd.check_dist(dist_dir, VERSION)
    assert not result.ok
    assert any("unlisted top-level entries" in err for err in result.errors)


@pytest.mark.parametrize(
    "forbidden_member",
    [
        "weatherbot/__pycache__/mod.cpython-313.pyc",
        "weatherbot/mod.pyc",
        "weatherbot/config.toml",
        "weatherbot/.env",
        "weatherbot/local.sqlite3",
        "weatherbot/docs/guide.md",
        "scripts/run.py",
        "frontend/index.html",
    ],
)
def test_fails_on_forbidden_wheel_members(tmp_path: Path, forbidden_member: str) -> None:
    members = _default_wheel_members()
    members[forbidden_member] = b"x\n"
    dist_dir = _build_valid_dist(tmp_path / "dist", wheel_members=members)
    result = cd.check_dist(dist_dir, VERSION)
    assert not result.ok


@pytest.mark.parametrize("marker", ["AL802026", "Hurricane Demo"])
def test_fails_when_synthetic_storm_marker_appears(tmp_path: Path, marker: str) -> None:
    members = _default_wheel_members()
    members["weatherbot/notes.py"] = f'STORM = "{marker}"\n'.encode()
    dist_dir = _build_valid_dist(tmp_path / "dist", wheel_members=members)
    result = cd.check_dist(dist_dir, VERSION)
    assert not result.ok
    assert any(marker in err for err in result.errors)


def test_fails_when_unlisted_coordinate_appears_in_distribution(tmp_path: Path) -> None:
    members = _default_sdist_members()
    # Assemble synthetic coordinate at runtime so this test file stays R2-clean.
    synthetic_pair = f"{31}.{4159}, {-92}.{6535}"
    members[f"weatherbot-{VERSION}/README.md"] = f"Location: {synthetic_pair}\n".encode()
    dist_dir = _build_valid_dist(tmp_path / "dist", sdist_members=members)
    result = cd.check_dist(dist_dir, VERSION)
    assert not result.ok
    assert any("personal-data" in err for err in result.errors)


def test_fails_when_wheel_exceeds_size_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dist_dir = _build_valid_dist(tmp_path / "dist")
    monkeypatch.setattr(cd, "MAX_WHEEL_BYTES", 10)
    result = cd.check_dist(dist_dir, VERSION)
    assert not result.ok
    assert any("exceeds" in err for err in result.errors)


def test_fails_when_metadata_field_mismatches(tmp_path: Path) -> None:
    members = _default_wheel_members()
    members[f"weatherbot-{VERSION}.dist-info/METADATA"] = _valid_metadata(
        VERSION, **{"License-Expression": "Apache-2.0"}
    ).encode("utf-8")
    dist_dir = _build_valid_dist(tmp_path / "dist", wheel_members=members)
    result = cd.check_dist(dist_dir, VERSION)
    assert not result.ok
    assert any("License-Expression" in err for err in result.errors)


def test_minified_frontend_assets_exempt_from_r2_but_still_checked_for_r1_and_markers(
    tmp_path: Path,
) -> None:
    members = _default_wheel_members()
    # Build synthetic Leaflet/lucide bundle constants at runtime so this file stays R2-clean.
    pole_lat = f"{85}.{0}{511287798}"
    svg_arc = f"{3}.{319} {1}.{915}"
    members["weatherbot/web/static/assets/index-ABC.js"] = (
        f"const MAX_LATITUDE={pole_lat}; const d='{svg_arc}';\n".encode()
    )
    dist_dir = _build_valid_dist(tmp_path / "dist", wheel_members=members)
    assert cd.check_dist(dist_dir, VERSION).ok

    # Denylist R1 still fires inside compiled frontend assets.
    r1_result = cd.check_dist(dist_dir, VERSION, denylist=[pole_lat])
    assert not r1_result.ok
    assert any("R1" in err for err in r1_result.errors)

    # Synthetic storm markers still fire inside compiled frontend assets.
    members_marker = dict(members)
    members_marker["weatherbot/web/static/assets/index-ABC.js"] += b"// AL802026\n"
    dist_marker = _build_valid_dist(tmp_path / "dist-marker", wheel_members=members_marker)
    marker_result = cd.check_dist(dist_marker, VERSION)
    assert not marker_result.ok
    assert any("AL802026" in err for err in marker_result.errors)
