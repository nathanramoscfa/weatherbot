# src/weatherbot/services/ai/narration.py
"""``NarrationService``: an AI interpretation of one official outlook graphic, off by default.

``stream(basin, horizon)`` is unavailable (``disabled``) unless ``[ai] outlook_narration``
is on. It reads the latest snapshot's outlook graphic for the basin and horizon and its
basin's TWO; the PNG comes from the raw-response cache's ``response_bodies`` by the
graphic's stored SHA-256, through the AI engine, and nothing is downloaded. A body that
is missing, corrupt, not that SHA-256, or not a PNG (``raw_cache.stored_png``) is
``no_graphic``. The request is the narration's frozen system prompt (marked for the
cache), then the image block (``image/png``, base64) and the TWO in an escaped
``<noaa_product>`` block with its links removed, then the task line; adaptive thinking at
effort ``low`` and ``max_tokens`` 2,000, streamed as ``OutlookNarration``. The ledger's
ceiling counts the image at its visual tokens (⌈width/28⌉ x ⌈height/28⌉), never its
base64 text.

``validate_narration`` withholds a narration that states any level, a URL, or a position,
lacks its caveat, passes its bounds, or states a chance the TWO's text does not state
(compared as numbers: "20%" matches "20 percent"). A narration is stored, ``ok`` or
withheld, once per graphic SHA-256, TWO text SHA-256, model, and prompt version, and an
``ok`` one is reused without a request unless ``new`` is asked for. Every surface labels it
"AI interpretation of the official graphic".

Nothing here logs a prompt or an answer. The module loads no SDK.
"""

import asyncio
import base64
import hashlib
import json
from collections.abc import AsyncGenerator, AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal
from uuid import UUID

from pydantic import TypeAdapter

from weatherbot.models import OutlookGraphic, Snapshot, TextProduct
from weatherbot.services.ai.context import (
    NoaaText,
    SourceKeys,
    SourceRef,
    noaa_text,
    render_noaa,
    text_key,
)
from weatherbot.services.ai.errors import AiUnavailable, AiUnavailableReason, InvalidOutputError
from weatherbot.services.ai.outputs import NewOutput, OutputRepository, StoredOutput
from weatherbot.services.ai.prompts import narration_prompt_version, narration_system_blocks
from weatherbot.services.ai.schemas import OutlookNarration
from weatherbot.services.ai.service import AiService
from weatherbot.services.ai.tools import BASIN_NAMES, TWO_BASINS, Basin
from weatherbot.services.ai.validate import ViolationRule, first_violation, validate_narration
from weatherbot.services.persistence.raw_cache import stored_png
from weatherbot.services.persistence.repositories import SnapshotRepository

type Horizon = Literal["2d0", "7d0"]
type NarrationWithheldReason = ViolationRule | Literal["incomplete", "invalid_output"]
type NarrationUnavailableReason = AiUnavailableReason | Literal["no_graphic", "no_outlook"]

NARRATION_LABEL: Final = "AI interpretation of the official graphic"
NARRATION_MAX_TOKENS: Final = 2_000
NARRATION_EFFORT: Final = "low"
HORIZONS: Final[tuple[Horizon, ...]] = ("2d0", "7d0")
HORIZON_NAMES: Final[Mapping[Horizon, str]] = {"2d0": "two days", "7d0": "seven days"}
INCOMPLETE_DETAIL: Final = "the narration did not arrive whole"
INVALID_DETAIL: Final = "the answer did not match its schema"
UNAVAILABLE_TEXT: Final[Mapping[str, str]] = {
    "disabled": "outlook narration is off; set outlook_narration = true under [ai]",
    "no_graphic": "the latest snapshot holds no stored outlook graphic for that basin and horizon",
    "no_outlook": "the latest snapshot holds no tropical weather outlook for that basin",
}
"""The narration's own unavailable reasons, as a person reads them."""
_SOURCE: Final = TypeAdapter(SourceRef)


@dataclass(frozen=True)
class Started:
    """A narration began: its model, the graphic, the TWO it is checked against, the prompt."""

    model: str
    basin: Basin
    horizon: Horizon
    graphic_sha256: str
    two_issued_at: datetime
    prompt_version: str


@dataclass(frozen=True)
class Done:
    """The narration passed and is stored (or was stored before, and reused)."""

    output_id: int
    narration: OutlookNarration
    created_at: datetime
    reused: bool


@dataclass(frozen=True)
class Withheld:
    """The narration was withheld: its reason, and fixed text that never quotes the model."""

    reason: NarrationWithheldReason
    detail: str
    output_id: int | None = None


