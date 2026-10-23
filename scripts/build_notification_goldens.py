# scripts/build_notification_goldens.py
"""Build or check the two frozen Irma notification replay goldens.

First run writes candidates with null approvals to ``tests/golden/notifications/``.
Review the four timelines (``defaults`` and ``strict`` at Miami-Dade and Nassau) and
their counts with ``--review-only``. Only after the operator explicitly approves that
review digest in the session, run ``--approve-date YYYY-MM-DD --review-sha256 SHA``.
An existing approval is retained only when its timelines and metadata are unchanged.
"""

import argparse
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Final, cast
from zoneinfo import ZoneInfo

from ladder_data import (
    CORPUS,
    ROOT,
    digest,
    output_path,
    public_landmarks,
    replay_timelines,
    utc,
)
from weatherbot.models import Location, Thresholds
from weatherbot.services.notifications import NotificationStep, replay_notifications
from weatherbot.services.policy import PolicySettings, QuietHours, format_wall_time
from weatherbot.services.replay import ReplayCorpus, ReplayStep

NOTIFICATION_GOLDENS: Final = ROOT / "tests/golden/notifications"
IRMA_ATCF_ID: Final = "AL112017"


def read_document(path: Path) -> dict[str, object]:
    """Read a golden document, rejecting a non-object JSON value."""
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        message = f"{path.name}: expected a golden object"
        raise TypeError(message)
    return cast("dict[str, object]", value)


def landmark_zone_name(location: Location) -> str:
    """Return the landmark's NWS time-zone name, or ``UTC`` outside NWS coverage."""
    if location.nws is not None and location.nws.time_zone:
        return location.nws.time_zone
    return "UTC"


def strict_policy_settings(location: Location) -> PolicySettings:
    """Build the strict policy settings (24h cooldown, all-day quiet hours in landmark zone)."""
    zone_name = landmark_zone_name(location)
    return PolicySettings(
        cooldown=timedelta(hours=24),
        quiet_hours=QuietHours.parse("00:00", "24:00", ZoneInfo(zone_name)),
    )


def policy_entry(settings: PolicySettings) -> dict[str, object]:
    """Describe the policy settings a timeline ran with."""
    quiet = settings.quiet_hours
    return {
        "cooldown_hours": settings.cooldown / timedelta(hours=1),
        "quiet_hours": (
            None
            if quiet is None
            else {
                "start": format_wall_time(quiet.start),
                "end": format_wall_time(quiet.end),
                "time_zone": str(quiet.time_zone),
            }
        ),
        "confirm_after_minutes": settings.confirm_after // timedelta(minutes=1),
        "max_holds": settings.max_holds,
    }


def step_entries(steps: tuple[NotificationStep, ...]) -> list[dict[str, object]]:
    """Project notification steps with a non-informational decision to golden dicts."""
    rows: list[dict[str, object]] = []
    for step in steps:
        if all(item.decision == "informational" for item in step.decisions):
            continue
        notification: dict[str, object] | None = None
        if step.notification is not None:
            notification = {
                "title": step.notification.title,
                "body": list(step.notification.body),
                "escalation": step.notification.escalation,
            }
        rows.append(
            {
                "advisory": step.advisory,
                "issued_at": utc(step.issued_at),
                "level": int(step.assessment.level),
                "decisions": [
                    {
                        "trigger": item.trigger,
                        "position": item.position,
                        "event_key": item.event_key,
                        "decision": item.decision,
                        "level_after": (
                            int(item.level_after) if item.level_after is not None else None
                        ),
                    }
                    for item in step.decisions
                ],
                "notification": notification,
            }
        )
    return rows


def build_timelines(
    replay_steps: tuple[ReplayStep, ...], location: Location
) -> dict[str, list[dict[str, object]]]:
    """Run ``replay_notifications`` under ``defaults`` and ``strict`` for ``location``."""
    defaults_steps = replay_notifications(
        replay_steps, location=location, settings=PolicySettings()
    )
    strict_steps = replay_notifications(
        replay_steps, location=location, settings=strict_policy_settings(location)
    )
    return {
        "defaults": step_entries(defaults_steps),
        "strict": step_entries(strict_steps),
    }


def candidates() -> dict[str, dict[str, object]]:
    """Build both Irma notification golden candidates from the committed replay corpus."""
    corpus = ReplayCorpus.open(CORPUS)
    thresholds = Thresholds()
    manifest_sha = hashlib.sha256((CORPUS / "corpus-manifest.json").read_bytes()).hexdigest()
    irma = next(storm for storm in corpus.storms() if storm.atcf_id == IRMA_ATCF_ID)
    found: dict[str, dict[str, object]] = {}
    for landmark, location in public_landmarks().items():
        name = f"{irma.atcf_id}-{landmark}.json"
        replay_steps = replay_timelines()[irma.atcf_id, landmark]
        timelines = build_timelines(replay_steps, location)
        found[name] = {
            "_file": f"tests/golden/notifications/{name}",
            "atcf_id": irma.atcf_id,
            "archive_name": irma.name,
            "landmark": landmark,
            "manifest_sha256": manifest_sha,
            "ruleset": thresholds.fingerprint(),
            "policy": {
                "defaults": policy_entry(PolicySettings()),
                "strict": policy_entry(strict_policy_settings(location)),
            },
            "timelines": timelines,
            "approval": None,
        }
    return found


