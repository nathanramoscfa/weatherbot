# src/weatherbot/services/tasks.py
r"""Windows Task Scheduler definitions, registration, removal, and state queries.

Weatherbot registers two scheduled tasks under ``\Weatherbot\`` without elevation:

- ``\Weatherbot\serve`` starts ``pythonw.exe -m weatherbot serve`` when the operator logs on,
  with no execution time limit and battery restrictions disabled.
- ``\Weatherbot\check`` starts ``pythonw.exe -m weatherbot check --once --if-stale`` at 25
  minutes past every hour (local time, after NHC's measured roster rewrites), with a
  30-minute time limit and ``StartWhenAvailable`` enabled.

Both tasks run under ``InteractiveToken`` and ``LeastPrivilege`` so Windows stores no password
and nothing runs elevated. Subprocesses invoke ``schtasks.exe`` and Windows PowerShell 5.1 by
their absolute paths under ``%SystemRoot%\System32`` with ``CREATE_NO_WINDOW``.
"""

import html
import json
import os
import subprocess  # fixed argument lists under System32, never a shell  # nosec B404
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PureWindowsPath
from typing import Final, Literal, Protocol, cast

from sqlalchemy.engine import Engine

from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import DatabaseError, open_database
from weatherbot.services.schedule import clear_runner_heartbeat_cadence

type TaskName = Literal["serve", "check"]

TASK_FOLDER: Final = "\\Weatherbot\\"
TASK_NAMES: Final[tuple[TaskName, ...]] = ("serve", "check")
CREATE_NO_WINDOW: Final = 0x08000000
SUBPROCESS_TIMEOUT_S: Final = 60
CHECK_START_MINUTE: Final = 25

TASK_RUNNING_RESULT: Final = 0x41301
TASK_NOT_RUN_RESULT: Final = 0x41303
HEALTHY_TASK_RESULTS: Final[frozenset[int]] = frozenset(
    {0, TASK_RUNNING_RESULT, TASK_NOT_RUN_RESULT}
)

ON_WINDOWS: Final = sys.platform == "win32"

_SYSTEM_ROOT: Final = PureWindowsPath(os.environ.get("SYSTEMROOT", r"C:\Windows"))
_SYSTEM32: Final = _SYSTEM_ROOT / "System32"
SCHTASKS_EXE: Final = str(_SYSTEM32 / "schtasks.exe")
POWERSHELL_EXE: Final = str(_SYSTEM32 / "WindowsPowerShell" / "v1.0" / "powershell.exe")

SERVE_ARGUMENTS: Final = "-m weatherbot serve"
CHECK_ARGUMENTS: Final = "-m weatherbot check --once --if-stale"
SERVE_TIME_LIMIT: Final = "PT0S"
CHECK_TIME_LIMIT: Final = "PT30M"
CHECK_INTERVAL: Final = "PT1H"

QUERY_SCRIPT: Final = (
    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
    "$folder = '\\Weatherbot\\'; "
    "$items = @("
    "Get-ScheduledTask -TaskPath $folder -ErrorAction SilentlyContinue | ForEach-Object { "
    "$info = $_ | Get-ScheduledTaskInfo -ErrorAction SilentlyContinue; "
    "$action = $_.Actions | Select-Object -First 1; "
    "[PSCustomObject]@{ "
    "name = [string]$_.TaskName; "
    "state = [string]$_.State; "
    "enabled = [bool]$_.Settings.Enabled; "
    "command = if ($null -ne $action) { [string]$action.Execute } else { '' }; "
    "arguments = if ($null -ne $action) { [string]$action.Arguments } else { '' }; "
    "working_directory = if ($null -ne $action) { [string]$action.WorkingDirectory } else { '' }; "
    "logon_type = [string]$_.Principal.LogonType; "
    "run_level = [string]$_.Principal.RunLevel; "
    "last_run_time = if ($null -ne $info -and $null -ne $info.LastRunTime) "
    "{ $info.LastRunTime.ToString('o') } else { $null }; "
    "next_run_time = if ($null -ne $info -and $null -ne $info.NextRunTime) "
    "{ $info.NextRunTime.ToString('o') } else { $null }; "
    "last_task_result = if ($null -ne $info) { $info.LastTaskResult } else { $null } "
    "} "
    "}); "
    "ConvertTo-Json -InputObject $items -Depth 4 -Compress"
)

_ABSENT_MARKERS: Final[tuple[str, ...]] = (
    "cannot find the file",
    "cannot find the path",
    "does not exist",
    "not found",
    "no msft_scheduledtask",
    "0x80070002",
)


