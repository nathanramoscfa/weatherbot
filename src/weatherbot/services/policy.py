# src/weatherbot/services/policy.py
"""The pure notification policy: one location's assessment and changes to its decisions.

Rule: ``weatherbot.services.policy`` imports only ``weatherbot.models`` and the standard
library's ``collections.abc``, ``dataclasses``, ``datetime``, ``typing``, and ``zoneinfo``.
It reads no clock, randomness, filesystem, environment, or logger, and touches no network
or database; ``tests/test_architecture.py`` scans it for each. CI holds its branch coverage
at 90 percent or more.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, tzinfo
from typing import Final, Literal
from zoneinfo import ZoneInfo

from weatherbot.models import RULE_TRIGGERS, AlertLevel, Assessment, ChangeEvent

DECISION_KINDS: Final = (
    "escalation",
    "sent",
    "repeat",
    "quiet_hours",
    "held",
    "withdrawn",
    "informational",
)
"""Every decision the policy can record for a trigger."""

type DecisionKind = Literal[
    "escalation",
    "sent",
    "repeat",
    "quiet_hours",
    "held",
    "withdrawn",
    "informational",
]
type TriggerKind = Literal[
    "level",
    "held",
    "level_changed",
    "advisory_issued",
    "official_added",
    "official_changed",
    "official_removed",
    "cone_entered",
    "cone_left",
]
type UnavailableKey = tuple[str, str | None, str | None, int | None]
"""An unavailable input's identity: ``(kind, source_id, atcf_id, threshold_kt)``."""

type EventKey = (
    tuple[Literal["level"], int, int]
    | tuple[Literal["advisory"], str, str]
    | tuple[Literal["cone"], str]
    | tuple[Literal["official"], Literal["nws_alert"], tuple[str, ...]]
    | tuple[Literal["official"], Literal["watch_warning_segment"], str, tuple[str, ...]]
)
"""A trigger's cooldown key."""

MAX_BODY_LINES: Final = 4
DEFAULT_MAX_HOLDS: Final = 3
QUIET_HOURS_MAX_LEVEL: Final = AlertLevel.TROPICAL_STORM_THREAT
MIDNIGHT_END: Final = "24:00"
HOURS_PER_DAY: Final = 24
MINUTES_PER_HOUR: Final = 60
UTC_ZONE: Final = ZoneInfo("UTC")


@dataclass(frozen=True, slots=True)
class PendingHeld:
    """A held drop waiting for confirmation: the lower level seen and the hold count."""

    level: AlertLevel
    count: int


def _empty_last_sent() -> dict[EventKey | str, datetime]:
    return {}


def parse_wall_time(text: str, *, allow_24: bool = False) -> time | Literal["24:00"]:
    """Parse ``"HH:MM"`` wall-clock text, allowing ``"24:00"`` only when asked.

    Args:
        text: The wall-clock string.
        allow_24: Whether ``"24:00"`` is accepted as midnight at the end of the day.

    Returns:
        A ``datetime.time``, or ``"24:00"`` when ``allow_24`` is true and ``text`` is
        ``"24:00"``.

    Raises:
        ValueError: When ``text`` is not ``"HH:MM"`` in range.
    """
    parts = text.split(":")
    if len(parts) != 2 or any(len(part) != 2 or not part.isdigit() for part in parts):  # noqa: PLR2004
        message = "wall-clock time must be HH:MM"
        raise ValueError(message)
    hour, minute = int(parts[0]), int(parts[1])
    if allow_24 and hour == HOURS_PER_DAY and minute == 0:
        return MIDNIGHT_END
    if not (0 <= hour < HOURS_PER_DAY and 0 <= minute < MINUTES_PER_HOUR):
        message = "wall-clock time is out of range"
        raise ValueError(message)
    return time(hour, minute)


def format_wall_time(value: time | Literal["24:00"]) -> str:
    """Format a wall-clock time as ``"HH:MM"``."""
    if value == MIDNIGHT_END:
        return MIDNIGHT_END
    return f"{value.hour:02d}:{value.minute:02d}"


