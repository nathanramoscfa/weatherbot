# src/weatherbot/web/routes/assessments.py
"""``GET /api/assessments``: latest stored assessment per watched location and staleness."""

from collections.abc import Sequence
from datetime import UTC
from typing import TYPE_CHECKING, Final, cast

from fastapi import APIRouter, Request

from weatherbot.models import (
    ArrivalReading,
    ChangeEvent,
    Evidence,
    Location,
    LocationWindProbability,
    OfficialProduct,
    StormThreat,
    UnavailableInput,
)
from weatherbot.services.assessments import RULE_TRIGGERS, is_county_context
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.health import Staleness, duration_text, staleness
from weatherbot.services.persistence.repositories import (
    AssessmentRepository,
    HeartbeatRepository,
    LocationRepository,
    SnapshotRepository,
    StoredAssessment,
)
from weatherbot.web.map_layers import get_cached_snapshot_bundle
from weatherbot.web.schemas import (
    ArrivalReadingResponse,
    AssessmentChangeResponse,
    AssessmentEvidenceResponse,
    AssessmentOfficialProductResponse,
    AssessmentsResponse,
    AssessmentUnavailableResponse,
    EvacuationOrderResponse,
    LocationAssessmentResponse,
    StalenessItemResponse,
    StoredAssessmentResponse,
    StormThreatResponse,
    ThreatLevelResponse,
    WindReadingResponse,
)

if TYPE_CHECKING:
    from weatherbot.web.app import WebState

router = APIRouter()

TOGGLE_CHANGED_NOTE: Final = (
    "The evacuation-order toggle was changed after this assessment was stored; "
    "run a fresh check to assess with the updated toggle."
)


def round_km(value: float | None) -> float | None:
    """Round a geodesic distance to a tenth of a kilometre."""
    return round(value, 1) if value is not None else None


def round_hours(value: float | None) -> float | None:
    """Round a lead time to a tenth of an hour."""
    return round(value, 1) if value is not None else None


def round_bearing(value: float | None) -> int | None:
    """Round a bearing to a whole degree in ``0..359``."""
    return round(value) % 360 if value is not None else None


def _evidence_response(item: Evidence) -> AssessmentEvidenceResponse:
    return AssessmentEvidenceResponse(
        product=item.product,
        source_id=item.source_id,
        code=item.code,
        atcf_id=item.atcf_id,
        storm_name=item.storm_name,
        advisory=str(item.advisory) if item.advisory is not None else None,
        issued_at=item.issued_at,
        test=item.test,
        distance_km=round_km(item.distance_km),
        at_end=item.at_end,
        crs=item.crs,
        closest_approach_at=item.closest_approach_at,
        lead_h=round_hours(item.lead_h),
        detail=item.detail,
    )


def _official_response(product: OfficialProduct) -> AssessmentOfficialProductResponse:
    return AssessmentOfficialProductResponse(
        kind=product.kind,
        code=product.code,
        alert_id=product.alert_id,
        issuer=product.issuer,
        atcf_id=product.atcf_id,
        storm_name=product.storm_name,
        advisory=str(product.advisory) if product.advisory is not None else None,
        issued_at=product.issued_at,
        expires_at=product.expires_at,
        zones=product.zones,
        distance_km=round_km(product.distance_km),
        breakpoints=product.breakpoints,
        covers=product.covers,
        is_county_context=is_county_context(product),
        rule=str(product.rule) if product.rule is not None else None,
        reason=product.reason,
    )


def _wind_response(reading: LocationWindProbability) -> WindReadingResponse:
    return WindReadingResponse(
        threshold_kt=reading.threshold_kt,
        synoptic_at=reading.synoptic_at,
        reading=reading.reading,
        label=reading.label,
        lower_pct=reading.lower_pct,
        upper_pct=reading.upper_pct,
    )


def _arrival_response(reading: ArrivalReading) -> ArrivalReadingResponse:
    return ArrivalReadingResponse(
        kind=reading.kind,
        origin=reading.origin,
        reading=reading.reading,
        advisory=str(reading.advisory) if reading.advisory is not None else None,
        start=reading.start,
        end=reading.end,
        approach_at=reading.approach_at,
        label=reading.label,
        reason=reading.reason,
    )


def _threat_response(threat: StormThreat) -> StormThreatResponse:
    return StormThreatResponse(
        atcf_id=threat.atcf_id,
        storm_name=threat.storm_name,
        advisory=str(threat.advisory) if threat.advisory is not None else None,
        issued_at=threat.issued_at,
        category=threat.category,
        development=threat.development,
        in_cone=threat.in_cone,
        distance_km=round_km(threat.distance_km),
        bearing_deg=round_bearing(threat.bearing_deg),
        closest_approach_at=threat.closest_approach_at,
        closest_approach_km=round_km(threat.closest_approach_km),
        lead_h=round_hours(threat.lead_h),
        hurricane_by_approach=threat.hurricane_by_approach,
        earliest_arrival=_arrival_response(threat.earliest_arrival),
        most_likely_arrival=_arrival_response(threat.most_likely_arrival),
    )


