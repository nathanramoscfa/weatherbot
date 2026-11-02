# tests/cli/test_brief_command.py
"""``weatherbot brief``: the label, the sections, the notice, the document, the ledger, the exits.

The locations are assessed by ``status`` over the recorded answers, then briefed through
a runtime whose Anthropic client replays hand-written streams through the real SDK. No
test skips: every one runs offline.
"""

import dataclasses
import json
import os
from typing import Any

from ai_support import RecordedAnswer, chunked_stream, load_answer, replay_client
from cli_support import MIAMI, NASSAU, Ran, add_landmark, parse, recorded_services, run, runtime

from weatherbot.cli.documents import BriefDocument
from weatherbot.cli.runtime import Runtime
from weatherbot.services.disclaimer import NOTICE

USAGE = 2
LABEL = "AI briefing · Claude Sonnet 5.5 · for the assessment of "
BRIEFING: dict[str, Any] = {
    "situation": "The tropics hold one hurricane, far to the west.",
    "what_it_means_here": "Weatherbot's engine decided the location's level from the products.",
    "timeline": [
        {"when": "2026-10-16T18:00Z", "what": "The storm passes far away.", "sources": []}
    ],
    "actions": ["Normal activities.", "Follow the instructions of your local officials."],
    "sources": [],
}


def _answer(**changes: object) -> RecordedAnswer:
    return RecordedAnswer.events(chunked_stream(json.dumps(BRIEFING | changes)))


def _assessed(*names: str) -> None:
    keys = {MIAMI: "miami-dade", NASSAU: "nassau"}
    with recorded_services():
        for name in names:
            assert add_landmark(name, keys[name]).exit_code == 0
        assert run(["status", "--json"]).exit_code == 0


def _runtime(answers: list[RecordedAnswer], **options: Any) -> tuple[Runtime, Any]:  # noqa: ANN401 - runtime's options
    client, replay = replay_client(answers)
    return dataclasses.replace(runtime(**options), make_claude=lambda: client), replay


def _brief(args: list[str], answers: list[RecordedAnswer], **options: Any) -> tuple[Ran, Any]:  # noqa: ANN401 - runtime's options
    rt, replay = _runtime(answers, **options)
    return run(["brief", *args], rt), replay


def test_brief_prints_the_label_the_sections_and_the_notice_last() -> None:
    _assessed(MIAMI)

    ran, replay = _brief([MIAMI], [_answer()])

    assert ran.exit_code == 0, ran.stderr
    lines = ran.stdout.splitlines()
    label = next(line for line in lines if line.startswith(LABEL))
    assert label.endswith(" UTC · not an official product")
    for heading in ("Situation", "What it means here", "Timeline", "Actions", "Sources"):
        assert heading in lines
    assert f"  {BRIEFING['situation']}" in lines
    assert "  2026-10-16T18:00Z: The storm passes far away." in lines
    assert lines.index(label) < lines.index("Situation") < lines.index("Actions")
    assert lines[-1] == NOTICE
    assert len(replay.requests) == 1


def test_brief_in_a_terminal_prints_the_same_text_in_rich() -> None:
    _assessed(MIAMI)

    ran, _ = _brief([MIAMI], [_answer()], terminal=True, width=200)

    assert ran.exit_code == 0
    assert LABEL in ran.stdout
    assert BRIEFING["what_it_means_here"] in ran.stdout
    assert ran.stdout.rstrip().endswith(NOTICE)


def test_a_stored_briefing_is_reused_without_a_request() -> None:
    _assessed(MIAMI)
    rt, replay = _runtime([_answer()])
    run(["brief", MIAMI], rt)

    again = run(["brief", MIAMI], rt)

    assert again.exit_code == 0
    assert "(A stored briefing, written " in again.stdout
    assert "no request was sent" in again.stdout
    assert len(replay.requests) == 1


def test_brief_without_a_location_briefs_every_one_in_turn() -> None:
    _assessed(MIAMI, NASSAU)

    ran, replay = _brief([], [_answer(), _answer()])

    assert ran.exit_code == 0, ran.stderr
    assert ran.stdout.count(LABEL) == 2  # noqa: PLR2004 - both landmarks
    assert ran.stdout.index(MIAMI) < ran.stdout.index(NASSAU)
    assert len(replay.requests) == 2  # noqa: PLR2004 - one request per location


def test_brief_json_validates_against_its_schema() -> None:
    _assessed(MIAMI)

    ran, _ = _brief([MIAMI, "--json"], [_answer()])

    assert ran.exit_code == 0
    document = parse(ran, BriefDocument)
    [entry] = document.data.briefings
    assert (entry.location, entry.status, entry.reused) == (MIAMI, "ok", False)
    assert entry.model == "claude-sonnet-5-5"
    assert entry.prompt_version is not None
    assert len(entry.prompt_version) == 64  # noqa: PLR2004 - a SHA-256
    assert entry.briefing is not None
    assert entry.briefing.situation == BRIEFING["situation"]
    assert entry.cost_micro_usd is not None
    assert entry.cost_micro_usd > 0
    assert entry.sources
    assert all(source.key.startswith("S") for source in entry.sources)
    assert document.data.today.requests == 1
    assert [kind.kind for kind in document.data.today.by_kind] == ["briefing"]
    assert document.disclaimer == NOTICE


def test_brief_cost_prints_the_ledger_and_sends_nothing() -> None:
    _assessed(MIAMI)
    rt, replay = _runtime([_answer()])
    run(["brief", MIAMI], rt)

    ran = run(["brief", "--cost"], rt)
    document = run(["brief", "--cost", "--json"], rt)

    assert ran.exit_code == 0
    assert "AI spend today (" in ran.stdout
    assert "of $1.00 (cap $1.00, allowance $0.00)" in ran.stdout
    assert "Requests and tokens by kind" in ran.stdout
    assert "briefing" in ran.stdout
    parsed = parse(document, BriefDocument)
    assert parsed.data.briefings == ()
    assert parsed.data.today.requests == 1
    assert len(replay.requests) == 1