@dataclass(frozen=True)
class Unavailable:
    """No narration could be asked for; nothing was stored."""

    reason: NarrationUnavailableReason


type NarrationEvent = Started | Done | Withheld | Unavailable


@dataclass(frozen=True)
class _Graphic:
    """The graphic to narrate, its PNG, and its basin's TWO."""

    snapshot_id: UUID
    graphic: OutlookGraphic
    png: bytes
    two: TextProduct
    two_text: NoaaText
    two_source: SourceRef
    two_sha256: str


def two_sha256(two: TextProduct) -> str:
    """Return the SHA-256 of a TWO's text, which a stored narration is checked against.

    Args:
        two: The TWO.

    Returns:
        The hexadecimal digest of its text as received.
    """
    return hashlib.sha256(two.text.encode("utf-8")).hexdigest()


def narration_params(png: bytes, two: NoaaText, basin: Basin, horizon: Horizon) -> dict[str, Any]:
    """Build a narration request's body, without ``model`` or its output format.

    Args:
        png: The graphic's PNG body.
        two: The basin's TWO, prepared for a request (``context.noaa_text``).
        basin: The graphic's basin.
        horizon: Its horizon.

    Returns:
        The body: the frozen narration prompt with its cache marker, the image block, the
        TWO's block and the task line, adaptive thinking, effort ``low``, and
        ``max_tokens`` 2,000.
    """
    task = (
        f"Task: describe the official graphic: the {BASIN_NAMES[basin]} outlook over "
        f"{HORIZON_NAMES[horizon]}."
    )
    image = {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.standard_b64encode(png).decode("ascii"),
        },
    }
    text = {"type": "text", "text": f"{render_noaa(two)}\n\n{task}"}
    return {
        "max_tokens": NARRATION_MAX_TOKENS,
        "system": narration_system_blocks(),
        "messages": [{"role": "user", "content": [image, text]}],
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": NARRATION_EFFORT},
    }


def stored_narration(stored: StoredOutput) -> tuple[OutlookNarration, SourceRef]:
    """Read a stored narration's content back: the narration and the TWO's source.

    Args:
        stored: An ``ok`` narration.

    Returns:
        The narration and the source of the TWO it was checked against.

    Raises:
        ValueError: The product holds no content.
    """
    if stored.content is None:
        message = "a withheld narration holds no content"
        raise ValueError(message)
    narration = OutlookNarration.model_validate(stored.content["narration"])
    # The strict models read instants from JSON text, as stored.
    source = _SOURCE.validate_json(json.dumps(stored.content["two"]))
    return narration, source


class _NotNarratableError(Exception):
    def __init__(self, *, reason: NarrationUnavailableReason) -> None:
        super().__init__(reason)
        self.reason: NarrationUnavailableReason = reason


def _find(
    snapshot: Snapshot | None, basin: Basin, horizon: Horizon
) -> tuple[OutlookGraphic, TextProduct]:
    if snapshot is None:
        raise _NotNarratableError(reason="no_graphic")
    graphic = next(
        (
            item
            for item in snapshot.outlook_graphics
            if item.basin == basin and item.horizon == horizon
        ),
        None,
    )
    if graphic is None:
        raise _NotNarratableError(reason="no_graphic")
    twos = [
        product
        for product in snapshot.text_products
        if product.code == "TWO" and product.location == TWO_BASINS[basin]
    ]
    if not twos:
        raise _NotNarratableError(reason="no_outlook")
    return graphic, max(twos, key=lambda product: product.issued_at)


