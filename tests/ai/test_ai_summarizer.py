# tests/ai/test_ai_summarizer.py
"""``ChangeSummarizer``: primed, woken, newest first, one at a time, never a backlog.

The database is a per-module template holding the Miami-Dade landmark, the recorded
snapshot, and its first assessment (whose changes are its initial events, so it never
qualifies). Later assessments drop or restore the recorded alert, so each has a change to
summarize; the answers are hand-written summaries replayed through the real SDK.
"""

import asyncio
import json
import logging
import threading
from collections.abc import Iterator, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from ai_support import (
    RecordedAnswer,
    copied_database,
    database_template,
    ledger_rows,
    message_body,
    output_rows,
    replayed_service,
    shared_recorded_snapshot,
    stored_later,
    stored_recorded,
)
from source_support import NOW

from weatherbot.services.ai.service import AiService
from weatherbot.services.ai.summaries import ChangeSummarizer, ChangeSummaryService
from weatherbot.services.config import AiSettings
from weatherbot.services.persistence.database import Database
from weatherbot.services.persistence.repositories import AssessmentRepository, StoredAssessment

pytestmark = pytest.mark.anyio

MIAMI = "Miami-Dade County Hall"
SUMMARY = json.dumps({"summary": "The rip current statement changed.", "sources": []})


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return database_template(tmp_path_factory.mktemp("summarizer"), stored_recorded)


@pytest.fixture
def database(template: Path) -> Iterator[Database]:
    with copied_database(template) as opened:
        yield opened


class _Published:
    """Records what the summarizer publishes."""

    def __init__(self) -> None:
        self.events: list[tuple[str, Mapping[str, Any] | None, tuple[str, ...], bool]] = []
        self.arrived = asyncio.Event()

    def __call__(
        self,
        event_kind: str,
        data: Mapping[str, Any] | None = None,
        invalidate: Any = (),  # noqa: ANN401 - the hub's query keys
        *,
        deduplicate: bool = False,
    ) -> None:
        self.events.append((event_kind, data, tuple(invalidate), deduplicate))
        self.arrived.set()


class _Ticking:
    """A clock that moves a second each time it is read, so every row has its own instant."""

    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


def _answers(count: int) -> list[RecordedAnswer]:
    return [RecordedAnswer.json(message_body(SUMMARY)) for _ in range(count)]


async def _later(database: Database, number: int, *, alerts: bool) -> StoredAssessment:
    """Store a later assessment, without the recorded alert or with it back."""
    recorded = await shared_recorded_snapshot()
    previous = AssessmentRepository(database.engine).latest(MIAMI)
    assert previous is not None
    changes: dict[str, object] = {} if alerts else {"alerts": {}}
    return stored_later(database, recorded, previous.assessment, number, **changes)


def _summarizer(service: AiService, published: _Published) -> ChangeSummarizer:
    return ChangeSummarizer(ChangeSummaryService(service), service, publish=published)


async def test_priming_marks_the_newest_assessment_so_history_is_never_backfilled(
    database: Database,
) -> None:
    before = await _later(database, 1, alerts=False)
    service, replay = replayed_service(database, _answers(1))
    summarizer = _summarizer(service, _Published())

    mark = await asyncio.to_thread(summarizer.prime)
    nothing = await summarizer.summarize_new()
    after = await _later(database, 2, alerts=True)
    outcomes = await summarizer.summarize_new()
    await service.close()

    assert mark == before.id
    assert nothing == ()
    assert [outcome.status for outcome in outcomes] == ["ok"]
    assert [row.assessment_id for row in output_rows(database.engine)] == [after.id]
    assert len(replay.requests) == 1
    assert summarizer.mark == after.id


