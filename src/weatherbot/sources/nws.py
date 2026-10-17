# src/weatherbot/sources/nws.py
"""The NWS API clients: points, merged alerts, and zones (register ``nws-*`` sources).

``lookup_point`` resolves a location through ``/points`` to its forecast zone, county,
office, and time zone, and turns the documented 404 ``InvalidPoint`` problem into an
``OutsideNwsCoverage`` result: the location is outside NWS coverage. ``fetch_alerts`` asks
for the active alerts at the location's point, for its county, and for its forecast zone,
and merges the answers by alert id; each alert keeps ``found_by`` (the queries that
returned it), its affected zones, and both geocode lists, the inputs issue #10's rule
needs in Phase 3. Nothing is filtered by zone here. ``fetch_zone`` reads a zone's metadata
and shape with a conditional request, because zones change rarely.

A location's coordinates appear only in the ``/points`` path and the alerts ``point``
parameter, written by ``format_point``, the only function that writes a coordinate into a
URL. Every request goes to ``api.weather.gov`` through the run's one fetcher, which paces
that host 1.2 seconds apart for these clients and the text-product client alike.
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Final, Literal
from urllib.parse import urlsplit

from weatherbot.models import (
    WGS84,
    AlertCategory,
    AlertCertainty,
    AlertMessageType,
    AlertQuery,
    AlertSeverity,
    AlertStatus,
    AlertUrgency,
    Geometry,
    Location,
    NwsAlert,
    NwsCoverage,
    NwsZone,
    Provenance,
    SourceId,
)
from weatherbot.sources.drift import warn_drift
from weatherbot.sources.errors import DocumentedProblem, SourceHttpError, SourceSchemaError
from weatherbot.sources.fields import Fields, as_mapping, as_sequence, model_errors, parse_document
from weatherbot.sources.http import Fetcher, FetchResult, SourceResult

POINTS: Final[SourceId] = "nws-points"
ALERTS_POINT: Final[SourceId] = "nws-alerts-point"
ALERTS_ZONE: Final[SourceId] = "nws-alerts-zone"
ZONES: Final[SourceId] = "nws-zones"
API_ROOT: Final = "https://api.weather.gov"

POINT_DECIMALS: Final = 4
"""The precision the API serves a point at (the register's "Points", 2026-10-17)."""
_QUANTUM: Final = Decimal(1).scaleb(-POINT_DECIMALS)

INVALID_POINT: Final = "https://api.weather.gov/problems/InvalidPoint"
"""The problem ``type`` of a ``/points`` request outside NWS coverage."""
HTTP_NOT_FOUND: Final = 404
HTTP_BAD_REQUEST: Final = 400

_RELATIVE_FIELDS: Final = frozenset({"city", "state"})
POINT_FIELDS_READ: Final = frozenset(
    {"forecastZone", "county", "cwa", "timeZone"}
    | {f"relativeLocation.properties.{name}" for name in _RELATIVE_FIELDS}
)
"""The ``/points`` properties the parser reads: the register's "Fields v2 uses"."""
_POINT_TOP: Final = frozenset({"forecastZone", "county", "cwa", "timeZone", "relativeLocation"})

_GEOCODE_FIELDS: Final = frozenset({"SAME", "UGC"})
_PARAMETER_FIELDS: Final = frozenset({"VTEC", "NWSheadline"})
_ALERT_TOP: Final = frozenset(
    {
        "id",
        "event",
        "headline",
        "severity",
        "certainty",
        "urgency",
        "status",
        "messageType",
        "category",
        "sent",
        "effective",
        "onset",
        "expires",
        "ends",
        "areaDesc",
        "affectedZones",
        "senderName",
        "references",
        "description",
        "instruction",
    }
)
ALERT_FIELDS_READ: Final = frozenset(
    _ALERT_TOP
    | {f"geocode.{name}" for name in _GEOCODE_FIELDS}
    | {f"parameters.{name}" for name in _PARAMETER_FIELDS}
)
"""The alert properties the parser reads, nested members as ``object.member``."""
OPTIONAL_ALERT_FIELDS: Final = frozenset(f"parameters.{name}" for name in _PARAMETER_FIELDS)
"""Read when present: a product without VTEC or a headline omits the parameter."""
_REFERENCE_FIELDS: Final = frozenset({"identifier"})

ZONE_FIELDS_READ: Final = frozenset(
    {"id", "type", "name", "state", "cwa", "timeZone", "effectiveDate"}
)
"""The zone properties the parser reads; the geometry is read as well."""
type ZoneKind = Literal["forecast", "county", "fire"]
ZONE_KINDS: Final[tuple[ZoneKind, ...]] = ("forecast", "county", "fire")
MAX_ZONE_BYTES: Final = 4 * 1024 * 1024
"""Over five times the largest recorded zone (784,207 bytes, ``county/FLC086``)."""

_ZONE_ID_LENGTH: Final = 6


def format_point(lat: float, lon: float) -> str:
    """Write a point as ``lat,lon`` with four decimals: the only writer of a URL coordinate.

    The API serves points at four decimals and redirects a finer request
    (``AdjustPointPrecision``), which the clients refuse. Each value is rounded half to
    even on its shortest decimal form, so ``format_point`` never adds a binary artefact.

    Args:
        lat: Degrees north, -90 to 90.
        lon: Degrees east, -180 to 180.

    Returns:
        For example ``25.7757,-80.1966`` for the Miami-Dade landmark.

    Raises:
        ValueError: A value is not finite or is out of range; the message never repeats it.
    """
    return f"{_degrees(lat, 90)},{_degrees(lon, 180)}"


def _degrees(value: float, limit: int) -> str:
    number = Decimal(repr(float(value)))
    if not number.is_finite() or abs(number) > limit:
        message = "a coordinate is not finite or is out of range"
        raise ValueError(message)
    rounded = number.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)
    return f"{rounded.copy_abs() if rounded.is_zero() else rounded:f}"


