# tests/services/test_settings_file.py
"""Tests for comment-preserving atomic writes in ``weatherbot.services.settings_file``."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from weatherbot.services.config import (
    AppPaths,
    ConfigError,
    load_settings,
    setting_origins,
)
from weatherbot.services.settings_file import (
    EDITABLE,
    EnvironmentOverrideError,
    SettingChange,
    StaleSettingsFileError,
    UneditableSettingError,
    applies_at,
    apply_changes,
    is_editable,
    restart_keys,
    settings_file_sha256,
)

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
INVALID_TIMEZONE_TAG = "Not/An-IANA-Zone-999"


def _write_toml(paths: AppPaths, text: str) -> str:
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    raw = text.encode("utf-8")
    paths.settings_path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_preserves_comments_blank_lines_and_key_order_outside_edited_lines() -> None:
    paths = AppPaths.resolve()
    original = (
        "# Top-of-file operator comment\n"
        "# Second header line\n"
        "\n"
        "[logging]\n"
        'level = "INFO" # keep inline comment\n'
        "\n"
        "# Notifications block comment\n"
        "[notifications]\n"
        "cooldown_hours = 6 # inline cooldown comment\n"
        'quiet_hours_start = "22:00"\n'
        'quiet_hours_end = "07:00"\n'
        'quiet_hours_time_zone = "America/New_York"\n'
        "toast = true\n"
        "\n"
        "# Footer comment after notifications\n"
        "[ai]\n"
        "enabled = true\n"
        "daily_cap_usd = 1.0\n"
    )
    sha = _write_toml(paths, original)

    update = apply_changes(
        paths,
        [
            SettingChange("notifications", "cooldown_hours", 12),
            SettingChange("ai", "daily_cap_usd", 2.5),
        ],
        expected_sha256=sha,
        environ={},
    )

    after = paths.settings_path.read_text(encoding="utf-8")
    expected = original.replace(
        "cooldown_hours = 6 # inline cooldown comment",
        "cooldown_hours = 12 # inline cooldown comment",
    ).replace("daily_cap_usd = 1.0", "daily_cap_usd = 2.5")
    assert after == expected
    assert update.settings_file_sha256 == settings_file_sha256(paths)
    assert update.next_cycle == ("[notifications] cooldown_hours",)
    assert update.next_start == ("[ai] daily_cap_usd",)
    assert update.settings.notifications.cooldown_hours == 12.0  # noqa: PLR2004
    assert update.settings.ai.daily_cap_usd == 2.5  # noqa: PLR2004


def test_creates_missing_file_and_adds_missing_table() -> None:
    paths = AppPaths.resolve()
    assert not paths.settings_path.exists()
    assert settings_file_sha256(paths) == EMPTY_SHA256

    first = apply_changes(
        paths,
        [SettingChange("retention", "history_days", 365)],
        expected_sha256=EMPTY_SHA256,
        environ={},
    )
    assert paths.settings_path.exists()
    assert first.next_cycle == ("[retention] history_days",)
    assert first.next_start == ()
    assert first.settings.retention.history_days == 365  # noqa: PLR2004

    second = apply_changes(
        paths,
        [
            SettingChange("notifications", "quiet_hours_start", "23:00"),
            SettingChange("notifications", "quiet_hours_end", "06:30"),
        ],
        expected_sha256=first.settings_file_sha256,
        environ={},
    )
    text = paths.settings_path.read_text(encoding="utf-8")
    assert "[retention]" in text
    assert "history_days = 365" in text
    assert "[notifications]" in text
    assert second.settings.notifications.quiet_hours_start == "23:00"
    assert second.settings.notifications.quiet_hours_end == "06:30"


@pytest.mark.parametrize(
    ("table", "key", "value"),
    [
        ("web", "host", "0.0.0.0"),  # noqa: S104
        ("web", "port", 9000),
        ("web", "corpus", "/tmp/corpus"),  # noqa: S108
        ("notifications", "ntfy_server", "https://ntfy.example.com"),
        ("ai", "model", "claude-opus-4-7"),
        ("ai", "summary_model", "claude-haiku-4-5"),
        ("engine", "coastal_reach_km", 30.0),
        ("monitor", "confirm_after_minutes", 10),
        ("logging", "level", "DEBUG"),
        ("http", "timeout_seconds", 15.0),
        ("notifications", "unknown_key", INVALID_TIMEZONE_TAG),
        ("unknown_table", "key", INVALID_TIMEZONE_TAG),
    ],
)
def test_refuses_every_non_allowlisted_setting_without_echoing_value(
    table: str,
    key: str,
    value: str | float,
) -> None:
    paths = AppPaths.resolve()
    assert not is_editable(table, key)

    with pytest.raises(UneditableSettingError) as exc_info:
        apply_changes(
            paths,
            [SettingChange(table, key, value)],
            expected_sha256=EMPTY_SHA256,
            environ={},
        )

    assert exc_info.value.table == table
    assert exc_info.value.key == key
    assert f"[{table}] {key}" in str(exc_info.value)
    assert INVALID_TIMEZONE_TAG not in str(exc_info.value)
    assert not paths.settings_path.exists()


def test_refuses_change_when_environment_variable_overrides_target_key() -> None:
    paths = AppPaths.resolve()

    with pytest.raises(EnvironmentOverrideError) as exc_info:
        apply_changes(
            paths,
            [SettingChange("retention", "history_days", 90)],
            expected_sha256=EMPTY_SHA256,
            environ={"WEATHERBOT_RETENTION_HISTORY_DAYS": "365"},
        )

    assert exc_info.value.table == "retention"
    assert exc_info.value.key == "history_days"
    assert exc_info.value.variable == "WEATHERBOT_RETENTION_HISTORY_DAYS"
    assert "WEATHERBOT_RETENTION_HISTORY_DAYS" in str(exc_info.value)
    assert not paths.settings_path.exists()


def test_validates_merged_settings_against_environment_overrides() -> None:
    paths = AppPaths.resolve()
    sha = _write_toml(
        paths,
        '[notifications]\nquiet_hours_start = "22:00"\nquiet_hours_end = "07:00"\n',
    )
    before = paths.settings_path.read_bytes()

    with pytest.raises(ConfigError, match="quiet_hours_end") as exc_info:
        apply_changes(
            paths,
            [SettingChange("notifications", "quiet_hours_end", "")],
            expected_sha256=sha,
            environ={"WEATHERBOT_NOTIFICATIONS_QUIET_HOURS_START": "22:00"},
        )

    assert "must be set when quiet_hours_start is set" in str(exc_info.value)
    assert paths.settings_path.read_bytes() == before


@pytest.mark.parametrize(
    ("change", "expected_key"),
    [
        (SettingChange("retention", "history_days", 15), "[retention] history_days"),
        (SettingChange("retention", "history_days", True), "[retention] history_days"),  # noqa: FBT003
        (
            SettingChange("notifications", "quiet_hours_time_zone", INVALID_TIMEZONE_TAG),
            "[notifications] quiet_hours_time_zone",
        ),
        (
            SettingChange("notifications", "cooldown_hours", -5),
            "[notifications] cooldown_hours",
        ),
        (
            SettingChange("notifications", "toast", "yes"),
            "[notifications] toast",
        ),
        (
            SettingChange("ai", "daily_cap_usd", -1.0),
            "[ai] daily_cap_usd",
        ),
    ],
)
def test_bad_values_raise_config_error_without_echoing_and_keep_file_untouched(
    change: SettingChange,
    expected_key: str,
) -> None:
    paths = AppPaths.resolve()
    sha = _write_toml(paths, "# original\n[retention]\nhistory_days = 0\n")
    before = paths.settings_path.read_bytes()

    with pytest.raises(ConfigError) as exc_info:
        apply_changes(
            paths,
            [change],
            expected_sha256=sha,
            environ={},
        )

    assert expected_key in str(exc_info.value)
    assert INVALID_TIMEZONE_TAG not in str(exc_info.value)
    assert paths.settings_path.read_bytes() == before


def test_refuses_stale_sha256_without_modifying_file() -> None:
    paths = AppPaths.resolve()
    _write_toml(paths, "[retention]\nhistory_days = 90\n")
    before = paths.settings_path.read_bytes()

    with pytest.raises(StaleSettingsFileError, match="changed on disk"):
        apply_changes(
            paths,
            [SettingChange("retention", "history_days", 180)],
            expected_sha256=EMPTY_SHA256,
            environ={},
        )

    assert paths.settings_path.read_bytes() == before


def test_retries_permission_error_on_replace_and_cleans_up_tmp_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = AppPaths.resolve()
    sha = _write_toml(paths, "[retention]\nhistory_days = 0\n")
    real_replace = Path.replace
    sleeps: list[float] = []
    calls = 0

    def flaky_replace(src: Path, dst: Path) -> Path:
        nonlocal calls
        calls += 1
        if calls < 3:  # noqa: PLR2004
            msg = "transient Windows sharing violation"
            raise PermissionError(msg)
        return real_replace(src, dst)

    monkeypatch.setattr(Path, "replace", flaky_replace)
    monkeypatch.setattr("weatherbot.services.settings_file.sys.platform", "win32")

    update = apply_changes(
        paths,
        [SettingChange("retention", "history_days", 60)],
        expected_sha256=sha,
        environ={},
        sleep=sleeps.append,
    )
    assert calls == 3  # noqa: PLR2004
    assert len(sleeps) == 2  # noqa: PLR2004
    assert update.settings.retention.history_days == 60  # noqa: PLR2004

    def always_denied(_src: Path, _dst: Path) -> Path:
        msg = "locked"
        raise PermissionError(msg)

    monkeypatch.setattr(Path, "replace", always_denied)
    with pytest.raises(PermissionError):
        apply_changes(
            paths,
            [SettingChange("retention", "history_days", 90)],
            expected_sha256=update.settings_file_sha256,
            environ={},
            sleep=sleeps.append,
        )

    leftovers = list(paths.config_dir.glob(".weatherbot-*.toml.tmp"))
    assert leftovers == []


def test_restart_keys_reports_only_next_start_settings_that_differ_from_startup() -> None:
    paths = AppPaths.resolve()
    started = load_settings(paths, {})
    sha = _write_toml(
        paths,
        '[notifications]\nquiet_hours_start = "22:00"\nquiet_hours_end = "07:00"\n'
        "[retention]\nhistory_days = 180\n",
    )
    origins = setting_origins(paths, {})
    assert restart_keys(started, origins) == ()

    apply_changes(
        paths,
        [SettingChange("ai", "daily_cap_usd", 3.0)],
        expected_sha256=sha,
        environ={},
    )
    origins_after = setting_origins(paths, {})
    assert restart_keys(started, origins_after) == ("[ai] daily_cap_usd",)
    assert len(EDITABLE) == 12  # noqa: PLR2004
    assert applies_at("retention", "history_days") == "next_cycle"
    assert applies_at("ai", "daily_cap_usd") == "next_start"
    assert applies_at("web", "port") == "next_start"
