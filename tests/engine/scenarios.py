# tests/engine/scenarios.py
"""Named scenarios: a snapshot, a location, and the level and rule the engine must give.

This step's tests and Step 5's mutation suite share them. The snapshots come from the
recorded fixtures (``tests/services/snapshot_support.py``) and the committed replay
corpus; the locations are the public landmarks, or a point derived at run time from a
recorded public product (a development region's representative point), never a
literal. The expected values use the provisional thresholds (``Thresholds()``).
"""

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cache
from typing import Final

import anyio
from engine_support import DORIAN, IRMA, MIAMI_DADE, NASSAU, REPLAY, landmark_location
from fixture_support import capture_directories, register_alert
from snapshot_support import LANDMARK_NAME, RecordedSnapshot, dorian, recorded_snapshot

from weatherbot.models import (
    RULE_LEVELS,
    AlertLevel,
    AlertQuery,
    DomainModel,
    LatLon,
    Location,
    NwsAlert,
    Provenance,
    RuleId,
    Snapshot,
    SourceOutcome,
)
from weatherbot.services.replay import ReplayCorpus
from weatherbot.sources import nws

RECORDED_DAY: Final = "2026-10-12"
COUNTY_ZONE: Final = "FLC086"
ALERT_SOURCES: Final = ("nws-alerts-point", "nws-alerts-zone")
RIP_CURRENT: Final = "Rip Current Statement"
COASTAL_FLOOD: Final = "Coastal Flood Statement"
HURRICANE_WARNING: Final = "Hurricane Warning"


@dataclass(frozen=True)
class Scenario:
    """A named snapshot and location, and the level, rule, and completeness they give."""

    name: str
    inputs: Callable[[], tuple[Snapshot, Location]]
    level: AlertLevel
    rule: RuleId
    complete: bool


# The recorded snapshot ---------------------------------------------------------------------


@cache
def recorded() -> RecordedSnapshot:
    """The snapshot built from the recorded fixtures, once."""
    return anyio.run(recorded_snapshot)


def rebuilt[M: DomainModel](model: M, **changes: object) -> M:
    """Return a model with some fields replaced, validated again."""
    fields = {name: getattr(model, name) for name in type(model).model_fields}
    return type(model).model_validate(fields | changes)


@cache
def recorded_maps() -> Snapshot:
    """The recorded snapshot of 2026-10-12, without the arrival-time stand-in.

    ``snapshot_support`` adds a roster entry for an archived storm only to carry the
    recorded arrival-time KMZ pair; the map service drew nothing for it, so it has no
    cone. Every other recorded input is kept, including the alerts of 2026-10-17.
    """
    snapshot = recorded().snapshot
    stand_in = dorian().atcf_id
    return rebuilt(snapshot, storms=tuple(s for s in snapshot.storms if s.atcf_id != stand_in))


def miami_dade(*, evacuation: bool = False) -> Location:
    """The Miami-Dade landmark, with the NWS zones its recorded ``/points`` answer gives."""
    return rebuilt(recorded().location, evacuation_order_in_effect=evacuation)


def development_region_location() -> Location:
    """A location at the representative point of the recorded Atlantic development region."""
    area = next(
        area
        for area in recorded_maps().outlook_areas
        if area.kind == "development_region" and area.basin == "Atlantic"
    )
    point = area.geometry.to_shapely().representative_point()
    return Location(
        name="Atlantic development region",
        point=LatLon(latitude=point.y, longitude=point.x),
    )


def rip_current() -> NwsAlert:
    """The Rip Current Statement recorded on 2026-10-17 (point, FLC086, and FLZ173)."""
    (alert,) = recorded().snapshot.alerts[LANDMARK_NAME]
    assert alert.event == RIP_CURRENT
    return alert


@cache
def county_statement() -> NwsAlert:
    """The register's FLC086 Coastal Flood Statement, added to the empty recorded answer.

    It is built from the register's description of 2026-10-12, as
    ``tests/contract/test_nws_captures.py`` builds it, and parsed by the NWS client.
    """
    directory = next(
        item
        for item in capture_directories()
        if item.source == "nws-alerts-zone" and item.day == RECORDED_DAY
    )
    entry = next(
        item for item in directory.entries if item["file"] == f"alerts-zone-{COUNTY_ZONE}.geojson"
    )
    fetched_at = datetime.fromisoformat(str(entry["fetched_at"]))
    document = json.loads(directory.payload(entry))
    document["features"] = [register_alert(fetched_at - timedelta(hours=6))]
    body = json.dumps(document).encode("utf-8")
    provenance = Provenance(
        source_id="nws-alerts-zone",
        url=str(entry["url"]),
        status=int(str(entry["status"])),
        fetched_at=fetched_at,
        sha256=hashlib.sha256(body).hexdigest(),
    )
    query = AlertQuery(kind="zone", zone_id=COUNTY_ZONE, provenance=provenance)
    (alert,) = nws.parse_alerts(body, query)
    assert alert.event == COASTAL_FLOOD
    return alert


