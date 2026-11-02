# src/weatherbot/web/routes/ai.py
"""The AI behind the loopback API: five reads, three guarded streams, and two controls.

The reads are plain functions, so FastAPI runs them in its thread pool: ``GET /api/ai``
(the state, the models, the features, and today's meter), ``GET /api/ai/calls`` (the
ledger: kinds, statuses, tokens, costs, and reasons, never text), and ``GET
/api/ai/briefings``, ``/api/ai/summaries``, and ``/api/ai/narrations`` (the stored
products, each source resolved from its stored record and linked only to a public NOAA
page that names no point, ``display.public_page``).

The streams ``POST /api/ai/briefings``, ``POST /api/ai/chat``, and ``POST
/api/ai/narrations`` spend the operator's money, so each is a write behind the same-origin
JSON guard, answered as typed server-sent events. Before one begins, its dependency reads
the AI's state in a worker thread and takes one of the four stream slots: a state other
than ``ready`` answers 503 with its reason (``capped`` answers 429), and a fifth stream
429 ``busy``, each with fixed text, never an SDK message. A stream reaches the database
only through the AI services, which read and write in worker threads (Phase 5's check
17); a reservation refused mid-stream ends it with an ``unavailable`` event. When the
page goes away, the generator's ``finally`` closes the service's iterator, so the caller
settles the ledger, and frees the slot.

``PUT /api/ai/pause`` and ``POST /api/ai/allowance`` write the ledger's control rows (an
allowance of at most one day's cap, three a day) and answer the status. With no AI service
(the OpenAPI export, the demonstration server), the reads answer AI off and nothing
stored, and the streams and the controls answer 503 ``disabled``.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterable, Mapping, Sequence
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import TYPE_CHECKING, Annotated, Any, Final, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.sse import EventSourceResponse

from weatherbot.models import OutlookGraphic
from weatherbot.services.ai import briefing, chat, narration
from weatherbot.services.ai.briefing import BriefingService, stored_briefing
from weatherbot.services.ai.context import SourceRef, stored_sources
from weatherbot.services.ai.display import public_page
from weatherbot.services.ai.errors import MESSAGES, AiUnavailableReason
from weatherbot.services.ai.ledger import (
    MAX_ALLOWANCES_PER_DAY,
    AllowanceRefusedError,
    AllowancesExhaustedError,
    CallKind,
    KindTotals,
    LedgerDay,
    LedgerEntry,
    micro_usd,
)
from weatherbot.services.ai.narration import NARRATION_LABEL, NarrationService, stored_narration
from weatherbot.services.ai.outputs import StoredOutput
from weatherbot.services.ai.pricing import model_name
from weatherbot.services.ai.summaries import ChangeSummaryService, stored_summary
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.persistence.repositories import LocationRepository, SnapshotRepository
from weatherbot.web.map_layers import get_cached_snapshot_bundle
from weatherbot.web.schemas import (
    AiAreaResponse,
    AiCallResponse,
    AiCallsResponse,
    AiFeaturesResponse,
    AiKindTotalsResponse,
    AiModelsResponse,
    AiRefusalResponse,
    AiSourceResponse,
    AiStatusResponse,
    AiTimelineItemResponse,
    AiTodayResponse,
    AllowanceRequest,
    BriefingRequest,
    BriefingsResponse,
    BriefingStreamEvent,
    ChatRequest,
    ChatStreamEvent,
    LocationBriefingResponse,
    NarrationRequest,
    NarrationsResponse,
    NarrationStreamEvent,
    PauseRequest,
    StoredBriefingResponse,
    StoredNarrationResponse,
    StoredSummaryResponse,
    SummariesResponse,
)

if TYPE_CHECKING:
    from weatherbot.services.ai.service import AiService
    from weatherbot.services.config import AiSettings
    from weatherbot.web.app import WebState

router = APIRouter()

DEFAULT_CALLS_LIMIT: Final = 20
MAX_CALLS_LIMIT: Final = 100
DEFAULT_SUMMARIES_LIMIT: Final = 50
MAX_SUMMARIES_LIMIT: Final = 200
UNKNOWN_LOCATION: Final = "unknown location query parameter: location"
ALLOWANCE_BOUNDS: Final = "an allowance is more than zero and at most one day's cap"
CONTROL_REFUSALS: Final[dict[int | str, dict[str, Any]]] = {
    503: {"model": AiRefusalResponse, "description": "AI is off: there is no AI service."},
}
_REFUSAL_JSON: Final = {
    "application/json": {"schema": {"$ref": "#/components/schemas/AiRefusalResponse"}}
}
STREAM_REFUSALS: Final[dict[int | str, dict[str, Any]]] = {
    429: {"description": "AI is capped, or four AI streams run.", "content": _REFUSAL_JSON},
    503: {"description": "AI is off, paused, or unavailable.", "content": _REFUSAL_JSON},
}
"""A stream's refusal is JSON, not an event: FastAPI would file a ``model`` under the
stream's own media type, so the content names the controls' ``AiRefusalResponse``."""
UNAVAILABLE_TEXT: Final[Mapping[str, str]] = {
    **cast("Mapping[str, str]", MESSAGES),
    **chat.UNAVAILABLE_TEXT,
    **narration.UNAVAILABLE_TEXT,
}
"""Every unavailable reason a stream can end with, as a person reads it."""


def _web(request: Request) -> "WebState":
    return cast("WebState", request.app.state.web)


def _refusal(status: HTTPStatus, reason: AiUnavailableReason) -> HTTPException:
    return HTTPException(status_code=status, detail={"reason": reason, "message": MESSAGES[reason]})


def _require_ai(state: "WebState") -> "AiService":
    if state.ai is None:
        raise _refusal(HTTPStatus.SERVICE_UNAVAILABLE, "disabled")
    return state.ai


def _unavailable_text(reason: str) -> str:
    return UNAVAILABLE_TEXT.get(reason, reason)


# Reads ------------------------------------------------------------------------------------


def _models(settings: "AiSettings") -> AiModelsResponse:
    return AiModelsResponse(
        model=settings.model,
        model_name=model_name(settings.model),
        summary_model=settings.summary_model,
        summary_model_name=model_name(settings.summary_model),
    )


def _features(settings: "AiSettings") -> AiFeaturesResponse:
    return AiFeaturesResponse(
        enabled=settings.enabled,
        change_summaries=settings.change_summaries,
        outlook_narration=settings.outlook_narration,
    )


def _kind_totals(totals: KindTotals) -> AiKindTotalsResponse:
    usage = totals.usage
    return AiKindTotalsResponse(
        kind=cast("CallKind", totals.kind),
        requests=totals.requests,
        input_tokens=usage.input_tokens,
        cache_write_tokens=usage.cache_write_5m_tokens + usage.cache_write_1h_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        output_tokens=usage.output_tokens,
        cost_micro_usd=totals.cost_micro_usd,
    )


def _today(day: LedgerDay, kinds: Sequence[KindTotals]) -> AiTodayResponse:
    by_kind = tuple(_kind_totals(totals) for totals in kinds)
    return AiTodayResponse(
        day=day.day,
        spent_micro_usd=day.spent_micro_usd,
        reserved_micro_usd=day.reserved_micro_usd,
        cap_micro_usd=day.cap_micro_usd,
        allowance_micro_usd=day.allowance_micro_usd,
        allowances_left=max(MAX_ALLOWANCES_PER_DAY - day.allowances, 0),
        calls=day.requests,
        input_tokens=sum(item.input_tokens for item in by_kind),
        cache_write_tokens=sum(item.cache_write_tokens for item in by_kind),
        cache_read_tokens=sum(item.cache_read_tokens for item in by_kind),
        output_tokens=sum(item.output_tokens for item in by_kind),
        by_kind=by_kind,
    )


def ai_status(state: "WebState") -> AiStatusResponse:
    """Read the AI's state, settings, and today's meter, without a request.

    Args:
        state: The web state.

    Returns:
        The status; AI off (``disabled``) and nothing spent when there is no AI service.
    """
    ai = state.ai
    if ai is None:
        settings = state.settings.ai
        nothing = LedgerDay(
            day=state.clock().astimezone().date().isoformat(),
            cap_micro_usd=0,
            allowance_micro_usd=0,
            spent_micro_usd=0,
            reserved_micro_usd=0,
            requests=0,
            allowances=0,
            paused=False,
        )
        return AiStatusResponse(
            state="off",
            reason="disabled",
            credential_source=None,
            models=_models(settings),
            features=_features(settings),
            today=_today(nothing, ()),
            paused=False,
            notice=NOTICE,
        )
    current = ai.state()
    return AiStatusResponse(
        state=current.state,
        reason=current.reason,
        credential_source=current.credential,
        models=_models(ai.settings),
        features=_features(ai.settings),
        today=_today(current.today, ai.ledger.by_kind()),
        paused=current.today.paused,
        notice=NOTICE,
    )


@router.get("/api/ai")
def get_ai(request: Request) -> AiStatusResponse:
    """Return the AI's state, models, features, and today's spend against the cap."""
    return ai_status(_web(request))


def _call(entry: LedgerEntry) -> AiCallResponse:
    usage = entry.usage
    return AiCallResponse(
        id=entry.id,
        kind=entry.kind,
        model=entry.model,
        location=entry.location_name,
        status=entry.status,
        started_at=entry.started_at,
        finished_at=entry.finished_at,
        input_tokens=usage.input_tokens,
        cache_write_tokens=usage.cache_write_5m_tokens + usage.cache_write_1h_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        output_tokens=usage.output_tokens,
        cost_micro_usd=entry.cost_micro_usd,
        allowance_micro_usd=entry.allowance_micro_usd,
        stop_reason=entry.stop_reason,
        refusal_category=entry.refusal_category,
        error_kind=entry.error_kind,
    )


@router.get("/api/ai/calls")
def get_ai_calls(
    request: Request,
    limit: Annotated[
        int, Query(ge=1, le=MAX_CALLS_LIMIT, description="Maximum ledger rows, newest first.")
    ] = DEFAULT_CALLS_LIMIT,
) -> AiCallsResponse:
    """Return the ledger's newest rows: kinds, statuses, tokens, costs, and reasons only."""
    ai = _web(request).ai
    entries = ai.ledger.recent(limit) if ai is not None else ()
    return AiCallsResponse(
        limit=limit, calls=tuple(_call(entry) for entry in entries), notice=NOTICE
    )


