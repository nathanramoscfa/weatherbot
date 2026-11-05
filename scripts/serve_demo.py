# scripts/serve_demo.py
"""Offline demonstration server for the Playwright browser smoke and the idle CPU measurement.

Runs ``weatherbot serve``'s monitor and web server (through ``cli/serve.py``'s ``_loop``)
in a temporary data directory with both public landmarks stored (``"simulated Miami-Dade"``
and ``"Parliament Square"``), every request answered by recorded fixtures through ``respx``
(and any other refused), ``--port`` (default 8799), ``--corpus DIR``,
``--roster-interval-minutes`` (1 for the smoke; the default keeps production's intervals,
for the idle measurement), and ``--switch-file PATH`` (once that file exists, the roster
serves the next advisory and the forecast zone serves the synthetic Hurricane Warning,
reusing ``scripts/simulate_advisory.py``'s simulation). Prints its process id and address,
and one line per roster poll and per cycle; removes its temporary directory on exit; and
writes nothing in the checkout.

The AI answers from recordings: ``--ai-replay`` (on by default; ``--no-ai-replay`` turns
AI off) hands ``serve`` a real SDK client whose transport replays ``tests/fixtures/ai/``
by request kind (a briefing by its location, a change summary, each chat round of a
recorded turn, a narration by its basin, a ``count_tokens`` probe), pacing each stream so
its sections arrive one by one; ``--ai-cap-usd`` sets today's cap (0.001 is below the
smallest request's ceiling, so the state reads ``capped``); and ``--ai-fail-auth`` answers
every request 401, as Anthropic does for a refused credential, so the third holds AI at
``auth_failed``. Every ``ANTHROPIC_*`` variable is removed and the SDK's profile directory
points at an empty one, so no credential is read and nothing leaves the machine. The
recordings answered the eval set's cases, so their text describes those cases (Parliament
Square's briefing is Dorian's first advisory there), and the validators still judge each
one against the demonstration's own context: an answer that fails them is withheld.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Final, cast

import anthropic
import httpx
import httpx2

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from weatherbot.models import Snapshot
    from weatherbot.services.monitor import CycleResult, CycleTrigger
    from weatherbot.services.persistence.database import Database
    from weatherbot.sources.http import Fetcher, ValidatorStore

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
for _extra in (
    REPO_ROOT / "src",
    REPO_ROOT / "scripts",
    REPO_ROOT / "tests" / "ai",
    REPO_ROOT / "tests" / "cli",
    REPO_ROOT / "tests" / "services",
    REPO_ROOT / "tests" / "sources",
    REPO_ROOT / "tests" / "contract",
):
    _text = str(_extra)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from ai_support import RecordedAnswer, fake_api_key, load_answer, load_rounds  # noqa: E402
from cli_support import (  # noqa: E402
    CORPUS,
    NASSAU,
    ROSTER_URL,
    add_landmark,
    directory,
    quiet_fetcher,
    recorded_services,
    runtime,
)
from source_support import NOW, entry  # noqa: E402

from simulate_advisory import (  # noqa: E402
    FORECAST_ALERTS_URL,
    SIMULATED_MIAMI,
    hurricane_warning_response,
    next_advisory_roster,
)
from synthetic_surge import (  # noqa: E402
    PEAK_SURGE_LINES_URL,
    PEAK_SURGE_POLYGONS_URL,
    synthetic_surge_lines_response,
    synthetic_surge_polygons_response,
)
from weatherbot.cli.runtime import EXIT_OK, Context  # noqa: E402
from weatherbot.cli.serve import _loop  # noqa: E402  # pyright: ignore[reportPrivateUsage]
from weatherbot.services.config import AppPaths, Settings, load_settings  # noqa: E402
from weatherbot.services.monitor import MonitorService  # noqa: E402
from weatherbot.services.notifications import LogChannel  # noqa: E402
from weatherbot.services.persistence.database import open_database  # noqa: E402
from weatherbot.services.replay import ReplayCorpus  # noqa: E402
from weatherbot.services.schedule import MonitorSchedule  # noqa: E402

DEFAULT_PORT: Final = 8799
REPLAYED_BRIEFINGS: Final = {NASSAU: "eval-briefing-al052019-001-nassau"}
"""The recorded briefing a landmark's request is answered with, by the name it carries: the
landmark's own level-1 case, whose source keys all exist in the demonstration's context."""
OTHER_BRIEFING: Final = "eval-briefing-recorded-miami-dade"
"""Any other location's briefing; the validators withhold it (its sources differ)."""
REPLAYED_SUMMARY: Final = "eval-summary-al112017-036-miami-dade"
"""Every change summary: the recorded rise to level 5, as the switch file's escalation is."""
REPLAYED_CHAT: Final = "chat-one-round"
"""Every chat turn: one lookup, then the answer."""
REPLAYED_NARRATIONS: Final = {"eastern North Pacific": "narration-pac-2d0"}
"""A narration by the basin its task line names; any other basin's is the Atlantic one."""
OTHER_NARRATION: Final = "narration-atl-7d0"
STREAM_SECONDS: Final = 3.0
"""How long a replayed stream takes, so a page sees its sections arrive one by one."""
PROBE_TOKENS: Final = 9
"""A ``count_tokens`` probe's answer."""


