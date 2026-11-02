# src/weatherbot/services/ai/context.py
"""What a request may say about a location: the privacy-reduced context, built from models.

This module is the only builder of what leaves the machine. ``briefing_context`` and
``change_context`` take the domain models (an assessment, its changes, its snapshot),
never rows, so a replay assessment, which is never stored, is briefed the same way. They
keep structured fields only:

- No engine-written sentence: an evidence ``detail``, an official product's ``reason``, a
  change's ``detail``, and an unavailable input's ``reason`` print a whole-kilometre
  distance and the minute of closest approach, which with the public forecast track would
  pin a home.
- A storm's distance is a band (``distance_band``), its bearing one of 8 compass points
  (``compass8``), and every instant, the closest approach included, is rounded to the
  hour (``to_hour``), as is the lead time.
- No coordinate of a location at any precision, no polygon or other geometry, no URL, no
  path, and no setting but the ladder's thresholds, which the frozen prompt carries. A
  source reaches the model as a key (``S1``, ``S2``, ...) with its product's code,
  issuer, advisory, and issuance; the server maps the key back to the record.

The NOAA texts are each storm threat's TCP, the TWO of every basin the snapshot holds,
and the covering alerts' headline, description, and instruction. Each loses its URLs to
"[link removed]" (a scheme, ``www.``, or a bare host with a path, such as
``hurricanes.gov/graphics_ep5.shtml``), is capped at 12,000 characters (marked when cut),
and is rendered by ``render_noaa`` in a ``<noaa_product>`` block whose ``&``, ``<``, and
``>`` are escaped, so no text can close it. The storm positions and public distances a
product quotes stay: they are public. ``render_context`` writes the context as JSON whose
``<``, ``>``, and ``&`` are escaped too, then the blocks; a context over 60,000 characters
raises ``ContextTooLarge``, which the caller maps to ``too_large``.

The chat's tools (``tools.py``) build their results from the same records, with
``SourceKeys``, ``level_ref``, ``threat_ref``, ``change_ref``, ``text_key``, ``noaa_text``,
and ``escaped_json``, so a tool says no more than a briefing's context does.

The module is pure: it imports the models, pydantic, and the standard library only, and
reads no clock, file, database, or network.
"""

import html
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Annotated, Final, Literal

from pydantic import AfterValidator, Field, TypeAdapter

from weatherbot.models import (
    RULE_TRIGGERS,
    AdvisoryNumber,
    AlertLevel,
    ArrivalKind,
    ArrivalOutcome,
    ArrivalReading,
    Assessment,
    ChangeEvent,
    ChangeKind,
    Citation,
    DomainModel,
    Evidence,
    LocationWindProbability,
    MissingInput,
    NwsAlert,
    OfficialProduct,
    Snapshot,
    SourceId,
    StormThreat,
    TextProduct,
    UtcDatetime,
)

NOAA_TEXT_LIMIT: Final = 12_000
CONTEXT_LIMIT: Final = 60_000
CUT_MARK: Final = "\n[cut: the rest of this product is not included]"
LINK_REMOVED: Final = "[link removed]"
URL_PATTERN: Final = re.compile(
    r"\b[a-z][a-z0-9+.\-]*://\S+"  # a scheme
    r"|\bwww\.\S+"  # www.
    r"|\b(?:[a-z0-9\-]+\.)+[a-z]{2,}/\S*",  # a bare host with a path
    re.IGNORECASE,
)
"""A URL: a scheme, ``www.``, or a bare host followed by a path."""
DASH: Final = "\N{EN DASH}"
DISTANCE_BANDS: Final[tuple[tuple[float, str], ...]] = (
    (50.0, "within 50 km (30 mi)"),
    (100.0, f"50{DASH}100 km (30{DASH}60 mi)"),
    (200.0, f"100{DASH}200 km (60{DASH}125 mi)"),
    (400.0, f"200{DASH}400 km (125{DASH}250 mi)"),
    (800.0, f"400{DASH}800 km (250{DASH}500 mi)"),
)
"""Each band's upper bound (exclusive) and its label (ranges written with an en dash); a
bound belongs to the band above."""
BEYOND_BANDS: Final = "beyond 800 km (500 mi)"
COMPASS_POINTS: Final = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
_HALF_HOUR: Final = timedelta(minutes=30)
_PRODUCT_TITLES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "nws_alert": "NWS alert",
        "watch_warning_segment": "NHC watch-warning segment",
        "cone": "NHC forecast cone",
        "wind_probability": "NHC wind-speed probabilities",
        "development_region": "NHC outlook development region",
    }
)
_ARRIVAL_TITLES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "earliest_reasonable": "NHC earliest-reasonable arrival time of tropical-storm winds",
        "most_likely": "NHC most-likely arrival time of tropical-storm winds",
        "track": "NHC forecast track points",
    }
)
_WIND_BANDS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "below_every_band": "below every band",
        "outside_coverage": "outside the product's coverage, so it says nothing here",
    }
)


