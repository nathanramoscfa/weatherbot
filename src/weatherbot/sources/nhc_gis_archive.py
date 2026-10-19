# src/weatherbot/sources/nhc_gis_archive.py
"""The replay corpus: the GIS archive's products, as the corpus script converts them.

Register source ``nhc-gis-archive``. ``fetch_replay_corpus.py convert`` turns each
archived shapefile into a gzip-compressed FeatureCollection that keeps the archive's
upper-case attributes and its native geographic CRS (``source_crs``), and lists it in
``corpus-manifest.json`` with its SHA-256, the original archive it came from (its URL and
SHA-256: the bytes NHC served), and the day the originals were recorded. ``parse_manifest``
reads the manifest; the parsers turn one converted file's bytes and its manifest entries
into the records the live map parsers build: ``ConeGeometry``, ``ForecastTrack``,
``TrackPoint``, ``WatchWarningSegment``, ``WindProbabilityProduct``, and the
``ArchiveStorm`` a replay snapshot carries in place of the roster's summary.

A parser checks the bytes against the manifest's size and SHA-256 before reading them,
decompresses and reads JSON under a size bound, and reads a feature's attributes only
through ``FIELDS_READ`` (the register's "Fields v2 uses" for each kind). A record's
provenance names the archive, the original's URL and SHA-256, the recording day at 00:00
UTC as ``fetched_at`` (the manifest records a day, so the instant is day precision), and,
for an advisory product, the advisory's issuance and number. ``ADVDATE`` dates the
advisory through ``parse_nhc_local_time``, ``VALIDTIME`` resolves against it, 9999 is
``None``, a one-vertex watch-warning line stays the Point the converter wrote with its
``geometry_note``, and geometry keeps the collection's native CRS, never relabeled. A
wind-speed-probability file reads its synoptic time from its member name and its bands
from ``PERCENTAGE``; a landmark-window extract records the area it covers.
"""

import hashlib
import re
import zlib
from collections.abc import Collection, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from types import MappingProxyType
from typing import Final, Literal, cast

from weatherbot.models import (
    Advisory,
    AdvisoryNumber,
    ArchiveStorm,
    ConeGeometry,
    Crs,
    ForecastTrack,
    Geometry,
    Provenance,
    SourceId,
    TrackPoint,
    WatchWarningSegment,
    WatchWarningType,
    WindProbabilityBand,
    WindProbabilityProduct,
    parse_nhc_local_time,
    parse_synoptic_time,
    resolve_track_valid_time,
)
from weatherbot.sources.errors import SourceSchemaError
from weatherbot.sources.fields import Fields, as_mapping, as_sequence, model_errors, parse_document

SOURCE: Final[SourceId] = "nhc-gis-archive"
ARRIVALS: Final[SourceId] = "nhc-arrival-times"
MANIFEST_NAME: Final = "corpus-manifest.json"
MANIFEST_SCHEMA: Final = 1
MAX_MANIFEST_BYTES: Final = 16 * 1024 * 1024
MAX_COLLECTION_BYTES: Final = 64 * 1024 * 1024
"""The bound on a converted collection's JSON, decompressed."""

FORECAST_KINDS: Final = ("cone", "track", "points", "watch-warning")
WSP_KINDS: Final = ("wsp-34kt", "wsp-50kt", "wsp-64kt")
ARRIVAL_KINDS: Final = ("toa_earliest_reasonable", "toa_most_likely")
WSP_ARCHIVE: Final = "wsp_120hr5km"
"""The original archive product a wind-speed-probability file is converted from."""

_ADVISORY_FIELDS: Final = frozenset({"BASIN", "STORMNUM", "ADVISNUM", "ADVDATE"})
FIELDS_READ: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "cone": _ADVISORY_FIELDS | {"STORMNAME", "STORMTYPE", "FCSTPRD"},
        "track": _ADVISORY_FIELDS,
        "points": _ADVISORY_FIELDS
        | {
            "TAU",
            "VALIDTIME",
            "FLDATELBL",
            "MAXWIND",
            "GUST",
            "MSLP",
            "TCDIR",
            "TCSPD",
            "TCDVLP",
            "STORMTYPE",
            "SSNUM",
            "DVLBL",
        },
        "watch-warning": _ADVISORY_FIELDS | {"TCWW"},
        "wsp": frozenset({"PERCENTAGE"}),
    }
)
"""The attributes each converted kind's parser reads, by kind (``wsp`` for every threshold)."""

