# src/weatherbot/cli/brief.py
"""``weatherbot brief``: Claude's plain-language briefing on each location's latest assessment.

``brief`` briefs the location named, or every stored location in turn, from its latest
stored assessment (``status`` or ``check`` assesses). It prints a label line first, naming
the model, the assessment, and that the text is not an official product; then each
section as it streams and passes the validators (Rich in a terminal, plain text
otherwise); and the disclaimer's notice last. A terminal cannot unprint, so a briefing
withheld after some of its sections printed ends with "disregard the sections above". A
stored briefing for the latest assessment is reused without a request unless ``--new``
asks for a new one. ``--json`` prints one ``brief`` document; ``--cost`` prints today's
ledger (spent, cap, allowance, requests, and tokens by kind) and sends nothing. It exits
0 when every briefing was written or reused, 1 when one was withheld or AI was
unavailable (with the reason), and 2 for a usage error.

``--outlook {atl,pac,cpac}`` (with ``--horizon {2d0,7d0}``, seven days by default) prints
an AI interpretation of NHC's official outlook graphic for the basin instead, once it
passes its checks, when ``[ai] outlook_narration`` is on; a stored narration of the same
graphic and TWO is reused without a request unless ``--new`` asks for a new one.

No prompt, context, or answer is logged; the answer goes to the operator's own terminal.
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Final, Literal, cast

import typer

from weatherbot.cli.documents import (
    BriefData,
    BriefDocument,
    BriefEntry,
    BriefingEntry,
    BriefKindEntry,
    BriefLedgerEntry,
    BriefNarrationEntry,
    BriefSourceEntry,
    BriefSourceNoteEntry,
    BriefTimelineEntry,
    NarrationAreaEntry,
    NarrationTextEntry,
)
from weatherbot.cli.runtime import (
    EXIT_FAILED,
    EXIT_OK,
    EXIT_USAGE,
    Output,
    context_of,
    fail,
    open_session,
)
from weatherbot.cli.snapshots import ADD_HINT, JsonOption
from weatherbot.services.ai.errors import MESSAGES
from weatherbot.services.ai.pricing import model_name, usd_text
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.locations import LocationService

if TYPE_CHECKING:
    from weatherbot.services.ai.briefing import BriefingEvent, BriefingService, Done
    from weatherbot.services.ai.ledger import KindTotals, LedgerDay
    from weatherbot.services.ai.narration import Started as NarrationStarted
    from weatherbot.services.ai.schemas import Briefing, OutlookNarration
    from weatherbot.services.ai.service import AiService

type EntryStatus = Literal["ok", "withheld", "unavailable"]
type Basin = Literal["atl", "pac", "cpac"]
type Horizon = Literal["2d0", "7d0"]

HEADINGS: Final[dict[str, str]] = {
    "situation": "Situation",
    "what_it_means_here": "What it means here",
    "timeline": "Timeline",
    "actions": "Actions",
    "sources": "Sources",
}
NO_ASSESSMENT: Final = "no assessment is stored for it yet; run weatherbot status first"
DISREGARD: Final = " — disregard the sections above"


@dataclass
class _Run:
    """One location's briefing as it streamed: what its document entry needs."""

    location: str
    model: str
    prompt_version: str | None = None
    assessment_id: int | None = None
    as_of: datetime | None = None
    entry: BriefEntry | None = None
    printed: list[str] = field(default_factory=list[str])


class _Silent(Output):
    """An output that prints nothing: under ``--json`` standard output holds the document."""

    def line(self, text: str = "", *, style: str | None = None) -> None:
        """Print nothing."""
        del text, style


def _briefing_entry(briefing: "Briefing") -> BriefingEntry:
    return BriefingEntry(
        situation=briefing.situation,
        what_it_means_here=briefing.what_it_means_here,
        timeline=tuple(
            BriefTimelineEntry(when=item.when, what=item.what, sources=tuple(item.sources))
            for item in briefing.timeline
        ),
        actions=tuple(briefing.actions),
        sources=tuple(
            BriefSourceNoteEntry(key=note.key, why=note.why) for note in briefing.sources
        ),
    )


def unavailable_text(reason: str) -> str:
    """Say why AI could not brief a location.

    Args:
        reason: An unavailable reason.

    Returns:
        Fixed text for the reason.
    """
    if reason == "no_assessment":
        return NO_ASSESSMENT
    return cast("dict[str, str]", MESSAGES).get(reason, reason)


