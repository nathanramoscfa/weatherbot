# tests/services/test_notification_replay.py
"""Replay invariants and privacy scan across all eight storm-landmark timelines."""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ladder_data import CORPUS, public_landmarks, replay_timelines
from weatherbot.services.notifications import NotificationStep, replay_notifications
from weatherbot.services.policy import (
    EventKey,
    PolicySettings,
    QuietHours,
)
from weatherbot.services.replay import ReplayCorpus

DECIMAL_RE = re.compile(r"\d+\.\d+")
DISTANCE_RE = re.compile(r"\bkm\b", re.IGNORECASE)
BEARING_RE = re.compile(r"\bdeg(?:rees?)?\b", re.IGNORECASE)
COORDINATE_RE = re.compile(r"-?\d{1,3}\.\d+\s*,\s*-?\d{1,3}\.\d+")
CLOCK_TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")
EXPECTED_TOTAL_ESCALATIONS = 29


def _assert_no_held_or_privacy_leak(run_steps: tuple[NotificationStep, ...], landmark: str) -> None:
    for step in run_steps:
        assert step.confirm_at is None
        assert all(d.decision != "held" for d in step.decisions)
        if step.notification is not None:
            for text in (step.notification.title, *step.notification.body):
                assert DECIMAL_RE.search(text) is None, f"{landmark}: {text}"
                assert DISTANCE_RE.search(text) is None, f"{landmark}: {text}"
                assert BEARING_RE.search(text) is None, f"{landmark}: {text}"
                assert COORDINATE_RE.search(text) is None, f"{landmark}: {text}"
                assert CLOCK_TIME_RE.search(text) is None, f"{landmark}: {text}"


def _count_escalations(run_steps: tuple[NotificationStep, ...]) -> int:
    count = 0
    for step in run_steps:
        if any(d.decision == "escalation" for d in step.decisions):
            count += 1
            assert step.notification is not None
            assert step.notification.escalation is True
    return count


def _assert_cooldown(run_steps: tuple[NotificationStep, ...], cooldown: timedelta) -> None:
    last_sent_by_key: dict[EventKey, datetime] = {}
    for step in run_steps:
        for d in step.decisions:
            if d.decision == "sent" and d.key is not None:
                prev = last_sent_by_key.get(d.key)
                if prev is not None:
                    assert (step.issued_at - prev) >= cooldown
                last_sent_by_key[d.key] = step.issued_at


def test_all_eight_replays_satisfy_policy_and_privacy_invariants() -> None:
    landmarks = public_landmarks()
    timelines = replay_timelines()
    assert len(timelines) == len(ReplayCorpus.open(CORPUS).manifest.storms) * len(landmarks)

    total_escalations_defaults = 0
    total_escalations_strict = 0

    for (_, landmark), steps in timelines.items():
        location = landmarks[landmark]
        zone_name = (
            location.nws.time_zone if location.nws is not None and location.nws.time_zone else "UTC"
        )
        strict_settings = PolicySettings(
            cooldown=timedelta(hours=24),
            quiet_hours=QuietHours.parse("00:00", "24:00", ZoneInfo(zone_name)),
        )

        defaults_run = replay_notifications(steps, location=location, settings=PolicySettings())
        strict_run = replay_notifications(steps, location=location, settings=strict_settings)

        _assert_no_held_or_privacy_leak(defaults_run, landmark)
        _assert_no_held_or_privacy_leak(strict_run, landmark)

        # Under defaults, the level decisions coincide with diff's level_changed events.
        for step in defaults_run:
            has_level_decision = any(d.trigger == "level" for d in step.decisions)
            has_level_event = any(e.kind == "level_changed" for e in step.changes)
            assert has_level_decision == has_level_event

        total_escalations_defaults += _count_escalations(defaults_run)
        total_escalations_strict += _count_escalations(strict_run)
        _assert_cooldown(defaults_run, PolicySettings().cooldown)
        _assert_cooldown(strict_run, strict_settings.cooldown)

    assert total_escalations_defaults == EXPECTED_TOTAL_ESCALATIONS
    assert total_escalations_strict == EXPECTED_TOTAL_ESCALATIONS
