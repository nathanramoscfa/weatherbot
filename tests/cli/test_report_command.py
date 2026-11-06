# tests/cli/test_report_command.py
"""Tests for ``weatherbot report``: file output, overwrite protection, briefing, and no SDK."""

import html
import subprocess
import sys
from pathlib import Path

from ai_support import FIXTURES, MODEL, stream_blocks
from cli_support import MIAMI, add_landmark, recorded_services, run
from source_support import NOW

from weatherbot.cli.runtime import EXIT_FAILED, EXIT_OK, EXIT_USAGE
from weatherbot.models import Thresholds
from weatherbot.services.ai.context import briefing_context
from weatherbot.services.ai.guard import ai_engine
from weatherbot.services.ai.outputs import NewOutput, OutputRepository
from weatherbot.services.ai.prompts import prompt_version
from weatherbot.services.ai.schemas import Briefing
from weatherbot.services.config import AppPaths
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import AssessmentRepository
from weatherbot.services.report import AI_LABEL_NOTE

ROOT = Path(__file__).resolve().parents[2]
SUPPORT = [ROOT / "scripts", *(ROOT / "tests" / name for name in ("contract", "sources", "cli"))]


def test_report_command_writes_html_refuses_overwrite_without_force_and_handles_briefing(
    tmp_path: Path,
) -> None:
    out_file = tmp_path / "out" / "report.html"
    missing_parent_out = tmp_path / "does-not-exist" / "report.html"

    with recorded_services():
        # Missing parent directory -> exit 2
        missing_parent = run(["report", "--out", str(missing_parent_out)])
        assert missing_parent.exit_code == EXIT_USAGE

        out_file.parent.mkdir(parents=True, exist_ok=True)

        # No location stored yet -> exit 1
        no_loc = run(["report", "--out", str(out_file)])
        assert no_loc.exit_code == EXIT_FAILED
        assert not out_file.exists()

        add_landmark(MIAMI, "miami-dade")
        status_res = run(["status"])
        assert status_res.exit_code == EXIT_OK

        # Unknown location -> exit 2
        unknown = run(["report", "NoSuchPlace", "--out", str(out_file)])
        assert unknown.exit_code == EXIT_USAGE
        assert not out_file.exists()

        # Store a recorded AI briefing for MIAMI
        paths = AppPaths.resolve()
        with open_database(paths, now=lambda: NOW) as database:
            latest = AssessmentRepository(database.engine).latest(MIAMI)
            assert latest is not None
            ctx = briefing_context(latest.assessment, latest.changes, None)
            raw_sse = (FIXTURES / "eval-briefing-recorded-miami-dade.sse").read_text(
                encoding="utf-8"
            )
            text_blocks = [b for b in stream_blocks(raw_sse) if b.get("type") == "text"]
            briefing_obj = Briefing.model_validate_json(str(text_blocks[0]["text"]))

            ai_eng = ai_engine(paths.database_path)
            try:
                OutputRepository(ai_eng, now=lambda: NOW).add(
                    NewOutput(
                        kind="briefing",
                        model=MODEL,
                        prompt_version=prompt_version(Thresholds()),
                        status="ok",
                        content={
                            "briefing": briefing_obj.model_dump(mode="json"),
                            "sources": [src.model_dump(mode="json") for src in ctx.sources],
                        },
                        location_name=MIAMI,
                        assessment_id=latest.id,
                    )
                )
            finally:
                ai_eng.dispose()

        # 1. Default report writes file, prints path and notice, omits AI briefing
        first = run(["report", "--out", str(out_file)])
        assert first.exit_code == EXIT_OK, first.stderr
        assert str(out_file) in first.stdout
        assert NOTICE in first.stdout
        default_html = out_file.read_text(encoding="utf-8")
        assert "<!doctype html>" in default_html
        assert MIAMI in default_html
        assert "report-ai-briefing" not in default_html

        # 2. Existing file without --force -> exit 2 and file is untouched
        out_file.write_text("sentinel", encoding="utf-8")
        refused = run(["report", "--out", str(out_file)])
        assert refused.exit_code == EXIT_USAGE
        assert out_file.read_text(encoding="utf-8") == "sentinel"

        # 3. With --force and --with-briefing -> overwrites and includes AI briefing
        forced = run(["report", MIAMI, "--out", str(out_file), "--force", "--with-briefing"])
        assert forced.exit_code == EXIT_OK, forced.stderr
        brief_html = out_file.read_text(encoding="utf-8")
        assert "report-ai-briefing" in brief_html
        assert AI_LABEL_NOTE in brief_html
        assert html.escape(briefing_obj.situation, quote=True) in brief_html


def test_report_command_never_loads_anthropic_sdk(tmp_path: Path) -> None:
    out_path = tmp_path / "no-sdk-report.html"
    script = f"""
import sys
sys.path[:0] = {[str(p) for p in SUPPORT]!r}
from cli_support import MIAMI, add_landmark, recorded_services, run
with recorded_services():
    add_landmark(MIAMI, "miami-dade")
    run(["status"])
    ran = run(["report", "--out", {str(out_path)!r}])
loaded = sorted(name for name in ("anthropic", "httpx2") if name in sys.modules)
print(f"exit={{ran.exit_code}} loaded={{','.join(loaded) or '-'}}")
"""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "exit=0 loaded=-"
    assert out_path.is_file()
