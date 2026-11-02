# src/weatherbot/services/ai/tools.py
"""The chat's nine tools: read-only, allowlisted, schema-checked, and bounded.

``TOOL_NAMES`` and ``TOOL_DEFINITIONS`` are literal and static, in a fixed order, so their
bytes never change between requests and the cache holds them. Every definition sets
``strict`` and an input schema with ``additionalProperties`` false and every property
``required``; none takes a URL, a path, a query, or SQL. Before a call runs, its name is
checked against the allowlist and its arguments are validated again here: an unknown
tool, a bad argument, or an unknown location or storm returns an error result that lists
the allowed values (the tool names, the stored locations' names, the latest snapshot's
storms, or the basins) and reads nothing else.

Each tool reads the stored data through the AI engine (``guard.ai_engine``), whose
authorizer refuses every write, and returns the shapes a briefing's context uses
(``context.py``): no coordinate of a location, no geometry, no URL, no path, and no
engine-written sentence; distances as bands, bearings as 8 compass points, instants and
lead times to the hour; NOAA text in escaped ``<noaa_product>`` blocks with its links
removed; sources as keys that belong to one result. A result is its JSON document, then
its blocks, and never more than ``RESULT_LIMIT`` characters: a result past it is cut and
marked. The calls of one round run in order in one worker thread and share each snapshot
they load.

This module loads no SDK and never fetches.
"""

import copy
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import Engine

from weatherbot.models import AlertLevel, DomainModel, Snapshot, StormProducts, Thresholds
from weatherbot.services.ai.context import (
    CUT_MARK,
    BriefingContext,
    ChangeRef,
    ContextTooLarge,
    Hour,
    NoaaText,
    SourceKeys,
    SourceRef,
    ThreatRef,
    briefing_context,
    change_ref,
    compass8,
    escaped_json,
    noaa_text,
    render_noaa,
    text_key,
    threat_ref,
    to_hour,
)
from weatherbot.services.ai.prompts import ladder_text
from weatherbot.services.health import staleness
from weatherbot.services.persistence.repositories import (
    AssessmentHead,
    AssessmentRepository,
    HeartbeatRepository,
    SnapshotRepository,
    StoredAssessment,
)

type ToolName = Literal[
    "list_locations",
    "get_assessment",
    "get_evidence",
    "get_alerts",
    "get_storms",
    "get_storm",
    "get_outlook",
    "get_ladder",
    "get_history",
]
type Basin = Literal["atl", "pac", "cpac"]

TOOL_NAMES: Final = (
    "list_locations",
    "get_assessment",
    "get_evidence",
    "get_alerts",
    "get_storms",
    "get_storm",
    "get_outlook",
    "get_ladder",
    "get_history",
)
"""The only tools the model can call, in the order their definitions are sent."""
BASINS: Final[tuple[Basin, ...]] = ("atl", "pac", "cpac")
TWO_BASINS: Final[Mapping[Basin, str]] = {"atl": "AT", "pac": "EP", "cpac": "CP"}
"""Each outlook basin's TWO, by the TWO's basin code."""
BASIN_NAMES: Final[Mapping[Basin, str]] = {
    "atl": "Atlantic",
    "pac": "eastern North Pacific",
    "cpac": "central North Pacific",
}
STORM_BASINS: Final[Mapping[str, str]] = {
    "AL": "Atlantic",
    "EP": "eastern North Pacific",
    "CP": "central North Pacific",
}
"""A storm's basin, by its ATCF id's first two letters."""
RESULT_LIMIT: Final = 8_000
RESULT_CUT: Final = "\n[cut: the rest of this result is not included]"
HISTORY_LIMIT: Final = 10
MIN_CUT_TEXT: Final = 200
"""A NOAA text cut shorter than this is left out instead."""

