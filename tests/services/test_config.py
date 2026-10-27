# tests/services/test_config.py
"""The configuration and data directories, and the settings precedence.

The isolation guard proves that, under the suite's autouse fixture, ``AppPaths`` never
asks ``platformdirs`` for the operator's real directories.
"""

import os
import sys
from pathlib import Path

import platformdirs
import pytest

from weatherbot.models import Thresholds
from weatherbot.services import config
from weatherbot.services.config import (
    AppPaths,
    ConfigError,
    Settings,
    ensure_directory,
    load_settings,
)

UNECHOED = "value-that-must-not-appear-7f3a"


def _refuse(*_: object, **__: object) -> str:
    message = "platformdirs was asked for a real directory during a test"
    raise AssertionError(message)


@pytest.fixture
def no_platformdirs(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("user_config_dir", "user_data_dir"):
        monkeypatch.setattr(platformdirs, name, _refuse)


# The isolation guard -------------------------------------------------------------------------


@pytest.mark.usefixtures("no_platformdirs")
def test_tests_never_resolve_the_operators_real_directories(tmp_path: Path) -> None:
    paths = AppPaths.resolve()

    assert paths.config_dir == tmp_path / "weatherbot-config"
    assert paths.data_dir == tmp_path / "weatherbot-data"
    assert paths.database_path.is_relative_to(tmp_path)
    assert paths.backup_dir.is_relative_to(tmp_path)
    assert paths.settings_path.is_relative_to(tmp_path)


def test_the_guard_clears_every_other_weatherbot_variable() -> None:
    names = {name.upper() for name in os.environ if name.upper().startswith("WEATHERBOT_")}

    assert names <= {
        "WEATHERBOT_CONFIG_DIR",
        "WEATHERBOT_DATA_DIR",
        "WEATHERBOT_DENYLIST",
        "WEATHERBOT_CORPUS_CACHE",
        "WEATHERBOT_NOTIFICATIONS_TOAST",
        "WEATHERBOT_WEB_PORT",
    }
    assert "WEATHERBOT_LOG_LEVEL" not in os.environ
    # The guard turns the toast off and picks a free web port, so no test shows a real
    # toast or collides with a running monitor on 8765.
    assert os.environ["WEATHERBOT_NOTIFICATIONS_TOAST"] == "false"
    assert os.environ["WEATHERBOT_WEB_PORT"] == "0"


def test_the_patched_platformdirs_would_catch_a_lookup(
    no_platformdirs: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del no_platformdirs
    monkeypatch.delenv("WEATHERBOT_DATA_DIR")

    with pytest.raises(AssertionError, match="real directory"):
        AppPaths.resolve()


# Directories ---------------------------------------------------------------------------------


def test_without_overrides_the_directories_come_from_platformdirs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    asked: list[tuple[str, object]] = []

    def user_dir(kind: str) -> object:
        def answer(name: str, *, appauthor: object) -> str:
            asked.append((name, appauthor))
            return str(tmp_path / kind)

        return answer

    monkeypatch.setattr(platformdirs, "user_config_dir", user_dir("config"))
    monkeypatch.setattr(platformdirs, "user_data_dir", user_dir("data"))

    paths = AppPaths.resolve({})

    assert paths == AppPaths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    assert asked == [("weatherbot", False), ("weatherbot", False)]
    assert paths.database_path == tmp_path / "data" / "weatherbot.sqlite3"
    assert paths.backup_dir == tmp_path / "data" / "backups"
    assert paths.settings_path == tmp_path / "config" / "weatherbot.toml"


@pytest.mark.usefixtures("no_platformdirs")
def test_an_override_must_be_an_absolute_path(tmp_path: Path) -> None:
    environ = {"WEATHERBOT_CONFIG_DIR": str(tmp_path), "WEATHERBOT_DATA_DIR": "relative"}

    with pytest.raises(ConfigError, match="WEATHERBOT_DATA_DIR must be an absolute path"):
        AppPaths.resolve(environ)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_directories_are_created_owner_only(tmp_path: Path) -> None:
    created = ensure_directory(tmp_path / "a" / "b")

    assert created.is_dir()
    assert created.stat().st_mode & 0o777 == config.OWNER_ONLY


def test_nothing_is_created_until_it_is_used() -> None:
    paths = AppPaths.resolve()

    assert not paths.config_dir.exists()
    assert not paths.data_dir.exists()


# Settings ------------------------------------------------------------------------------------


def _write(paths: AppPaths, text: str) -> None:
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    paths.settings_path.write_text(text, encoding="utf-8")


def test_without_a_file_the_defaults_apply() -> None:
    settings = load_settings(AppPaths.resolve(), {})

    assert settings == Settings()
    assert settings.logging.level == "INFO"
    assert settings.http.timeout_seconds == 30.0  # noqa: PLR2004 - the documented default


def test_the_environment_wins_over_the_file_and_the_file_over_the_default() -> None:
    paths = AppPaths.resolve()
    _write(paths, '[logging]\nlevel = "warning"\n\n[http]\ntimeout_seconds = 12\n')

    from_file = load_settings(paths, {})
    from_environment = load_settings(
        paths, {"WEATHERBOT_LOG_LEVEL": "debug", "WEATHERBOT_HTTP_TIMEOUT_SECONDS": "45.5"}
    )
    partly = load_settings(paths, {"WEATHERBOT_HTTP_TIMEOUT_SECONDS": "5"})

    assert (from_file.logging.level, from_file.http.timeout_seconds) == ("WARNING", 12.0)
    assert (from_environment.logging.level, from_environment.http.timeout_seconds) == (
        "DEBUG",
        45.5,
    )
    assert (partly.logging.level, partly.http.timeout_seconds) == ("WARNING", 5.0)


def test_an_override_applies_without_a_file() -> None:
    settings = load_settings(AppPaths.resolve(), {"WEATHERBOT_LOG_LEVEL": "ERROR"})

    assert settings.logging.level == "ERROR"
    assert settings.http.timeout_seconds == Settings().http.timeout_seconds


def test_load_settings_reads_os_environ_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEATHERBOT_LOG_LEVEL", "critical")

    assert load_settings(AppPaths.resolve()).logging.level == "CRITICAL"


@pytest.mark.parametrize(
    ("text", "key"),
    [
        (f'[logging]\nlevel = "INFO"\ncolour = "{UNECHOED}"\n', "[logging] colour"),
        (f'[secrets]\ntoken = "{UNECHOED}"\n', "[secrets]"),
        (f'home = "{UNECHOED}"\n', "[home]"),
    ],
    ids=["unknown-key", "unknown-table", "unknown-top-level"],
)
def test_an_unknown_key_is_named_and_its_value_never_echoed(text: str, key: str) -> None:
    paths = AppPaths.resolve()
    _write(paths, text)

    with pytest.raises(ConfigError) as failure:
        load_settings(paths, {})

    message = str(failure.value)
    assert key in message
    assert "is not a known setting" in message
    assert UNECHOED not in message
    assert UNECHOED not in repr(failure.value)


@pytest.mark.parametrize(
    ("text", "key"),
    [
        (f'[logging]\nlevel = "{UNECHOED}"\n', "[logging] level in weatherbot.toml"),
        (f'[http]\ntimeout_seconds = "{UNECHOED}"\n', "[http] timeout_seconds"),
        ("[http]\ntimeout_seconds = -3\n", "[http] timeout_seconds"),
        ("[http]\ntimeout_seconds = 9000\n", "[http] timeout_seconds"),
        ('logging = "flat"\n', "[logging]"),
    ],
    ids=["level", "timeout-text", "timeout-negative", "timeout-huge", "table-as-value"],
)
def test_a_bad_value_names_its_key_and_never_its_value(text: str, key: str) -> None:
    paths = AppPaths.resolve()
    _write(paths, text)

    with pytest.raises(ConfigError) as failure:
        load_settings(paths, {})

    assert key in str(failure.value)
    assert UNECHOED not in str(failure.value)
    assert "9000" not in str(failure.value)
    assert "-3" not in str(failure.value)


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("WEATHERBOT_LOG_LEVEL", UNECHOED),
        ("WEATHERBOT_HTTP_TIMEOUT_SECONDS", UNECHOED),
        ("WEATHERBOT_HTTP_TIMEOUT_SECONDS", "inf"),
    ],
)
def test_a_bad_override_names_its_variable_and_never_its_value(variable: str, value: str) -> None:
    with pytest.raises(ConfigError) as failure:
        load_settings(AppPaths.resolve(), {variable: value})

    assert variable in str(failure.value)
    assert value not in str(failure.value)


