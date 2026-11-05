# src/weatherbot/services/settings_file.py
"""Comment-preserving atomic writes to ``weatherbot.toml`` for the settings editor.

Only this module in ``src/weatherbot/`` imports ``tomlkit``. Reads stay on standard-library
``tomllib`` in ``weatherbot.services.config``; ``apply_changes`` mutates the parsed
``tomlkit`` document for the allowlisted keys in ``EDITABLE``, re-parses the rendered text
with ``tomllib``, validates the merged result through the same rules ``load_settings``
runs, and replaces ``weatherbot.toml`` atomically from a sibling temporary file.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, cast

import tomlkit
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import Table

from weatherbot.services.config import (
    ENVIRONMENT_OVERRIDES,
    AppPaths,
    ConfigError,
    SettingOrigin,
    Settings,
    SettingValue,
    ensure_directory,
    parse_settings_toml,
    validate_settings_document,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

type AppliesAt = Literal["next_cycle", "next_start"]

FILE_OWNER_ONLY: Final = 0o600
REPLACE_RETRY_COUNT: Final = 20
REPLACE_RETRY_DELAY_SECONDS: Final = 0.05

EDITABLE: Final[dict[tuple[str, str], AppliesAt]] = {
    ("notifications", "cooldown_hours"): "next_cycle",
    ("notifications", "quiet_hours_start"): "next_cycle",
    ("notifications", "quiet_hours_end"): "next_cycle",
    ("notifications", "quiet_hours_time_zone"): "next_cycle",
    ("notifications", "toast"): "next_start",
    ("notifications", "browser"): "next_start",
    ("notifications", "ntfy"): "next_start",
    ("ai", "enabled"): "next_start",
    ("ai", "daily_cap_usd"): "next_start",
    ("ai", "change_summaries"): "next_start",
    ("ai", "outlook_narration"): "next_start",
    ("retention", "history_days"): "next_cycle",
}
"""Allowlisted ``(table, key)`` pairs the settings editor may write, and when each applies."""

_BOOL_KEYS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("notifications", "toast"),
        ("notifications", "browser"),
        ("notifications", "ntfy"),
        ("ai", "enabled"),
        ("ai", "change_summaries"),
        ("ai", "outlook_narration"),
    }
)


class StaleSettingsFileError(ConfigError):
    """``weatherbot.toml`` changed on disk since the caller's ``expected_sha256`` was read."""


class EnvironmentOverrideError(ConfigError):
    """A requested setting change is overridden by a ``WEATHERBOT_*`` environment variable."""

    def __init__(self, table: str, key: str, variable: str) -> None:
        """Record the table, key, and overriding environment variable name."""
        self.table = table
        self.key = key
        self.variable = variable
        super().__init__(f"[{table}] {key} is overridden by {variable} in the environment")


class UneditableSettingError(ConfigError):
    """A requested setting is outside the ``EDITABLE`` allowlist."""

    def __init__(self, table: str, key: str) -> None:
        """Record the rejected table and key without echoing any value."""
        self.table = table
        self.key = key
        super().__init__(f"[{table}] {key} is not an editable setting")


@dataclass(frozen=True)
class SettingChange:
    """One setting update to write to ``weatherbot.toml``."""

    table: str
    key: str
    value: SettingValue


@dataclass(frozen=True)
class SettingsUpdate:
    """Result of ``apply_changes``: the new file digest, apply timings, and settings."""

    settings_file_sha256: str
    next_cycle: tuple[str, ...]
    next_start: tuple[str, ...]
    settings: Settings


def format_setting_key(table: str, key: str) -> str:
    """Format a ``(table, key)`` pair as ``[table] key``."""
    return f"[{table}] {key}"


def is_editable(table: str, key: str) -> bool:
    """Return whether ``(table, key)`` is on the ``EDITABLE`` allowlist."""
    return (table, key) in EDITABLE


def applies_at(table: str, key: str) -> AppliesAt:
    """Return whether ``(table, key)`` applies at ``next_cycle`` or ``next_start``."""
    return EDITABLE.get((table, key), "next_start")


def settings_file_sha256(path: Path | AppPaths) -> str:
    """Return the hex SHA-256 digest of ``path``'s bytes, or of ``b""`` when absent."""
    target = path.settings_path if isinstance(path, AppPaths) else path
    try:
        raw = target.read_bytes()
    except OSError:
        raw = b""
    return hashlib.sha256(raw).hexdigest()


def restart_keys(started: Settings, origins: Sequence[SettingOrigin]) -> tuple[str, ...]:
    """Return ``[table] key`` for every ``next_start`` setting whose value differs from startup."""
    differing: list[str] = []
    for item in origins:
        if applies_at(item.table, item.key) != "next_start":
            continue
        section = getattr(started, item.table, None)
        if section is None:
            continue
        started_value = getattr(section, item.key, None)
        if started_value != item.value:
            differing.append(format_setting_key(item.table, item.key))
    return tuple(differing)