def test_a_withheld_briefing_exits_1_and_says_to_disregard_the_sections_above() -> None:
    _assessed(MIAMI)
    bad: list[dict[str, object]] = [{"when": "soon", "what": "Level 5 now.", "sources": []}]

    ran, _ = _brief([MIAMI], [_answer(timeline=bad)])

    assert ran.exit_code == 1
    assert "Withheld: level (timeline states a level the engine did not)" in ran.stdout
    assert "disregard the sections above" in ran.stdout
    assert "Level 5 now" not in ran.stdout
    assert ran.stdout.splitlines()[-1] == NOTICE


def test_a_withheld_briefing_is_in_the_document_with_its_reason() -> None:
    _assessed(MIAMI)

    ran, _ = _brief([MIAMI, "--json"], [_answer(situation="Read www.example.invalid.")])

    assert ran.exit_code == 1
    [entry] = parse(ran, BriefDocument).data.briefings
    assert (entry.status, entry.withheld_reason, entry.briefing) == ("withheld", "url", None)
    assert entry.cost_micro_usd is not None


def test_ai_turned_off_is_unavailable_and_exits_1() -> None:
    _assessed(MIAMI)
    # The whole environment, so the paths stay in the test's temporary directories.
    environ = {**os.environ, "WEATHERBOT_AI_ENABLED": "false"}

    ran, replay = _brief([MIAMI], [], environ=environ)

    assert ran.exit_code == 1
    assert "AI unavailable: AI is turned off by [ai] enabled" in ran.stdout
    assert replay.requests == []


def test_a_location_without_an_assessment_is_unavailable() -> None:
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")

    ran, _ = _brief([MIAMI, "--json"], [])

    assert ran.exit_code == 1
    [entry] = parse(ran, BriefDocument).data.briefings
    assert (entry.status, entry.unavailable_reason) == ("unavailable", "no_assessment")


def test_an_unknown_location_or_none_stored_is_a_usage_error() -> None:
    ran, _ = _brief([MIAMI], [])
    assert ran.exit_code == USAGE
    assert "no location is stored" in ran.stderr

    _assessed(MIAMI)
    ran, _ = _brief(["Nowhere"], [])
    assert ran.exit_code == USAGE
    assert "no location is named 'Nowhere'" in ran.stderr


# brief --outlook ---------------------------------------------------------------------------

NARRATION_LABEL = "AI interpretation of the official graphic · Claude Sonnet 5.5 · NHC's "
NARRATION_ON = "WEATHERBOT_AI_OUTLOOK_NARRATION"


def test_brief_outlook_is_off_by_default_and_sends_nothing() -> None:
    _assessed(MIAMI)

    ran, replay = _brief(["--outlook", "atl"], [load_answer("narration-atl-7d0")])

    assert ran.exit_code == 1
    assert "AI unavailable: outlook narration is off; set outlook_narration = true" in ran.stdout
    assert replay.requests == []


def test_brief_outlook_prints_the_label_the_narration_and_the_notice_last() -> None:
    _assessed(MIAMI)
    environ = {**os.environ, NARRATION_ON: "true"}

    ran, replay = _brief(["--outlook", "atl"], [load_answer("narration-atl-7d0")], environ=environ)

    assert ran.exit_code == 0, ran.stderr
    lines = ran.stdout.splitlines()
    label = next(line for line in lines if line.startswith(NARRATION_LABEL))
    assert "Atlantic outlook over seven days, with its TWO of 2026-10-12 23:02 UTC" in label
    assert label.endswith(" · not an official product")
    for heading in ("Summary", "Areas", "Caveat"):
        assert heading in lines
    assert any(line.endswith(" Chance: 20%.") for line in lines)
    assert lines[-1] == NOTICE
    assert len(replay.requests) == 1


def test_brief_outlook_json_carries_the_narration_entry() -> None:
    _assessed(MIAMI)
    environ = {**os.environ, NARRATION_ON: "true"}

    ran, _ = _brief(
        ["--outlook", "pac", "--horizon", "2d0", "--json"],
        [load_answer("narration-pac-2d0")],
        environ=environ,
    )

    assert ran.exit_code == 0
    document = parse(ran, BriefDocument)
    entry = document.data.narration
    assert entry is not None
    assert (entry.basin, entry.horizon, entry.status, entry.reused) == ("pac", "2d0", "ok", False)
    assert entry.label == "AI interpretation of the official graphic"
    assert entry.narration is not None
    assert [area.chance_text for area in entry.narration.areas] == ["100%"]
    assert entry.cost_micro_usd is not None
    assert entry.graphic_sha256 is not None
    assert document.data.briefings == ()
    assert [kind.kind for kind in document.data.today.by_kind] == ["narration"]


def test_a_stored_narration_is_reused_without_a_request() -> None:
    _assessed(MIAMI)
    environ = {**os.environ, NARRATION_ON: "true"}
    rt, replay = _runtime([load_answer("narration-atl-7d0")], environ=environ)
    run(["brief", "--outlook", "atl"], rt)

    again = run(["brief", "--outlook", "atl"], rt)

    assert again.exit_code == 0
    assert "(A stored narration, written " in again.stdout
    assert len(replay.requests) == 1


def test_brief_a_location_and_an_outlook_together_is_a_usage_error() -> None:
    _assessed(MIAMI)

    ran, _ = _brief([MIAMI, "--outlook", "atl"], [])

    assert ran.exit_code == USAGE
    assert "brief a location or an outlook, not both" in ran.stderr