TOOL_DEFINITIONS: Final[tuple[dict[str, Any], ...]] = (
    {
        "name": "list_locations",
        "description": (
            "List Weatherbot's locations, each with its current official level (number and "
            "label), whether its inputs were complete, and the time of its latest assessment."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_assessment",
        "description": (
            "Read one location's latest assessment: its level, rule, and evidence, the official "
            "products the engine considered, the wind-speed probabilities there, each storm's "
            "threat (distance band, compass point, closest approach, and arrival times), the "
            "changes since the previous assessment, stale sources, and the sources. It holds "
            "no NOAA text: get_alerts and get_storm carry that."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The location's name, exactly as list_locations gives it.",
                }
            },
            "required": ["location"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_evidence",
        "description": (
            "Read why one location has its current level: the deciding rule and its trigger, "
            "each product that matched it, and the inputs that were unavailable."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The location's name, exactly as list_locations gives it.",
                }
            },
            "required": ["location"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_alerts",
        "description": (
            "Read the official products that cover one location: each NWS alert, with its "
            "headline, description, and instruction as NOAA text, and each NHC watch or "
            "warning segment."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The location's name, exactly as list_locations gives it.",
                }
            },
            "required": ["location"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_storms",
        "description": (
            "List the active storms in the latest snapshot: each one's name, ATCF id, basin, "
            "classification, category (1 to 5, absent below hurricane strength), and its "
            "latest advisory's number and time."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_storm",
        "description": (
            "Read one active storm: its summary from the latest snapshot, what it means for "
            "each location (distance band, compass point, closest approach, and arrival "
            "times), and its latest NHC public advisory (TCP) as NOAA text."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "atcf_id": {
                    "type": "string",
                    "description": (
                        "The storm's ATCF id, as get_storms gives it: two letters and six digits."
                    ),
                }
            },
            "required": ["atcf_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_outlook",
        "description": (
            "Read one basin's tropical weather outlook: the NHC Tropical Weather Outlook (TWO) "
            "as NOAA text, and the chances of formation that the outlook's areas carry."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "basin": {
                    "type": "string",
                    "enum": ["atl", "pac", "cpac"],
                    "description": (
                        "atl: the Atlantic; pac: the eastern North Pacific; cpac: the central "
                        "North Pacific."
                    ),
                }
            },
            "required": ["basin"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_ladder",
        "description": (
            "Read Weatherbot's alert ladder: the five levels with their labels and actions, the "
            "rules in the order the engine checks them, and the thresholds in effect."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_history",
        "description": (
            "Read one location's recent assessments, newest first: each one's time, level, "
            "rule, whether its inputs were complete, and its changes from the one before."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The location's name, exactly as list_locations gives it.",
                },
                "limit": {
                    "type": "integer",
                    "description": "How many assessments to read, from 1 to 10.",
                },
            },
            "required": ["location", "limit"],
            "additionalProperties": False,
        },
    },
)
"""The tool definitions, in ``TOOL_NAMES`` order; ``tool_params`` adds the cache marker."""


def tool_params() -> list[dict[str, Any]]:
    """Return the request's ``tools``: the definitions, the last one marked for the cache.

    Returns:
        A fresh copy of the nine definitions; the definitions themselves never change.
    """
    tools = [copy.deepcopy(definition) for definition in TOOL_DEFINITIONS]
    tools[-1]["cache_control"] = {"type": "ephemeral"}
    return tools


# The arguments, validated again ------------------------------------------------------------


class _Arguments(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)


class _NoArguments(_Arguments):
    pass


class _LocationArguments(_Arguments):
    location: str = Field(min_length=1, max_length=64)


class _HistoryArguments(_LocationArguments):
    limit: int = Field(ge=1, le=HISTORY_LIMIT)


class _StormArguments(_Arguments):
    atcf_id: str = Field(pattern=r"^[A-Z]{2}\d{6}$")


class _BasinArguments(_Arguments):
    basin: Basin


_ARGUMENTS: Final[Mapping[str, type[_Arguments]]] = {
    "list_locations": _NoArguments,
    "get_assessment": _LocationArguments,
    "get_evidence": _LocationArguments,
    "get_alerts": _LocationArguments,
    "get_storms": _NoArguments,
    "get_storm": _StormArguments,
    "get_outlook": _BasinArguments,
    "get_ladder": _NoArguments,
    "get_history": _HistoryArguments,
}
_SHAPES: Final[Mapping[str, str]] = {
    "list_locations": "no input",
    "get_assessment": "location, one of the allowed names",
    "get_evidence": "location, one of the allowed names",
    "get_alerts": "location, one of the allowed names",
    "get_storms": "no input",
    "get_storm": "atcf_id, one of the allowed storms",
    "get_outlook": "basin, one of the allowed basins",
    "get_ladder": "no input",
    "get_history": "location, one of the allowed names, and limit, an integer from 1 to 10",
}


# The results' records ----------------------------------------------------------------------


class LocationLevel(DomainModel):
    """A location's current official level, as ``list_locations`` returns it; never a point."""

    name: str
    level: int = Field(ge=1, le=5)
    label: str
    complete: bool
    as_of: Hour


class StormEntry(DomainModel):
    """An active storm, as ``get_storms`` returns it: no position."""

    name: str
    atcf_id: str
    basin: str | None = None
    classification: str | None = None
    development: str | None = None
    category: int | None = Field(default=None, ge=1, le=5)
    advisory: str | None = None
    advisory_issued: Hour | None = None


class StormDetail(StormEntry):
    """One storm's summary, as ``get_storm`` returns it; its position is only in its TCP."""

    intensity_kt: int | None = None
    pressure_mb: int | None = None
    moving_toward: str | None = Field(default=None, description="A compass point.")
    speed_mph: int | None = None


class StormThreatEntry(DomainModel):
    """What one storm means for one location, coarsened."""

    location: str
    threat: ThreatRef


class AreaEntry(DomainModel):
    """An outlook area's chances of formation, without its geometry."""

    kind: str
    chance_2day_pct: int | None = None
    chance_7day_pct: int | None = None
    risk_2day: str | None = None
    risk_7day: str | None = None
    issued: Hour
    source: str


class HistoryEntry(DomainModel):
    """One past assessment of a location: its level and its changes, without sentences."""

    as_of: Hour
    level: int = Field(ge=1, le=5)
    label: str
    rule: str
    complete: bool
    changes: tuple[ChangeRef, ...] = ()


@dataclass(frozen=True)
class ToolResult:
    """One call's result: the text the model reads, whether it is an error, its NOAA texts."""

    content: str
    is_error: bool = False
    noaa: tuple[NoaaText, ...] = ()
    """The NOAA texts the result quotes, against which a sentence's positions are checked."""


def _dump(model: DomainModel) -> dict[str, object]:
    return model.model_dump(mode="json", exclude_defaults=True)


def _cut(text: NoaaText, room: int) -> NoaaText | None:
    """A NOAA text cut to fit ``room`` characters as a block, marked; ``None`` if too short."""
    body = text.text
    while len(body) >= MIN_CUT_TEXT:
        candidate = text.model_copy(update={"text": body + CUT_MARK})
        excess = len(render_noaa(candidate)) - room
        if excess <= 0:
            return candidate
        body = body[: len(body) - excess]
    return None


def bounded(
    document: Mapping[str, object], texts: Sequence[NoaaText] = ()
) -> tuple[str, tuple[NoaaText, ...]]:
    """Render a result: its JSON document, then its blocks, within ``RESULT_LIMIT``.

    Args:
        document: The result's JSON document.
        texts: Its NOAA texts, in order.

    Returns:
        The text, at most ``RESULT_LIMIT`` characters and marked when cut, and the NOAA
        texts it holds (a cut text as cut).
    """
    text = escaped_json(document)
    budget = RESULT_LIMIT - len(RESULT_CUT)
    if len(text) > RESULT_LIMIT:
        return text[:budget] + RESULT_CUT, ()
    kept: list[NoaaText] = []
    for item in texts:
        block = f"\n\n{render_noaa(item)}"
        if len(text) + len(block) <= budget:
            text += block
            kept.append(item)
            continue
        cut = _cut(item, budget - len(text) - 2)
        if cut is not None:
            text += f"\n\n{render_noaa(cut)}"
            kept.append(cut)
        return text + RESULT_CUT, tuple(kept)
    return text, tuple(kept)


def _result(document: Mapping[str, object], texts: Sequence[NoaaText] = ()) -> ToolResult:
    content, kept = bounded(document, texts)
    return ToolResult(content, noaa=kept)


def _error(kind: str, message: str, allowed: object) -> ToolResult:
    document = {"error": kind, "message": message, "allowed": allowed}
    return ToolResult(bounded(document)[0], is_error=True)


def _referenced(sources: Sequence[SourceRef], keys: set[str]) -> list[dict[str, object]]:
    return [_dump(source) for source in sources if source.key in keys]


# Reading -----------------------------------------------------------------------------------


class _Reader:
    """One round's reads through the AI engine: each snapshot loaded at most once."""

    def __init__(self, engine: Engine, now: Callable[[], datetime]) -> None:
        self._engine = engine
        self._now = now
        self._heads: dict[str, AssessmentHead] | None = None
        self._snapshots: dict[UUID, Snapshot | None] = {}

    def heads(self) -> dict[str, AssessmentHead]:
        if self._heads is None:
            self._heads = AssessmentRepository(self._engine).latest_heads()
        return self._heads

    def location(self, name: str) -> str | None:
        """The stored name a requested name means: exact, else the one equal ignoring case."""
        heads = self.heads()
        if name in heads:
            return name
        folded = [stored for stored in heads if stored.casefold() == name.casefold()]
        return folded[0] if len(folded) == 1 else None

    def snapshot(self, snapshot_id: UUID) -> Snapshot | None:
        if snapshot_id not in self._snapshots:
            self._snapshots[snapshot_id] = SnapshotRepository(self._engine).load(snapshot_id)
        return self._snapshots[snapshot_id]

    def latest_snapshot(self) -> Snapshot | None:
        snapshot_id = SnapshotRepository(self._engine).latest_id()
        return self.snapshot(snapshot_id) if snapshot_id is not None else None

    def stored(self, name: str) -> StoredAssessment | None:
        return AssessmentRepository(self._engine).latest(name)

    def context(self, stored: StoredAssessment) -> BriefingContext:
        snapshot = self.snapshot(stored.assessment.snapshot_id)
        judged = staleness(HeartbeatRepository(self._engine).rows(), self._now())
        stale = [item.name for item in judged if item.stale and item.kind == "source"]
        return briefing_context(stored.assessment, stored.changes, snapshot, stale)

    def thresholds(self) -> Thresholds:
        heads = self.heads()
        return next(iter(heads.values())).thresholds if heads else Thresholds()


def _tau0_category(storm: StormProducts) -> tuple[int | None, str | None]:
    if not storm.track_points:
        return None, None
    first = min(storm.track_points, key=lambda point: (point.valid_at, point.tau_h))
    ssnum = first.saffir_simpson
    return (ssnum if ssnum is not None and ssnum >= 1 else None), first.development


def _latest_advisory(storm: StormProducts) -> tuple[str | None, datetime | None]:
    if storm.summary is not None:
        public = storm.summary.public_advisory
        return str(public.advisory), public.issued_at
    records = (storm.cone, *storm.track_points, storm.track)
    record = next((item for item in records if item is not None), None)
    if record is None:
        return None, None
    return str(record.advisory.number), record.advisory.issued_at


def storm_entry(storm: StormProducts) -> StormEntry:
    """Summarize an active storm without its position.

    Args:
        storm: The storm and its products.

    Returns:
        Its name, ATCF id, basin, classification, development and category at the
        advisory's first forecast point, and its latest advisory.
    """
    category, development = _tau0_category(storm)
    advisory, issued = _latest_advisory(storm)
    if storm.summary is not None:
        classification = storm.summary.classification.raw
    else:
        classification = storm.archived.storm_type if storm.archived is not None else None
    return StormEntry(
        name=storm.name,
        atcf_id=storm.atcf_id,
        basin=STORM_BASINS.get(storm.atcf_id[:2]),
        classification=classification,
        development=development,
        category=category,
        advisory=advisory,
        advisory_issued=to_hour(issued) if issued is not None else None,
    )


def _storm_detail(storm: StormProducts) -> StormDetail:
    entry = storm_entry(storm)
    summary = storm.summary
    if summary is None:
        return StormDetail(**dict(entry))
    direction = summary.movement_dir_deg
    speed = summary.movement_speed_mph
    return StormDetail(
        **dict(entry),
        intensity_kt=summary.intensity_kt,
        pressure_mb=summary.pressure_mb,
        moving_toward=compass8(direction) if direction is not None else None,
        speed_mph=round(speed) if speed is not None else None,
    )


def _in_basin(area_basin: str, basin: Basin) -> bool:
    text = area_basin.casefold()
    if basin == "cpac":
        return "central" in text
    if basin == "pac":
        return "pacific" in text and "central" not in text
    return "atlantic" in text


class Toolbox:
    """Runs the chat's tool calls through the AI engine, which refuses every write."""

    def __init__(self, engine: Engine, *, now: Callable[[], datetime]) -> None:
        """Create the toolbox.

        Args:
            engine: The AI engine (``guard.ai_engine``).
            now: The clock, for the stale sources.
        """
        self._engine = engine
        self._now = now

    @property
    def engine(self) -> Engine:
        """The engine every tool reads through."""
        return self._engine

    def run(self, calls: Sequence[tuple[str, object]]) -> tuple[ToolResult, ...]:
        """Run one round's calls in order, sharing each snapshot they load.

        Args:
            calls: Each call's tool name and its arguments as the model sent them.

        Returns:
            One result per call, in order.
        """
        reader = _Reader(self._engine, self._now)
        return tuple(self._one(reader, name, arguments) for name, arguments in calls)

    def _one(self, reader: _Reader, name: str, arguments: object) -> ToolResult:
        if name not in TOOL_NAMES:
            return _error("unknown_tool", "no tool has that name", list(TOOL_NAMES))
        try:
            checked = _ARGUMENTS[name].model_validate(arguments)
        except ValidationError:
            return self._bad_arguments(reader, name)
        try:
            return self._call(reader, name, checked)
        except ContextTooLarge:
            return _error("too_large", "the location's data is too large to read", [])

    def _call(  # noqa: PLR0911 - one return per tool
        self, reader: _Reader, name: ToolName, arguments: _Arguments
    ) -> ToolResult:
        if name == "list_locations":
            return self._list_locations(reader)
        if name == "get_storms":
            return self._get_storms(reader)
        if name == "get_ladder":
            return self._get_ladder(reader)
        if isinstance(arguments, _StormArguments):
            return self._get_storm(reader, arguments.atcf_id)
        if isinstance(arguments, _BasinArguments):
            return self._get_outlook(reader, arguments.basin)
        location = cast("_LocationArguments", arguments).location
        found = reader.location(location)
        stored = reader.stored(found) if found is not None else None
        if found is None or stored is None:
            allowed = list(reader.heads())
            return _error("unknown_location", "no stored location has that name", allowed)
        if isinstance(arguments, _HistoryArguments):
            return self._get_history(found, arguments.limit)
        context = reader.context(stored)
        if name == "get_assessment":
            return _result(context.model_dump(mode="json", exclude={"noaa"}, exclude_defaults=True))
        if name == "get_evidence":
            return self._get_evidence(context)
        return self._get_alerts(context)

    def _bad_arguments(self, reader: _Reader, name: str) -> ToolResult:
        allowed: dict[str, object] = {}
        if name in {"get_assessment", "get_evidence", "get_alerts", "get_history"}:
            allowed["location"] = list(reader.heads())
        if name == "get_history":
            allowed["limit"] = f"an integer from 1 to {HISTORY_LIMIT}"
        if name == "get_outlook":
            allowed["basin"] = list(BASINS)
        if name == "get_storm":
            allowed["atcf_id"] = self._storm_ids(reader)
        return _error("bad_arguments", f"{name} takes {_SHAPES[name]}", allowed)

    @staticmethod
    def _storm_ids(reader: _Reader) -> list[str]:
        snapshot = reader.latest_snapshot()
        return [storm.atcf_id for storm in snapshot.storms] if snapshot is not None else []

    @staticmethod
    def _list_locations(reader: _Reader) -> ToolResult:
        locations = [
            LocationLevel(
                name=name,
                level=head.level,
                label=AlertLevel(head.level).label,
                complete=head.complete,
                as_of=to_hour(head.as_of),
            )
            for name, head in reader.heads().items()
        ]
        return _result({"locations": [_dump(location) for location in locations]})

    @staticmethod
    def _get_evidence(context: BriefingContext) -> ToolResult:
        document = context.model_dump(
            mode="json",
            include={
                "location",
                "as_of",
                "level",
                "rule",
                "trigger",
                "complete",
                "unavailable",
                "evidence",
            },
            exclude_defaults=True,
        )
        keys = {item.source for item in context.evidence if item.source is not None}
        document["sources"] = _referenced(context.sources, keys)
        return _result(document)

    @staticmethod
    def _get_alerts(context: BriefingContext) -> ToolResult:
        covering = [product for product in context.official if product.covers]
        keys = {product.source for product in covering}
        document = context.model_dump(mode="json", include={"location", "as_of"})
        document["covering"] = [_dump(product) for product in covering]
        document["sources"] = _referenced(context.sources, keys)
        texts = [text for text in context.noaa if text.key in keys]
        return _result(document, texts)

    @staticmethod
    def _get_storms(reader: _Reader) -> ToolResult:
        snapshot = reader.latest_snapshot()
        storms = [storm_entry(storm) for storm in snapshot.storms] if snapshot is not None else []
        return _result({"storms": [_dump(storm) for storm in storms]})

    def _get_storm(self, reader: _Reader, atcf_id: str) -> ToolResult:
        snapshot = reader.latest_snapshot()
        storm = next(
            (item for item in (snapshot.storms if snapshot else ()) if item.atcf_id == atcf_id),
            None,
        )
        if snapshot is None or storm is None:
            allowed = self._storm_ids(reader)
            return _error("unknown_storm", "no active storm has that ATCF id", allowed)
        sources = SourceKeys()
        threats: list[StormThreatEntry] = []
        for name in reader.heads():
            stored = reader.stored(name)
            for threat in stored.assessment.threats if stored is not None else ():
                if threat.atcf_id == atcf_id:
                    reference = threat_ref(threat, None, sources, [])
                    threats.append(StormThreatEntry(location=name, threat=reference))
        tcps = [
            product
            for product in snapshot.text_products
            if product.code == "TCP" and product.atcf_id == atcf_id
        ]
        texts: list[NoaaText] = []
        key = None
        if tcps:
            tcp = max(tcps, key=lambda product: product.issued_at)
            key = text_key(tcp, sources, storm.name)
            texts.append(noaa_text(key, tcp.code, tcp.issued_at, tcp.text))
        document = {
            "storm": _dump(_storm_detail(storm)),
            "public_advisory": key,
            "threats": [_dump(threat) for threat in threats],
            "sources": [_dump(source) for source in sources.refs],
        }
        return _result(document, texts)

    @staticmethod
    def _get_outlook(reader: _Reader, basin: Basin) -> ToolResult:
        snapshot = reader.latest_snapshot()
        sources = SourceKeys()
        texts: list[NoaaText] = []
        key = None
        twos = [
            product
            for product in (snapshot.text_products if snapshot else ())
            if product.code == "TWO" and product.location == TWO_BASINS[basin]
        ]
        if twos:
            two = max(twos, key=lambda product: product.issued_at)
            key = text_key(two, sources, None)
            texts.append(noaa_text(key, two.code, two.issued_at, two.text))
        areas: list[AreaEntry] = []
        for area in snapshot.outlook_areas if snapshot else ():
            if not _in_basin(area.basin, basin):
                continue
            provenance = area.provenance
            source = sources.key(
                ("area", provenance.source_id, provenance.sha256),
                source_id=provenance.source_id,
                title="NHC graphical tropical weather outlook areas",
                issued=area.issued_at,
            )
            areas.append(
                AreaEntry(
                    kind=area.kind,
                    chance_2day_pct=area.chance_2day_pct,
                    chance_7day_pct=area.chance_7day_pct,
                    risk_2day=area.risk_2day.raw if area.risk_2day is not None else None,
                    risk_7day=area.risk_7day.raw if area.risk_7day is not None else None,
                    issued=to_hour(area.issued_at),
                    source=source,
                )
            )
        document = {
            "basin": BASIN_NAMES[basin],
            "outlook": key,
            "areas": [_dump(area) for area in areas],
            "sources": [_dump(source) for source in sources.refs],
        }
        return _result(document, texts)

    @staticmethod
    def _get_ladder(reader: _Reader) -> ToolResult:
        thresholds = reader.thresholds()
        return _result(
            {"ladder": ladder_text(thresholds), "thresholds": thresholds.model_dump(mode="json")}
        )

    def _get_history(self, location: str, limit: int) -> ToolResult:
        rows = AssessmentRepository(self._engine).history(location, limit)
        entries = [
            HistoryEntry(
                as_of=to_hour(row.assessment.as_of),
                level=int(row.assessment.level),
                label=row.assessment.level.label,
                rule=str(row.assessment.rule),
                complete=row.assessment.complete,
                changes=tuple(change_ref(event) for event in row.changes),
            )
            for row in rows
        ]
        return _result({"location": location, "history": [_dump(entry) for entry in entries]})