def points_url(lat: float, lon: float) -> str:
    """Return the ``/points`` URL of a point.

    Args:
        lat: Degrees north.
        lon: Degrees east.

    Returns:
        The URL.
    """
    return f"{API_ROOT}/points/{format_point(lat, lon)}"


def point_alerts_url(lat: float, lon: float) -> str:
    """Return the active-alerts URL of a point.

    Args:
        lat: Degrees north.
        lon: Degrees east.

    Returns:
        The URL.
    """
    return f"{API_ROOT}/alerts/active?point={format_point(lat, lon)}"


def zone_alerts_url(zone_id: str) -> str:
    """Return the active-alerts URL of a zone.

    Args:
        zone_id: A zone id, such as ``FLC086``.

    Returns:
        The URL.

    Raises:
        ValueError: The id is not an NWS zone id.
    """
    return f"{API_ROOT}/alerts/active/zone/{_zone_id(zone_id)}"


def zone_url(kind: ZoneKind, zone_id: str) -> str:
    """Return a zone's URL.

    Args:
        kind: ``forecast``, ``county``, or ``fire``.
        zone_id: A zone id, such as ``FLZ173``.

    Returns:
        The URL.

    Raises:
        ValueError: The kind or the id is not one the API serves.
    """
    if kind not in ZONE_KINDS:
        message = f"an NWS zone kind is one of {', '.join(ZONE_KINDS)}"
        raise ValueError(message)
    return f"{API_ROOT}/zones/{kind}/{_zone_id(zone_id)}"


def _zone_id(zone_id: str) -> str:
    if not _is_zone_id(zone_id):
        message = "an NWS zone id is two letters, C or Z, and three digits"
        raise ValueError(message)
    return zone_id


def _is_zone_id(text: str) -> bool:
    return (
        len(text) == _ZONE_ID_LENGTH
        and text[:2].isascii()
        and text[:2].isalpha()
        and text[:2].isupper()
        and text[2] in "CZ"
        and text[3:].isascii()
        and text[3:].isdigit()
    )


@dataclass(frozen=True)
class OutsideNwsCoverage:
    """The ``/points`` answer for a location the NWS does not cover: no zones, no alerts.

    Such a location's official watches and warnings come from NHC's breakpoint segments.
    """

    status: int
    problem_type: str
    title: str | None


def _properties(body: bytes, source_id: SourceId, what: str) -> Mapping[str, object]:
    document = as_mapping(parse_document(body, source_id, what), source_id, what)
    return as_mapping(document.get("properties"), source_id, f"{what}'s properties")