class ContextTooLarge(ValueError):  # noqa: N818 - the caller's too_large state, not a fault
    """A rendered context past ``CONTEXT_LIMIT`` characters; the message is fixed text."""

    def __init__(self) -> None:
        """Create the error with its fixed message."""
        super().__init__(f"the context passes {CONTEXT_LIMIT} characters")


def _on_the_hour(value: datetime) -> datetime:
    if value.minute or value.second or value.microsecond:
        message = "a context instant is rounded to the hour"
        raise ValueError(message)
    return value


type Hour = Annotated[UtcDatetime, AfterValidator(_on_the_hour)]
"""A UTC instant rounded to the hour: the only precision a context holds."""


def to_hour(instant: datetime) -> datetime:
    """Round an instant to the nearest hour, in UTC; half an hour rounds up.

    Args:
        instant: An aware instant.

    Returns:
        The hour.
    """
    utc = instant.astimezone(UTC)
    floor = utc.replace(minute=0, second=0, microsecond=0)
    return floor + timedelta(hours=1) if utc - floor >= _HALF_HOUR else floor


def whole_hours(hours: float) -> int:
    """Round a lead time to whole hours; half an hour rounds up.

    Args:
        hours: A duration in hours, at least 0.

    Returns:
        The whole hours.
    """
    return math.floor(hours + 0.5)


def distance_band(km: float) -> str:
    """Say a distance as one of six bands, each with its mile label.

    Args:
        km: A distance in kilometres, at least 0.

    Returns:
        "within 50 km (30 mi)", "50-100 km (30-60 mi)", "100-200 km (60-125 mi)",
        "200-400 km (125-250 mi)", "400-800 km (250-500 mi)", or "beyond 800 km (500 mi)",
        each range written with an en dash; a bound belongs to the band above it.

    Raises:
        ValueError: The distance is negative.
    """
    if km < 0:
        message = "a distance is at least 0"
        raise ValueError(message)
    for upper, label in DISTANCE_BANDS:
        if km < upper:
            return label
    return BEYOND_BANDS


def compass8(degrees: float) -> str:
    """Say a bearing as one of 8 compass points, each 45 degrees wide.

    Args:
        degrees: A bearing in degrees clockwise from true north.

    Returns:
        N, NE, E, SE, S, SW, W, or NW; a sector's lower edge belongs to it (22.5 is NE).
    """
    return COMPASS_POINTS[math.floor((degrees % 360.0 + 22.5) / 45.0) % 8]


def remove_links(text: str) -> str:
    """Replace every URL in a text with "[link removed]".

    Args:
        text: A product's text.

    Returns:
        The text with each URL (a scheme, ``www.``, or a bare host with a path) replaced.
    """
    return URL_PATTERN.sub(LINK_REMOVED, text)


def clean_noaa(text: str) -> str:
    """Prepare a NOAA text for a context: links removed, then capped and marked when cut.

    Args:
        text: The product's text as received.

    Returns:
        The text without links, at most ``NOAA_TEXT_LIMIT`` characters plus the cut mark.
    """
    cleaned = remove_links(text)
    if len(cleaned) > NOAA_TEXT_LIMIT:
        return cleaned[:NOAA_TEXT_LIMIT] + CUT_MARK
    return cleaned


# The context's records ------------------------------------------------------------------