class TaskSchedulerError(RuntimeError):
    """Task Scheduler refused a command or returned invalid output."""


class SubprocessRunner(Protocol):
    """Callable seam that runs a System32 command without a shell."""

    def __call__(
        self, argv: Sequence[str], *, creationflags: int = CREATE_NO_WINDOW
    ) -> subprocess.CompletedProcess[str]:
        """Execute ``argv`` and return its completed process."""
        ...


@dataclass(frozen=True)
class TaskOutcome:
    """The outcome of registering, starting, or removing one scheduled task."""

    name: str
    task_name: str
    ok: bool
    returncode: int
    detail: str | None = None


@dataclass(frozen=True)
class UninstallResult:
    """The outcomes of stopping ``serve`` and deleting both scheduled tasks."""

    stopped_serve: bool
    outcomes: tuple[TaskOutcome, ...]


@dataclass(frozen=True)
class ScheduledTask:
    r"""One scheduled task under ``\Weatherbot\`` read back from Task Scheduler."""

    name: str
    state: str
    enabled: bool
    command: str
    arguments: str
    working_directory: str
    logon_type: str
    run_level: str
    last_run_time: datetime | None = None
    next_run_time: datetime | None = None
    last_task_result: int | None = None


def run_subprocess(
    argv: Sequence[str], *, creationflags: int = CREATE_NO_WINDOW
) -> subprocess.CompletedProcess[str]:
    """Run an absolute ``System32`` executable with ``CREATE_NO_WINDOW``."""
    executable = str(argv[0]) if argv else ""
    if "system32" not in executable.lower() or creationflags != CREATE_NO_WINDOW:
        msg = (
            "Task Scheduler subprocesses require an absolute System32 executable "
            "and CREATE_NO_WINDOW."
        )
        raise ValueError(msg)
    return subprocess.run(  # noqa: S603 - fixed System32 argument list, no shell  # nosec B603
        list(argv),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=SUBPROCESS_TIMEOUT_S,
        check=False,
        creationflags=CREATE_NO_WINDOW,
    )


def current_user_id(env: Mapping[str, str] | None = None) -> str:
    r"""Return the current interactive session's ``USERDOMAIN\USERNAME``."""
    environment = os.environ if env is None else env
    username = environment.get("USERNAME", "").strip()
    if not username:
        msg = "USERNAME is not set in the environment."
        raise TaskSchedulerError(msg)
    domain = environment.get("USERDOMAIN", "").strip()
    return f"{domain}\\{username}" if domain else username


def resolve_pythonw(executable: Path | None = None) -> Path:
    """Return ``pythonw.exe`` beside ``executable`` (or ``sys.executable``), verifying it exists."""
    base = Path(sys.executable) if executable is None else Path(executable)
    target = base if base.name.lower() == "pythonw.exe" else base.with_name("pythonw.exe")
    if not target.is_file():
        msg = f"pythonw.exe was not found beside the interpreter ({target.name})."
        raise TaskSchedulerError(msg)
    return target


def is_checkout_interpreter(interpreter: Path | None = None) -> bool:
    """Return whether ``interpreter`` belongs to a Weatherbot source checkout's environment."""
    target = Path(sys.executable) if interpreter is None else Path(interpreter)
    env_dir = (
        target.parent.parent if target.parent.name.lower() in {"scripts", "bin"} else target.parent
    )
    for directory in (env_dir, env_dir.parent, target.parent.parent):
        pyproject = directory / "pyproject.toml"
        if not pyproject.is_file():
            continue
        try:
            parsed = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        project = parsed.get("project")
        if (
            isinstance(project, dict)
            and cast("dict[str, object]", project).get("name") == "weatherbot"
        ):
            return True
    return False


def check_start_boundary(reference: datetime | None = None) -> datetime:
    """Return the next hour at 25 minutes past from ``reference`` (in local time)."""
    base = datetime.now().astimezone() if reference is None else reference
    if base.tzinfo is None:
        base = base.astimezone()
    if (base.minute, base.second, base.microsecond) <= (CHECK_START_MINUTE, 0, 0):
        return base.replace(minute=CHECK_START_MINUTE, second=0, microsecond=0)
    next_hour = base.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return next_hour.replace(minute=CHECK_START_MINUTE)


