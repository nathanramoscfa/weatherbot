# tests/cli/cli_support.py
"""What the command tests share: recorded answers, a quiet runtime, and a runner.

Every recorded answer of every source is served by respx, so a command runs offline with
the real clients and the real database (in the test's temporary data directory). The
recorded roster links Simon's advisory 22 arrival-time KMZ pair, which was never
recorded; the recorded advisory 38 pair stands in for it, so the KMZ supersedes the
map-layer product, and its advisory mismatch is the run's Source-drift warning.
"""

import json
import re
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

import httpx
import respx
from fixture_support import REPOSITORY_ROOT, CaptureDirectory, latest_live, register_alert
from jsonschema import Draft202012Validator
from pydantic import BaseModel
from source_support import NOW, FakeClock, entry, serve
from typer.testing import CliRunner

from check_personal_data import load_landmarks
from weatherbot.cli import app
from weatherbot.cli.documents import DOCUMENTS, json_schema
from weatherbot.cli.runtime import Runtime
from weatherbot.models import SourceId
from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import open_database
from weatherbot.services.persistence.repositories import AssessmentRepository, StoredAssessment
from weatherbot.sources.http import Fetcher, HostPacer, ValidatorStore

ANSI_ESCAPE: Final = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
SERVED: Final[tuple[SourceId, ...]] = (
    "nhc-current-storms",
    "nhc-arrival-times",
    "nhc-map-tropical-weather",
    "nhc-map-tropical-summary",
    "nhc-map-breakpoints",
    "nhc-map-peak-surge",
    "nhc-map-surge-risk",
    "nhc-gis-rss",
    "nhc-text-products",
    "nhc-outlook-graphics",
    "nws-points",
    "nws-alerts-point",
    "nws-alerts-zone",
    "nws-zones",
    "overlay-radar",
    "overlay-satellite",
    "geocode-nominatim",
)
KMZ: Final = "https://www.nhc.noaa.gov/storm_graphics/api/EP202026_{adv}adv_{kind}_toa_34.kmz"
KINDS: Final = ("earliest_reasonable", "most_likely")
MIAMI: Final = "Miami-Dade County Hall"
NASSAU: Final = "Parliament Square"
CORPUS: Final = REPOSITORY_ROOT / "tests" / "fixtures" / "replay"
COUNTY_ALERTS: Final = "https://api.weather.gov/alerts/active/zone/FLC086"


def county_statement() -> dict[str, httpx.Response]:
    """An override: the county zone answers the register's FLC086 Coastal Flood Statement.

    The alert names other zones than the Miami-Dade landmark's, so it is context that sets
    no level (issue #10). It is built from the register's description, sent an hour
    before the test clock, inside the recorded zone answer.
    """
    capture = directory("nws-alerts-zone")
    document = json.loads(capture.payload(entry(capture, "alerts-zone-FLC086.geojson")))
    document["features"] = [register_alert(NOW - timedelta(hours=1))]
    body = json.dumps(document).encode("utf-8")
    headers = {"content-type": "application/geo+json"}
    return {COUNTY_ALERTS: httpx.Response(200, content=body, headers=headers)}


def history(name: str, limit: int = 10) -> tuple[StoredAssessment, ...]:
    """A location's stored assessments in the test's database, newest first."""
    with open_database(AppPaths.resolve()) as database:
        return AssessmentRepository(database.engine).history(name, limit)


def directory(source: SourceId) -> CaptureDirectory:
    """The newest live capture of a source."""
    found = latest_live(source)
    assert found is not None, f"{source} has no live capture"
    return found


def landmark(key: str) -> tuple[str, str]:
    """A landmark's latitude and longitude as written in scripts/public_landmarks.toml."""
    found = next(item for item in load_landmarks() if item.key == key)
    return str(found.lat), str(found.lon)


def quiet_fetcher(
    client: httpx.AsyncClient, validators: ValidatorStore, *, now: datetime = NOW
) -> Fetcher:
    """A fetcher on the run's store whose pacing and backoff waits are recorded, not slept.

    Every answer is fetched at ``now``.
    """
    clock, backoff = FakeClock(), FakeClock()
    return Fetcher(
        client,
        pacer=HostPacer(clock=clock, sleep=clock.sleep),
        validators=validators,
        sleep=backoff.sleep,
        jitter=lambda: 0.5,
        now=lambda: now,
        clock=clock,
    )


def runtime(*, terminal: bool = False, now: datetime = NOW, width: int | None = None) -> Runtime:
    """A runtime with the quiet fetcher, a fixed clock, and plain text unless asked."""
    return Runtime(make_fetcher=quiet_fetcher, now=lambda: now, terminal=terminal, width=width)


