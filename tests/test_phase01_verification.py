# tests/test_phase01_verification.py
"""Phase 1 verifier integration and failure-reporting regressions."""

import functools
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

import verify_phase01 as verification

ROOT = Path(__file__).resolve().parents[1]
STATIC_COUNT = 50
USAGE_ERROR = 2
TYPER = '"typer>=0.27.3"'
PYPROJECT = """\
# pyproject.toml
[build-system]
requires = ["uv_build"]
build-backend = "uv_build"

[project]
name = "weatherbot"
version = "{version}"
requires-python = ">=3.13"
dependencies = [{dependencies}]

[project.scripts]
weatherbot = "weatherbot.cli:app"
"""
type Historical = Callable[[Path], bool]


class Repository:
    """A throwaway Git repository holding Phase 1's skeleton, tagged like Phase 1."""

    def __init__(self, root: Path) -> None:
        """Remember the repository root."""
        self.root = root

    def git(self, *args: str) -> None:
        """Run Git in the repository with a fixed identity."""
        executable = shutil.which("git")
        assert executable is not None
        subprocess.run(  # noqa: S603 - fixed argument list, no shell
            [
                executable,
                "-c",
                "user.name=Verifier Test",
                "-c",
                "user.email=test@example.invalid",
                *args,
            ],
            cwd=self.root,
            check=True,
            capture_output=True,
        )
        verification.index_files.cache_clear()

    def write(self, relative: str, text: str = "") -> None:
        """Write a file and stage it."""
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.git("add", relative)

    def pyproject(self, version: str = "2.0.0.dev0", dependencies: str = TYPER) -> None:
        """Write and stage a minimal ``pyproject.toml``."""
        self.write("pyproject.toml", PYPROJECT.format(version=version, dependencies=dependencies))

    def commit_and_tag(self) -> None:
        """Commit everything staged and tag it as Phase 1."""
        self.git("commit", "-q", "-m", "phase 1")
        self.git("tag", "-a", verification.PHASE_1_TAG, "-m", "phase 1")


@pytest.fixture
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Repository]:
    """Yield a repository whose working tree still matches Phase 1 and is not yet tagged.

    The user's and the system's Git configuration are replaced by an empty file, so no
    signing, hook path, or template setting of the machine reaches the throwaway repository.
    """
    empty = tmp_path / "gitconfig"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    root = tmp_path / "repository"
    root.mkdir()
    repo = Repository(root)
    repo.git("init", "-q", "-b", "main")
    for name in sorted(verification.SKELETON):
        repo.write(name)
    repo.pyproject()
    yield repo
    verification.index_files.cache_clear()


HISTORICAL_CHECKS: dict[str, Historical] = {
    "07": verification.project_identity,
    "09": verification.skeleton_kept,
    "12": verification.runtime_entry,
}


def test_roadmap_doc_exists() -> None:
    assert (ROOT / "docs/roadmap/phase01-roadmap.md").is_file()


def test_qa_findings_doc_exists() -> None:
    assert (ROOT / "docs/phase01-qa-findings.md").is_file()