def logon_trigger_xml(user_id: str) -> str:
    """Render a ``LogonTrigger`` for ``user_id``."""
    escaped_user = html.escape(user_id, quote=True)
    return (
        "    <LogonTrigger>\n"
        "      <Enabled>true</Enabled>\n"
        f"      <UserId>{escaped_user}</UserId>\n"
        "    </LogonTrigger>"
    )


def hourly_trigger_xml(start: datetime) -> str:
    """Render an indefinite hourly ``TimeTrigger`` starting at ``start``."""
    escaped_start = html.escape(start.isoformat(timespec="seconds"), quote=True)
    return (
        "    <TimeTrigger>\n"
        "      <Repetition>\n"
        f"        <Interval>{CHECK_INTERVAL}</Interval>\n"
        "        <StopAtDurationEnd>false</StopAtDurationEnd>\n"
        "      </Repetition>\n"
        f"      <StartBoundary>{escaped_start}</StartBoundary>\n"
        "      <Enabled>true</Enabled>\n"
        "    </TimeTrigger>"
    )


def definition_xml(  # noqa: PLR0913 - explicit task definition attributes
    name: str,
    *,
    user_id: str,
    command: Path | str,
    arguments: str,
    working_directory: Path | str,
    trigger: str,
    enabled: bool = True,
    time_limit: str = SERVE_TIME_LIMIT,
    start_when_available: bool = False,
) -> str:
    """Render a Task Scheduler 1.2 XML document with every inserted value escaped."""
    short_name = name.removeprefix(TASK_FOLDER).lstrip("\\")
    uri = f"{TASK_FOLDER}{short_name}"
    escaped_short = html.escape(short_name, quote=True)
    escaped_uri = html.escape(uri, quote=True)
    escaped_user = html.escape(user_id, quote=True)
    escaped_command = html.escape(str(command), quote=True)
    escaped_arguments = html.escape(arguments, quote=True)
    escaped_workdir = html.escape(str(working_directory), quote=True)
    escaped_limit = html.escape(time_limit, quote=True)
    enabled_xml = "true" if enabled else "false"
    start_available_xml = "true" if start_when_available else "false"
    trigger_xml = logon_trigger_xml(user_id) if trigger == "logon" else trigger
    return (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        "  <RegistrationInfo>\n"
        f"    <Description>Registered by weatherbot install-task ({escaped_short}).</Description>\n"
        f"    <URI>{escaped_uri}</URI>\n"
        "  </RegistrationInfo>\n"
        "  <Triggers>\n"
        f"{trigger_xml}\n"
        "  </Triggers>\n"
        "  <Principals>\n"
        '    <Principal id="Author">\n'
        f"      <UserId>{escaped_user}</UserId>\n"
        "      <LogonType>InteractiveToken</LogonType>\n"
        "      <RunLevel>LeastPrivilege</RunLevel>\n"
        "    </Principal>\n"
        "  </Principals>\n"
        "  <Settings>\n"
        "    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n"
        "    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n"
        "    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n"
        "    <AllowHardTerminate>true</AllowHardTerminate>\n"
        f"    <StartWhenAvailable>{start_available_xml}</StartWhenAvailable>\n"
        "    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>\n"
        "    <AllowStartOnDemand>true</AllowStartOnDemand>\n"
        f"    <Enabled>{enabled_xml}</Enabled>\n"
        "    <Hidden>false</Hidden>\n"
        "    <RunOnlyIfIdle>false</RunOnlyIfIdle>\n"
        "    <WakeToRun>false</WakeToRun>\n"
        f"    <ExecutionTimeLimit>{escaped_limit}</ExecutionTimeLimit>\n"
        "    <Priority>7</Priority>\n"
        "  </Settings>\n"
        '  <Actions Context="Author">\n'
        "    <Exec>\n"
        f"      <Command>{escaped_command}</Command>\n"
        f"      <Arguments>{escaped_arguments}</Arguments>\n"
        f"      <WorkingDirectory>{escaped_workdir}</WorkingDirectory>\n"
        "    </Exec>\n"
        "  </Actions>\n"
        "</Task>\n"
    )


