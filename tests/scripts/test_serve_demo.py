# tests/scripts/test_serve_demo.py
"""Offline tests for ``scripts/serve_demo.py``: arguments, the switch file, and the AI replay."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anthropic
import pytest
from ai_support import FIXTURES, load_rounds, stream_blocks
from source_support import NOW

from weatherbot.services.ai.caller import request_kwargs
from weatherbot.services.ai.schemas import Briefing, ChangeSummary, OutlookNarration

if TYPE_CHECKING:
    from pydantic import BaseModel

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from serve_demo import (  # noqa: E402
    DEFAULT_PORT,
    REPLAYED_BRIEFINGS,
    REPLAYED_CHAT,
    REPLAYED_SUMMARY,
    DemoReplay,
    _baseline_forecast_alerts_response,  # pyright: ignore[reportPrivateUsage]
    _baseline_roster_response,  # pyright: ignore[reportPrivateUsage]
    _configure_demo_environ,  # pyright: ignore[reportPrivateUsage]
    _parse_args,  # pyright: ignore[reportPrivateUsage]
    _ServeAddressHandler,  # pyright: ignore[reportPrivateUsage]
    chat_round,
    demo_claude,
    request_kind,
)
from simulate_advisory import (  # noqa: E402
    hurricane_warning_response,
    next_advisory_roster,
)

MODEL = "claude-sonnet-5-5"


def _body(output: type[BaseModel] | None = None, **extra: Any) -> dict[str, Any]:  # noqa: ANN401 - request fields of any shape
    params: dict[str, Any] = {"max_tokens": 64, "messages": [{"role": "user", "content": "hi"}]}
    params.update(extra)
    return request_kwargs(params, output) if output is not None else params


def _text(message: anthropic.types.Message) -> str:
    return "".join(block.text for block in message.content if block.type == "text")


def test_parse_args_defaults_and_overrides(tmp_path: Path) -> None:
    defaults = _parse_args([])
    assert defaults.port == DEFAULT_PORT
    assert defaults.roster_interval_minutes is None
    assert defaults.switch_file is None
    assert defaults.ai_replay is True
    assert defaults.ai_cap_usd is None
    assert defaults.ai_fail_auth is False
    assert defaults.retention_days is None

    ai = _parse_args(
        ["--no-ai-replay", "--ai-cap-usd", "0.001", "--ai-fail-auth", "--retention-days", "30"]
    )
    assert ai.ai_replay is False
    assert ai.ai_cap_usd == 0.001  # noqa: PLR2004 - the smoke's tiny cap
    assert ai.ai_fail_auth is True
    assert ai.retention_days == 30  # noqa: PLR2004 - idle measurement's retention days

    switch_file = tmp_path / "switch.flag"
    corpus_dir = tmp_path / "corpus"
    overridden = _parse_args(
        [
            "--port",
            "0",
            "--corpus",
            str(corpus_dir),
            "--roster-interval-minutes",
            "1",
            "--switch-file",
            str(switch_file),
        ]
    )
    assert overridden.port == 0
    assert overridden.corpus == corpus_dir
    assert overridden.roster_interval_minutes == 1
    assert overridden.switch_file == switch_file


def test_baseline_and_switched_responses_serve_advisory_023_and_hurricane_warning() -> None:
    baseline_roster = json.loads(_baseline_roster_response().content)
    switched_roster = json.loads(next_advisory_roster())
    assert baseline_roster["activeStorms"][0]["publicAdvisory"]["advNum"] == "022a"
    assert switched_roster["activeStorms"][0]["publicAdvisory"]["advNum"] == "023"

    baseline_alerts = json.loads(_baseline_forecast_alerts_response().content)
    switched_alerts = json.loads(hurricane_warning_response(NOW).content)
    assert baseline_alerts["features"][0]["properties"]["event"] != "Hurricane Warning"
    assert len(switched_alerts["features"]) == 1
    assert switched_alerts["features"][0]["properties"]["event"] == "Hurricane Warning"


def test_serve_address_handler_emits_pid_and_address_once(
    capsys: pytest.CaptureFixture[str],
) -> None:
    handler = _ServeAddressHandler()
    logger = logging.getLogger("test.serve_demo.address")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info("unrelated message")
        logger.info("dashboard at http://127.0.0.1:8799")
        logger.info("dashboard at http://127.0.0.1:8799")
    finally:
        logger.removeHandler(handler)

    captured = capsys.readouterr()
    lines = [line.strip() for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1
    assert lines[0].startswith("pid=")
    assert lines[0].endswith("address=http://127.0.0.1:8799")


def test_the_demo_environment_drops_every_credential_and_sets_the_ai_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environ = {"ANTHROPIC_API_KEY": "set-for-the-test", "ANTHROPIC_AUTH_TOKEN": "x", "PATH": "p"}
    monkeypatch.setattr(os, "environ", environ)

    _configure_demo_environ(tmp_path, _parse_args(["--ai-cap-usd", "0.001"]))

    assert {name for name in environ if name.startswith("ANTHROPIC_")} == {"ANTHROPIC_CONFIG_DIR"}
    assert Path(environ["ANTHROPIC_CONFIG_DIR"]).is_dir()
    assert list(Path(environ["ANTHROPIC_CONFIG_DIR"]).iterdir()) == []
    assert environ["WEATHERBOT_AI_ENABLED"] == "true"
    assert environ["WEATHERBOT_AI_DAILY_CAP_USD"] == "0.001"

    _configure_demo_environ(tmp_path, _parse_args(["--no-ai-replay", "--retention-days", "30"]))
    assert environ["WEATHERBOT_AI_ENABLED"] == "false"
    assert "WEATHERBOT_RETENTION_HISTORY_DAYS" not in environ
    toml_path = tmp_path / "config" / "weatherbot.toml"
    assert toml_path.read_text(encoding="utf-8") == "[retention]\nhistory_days = 30\n"


def test_each_request_kind_is_named_from_its_path_and_body() -> None:
    assert request_kind("/v1/messages/count_tokens", _body()) == "count_tokens"
    assert request_kind("/v1/messages", _body(tools=[{"name": "get_storms"}])) == "chat"
    assert request_kind("/v1/messages", _body(Briefing)) == "briefing"
    assert request_kind("/v1/messages", _body(ChangeSummary)) == "summary"
    assert request_kind("/v1/messages", _body(OutlookNarration)) == "narration"


def test_a_chat_round_counts_the_assistant_messages_after_its_question() -> None:
    question = {"role": "user", "content": [{"type": "text", "text": "Which storms?"}]}
    asked = {"role": "assistant", "content": [{"type": "tool_use", "name": "get_storms"}]}
    answered = {"role": "user", "content": [{"type": "tool_result", "content": "{}"}]}
    replied = {"role": "assistant", "content": [{"type": "text", "text": "Simon."}]}

    assert chat_round({"messages": [question]}) == 0
    assert chat_round({"messages": [question, asked, answered]}) == 1
    assert chat_round({"messages": [question, asked, answered, asked, answered]}) == 2  # noqa: PLR2004 - the third round
    assert chat_round({"messages": [question, asked, answered, replied, question]}) == 0


def test_the_replay_answers_each_kind_through_the_real_sdk_and_sends_nothing() -> None:
    replay = DemoReplay(stream_seconds=0.0)
    client = demo_claude(replay)()
    (landmark, recording) = next(iter(REPLAYED_BRIEFINGS.items()))
    asking: anthropic.types.MessageParam = {
        "role": "user",
        "content": f'{{"location":"{landmark}"}}',
    }

    async def exchange() -> tuple[int, str, str, str]:
        counted = await client.messages.count_tokens(model=MODEL, messages=[asking])
        summary = await client.messages.create(model=MODEL, stream=False, **_body(ChangeSummary))
        briefing_body = _body(Briefing)
        briefing_body["messages"] = [asking]
        async with client.messages.stream(model=MODEL, **briefing_body) as stream:
            briefing = await stream.get_final_message()
        chat_body = _body(tools=[{"name": "get_assessment"}])
        async with client.messages.stream(model=MODEL, **chat_body) as stream:
            first = await stream.get_final_message()
        await client.close()
        return counted.input_tokens, _text(summary), _text(briefing), first.stop_reason or ""

    tokens, summary, briefing, stop = asyncio.run(exchange())

    recorded_summary = json.loads((FIXTURES / f"{REPLAYED_SUMMARY}.json").read_text("utf-8"))
    assert tokens > 0
    assert summary == recorded_summary["content"][-1]["text"]
    assert json.loads(briefing) == json.loads(
        "".join(
            str(block["text"])
            for block in stream_blocks((FIXTURES / f"{recording}.sse").read_text("utf-8"))
            if block["type"] == "text"
        )
    )
    first_round = stream_blocks(load_rounds(REPLAYED_CHAT)[0].body.decode("utf-8"))
    assert stop == "tool_use"
    assert any(block["type"] == "tool_use" for block in first_round)
    assert replay.kinds == ["count_tokens", "summary", "briefing", "chat"]


def test_with_fail_auth_every_request_is_refused_as_an_authentication_failure() -> None:
    replay = DemoReplay(fail_auth=True)
    client = demo_claude(replay)()

    async def refused() -> None:
        try:
            await client.messages.create(model=MODEL, stream=False, **_body(Briefing))
        finally:
            await client.close()

    with pytest.raises(anthropic.AuthenticationError):
        asyncio.run(refused())
    assert replay.kinds == ["briefing"]