@dataclass
class DemoReplay:
    """Answers each Anthropic request from ``tests/fixtures/ai/`` by its kind, never the network.

    A briefing is answered by the location its context names, a change summary and a chat
    turn by one recording each (a chat request's round is the number of assistant messages
    after its question), a narration by its basin, and a ``count_tokens`` probe with a
    count. With ``fail_auth`` every request is answered 401 ``authentication_error``.
    Streams are paced over ``stream_seconds``. Only the kind of each request is kept.
    """

    fail_auth: bool = False
    stream_seconds: float = STREAM_SECONDS
    kinds: list[str] = field(default_factory=list[str])

    async def handler(self, request: httpx2.Request) -> httpx2.Response:
        """Answer one request with its recorded answer.

        Args:
            request: The SDK's request.

        Returns:
            The answer; a stream's events arrive paced.
        """
        body = cast("dict[str, object]", json.loads(request.content) if request.content else {})
        kind = request_kind(request.url.path, body)
        self.kinds.append(kind)
        if self.fail_auth:
            return _response(RecordedAnswer.error(401, "authentication_error"))
        if kind == "count_tokens":
            return _response(RecordedAnswer.json({"input_tokens": PROBE_TOKENS}))
        answer = self.answer(kind, body)
        if answer.content_type != "text/event-stream":
            return _response(answer)
        headers = {"content-type": answer.content_type, "request-id": str(answer.request_id)}
        return httpx2.Response(200, content=self._paced(answer.body), headers=headers)

    def answer(self, kind: str, body: dict[str, object]) -> RecordedAnswer:
        """Choose the recording that answers a request of a kind.

        Args:
            kind: ``briefing``, ``summary``, ``chat``, or ``narration``.
            body: The request's body.

        Returns:
            The recorded answer.
        """
        text = json.dumps(body.get("messages", []))
        if kind == "briefing":
            name = next(
                (case for place, case in REPLAYED_BRIEFINGS.items() if place in text),
                OTHER_BRIEFING,
            )
            return load_answer(name)
        if kind == "summary":
            return load_answer(REPLAYED_SUMMARY)
        if kind == "chat":
            rounds = load_rounds(REPLAYED_CHAT)
            return rounds[min(chat_round(body), len(rounds) - 1)]
        name = next(
            (case for basin, case in REPLAYED_NARRATIONS.items() if basin in text),
            OTHER_NARRATION,
        )
        return load_answer(name)

    async def _paced(self, body: bytes) -> AsyncIterator[bytes]:
        events = [f"{event}\n\n".encode() for event in body.decode("utf-8").split("\n\n") if event]
        pause = self.stream_seconds / max(len(events), 1)
        for event in events:
            await asyncio.sleep(pause)
            yield event


def _response(answer: RecordedAnswer) -> httpx2.Response:
    headers = {"content-type": answer.content_type}
    if answer.request_id is not None:
        headers["request-id"] = answer.request_id
    return httpx2.Response(answer.status, content=answer.body, headers=headers)


