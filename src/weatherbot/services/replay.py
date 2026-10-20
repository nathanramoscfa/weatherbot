# src/weatherbot/services/replay.py
"""Replay: the corpus's advisories read back as snapshots.

``ReplayCorpus.open(directory)`` reads ``corpus-manifest.json`` from a corpus directory:
the committed subset under ``tests/fixtures/replay/``, or a complete conversion that
``scripts/fetch_replay_corpus.py convert --full --out DIR`` wrote. ``storms()`` lists each
storm; ``snapshots(atcf_id)`` yields one ``Snapshot(origin="replay")`` per advisory, in
the manifest's order. A replay snapshot is stamped with the advisory's issuance as both
its start and its completion, so its clock is the advisory's, and its id is a UUID 5 of
the storm and the advisory, so a replay is the same every time.

Each snapshot holds the storm's products of that advisory (cone, track, points, and
watches and warnings); the three wind-speed-probability products of the synoptic time
the manifest associates with the advisory, when there is one; and, when the directory
holds arrival-time KMZ, the pair of the latest full advisory at or before it, parsed by
``parse_arrival_kmz`` (outcome ``nhc-arrival-times`` ``ok``). Otherwise that outcome is
``skipped`` with the reason. The committed subset holds no KMZ.

Every file is checked before anything parses it: its path must be a plain relative path
that stays inside the directory (no absolute or parent-relative name, no link followed
out), the file must exist, and its bytes must match the manifest's size and SHA-256. A
file that breaks a rule raises ``ReplayError`` naming the file and the rule.
"""

import hashlib
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Final, Self
from uuid import NAMESPACE_URL, UUID, uuid5

from weatherbot.engine import assess, diff
from weatherbot.models import (
    AdvisoryNumber,
    ArrivalTimeProduct,
    Assessment,
    ChangeEvent,
    Location,
    Snapshot,
    SourceOutcome,
    StormProducts,
    Thresholds,
    WindProbabilityProduct,
)
from weatherbot.sources import nhc_gis_archive
from weatherbot.sources.errors import SourceSchemaError
from weatherbot.sources.nhc_arrival_times import MAX_KMZ_BYTES, parse_arrival_kmz
from weatherbot.sources.nhc_gis_archive import (
    ARRIVAL_KINDS,
    ARRIVALS,
    FORECAST_KINDS,
    MANIFEST_NAME,
    SOURCE,
    WSP_ARCHIVE,
    WSP_KINDS,
    ConvertedFile,
    CorpusEntry,
    CorpusManifest,
)

type _Parser[T] = Callable[[bytes, CorpusEntry], T]

REPLAY_NAMESPACE: Final = uuid5(
    NAMESPACE_URL, "https://github.com/nathanramoscfa/weatherbot#replay"
)
"""The namespace of replay snapshot ids: ``uuid5(REPLAY_NAMESPACE, "AL052019/036")``."""

NO_ARRIVAL_PRODUCTS: Final = "the corpus holds no arrival-time products"
MAX_FILE_BYTES: Final = 64 * 1024 * 1024
"""The bound on any one converted file; an arrival KMZ is bounded as the client bounds it."""


class ReplayError(Exception):
    """A corpus file broke a rule. The message names the file and the rule, never content."""

    def __init__(self, file: str, rule: str) -> None:
        """Name the file and the rule it broke.

        Args:
            file: The file, as the manifest names it.
            rule: The rule.
        """
        super().__init__(f"{file}: {rule}")
        self.file = file
        self.rule = rule


@dataclass(frozen=True)
class ReplayStorm:
    """One storm of a corpus: its ATCF id, archive name, advisory count, and issuances.

    ``name`` is the latest advisory's ``STORMNAME``: a storm's first advisories may name
    a depression by its number.
    """

    atcf_id: str
    name: str
    advisories: int
    first_issued_at: datetime
    last_issued_at: datetime


@dataclass(frozen=True, slots=True)
class ReplayStep:
    """One advisory's assessment and its changes from the preceding advisory.

    Replay steps are transient values. The service opens no database and writes no
    history; the caller owns how a timeline is shown.
    """

    assessment: Assessment
    changes: tuple[ChangeEvent, ...]


