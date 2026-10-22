# tests/cli/test_config_command.py
"""``weatherbot config show`` names each value's origin; ``config path`` names the files.

The directories are the test's own (``tests/conftest.py``); the tests compare paths and
print none.
"""

import re
from pathlib import Path
from typing import Final

import pytest
from cli_support import parse, run

from weatherbot.cli.documents import ConfigDocument, ConfigPathDocument
from weatherbot.services.config import ENVIRONMENT_OVERRIDES, AppPaths, Settings

FAILED: Final = 1
LOCK_WAIT: Final = "WEATHERBOT_MONITOR_CYCLE_LOCK_WAIT_SECONDS"


def _settings_file(text: str) -> Path:
    paths = AppPaths.resolve()
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    paths.settings_path.write_text(text, encoding="utf-8")
    return paths.settings_path


def test_config_show_lists_every_setting_at_its_default() -> None:
    document = parse(run(["config", "show", "--json"]), ConfigDocument)

    entries = {(entry.table, entry.key): entry for entry in document.data.settings}
    assert set(entries) == set(ENVIRONMENT_OVERRIDES)
    assert all(entry.origin == "default" for entry in entries.values())
    assert all(entry.variable == ENVIRONMENT_OVERRIDES[key] for key, entry in entries.items())
    defaults = Settings()
    assert entries["monitor", "cycle_lock_wait_seconds"].value == 120  # noqa: PLR2004 - the default
    assert entries["logging", "level"].value == defaults.logging.level
    assert entries["engine", "cone_horizon_h"].value == defaults.engine.cone_horizon_h
    assert not document.data.settings_file_exists


def test_config_show_names_a_file_value_and_an_environment_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written = _settings_file(
        "[http]\ntimeout_seconds = 12\n\n[monitor]\ncycle_lock_wait_seconds = 60\n"
    )
    monkeypatch.setenv(LOCK_WAIT, "30")

    document = parse(run(["config", "show", "--json"]), ConfigDocument)
    printed = run(["config", "show"])

    entries = {(entry.table, entry.key): entry for entry in document.data.settings}
    timeout = entries["http", "timeout_seconds"]
    assert (timeout.value, timeout.origin) == (12.0, "file")
    wait = entries["monitor", "cycle_lock_wait_seconds"]
    assert (wait.value, wait.origin, wait.variable) == (30, "environment", LOCK_WAIT)
    assert entries["logging", "level"].origin == "default"
    assert document.data.settings_file == str(written)
    assert document.data.settings_file_exists
    assert printed.exit_code == 0, printed.stderr
    assert re.search(
        rf"\[monitor\] cycle_lock_wait_seconds +30 +{LOCK_WAIT}$", printed.stdout, re.MULTILINE
    )
    assert re.search(r"\[http\] timeout_seconds +12\.0 +file$", printed.stdout, re.MULTILINE)
    assert re.search(r"\[logging\] level +INFO +default$", printed.stdout, re.MULTILINE)


def test_config_show_refuses_a_bad_value_and_names_its_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LOCK_WAIT, "0")

    result = run(["config", "show"])

    assert result.exit_code == FAILED
    assert LOCK_WAIT in result.stderr
    assert result.stdout == ""


def test_config_path_names_the_files_under_the_data_and_config_directories() -> None:
    document = parse(run(["config", "path", "--json"]), ConfigPathDocument)
    printed = run(["config", "path"])

    paths = AppPaths.resolve()
    data = document.data
    assert Path(data.config_dir) == paths.config_dir
    assert Path(data.settings_file) == paths.config_dir / "weatherbot.toml"
    assert Path(data.data_dir) == paths.data_dir
    assert Path(data.database_file) == paths.data_dir / "weatherbot.sqlite3"
    assert Path(data.backup_dir) == paths.data_dir / "backups"
    assert Path(data.cycle_lock_file) == paths.data_dir / "cycle.lock"
    assert Path(data.migrate_lock_file) == paths.data_dir / "migrate.lock"
    assert printed.exit_code == 0
    assert "Cycle lock" in printed.stdout
    assert "Migration lock" in printed.stdout
    assert not paths.data_dir.exists()  # printing the paths creates nothing