def request_kind(path: str, body: dict[str, object]) -> str:
    """Name a request's kind from its path and body, as the services build them.

    Args:
        path: The request's URL path.
        body: Its decoded body.

    Returns:
        ``count_tokens``, ``chat`` (it carries tools), or by its output schema
        ``briefing``, ``summary``, or ``narration``.
    """
    if path.endswith("/count_tokens"):
        return "count_tokens"
    if "tools" in body:
        return "chat"
    config = cast("dict[str, object]", body.get("output_config") or {})
    output = cast("dict[str, object]", config.get("format") or {})
    schema = cast("dict[str, object]", output.get("schema") or {})
    properties = cast("dict[str, object]", schema.get("properties") or {})
    if "situation" in properties:
        return "briefing"
    if "areas" in properties:
        return "narration"
    return "summary"


def chat_round(body: dict[str, object]) -> int:
    """Count a chat request's round: the assistant messages after the turn's question.

    Args:
        body: The request's decoded body.

    Returns:
        0 for the turn's first request, 1 after one tool round, and so on.
    """
    messages = cast("list[dict[str, object]]", body.get("messages", []))
    rounds = 0
    for message in messages:
        content = message.get("content")
        blocks = cast("list[dict[str, object]]", content if isinstance(content, list) else [])
        asks = isinstance(content, str) or any(block.get("type") == "text" for block in blocks)
        if message.get("role") == "user" and asks:
            rounds = 0
        elif message.get("role") == "assistant":
            rounds += 1
    return rounds


def demo_claude(replay: DemoReplay) -> Callable[[], anthropic.AsyncAnthropic]:
    """Build the factory ``serve`` asks for its client: one replaying client, every time.

    Args:
        replay: Answers every request.

    Returns:
        The factory; its key is built at run time and never sent anywhere.
    """
    client = anthropic.AsyncAnthropic(
        api_key=fake_api_key(),
        max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(
            transport=httpx2.MockTransport(replay.handler), follow_redirects=False
        ),
    )
    return lambda: client


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="Loopback TCP port to bind (default: 8799; 0 picks a free port).",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=CORPUS,
        help="Replay corpus directory to open (default: tests/fixtures/replay).",
    )
    parser.add_argument(
        "--roster-interval-minutes",
        type=int,
        default=None,
        help="Override roster poll intervals in minutes (1 for smoke; default keeps production).",
    )
    parser.add_argument(
        "--switch-file",
        type=Path,
        default=None,
        help="When this file exists, serve advisory 023 and the synthetic Hurricane Warning.",
    )
    parser.add_argument(
        "--ai-replay",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Answer AI requests from tests/fixtures/ai (default); --no-ai-replay turns AI off.",
    )
    parser.add_argument(
        "--ai-cap-usd",
        type=float,
        default=None,
        help="Today's AI cap in dollars (0.001 reads capped at once; default keeps $1.00).",
    )
    parser.add_argument(
        "--ai-fail-auth",
        action="store_true",
        help="Answer every AI request 401, as Anthropic does for a refused credential.",
    )
    return parser.parse_args(argv)


def _baseline_roster_response() -> httpx.Response:
    capture = directory("nhc-current-storms")
    (item,) = capture.entries
    return httpx.Response(
        200,
        content=capture.payload(item),
        headers={"content-type": "application/json"},
    )


def _baseline_forecast_alerts_response() -> httpx.Response:
    capture = directory("nws-alerts-zone")
    item = entry(capture, "alerts-zone-FLZ173.geojson")
    return httpx.Response(
        200,
        content=capture.payload(item),
        headers={"content-type": "application/geo+json"},
    )


class _ServeAddressHandler(logging.Handler):
    """Emits ``pid=<pid> address=<address>`` once ``cli/serve.py`` logs its address."""

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.printed = False

    def emit(self, record: logging.LogRecord) -> None:
        if self.printed:
            return
        msg = record.getMessage()
        prefix = "dashboard at "
        if msg.startswith(prefix):
            address = msg.removeprefix(prefix).strip()
            self.printed = True
            print(f"pid={os.getpid()} address={address}", flush=True)


