# src/weatherbot/web/routes/replay.py
"""``GET /api/replay`` and ``GET /api/replay/{atcf_id}/{advisory}``: historical map replay."""

from http import HTTPStatus
from typing import TYPE_CHECKING, Annotated, Final, Literal, cast

from fastapi import APIRouter, HTTPException, Request
from pydantic import BeforeValidator

from weatherbot.models import Snapshot
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.persistence.repositories import (
    AssessmentRepository,
    LocationRepository,
)
from weatherbot.services.replay import ReplayCorpus, ReplayError
from weatherbot.web.map_layers import build_map_response, build_wind_probability_response
from weatherbot.web.schemas import (
    MapResponse,
    ReplayStormsResponse,
    ReplayStormSummaryResponse,
    WindProbabilityResponse,
)

if TYPE_CHECKING:
    from weatherbot.web.app import WebState

router = APIRouter()

NO_CORPUS_DETAIL: Final = "no replay corpus is configured; pass --corpus DIR or set [web] corpus"
UNKNOWN_ATCF_ID_DETAIL: Final = "unknown replay storm parameter: atcf_id"
UNKNOWN_ADVISORY_DETAIL: Final = "unknown replay advisory parameter: advisory"
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
    assessment_repo = AssessmentRepository(engine, now=state.clock)
    assessments = {loc.name: assessment_repo.latest(loc.name) for loc in locations}

    return build_map_response(
        snapshot,
        locations,
        assessments=assessments,
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