def _replace_with_retry(
    src: Path,
    dst: Path,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Atomically replace ``dst`` with ``src``, retrying up to 1 s on ``PermissionError``."""
    attempts = REPLACE_RETRY_COUNT if sys.platform == "win32" else 1
    for attempt in range(1, attempts + 1):
        try:
            src.replace(dst)
        except PermissionError:
            if attempt >= attempts:
                raise
            sleep(REPLACE_RETRY_DELAY_SECONDS)
        else:
            return


def _validate_change_type(change: SettingChange, *, source: str) -> None:
    """Reject non-primitive values or booleans passed to numeric/string settings."""
    pair = (change.table, change.key)
    val = change.value
    if pair in _BOOL_KEYS:
        if not isinstance(val, bool):
            message = f"[{change.table}] {change.key} in {source}: Input should be a valid boolean"
            raise ConfigError(message)
        return
    if isinstance(val, bool):
        message = f"[{change.table}] {change.key} in {source}: invalid setting value"
        raise ConfigError(message)


def apply_changes(  # noqa: C901, PLR0912, PLR0915 - atomic multi-step TOML update
    paths: AppPaths,
    changes: Sequence[SettingChange],
    *,
    expected_sha256: str,
    environ: Mapping[str, str] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> SettingsUpdate:
    """Apply allowlisted setting changes to ``weatherbot.toml`` atomically.

    Args:
        paths: Application paths resolving ``weatherbot.toml``.
        changes: Setting updates to write.
        expected_sha256: Hex SHA-256 digest of ``weatherbot.toml`` when read by the caller
            (or SHA-256 of ``b""`` when the file did not exist).
        environ: Environment mapping; ``os.environ`` when omitted.
        sleep: Sleep function used between Windows ``PermissionError`` retries.

    Returns:
        ``SettingsUpdate`` naming the new file SHA-256, ``next_cycle`` keys, ``next_start``
        keys, and the validated ``Settings``.

    Raises:
        UneditableSettingError: Any target ``(table, key)`` is not in ``EDITABLE``.
        EnvironmentOverrideError: Any target ``(table, key)`` is set in ``environ``.
        StaleSettingsFileError: The file's current SHA-256 differs from ``expected_sha256``.
        ConfigError: The existing file or updated result is not valid TOML or fails
            ``Settings`` validation. Messages name keys or line/column positions, never values.
    """
    env = os.environ if environ is None else environ
    settings_path = paths.settings_path
    source = settings_path.name

    for change in changes:
        pair = (change.table, change.key)
        if pair not in EDITABLE:
            raise UneditableSettingError(change.table, change.key)
        variable = ENVIRONMENT_OVERRIDES[pair]
        if env.get(variable, "").strip():
            raise EnvironmentOverrideError(change.table, change.key, variable)

    try:
        raw_bytes = settings_path.read_bytes()
    except FileNotFoundError:
        raw_bytes = b""
    except OSError as error:
        message = f"{source} could not be read ({type(error).__name__})"
        raise ConfigError(message) from None

    current_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    if current_sha256 != expected_sha256.strip().lower():
        message = f"{source} changed on disk since it was loaded; reload and try again"
        raise StaleSettingsFileError(message)

    try:
        current_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        message = f"{source} is not valid UTF-8"
        raise ConfigError(message) from None

    parse_settings_toml(current_text, source=source)

    try:
        document = tomlkit.parse(current_text)
    except TOMLKitError:
        message = f"{source} is not valid TOML"
        raise ConfigError(message) from None

    next_cycle_keys: list[str] = []
    next_start_keys: list[str] = []

    for change in changes:
        _validate_change_type(change, source=source)
        if change.table not in document:
            document.add(change.table, tomlkit.table())
        section_obj = document[change.table]
        if not isinstance(section_obj, Table):
            message = f"[{change.table}] in {source}: is not a table"
            raise ConfigError(message)
        table_item = cast("dict[str, object]", section_obj)
        table_item[change.key] = change.value

        label = format_setting_key(change.table, change.key)
        timing = EDITABLE[change.table, change.key]
        if timing == "next_cycle":
            if label not in next_cycle_keys:
                next_cycle_keys.append(label)
        elif label not in next_start_keys:
            next_start_keys.append(label)

    rendered = tomlkit.dumps(document)
    if rendered and not rendered.endswith("\n"):
        rendered += "\n"

    parsed = parse_settings_toml(rendered, source=source)
    validated = validate_settings_document(parsed, env, source=source)

    rendered_bytes = rendered.encode("utf-8")
    ensure_directory(paths.config_dir)
    fd, tmp_name = tempfile.mkstemp(
        dir=paths.config_dir,
        prefix=".weatherbot-",
        suffix=".toml.tmp",
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(rendered_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        if sys.platform != "win32":
            tmp_path.chmod(FILE_OWNER_ONLY)
        _replace_with_retry(tmp_path, settings_path, sleep=sleep)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    return SettingsUpdate(
        settings_file_sha256=hashlib.sha256(rendered_bytes).hexdigest(),
        next_cycle=tuple(next_cycle_keys),
        next_start=tuple(next_start_keys),
        settings=validated,
    )