def test_a_file_that_is_not_toml_is_named_with_its_position_only() -> None:
    paths = AppPaths.resolve()
    _write(paths, f"[logging]\nlevel = {UNECHOED}\n")

    with pytest.raises(ConfigError) as failure:
        load_settings(paths, {})

    message = str(failure.value)
    assert message.startswith("weatherbot.toml is not valid TOML")
    assert "line 2" in message
    assert UNECHOED not in message


def test_the_configuration_never_reads_a_dotenv_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("WEATHERBOT_LOG_LEVEL=DEBUG\n", encoding="utf-8")
    paths = AppPaths.resolve()
    paths.config_dir.mkdir(parents=True)
    (paths.config_dir / ".env").write_text("WEATHERBOT_LOG_LEVEL=DEBUG\n", encoding="utf-8")

    assert load_settings(paths).logging.level == "INFO"


# The [engine] table ------------------------------------------------------------------------


def test_the_engine_table_defaults_to_the_calibrated_thresholds() -> None:
    assert load_settings(AppPaths.resolve(), {}).engine.thresholds() == Thresholds()


def test_each_threshold_has_its_override_variable() -> None:
    engine = {
        key: variable
        for (table, key), variable in config.ENVIRONMENT_OVERRIDES.items()
        if table == "engine"
    }

    assert engine == {name: f"WEATHERBOT_ENGINE_{name.upper()}" for name in Thresholds.model_fields}


