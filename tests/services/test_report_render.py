# tests/services/test_report_render.py
"""Tests for ``ReportService`` and ``render_report`` across levels, states, and SVG sparklines."""

import html
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from uuid import uuid4

import pytest
from ai_support import FIXTURES, MODEL, stream_blocks
from scenarios import SCENARIOS, Scenario, rebuilt, recorded_maps
from sqlalchemy import Engine

from weatherbot.engine import assess
from weatherbot.models import AlertLevel, Thresholds, UnavailableInput
from weatherbot.services.ai.context import BriefingContext, briefing_context
from weatherbot.services.ai.display import PUBLIC_PAGES
from weatherbot.services.ai.guard import ai_engine
from weatherbot.services.ai.outputs import NewOutput, OutputRepository
from weatherbot.services.ai.prompts import prompt_version
from weatherbot.services.ai.schemas import Briefing
from weatherbot.services.config import AppPaths
from weatherbot.services.disclaimer import DISCLAIMER_URL, ESSENTIALS, NOTICE
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import (
    AssessmentRepository,
    LocationNotFoundError,
    LocationRepository,
    SnapshotRepository,
)
from weatherbot.services.report import (
    AI_LABEL_NOTE,
    REPORT_META_CSP,
    NoReportAssessmentError,
    ReportService,
    linear_scale,
    render_report,
    round_svg,
    step_path,
    time_scale,
)

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
FORBIDDEN_TAGS = frozenset({"script", "link", "img", "iframe", "object", "base", "embed"})


def _make_paths(root: Path) -> AppPaths:
    return AppPaths(config_dir=root / "config", data_dir=root / "data")