_THRESHOLDS: Final[Mapping[str, Literal[34, 50, 64]]] = MappingProxyType(
    {"34": 34, "50": 50, "64": 64}
)
_WSP_MEMBER: Final = re.compile(r"(?P<stamp>\d{10})_wsp(?P<threshold>34|50|64)knt120hr_5km\.shp")
_ATCF_ID: Final = re.compile(r"(?:AL|EP|CP)\d{6}")
_SHA256: Final = re.compile(r"[0-9a-f]{64}")
_ARCHIVE_STATUS: Final = 200
"""The status the archive answered: the recorder keeps only a 200's bytes."""


@dataclass(frozen=True)
class ArchiveFile:
    """One original archive the manifest pins: the bytes NHC served."""

    file: str
    url: str
    sha256: str
    bytes: int
    storm: str
    advisories: tuple[str, ...]
    product: str
    synoptic_time: str | None


@dataclass(frozen=True)
class ConvertedFile:
    """One file of a corpus directory, traced to its original archive and member."""

    file: str
    source: str
    member: str
    product: str
    sha256: str
    bytes: int


@dataclass(frozen=True)
class CorpusStorm:
    """One storm's advisories, in issuance order, and those the subset left out."""

    advisories: tuple[str, ...]
    omitted_advisories: tuple[str, ...]


@dataclass(frozen=True)
class CorpusEntry:
    """What a parser needs besides a file's bytes: the file, its original, and the day."""

    converted: ConvertedFile
    archive: ArchiveFile
    recorded_on: date

    def provenance(
        self,
        source_id: SourceId = SOURCE,
        *,
        issued_at: datetime | None = None,
        advisory: AdvisoryNumber | None = None,
    ) -> Provenance:
        """Return the provenance of a record read from this file.

        Args:
            source_id: ``nhc-gis-archive``, or ``nhc-arrival-times`` for an arrival KMZ.
            issued_at: The product's own issuance, when it states one.
            advisory: The advisory number, when the product has one.

        Returns:
            The provenance: the original archive's URL and SHA-256, fetched on the
            recording day at 00:00 UTC.
        """
        return Provenance(
            source_id=source_id,
            url=self.archive.url,
            status=_ARCHIVE_STATUS,
            fetched_at=datetime.combine(self.recorded_on, time(0), tzinfo=UTC),
            sha256=self.archive.sha256,
            issued_at=issued_at,
            advisory=advisory,
        )


@dataclass(frozen=True)
class CorpusManifest:
    """A corpus directory's ``corpus-manifest.json``: the originals and the converted files."""

    recorded_on: date
    storms: Mapping[str, CorpusStorm]
    files: Mapping[str, ArchiveFile]
    subset: tuple[ConvertedFile, ...]
    subset_rule: str

    def entry(self, converted: ConvertedFile) -> CorpusEntry:
        """Return a converted file's parser input.

        Args:
            converted: One of ``subset``.

        Returns:
            The file, its original archive, and the recording day.
        """
        return CorpusEntry(converted, self.files[converted.source], self.recorded_on)


# The manifest ------------------------------------------------------------------------------


def _object(value: object, declared: Collection[str], where: str) -> Fields:
    return Fields(as_mapping(value, SOURCE, where), declared, source_id=SOURCE, where=where)


def _digest(fields: Fields, name: str) -> str:
    value = fields.text(name)
    if not _SHA256.fullmatch(value):
        message = f"{fields.where}: {name!r} is not a SHA-256"
        raise SourceSchemaError(SOURCE, message)
    return value


def _size(fields: Fields) -> int:
    value = fields.integer("bytes")
    if value < 0:
        message = f"{fields.where}: 'bytes' is negative"
        raise SourceSchemaError(SOURCE, message)
    return value


_MANIFEST_FIELDS: Final = frozenset(
    {"schema", "recorded_on", "storms", "files", "subset", "subset_rule"}
)
_STORM_FIELDS: Final = frozenset({"advisories", "omitted_advisories"})
_FILE_FIELDS: Final = frozenset(
    {"file", "url", "sha256", "bytes", "storm", "advisories", "product", "synoptic_time"}
)
_SUBSET_FIELDS: Final = frozenset({"file", "source", "member", "product", "sha256", "bytes"})