def _stand_in_kmz(router: respx.MockRouter) -> None:
    arrivals = directory("nhc-arrival-times")
    for kind in KINDS:
        body = arrivals.payload(entry(arrivals, f"EP202026_038adv_{kind}_toa_34.kmz"))
        router.get(KMZ.format(adv="022", kind=kind)).mock(
            return_value=httpx.Response(
                200, content=body, headers={"content-type": "application/vnd.google-earth.kmz"}
            )
        )


def _any_point(router: respx.MockRouter) -> None:
    """Answer a non-landmark point with the Miami-Dade answers (after the exact routes)."""
    points = directory("nws-points")
    alerts = directory("nws-alerts-point")
    geocode = directory("geocode-nominatim")
    for pattern, capture, name in (
        (r"https://api\.weather\.gov/points/.+", points, "points-miami-dade.json"),
        (
            r"https://api\.weather\.gov/alerts/active\?point=.+",
            alerts,
            "alerts-point-miami-dade.geojson",
        ),
        (r"https://nominatim\.openstreetmap\.org/reverse\?.+", geocode, "reverse-miami-dade.json"),
    ):
        item = entry(capture, name)
        recorded: object = item["headers"]
        assert isinstance(recorded, dict)
        headers = {"content-type": str(recorded["content-type"])}  # pyright: ignore[reportUnknownArgumentType] - a JSON object
        router.get(url__regex=pattern).mock(
            return_value=httpx.Response(200, content=capture.payload(item), headers=headers)
        )


ROSTER_URL: Final = "https://www.nhc.noaa.gov/CurrentStorms.json"
SUMMARY_CATALOG: Final = (
    "https://mapservices.weather.noaa.gov/tropical/rest/services/tropical/"
    "NHC_tropical_weather_summary/MapServer?f=json"
)


@contextmanager
def recorded_services(
    *, roster: bytes | None = None, overrides: Mapping[str, httpx.Response] | None = None
) -> Generator[respx.MockRouter]:
    """Serve every recorded answer.

    ``roster`` replaces the recorded roster's body; ``overrides`` answers URLs its own way
    instead of the recorded answers.
    """
    answers = dict(overrides or {})
    if roster is not None:
        answers[ROSTER_URL] = httpx.Response(
            200, content=roster, headers={"content-type": "application/json"}
        )
    with respx.mock(assert_all_called=False) as router:
        for source in SERVED:
            serve(router, directory(source))
        _stand_in_kmz(router)
        _any_point(router)
        # A route of the same pattern replaces the recorded one, so overrides come last.
        for url, response in answers.items():
            router.get(url).mock(return_value=response)
        yield router


@dataclass(frozen=True)
class Ran:
    """A command's exit code and its outputs, ANSI escapes stripped."""

    exit_code: int
    stdout: str
    stderr: str

    def json(self) -> dict[str, object]:
        """The one JSON document standard output holds."""
        document: object = json.loads(self.stdout)
        assert isinstance(document, dict)
        return document  # pyright: ignore[reportUnknownVariableType] - a JSON object


def run(args: Sequence[str], rt: Runtime | None = None) -> Ran:
    """Invoke ``weatherbot`` with arguments and a runtime."""
    result = CliRunner().invoke(app, list(args), obj=rt or runtime(), catch_exceptions=False)
    return Ran(
        result.exit_code, ANSI_ESCAPE.sub("", result.stdout), ANSI_ESCAPE.sub("", result.stderr)
    )


def add_landmark(name: str, key: str, *extra: str) -> Ran:
    """Add a landmark through ``locations add``."""
    lat, lon = landmark(key)
    return run(["locations", "add", name, "--lat", lat, "--lon", lon, *extra])


def parse[M: BaseModel](ran: Ran, model: type[M]) -> M:
    """Validate a command's document against its committed schema, then parse it."""
    name = next(key for key, value in DOCUMENTS.items() if value is model)
    validate(name, ran.json())
    return model.model_validate_json(ran.stdout)


def urls(router: respx.MockRouter) -> list[str]:
    """The URLs a router answered so far, in order (read inside its ``with`` block)."""
    return [str(call.request.url) for call in router.calls]  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType, reportUnknownVariableType] - respx's call list is untyped


def validate(name: str, document: dict[str, object]) -> None:
    """Validate a document against its committed schema in docs/schema/."""
    Draft202012Validator(committed_schema(name)).validate(document)  # pyright: ignore[reportUnknownMemberType] - the stubs leave validate's arguments open
    assert json_schema(name) == committed_schema(name)


def committed_schema(name: str) -> dict[str, object]:
    """Read a committed schema."""
    path = REPOSITORY_ROOT / "docs" / "schema" / f"{name}.schema.json"
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded  # pyright: ignore[reportUnknownVariableType] - a JSON object
