# src/weatherbot/services/report.py
"""Self-contained HTML threat report built from the privacy-reduced briefing context.

``ReportService`` reads stored locations, their latest stored assessments, their level
history points, and (only when explicitly requested) their latest unwithheld stored AI
briefing. Every location's assessment passes through ``briefing_context(..., snapshot=None)``
so the report carries only coarsened bands, 8-point compass bearings, and whole-hour
instants, never coordinates, raw kilometre figures, zone identifiers, forecast offices, or
engine-written sentences. ``render_report`` produces a single offline HTML5 document with
inline styles, an inline SVG level sparkline with a visually hidden table alternative, a
strict ``<meta http-equiv="Content-Security-Policy">``, and ``@media print`` rules.
"""

import html
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from sqlalchemy import Engine

from weatherbot.services.ai.briefing import stored_briefing
from weatherbot.services.ai.context import (
    ArrivalRef,
    BriefingContext,
    ChangeRef,
    ContextTooLarge,
    EvidenceRef,
    OfficialRef,
    SourceRef,
    ThreatRef,
    UnavailableRef,
    WindRef,
    briefing_context,
    to_hour,
)
from weatherbot.services.ai.display import public_page
from weatherbot.services.ai.outputs import OutputRepository, StoredOutput
from weatherbot.services.ai.pricing import model_name
from weatherbot.services.ai.schemas import Briefing
from weatherbot.services.disclaimer import DISCLAIMER_URL, ESSENTIALS, NOTICE
from weatherbot.services.health import staleness
from weatherbot.services.persistence.repositories import (
    AssessmentRepository,
    HeartbeatRepository,
    LevelPoint,
    LocationNotFoundError,
    LocationRepository,
    StoredAssessment,
)

AI_LABEL_NOTE: Final = (
    "AI-generated \u00b7 may be wrong \u00b7 the level above comes from official products"
)
REPORT_META_CSP: Final = "default-src 'none'; style-src 'unsafe-inline'"
REPORT_HEADER_CSP: Final = "default-src 'none'; style-src 'unsafe-inline'; sandbox"

SPARKLINE_WIDTH: Final = 80
SPARKLINE_HEIGHT: Final = 20
SPARKLINE_PAD_LEFT: Final = 6.0
SPARKLINE_PAD_RIGHT: Final = 74.0
SPARKLINE_PAD_BOTTOM: Final = 16.0
SPARKLINE_PAD_TOP: Final = 4.0

_PRODUCT_LABELS: Final[dict[str, str]] = {
    "evacuation_order": "Local evacuation order",
    "nws_alert": "NWS alert",
    "watch_warning_segment": "NHC watch-warning segment",
    "cone": "NHC forecast cone",
    "wind_probability": "NHC wind-speed probabilities",
    "development_region": "NHC outlook development region",
}


def _now() -> datetime:
    return datetime.now(UTC)


class NoReportAssessmentError(Exception):
    """No stored assessment is available to build the report."""


@dataclass(frozen=True)
class ReportBriefing:
    """An unwithheld stored AI briefing included in a location's report."""

    model: str
    model_label: str
    created_at: datetime
    stale: bool
    briefing: Briefing
    sources: tuple[SourceRef, ...]


@dataclass(frozen=True)
class ReportLocation:
    """One watched location's coarsened report data."""

    name: str
    context: BriefingContext
    level_points: tuple[LevelPoint, ...]
    briefing: ReportBriefing | None = None


@dataclass(frozen=True)
class ReportData:
    """The complete data for a rendered HTML report; holds no ``Location`` model."""

    generated_at: datetime
    locations: tuple[ReportLocation, ...]


# Sparkline geometry helpers (mirroring frontend/src/charts/scale.ts) --------------------


def round_svg(value: float) -> float:
    """Round an SVG coordinate to two decimal places, normalizing ``-0.0`` to ``0.0``."""
    rounded = round(value, 2)
    return 0.0 if rounded == 0.0 else rounded


