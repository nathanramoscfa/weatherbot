# tests/scripts/test_record_ai_fixtures.py
"""``scripts/record_ai_fixtures.py`` over a replay: bodies only, no overwrite, a budget."""

import json
from datetime import date
from pathlib import Path

import anthropic
import httpx2
import pytest
from ai_support import HEADER_NAMES, event_stream, fake_api_key, message_body

import record_ai_fixtures as recorder
from weatherbot.services.ai.pricing import TokenUsage, cost_micro_usd

TODAY = date(2026, 11, 1)
ANSWER = json.dumps(message_body('{"word": "ready"}')).encode()
STREAM = event_stream('{"word": "ready"}').encode()


class Wire:
    """Answers like Anthropic would, with headers a recording must never keep."""

    def __init__(self) -> None:
        """Start with no request seen."""
        self.requests: list[httpx2.Request] = []

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        """Answer one request: a stream when it asks for one, else a message."""
        self.requests.append(request)
        streamed = json.loads(request.content).get("stream") is True
        headers = {
            "content-type": "text/event-stream" if streamed else "application/json",
            "request-id": "req_synthetic",
            "anthropic-organization-id": "org-synthetic",
        }
        return httpx2.Response(200, content=STREAM if streamed else ANSWER, headers=headers)


@pytest.fixture
def recordings(tmp_path: Path) -> Path:
    return tmp_path / "fixtures-ai"


def _client(transport: httpx2.AsyncBaseTransport) -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(
        api_key=fake_api_key(),
        max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=transport),
    )


def _record(
    directory: Path, wire: Wire, *names: str, force: bool = False
) -> list[recorder.Recorded]:
    return recorder.record(
        list(names),
        directory=directory,
        force=force,
        today=TODAY,
        client_factory=_client,
        inner=httpx2.MockTransport(wire.handler),
    )


def test_the_recorder_writes_bodies_exactly_as_received_and_a_manifest(recordings: Path) -> None:
    wire = Wire()

    results = _record(recordings, wire, "round-trip", "round-trip-stream")

    assert (recordings / "round-trip.json").read_bytes() == ANSWER
    assert (recordings / "round-trip-stream.sse").read_bytes() == STREAM
    manifest = json.loads((recordings / "manifest.json").read_text(encoding="utf-8"))
    assert [entry["case"] for entry in manifest] == ["round-trip", "round-trip-stream"]
    assert manifest[0] == {
        "case": "round-trip",
        "kind": "parse",
        "model": "claude-sonnet-5-5",
        "date": "2026-11-01",
        "request_sha256": results[0].entry["request_sha256"],
        "bytes": len(ANSWER),
    }
    synthetic = cost_micro_usd("claude-sonnet-5-5", TokenUsage(input_tokens=20, output_tokens=5))
    assert [result.cost_micro_usd for result in results] == [synthetic, synthetic]
    assert len(wire.requests) == len(results)


def test_the_recorder_sends_the_callers_request_body(recordings: Path) -> None:
    wire = Wire()

    _record(recordings, wire, "round-trip")
    body = json.loads(wire.requests[0].content)

    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["output_config"]["effort"] == "low"
    assert not {"temperature", "top_p", "top_k"} & set(body)


def test_no_header_reaches_a_recording(recordings: Path) -> None:
    _record(recordings, Wire(), "round-trip", "round-trip-stream")

    for path in recordings.iterdir():
        text = path.read_text(encoding="utf-8").lower()
        assert not [name for name in HEADER_NAMES if name in text], path.name
        assert fake_api_key() not in text


def test_the_recorder_refuses_to_overwrite_without_force(recordings: Path) -> None:
    wire = Wire()
    _record(recordings, wire, "round-trip")

    with pytest.raises(recorder.RecordingError, match="without --force"):
        _record(recordings, wire, "round-trip")
    assert len(wire.requests) == 1

    _record(recordings, wire, "round-trip", force=True)
    assert len(wire.requests) == 2  # noqa: PLR2004 - the first and the forced recording


def test_the_recorder_writes_nothing_past_the_budget(recordings: Path) -> None:
    recordings.mkdir()
    (recordings / "large.bin").write_bytes(b"\0" * (recorder.BUDGET_BYTES - 100))

    with pytest.raises(recorder.RecordingError, match="budget"):
        _record(recordings, Wire(), "round-trip")

    assert sorted(path.name for path in recordings.iterdir()) == ["large.bin"]


def test_an_unknown_case_is_refused_before_any_request(recordings: Path) -> None:
    wire = Wire()

    with pytest.raises(recorder.RecordingError, match="round-trip"):
        _record(recordings, wire, "every-case")
    assert wire.requests == []


def test_list_names_the_cases(capsys: pytest.CaptureFixture[str]) -> None:
    assert recorder.main(["--list"]) == 0

    out = capsys.readouterr().out
    assert "round-trip  (parse" in out
    assert "round-trip-stream  (stream" in out


def test_a_refusal_exits_1_without_a_traceback(capsys: pytest.CaptureFixture[str]) -> None:
    assert recorder.main([]) == 1

    assert capsys.readouterr().err.startswith("error: name one or more cases")


def test_the_scenario_cases_are_ten_briefings_and_two_summaries() -> None:
    cases = recorder.scenario_cases()

    briefings = [name for name, case in cases.items() if case.kind == "stream"]
    summaries = [name for name, case in cases.items() if case.kind == "parse"]
    assert len(briefings) == 10  # noqa: PLR2004 - five scenarios, two landmarks
    assert summaries == ["scenario-landfall-miami-dade-summary", "scenario-landfall-nassau-summary"]
    assert all(name.startswith("scenario-") for name in cases)
    assert set(cases) <= set(recorder.all_cases())
    assert recorder.scenario_names("quiet") == [
        "scenario-quiet-miami-dade",
        "scenario-quiet-nassau",
    ]
    assert len(recorder.scenario_names("all")) == 12  # noqa: PLR2004 - the twelve requests
    assert recorder.resolve(["scenario"]).keys() == cases.keys()


def test_a_scenario_recording_refuses_without_a_credential_before_anything(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert recorder.main(["--scenario", "all"]) == 1

    captured = capsys.readouterr()
    assert captured.err.startswith("error: no Anthropic credential")
    assert "nothing was sent" in captured.err
    assert "requests" not in captured.out


def test_a_declined_plan_sends_nothing(recordings: Path) -> None:
    wire = Wire()
    plans: list[recorder.ScenarioPlan] = []

    def decline(plan: recorder.ScenarioPlan) -> bool:
        plans.append(plan)
        return False

    with pytest.raises(recorder.RecordingError, match="declined"):
        recorder.record(
            ["scenario-quiet-miami-dade"],
            directory=recordings,
            today=TODAY,
            client_factory=_client,
            inner=httpx2.MockTransport(wire.handler),
            confirm=decline,
        )

    assert wire.requests == []
    assert not recordings.exists()
    (plan,) = plans
    assert (plan.requests, plan.briefings, plan.summaries) == (1, 1, 0)
    assert plan.hard_ceiling_micro_usd > recorder.WORST_REQUEST_MICRO_USD