def _install_demo_instrumentation() -> Callable[[], None]:
    """Wrap ``MonitorSchedule`` and ``MonitorService`` to print roster polls and cycles."""
    original_init = MonitorSchedule.__init__
    original_run_roster = MonitorSchedule.run_roster
    original_run_cycle = MonitorService.run_cycle
    first_schedule_created = False

    def _wrapped_init(  # type: ignore[no-untyped-def]
        self: MonitorSchedule, *args: object, **kwargs: object
    ) -> None:
        nonlocal first_schedule_created
        if first_schedule_created:
            # The initial startup cycle already ran before WebServer bound its socket,
            # so ``_loop``'s MonitorSchedule starts with its startup cycle satisfied.
            kwargs["run_startup"] = False
        first_schedule_created = True
        original_init(self, *args, **kwargs)  # type: ignore[arg-type]

    async def _wrapped_run_roster(self: MonitorSchedule, now: datetime) -> None:
        await original_run_roster(self, now)
        print(f"roster_poll at={now.isoformat()}", flush=True)

    async def _wrapped_run_cycle(
        self: MonitorService,
        trigger: CycleTrigger,
        *,
        snapshot: Snapshot | None = None,
        assess: bool = True,
    ) -> CycleResult:
        result = await original_run_cycle(self, trigger, snapshot=snapshot, assess=assess)
        print(
            f"cycle id={result.cycle_id} trigger={result.trigger} status={result.status}",
            flush=True,
        )
        return result

    MonitorSchedule.__init__ = _wrapped_init  # type: ignore[method-assign]
    MonitorSchedule.run_roster = _wrapped_run_roster  # type: ignore[method-assign]
    MonitorService.run_cycle = _wrapped_run_cycle  # type: ignore[method-assign]

    def _restore() -> None:
        MonitorSchedule.__init__ = original_init  # type: ignore[method-assign]
        MonitorSchedule.run_roster = original_run_roster  # type: ignore[method-assign]
        MonitorService.run_cycle = original_run_cycle  # type: ignore[method-assign]

    return _restore


def _configure_demo_environ(root: Path, args: argparse.Namespace) -> None:
    # No credential reaches the demonstration: the replay answers every AI request.
    for variable in [name for name in os.environ if name.startswith("ANTHROPIC_")]:
        del os.environ[variable]
    profiles = root / "anthropic"
    profiles.mkdir(parents=True, exist_ok=True)
    os.environ["ANTHROPIC_CONFIG_DIR"] = str(profiles)
    os.environ["WEATHERBOT_DATA_DIR"] = str(root / "data")
    os.environ["WEATHERBOT_CONFIG_DIR"] = str(root / "config")
    os.environ["WEATHERBOT_WEB_PORT"] = str(int(args.port))
    os.environ["WEATHERBOT_NOTIFICATIONS_TOAST"] = "false"
    os.environ["WEATHERBOT_AI_ENABLED"] = "true" if args.ai_replay else "false"
    if args.ai_cap_usd is not None:
        os.environ["WEATHERBOT_AI_DAILY_CAP_USD"] = str(float(args.ai_cap_usd))
    if args.roster_interval_minutes is not None:
        interval_text = str(int(args.roster_interval_minutes))
        os.environ["WEATHERBOT_MONITOR_ROSTER_INTERVAL_MINUTES"] = interval_text
        os.environ["WEATHERBOT_MONITOR_ROSTER_INTERVAL_RELEVANT_MINUTES"] = interval_text


