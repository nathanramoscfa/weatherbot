# src/weatherbot/cli/notify.py
"""``weatherbot notify``: the notification log, the toast's identity, and a test toast.

``notify log`` lists the stored notifications newest first, each with its time in UTC and
in the location's time zone when known, its location, its title and body, and every
channel delivery's result. With ``--json`` it prints a ``notifications`` document that also
holds the decisions of the cycle that sent each notification.

``notify setup`` registers the toast's application identity under ``HKEY_CURRENT_USER``
(``--remove`` removes it) and says which; off Windows it changes nothing. ``notify test``
stores a test notification, which names no location, delivers it through every channel,
and prints each result; it exits 1 when a channel failed or was disabled, or when the
toast was unavailable on Windows with ``[notifications] toast`` on (the identity is
missing).
"""

import asyncio
from collections.abc import Sequence
from typing import Annotated, Final

import typer

from weatherbot.cli.documents import (
    NotificationDecisionEntry,
    NotificationDeliveryEntry,
    NotificationEntry,
    NotificationsData,
    NotificationsDocument,
    NotifySetupData,
    NotifySetupDocument,
    NotifyTestData,
    NotifyTestDocument,
)
from weatherbot.cli.runtime import EXIT_FAILED, EXIT_OK, Output, context_of, fail, open_session
from weatherbot.cli.snapshots import JsonOption, named_zone, when
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.notifications import (
    TEST_BODY,
    TEST_TITLE,
    NotificationService,
    StoredNotification,
)
from weatherbot.services.toast import (
    APP_ID,
    DISPLAY_NAME,
    IDENTITY_PATH,
    IdentityOutcome,
    delivery_failed,
)

DEFAULT_LIMIT: Final = 20
SETUP_LINES: Final[dict[IdentityOutcome, str]] = {
    "registered": f"Registered the toast identity {APP_ID} ({DISPLAY_NAME}) at {IDENTITY_PATH}.",
    "unchanged": f"The toast identity {APP_ID} is registered already; nothing changed.",
    "removed": f"Removed the toast identity {APP_ID} from {IDENTITY_PATH}.",
    "absent": f"The toast identity {APP_ID} is not registered; nothing to remove.",
    "not_needed": "Not Windows: toasts need no identity here, and nothing changed.",
}

app = typer.Typer(
    name="notify",
    help="The notification log, the toast's identity, and a test notification.",
    no_args_is_help=True,
)


def notification_entry(item: StoredNotification) -> NotificationEntry:
    """Turn a ``StoredNotification`` into its document entry."""
    zone = named_zone(item.location_time_zone)
    local_iso = item.created_at.astimezone(zone).isoformat() if zone is not None else None
    return NotificationEntry(
        id=item.id,
        location=item.location_name,
        time_zone=item.location_time_zone,
        assessment_id=item.assessment_id,
        cycle_id=item.cycle_id,
        kind=item.kind,
        level=int(item.level) if item.level is not None else None,
        escalation=item.escalation,
        title=item.title,
        body=item.body,
        created_at=item.created_at,
        created_at_local=local_iso,
        deliveries=tuple(
            NotificationDeliveryEntry(
                id=d.id,
                channel=d.channel,
                attempted_at=d.attempted_at,
                result=d.result,
                detail=d.detail,
            )
            for d in item.deliveries
        ),
        decisions=tuple(
            NotificationDecisionEntry(
                id=dec.id,
                location=dec.location_name,
                assessment_id=dec.assessment_id,
                change_position=dec.change_position,
                trigger=dec.trigger,
                event_key=dec.event_key,
                decision=dec.decision,
                level_after=int(dec.level_after) if dec.level_after is not None else None,
                notification_id=dec.notification_id,
                decided_at=dec.decided_at,
            )
            for dec in item.decisions
        ),
    )


def notification_entries(
    items: Sequence[StoredNotification],
) -> tuple[NotificationEntry, ...]:
    """Turn a sequence of ``StoredNotification`` records into document entries."""
    return tuple(notification_entry(item) for item in items)