class SourceRef(DomainModel):
    """A source as the model sees it: a key and its product's metadata, never a URL."""

    key: str = Field(pattern=r"^S\d+$")
    source_id: SourceId
    code: str | None = None
    issuer: str | None = None
    advisory: str | None = None
    issued: Hour | None = None
    title: str = Field(min_length=1)


_SOURCE_REFS: Final = TypeAdapter(tuple[SourceRef, ...])


def stored_sources(stored: object) -> tuple[SourceRef, ...]:
    """Read the sources a stored product's content holds back into records.

    Args:
        stored: The content's ``sources``, as stored (JSON values).

    Returns:
        The records; the strict models read instants from JSON text, as stored.
    """
    return _SOURCE_REFS.validate_json(json.dumps(stored))


class NoaaText(DomainModel):
    """A NOAA product's text for a context: its key, code, issuance, and cleaned text."""

    key: str = Field(pattern=r"^S\d+$")
    code: str = Field(min_length=1)
    issued: Hour | None = None
    text: str = Field(repr=False, description="Links removed and capped (clean_noaa).")


class LevelRef(DomainModel):
    """A level as the ladder names it."""

    number: int = Field(ge=1, le=5)
    label: str
    actions: str


class UnavailableRef(DomainModel):
    """An input the rules lacked: its kind and its source."""

    kind: MissingInput
    source_id: SourceId | None = None


class EvidenceRef(DomainModel):
    """One match of the deciding rule, without its distance or its sentence."""

    rule: str
    product: str
    code: str | None = None
    storm: str | None = None
    advisory: str | None = None
    issued: Hour | None = None
    test: str
    chance_pct: int | None = None
    threshold_kt: int | None = None
    source: str | None = None


class OfficialRef(DomainModel):
    """An official product the engine considered, without its distance or its sentence."""

    product: Literal["nws_alert", "watch_warning_segment"]
    code: str
    issuer: str | None = None
    storm: str | None = None
    advisory: str | None = None
    issued: Hour | None = None
    expires: Hour | None = None
    covers: bool
    rule: str | None = None
    source: str


class WindRef(DomainModel):
    """A wind-speed probability at the location: its threshold and band."""

    threshold_kt: int
    band: str
    source: str


class ArrivalRef(DomainModel):
    """When tropical-storm-force winds arrive, as one product says, to the hour."""

    kind: ArrivalKind
    outcome: ArrivalOutcome
    start: Hour | None = None
    end: Hour | None = None
    approach: Hour | None = Field(
        default=None, description="The track's closest approach, for the track fallback."
    )
    source: str | None = None


class ThreatRef(DomainModel):
    """What one storm means for the location, coarsened: a band, a compass point, hours."""

    storm: str
    atcf_id: str
    advisory: str | None = None
    category: int | None = None
    development: str | None = None
    in_cone: bool | None = None
    distance: str | None = Field(default=None, description="From the storm's center: a band.")
    compass_from_storm: str | None = Field(
        default=None, description="The location lies in this direction from the center."
    )
    closest_approach: Hour | None = None
    lead_h: int | None = None
    hurricane_by_approach: bool | None = None
    arrivals: tuple[ArrivalRef, ...]
    sources: tuple[str, ...] = ()


class ChangeRef(DomainModel):
    """One change since the previous assessment, without its sentence."""

    kind: ChangeKind
    previous_level: int | None = None
    level: int | None = None
    direction: str | None = None
    rule: str | None = None
    storm: str | None = None
    previous_advisory: str | None = None
    advisory: str | None = None
    in_cone: bool | None = None
    previous_codes: tuple[str, ...] = ()
    codes: tuple[str, ...] = ()


class BriefingContext(DomainModel):
    """Everything a briefing request says about one location's latest assessment."""

    location: str
    as_of: Hour
    level: LevelRef
    rule: str
    trigger: str
    complete: bool
    unavailable: tuple[UnavailableRef, ...]
    evidence: tuple[EvidenceRef, ...]
    official: tuple[OfficialRef, ...]
    wind_probabilities: tuple[WindRef, ...]
    threats: tuple[ThreatRef, ...]
    changes: tuple[ChangeRef, ...]
    stale_sources: tuple[str, ...]
    sources: tuple[SourceRef, ...]
    noaa: tuple[NoaaText, ...] = Field(description="Rendered as blocks, after the JSON.")