@dataclass(frozen=True, slots=True)
class QuietHours:
    """A quiet-hours window in a time zone.

    A ``start`` after ``end`` spans midnight; a ``start`` of ``00:00`` with an ``end`` of
    ``"24:00"`` covers the whole day; a ``start`` equal to ``end`` is refused.
    """

    start: time
    end: time | Literal["24:00"]
    time_zone: tzinfo = UTC_ZONE

    def __post_init__(self) -> None:
        """Refuse a quiet-hours window whose start and end are identical."""
        if isinstance(self.end, time) and self.start == self.end:
            message = "quiet_hours start and end must not be equal"
            raise ValueError(message)

    @classmethod
    def parse(cls, start: str, end: str, time_zone: tzinfo) -> "QuietHours":
        """Build ``QuietHours`` from ``"HH:MM"`` strings (``end`` up to ``"24:00"``)."""
        parsed_start = parse_wall_time(start, allow_24=False)
        if parsed_start == MIDNIGHT_END:  # pragma: no cover - allow_24=False never returns it
            message = "quiet_hours start must be 00:00 to 23:59"
            raise ValueError(message)
        parsed_end = parse_wall_time(end, allow_24=True)
        return cls(start=parsed_start, end=parsed_end, time_zone=time_zone)

    def contains(self, instant: datetime) -> bool:
        """Whether ``instant`` falls inside the quiet-hours window in ``self.time_zone``."""
        local = instant.astimezone(self.time_zone).timetz().replace(tzinfo=None)
        if self.end == MIDNIGHT_END:
            return local >= self.start
        if self.start < self.end:
            return self.start <= local < self.end
        return local >= self.start or local < self.end


@dataclass(frozen=True, slots=True)
class PolicySettings:
    """The policy's settings for one cycle."""

    cooldown: timedelta = timedelta(hours=6)
    quiet_hours: QuietHours | None = None
    confirm_after: timedelta = timedelta(minutes=5)
    max_holds: int = DEFAULT_MAX_HOLDS


@dataclass(frozen=True, slots=True)
class PolicyState:
    """A location's notification state before an assessment is decided."""

    announced_level: AlertLevel | None = None
    announced_unavailable: frozenset[UnavailableKey] = frozenset()
    announced_expiries: tuple[datetime, ...] = ()
    pending_held: PendingHeld | None = None
    last_sent: Mapping[EventKey | str, datetime] = field(default_factory=_empty_last_sent)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """One trigger's decision on an assessment."""

    trigger: TriggerKind
    position: int
    decision: DecisionKind
    event_key: str | None
    level_after: AlertLevel | None
    reason: str
    key: EventKey | None = None


@dataclass(frozen=True, slots=True)
class NotificationDraft:
    """The notification a cycle sends for a location."""

    location_name: str
    level: AlertLevel
    escalation: bool
    title: str
    body: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Decided:
    """What ``decide`` returns for one location's assessment."""

    decisions: tuple[PolicyDecision, ...]
    state: PolicyState
    notification: NotificationDraft | None
    confirm_at: datetime | None


@dataclass(frozen=True, slots=True)
class _CycleContext:
    state: PolicyState
    settings: PolicySettings
    now: datetime
    level: AlertLevel
    escalation_cycle: bool


@dataclass(frozen=True, slots=True)
class _LevelOutcome:
    decisions: tuple[PolicyDecision, ...]
    announced: AlertLevel
    unavailable: frozenset[UnavailableKey]
    expiries: tuple[datetime, ...]
    pending_held: PendingHeld | None
    confirm_at: datetime | None
    escalation_cycle: bool
    level_sent: bool
    incomplete_drop: bool
    sent_drop_key: EventKey | None


def unavailable_keys(assessment: Assessment) -> frozenset[UnavailableKey]:
    """Return the identities of the inputs ``assessment`` lacked."""
    return frozenset(
        (item.kind, item.source_id, item.atcf_id, item.threshold_kt)
        for item in assessment.unavailable
    )


def official_expiries(assessment: Assessment) -> tuple[datetime, ...]:
    """Return the expiry instants of the official products that covered the location."""
    return tuple(
        product.expires_at
        for product in assessment.official
        if product.covers and product.expires_at is not None
    )


