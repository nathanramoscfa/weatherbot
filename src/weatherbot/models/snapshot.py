# src/weatherbot/models/snapshot.py
"""A snapshot: everything fetched in one run, and what each source answered."""

from collections import Counter
from collections.abc import Iterable, Iterator
from typing import Literal, Self, cast
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from weatherbot.models.alerts import NwsAlert
from weatherbot.models.arrivals import ArrivalTimeProduct
from weatherbot.models.base import DomainModel
from weatherbot.models.outlook import OutlookArea, WindProbabilityProduct
from weatherbot.models.products import (
    Breakpoint,
    DisplayLayer,
    GisFeedItem,
    OutlookGraphic,
    TextProduct,
)
from weatherbot.models.provenance import Provenance, SourceId
from weatherbot.models.storms import (
    ArchiveStorm,
    ConeGeometry,
    ForecastTrack,
    StormSummary,
    TrackPoint,
    WatchWarningSegment,
    WindRadii,
)
from weatherbot.models.times import UtcDatetime

ROSTER: SourceId = "nhc-current-storms"
ARCHIVE: SourceId = "nhc-gis-archive"
REPLAY_SOURCES: frozenset[SourceId] = frozenset({ARCHIVE, "nhc-arrival-times"})
"""The only sources a replay snapshot's records may cite."""


class SourceOutcome(DomainModel):
    """What one source the snapshot asked for answered."""

    source_id: SourceId
    status: Literal["ok", "not_modified", "failed", "skipped"]
    error_kind: str | None = Field(default=None, description="For failed: the error's kind.")
    reason: str | None = Field(default=None, description="For skipped: why.")

    @model_validator(mode="after")
    def _detail_fits_status(self) -> Self:
        if (self.status == "failed") != (self.error_kind is not None):
            message = "a failed outcome, and only a failed one, names its error kind"
            raise ValueError(message)
        if (self.status == "skipped") != (self.reason is not None):
            message = "a skipped outcome, and only a skipped one, gives its reason"
            raise ValueError(message)
        return self


class StormProducts(DomainModel):
    """One storm and the advisory products fetched or replayed for it.

    A storm carries exactly one header: the roster's ``summary`` in a live snapshot, or
    the archive's ``archived`` record in a replay snapshot. ``atcf_id`` and ``name`` read
    whichever is present.
    """

    summary: StormSummary | None = None
    archived: ArchiveStorm | None = None
    cone: ConeGeometry | None = None
    track_points: tuple[TrackPoint, ...] = ()
    track: ForecastTrack | None = None
    watch_warnings: tuple[WatchWarningSegment, ...] = ()
    wind_radii: tuple[WindRadii, ...] = ()
    arrival_times: tuple[ArrivalTimeProduct, ...] = ()

    @model_validator(mode="after")
    def _one_storm(self) -> Self:
        if (self.summary is None) == (self.archived is None):
            message = "a storm carries exactly one header: the roster's summary or the archive's"
            raise ValueError(message)
        records = [self.cone, self.track, *self.track_points, *self.watch_warnings]
        records += [*self.wind_radii, *self.arrival_times]
        if any(r is not None and r.atcf_id != self.atcf_id for r in records):
            message = "every product of a storm belongs to that storm"
            raise ValueError(message)
        return self

    @property
    def atcf_id(self) -> str:
        """The storm's ATCF id, from whichever header it carries."""
        header = self.summary or self.archived
        return header.atcf_id if header is not None else ""

    @property
    def name(self) -> str:
        """The storm's name: the roster's, or the archive's ``STORMNAME``."""
        header = self.summary or self.archived
        return header.name if header is not None else ""


def _provenances(value: object) -> Iterator[Provenance]:
    """Yield every provenance a value holds, at any depth."""
    if isinstance(value, Provenance):
        yield value
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from _provenances(getattr(value, name))
    elif isinstance(value, tuple | list):
        for item in cast("Iterable[object]", value):
            yield from _provenances(item)
    elif isinstance(value, dict):
        for item in cast("dict[object, object]", value).values():
            yield from _provenances(item)