def _fmt_svg(value: float) -> str:
    rounded = round_svg(value)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def linear_scale(
    domain: tuple[float, float], range_bounds: tuple[float, float]
) -> Callable[[float], float]:
    """Build a linear scale from ``domain`` to ``range_bounds``."""
    d0, d1 = domain
    r0, r1 = range_bounds
    span = d1 - d0
    if span == 0.0:
        mid = round_svg((r0 + r1) / 2.0)
        return lambda _value: mid

    def _scale(value: float) -> float:
        ratio = (value - d0) / span
        return round_svg(r0 + ratio * (r1 - r0))

    return _scale


def time_scale(
    domain: tuple[datetime, datetime], range_bounds: tuple[float, float]
) -> Callable[[datetime], float]:
    """Build a UTC timestamp scale from ``domain`` to ``range_bounds``."""
    d0 = domain[0].astimezone(UTC).timestamp()
    d1 = domain[1].astimezone(UTC).timestamp()
    r0, r1 = range_bounds
    span = d1 - d0
    if span == 0.0:
        mid = round_svg((r0 + r1) / 2.0)
        return lambda _value: mid

    def _scale(value: datetime) -> float:
        ts = value.astimezone(UTC).timestamp()
        ratio = (ts - d0) / span
        return round_svg(r0 + ratio * (r1 - r0))

    return _scale


def step_path(points: Sequence[tuple[float, float]]) -> str:
    """Build an SVG horizontal-then-vertical step path string from ``(x, y)`` pairs."""
    if not points:
        return ""
    first_x, first_y = points[0]
    if len(points) == 1:
        fx = _fmt_svg(first_x)
        fy = _fmt_svg(first_y)
        return f"M {fx} {fy} L {fx} {fy}"
    commands: list[str] = [f"M {_fmt_svg(first_x)} {_fmt_svg(first_y)}"]
    for idx in range(1, len(points)):
        prev_x, prev_y = points[idx - 1]
        curr_x, curr_y = points[idx]
        px = round_svg(prev_x)
        py = round_svg(prev_y)
        cx = round_svg(curr_x)
        cy = round_svg(curr_y)
        if cx != px:
            commands.append(f"L {_fmt_svg(cx)} {_fmt_svg(py)}")
        if cy != py or cx == px:
            commands.append(f"L {_fmt_svg(cx)} {_fmt_svg(cy)}")
    return " ".join(commands)


# Service --------------------------------------------------------------------------------


def _build_context(stored: StoredAssessment, stale: Sequence[str]) -> BriefingContext:
    """Build ``BriefingContext`` with ``snapshot=None``, falling back if oversized."""
    try:
        return briefing_context(stored.assessment, stored.changes, None, stale)
    except ContextTooLarge:
        trimmed = stored.assessment.model_copy(
            update={"evidence": (), "official": (), "wind_probabilities": ()}
        )
        try:
            return briefing_context(trimmed, (), None, stale)
        except ContextTooLarge:
            minimal = trimmed.model_copy(update={"threats": (), "unavailable": ()})
            return briefing_context(minimal, (), None, ())


def _unpack_briefing(stored: StoredOutput | None, assessment_id: int) -> ReportBriefing | None:
    if stored is None or stored.status != "ok" or stored.content is None:
        return None
    briefing, sources = stored_briefing(stored)
    return ReportBriefing(
        model=stored.model,
        model_label=model_name(stored.model),
        created_at=to_hour(stored.created_at),
        stale=stored.assessment_id != assessment_id,
        briefing=briefing,
        sources=sources,
    )


