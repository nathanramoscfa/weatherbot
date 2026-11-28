# tests/test_release_workflow.py
"""Text-level trust-boundary tests for ``release.yml`` and ``install-canary.yml``."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
CANARY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "install-canary.yml"

ACTION_PIN_RE = re.compile(r"^[^\s]+@[0-9a-f]{40}\s+#\s+v\d+\.\d+\.\d+$")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _job(text: str, name: str) -> str:
    match = re.search(
        rf"^  {re.escape(name)}:\n.*?(?=^  [\w-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"missing job {name!r}"
    return match[0]


def _run_blocks(text: str) -> list[str]:
    """Extract every ``run:`` step body from a GitHub Actions workflow."""
    blocks: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^(\s+)(?:-\s+)?run:\s*(.*)$", line)
        if match is None:
            index += 1
            continue
        indent = len(match[1])
        rest = match[2].strip()
        if rest in {"|", ">-", ">", "|-"}:
            body_lines: list[str] = []
            index += 1
            while index < len(lines):
                sub = lines[index]
                if sub.strip() == "":
                    body_lines.append("")
                    index += 1
                    continue
                sub_indent = len(sub) - len(sub.lstrip(" "))
                if sub_indent <= indent:
                    break
                body_lines.append(sub)
                index += 1
            blocks.append("\n".join(body_lines))
        else:
            blocks.append(rest)
            index += 1
    return blocks


def test_release_workflow_triggers_permissions_and_concurrency() -> None:
    text = _read(RELEASE_WORKFLOW)

    # Triggers: exact two release-tag patterns and workflow_dispatch only.
    assert '      - "v[0-9]+.[0-9]+.[0-9]+"' in text
    assert '      - "v[0-9]+.[0-9]+.[0-9]+rc[0-9]+"' in text
    assert "  workflow_dispatch:" in text
    assert "pull_request_target:" not in text
    assert "branches:" not in text.split("jobs:", 1)[0]

    # Top-level least privilege and non-cancelling concurrency.
    header = text.split("jobs:", 1)[0]
    assert re.search(r"^permissions:\s*\{\}\s*$", header, re.MULTILINE)
    assert "cancel-in-progress: false" in header
    assert 'UV_LOCKED: "1"' in header


def test_release_workflow_job_permissions_and_environments() -> None:
    text = _read(RELEASE_WORKFLOW)
    all_jobs = (
        "build",
        "smoke-built",
        "publish-testpypi",
        "publish-pypi",
        "smoke-published",
        "github-release",
    )
    blocks = {name: _job(text, name) for name in all_jobs}

    # id-token: write appears ONLY in publish-testpypi and publish-pypi, each in its environment.
    id_token_jobs = {name for name, body in blocks.items() if "id-token: write" in body}
    assert id_token_jobs == {"publish-testpypi", "publish-pypi"}
    assert "name: testpypi" in blocks["publish-testpypi"]
    assert "repository-url: https://test.pypi.org/legacy/" in blocks["publish-testpypi"]
    assert "name: pypi" in blocks["publish-pypi"]
    assert "repository-url:" not in blocks["publish-pypi"]

    # Neither publish job grants contents permission.
    assert "contents:" not in blocks["publish-testpypi"]
    assert "contents:" not in blocks["publish-pypi"]

    # contents: write appears ONLY in github-release.
    contents_write_jobs = {name for name, body in blocks.items() if "contents: write" in body}
    assert contents_write_jobs == {"github-release"}

    # No repository secrets referenced anywhere.
    assert "secrets." not in text
    assert "self-hosted" not in text


def test_release_workflow_job_dependency_graph_and_guards() -> None:
    text = _read(RELEASE_WORKFLOW)
    build = _job(text, "build")
    smoke_built = _job(text, "smoke-built")
    pub_test = _job(text, "publish-testpypi")
    pub_pypi = _job(text, "publish-pypi")
    smoke_pub = _job(text, "smoke-published")
    gh_release = _job(text, "github-release")

    assert "scripts/check_dist.py" in build
    assert "git merge-base --is-ancestor" in build
    assert "weatherbot-replay-corpus-" in build

    assert "needs: [build]" in smoke_built
    assert "os: [ubuntu-latest, windows-latest]" in smoke_built
    assert 'python: ["3.13", "3.15"]' in smoke_built
    assert "scripts/release_smoke.py" in smoke_built

    # Both publish jobs depend on smoke-built and only run on push tags.
    assert "smoke-built" in pub_test
    assert "github.event_name == 'push'" in pub_test
    assert "is_candidate == 'true'" in pub_test
    assert "smoke-built" in pub_pypi
    assert "github.event_name == 'push'" in pub_pypi
    assert "is_candidate == 'false'" in pub_pypi

    # smoke-published runs whenever either publish job succeeded.
    assert "needs: [build, publish-testpypi, publish-pypi]" in smoke_pub
    assert "!cancelled()" in smoke_pub
    assert "needs.publish-testpypi.result == 'success'" in smoke_pub
    assert "needs.publish-pypi.result == 'success'" in smoke_pub
    assert "os: [ubuntu-latest, windows-latest]" in smoke_pub
    assert 'python: ["3.13", "3.15"]' in smoke_pub

    # github-release runs only after smoke-published succeeds.
    assert "needs: [build, smoke-published]" in gh_release
    assert "needs.smoke-published.result == 'success'" in gh_release
    assert "gh release create" in gh_release
    assert "--verify-tag" in gh_release
    assert "--prerelease" in gh_release


def test_install_canary_workflow_structure_and_guards() -> None:
    text = _read(CANARY_WORKFLOW)
    assert "schedule:" in text
    assert "cron:" in text
    assert "workflow_dispatch:" in text
    assert "simulate_failure:" in text
    assert "run-name:" in text
    assert "install-canary (simulated failure)" in text
    assert "permissions:" in text
    assert "contents: read" in text
    assert "contents: write" not in text
    assert "id-token:" not in text
    assert "pull_request_target:" not in text
    assert "secrets." not in text
    assert "self-hosted" not in text

    canary = _job(text, "canary")
    assert "os: [ubuntu-latest, windows-latest]" in canary
    assert "scripts/release_smoke.py --latest --min-version 2.0.0" in canary
    assert "inputs.simulate_failure" in canary


def test_both_workflows_pin_every_action_and_never_interpolate_untrusted_expressions() -> None:
    for path in (RELEASE_WORKFLOW, CANARY_WORKFLOW):
        text = _read(path)
        uses_lines = re.findall(r"^\s*-?\s*uses:\s*(.+)$", text, re.MULTILINE)
        assert uses_lines, path.name
        for line in uses_lines:
            assert ACTION_PIN_RE.fullmatch(line.strip()), f"{path.name}: unpinned action {line!r}"

        runs = _run_blocks(text)
        assert runs, path.name
        for block in runs:
            assert "${{" not in block, (
                f"{path.name}: expression interpolated directly in run:\n{block}"
            )
            assert "github.event" not in block, f"{path.name}: github.event in run:\n{block}"
            assert "github.ref" not in block, f"{path.name}: github.ref in run:\n{block}"