def test_the_engine_table_and_its_overrides_set_the_thresholds() -> None:
    paths = AppPaths.resolve()
    _write(
        paths,
        "[engine]\n"
        "coastal_reach_km = 30\n"
        "segment_end_tolerance_km = 4.5\n"
        "cone_horizon_h = 96\n"
        "hurricane_wind_floor_pct = 20\n"
        "tropical_storm_wind_floor_pct = 10\n"
        "development_chance_floor_pct = 30\n",
    )
    overrides = {
        "WEATHERBOT_ENGINE_CONE_HORIZON_H": "72",
        "WEATHERBOT_ENGINE_HURRICANE_WIND_FLOOR_PCT": "40",
        "WEATHERBOT_ENGINE_COASTAL_REACH_KM": "12.5",
    }

    from_file = load_settings(paths, {}).engine.thresholds()
    overridden = load_settings(paths, overrides).engine.thresholds()

    assert from_file == Thresholds(
        coastal_reach_km=30.0,
        segment_end_tolerance_km=4.5,
        cone_horizon_h=96,
        hurricane_wind_floor_pct=20,
        tropical_storm_wind_floor_pct=10,
        development_chance_floor_pct=30,
    )
    assert overridden == from_file.model_copy(
        update={"cone_horizon_h": 72, "hurricane_wind_floor_pct": 40, "coastal_reach_km": 12.5}
    )


@pytest.mark.parametrize(
    ("text", "key", "value"),
    [
        ("[engine]\ncoastal_reach_km = 201\n", "[engine] coastal_reach_km", "201"),
        ("[engine]\nsegment_end_tolerance_km = -1\n", "[engine] segment_end_tolerance_km", "-1"),
        ("[engine]\ncone_horizon_h = 121\n", "[engine] cone_horizon_h", "121"),
        ("[engine]\ncone_horizon_h = 0\n", "[engine] cone_horizon_h", "= 0"),
        ("[engine]\nhurricane_wind_floor_pct = 17\n", "[engine] hurricane_wind_floor_pct", "17"),
        (
            f'[engine]\ntropical_storm_wind_floor_pct = "{UNECHOED}"\n',
            "[engine] tropical_storm_wind_floor_pct",
            UNECHOED,
        ),
        (f'[engine]\nspeed = "{UNECHOED}"\n', "[engine] speed", UNECHOED),
    ],
    ids=["reach", "tolerance", "horizon-high", "horizon-zero", "floor", "floor-text", "unknown"],
)
def test_a_bad_engine_value_names_its_key_and_never_its_value(
    text: str, key: str, value: str
) -> None:
    paths = AppPaths.resolve()
    _write(paths, text)

    with pytest.raises(ConfigError) as failure:
        load_settings(paths, {})

    assert key in str(failure.value)
    assert value not in str(failure.value)


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("WEATHERBOT_ENGINE_COASTAL_REACH_KM", "nan"),
        ("WEATHERBOT_ENGINE_CONE_HORIZON_H", "72.5"),
        ("WEATHERBOT_ENGINE_DEVELOPMENT_CHANCE_FLOOR_PCT", "33"),
        ("WEATHERBOT_ENGINE_SEGMENT_END_TOLERANCE_KM", UNECHOED),
    ],
)
def test_a_bad_engine_override_names_its_variable_and_never_its_value(
    variable: str, value: str
) -> None:
    with pytest.raises(ConfigError) as failure:
        load_settings(AppPaths.resolve(), {variable: value})

    assert variable in str(failure.value)
    assert value not in str(failure.value)


