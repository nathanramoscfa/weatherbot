# tests/web/test_web_settings.py
"""``[web]`` settings validation, environment overrides, and ``config show --json``."""

import pytest
from cli_support import parse, run

from weatherbot.cli.documents import ConfigDocument
from weatherbot.services.config import (
    AppPaths,
    ConfigError,
    Settings,
    WebSettings,
    load_settings,
    setting_origins,
)

UNECHOED_HOST = "192.168.1.10"


def _write_toml(paths: AppPaths, text: str) -> None:
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    paths.settings_path.write_text(text, encoding="utf-8")


def test_web_settings_defaults_and_overrides() -> None:
    defaults = Settings()
    assert defaults.web == WebSettings(host="127.0.0.1", port=8765)
    assert defaults.web.address() == "http://127.0.0.1:8765"
    assert WebSettings(host="::1", port=9000).address() == "http://[::1]:9000"

    paths = AppPaths.resolve()
    _write_toml(paths, '[web]\nhost = "localhost"\nport = 8800\n')
    from_file = load_settings(paths, {})
    assert (from_file.web.host, from_file.web.port) == ("localhost", 8800)

    from_env = load_settings(
        paths,
        {"WEATHERBOT_WEB_HOST": "::1", "WEATHERBOT_WEB_PORT": "9100"},
    )
    assert (from_env.web.host, from_env.web.port) == ("::1", 9100)

    origins = {
        (item.table, item.key): item
        for item in setting_origins(paths, {"WEATHERBOT_WEB_PORT": "0"})
    }
    assert origins["web", "host"].origin == "file"
    assert origins["web", "host"].value == "localhost"
    assert origins["web", "port"].origin == "environment"
    assert origins["web", "port"].value == 0


def test_config_show_json_includes_web_table() -> None:
    doc = parse(run(["config", "show", "--json"]), ConfigDocument)
    entries = {(entry.table, entry.key): entry for entry in doc.data.settings}
    assert ("web", "host") in entries
    assert ("web", "port") in entries
    assert entries["web", "host"].variable == "WEATHERBOT_WEB_HOST"
    assert entries["web", "port"].variable == "WEATHERBOT_WEB_PORT"


@pytest.mark.parametrize(
    "bad_host",
    [
        "0.0.0.0",  # noqa: S104 - testing rejection of non-loopback bind address
        "::",
        UNECHOED_HOST,
        "example.com",
    ],
)
def test_non_loopback_web_host_raises_config_error_naming_phase_8_and_never_value(
    bad_host: str,
) -> None:
    paths = AppPaths.resolve()
    _write_toml(paths, f'[web]\nhost = "{bad_host}"\n')

    with pytest.raises(ConfigError) as exc_info:
        load_settings(paths, {})

    message = str(exc_info.value)
    assert "[web] host" in message
    assert "Phase 8" in message
    assert bad_host not in message.replace("::1", "")


@pytest.mark.parametrize(
    ("toml_text", "rejected"),
    [
        ("[web]\nport = 80\n", "80"),
        ("[web]\nport = 1023\n", "1023"),
        ("[web]\nport = -1\n", "-1"),
        ("[web]\nport = 70000\n", "70000"),
    ],
)
def test_invalid_web_port_raises_config_error_without_echoing_value(
    toml_text: str, rejected: str
) -> None:
    paths = AppPaths.resolve()
    _write_toml(paths, toml_text)

    with pytest.raises(ConfigError) as exc_info:
        load_settings(paths, {})

    message = str(exc_info.value)
    assert "[web] port" in message
    assert f"= {rejected}" not in message
    assert "70000" not in message
