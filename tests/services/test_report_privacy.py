# tests/services/test_report_privacy.py
"""Privacy scan over Level-5 HTML reports with and without the stored AI briefing."""

import html
import re
from datetime import UTC, datetime
from pathlib import Path

from ai_support import FIXTURES, MODEL, stream_blocks
from engine_support import DORIAN, IRMA, NASSAU, landmark_location
from scenarios import as_hurricane_warning, miami_dade, rebuilt, recorded, replay, rip_current

from weatherbot.engine import assess, diff
from weatherbot.models import AlertLevel, Assessment, ChangeEvent, Location, Thresholds
from weatherbot.services.ai.context import briefing_context
from weatherbot.services.ai.guard import ai_engine
from weatherbot.services.ai.outputs import NewOutput, OutputRepository
from weatherbot.services.ai.prompts import prompt_version
from weatherbot.services.ai.schemas import Briefing
from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import (
    AssessmentRepository,
    LocationRepository,
    SettingsRepository,
    SnapshotRepository,
)
from weatherbot.services.report import AI_LABEL_NOTE, ReportService, render_report

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
DECIMAL_3PLUS = re.compile(r"(?<![\d.])\d{1,3}\.\d{3,}(?![\d.])")
MIN_WHOLE_DIGITS = 3
FAKE_NTFY_TOPIC = "wb-private-topic-987654"
FAKE_NTFY_TOKEN = "tk_" + "private_report_secret_987654321"


def _coordinate_2plus_prefixes(lat: float, lon: float) -> set[str]:
    prefixes: set[str] = set()
    for val in (lat, lon, abs(lat), abs(lon)):
        for decimals in (2, 3, 4, 5, 6):
            prefixes.add(f"{val:.{decimals}f}")
        raw = str(val)
        if "." in raw:
            whole, frac = raw.split(".", 1)
            for end in range(2, len(frac) + 1):
                prefixes.add(f"{whole}.{frac[:end]}")
    return prefixes


def _km_renderings(value: float) -> set[str]:
    items = {repr(value), f"{value:.1f}", f"{value:.2f}"}
    whole = f"{value:.0f}"
    if len(whole) >= MIN_WHOLE_DIGITS and whole not in {"100", "200", "400", "500", "800"}:
        items.add(whole)
    return items


def _collect_measured_km(assessments: tuple[Assessment, ...]) -> list[float]:
    values = [
        val
        for assessment in assessments
        for threat in assessment.threats
        for val in (threat.distance_km, threat.closest_approach_km)
        if val is not None
    ]
    values.extend(
        ev.distance_km
        for assessment in assessments
        for ev in assessment.evidence
        if ev.distance_km is not None
    )
    values.extend(
        off.distance_km
        for assessment in assessments
        for off in assessment.official
        if off.distance_km is not None
    )
    return values


def _assert_no_raw_km_or_sentences(
    assessments: tuple[Assessment, ...],
    changes: tuple[ChangeEvent, ...],
    reports: tuple[str, ...],
) -> None:
    sentences = [
        *(ev.detail for assessment in assessments for ev in assessment.evidence),
        *(off.reason for assessment in assessments for off in assessment.official),
        *(chg.detail for chg in changes),
    ]
    for doc in reports:
        for sentence in sentences:
            assert sentence not in doc

    measured_km = _collect_measured_km(assessments)
    assert measured_km
    km_strings = set[str]().union(*(_km_renderings(val) for val in measured_km))
    for doc in reports:
        for km_val in km_strings:
            pat = re.compile(rf"(?<![\d.]){re.escape(km_val)}(?![\d])")
            assert not pat.search(doc), f"raw km figure {km_val!r} leaked into report"