def _required_child(fields: Fields, name: str, declared: Collection[str]) -> Fields:
    child = fields.child(name, declared)
    if child is None:
        message = f"{fields.where}: {name!r} is missing"
        raise SourceSchemaError(fields.source_id, message)
    return child


def _zone_of(fields: Fields, name: str) -> str:
    """Return the zone id a zone URL names: its last path segment."""
    segment = urlsplit(fields.text(name)).path.rstrip("/").rsplit("/", 1)[-1]
    if not _is_zone_id(segment):
        message = f"{fields.where}: {name!r} does not name an NWS zone"
        raise SourceSchemaError(fields.source_id, message)
    return segment


def parse_point(body: bytes, source_id: SourceId = POINTS) -> NwsCoverage:
    """Parse a ``/points`` answer into the location's ``NwsCoverage``.

    Args:
        body: The payload.
        source_id: The register id, for errors.

    Returns:
        The forecast zone and county (each URL's last path segment), the office, the time
        zone, and ``relativeLocation``'s city and state.

    Raises:
        SourceSchemaError: A field the register lists is missing or malformed.
    """
    what = "the points answer"
    fields = Fields(_properties(body, source_id, what), _POINT_TOP, source_id=source_id, where=what)
    relative = _required_child(
        _required_child(fields, "relativeLocation", {"properties"}), "properties", _RELATIVE_FIELDS
    )
    with model_errors(source_id, what):
        return NwsCoverage(
            forecast_zone=_zone_of(fields, "forecastZone"),
            county_zone=_zone_of(fields, "county"),
            cwa=fields.text("cwa"),
            time_zone=fields.text("timeZone"),
            city=relative.text("city"),
            state=relative.text("state"),
        )


async def lookup_point(
    fetcher: Fetcher, lat: float, lon: float
) -> SourceResult[NwsCoverage | OutsideNwsCoverage]:
    """Resolve a point to what the NWS says covers it.

    Args:
        fetcher: The run's fetcher.
        lat: Degrees north.
        lon: Degrees east.

    Returns:
        The coverage and the answer, or ``OutsideNwsCoverage`` (with no answer kept) for
        the documented 404 ``InvalidPoint`` problem.

    Raises:
        SourceHttpError: Any other problem, or an undeclared status.
    """
    try:
        result = await fetcher.get(points_url(lat, lon), source_id=POINTS, problems=(404,))
    except DocumentedProblem as problem:
        if problem.status == HTTP_NOT_FOUND and problem.problem_type == INVALID_POINT:
            outside = OutsideNwsCoverage(problem.status, INVALID_POINT, problem.title)
            return SourceResult(outside, ())
        raise SourceHttpError(POINTS, str(problem), status=problem.status) from None
    return SourceResult(parse_point(result.body), (result,))


def _instant(fields: Fields, name: str) -> datetime | None:
    text = fields.optional_text(name)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        message = f"{fields.where}: {name!r} is not an ISO 8601 instant"
        raise SourceSchemaError(fields.source_id, message) from None


def _required_instant(fields: Fields, name: str) -> datetime:
    value = _instant(fields, name)
    if value is None:
        message = f"{fields.where}: {name!r} is null"
        raise SourceSchemaError(fields.source_id, message)
    return value


def _references(fields: Fields) -> tuple[str, ...]:
    """Return the ids of the alerts an alert updates (each reference's ``identifier``)."""
    items = as_sequence(fields.raw("references"), fields.source_id, f"{fields.where}.references")
    identifiers: list[str] = []
    for index, item in enumerate(items):
        where = f"{fields.where}.references[{index}]"
        reference = Fields(
            as_mapping(item, fields.source_id, where),
            _REFERENCE_FIELDS,
            source_id=fields.source_id,
            where=where,
        )
        identifiers.append(reference.text("identifier"))
    return tuple(identifiers)


def _affected_zones(fields: Fields) -> tuple[str, ...]:
    zones: list[str] = []
    for url in fields.texts("affectedZones"):
        segment = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
        if not _is_zone_id(segment):
            message = f"{fields.where}: 'affectedZones' holds a URL that names no NWS zone"
            raise SourceSchemaError(fields.source_id, message)
        zones.append(segment)
    return tuple(zones)