class ReportService:
    """Builds privacy-reduced ``ReportData`` from stored rows without writing anything."""

    def __init__(self, engine: Engine, *, now: Callable[[], datetime] = _now) -> None:
        """Create the service.

        Args:
            engine: The open database engine.
            now: Clock returning the current UTC datetime.
        """
        self._engine = engine
        self._now = now

    def build(self, location: str | None = None, *, with_briefing: bool = False) -> ReportData:
        """Build ``ReportData`` for ``location`` or every stored location in name order.

        Args:
            location: Optional single stored location name.
            with_briefing: Include each location's latest unwithheld stored AI briefing.

        Returns:
            The assembled ``ReportData``.

        Raises:
            LocationNotFoundError: ``location`` is given and not stored.
            NoReportAssessmentError: No locations are stored, or a target location has no
                stored assessment yet.
        """
        now = self._now().astimezone(UTC)
        stored_names = [loc.name for loc in LocationRepository(self._engine, now=self._now).list()]
        if location is not None:
            if location not in stored_names:
                message = "no location of that name is stored"
                raise LocationNotFoundError(message)
            target_names = [location]
        else:
            if not stored_names:
                message = "no location is stored"
                raise NoReportAssessmentError(message)
            target_names = stored_names

        heartbeats = HeartbeatRepository(self._engine, now=self._now).rows()
        judged = staleness(heartbeats, now)
        stale_sources = tuple(item.name for item in judged if item.stale and item.kind == "source")

        assessments = AssessmentRepository(self._engine, now=self._now)
        outputs = OutputRepository(self._engine, now=self._now) if with_briefing else None

        report_locations: list[ReportLocation] = []
        for name in target_names:
            latest = assessments.latest(name)
            if latest is None:
                message = "no assessment is stored for the requested location"
                raise NoReportAssessmentError(message)
            context = _build_context(latest, stale_sources)
            points = assessments.level_points(name)
            briefing_item = (
                _unpack_briefing(outputs.latest_briefing(name), latest.id)
                if outputs is not None
                else None
            )
            report_locations.append(
                ReportLocation(
                    name=name,
                    context=context,
                    level_points=points,
                    briefing=briefing_item,
                )
            )

        return ReportData(generated_at=now, locations=tuple(report_locations))


# HTML Renderer --------------------------------------------------------------------------


def _esc(value: str) -> str:
    """Escape text and attribute values for safe HTML interpolation."""
    return html.escape(value, quote=True)


def _format_hour(instant: datetime | None) -> str:
    if instant is None:
        return "time not stated"
    return to_hour(instant).strftime("%Y-%m-%d %H:%M UTC")


def _format_instant(instant: datetime) -> str:
    return instant.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _agency(source_id: str) -> str:
    if source_id.startswith("nhc-"):
        return "NHC"
    if source_id.startswith("nws-"):
        return "NWS"
    return source_id


def _source_link(source: SourceRef | None, fallback_title: str) -> str:
    if source is None:
        return _esc(fallback_title)
    title = _esc(source.title)
    page = public_page(source.source_id)
    if page is None:
        return title
    return f'<a href="{_esc(page)}" rel="noopener noreferrer">{title}</a>'


