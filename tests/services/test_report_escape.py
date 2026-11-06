# tests/services/test_report_escape.py
"""HTML-escaping tests for location names, official titles/codes, and AI briefing text."""

from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

from ai_support import MODEL
from scenarios import miami_dade, rebuilt, recorded_maps, rip_current

from weatherbot.engine import assess
from weatherbot.models import Thresholds
from weatherbot.services.ai.context import briefing_context
from weatherbot.services.ai.guard import ai_engine
from weatherbot.services.ai.outputs import NewOutput, OutputRepository
from weatherbot.services.ai.prompts import prompt_version
from weatherbot.services.ai.schemas import Briefing, SourceNote, TimelineItem
from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import (
    AssessmentRepository,
    LocationRepository,
    SnapshotRepository,
)
from weatherbot.services.report import ReportService, render_report

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


class _EscapeParser(HTMLParser):
    """Collects all parsed element tags and attribute names to verify no injection occurred."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.attrs: list[tuple[str, str]] = []
        self.text_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        self.tags.append(lower)
        for name, _ in attrs:
            self.attrs.append((lower, name.lower()))

    def handle_data(self, data: str) -> None:
        self.text_chunks.append(data)


def test_every_dynamic_value_is_html_escaped_across_location_official_and_ai_text(
    tmp_path: Path,
) -> None:
    payload_loc = 'Harbor <script>alert("loc")</script> "Pier" \'A\' onload=evil()'
    payload_code = 'Warning <script>alert("code")</script> "X" onerror="boom()"'
    payload_ai = (
        ' Briefing <script>alert("ai")</script> <img src=x onerror="pwn()"> "quoted" & \'single\''
    )

    loc = rebuilt(miami_dade(), name=payload_loc)
    alert = rebuilt(rip_current(), event=payload_code)
    snap = rebuilt(recorded_maps(), alerts={payload_loc: (alert,)})
    assessment = assess(snap, loc, Thresholds())

    root = tmp_path / "escape"
    paths = AppPaths(config_dir=root / "config", data_dir=root / "data")
    with open_database(paths, now=lambda: NOW) as database:
        LocationRepository(database.engine, now=lambda: NOW).add(loc)
        SnapshotRepository(database.engine).save(snap)
        stored = AssessmentRepository(database.engine, now=lambda: NOW).save(assessment, ())

        ctx = briefing_context(stored.assessment, stored.changes, None)
        first_key = ctx.sources[0].key
        injected_briefing = Briefing(
            situation=payload_ai,
            what_it_means_here=f"Meaning {payload_ai}",
            timeline=[
                TimelineItem(
                    when='2026-10-18 12:00 UTC <script>alert("when")</script> "q"',
                    what=f"Event {payload_ai}",
                    sources=[first_key],
                )
            ],
            actions=[f"Action {payload_ai}"],
            sources=[SourceNote(key=first_key, why=f"Why {payload_ai}")],
        )

        ai_eng = ai_engine(paths.database_path)
        try:
            OutputRepository(ai_eng, now=lambda: NOW).add(
                NewOutput(
                    kind="briefing",
                    model=MODEL,
                    prompt_version=prompt_version(Thresholds()),
                    status="ok",
                    content={
                        "briefing": injected_briefing.model_dump(mode="json"),
                        "sources": [src.model_dump(mode="json") for src in ctx.sources],
                    },
                    location_name=payload_loc,
                    assessment_id=stored.id,
                )
            )
        finally:
            ai_eng.dispose()

        data = ReportService(database.engine, now=lambda: NOW).build(with_briefing=True)
        html_doc = render_report(data)

    # Raw unescaped tags must never appear
    assert "<script>" not in html_doc
    assert "<img " not in html_doc
    assert "&lt;script&gt;" in html_doc
    assert "&quot;" in html_doc
    assert "&#x27;" in html_doc

    parser = _EscapeParser()
    parser.feed(html_doc)
    assert "script" not in parser.tags
    assert "img" not in parser.tags
    assert not [attr for _, attr in parser.attrs if attr.startswith("on")]

    full_text = "".join(parser.text_chunks)
    assert payload_loc in full_text
    assert payload_code in full_text
    assert payload_ai in full_text