def task_xml(
    task: TaskName,
    *,
    user_id: str,
    interpreter: Path | str,
    working_directory: Path | str,
    start: datetime | None = None,
) -> str:
    """Render the XML definition for ``serve`` or ``check``."""
    if task == "serve":
        return definition_xml(
            "serve",
            user_id=user_id,
            command=interpreter,
            arguments=SERVE_ARGUMENTS,
            working_directory=working_directory,
            trigger=logon_trigger_xml(user_id),
            enabled=True,
            time_limit=SERVE_TIME_LIMIT,
            start_when_available=False,
        )
    if task == "check":
        boundary = check_start_boundary(start)
        return definition_xml(
            "check",
            user_id=user_id,
            command=interpreter,
            arguments=CHECK_ARGUMENTS,
            working_directory=working_directory,
            trigger=hourly_trigger_xml(boundary),
            enabled=True,
            time_limit=CHECK_TIME_LIMIT,
            start_when_available=True,
        )
    msg = f"Unknown task name: {task!r}"
    raise ValueError(msg)


def _output_detail(proc: subprocess.CompletedProcess[str]) -> str | None:
    text = (proc.stderr or proc.stdout).strip()
    if not text:
        return None
    return text.splitlines()[0].strip()


def _is_absent(proc: subprocess.CompletedProcess[str]) -> bool:
    combined = f"{proc.stdout}\n{proc.stderr}".lower()
    return any(marker in combined for marker in _ABSENT_MARKERS)


