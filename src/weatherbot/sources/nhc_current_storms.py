# src/weatherbot/sources/nhc_current_storms.py
"""The storm roster, ``CurrentStorms.json`` (register source ``nhc-current-storms``).

The roster names the active storms, their map-service slots (``binNumber``), and the
issuance of each product a client reads. Off-season it is ``{"activeStorms": []}``, which
parses to no storms. ``FIELDS_READ`` is the register's "Fields v2 uses" for the roster; the
field-coverage contract test keeps the two equal.
"""

from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Final

from weatherbot.models import (
    AdvisoryNumber,
    Provenance,
    RosterProduct,
    SourceId,
    StormClassification,
    StormSummary,
)
from weatherbot.sources.errors import SourceSchemaError
from weatherbot.sources.fields import (
    Fields,
    as_mapping,
    as_sequence,
    model_errors,
    parse_document,
)
from weatherbot.sources.http import Fetcher, SourceResult

SOURCE: Final[SourceId] = "nhc-current-storms"
ROSTER_URL: Final = "https://www.nhc.noaa.gov/CurrentStorms.json"

_STORM_FIELDS: Final = frozenset(
    {
        "id",
        "binNumber",
        "name",
        "classification",
        "intensity",
        "pressure",
        "latitudeNumeric",
        "longitudeNumeric",
        "movementDir",
        "movementSpeed",
        "lastUpdate",
        "stormSurgeWatchWarningGIS",
        "potentialStormSurgeFloodingGIS",
        "peakSurgeKML",
    }
)
# The product objects the clients read, and the members read in each.
_PRODUCT_FIELDS: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "publicAdvisory": frozenset({"advNum", "issuance"}),
        "trackCone": frozenset({"advNum", "issuance"}),
        "windSpeedProbabilitiesGIS": frozenset({"issuance"}),
        "earliestArrivalTimeTSWindsGIS": frozenset({"advNum", "issuance", "kmzFile"}),
        "mostLikelyTimeTSWindsGIS": frozenset({"advNum", "issuance", "kmzFile"}),
    }
)
FIELDS_READ: Final = frozenset(
    _STORM_FIELDS
    | {f"{product}.{member}" for product, members in _PRODUCT_FIELDS.items() for member in members}
)
"""Every roster field the parser reads, product members as ``object.member``."""


def _instant(fields: Fields, name: str) -> datetime:
    text = fields.text(name)
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        message = f"{fields.where}: {name!r} is not an ISO 8601 instant"
        raise SourceSchemaError(fields.source_id, message) from None


def _product(storm: Fields, name: str) -> RosterProduct | None:
    fields = storm.child(name, _PRODUCT_FIELDS[name])
    if fields is None:
        return None
    members = _PRODUCT_FIELDS[name]
    number = fields.code("advNum") if "advNum" in members else None
    url = fields.text("kmzFile") if "kmzFile" in members else None
    issued_at = _instant(fields, "issuance")
    with model_errors(storm.source_id, f"{storm.where}.{name}"):
        advisory = AdvisoryNumber.parse(number) if number is not None else None
        return RosterProduct(advisory=advisory, issued_at=issued_at, url=url)


def _storm(fields: Fields) -> StormSummary:
    wind_probabilities = fields.child(
        "windSpeedProbabilitiesGIS", _PRODUCT_FIELDS["windSpeedProbabilitiesGIS"]
    )
    public_advisory = _product(fields, "publicAdvisory")
    if public_advisory is None:
        message = f"{fields.where}: 'publicAdvisory' is missing"
        raise SourceSchemaError(fields.source_id, message)
    with model_errors(fields.source_id, fields.where):
        return StormSummary.model_validate(
            {
                "atcf_id": fields.text("id").upper(),
                "slot": fields.text("binNumber"),
                "name": fields.text("name"),
                "classification": StormClassification.parse(fields.text("classification")),
                "intensity_kt": fields.optional_integer("intensity"),
                "pressure_mb": fields.optional_integer("pressure"),
                "latitude": fields.number("latitudeNumeric"),
                "longitude": fields.number("longitudeNumeric"),
                "movement_dir_deg": fields.optional_number("movementDir"),
                "movement_speed_mph": fields.optional_number("movementSpeed"),
                "last_update": _instant(fields, "lastUpdate"),
                "public_advisory": public_advisory,
                "track_cone": _product(fields, "trackCone"),
                "earliest_arrival_kmz": _product(fields, "earliestArrivalTimeTSWindsGIS"),
                "most_likely_arrival_kmz": _product(fields, "mostLikelyTimeTSWindsGIS"),
                "wind_speed_probabilities_issued_at": (
                    _instant(wind_probabilities, "issuance") if wind_probabilities else None
                ),
                "has_storm_surge_watch_warning": (
                    fields.raw("stormSurgeWatchWarningGIS") is not None
                ),
                "has_potential_storm_surge_flooding": (
                    fields.raw("potentialStormSurgeFloodingGIS") is not None
                ),
                "has_peak_surge": fields.raw("peakSurgeKML") is not None,
            }
        )


def parse_current_storms(body: bytes, provenance: Provenance) -> tuple[StormSummary, ...]:
    """Parse ``CurrentStorms.json`` into the active storms.

    Args:
        body: The payload.
        provenance: The answer's provenance; its source id names the errors.

    Returns:
        One ``StormSummary`` per active storm, in the roster's order; none off-season.

    Raises:
        SourceSchemaError: The roster breaks the register's shape or the models' rules.
    """
    source = provenance.source_id
    document = as_mapping(parse_document(body, source, "the roster"), source, "the roster")
    storms = as_sequence(document.get("activeStorms"), source, "activeStorms")
    return tuple(
        _storm(
            Fields(
                as_mapping(storm, source, "an active storm"),
                FIELDS_READ,
                source_id=source,
                where=f"activeStorms[{index}]",
            )
        )
        for index, storm in enumerate(storms)
    )


async def fetch_current_storms(fetcher: Fetcher) -> SourceResult[tuple[StormSummary, ...]]:
    """Fetch and parse the roster, conditionally when the store holds its validators.

    Args:
        fetcher: The run's fetcher.

    Returns:
        The active storms and the answer.
    """
    result = await fetcher.get(ROSTER_URL, source_id=SOURCE)
    return SourceResult(parse_current_storms(result.body, result.provenance()), (result,))
