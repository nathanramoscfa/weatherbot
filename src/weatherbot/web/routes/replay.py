# src/weatherbot/web/routes/replay.py
"""``GET /api/replay`` routes: list storms, scrub timelines and assessments, and serve layers."""

from http import HTTPStatus
from typing import TYPE_CHECKING, Annotated, Final, Literal, cast

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BeforeValidator

from weatherbot.models import Location, Snapshot
from weatherbot.services.assessments import RULE_TRIGGERS, is_county_context
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.persistence.repositories import LocationRepository
from weatherbot.services.replay import ReplayCorpus, ReplayError, ReplayStep, replay_notes
from weatherbot.web.map_layers import build_map_response, build_wind_probability_response
from weatherbot.web.routes.assessments import (
    change_responses,
    evidence_response,
    official_response,
    threat_response,
    unavailable_response,
    wind_reading_response,
)
from weatherbot.web.schemas import (
    MapResponse,
    ReplayAssessmentResponse,
    ReplayStormsResponse,
    ReplayStormSummaryResponse,
    ReplayTimelineResponse,
    ReplayTimelineStepResponse,
    ThreatLevelResponse,
    WindProbabilityResponse,
)

if TYPE_CHECKING:
    from weatherbot.web.app import WebState

router = APIRouter()

NO_CORPUS_DETAIL: Final = "no replay corpus is configured; pass --corpus DIR or set [web] corpus"
UNKNOWN_ATCF_ID_DETAIL: Final = "unknown replay storm parameter: atcf_id"
UNKNOWN_ADVISORY_DETAIL: Final = "unknown replay advisory parameter: advisory"
UNKNOWN_LOCATION_DETAIL: Final = "unknown location query parameter: location"
CORRUPT_CORPUS_DETAIL: Final = "the replay corpus refused a file"


def _coerce_threshold_kt(value: object) -> object:
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return value


type WindThresholdQuery = Annotated[Literal[34, 50, 64], BeforeValidator(_coerce_threshold_kt)]


def _require_corpus(state: "WebState") -> ReplayCorpus:
    if state.corpus is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=NO_CORPUS_DETAIL,
        )
    return state.corpus


def _load_replay_snapshot(state: "WebState", atcf_id: str, advisory: str) -> Snapshot:
    corpus = _require_corpus(state)
    try:
        advisories = corpus.advisories(atcf_id)
    except ReplayError as err:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=UNKNOWN_ATCF_ID_DETAIL,
        ) from err

    if advisory not in advisories:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=UNKNOWN_ADVISORY_DETAIL,
        )

    try:
        return corpus.snapshot(atcf_id, advisory)
    except ReplayError as err:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=CORRUPT_CORPUS_DETAIL,
        ) from err


def _load_replay_timeline(
    state: "WebState",
    atcf_id: str,
    location: str,
) -> tuple[tuple[str, ...], Location, tuple[ReplayStep, ...]]:
    corpus = _require_corpus(state)
    timelines = state.replay_timelines
    if timelines is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=NO_CORPUS_DETAIL,
        )

    try:
        advisories = corpus.advisories(atcf_id)
    except ReplayError as err:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=UNKNOWN_ATCF_ID_DETAIL,
        ) from err

    stored = LocationRepository(state.database.engine, now=state.clock).get(location)
    if stored is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=UNKNOWN_LOCATION_DETAIL,
        )

    try:
        steps = timelines.timeline(
            atcf_id,
            stored,
            thresholds=state.settings.engine.thresholds(),
        )
    except ReplayError as err:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=CORRUPT_CORPUS_DETAIL,
        ) from err

    return advisories, stored, steps


@router.get("/api/replay")
def get_replay_storms(request: Request) -> ReplayStormsResponse:
    """List the historical storms and advisories available in the configured replay corpus."""
    state = cast("WebState", request.app.state.web)
    corpus = _require_corpus(state)
    try:
        storms = corpus.storms()
        summaries = tuple(
            ReplayStormSummaryResponse(
                atcf_id=storm.atcf_id,
                name=storm.name,
                advisory_count=storm.advisories,
                advisories=corpus.advisories(storm.atcf_id),
                first_issued_at=storm.first_issued_at,
                last_issued_at=storm.last_issued_at,
            )
            for storm in storms
        )
    except ReplayError as err:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=CORRUPT_CORPUS_DETAIL,
        ) from err

    return ReplayStormsResponse(
        storms=summaries,
        notice=NOTICE,
    )