def _render_sparkline(location_name: str, points: Sequence[LevelPoint]) -> str:
    ordered = sorted(points, key=lambda pt: (pt.as_of.astimezone(UTC), pt.id))
    current = ordered[-1] if ordered else None
    has_incomplete = any(not pt.complete for pt in ordered)
    if current is not None:
        suffix = ", includes incomplete assessment" if has_incomplete else ""
        title_text = (
            f"{location_name} threat level sparkline: current Level {int(current.level)} "
            f"({current.level.label}){suffix}"
        )
    else:
        title_text = f"{location_name} threat level sparkline: no stored assessments"

    y_scale = linear_scale((1.0, 5.0), (SPARKLINE_PAD_BOTTOM, SPARKLINE_PAD_TOP))
    if ordered:
        x_scale = time_scale(
            (ordered[0].as_of, ordered[-1].as_of),
            (SPARKLINE_PAD_LEFT, SPARKLINE_PAD_RIGHT),
        )
    else:

        def _default_x(_dt: datetime) -> float:
            return SPARKLINE_PAD_RIGHT

        x_scale = _default_x

    if len(ordered) == 1:
        y_val = y_scale(float(ordered[0].level))
        step_pts: list[tuple[float, float]] = [
            (SPARKLINE_PAD_LEFT, y_val),
            (SPARKLINE_PAD_RIGHT, y_val),
        ]
    else:
        step_pts = [(x_scale(pt.as_of), y_scale(float(pt.level))) for pt in ordered]

    path_d = step_path(step_pts)
    dot_x = SPARKLINE_PAD_RIGHT if len(ordered) <= 1 else round_svg(x_scale(ordered[-1].as_of))
    dot_y = round_svg(y_scale(float(ordered[-1].level))) if ordered else round_svg(y_scale(1.0))
    dash_attr = ' stroke-dasharray="2 2"' if has_incomplete else ""
    path_el = (
        f'<path d="{_esc(path_d)}" fill="none" stroke="currentColor" '
        f'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"{dash_attr} />'
        if path_d
        else ""
    )
    circle_el = (
        f'<circle cx="{_fmt_svg(dot_x)}" cy="{_fmt_svg(dot_y)}" r="2.5" fill="currentColor" />'
        if current is not None
        else ""
    )
    rows_html = "".join(
        "<tr>"
        f"<td>{_esc(_format_hour(pt.as_of))}</td>"
        f"<td>{_esc(f'Level {int(pt.level)} ({pt.level.label})')}</td>"
        f"<td>{_esc(str(pt.rule))}</td>"
        f"<td>{'Complete' if pt.complete else 'Incomplete (floor)'}</td>"
        "</tr>"
        for pt in ordered
    )
    esc_title = _esc(title_text)
    return (
        '<div class="sparkline-box">'
        f'<svg role="img" aria-label="{esc_title}" width="{SPARKLINE_WIDTH}" '
        f'height="{SPARKLINE_HEIGHT}" viewBox="0 0 {SPARKLINE_WIDTH} {SPARKLINE_HEIGHT}">'
        f"<title>{esc_title}</title>"
        f'<line x1="{_fmt_svg(SPARKLINE_PAD_LEFT)}" y1="{_fmt_svg(SPARKLINE_PAD_BOTTOM)}" '
        f'x2="{_fmt_svg(SPARKLINE_PAD_RIGHT)}" y2="{_fmt_svg(SPARKLINE_PAD_BOTTOM)}" '
        'stroke="#cbd5e1" stroke-width="0.75" />'
        f"{path_el}{circle_el}"
        "</svg>"
        '<table class="sr-only">'
        f"<caption>{esc_title}</caption>"
        "<thead><tr>"
        '<th scope="col">As of (UTC)</th>'
        '<th scope="col">Level</th>'
        '<th scope="col">Rule</th>'
        '<th scope="col">Completeness</th>'
        "</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table>"
        "</div>"
    )


def _render_evidence_item(item: EvidenceRef, sources: dict[str, SourceRef]) -> str:
    source = sources.get(item.source) if item.source is not None else None
    fallback = _PRODUCT_LABELS.get(item.product, item.product)
    if item.code:
        fallback = f"{fallback}: {item.code}"
    title_html = _source_link(source, fallback)
    agency = _agency(source.source_id) if source is not None else "Local"
    issued = _format_hour(item.issued or (source.issued if source is not None else None))
    extra = ""
    if item.chance_pct is not None and item.threshold_kt is not None:
        extra = f" \u00b7 {item.chance_pct}% chance of {item.threshold_kt}-kt winds"
    return (
        "<li>"
        f"<strong>{title_html}</strong> "
        f"({_esc(agency)} \u00b7 issued {_esc(issued)} \u00b7 rule {_esc(item.rule)} "
        f"\u00b7 test {_esc(item.test)}{_esc(extra)})"
        "</li>"
    )


def _render_official_item(item: OfficialRef, sources: dict[str, SourceRef]) -> str:
    source = sources.get(item.source)
    fallback = f"{_PRODUCT_LABELS.get(item.product, item.product)}: {item.code}"
    title_html = _source_link(source, fallback)
    agency = _agency(source.source_id) if source is not None else "Official"
    issued = _format_hour(item.issued)
    expires = f" \u00b7 expires {_esc(_format_hour(item.expires))}" if item.expires else ""
    coverage = "Covers location" if item.covers else "Nearby / county context"
    rule_part = f" \u00b7 rule {_esc(item.rule)}" if item.rule else ""
    return (
        "<li>"
        f"<strong>{title_html}</strong> "
        f"({_esc(agency)} \u00b7 issued {_esc(issued)}{expires} \u00b7 {_esc(coverage)}{rule_part})"
        "</li>"
    )