def _archive_file(value: object, index: int, storms: Collection[str]) -> ArchiveFile:
    fields = _object(value, _FILE_FIELDS, f"the manifest's file {index}")
    archive = ArchiveFile(
        file=fields.text("file"),
        url=fields.text("url"),
        sha256=_digest(fields, "sha256"),
        bytes=_size(fields),
        storm=fields.text("storm"),
        advisories=fields.texts("advisories"),
        product=fields.text("product"),
        synoptic_time=fields.optional_text("synoptic_time"),
    )
    if archive.storm not in storms or not archive.advisories:
        message = f"{fields.where} names no storm and advisory of the manifest"
        raise SourceSchemaError(SOURCE, message)
    return archive


def parse_manifest(body: bytes) -> CorpusManifest:
    """Read a corpus directory's ``corpus-manifest.json``.

    Args:
        body: The manifest's bytes.

    Returns:
        The manifest: the recording day, the storms, the originals by file, and the
        converted files in the manifest's order.

    Raises:
        SourceSchemaError: The manifest is too large, is not JSON, lacks a member, or
            lists a converted file whose original it does not pin.
    """
    if len(body) > MAX_MANIFEST_BYTES:
        message = f"the manifest is over {MAX_MANIFEST_BYTES} bytes"
        raise SourceSchemaError(SOURCE, message)
    fields = _object(parse_document(body, SOURCE, "the manifest"), _MANIFEST_FIELDS, "the manifest")
    if fields.integer("schema") != MANIFEST_SCHEMA:
        message = f"the manifest's schema is not {MANIFEST_SCHEMA}"
        raise SourceSchemaError(SOURCE, message)
    try:
        recorded_on = date.fromisoformat(fields.text("recorded_on"))
    except ValueError:
        message = "the manifest's 'recorded_on' is not a YYYY-MM-DD date"
        raise SourceSchemaError(SOURCE, message) from None
    storms: dict[str, CorpusStorm] = {}
    for atcf_id, value in as_mapping(fields.raw("storms"), SOURCE, "the manifest's storms").items():
        if not _ATCF_ID.fullmatch(atcf_id):
            message = "the manifest's storms are not keyed by ATCF id"
            raise SourceSchemaError(SOURCE, message)
        storm = _object(value, _STORM_FIELDS, f"the manifest's storm {atcf_id}")
        storms[atcf_id] = CorpusStorm(storm.texts("advisories"), storm.texts("omitted_advisories"))
    files = {
        archive.file: archive
        for index, value in enumerate(as_sequence(fields.raw("files"), SOURCE, "the files"))
        for archive in (_archive_file(value, index, storms),)
    }
    subset: list[ConvertedFile] = []
    for index, value in enumerate(as_sequence(fields.raw("subset"), SOURCE, "the subset")):
        item = _object(value, _SUBSET_FIELDS, f"the manifest's subset file {index}")
        converted = ConvertedFile(
            file=item.text("file"),
            source=item.text("source"),
            member=item.text("member"),
            product=item.text("product"),
            sha256=_digest(item, "sha256"),
            bytes=_size(item),
        )
        if converted.source not in files:
            message = f"{item.where} names an original the manifest does not pin"
            raise SourceSchemaError(SOURCE, message)
        subset.append(converted)
    return CorpusManifest(
        recorded_on=recorded_on,
        storms=MappingProxyType(storms),
        files=MappingProxyType(files),
        subset=tuple(subset),
        subset_rule=fields.text("subset_rule"),
    )


# Converted collections -------------------------------------------------------------------


def _gunzip(body: bytes, where: str) -> bytes:
    """Decompress one gzip member under the size bound."""
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        data = inflater.decompress(body, MAX_COLLECTION_BYTES + 1)
    except zlib.error:
        message = f"{where} is not gzip-compressed"
        raise SourceSchemaError(SOURCE, message) from None
    if len(data) > MAX_COLLECTION_BYTES or inflater.unconsumed_tail:
        message = f"{where} expands to more than {MAX_COLLECTION_BYTES} bytes"
        raise SourceSchemaError(SOURCE, message)
    if not inflater.eof or inflater.unused_data:
        message = f"{where} is not one complete gzip member"
        raise SourceSchemaError(SOURCE, message)
    return data