class Snapshot(DomainModel):
    """Everything one run fetched, with one outcome per source it asked for.

    Nothing in a snapshot stands in for a source it did not fetch: every record's source
    has an ``ok`` or ``not_modified`` outcome. Wind-speed probabilities belong to the
    snapshot, one product per threshold (issue #12).

    ``origin`` says where the snapshot came from. A ``live`` snapshot always asks the
    roster, and its storms carry the roster's summary. A ``replay`` snapshot is one
    advisory read back from the GIS archive: it has an ``nhc-gis-archive`` outcome and no
    roster outcome, its storms carry an ``ArchiveStorm``, and every record cites the
    archive or ``nhc-arrival-times``.
    """

    snapshot_id: UUID
    origin: Literal["live", "replay"] = "live"
    started_at: UtcDatetime
    completed_at: UtcDatetime
    storms: tuple[StormProducts, ...] = ()
    outlook_areas: tuple[OutlookArea, ...] = ()
    wind_probabilities: tuple[WindProbabilityProduct, ...] = ()
    text_products: tuple[TextProduct, ...] = ()
    gis_feed_items: tuple[GisFeedItem, ...] = ()
    outlook_graphics: tuple[OutlookGraphic, ...] = ()
    breakpoints: tuple[Breakpoint, ...] = ()
    display_layers: tuple[DisplayLayer, ...] = ()
    alerts: dict[str, tuple[NwsAlert, ...]] = Field(
        default_factory=dict[str, tuple[NwsAlert, ...]],
        description="Keyed by location name.",
    )
    source_outcomes: tuple[SourceOutcome, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.completed_at < self.started_at:
            message = "a snapshot completes after it starts"
            raise ValueError(message)
        sources: Counter[SourceId] = Counter(o.source_id for o in self.source_outcomes)
        if any(count > 1 for count in sources.values()) or self._primary not in sources:
            first = "the roster" if self.origin == "live" else "the GIS archive"
            message = f"one outcome per source asked for, {first} always among them"
            raise ValueError(message)
        storm_ids = [storm.atcf_id for storm in self.storms]
        thresholds = [product.threshold_kt for product in self.wind_probabilities]
        if len(set(storm_ids)) != len(storm_ids) or len(set(thresholds)) != len(thresholds):
            message = "one entry per storm, and one wind-probability product per threshold"
            raise ValueError(message)
        if any(not 1 <= len(name) <= 64 for name in self.alerts):  # noqa: PLR2004 - Location.name
            message = "alerts are keyed by location name"
            raise ValueError(message)
        if self.origin == "replay":
            self._check_replay(sources)
        elif any(storm.summary is None for storm in self.storms):
            message = "a live snapshot's storms carry the roster's summary"
            raise ValueError(message)
        fetched = {o.source_id for o in self.source_outcomes if o.status in ("ok", "not_modified")}
        if any(p.source_id not in fetched for p in _provenances(self)):
            message = "every record's source has an ok or not_modified outcome"
            raise ValueError(message)
        return self

    def _check_replay(self, sources: Counter[SourceId]) -> None:
        if ROSTER in sources:
            message = "a replay snapshot asks no roster"
            raise ValueError(message)
        if any(storm.archived is None for storm in self.storms):
            message = "a replay snapshot's storms carry the archive's record"
            raise ValueError(message)
        if any(p.source_id not in REPLAY_SOURCES for p in _provenances(self)):
            message = "a replay snapshot holds only records of the archive and the arrival times"
            raise ValueError(message)

    @property
    def _primary(self) -> SourceId:
        """The source a snapshot always asks: the roster, or for a replay the archive."""
        return ROSTER if self.origin == "live" else ARCHIVE

    @property
    def status(self) -> Literal["complete", "partial", "failed"]:
        """``failed`` when the roster (a replay's archive) failed; ``partial`` for any other."""
        failed = {o.source_id for o in self.source_outcomes if o.status == "failed"}
        if self._primary in failed:
            return "failed"
        return "partial" if failed else "complete"