def _render_wind_item(item: WindRef, sources: dict[str, SourceRef]) -> str:
    source = sources.get(item.source)
    agency = _agency(source.source_id) if source is not None else "NHC"
    return (
        "<li>"
        f"<strong>{item.threshold_kt}-kt winds:</strong> {_esc(item.band)} ({_esc(agency)})"
        "</li>"
    )


def _arrival_words(arrival: ArrivalRef) -> str:
    label = (
        "Earliest reasonable tropical-storm wind arrival"
        if arrival.kind == "earliest_reasonable"
        else "Most likely tropical-storm wind arrival"
    )
    outcome = arrival.outcome
    if outcome == "between" and arrival.start is not None and arrival.end is not None:
        when = f"{_format_hour(arrival.start)} to {_format_hour(arrival.end)}"
    elif outcome == "before" and arrival.end is not None:
        when = f"before {_format_hour(arrival.end)}"
    elif outcome == "after" and arrival.start is not None:
        when = f"after {_format_hour(arrival.start)}"
    elif outcome == "track" and arrival.approach is not None:
        when = f"track closest approach around {_format_hour(arrival.approach)}"
    elif outcome == "outside":
        when = "not expected at this location"
    else:
        when = "arrival time product unavailable"
    return f"{label}: {when}"


def _render_threat_item(threat: ThreatRef) -> str:
    header_parts = [f"{threat.storm} ({threat.atcf_id})"]
    if threat.advisory:
        header_parts.append(f"advisory {threat.advisory}")
    if threat.category is not None:
        header_parts.append(f"Category {threat.category}")
    elif threat.development:
        header_parts.append(threat.development)
    cone_text = (
        "Inside forecast cone"
        if threat.in_cone is True
        else "Outside forecast cone"
        if threat.in_cone is False
        else "Forecast cone unavailable"
    )
    distance_text = threat.distance or "distance band unavailable"
    bearing_text = (
        f"location lies {threat.compass_from_storm} from storm center"
        if threat.compass_from_storm
        else "bearing unavailable"
    )
    approach_parts: list[str] = []
    if threat.closest_approach is not None:
        approach_parts.append(f"closest approach {_format_hour(threat.closest_approach)}")
    if threat.lead_h is not None:
        approach_parts.append(f"lead {threat.lead_h} h")
    if threat.hurricane_by_approach is True:
        approach_parts.append("forecast at hurricane strength by closest approach")
    approach_text = ", ".join(approach_parts) if approach_parts else "closest approach unavailable"
    arrivals_html = "".join(
        f"<li>{_esc(_arrival_words(arrival))}</li>" for arrival in threat.arrivals
    )
    return (
        '<li class="threat-item">'
        f"<div><strong>{_esc(', '.join(header_parts))}</strong></div>"
        f"<div>{_esc(cone_text)} \u00b7 Distance: {_esc(distance_text)} \u00b7 "
        f"Bearing: {_esc(bearing_text)} \u00b7 {_esc(approach_text)}</div>"
        f"<ul>{arrivals_html}</ul>"
        "</li>"
    )


def _change_words(change: ChangeRef) -> str:
    kind = change.kind
    if kind == "level_changed":
        direction = change.direction or "changed"
        return (
            f"Threat level {direction} from Level {change.previous_level} "
            f"to Level {change.level} (rule {change.rule})."
        )
    if kind in ("official_added", "official_changed"):
        verb = "added" if kind == "official_added" else "updated"
        codes = ", ".join(change.codes) if change.codes else "official product"
        return f"Official product {verb}: {codes}."
    if kind == "official_removed":
        codes = ", ".join(change.previous_codes) if change.previous_codes else "official product"
        return f"Official product ended: {codes}."
    if kind in ("cone_entered", "cone_left"):
        verb = "entered" if kind == "cone_entered" else "left"
        return f"{change.storm or 'Storm'}: location {verb} the forecast cone."
    return (
        f"{change.storm or 'Storm'} advisory {change.advisory or '?'} issued"
        f"{f' (after {change.previous_advisory})' if change.previous_advisory else ''}."
    )