def write_xml_file(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` as UTF-16 little-endian with a byte-order mark."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-16"))


def install(  # noqa: PLR0913 - explicit task installation seams
    paths: AppPaths,
    *,
    interpreter: Path | str | None = None,
    user_id: str | None = None,
    env: Mapping[str, str] | None = None,
    start: datetime | None = None,
    runner: SubprocessRunner = run_subprocess,
) -> tuple[TaskOutcome, ...]:
    """Write each task's UTF-16 XML to ``paths.data_dir``, register it, and delete the XML."""
    resolved_interpreter = resolve_pythonw(Path(interpreter) if interpreter is not None else None)
    resolved_user = current_user_id(env) if user_id is None else user_id
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    outcomes: list[TaskOutcome] = []
    for task in TASK_NAMES:
        xml_path = paths.data_dir / f"task-{task}.xml"
        xml_text = task_xml(
            task,
            user_id=resolved_user,
            interpreter=resolved_interpreter,
            working_directory=paths.data_dir,
            start=start,
        )
        task_name = f"{TASK_FOLDER}{task}"
        try:
            write_xml_file(xml_path, xml_text)
            proc = runner(
                [SCHTASKS_EXE, "/Create", "/TN", task_name, "/XML", str(xml_path), "/F"],
                creationflags=CREATE_NO_WINDOW,
            )
        finally:
            xml_path.unlink(missing_ok=True)
        outcomes.append(
            TaskOutcome(
                name=task,
                task_name=task_name,
                ok=proc.returncode == 0,
                returncode=proc.returncode,
                detail=None if proc.returncode == 0 else _output_detail(proc),
            )
        )
    return tuple(outcomes)


def uninstall(
    *,
    engine: Engine | None = None,
    paths: AppPaths | None = None,
    now: datetime | None = None,
    runner: SubprocessRunner = run_subprocess,
) -> UninstallResult:
    """End a running ``serve`` task, delete both tasks, and clear ``serve``'s heartbeat cadence."""
    serve_task = f"{TASK_FOLDER}serve"
    end_proc = runner(
        [SCHTASKS_EXE, "/End", "/TN", serve_task],
        creationflags=CREATE_NO_WINDOW,
    )
    stopped_serve = end_proc.returncode == 0
    outcomes: list[TaskOutcome] = []
    for task in TASK_NAMES:
        task_name = f"{TASK_FOLDER}{task}"
        proc = runner(
            [SCHTASKS_EXE, "/Delete", "/TN", task_name, "/F"],
            creationflags=CREATE_NO_WINDOW,
        )
        absent = proc.returncode != 0 and _is_absent(proc)
        ok = proc.returncode == 0 or absent
        detail = "absent" if absent else (None if ok else _output_detail(proc))
        outcomes.append(
            TaskOutcome(
                name=task,
                task_name=task_name,
                ok=ok,
                returncode=0 if absent else proc.returncode,
                detail=detail,
            )
        )
    _clear_serve_cadence(engine=engine, paths=paths, now=now)
    return UninstallResult(stopped_serve=stopped_serve, outcomes=tuple(outcomes))


def _clear_serve_cadence(
    *, engine: Engine | None, paths: AppPaths | None, now: datetime | None
) -> None:
    instant = datetime.now(UTC) if now is None else now
    if engine is not None:
        clear_runner_heartbeat_cadence(engine, "serve", now=instant)
        return
    try:
        resolved = AppPaths.resolve() if paths is None else paths
    except Exception:  # noqa: BLE001 - best-effort cleanup when paths are unconfigured
        return
    if not resolved.database_path.is_file():
        return
    try:
        with open_database(resolved) as database:
            clear_runner_heartbeat_cadence(database.engine, "serve", now=instant)
    except (DatabaseError, OSError):
        return


def run(name: TaskName | str, *, runner: SubprocessRunner = run_subprocess) -> TaskOutcome:
    r"""Start ``\Weatherbot\<name>`` on demand via ``schtasks.exe /Run``."""
    short = name.removeprefix(TASK_FOLDER).lstrip("\\")
    if short not in TASK_NAMES:
        msg = f"Unknown task name: {name!r}"
        raise ValueError(msg)
    task_name = f"{TASK_FOLDER}{short}"
    proc = runner(
        [SCHTASKS_EXE, "/Run", "/TN", task_name],
        creationflags=CREATE_NO_WINDOW,
    )
    return TaskOutcome(
        name=short,
        task_name=task_name,
        ok=proc.returncode == 0,
        returncode=proc.returncode,
        detail=None if proc.returncode == 0 else _output_detail(proc),
    )


def _parse_instant(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.year < 2000:  # noqa: PLR2004 - Windows Task Scheduler uses 0001/1999 for never/none
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_result(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value & 0xFFFFFFFF if value < 0 else value
    if isinstance(value, str) and value.strip():
        raw = value.strip()
        try:
            parsed = int(raw, 16) if raw.lower().startswith("0x") else int(raw)
        except ValueError:
            return None
        return parsed & 0xFFFFFFFF if parsed < 0 else parsed
    return None


def _string_field(mapping: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str):
            return value
    return ""


def _bool_field(mapping: Mapping[str, object], *keys: str, default: bool = False) -> bool:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            if value.lower() == "true":
                return True
            if value.lower() == "false":
                return False
    return default


def _parse_task_object(item: object) -> ScheduledTask:
    if not isinstance(item, dict):
        msg = "Task Scheduler JSON item is not an object."
        raise TaskSchedulerError(msg)
    mapping = cast("dict[str, object]", item)
    raw_name = _string_field(mapping, "name", "Name", "TaskName")
    name = raw_name.removeprefix(TASK_FOLDER).lstrip("\\")
    if not name:
        msg = "Task Scheduler JSON item is missing a task name."
        raise TaskSchedulerError(msg)
    return ScheduledTask(
        name=name,
        state=_string_field(mapping, "state", "State") or "Unknown",
        enabled=_bool_field(mapping, "enabled", "Enabled", default=False),
        command=_string_field(mapping, "command", "Command", "Execute"),
        arguments=_string_field(mapping, "arguments", "Arguments"),
        working_directory=_string_field(mapping, "working_directory", "WorkingDirectory"),
        logon_type=_string_field(mapping, "logon_type", "LogonType"),
        run_level=_string_field(mapping, "run_level", "RunLevel"),
        last_run_time=_parse_instant(mapping.get("last_run_time", mapping.get("LastRunTime"))),
        next_run_time=_parse_instant(mapping.get("next_run_time", mapping.get("NextRunTime"))),
        last_task_result=_parse_result(
            mapping.get("last_task_result", mapping.get("LastTaskResult"))
        ),
    )


def query(*, runner: SubprocessRunner = run_subprocess) -> tuple[ScheduledTask, ...]:
    r"""Read every task under ``\Weatherbot\`` from one PowerShell 5.1 JSON call."""
    proc = runner(
        [
            POWERSHELL_EXE,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            QUERY_SCRIPT,
        ],
        creationflags=CREATE_NO_WINDOW,
    )
    if proc.returncode != 0:
        if _is_absent(proc):
            return ()
        detail = _output_detail(proc) or f"exit {proc.returncode}"
        msg = f"Task Scheduler query failed ({detail})."
        raise TaskSchedulerError(msg)
    text = proc.stdout.strip()
    if not text or text == "null":
        return ()
    try:
        loaded: object = json.loads(text)
    except json.JSONDecodeError as error:
        msg = "Task Scheduler query returned invalid JSON."
        raise TaskSchedulerError(msg) from error
    if loaded is None:
        return ()
    if isinstance(loaded, dict):
        return (_parse_task_object(cast("dict[str, object]", loaded)),)
    if isinstance(loaded, list):
        items = cast("list[object]", loaded)
        return tuple(_parse_task_object(item) for item in items)
    msg = "Task Scheduler query returned an unexpected JSON type."
    raise TaskSchedulerError(msg)
