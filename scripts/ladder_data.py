# scripts/ladder_data.py
"""Shared, public inputs and coordinate-free outcomes for the ladder development tools."""

import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from http import HTTPStatus
from pathlib import Path
from typing import Final, cast

from check_personal_data import load_landmarks
from weatherbot.engine.breakpoints import breakpoint_span
from weatherbot.engine.geometry import place
from weatherbot.models import (
    WGS84,
    LatLon,
    Location,
    Provenance,
    Snapshot,
    SourceId,
)
from weatherbot.services.replay import ReplayCorpus, ReplayStep
from weatherbot.sources import nhc_map, nws

ROOT: Final = Path(__file__).resolve().parents[1]
CORPUS: Final = ROOT / "tests/fixtures/replay"
GOLDENS: Final = ROOT / "tests/golden/replay"
RECORDED: Final = ROOT / "tests/fixtures/recorded"


def canonical(value: object) -> bytes:
    """Return deterministic JSON bytes for a digest."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: object) -> str:
    """Return the SHA-256 of canonical JSON."""
    return hashlib.sha256(canonical(value)).hexdigest()


def output_path(path: Path, directory: Path) -> Path:
    """Refuse a write outside its designated tree, including through a symbolic link.

    Args:
        path: The proposed output.
        directory: Its allowed directory, itself inside the checkout.

    Returns:
        The resolved output.

    Raises:
        ValueError: A path leaves the allowed tree or the checkout.
    """
    resolved, allowed = path.resolve(), directory.resolve()
    if not allowed.is_relative_to(ROOT) or not resolved.is_relative_to(allowed):
        message = "output must stay inside its designated repository directory"
        raise ValueError(message)
    return resolved


def _capture(source: SourceId, filename: str) -> tuple[bytes, Provenance]:
    for manifest in sorted((RECORDED / source).glob("*/manifest.json")):
        document = cast("dict[str, list[dict[str, object]]]", json.loads(manifest.read_bytes()))
        for entry in document["captures"]:
            if entry["file"] != filename:
                continue
            body = (manifest.parent / filename).read_bytes()
            if len(body) != entry["bytes"] or hashlib.sha256(body).hexdigest() != entry["sha256"]:
                message = f"recorded input failed verification: {source}/{filename}"
                raise ValueError(message)
            provenance = Provenance.model_validate_json(
                json.dumps(
                    {
                        "source_id": source,
                        **{name: entry[name] for name in ("url", "status", "fetched_at", "sha256")},
                    }
                )
            )
            return body, provenance
    message = f"recorded input is missing: {source}/{filename}"
    raise ValueError(message)


@cache
def public_landmarks() -> dict[str, Location]:
    """Build both landmarks from TOML, verified NWS answers, and the recorded catalogue."""
    body, provenance = _capture("nhc-map-breakpoints", "query-watch-warning-breakpoints.geojson")
    catalogue = nhc_map.parse_breakpoints("Watch_Warning_Breakpoints", json.loads(body), provenance)
    found: dict[str, Location] = {}
    for landmark in load_landmarks():
        body, answer = _capture("nws-points", f"points-{landmark.key}.json")
        coverage = nws.parse_point(body) if answer.status == HTTPStatus.OK else None
        if coverage is None and (
            answer.status != HTTPStatus.NOT_FOUND
            or json.loads(body).get("type") != "https://api.weather.gov/problems/InvalidPoint"
        ):
            message = "outside NWS coverage requires the recorded InvalidPoint answer"
            raise ValueError(message)
        point = LatLon(latitude=float(landmark.lat), longitude=float(landmark.lon))
        found[landmark.key] = Location(
            name=landmark.key,
            display_name=landmark.name,
            point=point,
            nws=coverage,
            breakpoint_span=breakpoint_span(place(point, WGS84), catalogue),
        )
    return found


@dataclass(frozen=True)
class Case:
    """One snapshot-location pair identified without coordinates."""

    name: str
    group: str
    advisory: str
    snapshot: Snapshot
    location: Location


@cache
def cases() -> tuple[Case, ...]:
    """Read all eight replay pairs and the shared named scenarios once.

    The scenarios are development inputs, so only this development helper adds their
    checkout directories to the import path. The installed application never reads tests.
    """
    corpus = ReplayCorpus.open(CORPUS)
    found: list[Case] = []
    for storm in corpus.storms():
        snapshots = tuple(corpus.snapshots(storm.atcf_id))
        for landmark, location in public_landmarks().items():
            group = f"{storm.atcf_id}-{landmark}"
            for snapshot in snapshots:
                cone = snapshot.storms[0].cone
                if cone is None:
                    message = "a replay case requires its verified advisory cone"
                    raise ValueError(message)
                advisory = str(cone.advisory.number)
                found.append(Case(f"{group}/{advisory}", group, advisory, snapshot, location))
    for directory in ("tests/engine", "tests/services", "tests/sources", "tests/contract"):
        sys.path.insert(0, str(ROOT / directory))
    from scenarios import SCENARIOS  # noqa: PLC0415 - checkout-only development inputs

    for scenario in SCENARIOS:
        snapshot, location = scenario.inputs()
        found.append(Case(scenario.name, "scenarios", scenario.name, snapshot, location))
    return tuple(found)


def utc(instant: datetime) -> str:
    """Render a UTC instant in the golden format."""
    return instant.isoformat().replace("+00:00", "Z")


def entries(steps: tuple[ReplayStep, ...]) -> list[dict[str, object]]:
    """Project a timeline to the public fields a golden freezes; retain event order."""
    return [
        {
            "advisory": str(step.assessment.threats[0].advisory),
            "issued_at": utc(step.assessment.as_of),
            "level": int(step.assessment.level),
            "rule": str(step.assessment.rule),
            "changes": [event.kind for event in step.changes],
            "official_codes": sorted({p.code for p in step.assessment.official if p.covers}),
        }
        for step in steps
    ]