class ChangeContext(DomainModel):
    """Everything a change summary request says: the two levels, the changes, the evidence."""

    location: str
    as_of: Hour
    previous_level: LevelRef
    level: LevelRef
    rule: str
    changes: tuple[ChangeRef, ...]
    evidence: tuple[EvidenceRef, ...]
    sources: tuple[SourceRef, ...]

    @property
    def noaa(self) -> tuple[NoaaText, ...]:
        """A change summary carries no NOAA text."""
        return ()


# The builders ---------------------------------------------------------------------------


def _advisory(value: AdvisoryNumber | None) -> str | None:
    return str(value) if value is not None else None


def _hour(instant: datetime | None) -> datetime | None:
    return to_hour(instant) if instant is not None else None


def _issuer(source_id: str, issuer: str | None = None) -> str | None:
    if issuer:
        return issuer
    if source_id.startswith("nhc-"):
        return "NHC"
    if source_id.startswith("nws-"):
        return "NWS"
    return None


def _title(label: str, code: str | None, storm: str | None, advisory: str | None) -> str:
    parts = [f"{label}: {code}" if code else label]
    if storm:
        parts.append(storm if advisory is None else f"{storm} advisory {advisory}")
    elif advisory:
        parts.append(f"advisory {advisory}")
    return ", ".join(parts)


class SourceKeys:
    """Hands out source keys in order of first use, one per product, for one request or result."""

    def __init__(self) -> None:
        """Start with no key handed out."""
        self._keys: dict[tuple[object, ...], str] = {}
        self.refs: list[SourceRef] = []

    def key(  # noqa: PLR0913 - a source's identity, then its metadata
        self,
        identity: tuple[object, ...],
        *,
        source_id: SourceId,
        title: str,
        code: str | None = None,
        issuer: str | None = None,
        advisory: str | None = None,
        issued: datetime | None = None,
    ) -> str:
        """Return a product's key, handing out the next one on its first use.

        Args:
            identity: What makes the product one source.
            source_id: Its register source.
            title: Its title, as a page shows it.
            code: Its product code.
            issuer: Its issuing office; read from the source when omitted.
            advisory: Its advisory, as NHC spells it.
            issued: Its issuance, rounded to the hour.

        Returns:
            The key: ``S1``, ``S2``, ...
        """
        found = self._keys.get(identity)
        if found is not None:
            return found
        key = f"S{len(self.refs) + 1}"
        self._keys[identity] = key
        self.refs.append(
            SourceRef(
                key=key,
                source_id=source_id,
                code=code,
                issuer=_issuer(source_id, issuer),
                advisory=advisory,
                issued=_hour(issued),
                title=title,
            )
        )
        return key

    def cited(  # noqa: PLR0913 - a citation, then what it cites
        self,
        citation: Citation,
        *,
        label: str,
        code: str | None = None,
        storm: str | None = None,
        atcf_id: str | None = None,
        advisory: AdvisoryNumber | None = None,
        issued: datetime | None = None,
        issuer: str | None = None,
    ) -> str:
        """Return the key of the product a citation names.

        Args:
            citation: The citation; its URL is never kept.
            label: The product's kind, as a title begins.
            code: Its product code.
            storm: The storm's name.
            atcf_id: The storm's ATCF id.
            advisory: Its advisory; the citation's when omitted.
            issued: Its issuance; the citation's when omitted.
            issuer: Its issuing office.

        Returns:
            The key.
        """
        spelled = _advisory(advisory or citation.advisory)
        identity = ("cited", citation.source_id, citation.sha256, label, code, atcf_id, spelled)
        return self.key(
            identity,
            source_id=citation.source_id,
            title=_title(label, code, storm, spelled),
            code=code,
            issuer=issuer,
            advisory=spelled,
            issued=issued or citation.issued_at,
        )


def level_ref(level: AlertLevel) -> LevelRef:
    """Name a level as the ladder does.

    Args:
        level: The level.

    Returns:
        Its number, label, and actions.
    """
    return LevelRef(number=int(level), label=level.label, actions=level.actions)