async def test_new_assessments_are_summarized_newest_first_one_at_a_time(
    database: Database,
) -> None:
    clock = _Ticking()
    service, replay = replayed_service(database, _answers(2), now=clock)
    summarizer = _summarizer(service, _Published())
    await asyncio.to_thread(summarizer.prime)
    older = await _later(database, 1, alerts=False)
    newer = await _later(database, 2, alerts=True)

    outcomes = await summarizer.summarize_new()
    await service.close()

    assert [outcome.status for outcome in outcomes] == ["ok", "ok"]
    assert [row.assessment_id for row in output_rows(database.engine)] == [newer.id, older.id]
    first, second = ledger_rows(database.engine)
    assert first.finished_at is not None
    assert first.finished_at <= second.started_at
    assert len(replay.requests) == len(outcomes)


async def test_an_assessment_without_a_change_is_skipped_without_a_request(
    database: Database,
) -> None:
    service, replay = replayed_service(database, _answers(1))
    summarizer = _summarizer(service, _Published())
    await asyncio.to_thread(summarizer.prime)
    first = await _later(database, 1, alerts=True)

    outcomes = await summarizer.summarize_new()
    await service.close()

    assert first.changes == ()
    assert [(outcome.status, outcome.reason) for outcome in outcomes] == [("skipped", "no_changes")]
    assert replay.requests == []


@pytest.mark.parametrize(
    ("settings", "pause"),
    [(AiSettings(change_summaries=False), False), (AiSettings(), True)],
    ids=["summaries-off", "paused"],
)
async def test_nothing_is_sent_while_summaries_are_off_or_ai_is_not_ready(
    database: Database, settings: AiSettings, *, pause: bool
) -> None:
    service, replay = replayed_service(database, _answers(1), settings=settings)
    if pause:
        service.ledger.pause()
    summarizer = _summarizer(service, _Published())
    await asyncio.to_thread(summarizer.prime)
    missed = await _later(database, 1, alerts=False)

    outcomes = await summarizer.summarize_new()
    await service.close()

    assert outcomes == ()
    assert replay.requests == []
    assert output_rows(database.engine) == []
    assert summarizer.mark == missed.id


async def test_each_stored_summary_is_published(database: Database) -> None:
    published = _Published()
    service, _ = replayed_service(database, _answers(1))
    summarizer = _summarizer(service, published)
    await asyncio.to_thread(summarizer.prime)
    await _later(database, 1, alerts=False)

    [outcome] = await summarizer.summarize_new()
    await service.close()

    assert published.events == [
        (
            "ai",
            {"output_id": outcome.output_id, "ai_kind": "summary", "location": MIAMI},
            ("briefings",),
            True,
        )
    ]


async def test_no_exception_escapes_and_the_next_pass_still_runs(
    database: Database, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    service, _ = replayed_service(database, _answers(1))
    summaries = ChangeSummaryService(service)
    summarizer = ChangeSummarizer(summaries, service, publish=_Published())
    await asyncio.to_thread(summarizer.prime)
    await _later(database, 1, alerts=False)

    async def failing(_assessment_id: int) -> object:
        message = "a failure (synthetic)"
        raise RuntimeError(message)

    monkeypatch.setattr(summaries, "summarize", failing)
    with caplog.at_level(logging.WARNING, logger="weatherbot.services.ai"):
        failed = await summarizer.summarize_new()
    monkeypatch.undo()
    await _later(database, 2, alerts=True)
    recovered = await summarizer.summarize_new()
    await service.close()

    assert failed == ()
    assert "change summaries failed (RuntimeError)" in caplog.text
    assert "synthetic" not in caplog.text
    assert [outcome.status for outcome in recovered] == ["ok"]


async def test_a_wake_from_another_thread_runs_a_pass(database: Database) -> None:
    published = _Published()
    service, replay = replayed_service(database, _answers(1))
    summarizer = _summarizer(service, published)
    await asyncio.to_thread(summarizer.prime)
    stop = asyncio.Event()
    running = asyncio.create_task(summarizer.run(stop))
    await asyncio.sleep(0)
    await _later(database, 1, alerts=False)

    waker = threading.Thread(target=summarizer.wake)
    waker.start()
    waker.join()
    await asyncio.wait_for(published.arrived.wait(), timeout=10)
    stop.set()
    await asyncio.wait_for(running, timeout=5)
    await service.close()

    assert len(replay.requests) == 1
    assert running.exception() is None
