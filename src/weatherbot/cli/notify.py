# src/weatherbot/cli/notify.py
"""``weatherbot notify log``: the notification log and each delivery's outcome.

Lists the stored notifications newest first, each with its time in UTC and in the
location's time zone when known, its location, its title and body, and every channel
delivery's result. With ``--json`` it prints a ``notifications`` document that also holds
the decisions of the cycle that sent each notification.
"""

from collections.abc import Sequence
from typing import Annotated, Final

import typer

from weatherbot.cli.documents import (
    NotificationDecisionEntry,
    NotificationDeliveryEntry,
    NotificationEntry,
    NotificationsData,
    NotificationsDocument,
)
from weatherbot.cli.runtime import EXIT_OK, Output, context_of, open_session
from weatherbot.cli.snapshots import JsonOption, named_zone, when
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.notifications import NotificationService, StoredNotification

DEFAULT_LIMIT: Final = 20

app = typer.Typer(
    name="notify",
    help="Inspect the notification log.",
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