def as_hurricane_warning(alert: NwsAlert) -> NwsAlert:
    """A copy of a recorded alert with its event set to Hurricane Warning, built here."""
    return rebuilt(alert, event=HURRICANE_WARNING)


def with_alerts(alerts: Sequence[NwsAlert]) -> Snapshot:
    """The recorded snapshot holding these alerts for the Miami-Dade landmark."""
    return rebuilt(recorded_maps(), alerts={LANDMARK_NAME: tuple(alerts)})


def alerts_failed() -> Snapshot:
    """The recorded snapshot with both alert sources failed, so it holds no alert list."""
    snapshot = recorded_maps()
    outcomes = tuple(
        SourceOutcome(source_id=item.source_id, status="failed", error_kind="SourceHttpError")
        if item.source_id in ALERT_SOURCES
        else item
        for item in snapshot.source_outcomes
    )
    return rebuilt(snapshot, alerts={}, source_outcomes=outcomes)


# The replay corpus -------------------------------------------------------------------------


@cache
def replay_snapshots(atcf_id: str) -> dict[str, Snapshot]:
    """Every replay snapshot of a storm in the committed corpus, by advisory number."""
    corpus = ReplayCorpus.open(REPLAY)
    return {
        str(snapshot.storms[0].cone.advisory.number): snapshot
        for snapshot in corpus.snapshots(atcf_id)
        if snapshot.storms[0].cone is not None
    }


def replay(atcf_id: str, advisory: str) -> Snapshot:
    """One advisory's replay snapshot (``advisory`` as NHC prints it, such as ``36``)."""
    return replay_snapshots(atcf_id)[advisory]


def nassau() -> Location:
    """The Nassau landmark: outside NWS coverage."""
    return landmark_location(NASSAU, name="Parliament Square, Nassau")


def replay_miami_dade() -> Location:
    """The Miami-Dade landmark with its NWS zones, as the replay scenarios assess it."""
    return landmark_location(MIAMI_DADE, name="Miami-Dade County Hall")


def _scenario(
    name: str, inputs: Callable[[], tuple[Snapshot, Location]], rule: RuleId, *, complete: bool
) -> Scenario:
    return Scenario(name, inputs, RULE_LEVELS[rule], rule, complete)


SCENARIOS: Final[tuple[Scenario, ...]] = (
    _scenario(
        "recorded-all-clear",
        lambda: (recorded_maps(), miami_dade()),
        RuleId.ALL_CLEAR,
        complete=True,
    ),
    _scenario(
        "recorded-development-region",
        lambda: (recorded_maps(), development_region_location()),
        RuleId.DEVELOPMENT_REGION,
        complete=True,
    ),
    _scenario(
        "issue-10-rip-current-covers-and-sets-no-level",
        lambda: (with_alerts([rip_current()]), miami_dade()),
        RuleId.ALL_CLEAR,
        complete=True,
    ),
    _scenario(
        "issue-10-county-statement-is-context",
        lambda: (with_alerts([county_statement()]), miami_dade()),
        RuleId.ALL_CLEAR,
        complete=True,
    ),
    _scenario(
        "issue-10-rip-current-as-hurricane-warning",
        lambda: (with_alerts([as_hurricane_warning(rip_current())]), miami_dade()),
        RuleId.HURRICANE_WARNING,
        complete=True,
    ),
    _scenario(
        "issue-10-county-statement-as-hurricane-warning",
        lambda: (with_alerts([as_hurricane_warning(county_statement())]), miami_dade()),
        RuleId.ALL_CLEAR,
        complete=True,
    ),
    _scenario(
        "evacuation-toggle-on",
        lambda: (recorded_maps(), miami_dade(evacuation=True)),
        RuleId.EVACUATION_ORDER,
        complete=True,
    ),
    _scenario(
        "replay-irma-036-miami-dade",
        lambda: (replay(IRMA, "36"), replay_miami_dade()),
        RuleId.HURRICANE_WARNING,
        complete=False,
    ),
    _scenario(
        "replay-irma-034-miami-dade",
        lambda: (replay(IRMA, "34"), replay_miami_dade()),
        RuleId.HURRICANE_WATCH,
        complete=False,
    ),
    _scenario(
        "replay-irma-022-miami-dade",
        lambda: (replay(IRMA, "22"), replay_miami_dade()),
        RuleId.HURRICANE_CONE,
        complete=False,
    ),
    _scenario(
        "replay-dorian-030-nassau",
        lambda: (replay(DORIAN, "30"), nassau()),
        RuleId.HURRICANE_WARNING,
        complete=False,
    ),
    _scenario(
        "replay-dorian-032-miami-dade",
        lambda: (replay(DORIAN, "32"), replay_miami_dade()),
        RuleId.HURRICANE_WIND_PROBABILITY,
        complete=False,
    ),
    _scenario(
        "partial-alerts-failed",
        lambda: (alerts_failed(), miami_dade()),
        RuleId.ALL_CLEAR,
        complete=False,
    ),
)
"""Every named scenario, in the order the tests report them."""


def scenario(name: str) -> Scenario:
    """Return the scenario of a name."""
    return next(item for item in SCENARIOS if item.name == name)