class NarrationService:
    """Narrates an official outlook graphic on demand, through the one caller and the ledger."""

    def __init__(self, service: AiService) -> None:
        """Create the service.

        Args:
            service: The AI service; its engine is the AI engine, which reads anything and
                writes only ``ai_calls`` and ``ai_outputs``.
        """
        self._service = service
        self._outputs = OutputRepository(service.engine, now=service.clock, stored=service.stored)

    def output(self, output_id: int) -> StoredOutput | None:
        """Read one stored narration.

        Args:
            output_id: Its id.

        Returns:
            The narration, or ``None``.
        """
        return self._outputs.get(output_id)

    def latest(self, graphic_sha256: str) -> StoredOutput | None:
        """Read the newest stored narration of an outlook graphic, withheld or not.

        Args:
            graphic_sha256: The graphic's PNG body's SHA-256.

        Returns:
            The narration, or ``None``.
        """
        return self._outputs.latest_narration(graphic_sha256)

    def _graphic(self, basin: Basin, horizon: Horizon) -> _Graphic:
        engine = self._service.engine
        repository = SnapshotRepository(engine)
        snapshot_id = repository.latest_id()
        snapshot = repository.load(snapshot_id) if snapshot_id is not None else None
        graphic, two = _find(snapshot, basin, horizon)
        png = stored_png(engine, graphic.provenance.sha256)
        if png is None or snapshot_id is None:
            raise _NotNarratableError(reason="no_graphic")
        sources = SourceKeys()
        key = text_key(two, sources, None)
        return _Graphic(
            snapshot_id=snapshot_id,
            graphic=graphic,
            png=png,
            two=two,
            two_text=noaa_text(key, two.code, two.issued_at, two.text),
            two_source=sources.refs[0],
            two_sha256=two_sha256(two),
        )

    async def stream(
        self, basin: Basin, horizon: Horizon = "7d0", *, new: bool = False
    ) -> AsyncGenerator[NarrationEvent]:
        """Narrate a basin's outlook graphic: reuse the stored one, or ask for a new one.

        Args:
            basin: ``atl``, ``pac``, or ``cpac``.
            horizon: ``2d0`` or ``7d0``.
            new: Ask for a new narration even when one is stored for the graphic.

        Yields:
            ``Started``, then ``Done`` or ``Withheld``; or ``Unavailable``.
        """
        if not self._service.settings.outlook_narration:
            yield Unavailable("disabled")
            return
        try:
            found = await asyncio.to_thread(self._graphic, basin, horizon)
        except _NotNarratableError as error:
            yield Unavailable(error.reason)
            return
        model = self._service.settings.model
        version = narration_prompt_version()
        started = Started(
            model, basin, horizon, found.graphic.provenance.sha256, found.two.issued_at, version
        )
        if not new:
            reused = await asyncio.to_thread(
                self._outputs.narration_for,
                found.graphic.provenance.sha256,
                found.two_sha256,
                model,
                version,
            )
            if reused is not None:
                narration, _ = stored_narration(reused)
                yield started
                yield Done(reused.id, narration, reused.created_at, reused=True)
                return
        try:
            self._service.caller()
        except AiUnavailable as error:
            yield Unavailable(error.reason)
            return
        yield started
        async for event in self._request(found, basin, horizon, version):
            yield event

    async def _store(
        self,
        found: _Graphic,
        version: str,
        call_id: int | None,
        outcome: OutlookNarration | Withheld,
        place: tuple[Basin, Horizon],
    ) -> StoredOutput:
        content = None
        if isinstance(outcome, OutlookNarration):
            content = {
                "narration": outcome.model_dump(mode="json"),
                "basin": place[0],
                "horizon": place[1],
                "graphic_sha256": found.graphic.provenance.sha256,
                "two_sha256": found.two_sha256,
                "two": found.two_source.model_dump(mode="json"),
            }
        output = NewOutput(
            kind="narration",
            model=self._service.settings.model,
            prompt_version=version,
            status="ok" if content is not None else "withheld",
            content=content,
            snapshot_id=found.snapshot_id,
            graphic_sha256=found.graphic.provenance.sha256,
            withheld_reason=outcome.reason if isinstance(outcome, Withheld) else None,
            call_id=call_id,
        )
        return await asyncio.to_thread(self._outputs.add, output)

    async def _request(
        self, found: _Graphic, basin: Basin, horizon: Horizon, version: str
    ) -> AsyncIterator[NarrationEvent]:
        params = narration_params(found.png, found.two_text, basin, horizon)
        call_id: int | None = None
        started = False
        outcome: OutlookNarration | Withheld
        try:
            async with self._service.caller().stream(
                kind="narration",
                model=self._service.settings.model,
                location=None,
                prompt_version=version,
                params=params,
                output_format=OutlookNarration,
            ) as events:
                call_id = events.call_id
                async for _ in events:
                    started = True
            narration = events.output
            if not isinstance(narration, OutlookNarration):
                outcome = Withheld("incomplete", INCOMPLETE_DETAIL)
            else:
                violation = first_violation(validate_narration(narration, found.two_text.text))
                outcome = (
                    narration if violation is None else Withheld(violation.rule, violation.detail)
                )
        except InvalidOutputError as error:
            call_id = error.call_id or call_id
            outcome = Withheld("invalid_output", INVALID_DETAIL)
        except AiUnavailable as error:
            call_id = error.call_id or call_id
            if error.reason != "truncated" and not (started and error.reason != "declined"):
                yield Unavailable(error.reason)
                return
            outcome = Withheld("incomplete", INCOMPLETE_DETAIL)
        saved = await self._store(found, version, call_id, outcome, (basin, horizon))
        if isinstance(outcome, Withheld):
            yield Withheld(outcome.reason, outcome.detail, saved.id)
            return
        yield Done(saved.id, outcome, saved.created_at, reused=False)