class ReplayService:
    """Assess the verified advisories of a corpus in their recorded order."""

    def __init__(self, corpus: "ReplayCorpus") -> None:
        """Use a corpus opened by ``ReplayCorpus.open``.

        Args:
            corpus: The verifying reader of the committed subset or a full conversion.
        """
        self._corpus = corpus

    def timeline(
        self, atcf_id: str, location: Location, thresholds: Thresholds
    ) -> tuple[ReplayStep, ...]:
        """Assess each advisory and compare it with the previous assessment.

        Args:
            atcf_id: A storm listed in the corpus manifest.
            location: The location to assess; no present-day state is read implicitly.
            thresholds: The thresholds to record in every assessment.

        Returns:
            The steps in advisory order, including the first assessment's initial events.

        Raises:
            ReplayError: The corpus refuses a storm or one of its product files.
        """
        steps: list[ReplayStep] = []
        previous: Assessment | None = None
        for snapshot in self._corpus.snapshots(atcf_id):
            current = assess(snapshot, location, thresholds)
            steps.append(ReplayStep(current, diff(previous, current)))
            previous = current
        return tuple(steps)


def snapshot_id(atcf_id: str, advisory: str) -> UUID:
    """Return a replay snapshot's id: a UUID 5 of the storm and the advisory.

    Args:
        atcf_id: The storm's ATCF id.
        advisory: The advisory as the manifest spells it, such as ``036`` or ``036A``.

    Returns:
        The id, the same on every replay.
    """
    return uuid5(REPLAY_NAMESPACE, f"{atcf_id}/{advisory}")


def _plain(name: str) -> PurePosixPath | None:
    """The relative path a manifest name spells, or ``None`` when it is not plain."""
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or ":" in name
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in name.split("/"))
    ):
        return None
    return path


