# tests/ai/test_ai_imports.py  # noqa: ERA001 - a file path, not code
"""Commands that do not use AI never load the Anthropic SDK (checked in a fresh process)."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SUPPORT = [ROOT / "scripts", *(ROOT / "tests" / name for name in ("contract", "sources", "cli"))]
SCRIPT = """
import sys
from pathlib import Path
sys.path[:0] = {support!r}
from cli_support import MIAMI, add_landmark, recorded_services, run
with recorded_services():
    if {args!r}[0] in ("status", "report"):
        add_landmark(MIAMI, "miami-dade")
    if {args!r}[0] == "report":
        run(["status"])
    ran = run({args!r})
loaded = sorted(name for name in ("anthropic", "httpx2") if name in sys.modules)
print(f"exit={{ran.exit_code}} loaded={{','.join(loaded) or '-'}}")
"""


@pytest.mark.parametrize(
    "args",
    [
        ["--version"],
        ["status", "--json"],
        ["config", "show"],
        ["report", "--out", "report.html"],
    ],
)
def test_a_command_that_does_not_use_ai_never_loads_the_sdk(args: list[str]) -> None:
    script = SCRIPT.format(support=[str(path) for path in SUPPORT], args=args)

    result = subprocess.run(  # noqa: S603 - this interpreter and a fixed script, no shell
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "exit=0 loaded=-"


def test_the_check_would_see_the_sdk_if_it_were_loaded() -> None:
    script = "import sys\nimport weatherbot.services.ai.caller\nprint('anthropic' in sys.modules)"

    result = subprocess.run(  # noqa: S603 - this interpreter and a fixed script, no shell
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=True,
    )

    assert result.stdout.strip() == "True"