# The [notifications] and [monitor] tables --------------------------------------------------


def test_notifications_and_monitor_confirm_settings_load_and_override() -> None:
    paths = AppPaths.resolve()
    _write(
        paths,
        "[monitor]\n"
        "confirm_after_minutes = 10\n\n"
        "[notifications]\n"
        "cooldown_hours = 12\n"
        'quiet_hours_start = "22:00"\n'
        'quiet_hours_end = "07:00"\n'
        'quiet_hours_time_zone = "America/New_York"\n',
    )
    from_file = load_settings(paths, {})
    assert from_file.monitor.confirm_after_minutes == 10  # noqa: PLR2004
    assert from_file.notifications.cooldown_hours == 12.0  # noqa: PLR2004
    assert from_file.notifications.quiet_hours_start == "22:00"
    assert from_file.notifications.quiet_hours_end == "07:00"
    assert from_file.notifications.quiet_hours_time_zone == "America/New_York"

    policy = from_file.policy_settings()
    assert policy.quiet_hours is not None
    assert policy.confirm_after.total_seconds() == 600  # noqa: PLR2004

    overridden = load_settings(
        paths,
        {
            "WEATHERBOT_MONITOR_CONFIRM_AFTER_MINUTES": "15",
            "WEATHERBOT_NOTIFICATIONS_COOLDOWN_HOURS": "24",
            "WEATHERBOT_NOTIFICATIONS_QUIET_HOURS_START": "00:00",
            "WEATHERBOT_NOTIFICATIONS_QUIET_HOURS_END": "24:00",
            "WEATHERBOT_NOTIFICATIONS_QUIET_HOURS_TIME_ZONE": "local",
        },
    )
    assert overridden.monitor.confirm_after_minutes == 15  # noqa: PLR2004
    assert overridden.notifications.cooldown_hours == 24.0  # noqa: PLR2004
    assert overridden.notifications.quiet_hours_end == "24:00"
    assert overridden.notifications.quiet_hours_time_zone == "local"
    assert overridden.policy_settings().quiet_hours is not None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            '[notifications]\nquiet_hours_start = "22:00"\n',
            "must be set when quiet_hours_start is set",
        ),
        (
            '[notifications]\nquiet_hours_start = "22:00"\nquiet_hours_end = "22:00"\n',
            "must not equal quiet_hours_start",
        ),
        (
            '[notifications]\nquiet_hours_start = "24:00"\nquiet_hours_end = "06:00"\n',
            "[notifications] quiet_hours_start",
        ),
        (
            '[notifications]\nquiet_hours_time_zone = "No/Such_Zone"\n',
            "[notifications] quiet_hours_time_zone",
        ),
        (
            "[notifications]\ncooldown_hours = 49\n",
            "[notifications] cooldown_hours",
        ),
        (
            "[monitor]\nconfirm_after_minutes = 0\n",
            "[monitor] confirm_after_minutes",
        ),
    ],
)
def test_bad_notification_or_confirm_settings_are_refused(text: str, expected: str) -> None:
    paths = AppPaths.resolve()
    _write(paths, text)

    with pytest.raises(ConfigError, match=r".*") as failure:
        load_settings(paths, {})

    assert expected in str(failure.value)