def test_verify_script_runs_fast() -> None:
    result = subprocess.run(  # noqa: S603 - fixed script path and arguments, no shell
        [sys.executable, str(ROOT / "scripts/verify_phase01.py"), "--fast"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(re.findall(r"^\[PASS\] \d{2} ", result.stdout, re.MULTILINE)) == STATIC_COUNT


def test_phase_verify_matrix_includes_01() -> None:
    assert verification.matrix_includes_01()


def test_static_checks_continue_after_failure_without_echoing_content(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def broken() -> bool:
        message = "PRIVATE-SAMPLE-MUST-NOT-APPEAR"
        raise ValueError(message)

    monkeypatch.setattr(
        verification,
        "STATIC_CHECKS",
        (
            ("broken check", broken),
            ("later check", lambda: True),
        ),
    )
    outcomes = verification.run_static_checks()
    output = capsys.readouterr().out
    assert [item.status for item in outcomes] == ["FAIL", "PASS"]
    assert "PRIVATE-SAMPLE-MUST-NOT-APPEAR" not in output
    assert verification.summary("fast", outcomes, 0) == 1


def test_skipped_evidence_cannot_pass_the_post_matrix() -> None:
    result = verification.aggregate(
        "V7.4",
        "security",
        [
            verification.Outcome("secrets", "history scan", "SKIP"),
            verification.Outcome("sast", "SAST", "PASS"),
        ],
    )
    assert result.status == "SKIP"


def test_mode_flags_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit) as error:
        verification.parse_args(["--fast", "--post"])
    assert error.value.code == USAGE_ERROR


def test_historical_checks_pass_on_a_grown_tree(repository: Repository) -> None:
    repository.commit_and_tag()
    repository.write("src/weatherbot/models/__init__.py", '"""Models."""\n')
    repository.pyproject(version="2.1.0", dependencies=f'"pydantic>=2", "shapely>=2", {TYPER}')

    assert {number: check(repository.root) for number, check in HISTORICAL_CHECKS.items()} == {
        "07": True,
        "09": True,
        "12": True,
    }


def tag_another_version(repo: Repository) -> None:
    repo.pyproject(version="2.0.0")


def tag_an_extra_module(repo: Repository) -> None:
    repo.write("src/weatherbot/models/__init__.py")


def tag_a_second_dependency(repo: Repository) -> None:
    repo.pyproject(dependencies=f'"httpx>=0.28", {TYPER}')


def tag_a_lookalike_of_typer(repo: Repository) -> None:
    repo.pyproject(dependencies='"typer-slim>=0.27"')


def untrack_a_skeleton_file(repo: Repository) -> None:
    repo.git("rm", "-q", "src/weatherbot/py.typed")


def drop_typer(repo: Repository) -> None:
    repo.pyproject(dependencies='"pydantic>=2"')


def rename_the_project(repo: Repository) -> None:
    repo.write("pyproject.toml", "[project]\nname = 'other'\n")


@pytest.mark.parametrize(
    ("number", "tag_differently"),
    [
        ("07", tag_another_version),
        ("09", tag_an_extra_module),
        ("12", tag_a_second_dependency),
        ("12", tag_a_lookalike_of_typer),
    ],
)
def test_each_historical_check_fails_when_the_tagged_tree_differs(
    repository: Repository, number: str, tag_differently: Callable[[Repository], None]
) -> None:
    tag_differently(repository)
    repository.commit_and_tag()

    assert not HISTORICAL_CHECKS[number](repository.root)


@pytest.mark.parametrize(
    ("number", "grow_wrongly"),
    [
        ("09", untrack_a_skeleton_file),
        ("12", drop_typer),
        ("07", rename_the_project),
    ],
)
def test_live_halves_still_fail_after_the_tag(
    repository: Repository, number: str, grow_wrongly: Callable[[Repository], None]
) -> None:
    repository.commit_and_tag()
    grow_wrongly(repository)

    assert not HISTORICAL_CHECKS[number](repository.root)


@pytest.mark.parametrize("number", sorted(HISTORICAL_CHECKS))
def test_a_missing_tag_fails_closed(repository: Repository, number: str) -> None:
    repository.git("commit", "-q", "-m", "untagged")

    with pytest.raises(subprocess.CalledProcessError):
        HISTORICAL_CHECKS[number](repository.root)


def test_a_missing_tag_reports_fail_not_pass(
    repository: Repository, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository.git("commit", "-q", "-m", "untagged")
    monkeypatch.setattr(
        verification,
        "STATIC_CHECKS",
        tuple(
            (f"check {n}", functools.partial(check, repository.root))
            for n, check in HISTORICAL_CHECKS.items()
        ),
    )

    outcomes = verification.run_static_checks()

    assert [(o.status, o.reason) for o in outcomes] == [("FAIL", "CalledProcessError")] * 3


def test_historical_descriptions_name_the_tag() -> None:
    descriptions = [verification.STATIC_CHECKS[int(n) - 1][0] for n in HISTORICAL_CHECKS]

    assert all(verification.PHASE_1_TAG in text for text in descriptions)