def _source(ref: SourceRef, why: str | None = None) -> AiSourceResponse:
    return AiSourceResponse(
        key=ref.key,
        source_id=ref.source_id,
        title=ref.title,
        code=ref.code,
        issuer=ref.issuer,
        advisory=ref.advisory,
        issued_at=ref.issued,
        why=why,
        url=public_page(ref.source_id),
    )


def _cited(
    keys: Sequence[tuple[str, str | None]], refs: Sequence[SourceRef]
) -> tuple[AiSourceResponse, ...]:
    """Resolve cited keys to their stored records; a key with no record is left out."""
    by_key = {ref.key: ref for ref in refs}
    return tuple(_source(by_key[key], why) for key, why in keys if key in by_key)


def _status(stored: StoredOutput) -> Literal["ok", "withheld"]:
    return "ok" if stored.status == "ok" else "withheld"


def _briefing(stored: StoredOutput, *, stale: bool) -> StoredBriefingResponse:
    written, refs = stored_briefing(stored) if stored.status == "ok" else (None, ())
    return StoredBriefingResponse(
        id=stored.id,
        status=_status(stored),
        withheld_reason=stored.withheld_reason,
        model=stored.model,
        model_name=model_name(stored.model),
        prompt_version=stored.prompt_version,
        assessment_id=stored.assessment_id,
        created_at=stored.created_at,
        stale=stale,
        situation=written.situation if written is not None else None,
        what_it_means_here=written.what_it_means_here if written is not None else None,
        timeline=tuple(
            AiTimelineItemResponse(when=item.when, what=item.what, sources=tuple(item.sources))
            for item in (written.timeline if written is not None else ())
        ),
        actions=tuple(written.actions) if written is not None else (),
        sources=(
            _cited([(note.key, note.why) for note in written.sources], refs)
            if written is not None
            else ()
        ),
    )