def _evidence(item: Evidence, sources: SourceKeys) -> EvidenceRef:
    source = None
    if item.citation is not None:
        source = sources.cited(
            item.citation,
            label=_PRODUCT_TITLES[item.product],
            code=item.code,
            storm=item.storm_name,
            atcf_id=item.atcf_id,
            advisory=item.advisory,
            issued=item.issued_at,
        )
    return EvidenceRef(
        rule=str(item.rule),
        product=item.product,
        code=item.code,
        storm=item.storm_name,
        advisory=_advisory(item.advisory),
        issued=_hour(item.issued_at),
        test=item.test,
        chance_pct=item.chance_pct,
        threshold_kt=item.threshold_kt,
        source=source,
    )


def _official(product: OfficialProduct, sources: SourceKeys) -> OfficialRef:
    source = sources.cited(
        product.citation,
        label=_PRODUCT_TITLES[product.kind],
        code=product.code,
        storm=product.storm_name,
        atcf_id=product.atcf_id,
        advisory=product.advisory,
        issued=product.issued_at,
        issuer=product.issuer,
    )
    return OfficialRef(
        product=product.kind,
        code=product.code,
        issuer=_issuer(product.citation.source_id, product.issuer),
        storm=product.storm_name,
        advisory=_advisory(product.advisory),
        issued=_hour(product.issued_at),
        expires=_hour(product.expires_at),
        covers=product.covers,
        rule=str(product.rule) if product.rule is not None else None,
        source=source,
    )


def _wind(reading: LocationWindProbability, sources: SourceKeys) -> WindRef:
    code = f"{reading.threshold_kt}-kt"
    source = sources.cited(reading.citation, label=_PRODUCT_TITLES["wind_probability"], code=code)
    band = reading.label if reading.reading == "band" and reading.label else None
    return WindRef(
        threshold_kt=reading.threshold_kt,
        band=band or _WIND_BANDS[reading.reading],
        source=source,
    )


def _arrival(reading: ArrivalReading, threat: StormThreat, sources: SourceKeys) -> ArrivalRef:
    source = None
    if reading.citation is not None:
        label = _ARRIVAL_TITLES["track" if reading.origin == "track" else reading.kind]
        source = sources.cited(
            reading.citation,
            label=label,
            storm=threat.storm_name,
            atcf_id=threat.atcf_id,
            advisory=reading.advisory,
        )
    return ArrivalRef(
        kind=reading.kind,
        outcome=reading.reading,
        start=_hour(reading.start),
        end=_hour(reading.end),
        approach=_hour(reading.approach_at),
        source=source,
    )


def _tcp(threat: StormThreat, snapshot: Snapshot | None) -> TextProduct | None:
    if snapshot is None:
        return None
    found = [
        product
        for product in snapshot.text_products
        if product.code == "TCP" and product.atcf_id == threat.atcf_id
    ]
    return max(found, key=lambda product: product.issued_at) if found else None


def text_key(product: TextProduct, sources: SourceKeys, storm: str | None) -> str:
    """Return the key of a TCP or a TWO.

    Args:
        product: The text product.
        sources: The keys handed out so far.
        storm: A TCP's storm name, for its title.

    Returns:
        The key.
    """
    advisory = _advisory(product.advisory)
    if product.code == "TCP":
        title = _title("NHC public advisory", None, storm, advisory)
    else:
        title = f"NHC tropical weather outlook, basin {product.location}"
    provenance = product.provenance
    identity = ("text", provenance.source_id, provenance.sha256, product.product_id)
    return sources.key(
        identity,
        source_id=provenance.source_id,
        title=title,
        code=product.code,
        issuer=product.issuing_office,
        advisory=advisory,
        issued=product.issued_at,
    )


def noaa_text(key: str, code: str, issued: datetime | None, text: str) -> NoaaText:
    """Prepare a NOAA text for a request: its links removed, capped, its issuance to the hour.

    Args:
        key: Its source key.
        code: Its product code, or an alert's event.
        issued: Its issuance.
        text: The text as received.

    Returns:
        The text, for ``render_noaa``.
    """
    return NoaaText(key=key, code=code, issued=_hour(issued), text=clean_noaa(text))


