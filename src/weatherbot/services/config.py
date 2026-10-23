# src/weatherbot/services/config.py
"""Where Weatherbot keeps its state, and the settings ``weatherbot.toml`` may change.

``AppPaths`` resolves the configuration and data directories: ``WEATHERBOT_CONFIG_DIR``
and ``WEATHERBOT_DATA_DIR`` when set, else the operating system's user directories
through ``platformdirs``. The database, its backups, and the lock files live in the data
directory; ``weatherbot.toml`` lives in the configuration directory.

``Settings`` holds the logging, HTTP, engine, monitor, and notification keys, with the
precedence environment, then file, then default; ``setting_origins`` says where each
effective value came from. A setting is never a secret, a location, or a coordinate:
locations live in the database. An error names the key that is wrong and never repeats its
value.
"""

import os
import re
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from typing import Final, Literal, Self, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import platformdirs
from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator

from weatherbot.models import (
    BAND_FLOORS,
    BandFloor,
    Thresholds,
)
from weatherbot.models.ladder import (
    COASTAL_REACH_MAX_KM,
    CONE_HORIZON_MAX_H,
    CONE_HORIZON_MIN_H,
    SEGMENT_END_TOLERANCE_MAX_KM,
)
from weatherbot.services.policy import PolicySettings, QuietHours, parse_wall_time

APP_NAME: Final = "weatherbot"
CONFIG_DIR_VARIABLE: Final = "WEATHERBOT_CONFIG_DIR"
DATA_DIR_VARIABLE: Final = "WEATHERBOT_DATA_DIR"
SETTINGS_FILE: Final = "weatherbot.toml"
DATABASE_FILE: Final = "weatherbot.sqlite3"
BACKUP_DIRECTORY: Final = "backups"
CYCLE_LOCK_FILE: Final = "cycle.lock"
MIGRATE_LOCK_FILE: Final = "migrate.lock"
OWNER_ONLY: Final = 0o700

# The environment variable that overrides each setting, by its (table, key) in the file.
ENVIRONMENT_OVERRIDES: Final[Mapping[tuple[str, str], str]] = {
    ("logging", "level"): "WEATHERBOT_LOG_LEVEL",
    ("http", "timeout_seconds"): "WEATHERBOT_HTTP_TIMEOUT_SECONDS",
    ("engine", "coastal_reach_km"): "WEATHERBOT_ENGINE_COASTAL_REACH_KM",
    ("engine", "segment_end_tolerance_km"): "WEATHERBOT_ENGINE_SEGMENT_END_TOLERANCE_KM",
    ("engine", "cone_horizon_h"): "WEATHERBOT_ENGINE_CONE_HORIZON_H",
    ("engine", "hurricane_wind_floor_pct"): "WEATHERBOT_ENGINE_HURRICANE_WIND_FLOOR_PCT",
    ("engine", "tropical_storm_wind_floor_pct"): "WEATHERBOT_ENGINE_TROPICAL_STORM_WIND_FLOOR_PCT",
    ("engine", "development_chance_floor_pct"): "WEATHERBOT_ENGINE_DEVELOPMENT_CHANCE_FLOOR_PCT",
    ("monitor", "cycle_lock_wait_seconds"): "WEATHERBOT_MONITOR_CYCLE_LOCK_WAIT_SECONDS",
    ("monitor", "confirm_after_minutes"): "WEATHERBOT_MONITOR_CONFIRM_AFTER_MINUTES",
    ("notifications", "cooldown_hours"): "WEATHERBOT_NOTIFICATIONS_COOLDOWN_HOURS",
    ("notifications", "quiet_hours_start"): "WEATHERBOT_NOTIFICATIONS_QUIET_HOURS_START",
    ("notifications", "quiet_hours_end"): "WEATHERBOT_NOTIFICATIONS_QUIET_HOURS_END",
    ("notifications", "quiet_hours_time_zone"): "WEATHERBOT_NOTIFICATIONS_QUIET_HOURS_TIME_ZONE",
    ("notifications", "toast"): "WEATHERBOT_NOTIFICATIONS_TOAST",
}
_TOML_POSITION: Final = re.compile(r"\(at line \d+, column \d+\)|\(at end of document\)")


