# src/weatherbot/cli/replay.py
"""``weatherbot replay``: a historical storm's ladder timeline at a stored location.

``replay ATCF_ID --location NAME --corpus DIR`` opens the corpus directory through
``ReplayCorpus``, which reads only inside that directory and checks every file against
its manifest before parsing it, and replays the storm's advisories at the stored location
with the configured thresholds. The evacuation-order toggle is a present-day input, so
the replay assesses with it off, and says so when the stored toggle is on. It prints the
transitions, each advisory where the level or the deciding rule changes, with its
issuance, the rule, the covering watches and warnings, and the change kinds; ``--every``
prints every advisory. Storm names are the corpus's own. Nothing is stored: history is
live only.

The committed subset's wind-speed probabilities are windows around the public landmarks;
for another location the command says once that they do not cover it, and names
``convert --full``, which writes the complete products for any location.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Final

import typer

from weatherbot.cli.documents import (
    ReplayData,
    ReplayDocument,
    ReplayLocationEntry,
    ReplayStepEntry,
    ReplayStormEntry,
)
from weatherbot.cli.runtime import EXIT_USAGE, Output, context_of, fail, open_session
from weatherbot.cli.snapshots import JsonOption, utc
from weatherbot.cli.status import change_entries
from weatherbot.models import Location
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.locations import LocationService
from weatherbot.services.replay import (
    ReplayCorpus,
    ReplayError,
    ReplayService,
    ReplayStep,
    ReplayStorm,
    without_evacuation_order,
)

FULL_CONVERSION: Final = "uv run python scripts/fetch_replay_corpus.py convert --full --out DIR"
_MISSING: Final[Mapping[str, str]] = {
    "nws_alerts": "NWS alerts",
    "source": "a source",
    "cone": "a usable cone",
    "forecast_points": "forecast points",
    "wind_probabilities": "wind-speed probabilities",
    "outlook_areas": "the tropical weather outlook",
    "arrival_times": "arrival-time products",
}


def _step(step: ReplayStep) -> ReplayStepEntry:
    assessment = step.assessment
    advisory = next(
        (str(threat.advisory) for threat in assessment.threats if threat.advisory is not None),
        "-",
    )
    return ReplayStepEntry(
        advisory=advisory,
        issued_at=assessment.as_of,
        level=int(assessment.level),
        level_name=assessment.level.label,
        rule=str(assessment.rule),
        complete=assessment.complete,
        official_codes=tuple(sorted({p.code for p in assessment.official if p.covers})),
        changes=change_entries(step.changes),
    )


def transitions(steps: Sequence[ReplayStepEntry]) -> tuple[ReplayStepEntry, ...]:
    """Keep the first advisory and each one where the level or the deciding rule changes.

    Args:
        steps: Every advisory's step, in order.

    Returns:
        The transitions.
    """
    kept: list[ReplayStepEntry] = []
    previous: tuple[int, str] | None = None
    for step in steps:
        key = (step.level, step.rule)
        if key != previous:
            kept.append(step)
        previous = key
    return tuple(kept)


def _notes(location: Location, steps: Sequence[ReplayStep]) -> tuple[str, ...]:
    notes: list[str] = []
    if location.evacuation_order_in_effect:
        notes.append(
            f"The stored evacuation-order toggle of {location.name!r} is on; the replay "
            "assesses with it off, because the toggle is a present-day input."
        )
    readings = [reading for step in steps for reading in step.assessment.wind_probabilities]
    if any(reading.reading == "outside_coverage" for reading in readings):
        notes.append(
            "The corpus's wind-speed probabilities are windows around the public landmarks "
            f"that do not cover {location.name!r}, so the replay reads none there. Convert "
            f"the complete products with: {FULL_CONVERSION}, then pass --corpus DIR."
        )
    kinds = sorted({item.kind for step in steps for item in step.assessment.unavailable})
    if kinds:
        lacked = [_MISSING[kind] for kind in kinds]
        listed = lacked[0] if len(lacked) == 1 else f"{', '.join(lacked[:-1])} and {lacked[-1]}"
        notes.append(
            f"Replayed assessments lack {listed}, so a level they show reads as at least "
            "that level."
        )
    return tuple(notes)


def _open(output: Output, corpus: Path, atcf_id: str) -> tuple[ReplayCorpus, ReplayStorm]:
    if not corpus.is_dir():
        fail(output, f"--corpus must name a directory: {corpus}", EXIT_USAGE)
    try:
        opened = ReplayCorpus.open(corpus)
    except ReplayError as error:
        fail(output, f"{corpus} is not a replay corpus: {error}", EXIT_USAGE)
    try:
        storms = {storm.atcf_id: storm for storm in opened.storms()}
    except ReplayError as error:
        fail(output, f"the corpus refused a file: {error}")
    storm = storms.get(atcf_id)
    if storm is None:
        held = ", ".join(f"{s.atcf_id} ({s.name})" for s in storms.values())
        fail(output, f"the corpus holds no storm {atcf_id!r}; it holds {held}", EXIT_USAGE)
    return opened, storm


def _print(output: Output, data: ReplayData) -> None:
    storm, location = data.storm, data.location
    output.line(
        f"{storm.name} ({storm.atcf_id}) at {location.name}: {storm.advisories} advisories, "
        f"{utc(storm.first_issued_at)} to {utc(storm.last_issued_at)}.",
        style="bold",
    )
    for note in data.notes:
        output.line(note, style="yellow")
    title = (
        "Every advisory"
        if data.every
        else f"Transitions: the {len(data.steps)} advisories where the level or the rule changes"
    )
    output.table(
        title,
        ("Advisory", "Issued", "Level", "Rule", "Watches and warnings", "Changes"),
        [
            (
                step.advisory,
                utc(step.issued_at),
                f"{step.level} {step.level_name}",
                step.rule,
                ", ".join(step.official_codes) or "-",
                ", ".join(change.kind for change in step.changes) or "-",
            )
            for step in data.steps
        ],
    )
    output.line("Nothing was stored: a replay is never part of the history.")


def replay(  # noqa: PLR0913 - the storm, then the command's options, keyword-only
    ctx: typer.Context,
    atcf_id: Annotated[str, typer.Argument(help="The storm's ATCF id, such as AL112017.")],
    *,
    location: Annotated[
        str, typer.Option("--location", help="The stored location to replay the storm at.")
    ],
    corpus: Annotated[
        Path,
        typer.Option(
            "--corpus",
            help="A replay corpus directory: tests/fixtures/replay, or a convert --full output.",
        ),
    ],
    json_output: JsonOption = False,
    every: Annotated[
        bool, typer.Option("--every", help="Print every advisory, not only the transitions.")
    ] = False,
) -> None:
    """Replay a historical storm's advisories at a stored location, and print its ladder."""
    context = context_of(ctx)
    output = Output(context.runtime, json_mode=json_output)
    with open_session(context, output) as database:
        stored = LocationService(database.engine).get(location)
    if stored is None:
        fail(output, f"no location is named {location!r}", EXIT_USAGE)
    opened, storm = _open(output, corpus, atcf_id)
    thresholds = context.settings.engine.thresholds()
    try:
        steps = ReplayService(opened).timeline(
            atcf_id, without_evacuation_order(stored), thresholds
        )
    except ReplayError as error:
        fail(output, f"the corpus refused a file: {error}")
    entries = tuple(_step(step) for step in steps)
    data = ReplayData(
        storm=ReplayStormEntry(
            atcf_id=storm.atcf_id,
            name=storm.name,
            advisories=storm.advisories,
            first_issued_at=storm.first_issued_at,
            last_issued_at=storm.last_issued_at,
        ),
        location=ReplayLocationEntry(
            name=stored.name,
            inside_nws_coverage=stored.nws is not None,
            evacuation_order_stored_on=stored.evacuation_order_in_effect,
        ),
        every=every,
        ruleset=thresholds.fingerprint(),
        steps=entries if every else transitions(entries),
        notes=_notes(stored, steps),
    )
    if json_output:
        output.document(
            ReplayDocument(generated_at=context.runtime.now(), disclaimer=NOTICE, data=data)
        )
        return
    _print(output, data)
    output.notice()