def _location(state: "WebState", location: str | None) -> tuple[str, ...]:
    """The watched locations' names, or the one asked for; 404 for an unknown name."""
    names = tuple(item.name for item in LocationRepository(state.database.engine).list())
    if location is None:
        return names
    if location not in names:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=UNKNOWN_LOCATION)
    return (location,)


@router.get("/api/ai/briefings")
def get_briefings(
    request: Request,
    location: Annotated[
        str | None, Query(description="Optional stored location name to filter by.")
    ] = None,
) -> BriefingsResponse:
    """Return each watched location's newest stored briefing, and whether it is stale."""
    state = _web(request)
    names = _location(state, location)
    briefings = BriefingService(state.ai) if state.ai is not None else None
    items: list[LocationBriefingResponse] = []
    for name in names:
        if briefings is None:
            items.append(LocationBriefingResponse(location=name, assessment_id=None, briefing=None))
            continue
        latest = briefings.latest(name)
        stored = latest.stored
        items.append(
            LocationBriefingResponse(
                location=name,
                assessment_id=latest.assessment_id,
                briefing=_briefing(stored, stale=latest.stale) if stored is not None else None,
            )
        )
    return BriefingsResponse(location=location, locations=tuple(items), notice=NOTICE)


def _summary(stored: StoredOutput) -> StoredSummaryResponse:
    written = stored_summary(stored)
    sources: tuple[AiSourceResponse, ...] = ()
    if written is not None and stored.content is not None:
        refs = stored_sources(stored.content["sources"])
        sources = _cited([(key, None) for key in written.sources], refs)
    return StoredSummaryResponse(
        id=stored.id,
        location=stored.location_name,
        assessment_id=stored.assessment_id,
        status=_status(stored),
        withheld_reason=stored.withheld_reason,
        model=stored.model,
        model_name=model_name(stored.model),
        prompt_version=stored.prompt_version,
        created_at=stored.created_at,
        summary=written.summary if written is not None else None,
        sources=sources,
    )


