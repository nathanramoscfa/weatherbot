# tests/services/test_policy.py
"""Unit tests for the pure notification policy in ``weatherbot.services.policy``."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from scenarios import (
    alerts_failed,
    as_hurricane_warning,
    miami_dade,
    rebuilt,
    rip_current,
    scenario,
    with_alerts,
)

from weatherbot.engine import assess, diff
from weatherbot.models import (
    RULE_TRIGGERS,
    AdvisoryNumber,
    AlertLevel,
    Assessment,
    ChangeEvent,
    Thresholds,
)
from weatherbot.services.policy import (
    MAX_BODY_LINES,
    EventKey,
    PendingHeld,
    PolicySettings,
    PolicyState,
    QuietHours,
    decide,
    format_event_key,
    format_wall_time,
    parse_event_key,
    parse_wall_time,
)

THRESHOLDS = Thresholds()
EASTERN = ZoneInfo("America/New_York")


def _assess_scenario(name: str) -> Assessment:
    snap, loc = scenario(name).inputs()
    return assess(snap, loc, THRESHOLDS)


def test_first_decision_at_level_1_is_informational_and_at_level_3_is_an_escalation() -> None:
    clear = _assess_scenario("issue-10-county-statement-is-context")
    first_clear = decide(
        PolicyState(),
        clear,
        diff(None, clear),
        PolicySettings(),
        clear.as_of,
    )
    assert first_clear.notification is None
    assert first_clear.confirm_at is None
    assert first_clear.state.announced_level == AlertLevel.ALL_CLEAR
    assert [d.decision for d in first_clear.decisions] == [
        "informational",
        "informational",
    ]
    assert first_clear.decisions[0].trigger == "level"
    assert first_clear.decisions[0].decision == "informational"

    cone = _assess_scenario("replay-irma-022-miami-dade")
    first_cone = decide(
        PolicyState(),
        cone,
        diff(None, cone),
        PolicySettings(),
        cone.as_of,
    )
    assert first_cone.notification is not None
    assert first_cone.notification.escalation is True
    assert first_cone.notification.level == AlertLevel.WATCH_HURRICANE_THREAT
    assert first_cone.notification.title == (
        f"{cone.location_name}: level 3, Watch / Hurricane Threat"
    )
    assert first_cone.notification.body[0] == f"Level 3: {RULE_TRIGGERS[cone.rule]}"


def test_escalation_from_an_incomplete_assessment_is_sent_at_once() -> None:
    clear = _assess_scenario("recorded-all-clear")
    state = decide(PolicyState(), clear, diff(None, clear)[:1], PolicySettings(), clear.as_of).state

    incomplete_high = rebuilt(
        _assess_scenario("replay-irma-034-miami-dade"),
        as_of=clear.as_of + timedelta(hours=3),
    )
    assert not incomplete_high.complete
    out = decide(
        state,
        incomplete_high,
        diff(clear, incomplete_high),
        PolicySettings(),
        incomplete_high.as_of,
    )
    assert out.notification is not None
    assert out.notification.escalation is True
    assert out.notification.level == AlertLevel.WARNING_WATCH_EVACUATION
    assert out.notification.body[0] == f"Level rose to 4: {RULE_TRIGGERS[incomplete_high.rule]}"


def test_drop_with_a_new_advisory_is_sent_at_once() -> None:
    high = _assess_scenario("replay-irma-036-miami-dade")
    low = _assess_scenario("replay-irma-022-miami-dade")
    later_low = rebuilt(low, as_of=high.as_of + timedelta(hours=3))
    state = decide(PolicyState(), high, diff(None, high), PolicySettings(), high.as_of).state

    out = decide(
        state,
        later_low,
        diff(high, later_low),
        PolicySettings(),
        later_low.as_of,
    )
    level_dec = next(d for d in out.decisions if d.trigger == "level")
    assert level_dec.decision == "sent"
    assert level_dec.event_key == "level:5:3"
    assert out.confirm_at is None
    assert out.notification is not None
    assert out.notification.escalation is False
    assert out.notification.body[0] == "Level fell to 3."


def test_drop_held_by_failed_nws_source_then_withdrawn_or_sent_on_confirmation() -> None:
    loc = miami_dade()
    warn_snap = with_alerts([as_hurricane_warning(rip_current())])
    high = assess(warn_snap, loc, THRESHOLDS)
    t0 = high.as_of
    state0 = decide(PolicyState(), high, diff(None, high), PolicySettings(), t0).state
    assert state0.announced_level == AlertLevel.HURRICANE_WARNING

    # NWS alert sources fail: assessment drops to level 1 with newly unavailable inputs.
    failed_low = rebuilt(
        assess(alerts_failed(), loc, THRESHOLDS),
        as_of=t0 + timedelta(minutes=15),
    )
    held = decide(
        state0,
        failed_low,
        diff(high, failed_low),
        PolicySettings(),
        failed_low.as_of,
    )
    assert held.notification is None
    assert held.confirm_at == failed_low.as_of + timedelta(minutes=5)
    assert held.state.announced_level == AlertLevel.HURRICANE_WARNING
    assert held.state.pending_held == PendingHeld(level=AlertLevel.ALL_CLEAR, count=1)
    assert [d.decision for d in held.decisions if d.trigger == "level"] == ["held"]

    # Branch A: confirmation cycle sees the source back at the old level (level 5) -> withdrawn.
    recovered_high = rebuilt(high, as_of=failed_low.as_of + timedelta(minutes=5))
    withdrawn = decide(
        held.state,
        recovered_high,
        diff(failed_low, recovered_high),
        PolicySettings(),
        recovered_high.as_of,
    )
    assert withdrawn.notification is None
    assert withdrawn.state.pending_held is None
    assert withdrawn.state.announced_level == AlertLevel.HURRICANE_WARNING
    by_trigger = {d.trigger: d.decision for d in withdrawn.decisions}
    assert by_trigger["held"] == "withdrawn"
    assert by_trigger["level_changed"] == "informational"

    # Branch B: confirmation cycle sees the source back and level really dropped to 1 -> sent.
    clear = rebuilt(_assess_scenario("recorded-all-clear"), as_of=recovered_high.as_of)
    confirmed_drop = decide(
        held.state,
        clear,
        diff(failed_low, clear),
        PolicySettings(),
        clear.as_of,
    )
    assert confirmed_drop.state.pending_held is None
    assert confirmed_drop.state.announced_level == AlertLevel.ALL_CLEAR
    assert confirmed_drop.notification is not None
    assert confirmed_drop.notification.body[0] == "Level fell to 1."


def test_drop_held_three_times_while_source_stays_down_then_sent_as_at_least() -> None:
    loc = miami_dade()
    high = assess(with_alerts([as_hurricane_warning(rip_current())]), loc, THRESHOLDS)
    t0 = high.as_of
    state = decide(PolicyState(), high, diff(None, high), PolicySettings(), t0).state
    previous = high

    base_failed = assess(alerts_failed(), loc, THRESHOLDS)
    for hold_num in (1, 2, 3):
        step_assessment = rebuilt(base_failed, as_of=t0 + timedelta(minutes=5 * hold_num))
        out = decide(
            state,
            step_assessment,
            diff(previous, step_assessment),
            PolicySettings(),
            step_assessment.as_of,
        )
        assert out.notification is None
        assert out.state.pending_held == PendingHeld(level=AlertLevel.ALL_CLEAR, count=hold_num)
        state = out.state
        previous = step_assessment

    # Fourth assessment with the source still down settles the drop as "at least".
    fourth = rebuilt(base_failed, as_of=t0 + timedelta(minutes=20))
    settled = decide(state, fourth, diff(previous, fourth), PolicySettings(), fourth.as_of)
    assert settled.state.pending_held is None
    assert settled.state.announced_level == AlertLevel.ALL_CLEAR
    assert settled.notification is not None
    assert settled.notification.body[0] == "Level fell to at least 1."


def test_a_held_drop_never_shows_through_another_triggers_notification() -> None:
    loc = miami_dade()
    high = assess(with_alerts([as_hurricane_warning(rip_current())]), loc, THRESHOLDS)
    state = decide(PolicyState(), high, diff(None, high), PolicySettings(), high.as_of).state
    failed_low = rebuilt(
        assess(alerts_failed(), loc, THRESHOLDS), as_of=high.as_of + timedelta(minutes=15)
    )
    advisory_in_cone = ChangeEvent(
        kind="advisory_issued",
        atcf_id="AL112017",
        storm_name="Irma",
        advisory=AdvisoryNumber.parse("23"),
        in_cone=True,
        detail="NHC issued advisory 23 for Irma, whose cone covers the location.",
    )
    # Quiet hours all day: the advisory is judged at the announced level 5, not the held 1.
    settings = PolicySettings(quiet_hours=QuietHours.parse("00:00", "24:00", EASTERN))

    out = decide(
        state,
        failed_low,
        (*diff(high, failed_low), advisory_in_cone),
        settings,
        failed_low.as_of,
    )

    assert [d.decision for d in out.decisions if d.trigger == "level"] == ["held"]
    assert out.state.announced_level == AlertLevel.HURRICANE_WARNING
    assert out.notification is not None
    assert out.notification.level == AlertLevel.HURRICANE_WARNING
    assert out.notification.title == (
        f"{high.location_name}: level 5, {AlertLevel.HURRICANE_WARNING.label}"
    )
    assert out.notification.body == (advisory_in_cone.detail,)


def test_drop_without_advisory_or_expired_alert_is_held_once_then_sent() -> None:
    # Toggle-driven level 4 has no covering official expiry and no new advisory on toggle-off.
    high = _assess_scenario("evacuation-toggle-on")
    clear = _assess_scenario("recorded-all-clear")
    t0 = high.as_of
    state0 = decide(PolicyState(), high, diff(None, high), PolicySettings(), t0).state

    drop1 = rebuilt(clear, as_of=t0 + timedelta(minutes=10))
    held = decide(state0, drop1, diff(high, drop1), PolicySettings(), drop1.as_of)
    assert held.notification is None
    assert held.state.pending_held == PendingHeld(level=AlertLevel.ALL_CLEAR, count=1)
    assert held.confirm_at == drop1.as_of + timedelta(minutes=5)

    # Next assessment has no new advisory either, but the no-advisory test never holds twice.
    drop2 = rebuilt(clear, as_of=drop1.as_of + timedelta(minutes=5))
    sent = decide(held.state, drop2, diff(drop1, drop2), PolicySettings(), drop2.as_of)
    assert sent.state.pending_held is None
    assert sent.state.announced_level == AlertLevel.ALL_CLEAR
    assert sent.notification is not None
    assert sent.notification.body[0] == "Level fell to 1."


def test_drop_when_a_covering_alert_expired_is_sent_at_once() -> None:
    loc = miami_dade()
    warning = as_hurricane_warning(rip_current())
    high = assess(with_alerts([warning]), loc, THRESHOLDS)
    state0 = decide(PolicyState(), high, diff(None, high), PolicySettings(), high.as_of).state

    # After the alert's expires instant, the drop is confirmed by the expiry without holding.
    after_expiry = rebuilt(
        _assess_scenario("recorded-all-clear"),
        as_of=warning.expires + timedelta(minutes=1),
    )
    out = decide(
        state0,
        after_expiry,
        diff(high, after_expiry),
        PolicySettings(),
        after_expiry.as_of,
    )
    assert out.confirm_at is None
    assert out.state.pending_held is None
    assert out.notification is not None
    assert out.notification.body[0] == "Level fell to 1."


def test_escalation_and_withdrawal_in_one_cycle_are_two_decisions() -> None:
    cone = _assess_scenario("replay-irma-022-miami-dade")
    watch = _assess_scenario("replay-irma-034-miami-dade")
    state_with_held = PolicyState(
        announced_level=AlertLevel.WATCH_HURRICANE_THREAT,
        pending_held=PendingHeld(level=AlertLevel.ALL_CLEAR, count=1),
    )
    out = decide(
        state_with_held,
        watch,
        diff(cone, watch),
        PolicySettings(),
        watch.as_of,
    )
    triggers = [(d.trigger, d.decision) for d in out.decisions[:2]]
    assert triggers == [("held", "withdrawn"), ("level", "escalation")]
    assert out.state.pending_held is None
    assert out.state.announced_level == AlertLevel.WARNING_WATCH_EVACUATION


def test_nws_alert_keeping_codes_is_repeat_and_watch_upgraded_to_warning_is_sent() -> None:
    clear = _assess_scenario("recorded-all-clear")
    t0 = clear.as_of
    state0 = decide(PolicyState(), clear, diff(None, clear)[:1], PolicySettings(), t0).state

    # First official_added for an NWS Tropical Storm Watch.
    added_watch = ChangeEvent(
        kind="official_added",
        product="nws_alert",
        alert_id="urn:oid:2.49.0.1.840.0.1",
        codes=("Tropical Storm Watch",),
        detail="The NWS issued a Tropical Storm Watch that covers the location.",
    )
    step1 = decide(state0, clear, (added_watch,), PolicySettings(), t0 + timedelta(hours=1))
    assert [d.decision for d in step1.decisions] == ["sent"]

    # An update to that NWS alert that keeps the same codes inside the 6-hour cooldown is repeat.
    updated_same = ChangeEvent(
        kind="official_changed",
        product="nws_alert",
        alert_id="urn:oid:2.49.0.1.840.0.2",
        previous_alert_id="urn:oid:2.49.0.1.840.0.1",
        codes=("Tropical Storm Watch",),
        previous_codes=("Tropical Storm Watch",),
        detail="The NWS updated the Tropical Storm Watch that covers the location.",
    )
    step2 = decide(step1.state, clear, (updated_same,), PolicySettings(), t0 + timedelta(hours=2))
    assert [d.decision for d in step2.decisions] == ["repeat"]
    assert step2.notification is None

    # Upgrading the watch to a Tropical Storm Warning changes the codes -> sent!
    upgraded_warning = ChangeEvent(
        kind="official_changed",
        product="nws_alert",
        alert_id="urn:oid:2.49.0.1.840.0.3",
        previous_alert_id="urn:oid:2.49.0.1.840.0.2",
        codes=("Tropical Storm Warning",),
        previous_codes=("Tropical Storm Watch",),
        detail="The NWS replaced the Tropical Storm Watch with a Tropical Storm Warning.",
    )
    step3 = decide(
        step2.state, clear, (upgraded_warning,), PolicySettings(), t0 + timedelta(hours=3)
    )
    assert [d.decision for d in step3.decisions] == ["sent"]
    assert step3.notification is not None


def test_cooldown_suppresses_represented_event_only_inside_its_window() -> None:
    clear = _assess_scenario("recorded-all-clear")
    t0 = clear.as_of
    state0 = decide(PolicyState(), clear, diff(None, clear)[:1], PolicySettings(), t0).state
    cone_event = ChangeEvent(
        kind="cone_entered",
        atcf_id="AL112017",
        storm_name="Irma",
        advisory=AdvisoryNumber.parse("22"),
        detail="The location entered the cone of Irma, advisory 22.",
    )

    first = decide(state0, clear, (cone_event,), PolicySettings(), t0 + timedelta(hours=1))
    assert [d.decision for d in first.decisions] == ["sent"]

    # Inside the 6-hour cooldown (5 hours later) -> repeat.
    inside = decide(first.state, clear, (cone_event,), PolicySettings(), t0 + timedelta(hours=6))
    assert [d.decision for d in inside.decisions] == ["repeat"]
    assert inside.notification is None

    # At or past the 6-hour cooldown (6 hours after t0 + 1h = t0 + 7h) -> sent again.
    after = decide(inside.state, clear, (cone_event,), PolicySettings(), t0 + timedelta(hours=7))
    assert [d.decision for d in after.decisions] == ["sent"]
    assert after.notification is not None

    # With a zero cooldown, even an immediate repeat is sent.
    zero_cd = PolicySettings(cooldown=timedelta(0))
    immediate = decide(after.state, clear, (cone_event,), zero_cd, t0 + timedelta(hours=7))
    assert [d.decision for d in immediate.decisions] == ["sent"]


def test_quiet_hours_across_midnight_and_same_day_hold_back_only_non_escalations_at_1_2() -> None:
    # Quiet hours 22:00 to 07:00 America/New_York (EDT is UTC-4 in September/October).
    quiet = QuietHours.parse("22:00", "07:00", EASTERN)
    settings = PolicySettings(quiet_hours=quiet)
    night_utc = datetime(2026, 10, 12, 3, 30, tzinfo=UTC)  # 23:30 EDT (inside window)
    day_utc = datetime(2026, 10, 12, 16, 0, tzinfo=UTC)  # 12:00 EDT (outside window)
    assert quiet.contains(night_utc) is True
    assert quiet.contains(day_utc) is False

    # Same-day window 09:00 to 17:00 EDT.
    day_quiet = QuietHours.parse("09:00", "17:00", EASTERN)
    assert day_quiet.contains(day_utc) is True
    assert day_quiet.contains(night_utc) is False

    # All-day window 00:00 to 24:00 EDT.
    all_day = QuietHours.parse("00:00", "24:00", EASTERN)
    assert all_day.contains(day_utc) is True
    assert all_day.contains(night_utc) is True

    clear = rebuilt(_assess_scenario("recorded-all-clear"), as_of=night_utc)
    state = PolicyState(announced_level=AlertLevel.ALL_CLEAR)
    advisory_in_cone = ChangeEvent(
        kind="advisory_issued",
        atcf_id="AL112017",
        storm_name="Irma",
        advisory=AdvisoryNumber.parse("22"),
        in_cone=True,
        detail="NHC issued advisory 22 for Irma, whose cone covers the location.",
    )

    # Non-escalation at level 1 during quiet hours -> quiet_hours, no notification.
    suppressed = decide(state, clear, (advisory_in_cone,), settings, night_utc)
    assert [d.decision for d in suppressed.decisions] == ["quiet_hours"]
    assert suppressed.notification is None

    # Non-escalation at level 3 during quiet hours -> sent!
    cone3 = rebuilt(_assess_scenario("replay-irma-022-miami-dade"), as_of=night_utc)
    state3 = PolicyState(announced_level=AlertLevel.WATCH_HURRICANE_THREAT)
    at_level_3 = decide(state3, cone3, (advisory_in_cone,), settings, night_utc)
    assert [d.decision for d in at_level_3.decisions] == ["sent"]
    assert at_level_3.notification is not None

    # Escalation to level 2 during quiet hours -> escalation and accompanying trigger sent!
    level2 = rebuilt(_assess_scenario("recorded-development-region"), as_of=night_utc)
    esc2 = decide(state, level2, (advisory_in_cone,), settings, night_utc)
    assert [d.decision for d in esc2.decisions] == ["escalation", "sent"]
    assert esc2.notification is not None
    assert esc2.notification.escalation is True

    # Drop to level 1 during quiet hours with a new advisory -> quiet_hours (level_sent is False).
    drop_quiet = decide(esc2.state, clear, (advisory_in_cone,), settings, night_utc)
    assert [d.decision for d in drop_quiet.decisions] == ["quiet_hours", "repeat"]
    assert drop_quiet.notification is None
    assert drop_quiet.state.announced_level == AlertLevel.ALL_CLEAR


def test_one_notification_per_location_per_cycle_and_body_capped_at_four_lines() -> None:
    clear = _assess_scenario("recorded-all-clear")
    watch = _assess_scenario("replay-irma-034-miami-dade")
    state = PolicyState(announced_level=AlertLevel.ALL_CLEAR)
    adv34 = AdvisoryNumber.parse("34")
    events = (
        ChangeEvent(
            kind="level_changed",
            previous_level=AlertLevel.ALL_CLEAR,
            level=watch.level,
            direction="up",
            rule=watch.rule,
            detail="Level rose.",
        ),
        ChangeEvent(
            kind="advisory_issued",
            atcf_id="AL112017",
            storm_name="Irma",
            advisory=adv34,
            in_cone=True,
            detail="Line two.",
        ),
        ChangeEvent(
            kind="cone_entered",
            atcf_id="AL112017",
            storm_name="Irma",
            advisory=adv34,
            detail="Line three.",
        ),
        ChangeEvent(
            kind="official_added",
            product="watch_warning_segment",
            atcf_id="AL112017",
            storm_name="Irma",
            advisory=adv34,
            codes=("HWA",),
            detail="Line four.",
        ),
        ChangeEvent(
            kind="official_added",
            product="nws_alert",
            alert_id="alert-1",
            codes=("Hurricane Watch",),
            detail="Line five (dropped by the 4-line cap).",
        ),
        ChangeEvent(
            kind="cone_left",
            atcf_id="AL112017",
            storm_name="Irma",
            advisory=adv34,
            detail="Informational cone_left.",
        ),
    )
    del clear
    out = decide(state, watch, events, PolicySettings(), watch.as_of)
    assert out.notification is not None
    assert len(out.notification.body) == MAX_BODY_LINES
    assert out.notification.body == (
        f"Level rose to 4: {RULE_TRIGGERS[watch.rule]}",
        "Line two.",
        "Line three.",
        "Line four.",
    )


def test_event_key_and_wall_time_formatting_and_validation() -> None:
    keys: list[EventKey] = [
        ("level", AlertLevel(3), AlertLevel(1)),
        ("advisory", "AL112017", "22A"),
        ("cone", "AL112017"),
        ("official", "nws_alert", ("Hurricane Watch", "Tropical Storm Warning")),
        ("official", "watch_warning_segment", "AL112017", ("HWA", "TWR")),
    ]
    for key in keys:
        assert parse_event_key(format_event_key(key)) == key

    # String-keyed last_sent lookup also hits the cooldown.
    now = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
    clear = _assess_scenario("recorded-all-clear")
    state = PolicyState(
        announced_level=AlertLevel.ALL_CLEAR,
        last_sent={"cone:AL112017": now - timedelta(hours=1)},
    )
    cone_ev = ChangeEvent(
        kind="cone_entered",
        atcf_id="AL112017",
        storm_name="Irma",
        advisory=AdvisoryNumber.parse("22"),
        detail="Entered cone.",
    )
    assert decide(state, clear, (cone_ev,), PolicySettings(), now).decisions[0].decision == "repeat"

    assert format_wall_time(time(7, 5)) == "07:05"
    assert format_wall_time("24:00") == "24:00"
    with pytest.raises(ValueError, match="HH:MM"):
        parse_wall_time("7:05")
    with pytest.raises(ValueError, match="out of range"):
        parse_wall_time("24:00", allow_24=False)
    with pytest.raises(ValueError, match="must not be equal"):
        QuietHours(start=time(8, 0), end=time(8, 0))
    with pytest.raises(ValueError, match="unrecognized event key"):
        parse_event_key("unknown:1")
