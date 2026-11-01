# tests/ai/test_ai_client.py
"""Where the credential comes from, never what it is, and the AI's state machine."""

import asyncio
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import anthropic
import pytest
from ai_support import MODEL, RecordedAnswer, fake_api_key, ledger_rows, replay_client
from sqlalchemy import Engine

from weatherbot.services.ai.client import (
    SOURCE_TEXT,
    blank_key,
    credential_source,
    default_client,
    has_credential,
)
from weatherbot.services.ai.errors import AUTH_HOLD, AiUnavailable
from weatherbot.services.ai.guard import ai_engine
from weatherbot.services.ai.service import AiService, smallest_ceiling
from weatherbot.services.config import AiSettings, AppPaths
from weatherbot.services.persistence.database import open_database

NOW = datetime(2026, 10, 31, 15, 0, tzinfo=UTC)
PROBE_TOKENS = 9


class Clock:
    """A clock a test moves by hand."""

    def __init__(self) -> None:
        """Start at ``NOW``."""
        self.at = NOW

    def __call__(self) -> datetime:
        """Read the clock."""
        return self.at


def _profile_client() -> anthropic.AsyncAnthropic:
    """A client the factory can construct without either variable: a profile's stand-in."""
    client, _ = replay_client([])
    return client


@pytest.fixture
def engine() -> Iterator[Engine]:
    with open_database(AppPaths.resolve()) as database:
        guarded = ai_engine(database.path)
        yield guarded
        guarded.dispose()


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({"ANTHROPIC_API_KEY": "set"}, "environment"),
        ({"ANTHROPIC_API_KEY": "set", "ANTHROPIC_AUTH_TOKEN": "set"}, "environment"),
        ({"ANTHROPIC_AUTH_TOKEN": "set"}, "auth_token"),
        ({"ANTHROPIC_API_KEY": "", "ANTHROPIC_AUTH_TOKEN": "set"}, "auth_token"),
        ({"ANTHROPIC_API_KEY": "   "}, "environment"),
    ],
)
def test_a_variable_names_the_source_without_constructing_a_client(
    environ: dict[str, str], expected: str
) -> None:
    def refuse() -> anthropic.AsyncAnthropic:
        raise AssertionError

    assert credential_source(environ, refuse) == expected


def test_no_variable_and_no_profile_is_none(capsys: pytest.CaptureFixture[str]) -> None:
    # tests/conftest.py clears every ANTHROPIC_* variable and empties the profile directory.
    assert credential_source({}, default_client) == "none"
    assert capsys.readouterr() == ("", "")


def test_a_blank_key_is_unset_so_a_profile_still_applies() -> None:
    assert credential_source({"ANTHROPIC_API_KEY": ""}, _profile_client) == "profile"
    assert credential_source({"ANTHROPIC_API_KEY": ""}, default_client) == "none"
    assert blank_key({"ANTHROPIC_API_KEY": ""})
    assert blank_key({"ANTHROPIC_API_KEY": "  "})
    assert not blank_key({"ANTHROPIC_API_KEY": "set"})
    assert not blank_key({})


def _unresolved_client() -> anthropic.AsyncAnthropic:
    """What the SDK builds with no credential and no profile directory at all."""
    return cast(
        "anthropic.AsyncAnthropic", SimpleNamespace(api_key=None, auth_token=None, credentials=None)
    )


def test_a_client_that_resolved_no_credential_is_none() -> None:
    assert not has_credential(_unresolved_client())
    assert has_credential(_profile_client())
    assert credential_source({}, _unresolved_client) == "none"


def test_a_client_with_no_credential_is_never_used(engine: Engine) -> None:
    service = AiService(
        engine, AiSettings(), factory=_unresolved_client, environ={}, now=Clock(), local_zone=UTC
    )

    assert service.state().reason == "no_credential"
    with pytest.raises(AiUnavailable) as error:
        service.caller()
    assert error.value.reason == "no_credential"


def test_the_source_text_never_holds_a_value_or_a_path() -> None:
    texts = " ".join(SOURCE_TEXT.values())

    assert "sk-" not in texts
    assert "\\" not in texts
    assert "/" not in texts


def test_resolving_the_source_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    key = fake_api_key()

    credential_source({"ANTHROPIC_API_KEY": key}, _profile_client)
    credential_source({}, _profile_client)

    assert key not in caplog.text
    assert not [r for r in caplog.records if r.name.startswith("anthropic")]


def _service(
    engine: Engine,
    *,
    settings: AiSettings | None = None,
    environ: dict[str, str] | None = None,
    answers: list[RecordedAnswer] | None = None,
    clock: Clock | None = None,
) -> AiService:
    client, _ = replay_client(answers or [])
    return AiService(
        engine,
        settings or AiSettings(),
        factory=lambda: client,
        environ=environ if environ is not None else {"ANTHROPIC_API_KEY": fake_api_key()},
        now=clock or Clock(),
        local_zone=UTC,
    )


def test_disabled_is_off_and_never_constructs_a_client(engine: Engine) -> None:
    built: list[object] = []

    def factory() -> anthropic.AsyncAnthropic:
        built.append(1)
        raise AssertionError

    service = AiService(
        engine, AiSettings(enabled=False), factory=factory, environ={}, now=Clock(), local_zone=UTC
    )
    state = service.state()

    assert (state.state, state.reason, state.credential) == ("off", "disabled", None)
    with pytest.raises(AiUnavailable, match="turned off"):
        service.caller()
    assert built == []


