# tests/ai/test_ai_redaction.py
"""No log record or traceback carries a key, and the SDK's loggers stay silent at DEBUG."""

import asyncio
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import override

import pytest
from ai_support import MODEL, RecordedAnswer, fake_api_key, message_body, replay_client
from sqlalchemy import Engine

from weatherbot.services.ai.caller import AiCaller
from weatherbot.services.ai.guard import ai_engine
from weatherbot.services.ai.ledger import Ledger
from weatherbot.services.config import AppPaths
from weatherbot.services.logs import (
    QUIET_LIBRARIES,
    SILENT_LIBRARIES,
    configure_logging,
    redact_secrets,
)
from weatherbot.services.persistence.database import open_database

QUESTION = "Is the storm near the lighthouse at Cape Florida?"
NOW = datetime(2026, 10, 31, 15, 0, tzinfo=UTC)
LOGGER = logging.getLogger("weatherbot.tests.redaction")


class Everything(logging.Handler):
    """Keeps every record any logger emits, formatted."""

    def __init__(self) -> None:
        """Keep everything, from DEBUG up."""
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    @override
    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def text(self) -> str:
        """Every kept record's message, one per line."""
        return "\n".join(record.getMessage() for record in self.records)


def _fail(error: Exception) -> None:
    raise error


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    yield
    configure_logging("WARNING")


@pytest.mark.parametrize(
    "template",
    [
        "the key is {key}",
        "Authorization: Bearer {key}",
        "headers {{'authorization': 'Bearer {key}', 'x-api-key': '{key}'}}",
        "X-Api-Key: {key}",
        "ANTHROPIC_API_KEY={key}",
    ],
)
def test_a_secret_never_survives_redaction(template: str) -> None:
    key = fake_api_key()

    redacted = redact_secrets(template.format(key=key))

    assert key not in redacted
    assert "<redacted>" in redacted


def test_an_authorization_value_without_a_key_shape_is_redacted() -> None:
    assert redact_secrets("authorization: Bearer opaque.token.value") == "authorization: <redacted>"


def test_text_without_a_secret_is_unchanged() -> None:
    text = "the authorization flow completed; x-api-key header absent"

    assert redact_secrets(text) == text


def test_a_record_on_standard_error_loses_the_key(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("DEBUG")
    key = fake_api_key()

    messages = ("debug %s", "Authorization: Bearer %s")
    LOGGER.debug(messages[0], key)
    LOGGER.warning(messages[1], key)

    err = capsys.readouterr().err
    assert key not in err
    assert err.count("<redacted>") == len(messages)


def test_a_traceback_loses_the_key(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    key = fake_api_key()

    try:
        _fail(RuntimeError(f"refused with x-api-key: {key}"))
    except RuntimeError:
        LOGGER.exception("the request failed")

    err = capsys.readouterr().err
    assert "RuntimeError" in err
    assert key not in err


def test_the_log_file_loses_the_key(tmp_path: Path) -> None:
    log_file = tmp_path / "logs" / "weatherbot.log"
    configure_logging("INFO", log_file=log_file)
    key = fake_api_key()

    LOGGER.warning("ANTHROPIC_API_KEY=%s", key)
    try:
        _fail(ValueError(key))
    except ValueError:
        LOGGER.exception("failed")
    configure_logging("INFO")

    text = log_file.read_text(encoding="utf-8")
    assert key not in text
    assert "<redacted>" in text


def test_the_sdk_loggers_stay_at_warning_at_every_level() -> None:
    for level in ("DEBUG", "INFO", "WARNING"):
        configure_logging(level)
        assert {logging.getLogger(name).level for name in SILENT_LIBRARIES} == {logging.WARNING}
    assert not set(SILENT_LIBRARIES) & set(QUIET_LIBRARIES)


@pytest.fixture
def engine() -> Iterator[Engine]:
    with open_database(AppPaths.resolve()) as database:
        guarded = ai_engine(database.path)
        yield guarded
        guarded.dispose()


def test_at_debug_a_replayed_request_puts_no_question_or_key_in_any_record(engine: Engine) -> None:
    configure_logging("DEBUG")
    everything = Everything()
    logging.getLogger().addHandler(everything)
    client, replay = replay_client([RecordedAnswer.json(message_body("ok"))])
    caller = AiCaller(
        lambda: client,
        Ledger(engine, cap_micro_usd=1_000_000, now=lambda: NOW),
        now=lambda: NOW,
    )
    params = {
        "max_tokens": 16,
        "system": "You narrate official products.",
        "messages": [{"role": "user", "content": QUESTION}],
    }
    try:
        asyncio.run(
            caller.create(
                kind="chat", model=MODEL, location=None, prompt_version=None, params=params
            )
        )
    finally:
        logging.getLogger().removeHandler(everything)

    assert replay.requests[0].body["messages"] == params["messages"]
    assert QUESTION not in everything.text()
    assert "narrate official products" not in everything.text()
    assert fake_api_key() not in everything.text()
    assert not [r for r in everything.records if r.name.split(".")[0] in SILENT_LIBRARIES]
