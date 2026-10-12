# scripts/audit_deps.py
"""Dependency audit for the security gate: ``pip-audit --strict`` over ``uv.lock``.

Auditing the live virtual environment would fail for the wrong reason (the editable
``weatherbot`` project is not on PyPI at its development version), so the gate audits
what is actually pinned: the lockfile, every dependency group included, exported with
hashes to a temporary requirements file. Because every requirement is pinned and
hashed, pip-audit looks the versions up without installing anything (``--disable-pip``).
Any finding, or any requirement pip-audit cannot audit, exits non-zero. Runs the same
on Windows and Ubuntu.

Usage (from anywhere in the repository)::

    uv run python scripts/audit_deps.py
"""

import shutil
import subprocess  # runs uv and pip-audit from argument lists, never a shell  # nosec B404
import sys
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    """Export the locked set and audit it.

    Returns:
        The exit status: 0 when the audit is clean, non-zero on any finding or failure.
    """
    uv = shutil.which("uv")
    if uv is None:
        print("audit_deps: `uv` is not on PATH", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="weatherbot-audit-") as directory:
        requirements = Path(directory) / "requirements.txt"
        export = subprocess.run(  # noqa: S603 - fixed argument list, no shell  # nosec B603
            [
                uv,
                "export",
                "--frozen",
                "--no-emit-project",
                "--all-groups",
                "--format",
                "requirements-txt",
                "--quiet",
                "--output-file",
                str(requirements),
            ],
            cwd=REPOSITORY_ROOT,
            check=False,
        )
        if export.returncode != 0:
            print("audit_deps: `uv export` failed; is uv.lock up to date?", file=sys.stderr)
            return export.returncode
        audit = subprocess.run(  # noqa: S603 - fixed argument list, no shell  # nosec B603
            [
                sys.executable,
                "-m",
                "pip_audit",
                "--strict",
                "--disable-pip",
                "--require-hashes",
                "--progress-spinner",
                "off",
                "--requirement",
                str(requirements),
            ],
            cwd=REPOSITORY_ROOT,
            check=False,
        )
        return audit.returncode


if __name__ == "__main__":
    raise SystemExit(main())