def _render_unavailable(unavailable: Sequence[UnavailableRef], stale_sources: Sequence[str]) -> str:
    if not unavailable and not stale_sources:
        return ""
    items: list[str] = [
        f"<li>Unavailable input: {_esc(item.kind)}"
        f"{_esc(f' ({_agency(item.source_id)})' if item.source_id else '')}</li>"
        for item in unavailable
    ]
    items.extend(
        f"<li>Stale source heartbeat: {_esc(source_name)}</li>" for source_name in stale_sources
    )
    return (
        '<section class="report-subsection">'
        "<h3>Unavailable inputs and stale sources</h3>"
        f"<ul>{''.join(items)}</ul>"
        "</section>"
    )


def _render_briefing(report_briefing: ReportBriefing | None) -> str:
    if report_briefing is None:
        return ""
    b = report_briefing.briefing
    sources_by_key = {src.key: src for src in report_briefing.sources}
    written = _format_hour(report_briefing.created_at)
    label_line = (
        f"AI briefing \u00b7 {report_briefing.model_label} \u00b7 "
        f"written {written} \u00b7 may be wrong"
    )
    stale_html = (
        '<p class="ai-stale-note">'
        "Stale briefing: written for an earlier assessment; a newer assessment is now stored."
        "</p>"
        if report_briefing.stale
        else ""
    )
    timeline_items = "".join(
        "<li>"
        f"<strong>{_esc(item.when)}:</strong> {_esc(item.what)}"
        f"{_esc(f' [{", ".join(item.sources)}]') if item.sources else ''}"
        "</li>"
        for item in b.timeline
    )
    action_items = "".join(f"<li>{_esc(action)}</li>" for action in b.actions)
    source_items: list[str] = []
    for note in b.sources:
        src_ref = sources_by_key.get(note.key)
        link_html = _source_link(src_ref, note.key)
        agency = f" ({_esc(_agency(src_ref.source_id))})" if src_ref is not None else ""
        source_items.append(
            f"<li><strong>{_esc(note.key)}</strong> ({link_html}{agency}): {_esc(note.why)}</li>"
        )
    return (
        '<section class="ai-briefing-section" data-testid="report-ai-briefing">'
        '<div class="ai-label" data-testid="ai-label">'
        f'<p class="ai-label-title">{_esc(label_line)}</p>'
        f'<p class="ai-label-note">{_esc(AI_LABEL_NOTE)}</p>'
        "</div>"
        f"{stale_html}"
        '<div class="ai-section"><h4>Situation</h4>'
        f"<p>{_esc(b.situation)}</p></div>"
        '<div class="ai-section"><h4>What it means here</h4>'
        f"<p>{_esc(b.what_it_means_here)}</p></div>"
        '<div class="ai-section"><h4>Timeline</h4>'
        f"<ul>{timeline_items}</ul></div>"
        '<div class="ai-section"><h4>Actions</h4>'
        f"<ul>{action_items}</ul></div>"
        '<div class="ai-section"><h4>Sources</h4>'
        f"<ul>{''.join(source_items)}</ul></div>"
        "</section>"
    )