def _print_log(output: Output, data: NotificationsData) -> None:
    if not data.notifications:
        output.line("No notifications are stored.")
        return
    for index, entry in enumerate(data.notifications):
        if index > 0:
            output.line()
        zone = named_zone(entry.time_zone)
        location_label = entry.location or entry.kind
        output.line(
            f"[{when(entry.created_at, zone)}] {location_label} — {entry.title}",
            style="bold",
        )
        for line in entry.body:
            output.line(f"  {line}")
        if entry.deliveries:
            channels = ", ".join(
                f"{d.channel}: {d.result}" + (f" ({d.detail})" if d.detail else "")
                for d in entry.deliveries
            )
            output.line(f"  Deliveries: {channels}")


@app.command("log")
def log(
    ctx: typer.Context,
    *,
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            min=1,
            help="Maximum notifications to list, newest first.",
        ),
    ] = DEFAULT_LIMIT,
    json_output: JsonOption = False,
) -> None:
    """List the stored notifications, newest first, with their deliveries."""
    context = context_of(ctx)
    output = Output(context.runtime, json_mode=json_output)
    with open_session(context, output) as database:
        service = NotificationService(
            database.engine,
            settings=context.settings,
            now=context.runtime.now,
        )
        stored = service.recent(limit=limit)
    now = context.runtime.now()
    data = NotificationsData(
        limit=limit,
        notifications=notification_entries(stored),
    )
    if json_output:
        output.document(NotificationsDocument(generated_at=now, disclaimer=NOTICE, data=data))
        raise typer.Exit(EXIT_OK)
    _print_log(output, data)
    output.notice()
    raise typer.Exit(EXIT_OK)


@app.command("setup")
def setup(
    ctx: typer.Context,
    *,
    remove: Annotated[
        bool, typer.Option("--remove", help="Remove the identity instead of registering it.")
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Register the toast's identity under HKEY_CURRENT_USER (Windows), or remove it."""
    context = context_of(ctx)
    output = Output(context.runtime, json_mode=json_output)
    identity = context.runtime.identity()
    try:
        outcome = identity.unregister() if remove else identity.register()
    except OSError as error:
        fail(output, f"the registry refused the change ({type(error).__name__})")
    data = NotifySetupData(
        action="remove" if remove else "register",
        outcome=outcome,
        app_id=APP_ID,
        display_name=DISPLAY_NAME,
        registry_key=IDENTITY_PATH if identity.needed else None,
    )
    if json_output:
        output.document(
            NotifySetupDocument(generated_at=context.runtime.now(), disclaimer=NOTICE, data=data)
        )
        raise typer.Exit(EXIT_OK)
    output.line(SETUP_LINES[outcome])
    raise typer.Exit(EXIT_OK)


def _print_test(output: Output, data: NotifyTestData) -> None:
    entry = data.notification
    output.line(f"Sent a test notification: {entry.title}")
    for delivery in entry.deliveries:
        detail = f" ({delivery.detail})" if delivery.detail else ""
        output.line(f"  {delivery.channel}: {delivery.result}{detail}")
    if data.failed:
        output.line("FAILED: a channel did not deliver it", style="bold red")
    else:
        output.line("Every channel answered as expected.", style="bold green")


@app.command("test")
def send_test(ctx: typer.Context, *, json_output: JsonOption = False) -> None:
    """Send a test notification through every channel, and print what each did with it."""
    context = context_of(ctx)
    output = Output(context.runtime, json_mode=json_output)
    with open_session(context, output) as database:
        service = NotificationService(
            database.engine,
            settings=context.settings,
            now=context.runtime.now,
            channels=context.channels,
        )
        sent = asyncio.run(service.send("test", title=TEST_TITLE, body=TEST_BODY))
    windows = context.runtime.identity().needed
    toast_on = context.settings.notifications.toast
    data = NotifyTestData(
        notification=notification_entry(sent),
        failed=any(
            delivery_failed(d.result, windows=windows, toast_on=toast_on) for d in sent.deliveries
        ),
    )
    code = EXIT_FAILED if data.failed else EXIT_OK
    if json_output:
        output.document(
            NotifyTestDocument(generated_at=context.runtime.now(), disclaimer=NOTICE, data=data)
        )
        raise typer.Exit(code)
    _print_test(output, data)
    raise typer.Exit(code)