def _verify(body: bytes, converted: ConvertedFile) -> None:
    """Refuse bytes whose size or SHA-256 differs from the manifest's, before any parse.

    Args:
        body: A converted file's bytes.
        converted: Its manifest entry.

    Raises:
        SourceSchemaError: The bytes are not the ones the manifest pins.
    """
    if len(body) != converted.bytes or hashlib.sha256(body).hexdigest() != converted.sha256:
        message = f"{converted.file} does not match the manifest's size and SHA-256; not parsed"
        raise SourceSchemaError(SOURCE, message)


def _collection(
    body: bytes, entry: CorpusEntry, kinds: Collection[str]
) -> tuple[Mapping[str, object], Crs]:
    """Verify, decompress, and read a converted collection; return it and its native CRS."""
    where = entry.converted.file
    if entry.converted.product not in kinds:
        message = f"{where} is a {entry.converted.product} file, not {' or '.join(kinds)}"
        raise SourceSchemaError(SOURCE, message)
    _verify(body, entry.converted)
    document = as_mapping(parse_document(_gunzip(body, where), SOURCE, where), SOURCE, where)
    if document.get("type") != "FeatureCollection":
        message = f"{where} is not a FeatureCollection"
        raise SourceSchemaError(SOURCE, message)
    if document.get("storm") != entry.archive.storm or document.get("source") != entry.archive.file:
        message = f"{where} names another storm or original than its manifest entry"
        raise SourceSchemaError(SOURCE, message)
    source_crs = as_mapping(document.get("source_crs"), SOURCE, f"{where}'s source_crs")
    with model_errors(SOURCE, f"{where}'s source_crs"):
        return document, Crs.native(source_crs)


def _features(
    document: Mapping[str, object], kind: str, where: str
) -> Iterator[tuple[Mapping[str, object], Fields]]:
    """Yield each feature with its attributes, read through the kind's declared fields."""
    features = as_sequence(document.get("features"), SOURCE, f"{where}'s features")
    for index, item in enumerate(features):
        here = f"{where} feature {index}"
        feature = as_mapping(item, SOURCE, here)
        properties = as_mapping(feature.get("properties"), SOURCE, f"{here}'s properties")
        yield feature, Fields(properties, FIELDS_READ[kind], source_id=SOURCE, where=here)


def _only(
    document: Mapping[str, object], kind: str, where: str
) -> tuple[Mapping[str, object], Fields]:
    found = list(_features(document, kind, where))
    if len(found) != 1:
        message = f"{where} holds {len(found)} features, not one"
        raise SourceSchemaError(SOURCE, message)
    return found[0]


def _geometry(feature: Mapping[str, object], fields: Fields, crs: Crs) -> Geometry:
    value = feature.get("geometry")
    if not isinstance(value, dict):
        message = f"{fields.where} has no geometry"
        raise SourceSchemaError(SOURCE, message)
    with model_errors(SOURCE, f"{fields.where}'s geometry"):
        return Geometry.from_geojson(cast("dict[str, object]", value), crs)


def _note(feature: Mapping[str, object], fields: Fields) -> str | None:
    note = feature.get("geometry_note")
    if note is not None and not isinstance(note, str):
        message = f"{fields.where}'s geometry_note is not text"
        raise SourceSchemaError(SOURCE, message)
    return note


def _advisory(fields: Fields, entry: CorpusEntry) -> Advisory:
    """Read a feature's storm and advisory, checked against the manifest's."""
    storm = entry.archive.storm
    basin, number = fields.text("BASIN"), fields.integer("STORMNUM")
    number_text, text = fields.code("ADVISNUM"), fields.text("ADVDATE")
    if basin.upper() != storm[:2] or number != int(storm[2:4]):
        message = f"{fields.where}: 'BASIN' and 'STORMNUM' name another storm than {storm}"
        raise SourceSchemaError(SOURCE, message)
    with model_errors(SOURCE, f"{fields.where}'s advisory"):
        advisory = Advisory(
            atcf_id=storm,
            number=AdvisoryNumber.parse(number_text),
            issued_at=parse_nhc_local_time(text),
            local_text=text,
        )
        expected = AdvisoryNumber.parse(entry.archive.advisories[0])
    if advisory.number != expected:
        message = f"{fields.where}: 'ADVISNUM' is not the manifest's advisory {expected}"
        raise SourceSchemaError(SOURCE, message)
    return advisory