@router.get("/api/ai/summaries")
def get_summaries(
    request: Request,
    location: Annotated[
        str | None, Query(description="Optional stored location name to filter by.")
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=MAX_SUMMARIES_LIMIT, description="Maximum summaries, newest first."),
    ] = DEFAULT_SUMMARIES_LIMIT,
) -> SummariesResponse:
    """Return the stored change summaries, newest first, withheld ones with their reason."""
    state = _web(request)
    if location is not None:
        _location(state, location)
    stored = ChangeSummaryService(state.ai).latest(location, limit) if state.ai is not None else ()
    return SummariesResponse(
        location=location,
        limit=limit,
        summaries=tuple(_summary(item) for item in stored),
        notice=NOTICE,
    )


def _narration(stored: StoredOutput, graphic: OutlookGraphic) -> StoredNarrationResponse:
    written, two = stored_narration(stored) if stored.status == "ok" else (None, None)
    return StoredNarrationResponse(
        id=stored.id,
        basin=graphic.basin,
        horizon=graphic.horizon,
        graphic_sha256=graphic.provenance.sha256,
        status=_status(stored),
        withheld_reason=stored.withheld_reason,
        model=stored.model,
        model_name=model_name(stored.model),
        prompt_version=stored.prompt_version,
        created_at=stored.created_at,
        summary=written.summary if written is not None else None,
        areas=tuple(
            AiAreaResponse(description=area.description, chance_text=area.chance_text)
            for area in (written.areas if written is not None else ())
        ),
        caveat=written.caveat if written is not None else None,
        two=_source(two) if two is not None else None,
    )


@router.get("/api/ai/narrations")
def get_narrations(request: Request) -> NarrationsResponse:
    """Return the newest stored narration of each of the latest snapshot's outlook graphics."""
    state = _web(request)
    ai = state.ai
    settings = ai.settings if ai is not None else state.settings.ai
    items: list[StoredNarrationResponse] = []
    if ai is not None:
        bundle = get_cached_snapshot_bundle(SnapshotRepository(state.database.engine))
        narrations = NarrationService(ai)
        for graphic in bundle.snapshot.outlook_graphics if bundle is not None else ():
            stored = narrations.latest(graphic.provenance.sha256)
            if stored is not None:
                items.append(_narration(stored, graphic))
    return NarrationsResponse(
        enabled=settings.outlook_narration,
        label=NARRATION_LABEL,
        narrations=tuple(items),
        notice=NOTICE,
    )