class ReplayCorpus:
    """A corpus directory, read through its manifest; every file verified before parsing."""

    def __init__(self, directory: Path, manifest: CorpusManifest) -> None:
        """Wrap an opened corpus; use ``ReplayCorpus.open``.

        Args:
            directory: The corpus directory.
            manifest: Its manifest.

        Raises:
            ReplayError: A file's path leaves the directory or is over the size bound.
        """
        self._root = directory.resolve()
        self.manifest = manifest
        self._forecast: dict[tuple[str, str, str], ConvertedFile] = {}
        self._wsp: dict[tuple[str, str], list[ConvertedFile]] = {}
        self._arrivals: dict[tuple[str, str, str], ConvertedFile] = {}
        for converted in manifest.subset:
            self._path(converted.file)
            limit = MAX_KMZ_BYTES if converted.product in ARRIVAL_KINDS else MAX_FILE_BYTES
            if converted.bytes > limit:
                raise ReplayError(converted.file, f"the manifest lists it over {limit} bytes")
            self._index(converted)
        self._has_arrivals = bool(self._arrivals)

    def _index(self, converted: ConvertedFile) -> None:
        archive = self.manifest.files[converted.source]
        storm, product = archive.storm, converted.product
        if product in FORECAST_KINDS:
            self._forecast[storm, archive.advisories[0], product] = converted
        elif product in WSP_KINDS and archive.product == WSP_ARCHIVE:
            for advisory in archive.advisories:
                self._wsp.setdefault((storm, advisory), []).append(converted)
        elif product in ARRIVAL_KINDS:
            self._arrivals[storm, archive.advisories[0], product] = converted

    @classmethod
    def open(cls, directory: Path) -> Self:
        """Open a corpus directory by its ``corpus-manifest.json``.

        Args:
            directory: The committed subset's directory or a ``convert --full`` output.

        Returns:
            The corpus.

        Raises:
            ReplayError: The manifest is missing, too large, or does not parse, or a file
                it lists leaves the directory.
        """
        path = directory / MANIFEST_NAME
        if not path.is_file():
            raise ReplayError(MANIFEST_NAME, "the corpus directory holds no manifest")
        if path.stat().st_size > nhc_gis_archive.MAX_MANIFEST_BYTES:
            raise ReplayError(MANIFEST_NAME, "the manifest is over its size bound")
        try:
            manifest = nhc_gis_archive.parse_manifest(path.read_bytes())
        except SourceSchemaError as error:
            raise ReplayError(MANIFEST_NAME, f"it does not parse: {error}") from None
        return cls(directory, manifest)

    def _path(self, name: str) -> Path:
        plain = _plain(name)
        if plain is None:
            raise ReplayError(name, "the path is not a plain relative path inside the corpus")
        target = self._root.joinpath(*plain.parts)
        if not target.resolve().is_relative_to(self._root):
            raise ReplayError(name, "the path leaves the corpus directory")
        return target

    def _read(self, converted: ConvertedFile) -> bytes:
        """Return a file's bytes once they match the manifest's size and SHA-256."""
        path = self._path(converted.file)
        if not path.is_file():
            raise ReplayError(converted.file, "the file is missing")
        if path.stat().st_size != converted.bytes:
            raise ReplayError(converted.file, "the size differs from the manifest's")
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != converted.sha256:
            raise ReplayError(converted.file, "the SHA-256 differs from the manifest's")
        return body

    def _storm(self, atcf_id: str) -> nhc_gis_archive.CorpusStorm:
        storm = self.manifest.storms.get(atcf_id)
        if storm is None:
            raise ReplayError(MANIFEST_NAME, f"the manifest lists no storm {atcf_id!r}")
        return storm

    def _advisories(self, atcf_id: str) -> list[str]:
        storm = self._storm(atcf_id)
        return [a for a in storm.advisories if a not in storm.omitted_advisories]

    def _cone(self, atcf_id: str, advisory: str) -> ConvertedFile:
        found = self._forecast.get((atcf_id, advisory, "cone"))
        if found is None:
            raise ReplayError(MANIFEST_NAME, f"no cone is listed for {atcf_id} {advisory}")
        return found

    def storms(self) -> tuple[ReplayStorm, ...]:
        """List each storm: its ATCF id, archive name, advisory count, and issuances.

        Returns:
            One entry per storm, in the manifest's order.

        Raises:
            ReplayError: A first or last cone is missing, tampered, or unreadable.
        """
        found: list[ReplayStorm] = []
        for atcf_id in self.manifest.storms:
            advisories = self._advisories(atcf_id)
            first = self._parsed_cone(atcf_id, advisories[0])
            last = self._parsed_cone(atcf_id, advisories[-1])
            found.append(
                ReplayStorm(
                    atcf_id=atcf_id,
                    name=last[1],
                    advisories=len(advisories),
                    first_issued_at=first[0],
                    last_issued_at=last[0],
                )
            )
        return tuple(found)

    def _parsed_cone(self, atcf_id: str, advisory: str) -> tuple[datetime, str]:
        converted = self._cone(atcf_id, advisory)
        body = self._read(converted)
        entry = self.manifest.entry(converted)
        cone = _parsed(converted, lambda: nhc_gis_archive.parse_cone(body, entry))
        storm = _parsed(converted, lambda: nhc_gis_archive.parse_archive_storm(body, entry))
        if cone.advisory.issued_at is None:
            raise ReplayError(converted.file, "the cone's ADVDATE names no instant")
        return cone.advisory.issued_at, storm.name

    def snapshots(self, atcf_id: str) -> Iterator[Snapshot]:
        """Yield one replay snapshot per advisory of a storm, in the manifest's order.

        Args:
            atcf_id: The storm's ATCF id.

        Yields:
            The snapshots.

        Raises:
            ReplayError: The storm is not in the corpus, or a file is missing, tampered,
                outside the directory, or unreadable.
        """
        advisories = self._advisories(atcf_id)
        for index, advisory in enumerate(advisories):
            yield self._snapshot(atcf_id, advisory, advisories[: index + 1])

    def _snapshot(self, atcf_id: str, advisory: str, so_far: Sequence[str]) -> Snapshot:
        cone_file = self._cone(atcf_id, advisory)
        cone_body = self._read(cone_file)
        entry = self.manifest.entry(cone_file)
        cone = _parsed(cone_file, lambda: nhc_gis_archive.parse_cone(cone_body, entry))
        storm = _parsed(cone_file, lambda: nhc_gis_archive.parse_archive_storm(cone_body, entry))
        issued_at = cone.advisory.issued_at
        if issued_at is None:
            raise ReplayError(cone_file.file, "the cone's ADVDATE names no instant")
        track_file = self._forecast.get((atcf_id, advisory, "track"))
        points_file = self._forecast.get((atcf_id, advisory, "points"))
        segments_file = self._forecast.get((atcf_id, advisory, "watch-warning"))
        arrivals, arrival_outcome = self._arrival_pair(atcf_id, so_far)
        products = StormProducts(
            archived=storm,
            cone=cone,
            track=self._parse(track_file, nhc_gis_archive.parse_track) if track_file else None,
            track_points=(
                self._parse(points_file, nhc_gis_archive.parse_track_points) if points_file else ()
            ),
            watch_warnings=(
                self._parse(segments_file, nhc_gis_archive.parse_watch_warnings)
                if segments_file
                else ()
            ),
            arrival_times=arrivals,
        )
        return Snapshot(
            snapshot_id=snapshot_id(atcf_id, advisory),
            origin="replay",
            started_at=issued_at,
            completed_at=issued_at,
            storms=(products,),
            wind_probabilities=self._probabilities(atcf_id, advisory),
            source_outcomes=(SourceOutcome(source_id=SOURCE, status="ok"), arrival_outcome),
        )

    def _parse[T](self, converted: ConvertedFile, parser: _Parser[T]) -> T:
        body = self._read(converted)
        entry = self.manifest.entry(converted)
        return _parsed(converted, lambda: parser(body, entry))

    def _probabilities(self, atcf_id: str, advisory: str) -> tuple[WindProbabilityProduct, ...]:
        files = sorted(self._wsp.get((atcf_id, advisory), ()), key=lambda f: f.product)
        return tuple(self._parse(f, nhc_gis_archive.parse_wind_probabilities) for f in files)

    def _arrival_pair(
        self, atcf_id: str, so_far: Sequence[str]
    ) -> tuple[tuple[ArrivalTimeProduct, ...], SourceOutcome]:
        """The KMZ pair of the latest full advisory at or before the last of ``so_far``."""
        if not self._has_arrivals:
            return (), SourceOutcome(
                source_id=ARRIVALS, status="skipped", reason=NO_ARRIVAL_PRODUCTS
            )
        full = next(
            (a for a in reversed(so_far) if not AdvisoryNumber.parse(a).is_intermediate), None
        )
        pair = [self._arrivals.get((atcf_id, full or "", kind)) for kind in ARRIVAL_KINDS]
        files = [converted for converted in pair if converted is not None]
        if full is None or len(files) != len(ARRIVAL_KINDS):
            reason = f"{NO_ARRIVAL_PRODUCTS} for {atcf_id} advisory {full or so_far[-1]}"
            return (), SourceOutcome(source_id=ARRIVALS, status="skipped", reason=reason)
        products = tuple(self._kmz(converted, full) for converted in files)
        return products, SourceOutcome(source_id=ARRIVALS, status="ok")

    def _kmz(self, converted: ConvertedFile, advisory: str) -> ArrivalTimeProduct:
        body = self._read(converted)
        entry = self.manifest.entry(converted)
        provenance = entry.provenance(ARRIVALS, advisory=AdvisoryNumber.parse(advisory))
        return _parsed(converted, lambda: parse_arrival_kmz(body, provenance))


def _parsed[T](converted: ConvertedFile, parse: Callable[[], T]) -> T:
    """Run a parse of verified bytes; a schema error names the file it came from."""
    try:
        return parse()
    except SourceSchemaError as error:
        raise ReplayError(converted.file, f"it does not parse: {error}") from None