class _Printer:
    """Prints a briefing's events as they arrive, and builds its document entry."""

    def __init__(self, output: Output, service: "AiService", briefings: "BriefingService") -> None:
        self._output = output
        self._service = service
        self._briefings = briefings

    def _cost(self, output_id: int | None) -> int | None:
        stored = self._briefings.output(output_id) if output_id is not None else None
        if stored is None or stored.call_id is None:
            return None
        entry = self._service.ledger.entry(stored.call_id)
        return entry.cost_micro_usd if entry is not None else None

    def _sources(self, output_id: int) -> tuple[BriefSourceEntry, ...]:
        from weatherbot.services.ai.briefing import stored_briefing  # noqa: PLC0415 - AI loads on demand

        stored = self._briefings.output(output_id)
        if stored is None:  # pragma: no cover - a Done names a stored briefing
            return ()
        _, refs = stored_briefing(stored)
        return tuple(
            BriefSourceEntry(
                key=ref.key,
                source_id=ref.source_id,
                code=ref.code,
                issuer=ref.issuer,
                advisory=ref.advisory,
                issued=ref.issued,
                title=ref.title,
            )
            for ref in refs
        )

    def _done(self, run: _Run, event: "Done") -> BriefEntry:
        return _entry(
            run,
            "ok",
            briefing=_briefing_entry(event.briefing),
            sources=self._sources(event.output_id),
            reused=event.reused,
            created_at=event.created_at,
            cost=None if event.reused else self._cost(event.output_id),
        )

    def handle(self, run: _Run, event: "BriefingEvent") -> None:
        """Print one event, and keep what the run's entry needs.

        Args:
            run: The location's run.
            event: The event.
        """
        from weatherbot.services.ai.briefing import (  # noqa: PLC0415 - AI loads on demand
            Done,
            Section,
            Started,
            Withheld,
        )

        output = self._output
        if isinstance(event, Started):
            run.model, run.prompt_version = event.model, event.prompt_version
            run.assessment_id, run.as_of = event.assessment_id, event.as_of
            output.line(
                f"AI briefing · {model_name(event.model)} · for the assessment of "
                f"{event.as_of:%Y-%m-%d %H:%M} UTC · not an official product",
                style="bold",
            )
        elif isinstance(event, Section):
            run.printed.append(event.name)
            output.line()
            output.line(HEADINGS[event.name], style="bold")
            for line in event.text.splitlines():
                output.line(f"  {line}")
        elif isinstance(event, Done):
            if event.reused:
                output.line()
                output.line(
                    f"(A stored briefing, written {event.created_at:%Y-%m-%d %H:%M} UTC; no "
                    "request was sent. --new asks for a new one.)",
                    style="dim",
                )
            run.entry = self._done(run, event)
        elif isinstance(event, Withheld):
            output.line()
            tail = DISREGARD if run.printed else ""
            output.line(f"Withheld: {event.reason} ({event.detail}){tail}", style="yellow")
            cost = self._cost(event.output_id)
            run.entry = _entry(run, "withheld", withheld=event.reason, cost=cost)
        else:
            output.line(f"AI unavailable: {unavailable_text(event.reason)}", style="yellow")
            run.entry = _entry(run, "unavailable", unavailable=event.reason)


def _entry(  # noqa: PLR0913 - one document entry's fields
    run: _Run,
    status: EntryStatus,
    *,
    briefing: BriefingEntry | None = None,
    sources: tuple[BriefSourceEntry, ...] = (),
    withheld: str | None = None,
    unavailable: str | None = None,
    reused: bool = False,
    created_at: datetime | None = None,
    cost: int | None = None,
) -> BriefEntry:
    return BriefEntry(
        location=run.location,
        model=run.model,
        prompt_version=run.prompt_version,
        assessment_id=run.assessment_id,
        as_of=run.as_of,
        status=status,
        briefing=briefing,
        sources=sources,
        withheld_reason=withheld,
        unavailable_reason=unavailable,
        reused=reused,
        created_at=created_at,
        cost_micro_usd=cost,
    )


def _ledger_entry(today: "LedgerDay", kinds: Sequence["KindTotals"]) -> BriefLedgerEntry:
    return BriefLedgerEntry(
        day=today.day,
        cap_micro_usd=today.cap_micro_usd,
        allowance_micro_usd=today.allowance_micro_usd,
        spent_micro_usd=today.spent_micro_usd,
        reserved_micro_usd=today.reserved_micro_usd,
        requests=today.requests,
        paused=today.paused,
        by_kind=tuple(
            BriefKindEntry(
                kind=kind.kind,
                requests=kind.requests,
                input_tokens=kind.usage.input_tokens,
                cache_write_5m_tokens=kind.usage.cache_write_5m_tokens,
                cache_write_1h_tokens=kind.usage.cache_write_1h_tokens,
                cache_read_tokens=kind.usage.cache_read_tokens,
                output_tokens=kind.usage.output_tokens,
                cost_micro_usd=kind.cost_micro_usd,
            )
            for kind in kinds
        ),
    )