def _seed_level_five_database(
    paths: AppPaths,
) -> tuple[Location, Location, Assessment, Assessment, tuple[ChangeEvent, ...], str, Briefing]:
    home = rebuilt(
        miami_dade(),
        name="Home",
        display_name="111 NW 1st Street, Downtown, Miami-Dade County, Florida",
    )
    island = rebuilt(
        landmark_location(NASSAU, name="Island Office"),
        display_name="Parliament Square, Bay Street, Nassau, New Providence",
    )
    alert_hw = as_hurricane_warning(rip_current())
    live_holder = rebuilt(
        recorded().snapshot,
        alerts={"Home": (alert_hw,)},
    )
    prev_home = rebuilt(
        assess(replay(IRMA, "22"), home, Thresholds()),
        origin="live",
        snapshot_id=live_holder.snapshot_id,
    )
    irma_raw = assess(replay(IRMA, "36"), home, Thresholds())
    alert_raw = assess(live_holder, home, Thresholds())
    home_assessment = rebuilt(
        irma_raw,
        origin="live",
        snapshot_id=live_holder.snapshot_id,
        evidence=irma_raw.evidence + alert_raw.evidence,
        official=irma_raw.official + alert_raw.official,
        threats=irma_raw.threats + alert_raw.threats,
    )
    home_changes = diff(prev_home, home_assessment)
    island_assessment = rebuilt(
        assess(replay(DORIAN, "30"), island, Thresholds()),
        origin="live",
        snapshot_id=live_holder.snapshot_id,
    )
    raw_sse = (FIXTURES / "eval-briefing-recorded-miami-dade.sse").read_text(encoding="utf-8")
    text_blocks = [b for b in stream_blocks(raw_sse) if b.get("type") == "text"]
    briefing_obj = Briefing.model_validate_json(str(text_blocks[0]["text"]))

    with open_database(paths, now=lambda: NOW) as database:
        SettingsRepository(database.engine).set("ntfy_topic", FAKE_NTFY_TOPIC)
        SettingsRepository(database.engine).set("ntfy_token", FAKE_NTFY_TOKEN)
        loc_repo = LocationRepository(database.engine, now=lambda: NOW)
        loc_repo.add(home)
        loc_repo.add(island)
        SnapshotRepository(database.engine).save(live_holder)
        assess_repo = AssessmentRepository(database.engine, now=lambda: NOW)
        stored_home = assess_repo.save(home_assessment, home_changes)
        assess_repo.save(island_assessment, ())
        ctx_home = briefing_context(stored_home.assessment, stored_home.changes, None)

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
                        "sources": [src.model_dump(mode="json") for src in ctx_home.sources],
                    },
                    location_name="Home",
                    assessment_id=stored_home.id,
                )
            )
        finally:
            ai_eng.dispose()

    assert alert_hw.area_desc is not None
    return (
        home,
        island,
        home_assessment,
        island_assessment,
        home_changes,
        alert_hw.area_desc,
        briefing_obj,
    )


def test_level_five_report_privacy_scan_default_and_with_briefing(tmp_path: Path) -> None:
    root = tmp_path / "privacy"
    paths = AppPaths(config_dir=root / "config", data_dir=root / "data")
    (
        home,
        island,
        home_assessment,
        island_assessment,
        home_changes,
        area_desc,
        briefing_obj,
    ) = _seed_level_five_database(paths)

    assert home_assessment.level == AlertLevel.HURRICANE_WARNING
    assert island_assessment.level == AlertLevel.HURRICANE_WARNING

    with open_database(paths, now=lambda: NOW) as database:
        service = ReportService(database.engine, now=lambda: NOW)
        default_data = service.build(with_briefing=False)
        briefing_data = service.build(with_briefing=True)

    for loc_entry in (*default_data.locations, *briefing_data.locations):
        assert not isinstance(loc_entry, Location)
        assert not hasattr(loc_entry, "point")
        assert not hasattr(loc_entry, "display_name")

    default_html = render_report(default_data)
    briefing_html = render_report(briefing_data)

    # 1. Both landmarks' coordinates at 2 or more decimals must be absent from both reports.
    coord_strings = _coordinate_2plus_prefixes(
        home.point.latitude, home.point.longitude
    ) | _coordinate_2plus_prefixes(island.point.latitude, island.point.longitude)
    for html_doc in (default_html, briefing_html):
        for coord in coord_strings:
            assert coord not in html_doc, f"coordinate {coord!r} leaked into report"
        cleaned_decimals = html_doc.replace("0.375rem", "")
        assert not DECIMAL_3PLUS.search(cleaned_decimals)

    # 2. Display names, zone IDs, NWS query URLs, and ntfy token/topic must be absent.
    forbidden_substrings = {
        "111 NW 1st Street",
        "Bay Street, Nassau",
        "New Providence",
        "FLZ173",
        "FLC086",
        "api.weather.gov",
        FAKE_NTFY_TOPIC,
        FAKE_NTFY_TOKEN,
        "private_report_secret",
    }
    for html_doc in (default_html, briefing_html):
        for forbidden in forbidden_substrings:
            assert forbidden not in html_doc, f"{forbidden!r} leaked into report"

    # 3. Raw kilometre figures and engine-written sentences must be absent from both reports.
    _assert_no_raw_km_or_sentences(
        (home_assessment, island_assessment),
        home_changes,
        (default_html, briefing_html),
    )

    # 4. Without the briefing, Miami, Dade, MFL, and areaDesc appear nowhere in default_html.
    for office_or_county in ("Miami", "Dade", "MFL", area_desc):
        assert office_or_county not in default_html, (
            f"{office_or_county!r} appeared in default report without briefing"
        )
    assert "report-ai-briefing" not in default_html

    # 5. With the briefing asked for, the unwithheld briefing appears with its label.
    assert "report-ai-briefing" in briefing_html
    assert "AI briefing · Claude Sonnet 5.5" in briefing_html
    assert AI_LABEL_NOTE in briefing_html
    assert html.escape(briefing_obj.situation, quote=True) in briefing_html