def format_event_key(key: EventKey) -> str:
    """Format an ``EventKey`` tuple as a stable string for storage and JSON."""
    if key[0] == "level":
        return f"level:{int(key[1])}:{int(key[2])}"
    if key[0] == "advisory":
        return f"advisory:{key[1]}:{key[2]}"
    if key[0] == "cone":
        return f"cone:{key[1]}"
    if key[1] == "nws_alert":
        return f"official:nws_alert:{','.join(key[2])}"
    return f"official:watch_warning_segment:{key[2]}:{','.join(key[3])}"


def parse_event_key(text: str) -> EventKey:
    """Parse a stored ``event_key`` string back into its ``EventKey`` tuple."""
    parts = text.split(":")
    match parts:
        case ["level", previous, current]:
            return ("level", AlertLevel(int(previous)), AlertLevel(int(current)))
        case ["advisory", atcf_id, advisory]:
            return ("advisory", atcf_id, advisory)
        case ["cone", atcf_id]:
            return ("cone", atcf_id)
        case ["official", "nws_alert", codes]:
            return ("official", "nws_alert", tuple(codes.split(",")) if codes else ())
        case ["official", "watch_warning_segment", atcf_id, codes]:
            return (
                "official",
                "watch_warning_segment",
                atcf_id,
                tuple(codes.split(",")) if codes else (),
            )
        case _:
            message = f"unrecognized event key: {text!r}"
            raise ValueError(message)


def _sent_at(last_sent: Mapping[EventKey | str, datetime], key: EventKey) -> datetime | None:
    found = last_sent.get(key)
    if found is not None:
        return found
    return last_sent.get(format_event_key(key))


def _in_cooldown(
    last_sent: Mapping[EventKey | str, datetime],
    key: EventKey,
    now: datetime,
    cooldown: timedelta,
) -> bool:
    previous = _sent_at(last_sent, key)
    if previous is None or cooldown <= timedelta(0):
        return False
    return (now - previous) < cooldown


def _in_quiet_hours(level: AlertLevel, now: datetime, quiet_hours: QuietHours | None) -> bool:
    return quiet_hours is not None and level <= QUIET_HOURS_MAX_LEVEL and quiet_hours.contains(now)


def _decide_keyed(key: EventKey, ctx: _CycleContext, sent_reason: str) -> tuple[DecisionKind, str]:
    if _in_cooldown(ctx.state.last_sent, key, ctx.now, ctx.settings.cooldown):
        return "repeat", "sent within the cooldown window"
    if not ctx.escalation_cycle and _in_quiet_hours(ctx.level, ctx.now, ctx.settings.quiet_hours):
        return "quiet_hours", f"level {int(ctx.level)} falls in quiet hours"
    return "sent", sent_reason


def _event_key(event: ChangeEvent) -> EventKey | None:
    if event.kind == "advisory_issued" and event.in_cone is True:
        return ("advisory", str(event.atcf_id), str(event.advisory))
    if event.kind == "cone_entered":
        return ("cone", str(event.atcf_id))
    if event.kind in ("official_added", "official_changed"):
        if event.product == "nws_alert":
            return ("official", "nws_alert", event.codes)
        return ("official", "watch_warning_segment", str(event.atcf_id), event.codes)
    return None


def _level_line(
    previous_announced: AlertLevel | None,
    assessment: Assessment,
    *,
    incomplete_drop: bool,
) -> str:
    level = int(assessment.level)
    trigger = RULE_TRIGGERS[assessment.rule]
    if previous_announced is None:
        return f"Level {level}: {trigger}"
    if assessment.level > previous_announced:
        return f"Level rose to {level}: {trigger}"
    if incomplete_drop:
        return f"Level fell to at least {level}."
    return f"Level fell to {level}."