def _print_ledger(output: Output, ledger: BriefLedgerEntry) -> None:
    limit = ledger.cap_micro_usd + ledger.allowance_micro_usd
    paused = "; paused" if ledger.paused else ""
    output.line(
        f"AI spend today ({ledger.day}): {usd_text(ledger.spent_micro_usd)} of "
        f"{usd_text(limit)} (cap {usd_text(ledger.cap_micro_usd)}, allowance "
        f"{usd_text(ledger.allowance_micro_usd)}); {usd_text(ledger.reserved_micro_usd)} "
        f"reserved; {ledger.requests} requests{paused}"
    )
    rows = [
        [
            kind.kind,
            str(kind.requests),
            str(kind.input_tokens),
            str(kind.cache_write_5m_tokens + kind.cache_write_1h_tokens),
            str(kind.cache_read_tokens),
            str(kind.output_tokens),
            usd_text(kind.cost_micro_usd),
        ]
        for kind in ledger.by_kind
    ]
    columns = ("Kind", "Requests", "Input", "Cache write", "Cache read", "Output", "Cost")
    output.table("Requests and tokens by kind", columns, rows)


def _choose(output: Output, names: Sequence[str], location: str | None) -> list[str]:
    if not names:
        fail(output, f"no location is stored; {ADD_HINT}", EXIT_USAGE)
    if location is None:
        return list(names)
    if location not in names:
        fail(output, f"no location is named {location!r}", EXIT_USAGE)
    return [location]


async def _run(
    output: Output, service: "AiService", names: Sequence[str], *, new: bool
) -> tuple[list[_Run], BriefLedgerEntry]:
    from weatherbot.services.ai.briefing import BriefingService  # noqa: PLC0415 - AI loads on demand

    try:
        briefings = BriefingService(service)
        printer = _Printer(output, service, briefings)
        runs: list[_Run] = []
        for name in names:
            run = _Run(location=name, model=service.settings.model)
            output.line()
            output.line(name, style="bold")
            async for event in briefings.stream(name, new=new):
                printer.handle(run, event)
            runs.append(run)
        ledger = _ledger_entry(service.ledger.today(), service.ledger.by_kind())
    finally:
        await service.close()
    return runs, ledger


def _narration_entry(  # noqa: PLR0913 - one document entry's fields
    started: "NarrationStarted | None",
    place: tuple[Basin, Horizon],
    model: str,
    status: EntryStatus,
    *,
    narration: "OutlookNarration | None" = None,
    withheld: str | None = None,
    unavailable: str | None = None,
    reused: bool = False,
    created_at: datetime | None = None,
    cost: int | None = None,
) -> BriefNarrationEntry:
    from weatherbot.services.ai.narration import NARRATION_LABEL  # noqa: PLC0415 - AI loads on demand

    text = None
    if narration is not None:
        text = NarrationTextEntry(
            summary=narration.summary,
            areas=tuple(
                NarrationAreaEntry(description=area.description, chance_text=area.chance_text)
                for area in narration.areas
            ),
            caveat=narration.caveat,
        )
    return BriefNarrationEntry(
        label=NARRATION_LABEL,
        basin=place[0],
        horizon=place[1],
        model=started.model if started is not None else model,
        prompt_version=started.prompt_version if started is not None else None,
        graphic_sha256=started.graphic_sha256 if started is not None else None,
        two_issued_at=started.two_issued_at if started is not None else None,
        status=status,
        narration=text,
        withheld_reason=withheld,
        unavailable_reason=unavailable,
        reused=reused,
        created_at=created_at,
        cost_micro_usd=cost,
    )


def _print_narration(output: Output, narration: "OutlookNarration") -> None:
    output.line()
    output.line("Summary", style="bold")
    output.line(f"  {narration.summary}")
    output.line()
    output.line("Areas", style="bold")
    if not narration.areas:
        output.line("  none")
    for area in narration.areas:
        output.line(f"  {area.description} Chance: {area.chance_text}.")
    output.line()
    output.line("Caveat", style="bold")
    output.line(f"  {narration.caveat}")