def threat_ref(
    threat: StormThreat, snapshot: Snapshot | None, sources: SourceKeys, texts: list[NoaaText]
) -> ThreatRef:
    """Coarsen one storm's threat: a band, a compass point, and hours.

    Args:
        threat: The storm's threat to the location.
        snapshot: The snapshot, for the storm's latest TCP; ``None`` adds no text.
        sources: The keys handed out so far.
        texts: Where the TCP's text is appended.

    Returns:
        The threat as a request may say it.
    """
    arrivals = tuple(
        _arrival(reading, threat, sources)
        for reading in (threat.earliest_arrival, threat.most_likely_arrival)
    )
    keys = [arrival.source for arrival in arrivals if arrival.source is not None]
    tcp = _tcp(threat, snapshot)
    if tcp is not None:
        key = text_key(tcp, sources, threat.storm_name)
        keys.insert(0, key)
        texts.append(noaa_text(key, tcp.code, tcp.issued_at, tcp.text))
    return ThreatRef(
        storm=threat.storm_name,
        atcf_id=threat.atcf_id,
        advisory=_advisory(threat.advisory),
        category=threat.category,
        development=threat.development,
        in_cone=threat.in_cone,
        distance=distance_band(threat.distance_km) if threat.distance_km is not None else None,
        compass_from_storm=compass8(threat.bearing_deg) if threat.bearing_deg is not None else None,
        closest_approach=_hour(threat.closest_approach_at),
        lead_h=whole_hours(threat.lead_h) if threat.lead_h is not None else None,
        hurricane_by_approach=threat.hurricane_by_approach,
        arrivals=arrivals,
        sources=tuple(dict.fromkeys(keys)),
    )


def change_ref(event: ChangeEvent) -> ChangeRef:
    """Keep a change's structured fields, without its sentence.

    Args:
        event: The change.

    Returns:
        The change as a request may say it.
    """
    return ChangeRef(
        kind=event.kind,
        previous_level=int(event.previous_level) if event.previous_level is not None else None,
        level=int(event.level) if event.level is not None else None,
        direction=event.direction,
        rule=str(event.rule) if event.rule is not None else None,
        storm=event.storm_name,
        previous_advisory=_advisory(event.previous_advisory),
        advisory=_advisory(event.advisory),
        in_cone=event.in_cone,
        previous_codes=event.previous_codes,
        codes=event.codes,
    )


def _alert_texts(
    assessment: Assessment,
    snapshot: Snapshot | None,
    keys: Mapping[str, str],
) -> Iterable[NoaaText]:
    if snapshot is None:
        return
    alerts: dict[str, NwsAlert] = {
        alert.id: alert for alert in snapshot.alerts.get(assessment.location_name, ())
    }
    for product in assessment.official:
        if product.kind != "nws_alert" or not product.covers or product.alert_id is None:
            continue
        alert = alerts.get(product.alert_id)
        key = keys.get(product.alert_id)
        if alert is None or key is None:
            continue
        parts = (alert.headline, alert.description, alert.instruction)
        text = "\n\n".join(part for part in parts if part)
        if text:
            yield noaa_text(key, alert.event, alert.sent, text)


def briefing_context(
    assessment: Assessment,
    changes: Sequence[ChangeEvent],
    snapshot: Snapshot | None,
    stale: Sequence[str] = (),
) -> BriefingContext:
    """Build a briefing's context from an assessment, its changes, and its snapshot.

    Args:
        assessment: The location's latest assessment, stored or replayed.
        changes: Its changes from the previous assessment.
        snapshot: The snapshot it was assessed from, for the NOAA texts; ``None`` when the
            texts are not at hand (a replay snapshot holds none anyway).
        stale: The names of the sources whose heartbeats are stale.

    Returns:
        The context.

    Raises:
        ContextTooLarge: The rendered context passes ``CONTEXT_LIMIT`` characters.
    """
    sources = SourceKeys()
    evidence = tuple(_evidence(item, sources) for item in assessment.evidence)
    official = tuple(_official(product, sources) for product in assessment.official)
    alert_keys = {
        product.alert_id: ref.source
        for product, ref in zip(assessment.official, official, strict=True)
        if product.alert_id is not None
    }
    winds = tuple(_wind(reading, sources) for reading in assessment.wind_probabilities)
    texts: list[NoaaText] = []
    threats = tuple(threat_ref(threat, snapshot, sources, texts) for threat in assessment.threats)
    if snapshot is not None:
        for product in snapshot.text_products:
            if product.code == "TWO":
                key = text_key(product, sources, None)
                texts.append(noaa_text(key, product.code, product.issued_at, product.text))
    texts.extend(_alert_texts(assessment, snapshot, alert_keys))
    context = BriefingContext(
        location=assessment.location_name,
        as_of=to_hour(assessment.as_of),
        level=level_ref(assessment.level),
        rule=str(assessment.rule),
        trigger=RULE_TRIGGERS[assessment.rule],
        complete=assessment.complete,
        unavailable=tuple(
            UnavailableRef(kind=item.kind, source_id=item.source_id)
            for item in assessment.unavailable
        ),
        evidence=evidence,
        official=official,
        wind_probabilities=winds,
        threats=threats,
        changes=tuple(change_ref(event) for event in changes),
        stale_sources=tuple(stale),
        sources=tuple(sources.refs),
        noaa=tuple(texts),
    )
    render_context(context)
    return context