class ConfigError(Exception):
    """The configuration is unusable. The message names the key, never its value."""


def ensure_directory(path: Path) -> Path:
    """Create a directory if it is missing, owner-only (0o700) on POSIX.

    Args:
        path: The directory.

    Returns:
        The directory.
    """
    path.mkdir(mode=OWNER_ONLY, parents=True, exist_ok=True)
    if sys.platform != "win32":
        path.chmod(OWNER_ONLY)
    return path


def _override(environ: Mapping[str, str], variable: str) -> Path | None:
    value = environ.get(variable, "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        # A relative directory would resolve against the working directory, which can be
        # the checkout: the failure that lost version 1's recorded responses.
        message = f"{variable} must be an absolute path"
        raise ConfigError(message)
    return path


@dataclass(frozen=True)
class AppPaths:
    """The configuration and data directories, and the files inside them."""

    config_dir: Path
    data_dir: Path

    @classmethod
    def resolve(cls, environ: Mapping[str, str] | None = None) -> Self:
        """Resolve the directories from the overrides, else from ``platformdirs``.

        ``platformdirs`` is asked only for a directory that has no override.

        Args:
            environ: The environment; ``os.environ`` when omitted.

        Returns:
            The paths. Nothing is created until it is used.

        Raises:
            ConfigError: An override is not an absolute path.
        """
        env = os.environ if environ is None else environ
        config_dir = _override(env, CONFIG_DIR_VARIABLE) or Path(
            platformdirs.user_config_dir(APP_NAME, appauthor=False)
        )
        data_dir = _override(env, DATA_DIR_VARIABLE) or Path(
            platformdirs.user_data_dir(APP_NAME, appauthor=False)
        )
        return cls(config_dir=config_dir, data_dir=data_dir)

    @property
    def settings_path(self) -> Path:
        """``weatherbot.toml`` in the configuration directory."""
        return self.config_dir / SETTINGS_FILE

    @property
    def database_path(self) -> Path:
        """The SQLite database in the data directory."""
        return self.data_dir / DATABASE_FILE

    @property
    def backup_dir(self) -> Path:
        """Where a database is copied before a migration."""
        return self.data_dir / BACKUP_DIRECTORY

    @property
    def cycle_lock_path(self) -> Path:
        """The lock every monitor cycle holds, in whichever process runs it."""
        return self.data_dir / CYCLE_LOCK_FILE

    @property
    def migrate_lock_path(self) -> Path:
        """The lock a process holds while it backs up and upgrades the database."""
        return self.data_dir / MIGRATE_LOCK_FILE


type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class _Section(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", allow_inf_nan=False, hide_input_in_errors=True
    )


class LoggingSettings(_Section):
    """``[logging]``."""

    level: LogLevel = "INFO"

    @field_validator("level", mode="before")
    @classmethod
    def _upper(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class HttpSettings(_Section):
    """``[http]``."""

    timeout_seconds: float = Field(default=30.0, gt=0, le=300)


_DEFAULT_THRESHOLDS: Final = Thresholds()


def _band_floor(value: int) -> int:
    if value not in BAND_FLOORS:
        message = f"must be a band lower bound: {', '.join(map(str, BAND_FLOORS))}"
        raise ValueError(message)
    return value


class EngineSettings(_Section):
    """``[engine]``: the ladder's six thresholds, with ``Thresholds``' defaults and ranges.

    A floor is one of the wind-speed-probability band lower bounds.
    """

    coastal_reach_km: float = Field(
        default=_DEFAULT_THRESHOLDS.coastal_reach_km, ge=0, le=COASTAL_REACH_MAX_KM
    )
    segment_end_tolerance_km: float = Field(
        default=_DEFAULT_THRESHOLDS.segment_end_tolerance_km,
        ge=0,
        le=SEGMENT_END_TOLERANCE_MAX_KM,
    )
    cone_horizon_h: int = Field(
        default=_DEFAULT_THRESHOLDS.cone_horizon_h, ge=CONE_HORIZON_MIN_H, le=CONE_HORIZON_MAX_H
    )
    hurricane_wind_floor_pct: int = _DEFAULT_THRESHOLDS.hurricane_wind_floor_pct
    tropical_storm_wind_floor_pct: int = _DEFAULT_THRESHOLDS.tropical_storm_wind_floor_pct
    development_chance_floor_pct: int = _DEFAULT_THRESHOLDS.development_chance_floor_pct

    @field_validator(
        "hurricane_wind_floor_pct",
        "tropical_storm_wind_floor_pct",
        "development_chance_floor_pct",
    )
    @classmethod
    def _floor(cls, value: int) -> int:
        return _band_floor(value)

    def thresholds(self) -> Thresholds:
        """Build the engine's thresholds from this table.

        Returns:
            The thresholds.
        """
        return Thresholds(
            coastal_reach_km=float(self.coastal_reach_km),
            segment_end_tolerance_km=float(self.segment_end_tolerance_km),
            cone_horizon_h=self.cone_horizon_h,
            hurricane_wind_floor_pct=cast("BandFloor", self.hurricane_wind_floor_pct),
            tropical_storm_wind_floor_pct=cast("BandFloor", self.tropical_storm_wind_floor_pct),
            development_chance_floor_pct=cast("BandFloor", self.development_chance_floor_pct),
        )


class MonitorSettings(_Section):
    """``[monitor]``: how the monitor cycle runs."""

    cycle_lock_wait_seconds: int = Field(default=120, ge=1, le=3600)
    confirm_after_minutes: int = Field(default=5, ge=1, le=60)


class NotificationSettings(_Section):
    """``[notifications]``: the cooldown and quiet hours, and whether the toast is on."""

    cooldown_hours: int = Field(default=6, ge=0, le=48)
    quiet_hours_start: str = ""
    quiet_hours_end: str = Field(default="", validate_default=True)
    quiet_hours_time_zone: str = "local"
    toast: bool = True

    @field_validator("quiet_hours_start")
    @classmethod
    def _start(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            return ""
        parse_wall_time(cleaned, allow_24=False)
        return cleaned

    @field_validator("quiet_hours_end")
    @classmethod
    def _end(cls, value: str, info: ValidationInfo) -> str:
        cleaned = value.strip()
        start = str(info.data.get("quiet_hours_start", ""))
        if not cleaned:
            if start:
                message = "must be set when quiet_hours_start is set"
                raise ValueError(message)
            return ""
        parse_wall_time(cleaned, allow_24=True)
        if not start:
            message = "requires quiet_hours_start to be set"
            raise ValueError(message)
        if cleaned == start:
            message = "must not equal quiet_hours_start"
            raise ValueError(message)
        return cleaned

    @field_validator("quiet_hours_time_zone")
    @classmethod
    def _time_zone(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            message = "must be 'local' or an IANA time zone"
            raise ValueError(message)
        if cleaned != "local":
            try:
                ZoneInfo(cleaned)
            except (ZoneInfoNotFoundError, ValueError):
                message = "must be 'local' or a known IANA time zone"
                raise ValueError(message) from None
        return cleaned

    def quiet_hours(self, *, local_zone: tzinfo | None = None) -> QuietHours | None:
        """Resolve the quiet-hours window at this cycle's time zone, when configured."""
        if not (self.quiet_hours_start and self.quiet_hours_end):
            return None
        zone = (
            (local_zone or datetime.now().astimezone().tzinfo or UTC)
            if self.quiet_hours_time_zone == "local"
            else ZoneInfo(self.quiet_hours_time_zone)
        )
        return QuietHours.parse(self.quiet_hours_start, self.quiet_hours_end, zone)


class Settings(_Section):
    """The settings: ``[logging]``, ``[http]``, ``[engine]``, ``[monitor]``, ``[notifications]``."""

    logging: LoggingSettings = LoggingSettings()
    http: HttpSettings = HttpSettings()
    engine: EngineSettings = EngineSettings()
    monitor: MonitorSettings = MonitorSettings()
    notifications: NotificationSettings = NotificationSettings()

    def policy_settings(self, *, local_zone: tzinfo | None = None) -> PolicySettings:
        """Build the notification policy's settings for a cycle."""
        return PolicySettings(
            cooldown=timedelta(hours=self.notifications.cooldown_hours),
            quiet_hours=self.notifications.quiet_hours(local_zone=local_zone),
            confirm_after=timedelta(minutes=self.monitor.confirm_after_minutes),
        )


def _key(location: tuple[str | int, ...]) -> str:
    """Spell an error location as the file does: ``[http] timeout_seconds``."""
    parts = [str(part) for part in location]
    if len(parts) == 1:
        return f"[{parts[0]}]"
    return f"[{parts[0]}] {'.'.join(parts[1:])}"


def _describe(error: ValidationError, origin: Mapping[tuple[str, str], str], source: str) -> str:
    """Name each wrong key and what is wrong with it; the input never appears."""
    problems: list[str] = []
    for item in error.errors(include_input=False, include_url=False, include_context=False):
        location = tuple(item["loc"])
        where = origin.get((str(location[0]), str(location[1]))) if len(location) == 2 else None  # noqa: PLR2004 - (table, key)
        name = where or f"{_key(location)} in {source}"
        reason = "is not a known setting" if item["type"] == "extra_forbidden" else item["msg"]
        problems.append(f"{name}: {reason}")
    return "; ".join(problems)


def _read_file(path: Path) -> dict[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        # The position only: a decoder message could quote the text around it.
        position = _TOML_POSITION.search(str(error))
        where = f" {position.group(0)}" if position else ""
        message = f"{path.name} is not valid TOML{where}"
        raise ConfigError(message) from None


def load_settings(paths: AppPaths, environ: Mapping[str, str] | None = None) -> Settings:
    """Read ``weatherbot.toml`` and the ``WEATHERBOT_*`` overrides.

    The precedence is environment, then file, then default. The configuration never
    reads the personal-data denylist or a ``.env`` file.

    Args:
        paths: Where ``weatherbot.toml`` lives; a missing file means the defaults.
        environ: The environment; ``os.environ`` when omitted.

    Returns:
        The settings.

    Raises:
        ConfigError: The file is not TOML, names an unknown key, or holds a bad value, or
            an override holds a bad value. The message names the key, never the value.
    """
    env = os.environ if environ is None else environ
    source = paths.settings_path.name
    document = _read_file(paths.settings_path)
    try:
        Settings.model_validate(document)
    except ValidationError as error:
        raise ConfigError(_describe(error, {}, source)) from None
    # Validated above: every top-level value is one of the known tables.
    merged = {name: dict(cast("Mapping[str, object]", table)) for name, table in document.items()}
    origin: dict[tuple[str, str], str] = {}
    for (table, key), variable in ENVIRONMENT_OVERRIDES.items():
        value = env.get(variable, "").strip()
        if value:
            merged.setdefault(table, {})[key] = value
            origin[table, key] = variable
    try:
        return Settings.model_validate(merged)
    except ValidationError as error:
        raise ConfigError(_describe(error, origin, source)) from None


type SettingOriginKind = Literal["default", "file", "environment"]
type SettingValue = str | int | float | bool


@dataclass(frozen=True)
class SettingOrigin:
    """One setting's effective value, and where it came from."""

    table: str
    key: str
    value: SettingValue
    origin: SettingOriginKind
    variable: str
    """The environment variable that overrides it."""


def setting_origins(
    paths: AppPaths, environ: Mapping[str, str] | None = None
) -> tuple[SettingOrigin, ...]:
    """Say every setting's effective value and its origin: environment, file, or default.

    Args:
        paths: Where ``weatherbot.toml`` lives.
        environ: The environment; ``os.environ`` when omitted.

    Returns:
        One entry per setting, table by table in ``Settings``' order.

    Raises:
        ConfigError: The settings do not load (``load_settings``).
    """
    env = os.environ if environ is None else environ
    settings = load_settings(paths, env)
    document = _read_file(paths.settings_path)
    entries: list[SettingOrigin] = []
    for table in Settings.model_fields:
        section = cast("_Section", getattr(settings, table))
        written = document.get(table, {})
        in_file: Mapping[str, object] = (
            cast("Mapping[str, object]", written) if isinstance(written, dict) else {}
        )
        for key in type(section).model_fields:
            variable = ENVIRONMENT_OVERRIDES[table, key]
            origin: SettingOriginKind = "default"
            if env.get(variable, "").strip():
                origin = "environment"
            elif key in in_file:
                origin = "file"
            value = cast("SettingValue", getattr(section, key))
            entries.append(SettingOrigin(table, key, value, origin, variable))
    return tuple(entries)