def _render_location(loc: ReportLocation) -> str:
    ctx = loc.context
    sources_by_key = {src.key: src for src in ctx.sources}
    at_least_prefix = "at least " if not ctx.complete else ""
    incomplete_note = (
        '<p class="incomplete-banner">'
        f"Assessment incomplete: threat is at least Level {ctx.level.number} "
        f"({_esc(ctx.level.label)}) \u2014 floor based on available inputs."
        "</p>"
        if not ctx.complete
        else ""
    )

    evidence_html = (
        "<ul>"
        + "".join(_render_evidence_item(item, sources_by_key) for item in ctx.evidence)
        + "</ul>"
        if ctx.evidence
        else "<p>No rule match evidence recorded (baseline clear conditions).</p>"
    )
    official_html = (
        "<ul>"
        + "".join(_render_official_item(item, sources_by_key) for item in ctx.official)
        + "</ul>"
        if ctx.official
        else "<p>No active NWS alerts or NHC watch-warning segments.</p>"
    )
    winds_html = (
        "<ul>"
        + "".join(_render_wind_item(item, sources_by_key) for item in ctx.wind_probabilities)
        + "</ul>"
        if ctx.wind_probabilities
        else "<p>No wind-speed probability bands recorded.</p>"
    )
    threats_html = (
        "<ul>" + "".join(_render_threat_item(item) for item in ctx.threats) + "</ul>"
        if ctx.threats
        else "<p>No active tropical cyclones tracked.</p>"
    )
    changes_html = (
        "<ul>" + "".join(f"<li>{_esc(_change_words(item))}</li>" for item in ctx.changes) + "</ul>"
        if ctx.changes
        else "<p>No changes since the previous assessment.</p>"
    )
    sparkline_html = _render_sparkline(loc.name, loc.level_points)
    unavailable_html = _render_unavailable(ctx.unavailable, ctx.stale_sources)
    briefing_html = _render_briefing(loc.briefing)

    return (
        '<article class="location-report">'
        '<header class="location-header">'
        '<div class="location-heading-row">'
        f"<h2>{_esc(loc.name)}</h2>"
        f"{sparkline_html}"
        "</div>"
        '<p class="level-line">'
        f"<strong>Threat level: {_esc(at_least_prefix)}Level {ctx.level.number} "
        f"\u2014 {_esc(ctx.level.label)}</strong> "
        f"(rule <code>{_esc(ctx.rule)}</code> \u00b7 assessed {_esc(_format_hour(ctx.as_of))})"
        "</p>"
        '<p class="actions-line">'
        f"<strong>Recommended actions:</strong> {_esc(ctx.level.actions)}</p>"
        '<p class="trigger-line">'
        f"<strong>Deciding rule trigger:</strong> {_esc(ctx.trigger)}</p>"
        f"{incomplete_note}"
        "</header>"
        f"{unavailable_html}"
        '<section class="report-subsection"><h3>Deciding evidence</h3>'
        f"{evidence_html}</section>"
        '<section class="report-subsection"><h3>Official watches, warnings, and alerts</h3>'
        f"{official_html}</section>"
        '<section class="report-subsection"><h3>Wind-speed probability bands</h3>'
        f"{winds_html}</section>"
        '<section class="report-subsection"><h3>Storm threats and wind arrival times</h3>'
        f"{threats_html}</section>"
        '<section class="report-subsection"><h3>Recent changes</h3>'
        f"{changes_html}</section>"
        f"{briefing_html}"
        "</article>"
    )