async def _narrate(
    output: Output, service: "AiService", place: tuple[Basin, Horizon], *, new: bool
) -> tuple[BriefNarrationEntry, BriefLedgerEntry]:
    """Narrate one outlook graphic, printing it once it passes, and read today's ledger."""
    from weatherbot.services.ai.narration import (  # noqa: PLC0415 - AI loads on demand
        HORIZON_NAMES,
        NARRATION_LABEL,
        UNAVAILABLE_TEXT,
        Done,
        NarrationService,
        Started,
        Withheld,
    )
    from weatherbot.services.ai.tools import BASIN_NAMES  # noqa: PLC0415 - as above

    model = service.settings.model
    try:
        narrations = NarrationService(service)
        started: NarrationStarted | None = None
        entry = _narration_entry(None, place, model, "unavailable")
        async for event in narrations.stream(place[0], place[1], new=new):
            if isinstance(event, Started):
                started = event
                output.line(
                    f"{NARRATION_LABEL} · {model_name(event.model)} · NHC's "
                    f"{BASIN_NAMES[place[0]]} outlook over {HORIZON_NAMES[place[1]]}, with its "
                    f"TWO of {event.two_issued_at:%Y-%m-%d %H:%M} UTC · not an official product",
                    style="bold",
                )
            elif isinstance(event, Done):
                _print_narration(output, event.narration)
                if event.reused:
                    output.line()
                    output.line(
                        f"(A stored narration, written {event.created_at:%Y-%m-%d %H:%M} UTC; "
                        "no request was sent. --new asks for a new one.)",
                        style="dim",
                    )
                stored = narrations.output(event.output_id)
                cost = None
                if not event.reused and stored is not None and stored.call_id is not None:
                    found = service.ledger.entry(stored.call_id)
                    cost = found.cost_micro_usd if found is not None else None
                entry = _narration_entry(
                    started,
                    place,
                    model,
                    "ok",
                    narration=event.narration,
                    reused=event.reused,
                    created_at=event.created_at,
                    cost=cost,
                )
            elif isinstance(event, Withheld):
                output.line(f"Withheld: {event.reason} ({event.detail})", style="yellow")
                entry = _narration_entry(started, place, model, "withheld", withheld=event.reason)
            else:
                known = {**cast("dict[str, str]", MESSAGES), **UNAVAILABLE_TEXT}
                output.line(
                    f"AI unavailable: {known.get(event.reason, event.reason)}", style="yellow"
                )
                entry = _narration_entry(
                    started, place, model, "unavailable", unavailable=event.reason
                )
        ledger = _ledger_entry(service.ledger.today(), service.ledger.by_kind())
    finally:
        await service.close()
    return entry, ledger


def brief(  # noqa: PLR0913 - the command's options
    ctx: typer.Context,
    location: Annotated[
        str | None, typer.Argument(help="Brief this location only; every one by default.")
    ] = None,
    *,
    new: Annotated[
        bool, typer.Option("--new", help="Ask for a new briefing even when one is stored.")
    ] = False,
    json_output: JsonOption = False,
    cost: Annotated[
        bool, typer.Option("--cost", help="Print today's AI spend and send nothing.")
    ] = False,
    outlook: Annotated[
        Literal["atl", "pac", "cpac"] | None,
        typer.Option(
            "--outlook",
            help="Narrate NHC's outlook graphic for this basin instead ([ai] outlook_narration).",
        ),
    ] = None,
    horizon: Annotated[
        Literal["2d0", "7d0"],
        typer.Option("--horizon", help="The outlook graphic's horizon: two days or seven days."),
    ] = "7d0",
) -> None:
    """Brief each location in plain language from its latest assessment, through Claude."""
    context = context_of(ctx)
    output = Output(context.runtime, json_mode=json_output)
    if outlook is not None and location is not None:
        fail(output, "brief a location or an outlook, not both", EXIT_USAGE)
    narration: BriefNarrationEntry | None = None
    runs: list[_Run] = []
    with open_session(context, output) as database:
        shown = _Silent(context.runtime, json_mode=True) if json_output else output
        if outlook is not None and not cost:
            service = context.ai_service(database)
            narration, ledger = asyncio.run(_narrate(shown, service, (outlook, horizon), new=new))
        else:
            names = [stored.name for stored in LocationService(database.engine).list()]
            chosen = [] if cost else _choose(output, names, location)
            service = context.ai_service(database)
            runs, ledger = asyncio.run(_run(shown, service, chosen, new=new))
    entries = tuple(run.entry for run in runs if run.entry is not None)
    failed = any(entry.status != "ok" for entry in entries)
    code = (
        EXIT_FAILED if failed or (narration is not None and narration.status != "ok") else EXIT_OK
    )
    if json_output:
        data = BriefData(briefings=entries, narration=narration, today=ledger)
        output.document(
            BriefDocument(generated_at=context.runtime.now(), disclaimer=NOTICE, data=data)
        )
        raise typer.Exit(code)
    if cost:
        _print_ledger(output, ledger)
    output.notice()
    raise typer.Exit(code)
