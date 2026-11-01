# tests/ai/test_ai_settings.py
"""The ``[ai]`` table: its defaults, its six overrides, and its refusals."""

import json

import pytest
from cli_support import run

from weatherbot.services.config import (
    ENVIRONMENT_OVERRIDES,
    AiSettings,
    AppPaths,
    ConfigError,
    Settings,
    load_settings,
    setting_origins,
)

CAP_USD = 3.0
AI_VARIABLES = {
    "enabled": "WEATHERBOT_AI_ENABLED",
    "model": "WEATHERBOT_AI_MODEL",
    "summary_model": "WEATHERBOT_AI_SUMMARY_MODEL",
    "daily_cap_usd": "WEATHERBOT_AI_DAILY_CAP_USD",
    "change_summaries": "WEATHERBOT_AI_CHANGE_SUMMARIES",
    "outlook_narration": "WEATHERBOT_AI_OUTLOOK_NARRATION",
}


def test_the_defaults() -> None:
    ai = Settings().ai

    assert ai == AiSettings()
    assert ai.enabled is True
    assert ai.model == ai.summary_model == "claude-sonnet-5-5"
    assert ai.daily_cap_usd == 1.0
    assert ai.change_summaries is True
    assert ai.outlook_narration is False


def test_each_key_has_its_literal_override() -> None:
    assert {key: ENVIRONMENT_OVERRIDES["ai", key] for key in AiSettings.model_fields} == (
        AI_VARIABLES
    )


def test_the_six_overrides_apply() -> None:
    paths = AppPaths.resolve()
    environ = {
        "WEATHERBOT_AI_ENABLED": "false",
        "WEATHERBOT_AI_MODEL": "claude-opus-5-5",
        "WEATHERBOT_AI_SUMMARY_MODEL": "claude-haiku-5-5",
        "WEATHERBOT_AI_DAILY_CAP_USD": "2.5",
        "WEATHERBOT_AI_CHANGE_SUMMARIES": "false",
        "WEATHERBOT_AI_OUTLOOK_NARRATION": "true",
    }

    ai = load_settings(paths, environ).ai
    origins = {(o.table, o.key): o.origin for o in setting_origins(paths, environ)}

    assert ai == AiSettings(
        enabled=False,
        model="claude-opus-5-5",
        summary_model="claude-haiku-5-5",
        daily_cap_usd=2.5,
        change_summaries=False,
        outlook_narration=True,
    )
    assert {origins["ai", key] for key in AI_VARIABLES} == {"environment"}


@pytest.mark.parametrize(
    ("key", "variable"),
    [("model", "WEATHERBOT_AI_MODEL"), ("summary_model", "WEATHERBOT_AI_SUMMARY_MODEL")],
)
def test_an_unpriced_model_names_the_key_and_the_allowed_models_never_the_input(
    key: str, variable: str
) -> None:
    secretish = "claude-private-preview-7"
    with pytest.raises(ConfigError) as error:
        load_settings(AppPaths.resolve(), {variable: secretish})

    message = str(error.value)
    assert variable in message
    assert f"[ai] {key}" in message
    assert "claude-sonnet-5-5" in message
    assert secretish not in message


def test_an_unpriced_model_in_the_file_names_the_key() -> None:
    paths = AppPaths.resolve()
    paths.config_dir.mkdir(parents=True)
    paths.settings_path.write_text('[ai]\nmodel = "claude-other"\n', encoding="utf-8")

    with pytest.raises(ConfigError, match=r"\[ai\] model") as error:
        load_settings(paths, {})
    assert "claude-other" not in str(error.value)


@pytest.mark.parametrize("value", ["-1", "100.01"])
def test_the_cap_stays_between_zero_and_a_hundred_dollars(value: str) -> None:
    with pytest.raises(ConfigError, match="WEATHERBOT_AI_DAILY_CAP_USD"):
        load_settings(AppPaths.resolve(), {"WEATHERBOT_AI_DAILY_CAP_USD": value})


def test_config_show_lists_the_ai_table_with_its_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEATHERBOT_AI_DAILY_CAP_USD", str(CAP_USD))
    result = run(["config", "show", "--json"])

    assert result.exit_code == 0
    entries = json.loads(result.stdout)["data"]["settings"]
    ai = {entry["key"]: entry for entry in entries if entry["table"] == "ai"}
    assert set(ai) == set(AI_VARIABLES)
    assert ai["daily_cap_usd"]["value"] == CAP_USD
    assert ai["daily_cap_usd"]["origin"] == "environment"
    assert ai["model"]["origin"] == "default"