_STYLES: Final = """
  :root {
    color-scheme: light;
  }
  * {
    box-sizing: border-box;
  }
  body {
    margin: 0;
    padding: 1.5rem;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 0.95rem;
    line-height: 1.5;
    color: #0f172a;
    background: #ffffff;
  }
  main, header.report-top, footer.report-footer {
    max-width: 56rem;
    margin: 0 auto;
  }
  header.report-top {
    border-bottom: 2px solid #0f172a;
    padding-bottom: 0.75rem;
    margin-bottom: 1.25rem;
  }
  header.report-top h1 {
    margin: 0 0 0.35rem 0;
    font-size: 1.4rem;
  }
  .notice-banner {
    margin: 0;
    padding: 0.5rem 0.75rem;
    background: #f8fafc;
    border: 1px solid #cbd5e1;
    border-radius: 0.375rem;
    font-weight: 600;
  }
  article.location-report {
    border: 1px solid #cbd5e1;
    border-radius: 0.5rem;
    padding: 1rem 1.25rem;
    margin-bottom: 1.25rem;
    background: #ffffff;
  }
  header.location-header {
    break-inside: avoid;
    page-break-inside: avoid;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 0.75rem;
    margin-bottom: 0.75rem;
  }
  .location-heading-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    break-inside: avoid;
    page-break-inside: avoid;
  }
  .location-heading-row h2 {
    margin: 0;
    font-size: 1.25rem;
    break-after: avoid;
    page-break-after: avoid;
  }
  .level-line, .actions-line, .trigger-line {
    margin: 0.25rem 0;
  }
  .incomplete-banner {
    margin: 0.5rem 0 0 0;
    padding: 0.4rem 0.6rem;
    border: 1px solid #d97706;
    background: #fffbeb;
    font-weight: 600;
  }
  .report-subsection {
    margin-top: 0.75rem;
    break-inside: avoid;
    page-break-inside: avoid;
  }
  .report-subsection h3 {
    margin: 0 0 0.25rem 0;
    font-size: 1rem;
    break-after: avoid;
    page-break-after: avoid;
  }
  .report-subsection ul {
    margin: 0.25rem 0;
    padding-left: 1.25rem;
  }
  .report-subsection p {
    margin: 0.25rem 0;
  }
  .ai-briefing-section {
    margin-top: 1rem;
    padding: 0.75rem 1rem;
    border: 1px solid #c4b5fd;
    border-radius: 0.375rem;
    background: #faf5ff;
    break-inside: avoid;
    page-break-inside: avoid;
  }
  .ai-label-title {
    margin: 0;
    font-weight: 600;
    font-size: 0.85rem;
  }
  .ai-label-note {
    margin: 0.15rem 0 0.5rem 0;
    font-size: 0.8rem;
  }
  .ai-stale-note {
    margin: 0.35rem 0;
    padding: 0.35rem 0.5rem;
    border: 1px solid #d97706;
    background: #fffbeb;
    font-weight: 600;
    font-size: 0.85rem;
  }
  .ai-section h4 {
    margin: 0.5rem 0 0.2rem 0;
    font-size: 0.9rem;
  }
  .ai-section p, .ai-section ul {
    margin: 0.2rem 0;
  }
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }
  footer.report-footer {
    border-top: 1px solid #cbd5e1;
    padding-top: 0.75rem;
    margin-top: 1.5rem;
    font-size: 0.85rem;
    color: #334155;
  }
  footer.report-footer p {
    margin: 0.35rem 0;
  }
  @media print {
    body {
      padding: 0;
      color: #000000;
      background: #ffffff;
    }
    .notice-banner,
    article.location-report,
    .incomplete-banner,
    .ai-briefing-section,
    .ai-stale-note {
      color: #000000;
      background: #ffffff;
      border-color: #000000;
    }
    header.location-header,
    .location-heading-row,
    .location-heading-row h2,
    .report-subsection,
    .report-subsection h3 {
      break-inside: avoid;
      page-break-inside: avoid;
      break-after: avoid;
      page-break-after: avoid;
    }
    a {
      color: #000000;
      text-decoration: underline;
    }
  }
"""


def render_report(data: ReportData) -> str:
    """Render ``ReportData`` into a self-contained HTML5 document string."""
    names = ", ".join(loc.name for loc in data.locations)
    title = f"Weatherbot Threat Report \u2014 {names}" if names else "Weatherbot Threat Report"
    locations_html = "".join(_render_location(loc) for loc in data.locations)
    essentials_html = "".join(f"<p>{_esc(paragraph)}</p>" for paragraph in ESSENTIALS)
    generated_str = _format_instant(data.generated_at)

    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'  <meta http-equiv="Content-Security-Policy" content="{_esc(REPORT_META_CSP)}">\n'
        f"  <title>{_esc(title)}</title>\n"
        f"  <style>{_STYLES}</style>\n"
        "</head>\n"
        "<body>\n"
        '  <header class="report-top">\n'
        f"    <h1>{_esc(title)}</h1>\n"
        f'    <p class="notice-banner" data-testid="report-notice">{_esc(NOTICE)}</p>\n'
        "  </header>\n"
        f"  <main>\n{locations_html}\n  </main>\n"
        '  <footer class="report-footer" data-testid="report-footer">\n'
        f"    <p><strong>Generated:</strong> {_esc(generated_str)}</p>\n"
        f"    {essentials_html}\n"
        f"    <p>Full disclaimer: {_esc(DISCLAIMER_URL)}</p>\n"
        "  </footer>\n"
        "</body>\n"
        "</html>\n"
    )
