# src/weatherbot/cli/ask.py
"""``weatherbot ask``: one question, answered by Claude from Weatherbot's stored data only.

``ask QUESTION`` runs one chat turn (``services.ai.chat``): Claude reads the stored
locations, assessments, evidence, alerts, storms, outlooks, and ladder through the nine
read-only tools, and every sentence of its answer passes the current-level, URL, and
coordinate checks before it prints. It prints a label line first, naming the model and
saying the text is not an official product; then each tool's name as it is used (to
standard error in plain text, dimmed in a terminal); then the answer, sentence by
sentence; and the disclaimer's notice last. A terminal cannot unprint, so an answer
withheld after some of its sentences printed ends with "disregard the answer above".
``--location`` names the location the question is about; every stored location's level
is given otherwise. ``--json`` prints one ``ask`` document. It exits 0 when the answer
arrived whole, 1 when it was withheld or AI was unavailable (with the reason), and 2 for
a usage error.

The question is never logged; it and the answer go to the operator's own terminal only.
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated, Final, Literal, cast

import typer

from weatherbot.cli.documents import AskData, AskDocument
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
from weatherbot.services.ai.pricing import model_name
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.locations import LocationService

if TYPE_CHECKING:
    from weatherbot.services.ai.chat import ChatEvent
    from weatherbot.services.ai.service import AiService

type AskStatus = Literal["ok", "withheld", "unavailable"]

QUESTION_LIMIT: Final = 2_000
"""The chat's own bound (``services.ai.chat.QUESTION_LIMIT``), checked before AI loads."""
DISREGARD: Final = " — disregard the answer above"


@dataclass
class _Run:
    """The turn as it streamed: what the document needs."""

    model: str
    status: AskStatus = "unavailable"
    sentences: list[str] = field(default_factory=list[str])
    tools: list[str] = field(default_factory=list[str])
    call_ids: tuple[int, ...] = ()
    withheld: str | None = None
    unavailable: str | None = None


def unavailable_text(reason: str) -> str:
    """Say why the chat could not answer.

    Args:
        reason: An unavailable reason.

    Returns:
        Fixed text for the reason.
    """
    from weatherbot.services.ai.chat import UNAVAILABLE_TEXT  # noqa: PLC0415 - AI loads on demand

    known = {**cast("dict[str, str]", MESSAGES), **UNAVAILABLE_TEXT}
    return known.get(reason, reason)


class _Printer:
    """Prints a turn's events as they arrive (nothing under ``--json``) and keeps its run."""

    def __init__(self, output: Output, *, quiet: bool) -> None:
        self._output = output
        self._quiet = quiet

    def _line(self, text: str = "", *, style: str | None = None) -> None:
        if not self._quiet:
            self._output.line(text, style=style)

    def _tool(self, name: str) -> None:
        if self._quiet:
            return
        if self._output.rich:
            self._output.line(f"looked up: {name}", style="dim")
        else:
            self._output.note(f"looked up: {name}")

    def handle(self, run: _Run, event: "ChatEvent") -> None:
        """Print one event, and keep what the document needs.

        Args:
            run: The turn's run.
            event: The event.
        """
        from weatherbot.services.ai.chat import Done, Started, Text, Tool, Withheld  # noqa: PLC0415 - AI loads on demand

        if isinstance(event, Started):
            run.model = event.model
            self._line(
                f"AI answer · {model_name(event.model)} · from Weatherbot's stored data · not an "
                "official product",
                style="bold",
            )
            self._line()
        elif isinstance(event, Tool):
            run.tools.append(event.name)
            self._tool(event.name)
        elif isinstance(event, Text):
            run.sentences.append(event.sentence)
            self._line(event.sentence)
        elif isinstance(event, Done):
            run.status, run.call_ids = "ok", event.call_ids
        elif isinstance(event, Withheld):
            tail = DISREGARD if run.sentences else ""
            self._line(f"Withheld: {event.reason} ({event.detail}){tail}", style="yellow")
            run.status, run.call_ids, run.withheld = "withheld", event.call_ids, event.reason
        else:
            self._line(f"AI unavailable: {unavailable_text(event.reason)}", style="yellow")
            run.status, run.call_ids, run.unavailable = "unavailable", event.call_ids, event.reason


def _costs(service: "AiService", call_ids: Sequence[int]) -> tuple[int, tuple[str, ...]]:
    """The requests' total cost at list price, and their request ids."""
    total = 0
    request_ids: list[str] = []
    for call_id in call_ids:
        entry = service.ledger.entry(call_id)
        if entry is None:  # pragma: no cover - a turn names its own rows
            continue
        total += entry.cost_micro_usd or 0
        if entry.request_id is not None:
            request_ids.append(entry.request_id)
    return total, tuple(request_ids)


async def _ask(
    printer: _Printer, service: "AiService", question: str, location: str | None
) -> tuple[_Run, int, tuple[str, ...]]:
    from weatherbot.services.ai.chat import ChatService  # noqa: PLC0415 - AI loads on demand

    run = _Run(model=service.settings.model)
    try:
        async for event in ChatService(service).turn(None, question, location):
            printer.handle(run, event)
        cost, request_ids = _costs(service, run.call_ids)
    finally:
        await service.close()
    return run, cost, request_ids


def ask(
    ctx: typer.Context,
    question: Annotated[
        str, typer.Argument(help="The question, 1 to 2,000 characters; it is never logged.")
    ],
    *,
    location: Annotated[
        str | None,
        typer.Option(
            "--location", help="The location the question is about; every one by default."
        ),
    ] = None,
    json_output: JsonOption = False,
) -> None:
    """Ask Claude one question about your locations, answered from the stored data only."""
    context = context_of(ctx)
    output = Output(context.runtime, json_mode=json_output)
    if not question.strip() or len(question) > QUESTION_LIMIT:
        fail(output, f"a question is 1 to {QUESTION_LIMIT:,} characters", EXIT_USAGE)
    with open_session(context, output) as database:
        names = [stored.name for stored in LocationService(database.engine).list()]
        if not names:
            fail(output, f"no location is stored; {ADD_HINT}", EXIT_USAGE)
        if location is not None and location not in names:
            fail(output, f"no location is named {location!r}", EXIT_USAGE)
        service = context.ai_service(database)
        printer = _Printer(output, quiet=json_output)
        run, cost, request_ids = asyncio.run(_ask(printer, service, question, location))
    code = EXIT_OK if run.status == "ok" else EXIT_FAILED
    if json_output:
        data = AskData(
            question=question,
            location=location,
            status=run.status,
            answer=" ".join(run.sentences) if run.status == "ok" else None,
            tools_used=tuple(run.tools),
            model=run.model,
            request_ids=request_ids,
            cost_micro_usd=cost,
            withheld_reason=run.withheld,
            unavailable_reason=run.unavailable,
        )
        output.document(
            AskDocument(generated_at=context.runtime.now(), disclaimer=NOTICE, data=data)
        )
        raise typer.Exit(code)
    output.notice()
    raise typer.Exit(code)