def review_digest(documents: dict[str, dict[str, object]]) -> str:
    """Bind the review to both Irma candidates, including their source and ruleset hashes."""
    return digest(
        {
            name: {key: value for key, value in document.items() if key != "approval"}
            for name, document in documents.items()
        }
    )


def approved(document: dict[str, object]) -> bool:
    """Check both the approval date and its digest of the exact timelines."""
    record = document.get("approval")
    if not isinstance(record, dict):
        return False
    approval = cast("dict[str, object]", record)
    try:
        day = date.fromisoformat(str(approval["date"]))
    except (KeyError, ValueError):
        return False
    return day.isoformat() == approval["date"] and approval.get("timelines_sha256") == digest(
        document["timelines"]
    )


def review(documents: dict[str, dict[str, object]]) -> str:
    """Render the four Irma notification timelines and summary counts as Markdown."""
    lines: list[str] = []
    for document in documents.values():
        timelines = cast("dict[str, list[dict[str, object]]]", document["timelines"])
        for profile in ("defaults", "strict"):
            rows = timelines[profile]
            sent_rows = [row for row in rows if row["notification"] is not None]
            header = (
                f"### {document['archive_name']} ({document['atcf_id']}) — "
                f"{document['landmark']} ({profile}: {len(sent_rows)} notifications, "
                f"{len(rows)} non-informational steps)"
            )
            lines += [
                header,
                "",
                "| Advisory | Issued UTC | Level | Decisions | Notification |",
                "| --- | --- | --- | --- | --- |",
            ]
            for row in rows:
                decs = ", ".join(
                    f"{d['trigger']}={d['decision']}"
                    for d in cast("list[dict[str, object]]", row["decisions"])
                    if d["decision"] != "informational"
                )
                notif = cast("dict[str, object] | None", row["notification"])
                notif_text = "—"
                if notif is not None:
                    body = "; ".join(cast("list[str]", notif["body"]))
                    notif_text = f"{notif['title']} — {body}"
                lines.append(
                    f"| {row['advisory']} | {row['issued_at']} | {row['level']} | "
                    f"{decs} | {notif_text} |"
                )
            lines.append("")
    lines += [f"Review SHA-256: `{review_digest(documents)}`", ""]
    return "\n".join(lines)


def retain_approval(
    candidate: dict[str, object], existing: dict[str, object] | None, day: date | None
) -> dict[str, object]:
    """Retain an unchanged approval or attach a newly authorized one; refuse a silent edit.

    Raises:
        ValueError: A frozen golden changed without a fresh approval.
    """
    updated = dict(candidate)
    if day is not None:
        updated["approval"] = {
            "date": day.isoformat(),
            "timelines_sha256": digest(candidate["timelines"]),
        }
    elif existing is not None and existing.get("approval") is not None:
        same = {k: v for k, v in existing.items() if k != "approval"} == {
            k: v for k, v in candidate.items() if k != "approval"
        }
        if not same or not approved(existing):
            message = "a frozen notification golden requires a new operator approval"
            raise ValueError(message)
        updated["approval"] = existing["approval"]
    return updated


def main(argv: list[str] | None = None) -> int:
    """Build candidates, check frozen files, or record an operator-authorized approval."""
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true")
    action.add_argument("--review-only", action="store_true")
    action.add_argument("--approve-date", type=date.fromisoformat)
    parser.add_argument("--review-sha256")
    args = parser.parse_args(argv)
    if bool(args.approve_date) != bool(args.review_sha256) or (args.check and args.approve_date):
        parser.error("approval needs both --approve-date and --review-sha256; --check never writes")
    documents = candidates()
    if args.approve_date and args.review_sha256 != review_digest(documents):
        parser.error("review digest differs; review the current candidates before approval")
    if args.review_only:
        print(review(documents))
        return 0
    expected_names = set(documents)
    existing_names: set[str] = (
        {path.name for path in NOTIFICATION_GOLDENS.glob("*.json")}
        if NOTIFICATION_GOLDENS.is_dir()
        else set()
    )
    failures = sorted(existing_names - expected_names)
    for name, candidate in documents.items():
        path = output_path(NOTIFICATION_GOLDENS / name, NOTIFICATION_GOLDENS)
        existing = read_document(path) if path.is_file() else None
        same = existing is not None and {k: v for k, v in existing.items() if k != "approval"} == {
            k: v for k, v in candidate.items() if k != "approval"
        }
        if args.check:
            if not same or existing is None or not approved(existing):
                failures.append(name)
            continue
        try:
            updated = retain_approval(candidate, existing, args.approve_date)
        except ValueError:
            failures.append(name)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8", newline="\n")
    for name in failures:
        print(f"STALE or unapproved: tests/golden/notifications/{name}")
    if failures:
        return 1
    action_label = (
        "approved notification goldens checked" if args.check else "notification goldens written"
    )
    print(f"OK {len(documents)} {action_label}")
    print(f"Review SHA-256: {review_digest(documents)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
