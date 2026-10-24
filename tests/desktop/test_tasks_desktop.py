# tests/desktop/test_tasks_desktop.py
r"""Real Task Scheduler probe on the operator's Windows machine (``pytest -m desktop``).

Registers a disposable, disabled ``\Weatherbot\probe`` task without elevation using
``definition_xml``, reads it back via ``query()``, and deletes it in a ``finally`` block.
"""

import os
import sys
from pathlib import Path, PureWindowsPath

import pytest

from weatherbot.services.tasks import (
    CREATE_NO_WINDOW,
    SCHTASKS_EXE,
    TASK_FOLDER,
    current_user_id,
    definition_xml,
    query,
    run_subprocess,
    write_xml_file,
)


@pytest.mark.desktop
def test_unelevated_task_registers_reads_back_and_deletes(tmp_path: Path) -> None:
    assert sys.platform == "win32", "the desktop tests run on the operator's Windows machine"
    user_id = current_user_id()
    system_root = PureWindowsPath(os.environ.get("SYSTEMROOT", r"C:\Windows"))
    cmd_exe = str(system_root / "System32" / "cmd.exe")
    task_name = f"{TASK_FOLDER}probe"
    xml_path = tmp_path / "task-probe.xml"

    xml_text = definition_xml(
        task_name,
        user_id=user_id,
        command=cmd_exe,
        arguments="/c exit 0",
        working_directory=tmp_path,
        trigger="logon",
        enabled=False,
    )
    write_xml_file(xml_path, xml_text)
    try:
        created = run_subprocess(
            [SCHTASKS_EXE, "/Create", "/TN", task_name, "/XML", str(xml_path), "/F"],
            creationflags=CREATE_NO_WINDOW,
        )
        assert created.returncode == 0, created.stderr or created.stdout

        tasks = query()
        probe = next((t for t in tasks if t.name == "probe"), None)
        assert probe is not None
        assert probe.enabled is False
        assert probe.logon_type == "InteractiveToken"
        assert probe.run_level == "LeastPrivilege"
        assert probe.arguments == "/c exit 0"
    finally:
        xml_path.unlink(missing_ok=True)
        run_subprocess(
            [SCHTASKS_EXE, "/Delete", "/TN", task_name, "/F"],
            creationflags=CREATE_NO_WINDOW,
        )
