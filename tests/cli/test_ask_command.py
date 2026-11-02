# tests/cli/test_ask_command.py
"""``weatherbot ask``: the label, the tools, the sentences, the notice, the document, the exits.

The locations are assessed by ``status`` over the recorded answers, then asked about
through a runtime whose Anthropic client replays the recorded chat turn or hand-written
streams through the real SDK. No test skips: every one runs offline.
"""

import dataclasses
import json
import os
from typing import Any

from ai_support import (
    RecordedAnswer,
    chunked_stream,
    load_rounds,
    recorded_tool_names,
    replay_client,
    tool_stream,
)
from cli_support import MIAMI, NASSAU, Ran, add_landmark, parse, recorded_services, run, runtime
from eval.chat_cases import chat_case

from weatherbot.cli.ask import QUESTION_LIMIT
from weatherbot.cli.documents import AskDocument
from weatherbot.cli.runtime import Runtime
from weatherbot.services.ai import chat as chat_module
from weatherbot.services.disclaimer import NOTICE

USAGE = 2
LABEL = "AI answer · Claude Sonnet 5.5 · from Weatherbot's stored data · not an official product"
QUESTION = "What is the official level here, and why?"
ANSWER = f"{MIAMI} is at least level 1, All Clear. No rule matched."


def _assessed(*names: str) -> None:
    keys = {MIAMI: "miami-dade", NASSAU: "nassau"}
    with recorded_services():
        for name in names:
            assert add_landmark(name, keys[name]).exit_code == 0
        assert run(["status", "--json"]).exit_code == 0


def _runtime(answers: list[RecordedAnswer], **options: Any) -> tuple[Runtime, Any]:  # noqa: ANN401 - runtime's options
    client, replay = replay_client(answers)
    return dataclasses.replace(runtime(**options), make_claude=lambda: client), replay


def _ask(args: list[str], answers: list[RecordedAnswer], **options: Any) -> tuple[Ran, Any]:  # noqa: ANN401 - runtime's options
    rt, replay = _runtime(answers, **options)
    return run(["ask", *args], rt), replay


def _lookup_then(text: str) -> list[RecordedAnswer]:
    return [
        RecordedAnswer.events(tool_stream(("get_evidence", {"location": MIAMI}))),
        RecordedAnswer.events(chunked_stream(text)),
    ]


def test_ask_prints_the_label_the_tools_the_sentences_and_the_notice_last() -> None:
    _assessed(MIAMI)

    ran, replay = _ask([QUESTION, "--location", MIAMI], _lookup_then(ANSWER))

    assert ran.exit_code == 0, ran.stderr
    lines = ran.stdout.splitlines()
    assert lines[0] == LABEL
    assert f"{MIAMI} is at least level 1, All Clear." in lines
    assert "No rule matched." in lines
    assert lines[-1] == NOTICE
    assert "looked up: get_evidence" in ran.stderr
    assert "looked up" not in ran.stdout
    assert len(replay.requests) == 2  # noqa: PLR2004 - a lookup, then the answer


def test_ask_replays_a_recorded_turn_after_its_tool_round() -> None:
    _assessed(MIAMI, NASSAU)
    case = chat_case("chat-one-round")

    ran, replay = _ask([case.question, "--location", MIAMI], load_rounds(case.name))

    assert ran.exit_code == 0, ran.stderr
    assert ran.stdout.splitlines()[0] == LABEL
    assert f"{MIAMI} is at least level 1, All Clear" in ran.stdout
    for name in recorded_tool_names(case.name):
        assert f"looked up: {name}" in ran.stderr
    assert ran.stdout.splitlines()[-1] == NOTICE
    assert len(replay.requests) == 2  # noqa: PLR2004 - the recorded rounds


def test_ask_in_a_terminal_prints_the_tools_dimmed_on_standard_output() -> None:
    _assessed(MIAMI)

    ran, _ = _ask([QUESTION], _lookup_then(ANSWER), terminal=True, width=200)

    assert ran.exit_code == 0
    assert LABEL in ran.stdout
    assert "looked up: get_evidence" in ran.stdout
    assert ran.stdout.rstrip().endswith(NOTICE)


