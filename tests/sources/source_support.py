# tests/sources/source_support.py
"""Helpers the source-client tests share: a fake clock, a quiet fetcher, recorded answers."""

import asyncio
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
import respx
from fixture_support import CaptureDirectory, as_object, latest_live

from weatherbot.models import SourceId, StormSummary
from weatherbot.sources.http import Fetcher, FetchResult, HostPacer
from weatherbot.sources.nhc_current_storms import parse_current_storms

NOW = datetime(2026, 10, 13, 1, 30, tzinfo=UTC)
LAYER_NOTE = re.compile(r"layer '(?P<name>.+)', id \d+")


@dataclass
class FakeClock:
    """A monotonic clock that only moves when something sleeps on it."""

    now: float = 0.0
    sleeps: list[float] = field(default_factory=list[float])

    def __call__(self) -> float:
        """Read the clock."""
        return self.now

    async def sleep(self, seconds: float) -> None:
        """Advance the clock instead of waiting, and let other tasks run."""
        self.sleeps.append(seconds)
        self.now += seconds
        await asyncio.sleep(0)


@dataclass
class Quiet:
    """A fetcher whose pacing and backoff waits are recorded, never slept."""

    clock: FakeClock = field(default_factory=FakeClock)
    backoff: FakeClock = field(default_factory=FakeClock)

    def fetcher(self, client: httpx.AsyncClient) -> Fetcher:
        """Build a fetcher on this clock, with a jitter fraction of one half."""
        return Fetcher(
            client,
            pacer=HostPacer(clock=self.clock, sleep=self.clock.sleep),
            sleep=self.backoff.sleep,
            jitter=lambda: 0.5,
            now=lambda: NOW,
            clock=self.clock,
        )


def recorded(source: SourceId) -> CaptureDirectory:
    """Return the newest live capture directory of a source."""
    directory = latest_live(source)
    assert directory is not None, f"{source} has no live capture"
    return directory


def entry(directory: CaptureDirectory, name: str) -> dict[str, object]:
    """Return the manifest entry of a stored file."""
    return next(item for item in directory.entries if item["file"] == name)


def layer_name(item: Mapping[str, object]) -> str | None:
    """Return the layer a query or count capture is of, from the manifest's note."""
    found = LAYER_NOTE.fullmatch(str(item.get("notes", "")))
    return found["name"] if found else None


def recorded_result(directory: CaptureDirectory, item: dict[str, object]) -> FetchResult:
    """Rebuild the answer a capture recorded."""
    body = directory.payload(item)
    return FetchResult(
        source_id=directory.source,  # pyright: ignore[reportArgumentType] - a register id
        url=str(item["url"]),
        status=int(str(item["status"])),
        body=body,
        headers={str(k): str(v) for k, v in as_object(item["headers"]).items()},
        fetched_at=datetime.fromisoformat(str(item["fetched_at"])),
        sha256=hashlib.sha256(body).hexdigest(),
    )


def recorded_storms() -> tuple[StormSummary, ...]:
    """Parse the recorded roster."""
    directory = recorded("nhc-current-storms")
    result = recorded_result(directory, entry(directory, "CurrentStorms.json"))
    return parse_current_storms(result.body, result.provenance())


def recorded_roster_document() -> dict[str, object]:
    """Return the recorded roster as parsed JSON, for tests that edit a copy."""
    directory = recorded("nhc-current-storms")
    return as_object(json.loads(directory.payload(entry(directory, "CurrentStorms.json"))))


def serve(router: respx.MockRouter, directory: CaptureDirectory) -> None:
    """Answer every URL a capture directory recorded with the recorded bytes and headers."""
    for item in directory.entries:
        headers = {
            str(k): str(v)
            for k, v in as_object(item["headers"]).items()
            if k not in {"content-length", "content-encoding"}
        }
        router.get(str(item["url"])).mock(
            return_value=httpx.Response(
                int(str(item["status"])), content=directory.payload(item), headers=headers
            )
        )