def previous_level(assessment: Assessment, changes: Sequence[ChangeEvent]) -> AlertLevel:
    """Read the level before an assessment from its changes.

    Args:
        assessment: The assessment.
        changes: Its changes from the previous assessment.

    Returns:
        The previous level a ``level_changed`` event names, or the assessment's own level
        when the level did not change.
    """
    for event in changes:
        if event.kind == "level_changed" and event.previous_level is not None:
            return event.previous_level
    return assessment.level


def change_context(assessment: Assessment, changes: Sequence[ChangeEvent]) -> ChangeContext:
    """Build a change summary's context: the two levels, the changes, and the evidence.

    Args:
        assessment: The new assessment.
        changes: Its changes from the previous assessment.

    Returns:
        The context.

    Raises:
        ContextTooLarge: The rendered context passes ``CONTEXT_LIMIT`` characters.
    """
    sources = SourceKeys()
    evidence = tuple(_evidence(item, sources) for item in assessment.evidence)
    context = ChangeContext(
        location=assessment.location_name,
        as_of=to_hour(assessment.as_of),
        previous_level=level_ref(previous_level(assessment, changes)),
        level=level_ref(assessment.level),
        rule=str(assessment.rule),
        changes=tuple(change_ref(event) for event in changes),
        evidence=evidence,
        sources=tuple(sources.refs),
    )
    render_context(context)
    return context


# Rendering ------------------------------------------------------------------------------


def _attribute(value: str) -> str:
    return html.escape(value, quote=True)


def render_noaa(text: NoaaText) -> str:
    """Render a NOAA text as an escaped ``<noaa_product>`` block, its links removed.

    Args:
        text: The text.

    Returns:
        The block: its ``&``, ``<``, and ``>`` escaped, so nothing in it can close it.
    """
    attributes = f'key="{_attribute(text.key)}" code="{_attribute(text.code)}"'
    if text.issued is not None:
        attributes += f' issued="{text.issued.strftime("%Y-%m-%dT%H:%MZ")}"'
    body = html.escape(remove_links(text.text), quote=False)
    return f"<noaa_product {attributes}>\n{body}\n</noaa_product>"


def escaped_json(document: object) -> str:
    """Write a document as compact JSON whose ``&``, ``<``, and ``>`` are escaped.

    Args:
        document: A JSON value.

    Returns:
        The JSON text; no value in it can open or close a block.
    """
    text = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
    # Valid JSON escapes, so no value can open or close a block.
    return text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def _json_text(context: BriefingContext | ChangeContext) -> str:
    return escaped_json(context.model_dump(mode="json", exclude={"noaa"}, exclude_defaults=True))


def render_context(context: BriefingContext | ChangeContext) -> str:
    """Render a context for the user turn: the JSON document, then each NOAA block.

    Args:
        context: The context.

    Returns:
        The text.

    Raises:
        ContextTooLarge: The text passes ``CONTEXT_LIMIT`` characters.
    """
    parts = [f"<context>\n{_json_text(context)}\n</context>"]
    parts.extend(render_noaa(text) for text in context.noaa)
    rendered = "\n\n".join(parts)
    if len(rendered) > CONTEXT_LIMIT:
        raise ContextTooLarge
    return rendered