def test_ask_json_validates_against_its_schema() -> None:
    _assessed(MIAMI)

    ran, _ = _ask([QUESTION, "--location", MIAMI, "--json"], _lookup_then(ANSWER))

    assert ran.exit_code == 0
    document = parse(ran, AskDocument)
    data = document.data
    assert (data.question, data.location, data.status) == (QUESTION, MIAMI, "ok")
    assert data.answer == ANSWER
    assert data.tools_used == ("get_evidence",)
    assert data.model == "claude-sonnet-5-5"
    assert data.request_ids == ("req_replayed_0001", "req_replayed_0001")
    assert data.cost_micro_usd > 0
    assert (data.withheld_reason, data.unavailable_reason) == (None, None)
    assert document.disclaimer == NOTICE
    assert "looked up" not in ran.stderr


def test_a_withheld_answer_exits_1_and_says_to_disregard_the_answer_above() -> None:
    _assessed(MIAMI)

    ran, _ = _ask([QUESTION], _lookup_then(f"{ANSWER} {MIAMI} is now level 5."))

    assert ran.exit_code == 1
    assert "Withheld: level (the answer states another current level)" in ran.stdout
    assert "disregard the answer above" in ran.stdout
    assert "is now level 5" not in ran.stdout
    assert ran.stdout.splitlines()[-1] == NOTICE


def test_a_withheld_answer_is_in_the_document_without_its_text() -> None:
    _assessed(MIAMI)

    ran, _ = _ask([QUESTION, "--json"], _lookup_then("Read www.example.invalid/x now."))

    assert ran.exit_code == 1
    data = parse(ran, AskDocument).data
    assert (data.status, data.withheld_reason, data.answer) == ("withheld", "url", None)
    assert data.cost_micro_usd > 0


def test_ai_turned_off_is_unavailable_and_exits_1() -> None:
    _assessed(MIAMI)
    # The whole environment, so the paths stay in the test's temporary directories.
    environ = {**os.environ, "WEATHERBOT_AI_ENABLED": "false"}

    ran, replay = _ask([QUESTION], [], environ=environ)

    assert ran.exit_code == 1
    assert "AI unavailable: AI is turned off by [ai] enabled" in ran.stdout
    assert LABEL not in ran.stdout
    assert replay.requests == []


def test_too_many_lookups_is_unavailable_and_in_the_document() -> None:
    _assessed(MIAMI)
    answers = [RecordedAnswer.events(tool_stream(("get_ladder", {}))) for _ in range(6)]

    ran, _ = _ask([QUESTION, "--json"], answers)

    assert ran.exit_code == 1
    data = parse(ran, AskDocument).data
    assert (data.status, data.unavailable_reason) == ("unavailable", "too_many_lookups")
    assert data.tools_used == ("get_ladder",) * 5
    assert len(data.request_ids) == 6  # noqa: PLR2004 - six rounds


def test_a_bad_question_location_or_none_stored_is_a_usage_error() -> None:
    ran, _ = _ask([QUESTION], [])
    assert ran.exit_code == USAGE
    assert "no location is stored" in ran.stderr

    _assessed(MIAMI)
    for question in ("", "   ", "x" * (QUESTION_LIMIT + 1)):
        ran, _ = _ask([question], [])
        assert ran.exit_code == USAGE
        assert "a question is 1 to 2,000 characters" in ran.stderr
    ran, _ = _ask([QUESTION, "--location", "Nowhere"], [])
    assert ran.exit_code == USAGE
    assert "no location is named 'Nowhere'" in ran.stderr


def test_the_question_is_never_logged_even_at_debug() -> None:
    _assessed(MIAMI)
    rt, _ = _runtime(_lookup_then(ANSWER))

    ran = run(["--verbose", "ask", QUESTION], rt)

    assert ran.exit_code == 0
    assert QUESTION not in ran.stderr
    assert json.dumps(QUESTION) not in ran.stderr


def test_the_commands_bound_is_the_chats() -> None:
    assert QUESTION_LIMIT == chat_module.QUESTION_LIMIT