def _unavailable_response(item: UnavailableInput) -> AssessmentUnavailableResponse:
    return AssessmentUnavailableResponse(
        kind=item.kind,
        source_id=item.source_id,
        storm_name=item.storm_name,
        threshold_kt=item.threshold_kt,
        reason=item.reason,
    )


def change_responses(changes: Sequence[ChangeEvent]) -> tuple[AssessmentChangeResponse, ...]:
    """Convert domain ``ChangeEvent`` items into ``AssessmentChangeResponse`` items."""
    return tuple(
        AssessmentChangeResponse(kind=event.kind, detail=event.detail) for event in changes
    )


def _staleness_responses(judged: Sequence[Staleness]) -> tuple[StalenessItemResponse, ...]:
    return tuple(
        StalenessItemResponse(
            kind=item.kind,
            name=item.name,
            last_success_at=item.last_success_at,
            expected_every_s=item.expected_every_s,
            age_s=item.age_s,
            stale=item.stale,
        )
        for item in judged
    )


def _stale_banner(entries: Sequence[StalenessItemResponse]) -> tuple[str, ...]:
    lines: list[str] = []
    for entry in entries:
        if not entry.stale or entry.expected_every_s is None:
            continue
        cadence = duration_text(entry.expected_every_s)
        if entry.age_s is None:
            lines.append(f"Stale data: {entry.name} has never succeeded; expected every {cadence}.")
        else:
            age = duration_text(entry.age_s)
            lines.append(
                f"Stale data: {entry.name} last succeeded {age} ago; expected every {cadence}."
            )
    return tuple(lines)


def stored_assessment_to_response(
    location: Location, stored: StoredAssessment
) -> StoredAssessmentResponse:
    """Build a ``StoredAssessmentResponse`` for ``location`` and its ``stored`` assessment."""
    assessment = stored.assessment
    level = assessment.level
    set_at = location.evacuation_order_set_at
    toggle_changed = set_at is not None and set_at > stored.stored_at
    return StoredAssessmentResponse(
        id=stored.id,
        stored_at=stored.stored_at,
        snapshot_id=assessment.snapshot_id,
        as_of=assessment.as_of,
        level=ThreatLevelResponse(
            number=int(level),
            label=level.label,
            actions=level.actions,
        ),
        rule=str(assessment.rule),
        rule_trigger=RULE_TRIGGERS[assessment.rule],
        complete=assessment.complete,
        unavailable=tuple(_unavailable_response(item) for item in assessment.unavailable),
        evidence=tuple(_evidence_response(item) for item in assessment.evidence),
        official=tuple(
            _official_response(product)
            for product in assessment.official
            if product.covers or is_county_context(product)
        ),
        wind_probabilities=tuple(
            _wind_response(reading) for reading in assessment.wind_probabilities
        ),
        threats=tuple(_threat_response(threat) for threat in assessment.threats),
        changes=change_responses(stored.changes),
        breakpoint_span=assessment.breakpoint_span,
        evacuation_order=EvacuationOrderResponse(
            on=location.evacuation_order_in_effect,
            set_at=location.evacuation_order_set_at,
        ),
        ruleset=assessment.ruleset,
        toggle_changed=toggle_changed,
        toggle_note=TOGGLE_CHANGED_NOTE if toggle_changed else None,
    )


def _location_assessment_response(
    location: Location, stored: StoredAssessment | None
) -> LocationAssessmentResponse:
    return LocationAssessmentResponse(
        name=location.name,
        inside_nws_coverage=location.nws is not None,
        time_zone=location.nws.time_zone if location.nws is not None else None,
        evacuation_order=EvacuationOrderResponse(
            on=location.evacuation_order_in_effect,
            set_at=location.evacuation_order_set_at,
        ),
        breakpoint_span=(
            stored.assessment.breakpoint_span if stored is not None else location.breakpoint_span
        ),
        assessment=(
            stored_assessment_to_response(location, stored) if stored is not None else None
        ),
    )


@router.get("/api/assessments")
def get_assessments(request: Request) -> AssessmentsResponse:
    """Return each stored location's latest assessment, staleness, and snapshot summary."""
    state = cast("WebState", request.app.state.web)
    engine = state.database.engine
    now = state.clock().astimezone(UTC)

    locations = LocationRepository(engine, now=state.clock).list()
    assessment_repo = AssessmentRepository(engine, now=state.clock)
    location_items = tuple(
        _location_assessment_response(loc, assessment_repo.latest(loc.name)) for loc in locations
    )

    bundle = get_cached_snapshot_bundle(SnapshotRepository(engine))
    snapshot_summary = bundle.summary(now) if bundle is not None else None

    heartbeats = HeartbeatRepository(engine, now=state.clock).rows()
    judged = _staleness_responses(staleness(heartbeats, now))

    return AssessmentsResponse(
        snapshot=snapshot_summary,
        locations=location_items,
        staleness=judged,
        stale_banner=_stale_banner(judged),
        notice=NOTICE,
    )