@router.get("/api/replay/{atcf_id}/timeline")
def get_replay_timeline(
    request: Request,
    atcf_id: str,
    location: Annotated[
        str,
        Query(
            min_length=1,
            max_length=64,
            description="Stored location name to replay the storm at.",
        ),
    ],
) -> ReplayTimelineResponse:
    """Return every replayed advisory step and notes for ``atcf_id`` at ``location``."""
    state = cast("WebState", request.app.state.web)
    advisories, stored, steps = _load_replay_timeline(state, atcf_id, location)
    storm_name = (
        steps[-1].assessment.threats[0].storm_name
        if steps and steps[-1].assessment.threats
        else atcf_id
    )
    step_items = tuple(
        ReplayTimelineStepResponse(
            advisory_id=adv_id,
            advisory=next(
                (
                    str(threat.advisory)
                    for threat in step.assessment.threats
                    if threat.advisory is not None
                ),
                adv_id,
            ),
            issued_at=step.assessment.as_of,
            level=ThreatLevelResponse(
                number=int(step.assessment.level),
                label=step.assessment.level.label,
                actions=step.assessment.level.actions,
            ),
            rule=str(step.assessment.rule),
            rule_trigger=RULE_TRIGGERS[step.assessment.rule],
            complete=step.assessment.complete,
            official_codes=tuple(sorted({p.code for p in step.assessment.official if p.covers})),
            changes=change_responses(step.changes),
        )
        for adv_id, step in zip(advisories, steps, strict=True)
    )
    return ReplayTimelineResponse(
        atcf_id=atcf_id,
        name=storm_name,
        location=stored.name,
        time_zone=stored.nws.time_zone if stored.nws is not None else None,
        ruleset=state.settings.engine.thresholds().fingerprint(),
        notes=replay_notes(stored, steps),
        steps=step_items,
        notice=NOTICE,
    )


@router.get("/api/replay/{atcf_id}/{advisory}")
def get_replay_advisory_map(
    request: Request,
    atcf_id: str,
    advisory: str,
) -> MapResponse:
    """Build the GeoJSON map layer payload for one replayed advisory without decoding others."""
    state = cast("WebState", request.app.state.web)
    snapshot = _load_replay_snapshot(state, atcf_id, advisory)

    engine = state.database.engine
    locations = LocationRepository(engine, now=state.clock).list()

    return build_map_response(
        snapshot,
        locations,
    )


@router.get("/api/replay/{atcf_id}/{advisory}/assessment")
def get_replay_assessment(
    request: Request,
    atcf_id: str,
    advisory: str,
    location: Annotated[
        str,
        Query(
            min_length=1,
            max_length=64,
            description="Stored location name to replay the advisory at.",
        ),
    ],
) -> ReplayAssessmentResponse:
    """Return the full replayed assessment for ``atcf_id`` at ``advisory`` and ``location``."""
    state = cast("WebState", request.app.state.web)
    corpus = _require_corpus(state)
    try:
        advisories = corpus.advisories(atcf_id)
    except ReplayError as err:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=UNKNOWN_ATCF_ID_DETAIL,
        ) from err

    if advisory not in advisories:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=UNKNOWN_ADVISORY_DETAIL,
        )

    _, stored, steps = _load_replay_timeline(state, atcf_id, location)
    step = steps[advisories.index(advisory)]
    assessment = step.assessment
    level = assessment.level
    printed_advisory = next(
        (str(threat.advisory) for threat in assessment.threats if threat.advisory is not None),
        advisory,
    )
    storm_name = (
        steps[-1].assessment.threats[0].storm_name
        if steps and steps[-1].assessment.threats
        else atcf_id
    )
    return ReplayAssessmentResponse(
        origin="replay",
        atcf_id=atcf_id,
        name=storm_name,
        advisory_id=advisory,
        advisory=printed_advisory,
        location=stored.name,
        inside_nws_coverage=stored.nws is not None,
        time_zone=stored.nws.time_zone if stored.nws is not None else None,
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
        unavailable=tuple(unavailable_response(item) for item in assessment.unavailable),
        evidence=tuple(evidence_response(item) for item in assessment.evidence),
        official=tuple(
            official_response(product)
            for product in assessment.official
            if product.covers or is_county_context(product)
        ),
        wind_probabilities=tuple(
            wind_reading_response(reading) for reading in assessment.wind_probabilities
        ),
        threats=tuple(threat_response(threat) for threat in assessment.threats),
        changes=change_responses(step.changes),
        breakpoint_span=assessment.breakpoint_span,
        ruleset=assessment.ruleset,
        notice=NOTICE,
    )


@router.get("/api/replay/{atcf_id}/{advisory}/wind-probabilities")
def get_replay_advisory_wind_probabilities(
    request: Request,
    atcf_id: str,
    advisory: str,
    threshold_kt: WindThresholdQuery = 34,
) -> WindProbabilityResponse:
    """Build cumulative 120-hour wind probability bands for one replayed advisory."""
    state = cast("WebState", request.app.state.web)
    snapshot = _load_replay_snapshot(state, atcf_id, advisory)
    return build_wind_probability_response(snapshot, threshold_kt)