def _geometry(feature: Mapping[str, object], source_id: SourceId, what: str) -> Geometry | None:
    value = feature.get("geometry")
    if value is None:
        return None
    with model_errors(source_id, f"{what}'s geometry"):
        return Geometry.from_geojson(as_mapping(value, source_id, f"{what}'s geometry"), WGS84)


def parse_alert(feature: Mapping[str, object], query: AlertQuery) -> NwsAlert:
    """Parse one alert feature, found by one query.

    Args:
        feature: The GeoJSON feature.
        query: The query whose answer held it.

    Returns:
        The alert, with ``found_by`` holding that query alone.

    Raises:
        SourceSchemaError: A field the register lists is missing or malformed.
    """
    source = query.provenance.source_id
    what = "an alert"
    properties = as_mapping(feature.get("properties"), source, f"{what}'s properties")
    fields = Fields(properties, _ALERT_TOP, source_id=source, where=what)
    what = f"alert {fields.text('id')}"
    fields.where = what
    geocode = _required_child(fields, "geocode", _GEOCODE_FIELDS)
    parameters = _required_child(fields, "parameters", _PARAMETER_FIELDS)

    def listed(name: str) -> tuple[str, ...]:
        return parameters.texts(name) if parameters.has(name) else ()

    with model_errors(source, what):
        return NwsAlert(
            id=fields.text("id"),
            event=fields.text("event"),
            headline=fields.optional_text("headline"),
            severity=AlertSeverity.parse(fields.text("severity")),
            certainty=AlertCertainty.parse(fields.text("certainty")),
            urgency=AlertUrgency.parse(fields.text("urgency")),
            status=AlertStatus.parse(fields.text("status")),
            message_type=AlertMessageType.parse(fields.text("messageType")),
            category=AlertCategory.parse(fields.text("category")),
            sent=_required_instant(fields, "sent"),
            effective=_required_instant(fields, "effective"),
            onset=_instant(fields, "onset"),
            expires=_required_instant(fields, "expires"),
            ends=_instant(fields, "ends"),
            area_desc=fields.text("areaDesc"),
            sender_name=fields.text("senderName"),
            references=_references(fields),
            vtec=listed("VTEC"),
            nws_headline=listed("NWSheadline"),
            description=fields.optional_text("description"),
            instruction=fields.optional_text("instruction"),
            affected_zone_ids=_affected_zones(fields),
            geocode_same=geocode.texts("SAME"),
            geocode_ugc=geocode.texts("UGC"),
            geometry=_geometry(feature, source, what),
            found_by=(query,),
        )


def parse_alerts(body: bytes, query: AlertQuery) -> tuple[NwsAlert, ...]:
    """Parse an active-alerts answer: a FeatureCollection, possibly empty.

    Args:
        body: The payload.
        query: The query it answered, with the answer's provenance.

    Returns:
        The alerts, in the answer's order.

    Raises:
        SourceSchemaError: The answer is not a FeatureCollection, or an alert is malformed.
    """
    source = query.provenance.source_id
    what = "the alerts answer"
    document = as_mapping(parse_document(body, source, what), source, what)
    features = as_sequence(document.get("features"), source, f"{what}'s features")
    return tuple(
        parse_alert(as_mapping(feature, source, f"{what} feature {index}"), query)
        for index, feature in enumerate(features)
    )


def merge_alerts(answers: Sequence[Sequence[NwsAlert]]) -> tuple[NwsAlert, ...]:
    """Merge the answers of several queries into one alert per id.

    Args:
        answers: Each query's alerts, in query order.

    Returns:
        One alert per id, in order of first appearance, each with ``found_by`` listing
        every query that returned it in query order. An alert whose copies disagree beyond
        ``found_by`` keeps the first copy and is logged as Source drift.
    """
    merged: dict[str, NwsAlert] = {}
    for alerts in answers:
        for alert in alerts:
            kept = merged.get(alert.id)
            if kept is None:
                merged[alert.id] = alert
                continue
            if kept.model_copy(update={"found_by": alert.found_by}) != alert:
                warn_drift(
                    alert.found_by[0].provenance.source_id,
                    f"alert {alert.id} differs between the queries that returned it; "
                    "the first copy is kept",
                )
            merged[alert.id] = kept.model_copy(update={"found_by": kept.found_by + alert.found_by})
    return tuple(merged.values())