def _decide_drop(
    state: PolicyState,
    assessment: Assessment,
    changes: Sequence[ChangeEvent],
    settings: PolicySettings,
    now: datetime,
) -> _LevelOutcome:
    announced = state.announced_level or assessment.level
    level = assessment.level
    current_unavailable = unavailable_keys(assessment)
    missing_input = bool(current_unavailable - state.announced_unavailable)
    has_advisory = any(event.kind == "advisory_issued" for event in changes)
    any_expired = any(expiry <= assessment.as_of for expiry in state.announced_expiries)
    level_position = next(
        (index for index, event in enumerate(changes) if event.kind == "level_changed"),
        -1,
    )
    prior_holds = state.pending_held.count if state.pending_held is not None else 0
    hold_for_missing = missing_input and prior_holds < settings.max_holds
    hold_for_unconfirmed = state.pending_held is None and not has_advisory and not any_expired

    if hold_for_missing or hold_for_unconfirmed:
        hold_count = prior_holds + 1
        hold_reason = (
            f"drop from {int(announced)} to {int(level)} held ({hold_count}/"
            f"{settings.max_holds}): missing input"
            if hold_for_missing
            else f"drop from {int(announced)} to {int(level)} held: no new advisory or "
            "expired official product"
        )
        return _LevelOutcome(
            decisions=(
                PolicyDecision(
                    trigger="level",
                    position=level_position,
                    decision="held",
                    event_key=None,
                    level_after=announced,
                    reason=hold_reason,
                ),
            ),
            announced=announced,
            unavailable=state.announced_unavailable,
            expiries=state.announced_expiries,
            pending_held=PendingHeld(level=level, count=hold_count),
            confirm_at=now + settings.confirm_after,
            escalation_cycle=False,
            level_sent=False,
            incomplete_drop=False,
            sent_drop_key=None,
        )

    drop_key: EventKey = ("level", int(announced), int(level))
    ctx = _CycleContext(
        state=state,
        settings=settings,
        now=now,
        level=level,
        escalation_cycle=False,
    )
    sent_reason = (
        f"level fell from {int(announced)} to at least {int(level)} after {prior_holds} holds"
        if missing_input
        else f"level fell from {int(announced)} to {int(level)}"
    )
    drop_decision, drop_reason = _decide_keyed(drop_key, ctx, sent_reason)
    level_sent = drop_decision == "sent"
    return _LevelOutcome(
        decisions=(
            PolicyDecision(
                trigger="level",
                position=level_position,
                decision=drop_decision,
                event_key=format_event_key(drop_key),
                level_after=level,
                reason=drop_reason,
                key=drop_key,
            ),
        ),
        announced=level,
        unavailable=current_unavailable,
        expiries=official_expiries(assessment),
        pending_held=None,
        confirm_at=None,
        escalation_cycle=False,
        level_sent=level_sent,
        incomplete_drop=missing_input,
        sent_drop_key=drop_key if level_sent else None,
    )


def _decide_level(
    state: PolicyState,
    assessment: Assessment,
    changes: Sequence[ChangeEvent],
    settings: PolicySettings,
    now: datetime,
) -> _LevelOutcome:
    announced = state.announced_level
    level = assessment.level
    current_unavailable = unavailable_keys(assessment)
    level_position = next(
        (index for index, event in enumerate(changes) if event.kind == "level_changed"),
        -1,
    )

    if announced is None:
        escalated = level >= AlertLevel.TROPICAL_STORM_THREAT
        decision: DecisionKind = "escalation" if escalated else "informational"
        reason = (
            f"initial assessment at level {int(level)}"
            if escalated
            else "initial assessment at level 1 (All Clear)"
        )
        return _LevelOutcome(
            decisions=(
                PolicyDecision(
                    trigger="level",
                    position=level_position,
                    decision=decision,
                    event_key=None,
                    level_after=level,
                    reason=reason,
                ),
            ),
            announced=level,
            unavailable=current_unavailable,
            expiries=official_expiries(assessment),
            pending_held=None,
            confirm_at=None,
            escalation_cycle=escalated,
            level_sent=escalated,
            incomplete_drop=False,
            sent_drop_key=None,
        )

    if level > announced:
        decs: list[PolicyDecision] = []
        if state.pending_held is not None:
            decs.append(
                PolicyDecision(
                    trigger="held",
                    position=-1,
                    decision="withdrawn",
                    event_key=None,
                    level_after=level,
                    reason=f"pending drop withdrawn as level rose above {int(announced)}",
                )
            )
        decs.append(
            PolicyDecision(
                trigger="level",
                position=level_position,
                decision="escalation",
                event_key=None,
                level_after=level,
                reason=f"level rose from {int(announced)} to {int(level)}",
            )
        )
        return _LevelOutcome(
            decisions=tuple(decs),
            announced=level,
            unavailable=current_unavailable,
            expiries=official_expiries(assessment),
            pending_held=None,
            confirm_at=None,
            escalation_cycle=True,
            level_sent=True,
            incomplete_drop=False,
            sent_drop_key=None,
        )

    if level == announced:
        same_decs: tuple[PolicyDecision, ...] = ()
        if state.pending_held is not None:
            same_decs = (
                PolicyDecision(
                    trigger="held",
                    position=-1,
                    decision="withdrawn",
                    event_key=None,
                    level_after=announced,
                    reason=f"pending drop withdrawn at level {int(announced)}",
                ),
            )
        return _LevelOutcome(
            decisions=same_decs,
            announced=announced,
            unavailable=state.announced_unavailable,
            expiries=state.announced_expiries,
            pending_held=None,
            confirm_at=None,
            escalation_cycle=False,
            level_sent=False,
            incomplete_drop=False,
            sent_drop_key=None,
        )

    return _decide_drop(state, assessment, changes, settings, now)