def _provenance(entry: CorpusEntry, advisory: Advisory) -> Provenance:
    return entry.provenance(issued_at=advisory.issued_at, advisory=advisory.number)


def parse_cone(body: bytes, entry: CorpusEntry) -> ConeGeometry:
    """Parse a converted ``cone`` collection: the advisory's forecast cone.

    Args:
        body: The file's bytes, as stored.
        entry: Its manifest entries.

    Returns:
        The cone.

    Raises:
        SourceSchemaError: The bytes are not the manifest's, or the collection breaks a
            rule: a missing or mistyped field, another storm or advisory, or not one cone.
    """
    document, crs = _collection(body, entry, ("cone",))
    feature, fields = _only(document, "cone", entry.converted.file)
    advisory = _advisory(fields, entry)
    with model_errors(SOURCE, fields.where):
        return ConeGeometry(
            atcf_id=entry.archive.storm,
            advisory=advisory,
            provenance=_provenance(entry, advisory),
            forecast_period_h=fields.integer("FCSTPRD"),
            geometry=_geometry(feature, fields, crs),
        )


def parse_archive_storm(body: bytes, entry: CorpusEntry) -> ArchiveStorm:
    """Parse a converted ``cone`` collection's storm: its name and type as the archive spells them.

    Args:
        body: The cone file's bytes, as stored.
        entry: Its manifest entries.

    Returns:
        The storm, with the cone's provenance.

    Raises:
        SourceSchemaError: The bytes are not the manifest's, or a field is missing.
    """
    document, _crs = _collection(body, entry, ("cone",))
    _feature, fields = _only(document, "cone", entry.converted.file)
    advisory = _advisory(fields, entry)
    with model_errors(SOURCE, fields.where):
        return ArchiveStorm(
            atcf_id=entry.archive.storm,
            name=fields.text("STORMNAME"),
            storm_type=fields.text("STORMTYPE"),
            provenance=_provenance(entry, advisory),
        )


def parse_track(body: bytes, entry: CorpusEntry) -> ForecastTrack:
    """Parse a converted ``track`` collection: the forecast track line.

    Args:
        body: The file's bytes, as stored.
        entry: Its manifest entries.

    Returns:
        The track.

    Raises:
        SourceSchemaError: The bytes are not the manifest's, or the collection breaks a rule.
    """
    document, crs = _collection(body, entry, ("track",))
    feature, fields = _only(document, "track", entry.converted.file)
    advisory = _advisory(fields, entry)
    with model_errors(SOURCE, fields.where):
        return ForecastTrack(
            atcf_id=entry.archive.storm,
            advisory=advisory,
            provenance=_provenance(entry, advisory),
            geometry=_geometry(feature, fields, crs),
        )


def parse_track_points(body: bytes, entry: CorpusEntry) -> tuple[TrackPoint, ...]:
    """Parse a converted ``points`` collection, timing each point against its advisory.

    Args:
        body: The file's bytes, as stored.
        entry: Its manifest entries.

    Returns:
        The forecast points, in the collection's order.

    Raises:
        SourceSchemaError: The bytes are not the manifest's, a point's advisory names no
            instant to time it against, or the collection breaks another rule.
    """
    document, crs = _collection(body, entry, ("points",))
    points: list[TrackPoint] = []
    for feature, fields in _features(document, "points", entry.converted.file):
        advisory = _advisory(fields, entry)
        if advisory.issued_at is None:
            message = f"{fields.where}: the advisory has no instant to time the point against"
            raise SourceSchemaError(SOURCE, message)
        with model_errors(SOURCE, fields.where):
            points.append(
                TrackPoint(
                    atcf_id=entry.archive.storm,
                    advisory=advisory,
                    provenance=_provenance(entry, advisory),
                    tau_h=fields.integer("TAU"),
                    valid_at=resolve_track_valid_time(fields.text("VALIDTIME"), advisory.issued_at),
                    valid_local_text=fields.optional_text("FLDATELBL"),
                    position=_geometry(feature, fields, crs),
                    max_wind_kt=fields.optional_integer("MAXWIND"),
                    gust_kt=fields.optional_integer("GUST"),
                    mslp_mb=fields.optional_integer("MSLP", sentinel=True),
                    direction_deg=fields.optional_integer("TCDIR", sentinel=True),
                    speed_kt=fields.optional_integer("TCSPD", sentinel=True),
                    development=fields.text("TCDVLP"),
                    storm_type=fields.text("STORMTYPE"),
                    saffir_simpson=fields.optional_integer("SSNUM"),
                    label=fields.text("DVLBL"),
                )
            )
    return tuple(points)