def test_no_credential_is_off(engine: Engine) -> None:
    service = AiService(
        engine, AiSettings(), factory=default_client, environ={}, now=Clock(), local_zone=UTC
    )

    state = service.state()

    assert (state.state, state.reason, state.credential) == ("off", "no_credential", "none")
    with pytest.raises(AiUnavailable) as error:
        service.caller()
    assert error.value.reason == "no_credential"


def test_an_empty_key_with_no_profile_is_off(engine: Engine) -> None:
    service = AiService(
        engine,
        AiSettings(),
        factory=default_client,
        environ={"ANTHROPIC_API_KEY": ""},
        now=Clock(),
        local_zone=UTC,
    )

    assert service.state().reason == "no_credential"


def test_a_key_is_ready_with_todays_spend(engine: Engine) -> None:
    state = _service(engine).state()

    assert (state.state, state.reason, state.credential) == ("ready", None, "environment")
    assert (state.model, state.summary_model) == (MODEL, MODEL)
    assert (state.change_summaries, state.outlook_narration) == (True, False)
    assert (state.today.spent_micro_usd, state.today.cap_micro_usd) == (0, 1_000_000)


def test_a_profile_is_ready(engine: Engine) -> None:
    assert _service(engine, environ={}).state().credential == "profile"


def test_the_pause_reads_paused(engine: Engine) -> None:
    service = _service(engine)
    service.ledger.pause()

    assert (service.state().state, service.state().reason) == ("paused", "paused")


def test_headroom_below_the_smallest_request_reads_capped(engine: Engine) -> None:
    smallest = smallest_ceiling(MODEL)
    service = _service(engine, settings=AiSettings(daily_cap_usd=(smallest - 1) / 1_000_000))

    assert (service.state().state, service.state().reason) == ("capped", "capped")


def test_a_cheaper_summary_model_lowers_the_smallest_request(engine: Engine) -> None:
    cap = smallest_ceiling(MODEL) - 1
    service = _service(
        engine,
        settings=AiSettings(daily_cap_usd=cap / 1_000_000, summary_model="claude-haiku-5-5"),
    )

    assert service.state().state == "ready"


def test_an_unpriced_model_is_unavailable(engine: Engine) -> None:
    settings = AiSettings.model_construct(
        enabled=True,
        model="claude-unpriced",
        summary_model=MODEL,
        daily_cap_usd=1.0,
        change_summaries=True,
        outlook_narration=False,
    )

    state = _service(engine, settings=settings).state()

    assert (state.state, state.reason) == ("unavailable", "price_unknown")


def test_three_authentication_failures_read_unavailable_until_a_success(engine: Engine) -> None:
    clock = Clock()
    unauthorized = RecordedAnswer.error(401, "authentication_error")
    ok = RecordedAnswer.json(
        {
            "id": "msg_synthetic",
            "type": "message",
            "role": "assistant",
            "model": MODEL,
            "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 5, "output_tokens": 1},
        }
    )
    service = _service(engine, answers=[unauthorized] * 3 + [ok], clock=clock)
    params = {"max_tokens": 16, "messages": [{"role": "user", "content": "hi"}]}

    async def send() -> None:
        await service.caller().create(
            kind="chat", model=MODEL, location=None, prompt_version=None, params=params
        )

    for _ in range(3):
        with pytest.raises(AiUnavailable):
            asyncio.run(send())
    held = service.state()
    clock.at = NOW + AUTH_HOLD
    asyncio.run(send())

    assert (held.state, held.reason) == ("unavailable", "auth_failed")
    assert service.state().state == "ready"
    assert [row.status for row in ledger_rows(engine)] == ["failed", "failed", "failed", "ok"]


def test_the_client_is_constructed_once_and_closed(engine: Engine) -> None:
    built: list[anthropic.AsyncAnthropic] = []

    def factory() -> anthropic.AsyncAnthropic:
        client, _ = replay_client([])
        built.append(client)
        return client

    service = AiService(
        engine,
        AiSettings(),
        factory=factory,
        environ={"ANTHROPIC_API_KEY": fake_api_key()},
        now=Clock(),
        local_zone=UTC,
    )
    first = service.caller()
    second = service.caller()
    asyncio.run(service.close())

    assert first is second
    assert len(built) == 1
    assert built[0].is_closed()


def test_the_probe_is_free_and_unrecorded(engine: Engine) -> None:
    service = _service(engine, answers=[RecordedAnswer.json({"input_tokens": PROBE_TOKENS})])

    counted = asyncio.run(service.probe())

    assert counted == PROBE_TOKENS
    assert ledger_rows(engine) == []


def test_a_failed_probe_names_its_reason_only(engine: Engine) -> None:
    service = _service(engine, answers=[RecordedAnswer.error(401, "authentication_error")])

    with pytest.raises(AiUnavailable) as error:
        asyncio.run(service.probe())

    assert error.value.reason == "auth_failed"
    assert "synthetic" not in str(error.value)