class _ReportDomInspector(HTMLParser):
    """Inspects tags, attributes, links, and meta CSP in a rendered HTML report."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.forbidden_tags: list[str] = []
        self.event_attributes: list[tuple[str, str]] = []
        self.links: list[dict[str, str | None]] = []
        self.meta_csp: list[str] = []
        self.has_title = False
        self.svg_count = 0
        self.sr_table_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        self.tags.append(lower)
        if lower in FORBIDDEN_TAGS:
            self.forbidden_tags.append(lower)
        attr_map = {k.lower(): v for k, v in attrs}
        for attr_name in attr_map:
            if attr_name.startswith("on"):
                self.event_attributes.append((lower, attr_name))
        if lower == "a":
            self.links.append(attr_map)
        elif lower == "meta":
            if (attr_map.get("http-equiv") or "").lower() == "content-security-policy":
                self.meta_csp.append(attr_map.get("content") or "")
        elif lower == "title":
            self.has_title = True
        elif lower == "svg":
            self.svg_count += 1
        elif lower == "table" and attr_map.get("class") == "sr-only":
            self.sr_table_count += 1


def _scenario_for_level(level: AlertLevel) -> Scenario:
    return next(item for item in SCENARIOS if item.level == level)


def _recorded_briefing_payload(context: BriefingContext) -> dict[str, object]:
    raw_sse = (FIXTURES / "eval-briefing-recorded-miami-dade.sse").read_text(encoding="utf-8")
    text_blocks = [b for b in stream_blocks(raw_sse) if b.get("type") == "text"]
    briefing = Briefing.model_validate_json(str(text_blocks[0]["text"]))
    return {
        "briefing": briefing.model_dump(mode="json"),
        "sources": [src.model_dump(mode="json") for src in context.sources],
    }


def _store_scenario_as_live(
    engine: Engine,
    scenario: Scenario,
    *,
    location_name: str | None = None,
) -> int:
    snapshot, location = scenario.inputs()
    if location_name is not None:
        location = rebuilt(location, name=location_name)
    live_holder = rebuilt(
        recorded_maps(),
        snapshot_id=uuid4(),
        started_at=snapshot.started_at,
        completed_at=snapshot.completed_at,
        alerts={},
    )
    assessment = rebuilt(
        assess(snapshot, location, Thresholds()),
        origin="live",
        snapshot_id=live_holder.snapshot_id,
    )
    loc_repo = LocationRepository(engine, now=lambda: NOW)
    if loc_repo.get(location.name) is None:
        loc_repo.add(location)
    SnapshotRepository(engine).save(live_holder)
    stored = AssessmentRepository(engine, now=lambda: NOW).save(assessment, ())
    return stored.id


@pytest.mark.parametrize(
    "level",
    [
        AlertLevel.ALL_CLEAR,
        AlertLevel.TROPICAL_STORM_THREAT,
        AlertLevel.WATCH_HURRICANE_THREAT,
        AlertLevel.WARNING_WATCH_EVACUATION,
        AlertLevel.HURRICANE_WARNING,
    ],
)
def test_render_report_covers_every_alert_level_and_contains_no_forbidden_tags(
    tmp_path: Path,
    level: AlertLevel,
) -> None:
    scen = _scenario_for_level(level)
    paths = _make_paths(tmp_path / f"level-{int(level)}")
    with open_database(paths, now=lambda: NOW) as database:
        _store_scenario_as_live(database.engine, scen)
        service = ReportService(database.engine, now=lambda: NOW)
        data = service.build()
        rendered = render_report(data)

    assert len(data.locations) == 1
    loc = data.locations[0]
    assert loc.context.level.number == int(level)
    assert f"Level {int(level)}" in rendered
    assert level.label in rendered
    assert level.actions in rendered
    assert NOTICE in rendered
    for paragraph in ESSENTIALS:
        assert html.escape(paragraph, quote=True) in rendered
    assert DISCLAIMER_URL in rendered

    inspector = _ReportDomInspector()
    inspector.feed(rendered)
    assert inspector.has_title
    assert inspector.meta_csp == [REPORT_META_CSP]
    assert not inspector.forbidden_tags
    assert not inspector.event_attributes
    assert inspector.svg_count == 1
    assert inspector.sr_table_count == 1
    allowed_urls = set(PUBLIC_PAGES.values())
    for link in inspector.links:
        assert link.get("href") in allowed_urls
        assert link.get("rel") == "noopener noreferrer"


def test_incomplete_assessment_renders_at_least_unavailable_inputs_and_dashed_sparkline(
    tmp_path: Path,
) -> None:
    scen = next(item for item in SCENARIOS if item.name == "partial-alerts-failed")
    paths = _make_paths(tmp_path / "incomplete")
    with open_database(paths, now=lambda: NOW) as database:
        _store_scenario_as_live(database.engine, scen)
        data = ReportService(database.engine, now=lambda: NOW).build()
        rendered = render_report(data)

    assert not data.locations[0].context.complete
    assert "at least Level 1" in rendered
    assert "Unavailable inputs and stale sources" in rendered
    assert "nws_alerts" in rendered
    assert 'stroke-dasharray="2 2"' in rendered
    assert "Incomplete (floor)" in rendered


def test_briefing_inclusion_states_none_stored_withheld_ok_and_stale(
    tmp_path: Path,
) -> None:
    scen = _scenario_for_level(AlertLevel.ALL_CLEAR)
    paths = _make_paths(tmp_path / "briefings")
    with open_database(paths, now=lambda: NOW) as database:
        first_id = _store_scenario_as_live(database.engine, scen)
        service = ReportService(database.engine, now=lambda: NOW)

        # 1. No AI outputs stored at all: both default and with_briefing=True omit AI section.
        default_no_ai = render_report(service.build(with_briefing=False))
        asked_no_ai = render_report(service.build(with_briefing=True))
        assert "report-ai-briefing" not in default_no_ai
        assert "report-ai-briefing" not in asked_no_ai

        # 2. Withheld briefing stored: omitted even when with_briefing=True.
        ai_eng = ai_engine(paths.database_path)
        try:
            outputs = OutputRepository(ai_eng, now=lambda: NOW)
            loc_name = scen.inputs()[1].name
            outputs.add(
                NewOutput(
                    kind="briefing",
                    model=MODEL,
                    prompt_version=prompt_version(Thresholds()),
                    status="withheld",
                    content=None,
                    location_name=loc_name,
                    assessment_id=first_id,
                    withheld_reason="level_mismatch",
                )
            )
            withheld_report = render_report(service.build(with_briefing=True))
            assert "report-ai-briefing" not in withheld_report

            # 3. Unwithheld ("ok") briefing stored for current assessment:
            # omitted when with_briefing=False, included and fresh when with_briefing=True.
            latest_stored = AssessmentRepository(database.engine).latest(loc_name)
            assert latest_stored is not None
            ctx = briefing_context(latest_stored.assessment, latest_stored.changes, None)
            outputs.add(
                NewOutput(
                    kind="briefing",
                    model=MODEL,
                    prompt_version=prompt_version(Thresholds()),
                    status="ok",
                    content=_recorded_briefing_payload(ctx),
                    location_name=loc_name,
                    assessment_id=first_id,
                )
            )
            assert "report-ai-briefing" not in render_report(service.build(with_briefing=False))
            fresh_data = service.build(with_briefing=True)
            assert fresh_data.locations[0].briefing is not None
            assert not fresh_data.locations[0].briefing.stale
            fresh_html = render_report(fresh_data)
            expected_label = (
                "AI briefing · Claude Sonnet 5.5 · written 2026-10-18 12:00 UTC · may be wrong"
            )
            assert expected_label in fresh_html
            assert AI_LABEL_NOTE in fresh_html
            assert "Stale briefing:" not in fresh_html

            # 4. Newer assessment stored -> briefing is marked stale.
            later_snap = rebuilt(
                recorded_maps(),
                snapshot_id=uuid4(),
                completed_at=NOW + timedelta(hours=1),
                alerts={},
            )
            SnapshotRepository(database.engine).save(later_snap)
            newer_assessment = rebuilt(
                latest_stored.assessment,
                snapshot_id=later_snap.snapshot_id,
                as_of=later_snap.completed_at,
            )
            AssessmentRepository(database.engine, now=lambda: NOW).save(newer_assessment, ())
            stale_data = service.build(with_briefing=True)
            assert stale_data.locations[0].briefing is not None
            assert stale_data.locations[0].briefing.stale
            stale_html = render_report(stale_data)
            assert "Stale briefing: written for an earlier assessment" in stale_html
        finally:
            ai_eng.dispose()


def test_sparkline_scales_and_step_path_mirror_frontend_chart_scale() -> None:
    expected_rounded = 12.35
    pad_left = 6.0
    pad_right = 74.0
    mid_x = 40.0
    assert round_svg(-0.0) == 0.0
    assert round_svg(12.3456) == expected_rounded
    assert step_path(()) == ""
    assert step_path([(pad_left, 16.0)]) == "M 6 16 L 6 16"
    assert step_path([(pad_left, 16.0), (mid_x, 10.0), (pad_right, 4.0)]) == (
        "M 6 16 L 40 16 L 40 10 L 74 10 L 74 4"
    )
    t0 = datetime(2026, 10, 18, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
    t_scale = time_scale((t0, t1), (pad_left, pad_right))
    assert t_scale(t0) == pad_left
    assert t_scale(t1) == pad_right
    assert t_scale(datetime(2026, 10, 18, 6, 0, tzinfo=UTC)) == mid_x
    flat_time = time_scale((t0, t0), (pad_left, pad_right))
    assert flat_time(t0) == mid_x
    y_scale = linear_scale((1.0, 5.0), (16.0, 4.0))
    pts = tuple(y_scale(float(lvl)) for lvl in range(1, 6))
    assert pts == (16.0, 13.0, 10.0, 7.0, 4.0)


def test_build_falls_back_cleanly_when_context_exceeds_limit_and_checks_errors(
    tmp_path: Path,
) -> None:
    scen = _scenario_for_level(AlertLevel.ALL_CLEAR)
    paths = _make_paths(tmp_path / "oversized")
    with open_database(paths, now=lambda: NOW) as database:
        service = ReportService(database.engine, now=lambda: NOW)
        with pytest.raises(NoReportAssessmentError):
            service.build()

        _store_scenario_as_live(database.engine, scen)
        with pytest.raises(LocationNotFoundError):
            service.build("Unknown Place")

        loc_name = scen.inputs()[1].name
        latest = AssessmentRepository(database.engine).latest(loc_name)
        assert latest is not None
        huge_unavailable = tuple(
            UnavailableInput(
                kind="nws_alerts",
                source_id="nws-alerts-zone",
                storm_name=f"Storm-{idx:04d}-" + ("X" * 200),
                reason="unavailable",
            )
            for idx in range(2500)
        )
        oversized_snap = rebuilt(
            recorded_maps(),
            snapshot_id=uuid4(),
            completed_at=latest.assessment.as_of + timedelta(hours=2),
            alerts={},
        )
        SnapshotRepository(database.engine).save(oversized_snap)
        oversized = rebuilt(
            latest.assessment,
            snapshot_id=oversized_snap.snapshot_id,
            complete=False,
            unavailable=huge_unavailable,
            as_of=oversized_snap.completed_at,
        )
        AssessmentRepository(database.engine, now=lambda: NOW).save(oversized, ())
        data = service.build(loc_name)
        assert data.locations[0].name == loc_name
        assert "Level 1" in render_report(data)