# Streams ----------------------------------------------------------------------------------


@dataclass
class OpenStream[T]:
    """A stream about to begin: its validated body, the AI service, and the slot it holds."""

    state: "WebState"
    ai: "AiService"
    body: T
    _released: bool = field(default=False, repr=False)

    def release(self) -> None:
        """Free the stream's slot, once."""
        if not self._released:
            self._released = True
            self.state.ai_streams.release()


async def _open_stream[T](request: Request, body: T) -> OpenStream[T]:
    """Refuse a stream AI cannot run now, then take one of the four slots.

    Raises:
        HTTPException: 503 with the state's reason (429 when capped), or 429 ``busy`` when
            four AI streams run already.
    """
    state = _web(request)
    ai = _require_ai(state)
    current = await asyncio.to_thread(ai.state)
    if current.state != "ready":
        status = (
            HTTPStatus.TOO_MANY_REQUESTS
            if current.state == "capped"
            else HTTPStatus.SERVICE_UNAVAILABLE
        )
        raise _refusal(status, current.reason or "disabled")
    if state.ai_streams.locked():
        raise _refusal(HTTPStatus.TOO_MANY_REQUESTS, "busy")
    await state.ai_streams.acquire()  # never waits: nothing ran since locked() said a slot is free
    return OpenStream(state, ai, body)


async def open_briefing(request: Request, body: BriefingRequest) -> OpenStream[BriefingRequest]:
    """Open a briefing stream once its body is valid."""
    return await _open_stream(request, body)


async def open_chat(request: Request, body: ChatRequest) -> OpenStream[ChatRequest]:
    """Open a chat stream once its body is valid."""
    return await _open_stream(request, body)


async def open_narration(request: Request, body: NarrationRequest) -> OpenStream[NarrationRequest]:
    """Open a narration stream once its body is valid."""
    return await _open_stream(request, body)


def briefing_event(event: briefing.BriefingEvent) -> BriefingStreamEvent:
    """Convert a briefing's event into its stream model."""
    if isinstance(event, briefing.Started):
        return BriefingStreamEvent(
            kind="started",
            model=event.model,
            model_name=model_name(event.model),
            assessment_id=event.assessment_id,
            as_of=event.as_of,
            prompt_version=event.prompt_version,
        )
    if isinstance(event, briefing.Section):
        return BriefingStreamEvent(kind="section", section=event.name, text=event.text)
    if isinstance(event, briefing.Done):
        return BriefingStreamEvent(
            kind="done", output_id=event.output_id, created_at=event.created_at, reused=event.reused
        )
    if isinstance(event, briefing.Withheld):
        return BriefingStreamEvent(
            kind="withheld", reason=event.reason, detail=event.detail, output_id=event.output_id
        )
    return BriefingStreamEvent(
        kind="unavailable", reason=event.reason, detail=_unavailable_text(event.reason)
    )


def chat_event(event: chat.ChatEvent) -> ChatStreamEvent:
    """Convert a chat turn's event into its stream model."""
    if isinstance(event, chat.Started):
        return ChatStreamEvent(
            kind="started",
            conversation_id=event.conversation_id,
            model=event.model,
            model_name=model_name(event.model),
        )
    if isinstance(event, chat.Tool):
        return ChatStreamEvent(kind="tool", tool=event.name)
    if isinstance(event, chat.Text):
        return ChatStreamEvent(kind="text", text=event.sentence)
    if isinstance(event, chat.Done):
        return ChatStreamEvent(kind="done", call_ids=event.call_ids)
    if isinstance(event, chat.Withheld):
        return ChatStreamEvent(
            kind="withheld", reason=event.reason, detail=event.detail, call_ids=event.call_ids
        )
    return ChatStreamEvent(
        kind="unavailable",
        reason=event.reason,
        detail=_unavailable_text(event.reason),
        call_ids=event.call_ids,
    )


