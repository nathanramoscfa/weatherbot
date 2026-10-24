# src/weatherbot/cli/tasks.py
r"""``weatherbot install-task`` and ``weatherbot uninstall-task``: Task Scheduler registration.

``install-task`` registers the toast application identity (if missing), registers
``\Weatherbot\serve`` (logon trigger) and ``\Weatherbot\check`` (hourly trigger at 25 minutes
past the hour) using ``pythonw.exe`` beside the running interpreter, and reads both tasks back
from Task Scheduler. Unless ``--allow-checkout`` is passed, it refuses to register a source
checkout's virtual environment. ``uninstall-task`` stops ``\Weatherbot\serve``, deletes both
tasks, and clears the ``serve`` runner heartbeat's expected cadence.
"""

import os
from typing import Annotated

import typer

from weatherbot.cli.documents import (
    InstallTaskData,
    InstallTaskDocument,
    ScheduledTaskEntry,
    TaskOutcomeEntry,
    UninstallTaskData,
    UninstallTaskDocument,
)
from weatherbot.cli.notify import SETUP_LINES
from weatherbot.cli.runtime import (
    EXIT_FAILED,
    EXIT_OK,
    EXIT_USAGE,
    Output,
    context_of,
    fail,
)
from weatherbot.cli.snapshots import JsonOption, utc
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.tasks import (
    ScheduledTask,
    TaskOutcome,
    TaskSchedulerError,
    install,
    is_checkout_interpreter,
    query,
    resolve_pythonw,
    uninstall,
)

WINDOWS_ONLY = "Task Scheduler commands are only available on Windows"
CHECKOUT_REFUSED = (
    "refusing to register a source checkout environment; install the tool first with "
    "'uv tool install --from <checkout> weatherbot' (or pass --allow-checkout)"
)


def _outcome_entries(outcomes: tuple[TaskOutcome, ...]) -> tuple[TaskOutcomeEntry, ...]:
    return tuple(
        TaskOutcomeEntry(
            name=item.name,
            task_name=item.task_name,
            ok=item.ok,
            returncode=item.returncode,
            detail=item.detail,
        )
        for item in outcomes
    )


def _task_entries(tasks: tuple[ScheduledTask, ...]) -> tuple[ScheduledTaskEntry, ...]:
    return tuple(
        ScheduledTaskEntry(
            name=item.name,
            state=item.state,
            enabled=item.enabled,
            last_run_time=item.last_run_time,
            next_run_time=item.next_run_time,
            last_task_result=item.last_task_result,
        )
        for item in tasks
    )


def _print_install(output: Output, data: InstallTaskData) -> None:
    output.line(SETUP_LINES[data.identity_outcome])
    output.table(
        "Scheduled tasks registered",
        ("Task", "Full name", "Status", "Detail"),
        [
            (
                task.name,
                task.task_name,
                "registered" if task.ok else f"failed ({task.returncode})",
                task.detail or "-",
            )
            for task in data.outcomes
        ],
    )
    if data.tasks:
        output.table(
            "Task Scheduler state",
            ("Task", "State", "Enabled", "Next run"),
            [
                (
                    task.name,
                    task.state,
                    "yes" if task.enabled else "no",
                    utc(task.next_run_time) if task.next_run_time else "-",
                )
                for task in data.tasks
            ],
        )


def _print_uninstall(output: Output, data: UninstallTaskData) -> None:
    output.table(
        "Scheduled tasks removed",
        ("Task", "Full name", "Status", "Detail"),
        [
            (
                task.name,
                task.task_name,
                "removed" if task.ok else f"failed ({task.returncode})",
                task.detail or "-",
            )
            for task in data.outcomes
        ],
    )


def install_task(
    ctx: typer.Context,
    *,
    allow_checkout: Annotated[
        bool,
        typer.Option(
            "--allow-checkout",
            help="Allow registering a source checkout interpreter.",
        ),
    ] = False,
    json_output: JsonOption = False,
) -> None:
    r"""Register ``\Weatherbot\serve`` and ``\Weatherbot\check`` in Windows Task Scheduler."""
    context = context_of(ctx)
    output = Output(context.runtime, json_mode=json_output)
    if not context.runtime.windows:
        fail(output, WINDOWS_ONLY, EXIT_USAGE)

    if not allow_checkout and is_checkout_interpreter(context.runtime.interpreter):
        fail(output, CHECKOUT_REFUSED, EXIT_USAGE)

    if context.paths is None or context.problem:
        fail(output, context.problem or "the configuration is unusable")

    try:
        identity_outcome = context.runtime.identity().register()
    except OSError as error:
        fail(output, f"the registry refused the change ({type(error).__name__})")

    env = os.environ if context.runtime.environ is None else context.runtime.environ
    try:
        pythonw = resolve_pythonw(context.runtime.interpreter)
        outcomes = install(
            context.paths,
            interpreter=pythonw,
            env=env,
            start=context.runtime.now().astimezone(),
            runner=context.runtime.task_runner,
        )
        queried = query(runner=context.runtime.task_runner)
    except TaskSchedulerError as error:
        fail(output, str(error), EXIT_FAILED)

    failed = not all(item.ok for item in outcomes)
    data = InstallTaskData(
        identity_outcome=identity_outcome,
        outcomes=_outcome_entries(outcomes),
        tasks=_task_entries(queried),
        failed=failed,
    )
    code = EXIT_FAILED if failed else EXIT_OK
    if json_output:
        output.document(
            InstallTaskDocument(
                generated_at=context.runtime.now(),
                disclaimer=NOTICE,
                data=data,
            )
        )
        raise typer.Exit(code)
    _print_install(output, data)
    output.notice()
    raise typer.Exit(code)


def uninstall_task(
    ctx: typer.Context,
    *,
    json_output: JsonOption = False,
) -> None:
    r"""Stop ``\Weatherbot\serve`` and remove both Weatherbot scheduled tasks."""
    context = context_of(ctx)
    output = Output(context.runtime, json_mode=json_output)
    if not context.runtime.windows:
        fail(output, WINDOWS_ONLY, EXIT_USAGE)

    now = context.runtime.now()
    result = uninstall(
        paths=context.paths,
        now=now,
        runner=context.runtime.task_runner,
    )
    failed = not all(item.ok for item in result.outcomes)
    data = UninstallTaskData(
        stopped_serve=result.stopped_serve,
        outcomes=_outcome_entries(result.outcomes),
        failed=failed,
    )
    code = EXIT_FAILED if failed else EXIT_OK
    if json_output:
        output.document(
            UninstallTaskDocument(
                generated_at=now,
                disclaimer=NOTICE,
                data=data,
            )
        )
        raise typer.Exit(code)
    _print_uninstall(output, data)
    output.notice()
    raise typer.Exit(code)
