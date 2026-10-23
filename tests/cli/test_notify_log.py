# tests/cli/test_notify_log.py
"""``weatherbot notify log`` lists stored notifications newest first and validates its schema."""

from cli_support import (
    MIAMI,
    NASSAU,
    add_landmark,
    parse,
    recorded_services,
    run,
)

from weatherbot.cli.documents import NotificationsDocument
from weatherbot.services.disclaimer import NOTICE


def test_notify_log_when_empty_prints_message_and_validates_json() -> None:
    text_result = run(["notify", "log"])
    assert text_result.exit_code == 0, text_result.stderr
    assert "No notifications are stored." in text_result.stdout
    assert text_result.stdout.rstrip().endswith(NOTICE)

    doc = parse(run(["notify", "log", "--json"]), NotificationsDocument)
    assert doc.command == "notify log"
    assert doc.data.limit == 20  # noqa: PLR2004
    assert doc.data.notifications == ()


def test_notify_log_lists_newest_first_with_deliveries_and_decisions_in_json() -> None:
    with recorded_services():
        add_landmark(MIAMI, "miami-dade")
        add_landmark(NASSAU, "nassau")
        run(["locations", "evacuation", NASSAU, "on"])
        run(["check", "--once"])

    text_result = run(["notify", "log", "--limit", "5"])
    assert text_result.exit_code == 0, text_result.stderr
    assert f"{MIAMI}: level 1, All Clear" in text_result.stdout
    assert f"{NASSAU}: level 4, Warning / Watch / Evacuation" in text_result.stdout
    assert "Deliveries: log: delivered, toast: delivered" in text_result.stdout
    assert "EDT" in text_result.stdout or "EST" in text_result.stdout
    assert text_result.stdout.rstrip().endswith(NOTICE)

    doc = parse(run(["notify", "log", "--limit", "5", "--json"]), NotificationsDocument)
    assert doc.data.limit == 5  # noqa: PLR2004
    assert len(doc.data.notifications) == 2  # noqa: PLR2004
    # Newest id first: Nassau was assessed second, so its notification is first.
    first, second = doc.data.notifications
    assert first.id > second.id
    assert first.location == NASSAU
    assert first.created_at_local is None
    assert first.escalation is True
    # Every command delivers through the in-app log and the toast beside it.
    both = [("log", "delivered"), ("toast", "delivered")]
    assert [(d.channel, d.result) for d in first.deliveries] == both
    assert any(d.decision == "escalation" for d in first.decisions)

    assert second.location == MIAMI
    assert second.time_zone == "America/New_York"
    assert second.created_at_local is not None
    assert [(d.channel, d.result) for d in second.deliveries] == both

    limited = parse(run(["notify", "log", "--limit", "1", "--json"]), NotificationsDocument)
    assert len(limited.data.notifications) == 1
    assert limited.data.notifications[0].id == first.id