def narration_event(event: narration.NarrationEvent) -> NarrationStreamEvent:
    """Convert a narration's event into its stream model."""
    if isinstance(event, narration.Started):
        return NarrationStreamEvent(
            kind="started",
            model=event.model,
            model_name=model_name(event.model),
            basin=event.basin,
            horizon=event.horizon,
            graphic_sha256=event.graphic_sha256,
            two_issued_at=event.two_issued_at,
            prompt_version=event.prompt_version,
        )
    if isinstance(event, narration.Done):
        written = event.narration
        return NarrationStreamEvent(
            kind="done",
            output_id=event.output_id,
            created_at=event.created_at,
            reused=event.reused,
            summary=written.summary,
            areas=tuple(
                AiAreaResponse(description=area.description, chance_text=area.chance_text)
                for area in written.areas
            ),
            caveat=written.caveat,
        )
    if isinstance(event, narration.Withheld):
        return NarrationStreamEvent(
            kind="withheld", reason=event.reason, detail=event.detail, output_id=event.output_id
        )
    return NarrationStreamEvent(
        kind="unavailable", reason=event.reason, detail=_unavailable_text(event.reason)
    )


@router.post("/api/ai/briefings", response_class=EventSourceResponse, responses=STREAM_REFUSALS)
async def stream_briefing(
    stream: Annotated[OpenStream[BriefingRequest], Depends(open_briefing)],
) -> AsyncIterable[BriefingStreamEvent]:
    """Brief a location: replay its stored briefing, or stream a new one section by section."""
    events = BriefingService(stream.ai).stream(stream.body.location, new=stream.body.new)
    try:
        async with contextlib.aclosing(events):
            async for event in events:
                yield briefing_event(event)
    finally:
        stream.release()


@router.post("/api/ai/chat", response_class=EventSourceResponse, responses=STREAM_REFUSALS)
async def stream_chat(
    stream: Annotated[OpenStream[ChatRequest], Depends(open_chat)],
) -> AsyncIterable[ChatStreamEvent]:
    """Answer one question from the stored data, sentence by sentence."""
    body = stream.body
    events = stream.state.chat_service(stream.ai).turn(
        body.conversation_id, body.question, body.location
    )
    try:
        async with contextlib.aclosing(events):
            async for event in events:
                yield chat_event(event)
    finally:
        stream.release()


@router.post("/api/ai/narrations", response_class=EventSourceResponse, responses=STREAM_REFUSALS)
async def stream_narration(
    stream: Annotated[OpenStream[NarrationRequest], Depends(open_narration)],
) -> AsyncIterable[NarrationStreamEvent]:
    """Narrate one official outlook graphic: reuse the stored narration, or write one."""
    events = NarrationService(stream.ai).stream(stream.body.basin, stream.body.horizon)
    try:
        async with contextlib.aclosing(events):
            async for event in events:
                yield narration_event(event)
    finally:
        stream.release()


# Controls ---------------------------------------------------------------------------------


@router.put("/api/ai/pause", responses=CONTROL_REFUSALS)
def put_pause(request: Request, body: PauseRequest) -> AiStatusResponse:
    """Pause every AI request, or lift the pause; a control row records each change."""
    state = _web(request)
    ai = _require_ai(state)
    if ai.ledger.today().paused != body.paused:
        if body.paused:
            ai.ledger.pause()
        else:
            ai.ledger.resume()
    return ai_status(state)


@router.post(
    "/api/ai/allowance",
    responses={**CONTROL_REFUSALS, 409: {"description": "Today's three allowances are used."}},
)
def post_allowance(request: Request, body: AllowanceRequest) -> AiStatusResponse:
    """Raise today's limit by at most one day's cap; a fourth allowance in a day answers 409."""
    state = _web(request)
    ai = _require_ai(state)
    amount = micro_usd(body.usd)
    if not 0 < amount <= ai.ledger.cap_micro_usd:
        raise HTTPException(status_code=HTTPStatus.UNPROCESSABLE_CONTENT, detail=ALLOWANCE_BOUNDS)
    try:
        ai.ledger.allow(amount)
    except AllowancesExhaustedError as error:
        raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=str(error)) from error
    except AllowanceRefusedError as error:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    return ai_status(state)