def decide(
    state: PolicyState,
    assessment: Assessment,
    changes: Sequence[ChangeEvent],
    settings: PolicySettings,
    now: datetime,
) -> Decided:
    """Decide one location's assessment and change events without side effects.

    Args:
        state: The location's policy state before this assessment.
        assessment: The current assessment.
        changes: The change events from the previous assessment to ``assessment``.
        settings: Cooldown, quiet-hours, confirmation, and hold-limit settings.
        now: The cycle's decision instant (``assessment.as_of`` in a replay).

    Returns:
        The trigger decisions, the updated ``PolicyState``, the notification when at
        least one trigger was ``escalation`` or ``sent``, and the confirmation instant
        when a drop was held.
    """
    level_out = _decide_level(state, assessment, changes, settings, now)
    decisions: list[PolicyDecision] = list(level_out.decisions)
    sent_keys: dict[EventKey, datetime] = {}
    if level_out.sent_drop_key is not None:
        sent_keys[level_out.sent_drop_key] = now

    body_lines: list[str] = []
    if level_out.level_sent:
        body_lines.append(
            _level_line(
                state.announced_level,
                assessment,
                incomplete_drop=level_out.incomplete_drop,
            )
        )

    # The announced level is the assessment's except while a drop is held, when it stays
    # A: a held drop must not show through another trigger's notification or quiet hours.
    announced = level_out.announced
    ctx = _CycleContext(
        state=state,
        settings=settings,
        now=now,
        level=announced,
        escalation_cycle=level_out.escalation_cycle,
    )
    for index, event in enumerate(changes):
        if event.kind == "level_changed":
            if state.announced_level is not None and assessment.level == state.announced_level:
                decisions.append(
                    PolicyDecision(
                        trigger="level_changed",
                        position=index,
                        decision="informational",
                        event_key=None,
                        level_after=level_out.announced,
                        reason="level returned to the announced level",
                    )
                )
            continue
        key = _event_key(event)
        if key is None:
            decisions.append(
                PolicyDecision(
                    trigger=event.kind,
                    position=index,
                    decision="informational",
                    event_key=None,
                    level_after=level_out.announced,
                    reason=f"{event.kind} is informational",
                )
            )
            continue
        verdict, reason = _decide_keyed(key, ctx, f"{event.kind} notified")
        if verdict == "sent":
            sent_keys[key] = now
            if len(body_lines) < MAX_BODY_LINES:
                body_lines.append(event.detail)
        decisions.append(
            PolicyDecision(
                trigger=event.kind,
                position=index,
                decision=verdict,
                event_key=format_event_key(key),
                level_after=level_out.announced,
                reason=reason,
                key=key,
            )
        )

    merged_last_sent: dict[EventKey | str, datetime] = {
        **state.last_sent,
        **sent_keys,
    }
    notification: NotificationDraft | None = None
    if any(item.decision in ("escalation", "sent") for item in decisions):
        notification = NotificationDraft(
            location_name=assessment.location_name,
            level=announced,
            escalation=level_out.escalation_cycle,
            title=f"{assessment.location_name}: level {int(announced)}, {announced.label}",
            body=tuple(body_lines),
        )

    new_state = PolicyState(
        announced_level=announced,
        announced_unavailable=level_out.unavailable,
        announced_expiries=level_out.expiries,
        pending_held=level_out.pending_held,
        last_sent=merged_last_sent,
    )
    return Decided(
        decisions=tuple(decisions),
        state=new_state,
        notification=notification,
        confirm_at=level_out.confirm_at,
    )