def _run_serve_loop(  # noqa: PLR0913 - the open database, its settings, and the demo's seams
    database: Database,
    paths: AppPaths,
    settings: Settings,
    clock: Callable[[], datetime],
    corpus: ReplayCorpus | None,
    *,
    replay: DemoReplay,
) -> None:
    def _make_demo_fetcher(
        client: httpx.AsyncClient,
        validators: ValidatorStore,
        *,
        now: datetime = NOW,
    ) -> Fetcher:
        return quiet_fetcher(client, validators, now=clock() if now == NOW else now)

    rt = runtime(now=NOW, environ=dict(os.environ))
    object.__setattr__(rt, "now", clock)
    object.__setattr__(rt, "make_fetcher", _make_demo_fetcher)
    object.__setattr__(rt, "make_claude", demo_claude(replay))

    # Run the initial startup cycle before the web server binds its port so
    # assessments, snapshot, and heartbeats are ready on the first request.
    initial_schedule = MonitorSchedule(
        database.engine,
        paths,
        settings=settings,
        runner="serve",
        clock=clock,
        make_fetcher=rt.make_fetcher,
        channels=(LogChannel(), rt.make_toast(settings)),
        run_startup=True,
    )
    asyncio.run(initial_schedule.run_startup(clock()))

    context = Context(
        runtime=rt,
        paths=paths,
        settings=settings,
    )

    async def _run_with_sigbreak() -> None:
        loop = asyncio.get_running_loop()
        sigbreak = getattr(signal, "SIGBREAK", None)
        if sigbreak is not None:
            with contextlib.suppress(ValueError, OSError):
                signal.signal(
                    sigbreak,
                    lambda _s, _f: loop.call_soon_threadsafe(signal.raise_signal, signal.SIGINT),
                )
        await _loop(
            context,
            database,
            paths,
            "serve",
            open_browser=False,
            corpus=corpus,
        )

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_run_with_sigbreak())


def main(argv: list[str] | None = None) -> int:
    """Run the recorded demonstration server until interrupted."""
    args = _parse_args(argv)
    start_monotonic = time.monotonic()

    def clock() -> datetime:
        return NOW + timedelta(seconds=max(0.0, time.monotonic() - start_monotonic))

    switch_file: Path | None = args.switch_file
    corpus_dir: Path | None = args.corpus
    corpus = (
        ReplayCorpus.open(corpus_dir) if corpus_dir is not None and corpus_dir.is_dir() else None
    )

    baseline_roster = _baseline_roster_response()
    next_roster = httpx.Response(
        200,
        content=next_advisory_roster(),
        headers={"content-type": "application/json"},
    )
    baseline_alerts = _baseline_forecast_alerts_response()

    def _is_switched() -> bool:
        return switch_file is not None and switch_file.exists()

    def _roster_side_effect(_request: httpx.Request) -> httpx.Response:
        return next_roster if _is_switched() else baseline_roster

    def _alerts_side_effect(_request: httpx.Request) -> httpx.Response:
        return hurricane_warning_response(clock()) if _is_switched() else baseline_alerts

    restore_instrumentation = _install_demo_instrumentation()
    serve_logger = logging.getLogger("weatherbot.cli.serve")
    address_handler = _ServeAddressHandler()
    serve_logger.addHandler(address_handler)
    serve_logger.setLevel(logging.INFO)

    try:
        with TemporaryDirectory(prefix="weatherbot-serve-demo-") as tmp:
            _configure_demo_environ(Path(tmp), args)
            with recorded_services() as router:
                router.get(ROSTER_URL).mock(side_effect=_roster_side_effect)
                router.get(FORECAST_ALERTS_URL).mock(side_effect=_alerts_side_effect)
                router.get(PEAK_SURGE_POLYGONS_URL).mock(
                    return_value=synthetic_surge_polygons_response()
                )
                router.get(PEAK_SURGE_LINES_URL).mock(return_value=synthetic_surge_lines_response())

                ran_miami = add_landmark(SIMULATED_MIAMI, "miami-dade", "--polygon", "forecast")
                if ran_miami.exit_code != EXIT_OK:
                    return ran_miami.exit_code
                ran_nassau = add_landmark(NASSAU, "nassau")
                if ran_nassau.exit_code != EXIT_OK:
                    return ran_nassau.exit_code

                paths = AppPaths.resolve(os.environ)
                settings = load_settings(paths, os.environ)
                replay = DemoReplay(fail_auth=bool(args.ai_fail_auth))
                with open_database(paths) as database:
                    _run_serve_loop(database, paths, settings, clock, corpus, replay=replay)
        return EXIT_OK
    finally:
        serve_logger.removeHandler(address_handler)
        restore_instrumentation()


if __name__ == "__main__":
    raise SystemExit(main())