async def _alerts(
    fetcher: Fetcher, url: str, source_id: SourceId, zone_id: str | None
) -> tuple[tuple[NwsAlert, ...], FetchResult]:
    problems = (HTTP_BAD_REQUEST,) if zone_id is None else ()
    result = await fetcher.get(url, source_id=source_id, problems=problems)
    query = AlertQuery(
        kind="point" if zone_id is None else "zone",
        zone_id=zone_id,
        provenance=result.provenance(),
    )
    return parse_alerts(result.body, query), result


async def fetch_alerts(fetcher: Fetcher, location: Location) -> SourceResult[tuple[NwsAlert, ...]]:
    """Fetch the active alerts at a location's point, county, and forecast zone, merged.

    The three requests leave one after another (the fetcher spaces them 1.2 seconds
    apart). Nothing is filtered by zone: whether a county alert outside the location's
    forecast zone applies is issue #10's rule, which Phase 3 decides.

    Args:
        fetcher: The run's fetcher.
        location: The location; one outside NWS coverage (``nws`` is ``None``) makes no
            request.

    Returns:
        The merged alerts and every answer.

    Raises:
        DocumentedProblem: The point query's documented 400 (``InvalidParameter``, out of
            bounds).
    """
    coverage = location.nws
    if coverage is None:
        return SourceResult((), ())
    point = location.point
    requests: list[tuple[str, SourceId, str | None]] = [
        (point_alerts_url(point.latitude, point.longitude), ALERTS_POINT, None),
        (zone_alerts_url(coverage.county_zone), ALERTS_ZONE, coverage.county_zone),
        (zone_alerts_url(coverage.forecast_zone), ALERTS_ZONE, coverage.forecast_zone),
    ]
    answers: list[tuple[NwsAlert, ...]] = []
    responses: list[FetchResult] = []
    for url, source_id, zone_id in requests:
        alerts, result = await _alerts(fetcher, url, source_id, zone_id)
        answers.append(alerts)
        responses.append(result)
    return SourceResult(merge_alerts(answers), tuple(responses))


def parse_zone(body: bytes, provenance: Provenance, *, zone_id: str) -> NwsZone:
    """Parse a zone answer into an ``NwsZone``.

    Args:
        body: The payload.
        provenance: The answer's provenance.
        zone_id: The zone id that was requested; the answer must name it.

    Returns:
        The zone, its shape labelled EPSG:4326 as the API's GeoJSON states.

    Raises:
        SourceSchemaError: A field is missing, the shape is absent, or the answer names
            another zone.
    """
    source = provenance.source_id
    what = f"zone {zone_id}"
    document = as_mapping(parse_document(body, source, what), source, what)
    properties = as_mapping(document.get("properties"), source, f"{what}'s properties")
    fields = Fields(properties, ZONE_FIELDS_READ, source_id=source, where=what)
    if fields.text("id") != zone_id:
        raise SourceSchemaError(source, f"{what}: the answer names another zone")
    geometry = _geometry(document, source, what)
    if geometry is None:
        raise SourceSchemaError(source, f"{what}: the answer has no geometry")
    with model_errors(source, what):
        return NwsZone(
            id=zone_id,
            type=fields.text("type"),
            name=fields.text("name"),
            state=fields.text("state"),
            cwa=fields.texts("cwa"),
            time_zone=fields.texts("timeZone"),
            effective_date=_required_instant(fields, "effectiveDate"),
            geometry=geometry,
            provenance=provenance,
        )


async def fetch_zone(fetcher: Fetcher, kind: ZoneKind, zone_id: str) -> SourceResult[NwsZone]:
    """Fetch a zone's metadata and shape, conditionally once its validators are stored.

    Args:
        fetcher: The run's fetcher, whose validator store makes a repeat request
            conditional; a 304 reuses the stored body.
        kind: ``forecast``, ``county``, or ``fire``.
        zone_id: The zone id.

    Returns:
        The zone and its answer.
    """
    result = await fetcher.get(zone_url(kind, zone_id), source_id=ZONES, max_bytes=MAX_ZONE_BYTES)
    zone = parse_zone(result.body, result.provenance(), zone_id=zone_id)
    return SourceResult(zone, (result,))