def parse_watch_warnings(body: bytes, entry: CorpusEntry) -> tuple[WatchWarningSegment, ...]:
    """Parse a converted ``watch-warning`` collection into segments, unknown codes kept.

    A one-vertex source line is the Point the converter wrote, with its ``geometry_note``.

    Args:
        body: The file's bytes, as stored.
        entry: Its manifest entries.

    Returns:
        The segments, in the collection's order.

    Raises:
        SourceSchemaError: The bytes are not the manifest's, or the collection breaks a rule.
    """
    document, crs = _collection(body, entry, ("watch-warning",))
    segments: list[WatchWarningSegment] = []
    for feature, fields in _features(document, "watch-warning", entry.converted.file):
        advisory = _advisory(fields, entry)
        code = fields.text("TCWW")
        with model_errors(SOURCE, fields.where):
            segments.append(
                WatchWarningSegment(
                    atcf_id=entry.archive.storm,
                    advisory=advisory,
                    provenance=_provenance(entry, advisory),
                    tcww=WatchWarningType.parse(code),
                    geometry=_geometry(feature, fields, crs),
                    geometry_note=_note(feature, fields),
                )
            )
    return tuple(segments)


def parse_wind_probabilities(body: bytes, entry: CorpusEntry) -> WindProbabilityProduct:
    """Parse a converted 5 km wind-speed-probability collection, full or a window extract.

    The synoptic time and the threshold come from the archive member's name
    (``YYYYMMDDHH_wsp34knt120hr_5km.shp``) and must agree with the collection's own
    members; the bands come from ``PERCENTAGE``. A window extract's ``window`` member
    gives the area it covers, which becomes the product's ``coverage``.

    Args:
        body: The file's bytes, as stored.
        entry: Its manifest entries.

    Returns:
        The product. Its provenance states no issuance and no advisory: the archive's
        probability files name a synoptic time only.

    Raises:
        SourceSchemaError: The bytes are not the manifest's, the member's name is not a
            5 km probability file, or the collection disagrees with it.
    """
    where = entry.converted.file
    document, crs = _collection(body, entry, WSP_KINDS)
    match = _WSP_MEMBER.fullmatch(entry.converted.member)
    if match is None:
        message = f"{where}'s member is not a 5 km wind-speed-probability shapefile"
        raise SourceSchemaError(SOURCE, message)
    threshold = _THRESHOLDS[match["threshold"]]
    if (
        entry.converted.product != f"wsp-{threshold}kt"
        or document.get("threshold_kt") != threshold
        or document.get("synoptic_time") != match["stamp"]
        or entry.archive.synoptic_time != match["stamp"]
    ):
        message = f"{where}'s threshold or synoptic time disagrees with its member's name"
        raise SourceSchemaError(SOURCE, message)
    bands: list[WindProbabilityBand] = []
    for feature, fields in _features(document, "wsp", where):
        label = fields.text("PERCENTAGE")
        with model_errors(SOURCE, fields.where):
            bands.append(
                WindProbabilityBand.from_label(
                    label, _geometry(feature, fields, crs), _note(feature, fields)
                )
            )
    window = document.get("window")
    coverage: Geometry | None = None
    if window is not None:
        area = as_mapping(window, SOURCE, f"{where}'s window").get("geometry")
        shape = as_mapping(area, SOURCE, f"{where}'s window geometry")
        with model_errors(SOURCE, f"{where}'s window"):
            coverage = Geometry.from_geojson(shape, crs)
    with model_errors(SOURCE, where):
        return WindProbabilityProduct(
            threshold_kt=threshold,
            synoptic_at=parse_synoptic_time(entry.converted.member),
            bands=tuple(bands),
            coverage=coverage,
            provenance=entry.provenance(),
        )
