# tests/services/test_doctor_ai.py
"""``doctor``'s ``ai`` check: every state, no request offline, and no secret or path."""

import asyncio
import dataclasses
import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime

import anthropic
import pytest
from ai_support import RecordedAnswer, Replay, fake_api_key, replay_client
from cli_support import run, runtime

from weatherbot.services.ai.client import default_client
from weatherbot.services.config import AiSettings, AppPaths
from weatherbot.services.doctor import Check, ai_check
from weatherbot.services.persistence.database import Database, open_database

NOW = datetime(2026, 10, 31, 15, 0, tzinfo=UTC)
KEYED = {"ANTHROPIC_API_KEY": "set-for-the-test"}


@pytest.fixture
def database() -> Iterator[Database]:
    with open_database(AppPaths.resolve()) as opened:
        yield opened


def _check(
    database: Database | None,
    *,
    settings: AiSettings | None = None,
    environ: dict[str, str] | None = None,
    answers: list[RecordedAnswer] | None = None,
    offline: bool = False,
) -> tuple[Check, Replay]:
    client, replay = replay_client(answers or [])
    check = asyncio.run(
        ai_check(
            database,
            settings or AiSettings(),
            factory=lambda: client,
            environ=KEYED if environ is None else environ,
            now=lambda: NOW,
            offline=offline,
        )
    )
    return check, replay


def _clean(check: Check) -> None:
    assert fake_api_key() not in check.detail
    assert "set-for-the-test" not in check.detail
    assert "\\" not in check.detail
    assert "/" not in check.detail


def test_a_closed_database_skips() -> None:
    check, replay = _check(None)

    assert (check.name, check.status) == ("ai", "skip")
    assert replay.requests == []


def test_ai_turned_off_skips_without_a_client(database: Database) -> None:
    check, replay = _check(database, settings=AiSettings(enabled=False))

    assert (check.status, check.detail) == ("skip", "turned off by [ai] enabled")
    assert replay.requests == []


def test_no_credential_skips_and_names_the_two_routes(database: Database) -> None:
    check = asyncio.run(
        ai_check(
            database,
            AiSettings(),
            factory=default_client,
            environ={},
            now=lambda: NOW,
            offline=False,
        )
    )

    assert check.status == "skip"
    assert "ANTHROPIC_API_KEY" in check.detail
    assert "ant auth login" in check.detail
    assert "everything but AI works without one" in check.detail
    assert "blank" not in check.detail


def test_a_blank_key_is_noted(database: Database) -> None:
    check = asyncio.run(
        ai_check(
            database,
            AiSettings(),
            factory=default_client,
            environ={"ANTHROPIC_API_KEY": ""},
            now=lambda: NOW,
            offline=True,
        )
    )

    assert check.status == "skip"
    assert check.detail.endswith("ANTHROPIC_API_KEY is set but blank")


def test_offline_passes_on_presence_and_sends_nothing(database: Database) -> None:
    check, replay = _check(database, offline=True)

    assert check.status == "pass"
    assert check.detail == (
        "credential from the environment (ANTHROPIC_API_KEY); $0.00 of $1.00 today"
    )
    assert replay.requests == []
    _clean(check)


def test_online_passes_after_one_free_probe(database: Database) -> None:
    check, replay = _check(database, answers=[RecordedAnswer.json({"input_tokens": 8})])

    assert check.status == "pass"
    assert check.detail.endswith("; authenticated")
    assert [request.path for request in replay.requests] == ["/v1/messages/count_tokens"]
    _clean(check)


def test_a_profile_is_named_as_a_profile(database: Database) -> None:
    check, _ = _check(database, environ={}, offline=True)

    assert check.detail.startswith("credential from an ant auth login profile;")


def test_a_failed_probe_fails_with_its_reason_only(database: Database) -> None:
    check, _ = _check(database, answers=[RecordedAnswer.error(401, "authentication_error")])

    assert check.status == "fail"
    assert check.detail.startswith("the probe failed (auth_failed)")
    assert "synthetic" not in check.detail
    _clean(check)


def test_an_unpriced_model_fails(database: Database) -> None:
    settings = AiSettings.model_construct(
        enabled=True,
        model="claude-unpriced",
        summary_model="claude-sonnet-5-5",
        daily_cap_usd=1.0,
        change_summaries=True,
        outlook_narration=False,
    )

    check, replay = _check(database, settings=settings)

    assert check.status == "fail"
    assert "price table" in check.detail
    assert replay.requests == []


def test_doctor_offline_json_on_a_fresh_database_exits_0_with_ai_skipped() -> None:
    result = run(["doctor", "--offline", "--json"])

    assert result.exit_code == 0
    checks = {check["name"]: check for check in json.loads(result.stdout)["data"]["checks"]}
    assert checks["ai"]["status"] == "skip"
    assert "no Anthropic credential" in checks["ai"]["detail"]


def test_doctor_names_only_the_source() -> None:
    client, replay = replay_client([])
    key = fake_api_key()
    # The key reaches doctor through the runtime's environment, never os.environ.
    environ = {**os.environ, "ANTHROPIC_API_KEY": key}
    rt = dataclasses.replace(runtime(environ=environ), make_claude=lambda: client)

    result = run(["doctor", "--offline", "--json"], rt)
    checks = {check["name"]: check for check in json.loads(result.stdout)["data"]["checks"]}

    assert checks["ai"]["status"] == "pass"
    assert "the environment (ANTHROPIC_API_KEY)" in checks["ai"]["detail"]
    assert key not in result.stdout
    assert key not in result.stderr
    assert replay.requests == []
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_doctor_json_fails_ai_online_when_anthropic_refuses_the_credential() -> None:
    # The authentication alarm, as the operator's doctor would show it (Phase 6 Step 6).
    client, replay = replay_client([RecordedAnswer.error(401, "authentication_error")])
    key = fake_api_key()
    environ = {**os.environ, "ANTHROPIC_API_KEY": key}
    rt = dataclasses.replace(runtime(environ=environ), make_claude=lambda: client)

    result = run(["doctor", "--json"], rt)
    checks = {check["name"]: check for check in json.loads(result.stdout)["data"]["checks"]}

    assert result.exit_code == 1
    assert checks["ai"]["status"] == "fail"
    assert checks["ai"]["detail"].startswith("the probe failed (auth_failed)")
    assert "the environment (ANTHROPIC_API_KEY)" in checks["ai"]["detail"]
    assert [request.path for request in replay.requests] == ["/v1/messages/count_tokens"]
    assert key not in result.stdout
    assert key not in result.stderr
    assert "synthetic" not in result.stdout


def test_the_sdk_raises_credentials_error_without_a_credential() -> None:
    with pytest.raises(anthropic.CredentialsError):
        default_client()
