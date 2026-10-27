# src/weatherbot/services/notifications.py
"""Notification service: runs the pure policy per cycle, logs decisions, and delivers.

``NotificationService.decide_cycle`` reconstructs each location's ``PolicyState`` from the
stored assessments and decisions, runs ``weatherbot.services.policy.decide`` once for each
newly created assessment, stores the decisions and any notification in a ``BEGIN IMMEDIATE``
transaction, and delivers each notification through the configured channels: ``LogChannel``
alone by default, and the toast beside it when the caller passes one
(``weatherbot.services.toast``). An assessment that was already decided is never decided
again. ``send`` stores and delivers a notification that belongs to no location, such as
``weatherbot notify test``'s.

``replay_notifications`` runs the same ``decide`` in memory over a historical replay
timeline, with ``now`` set to each advisory's ``as_of``, storing nothing.

Log records here name locations, triggers, decisions, and channel results, never the title
or body of a notification above DEBUG.
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Literal, Protocol, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from weatherbot.models import AlertLevel, Assessment, ChangeEvent, Location
from weatherbot.services.assessments import AssessedLocation
from weatherbot.services.config import Settings
from weatherbot.services.persistence.codec import validated
from weatherbot.services.persistence.database import (
    DatabaseError,
    MigrationFailedError,
    UnknownRevisionError,
    writing_session,
)
from weatherbot.services.persistence.tables import (
    AssessmentRow,
    LocationRow,
    NotificationDecisionRow,
    NotificationDeliveryRow,
    NotificationRow,
)
from weatherbot.services.policy import (
    DecisionKind,
    EventKey,
    NotificationDraft,
    PendingHeld,
    PolicyDecision,
    PolicySettings,
    PolicyState,
    TriggerKind,
    UnavailableKey,
    decide,
    official_expiries,
    parse_event_key,
    unavailable_keys,
)
from weatherbot.services.replay import ReplayStep

LOGGER: Final = logging.getLogger("weatherbot.services.notifications")

NOTIFICATION_KINDS: Final = ("location", "degraded", "recovered", "stale_monitor", "test")
type NotificationKind = Literal["location", "degraded", "recovered", "stale_monitor", "test"]

CHANNEL_NAMES: Final = ("log", "toast", "browser")
type ChannelName = Literal["log", "toast", "browser"]

DELIVERY_RESULTS: Final = ("delivered", "failed", "disabled", "unavailable")
type DeliveryResult = Literal["delivered", "failed", "disabled", "unavailable"]

TEST_TITLE: Final = "Weatherbot test notification"
TEST_BODY: Final = ("If you can read this, toasts work.",)
"""``weatherbot notify test``'s notification: it says it is a test and names no location."""


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Delivery:
    """What a channel's ``deliver`` attempt returns."""

    result: DeliveryResult
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class StoredDelivery:
    """A channel delivery attempt as stored in ``notification_deliveries``."""

    id: int
    channel: str
    attempted_at: datetime
    result: DeliveryResult
    detail: str | None


@dataclass(frozen=True, slots=True)
class StoredDecision:
    """A trigger's policy decision as stored in ``notification_decisions``."""

    id: int
    location_name: str
    assessment_id: int
    change_position: int
    trigger: TriggerKind
    event_key: str | None
    decision: DecisionKind
    level_after: AlertLevel | None
    notification_id: int | None
    decided_at: datetime
    reason: str = ""


@dataclass(frozen=True, slots=True)
class StoredNotification:
    """A notification stored in ``notifications``, with its deliveries and decisions."""

    id: int
    location_name: str | None
    location_time_zone: str | None
    assessment_id: int | None
    cycle_id: int | None
    kind: NotificationKind
    level: AlertLevel | None
    escalation: bool
    title: str
    body: tuple[str, ...]
    created_at: datetime
    deliveries: tuple[StoredDelivery, ...] = ()
    decisions: tuple[StoredDecision, ...] = ()


class Channel(Protocol):
    """A notification delivery channel."""

    @property
    def name(self) -> str:
        """The channel's identifier (``log``, ``toast``, ``browser``, ...)."""
        ...

    @property
    def interrupts(self) -> bool:
        """Whether delivering through this channel interrupts the operator."""
        ...

    async def deliver(self, notification: StoredNotification) -> Delivery:
        """Deliver ``notification`` and return the outcome."""
        ...


class LogChannel:
    """The in-app log channel: storing the notification in SQLite is its delivery."""

    @property
    def name(self) -> str:
        """The channel's identifier."""
        return "log"

    @property
    def interrupts(self) -> bool:
        """The in-app log never interrupts the operator."""
        return False

    async def deliver(self, notification: StoredNotification) -> Delivery:
        """Record that the notification is in the local log."""
        del notification
        return Delivery(result="delivered")


def _reason_for(trigger: str, decision: str, level_after: int | None) -> str:
    reasons: dict[str, str] = {
        "escalation": (
            f"escalated to level {level_after}" if level_after is not None else "escalation"
        ),
        "sent": (
            f"level fell to {level_after}"
            if trigger == "level" and level_after is not None
            else f"{trigger} notified"
        ),
        "repeat": "sent within the cooldown window",
        "quiet_hours": f"level {level_after} falls in quiet hours",
        "held": "drop held for confirmation",
        "withdrawn": f"pending drop withdrawn at level {level_after}",
    }
    return reasons.get(decision, f"{trigger} is informational")


def _load_state(session: Session, location_id: int) -> PolicyState:
    rows = session.scalars(
        select(NotificationDecisionRow)
        .where(NotificationDecisionRow.location_id == location_id)
        .order_by(NotificationDecisionRow.id.asc())
    ).all()
    if not rows:
        return PolicyState()

    announced_level: AlertLevel | None = None
    announcing_assessment_id: int | None = None
    pending_held: PendingHeld | None = None
    last_sent: dict[EventKey | str, datetime] = {}

    for row in rows:
        if row.level_after is not None:
            announced_level = AlertLevel(row.level_after)
        if row.trigger == "level" and row.decision != "held":
            announcing_assessment_id = row.assessment_id
            pending_held = None
        elif row.trigger == "held" and row.decision == "withdrawn":
            pending_held = None
        elif row.trigger == "level" and row.decision == "held":
            held_level_int = session.scalar(
                select(AssessmentRow.level).where(AssessmentRow.id == row.assessment_id)
            )
            held_level = AlertLevel(held_level_int) if held_level_int is not None else AlertLevel(1)
            prior_count = pending_held.count if pending_held is not None else 0
            pending_held = PendingHeld(level=held_level, count=prior_count + 1)

        if row.decision == "sent" and row.event_key is not None:
            last_sent[parse_event_key(row.event_key)] = row.decided_at

    announced_unavailable: frozenset[UnavailableKey] = frozenset()
    announced_expiries: tuple[datetime, ...] = ()
    if announcing_assessment_id is not None:
        raw = session.scalar(
            select(AssessmentRow.assessment).where(AssessmentRow.id == announcing_assessment_id)
        )
        if raw is not None:
            announcing = validated(Assessment, raw)
            announced_unavailable = unavailable_keys(announcing)
            announced_expiries = official_expiries(announcing)

    return PolicyState(
        announced_level=announced_level,
        announced_unavailable=announced_unavailable,
        announced_expiries=announced_expiries,
        pending_held=pending_held,
        last_sent=last_sent,
    )


def _store_location_decisions(  # noqa: PLR0913 - database session and cycle context
    session: Session,
    item: AssessedLocation,
    *,
    cycle_id: int | None,
    policy_settings: PolicySettings,
    now: datetime,
    confirm_times: list[datetime],
) -> tuple[StoredNotification, tuple[StoredDecision, ...]] | None:
    if not item.created:
        return None
    already = session.scalar(
        select(NotificationDecisionRow.id)
        .where(NotificationDecisionRow.assessment_id == item.stored.id)
        .limit(1)
    )
    if already is not None:
        return None
    location_row = session.scalar(select(LocationRow).where(LocationRow.name == item.location.name))
    if location_row is None:  # pragma: no cover - AssessmentService requires it
        return None

    state = _load_state(session, location_row.id)
    decided = decide(
        state,
        item.stored.assessment,
        item.stored.changes,
        policy_settings,
        now,
    )
    if decided.confirm_at is not None:
        confirm_times.append(decided.confirm_at)

    notification_row: NotificationRow | None = None
    if decided.notification is not None:
        draft = decided.notification
        notification_row = NotificationRow(
            location_id=location_row.id,
            assessment_id=item.stored.id,
            cycle_id=cycle_id,
            kind="location",
            level=int(draft.level),
            escalation=draft.escalation,
            title=draft.title,
            body=list(draft.body),
            created_at=now,
        )
        session.add(notification_row)
        session.flush()

    stored_decisions: list[StoredDecision] = []
    for d in decided.decisions:
        row = NotificationDecisionRow(
            location_id=location_row.id,
            assessment_id=item.stored.id,
            change_position=d.position,
            trigger=d.trigger,
            event_key=d.event_key,
            decision=d.decision,
            level_after=int(d.level_after) if d.level_after is not None else None,
            notification_id=notification_row.id if notification_row is not None else None,
            decided_at=now,
        )
        session.add(row)
        session.flush()
        LOGGER.info(
            "notification decision: location=%s trigger=%s decision=%s",
            item.location.name,
            d.trigger,
            d.decision,
        )
        stored_decisions.append(
            StoredDecision(
                id=row.id,
                location_name=item.location.name,
                assessment_id=item.stored.id,
                change_position=d.position,
                trigger=d.trigger,
                event_key=d.event_key,
                decision=d.decision,
                level_after=d.level_after,
                notification_id=row.notification_id,
                decided_at=now,
                reason=d.reason,
            )
        )

    if notification_row is None or decided.notification is None:
        return None
    return (
        StoredNotification(
            id=notification_row.id,
            location_name=item.location.name,
            location_time_zone=item.location.nws.time_zone if item.location.nws else None,
            assessment_id=item.stored.id,
            cycle_id=cycle_id,
            kind="location",
            level=decided.notification.level,
            escalation=decided.notification.escalation,
            title=decided.notification.title,
            body=decided.notification.body,
            created_at=now,
        ),
        tuple(stored_decisions),
    )


class NotificationService:
    """Decides each newly stored assessment once, stores the log, and runs the channels."""

    def __init__(
        self,
        engine: Engine,
        *,
        settings: Settings | None = None,
        now: Callable[[], datetime] = _now,
        channels: Sequence[Channel] | None = None,
    ) -> None:
        """Create the notification service on an open database.

        Args:
            engine: The SQLite database engine.
            settings: Effective application settings.
            now: Clock returning the current UTC instant.
            channels: Delivery channels to run; defaults to ``LogChannel`` only.
        """
        self._engine = engine
        self._settings = settings or Settings()
        self._now = now
        default_channels: tuple[Channel, ...] = (LogChannel(),)
        self._channels: tuple[Channel, ...] = (
            tuple(channels) if channels is not None else default_channels
        )
        self.confirm_at: datetime | None = None

    async def _deliver_one(
        self,
        notification: StoredNotification,
        decisions: tuple[StoredDecision, ...],
        *,
        include_toast: bool = True,
    ) -> StoredNotification:
        """Deliver one stored notification through channels and persist delivery rows.

        When ``include_toast`` is ``False``, only channels that do not interrupt
        (``not channel.interrupts``) are called, holding back both the desktop toast
        and browser notifications during quiet hours.
        """
        active_channels = (
            self._channels
            if include_toast
            else tuple(c for c in self._channels if not c.interrupts)
        )
        channel_outcomes: list[tuple[str, datetime, Delivery]] = []
        for channel in active_channels:
            attempted_at = self._now()
            outcome = await channel.deliver(notification)
            channel_outcomes.append((channel.name, attempted_at, outcome))
            LOGGER.info(
                "notification delivery: id=%d channel=%s result=%s",
                notification.id,
                channel.name,
                outcome.result,
            )

        deliveries: list[StoredDelivery] = []
        with writing_session(self._engine) as session:
            for channel_name, attempted_at, outcome in channel_outcomes:
                delivery_row = NotificationDeliveryRow(
                    notification_id=notification.id,
                    channel=channel_name,
                    attempted_at=attempted_at,
                    result=outcome.result,
                    detail=outcome.detail,
                )
                session.add(delivery_row)
                session.flush()
                deliveries.append(
                    StoredDelivery(
                        id=delivery_row.id,
                        channel=channel_name,
                        attempted_at=attempted_at,
                        result=outcome.result,
                        detail=outcome.detail,
                    )
                )

        return StoredNotification(
            id=notification.id,
            location_name=notification.location_name,
            location_time_zone=notification.location_time_zone,
            assessment_id=notification.assessment_id,
            cycle_id=notification.cycle_id,
            kind=notification.kind,
            level=notification.level,
            escalation=notification.escalation,
            title=notification.title,
            body=notification.body,
            created_at=notification.created_at,
            deliveries=tuple(deliveries),
            decisions=decisions,
        )

    async def decide_cycle(
        self,
        cycle_id: int | None,
        assessed: Sequence[AssessedLocation],
    ) -> tuple[StoredNotification, ...]:
        """Decide every newly created assessment in ``assessed`` and deliver notifications.

        Args:
            cycle_id: The monitor cycle's id, or ``None``.
            assessed: The cycle's assessed locations.

        Returns:
            The notifications sent during this cycle, in location order. ``self.confirm_at``
            holds the earliest confirmation instant requested by a held drop, or ``None``.
        """
        now = self._now()
        # "local" quiet hours take the machine's offset at this cycle's instant, so a
        # long-running monitor follows a daylight-time change.
        policy_settings = self._settings.policy_settings(local_zone=now.astimezone().tzinfo)
        pending_deliveries: list[tuple[StoredNotification, tuple[StoredDecision, ...]]] = []
        confirm_times: list[datetime] = []

        with writing_session(self._engine) as session:
            for item in assessed:
                stored = _store_location_decisions(
                    session,
                    item,
                    cycle_id=cycle_id,
                    policy_settings=policy_settings,
                    now=now,
                    confirm_times=confirm_times,
                )
                if stored is not None:
                    pending_deliveries.append(stored)

        self.confirm_at = min(confirm_times) if confirm_times else None
        if not pending_deliveries:
            return ()

        return tuple(
            [
                await self._deliver_one(notification, decisions)
                for notification, decisions in pending_deliveries
            ]
        )

    async def send(
        self,
        kind: NotificationKind,
        *,
        title: str,
        body: Sequence[str],
        cycle_id: int | None = None,
        include_toast: bool = True,
    ) -> StoredNotification:
        """Store a notification that belongs to no location, then deliver it.

        Args:
            kind: What it is about, such as ``test``, ``degraded``, or ``recovered``.
            title: Its title.
            body: Its lines, which name and never locate.
            cycle_id: Optional monitor cycle id that triggered it.
            include_toast: When ``False``, delivers only to channels that do not interrupt
                (``LogChannel``), holding interrupting channels (toast and browser) back
                during quiet hours or when a recovery had no degraded toast.

        Returns:
            The stored notification with one delivery per active channel.
        """
        now = self._now()
        with writing_session(self._engine) as session:
            row = NotificationRow(
                cycle_id=cycle_id,
                kind=kind,
                escalation=False,
                title=title,
                body=list(body),
                created_at=now,
            )
            session.add(row)
            session.flush()
            notification = StoredNotification(
                id=row.id,
                location_name=None,
                location_time_zone=None,
                assessment_id=None,
                cycle_id=cycle_id,
                kind=kind,
                level=None,
                escalation=False,
                title=title,
                body=tuple(body),
                created_at=now,
            )
        LOGGER.info("notification stored: id=%d kind=%s", notification.id, kind)
        return await self._deliver_one(notification, (), include_toast=include_toast)

    def latest_delivery(self, channel: ChannelName) -> StoredDelivery | None:
        """Return the newest stored delivery through ``channel``, if any.

        Args:
            channel: The channel's name.

        Returns:
            The delivery, or ``None`` when nothing was ever sent through the channel.
        """
        with Session(self._engine) as session:
            row = session.scalars(
                select(NotificationDeliveryRow)
                .where(NotificationDeliveryRow.channel == channel)
                .order_by(
                    NotificationDeliveryRow.attempted_at.desc(), NotificationDeliveryRow.id.desc()
                )
                .limit(1)
            ).first()
            if row is None:
                return None
            return StoredDelivery(
                id=row.id,
                channel=row.channel,
                attempted_at=row.attempted_at,
                result=cast("DeliveryResult", row.result),
                detail=row.detail,
            )

    def delivered_before(self, channel: ChannelName) -> bool:
        """Say whether any notification was ever delivered through ``channel``.

        Args:
            channel: The channel's name.

        Returns:
            Whether a stored delivery through it reads ``delivered``.
        """
        with Session(self._engine) as session:
            found = session.scalar(
                select(NotificationDeliveryRow.id)
                .where(
                    NotificationDeliveryRow.channel == channel,
                    NotificationDeliveryRow.result == "delivered",
                )
                .limit(1)
            )
        return found is not None

    def recent(self, limit: int = 20) -> tuple[StoredNotification, ...]:
        """Return up to ``limit`` stored notifications, newest first.

        Args:
            limit: Maximum number of notifications to return (at least 1).

        Returns:
            The notifications, with their deliveries and decisions.

        Raises:
            ValueError: When ``limit`` is less than 1.
        """
        if limit < 1:
            message = "limit must be at least 1"
            raise ValueError(message)
        with Session(self._engine) as session:
            rows = session.scalars(
                select(NotificationRow)
                .order_by(NotificationRow.created_at.desc(), NotificationRow.id.desc())
                .limit(limit)
            ).all()
            results: list[StoredNotification] = []
            for row in rows:
                location_name: str | None = None
                location_zone: str | None = None
                if row.location_id is not None:
                    loc = session.get(LocationRow, row.location_id)
                    if loc is not None:
                        location_name = loc.name
                        location_zone = loc.nws_time_zone
                delivery_rows = session.scalars(
                    select(NotificationDeliveryRow)
                    .where(NotificationDeliveryRow.notification_id == row.id)
                    .order_by(NotificationDeliveryRow.id.asc())
                ).all()
                decision_rows = session.scalars(
                    select(NotificationDecisionRow)
                    .where(NotificationDecisionRow.notification_id == row.id)
                    .order_by(NotificationDecisionRow.id.asc())
                ).all()
                results.append(
                    StoredNotification(
                        id=row.id,
                        location_name=location_name,
                        location_time_zone=location_zone,
                        assessment_id=row.assessment_id,
                        cycle_id=row.cycle_id,
                        kind=cast("NotificationKind", row.kind),
                        level=AlertLevel(row.level) if row.level is not None else None,
                        escalation=row.escalation,
                        title=row.title,
                        body=tuple(str(line) for line in row.body),
                        created_at=row.created_at,
                        deliveries=tuple(
                            StoredDelivery(
                                id=d.id,
                                channel=d.channel,
                                attempted_at=d.attempted_at,
                                result=cast("DeliveryResult", d.result),
                                detail=d.detail,
                            )
                            for d in delivery_rows
                        ),
                        decisions=tuple(
                            StoredDecision(
                                id=dec.id,
                                location_name=location_name or "",
                                assessment_id=dec.assessment_id,
                                change_position=dec.change_position,
                                trigger=cast("TriggerKind", dec.trigger),
                                event_key=dec.event_key,
                                decision=cast("DecisionKind", dec.decision),
                                level_after=(
                                    AlertLevel(dec.level_after)
                                    if dec.level_after is not None
                                    else None
                                ),
                                notification_id=dec.notification_id,
                                decided_at=dec.decided_at,
                                reason=_reason_for(dec.trigger, dec.decision, dec.level_after),
                            )
                            for dec in decision_rows
                        ),
                    )
                )
            return tuple(results)


def database_error_kind(error: DatabaseError) -> str:
    """Return the short kind label for a ``DatabaseError``."""
    if isinstance(error, UnknownRevisionError):
        return "unknown_revision"
    if isinstance(error, MigrationFailedError):
        return "migration_failed"
    return "database_error"


async def deliver_database_refused_toast(
    toast: Channel,
    error: DatabaseError,
    *,
    now: datetime | None = None,
) -> Delivery:
    """Deliver one database-free toast when ``open_database`` fails at monitor start.

    Args:
        toast: The toast channel (``Runtime.make_toast(settings)``).
        error: The ``DatabaseError`` raised by ``open_database``.
        now: The current UTC instant; defaults to ``datetime.now(UTC)``.

    Returns:
        The channel's ``Delivery`` outcome.
    """
    instant = now if now is not None else _now()
    kind = database_error_kind(error)
    title = f"Weatherbot cannot open its database: {kind}; reinstall or restore it."
    notification = StoredNotification(
        id=0,
        location_name=None,
        location_time_zone=None,
        assessment_id=None,
        cycle_id=None,
        kind="degraded",
        level=None,
        escalation=False,
        title=title,
        body=("Reinstall Weatherbot or restore the database from a backup.",),
        created_at=instant,
    )
    outcome = await toast.deliver(notification)
    LOGGER.error("database cannot be opened (%s): toast result=%s", kind, outcome.result)
    return outcome


@dataclass(frozen=True, slots=True)
class NotificationStep:
    """One replayed advisory's assessment, changes, policy decisions, and notification."""

    advisory: str
    issued_at: datetime
    assessment: Assessment
    changes: tuple[ChangeEvent, ...]
    decisions: tuple[PolicyDecision, ...]
    notification: NotificationDraft | None
    confirm_at: datetime | None


def _location_zone(location: Location | None) -> ZoneInfo:
    if location is not None and location.nws is not None and location.nws.time_zone:
        try:
            return ZoneInfo(location.nws.time_zone)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return ZoneInfo("UTC")


def replay_notifications(
    steps: Sequence[ReplayStep],
    *,
    location: Location | None = None,
    settings: PolicySettings | Settings | None = None,
) -> tuple[NotificationStep, ...]:
    """Run ``decide`` over a replay timeline in memory, storing nothing.

    Args:
        steps: The steps from ``ReplayService.timeline``.
        location: The replayed location (used to resolve ``local`` quiet-hours zone when
            ``settings`` is a ``Settings`` object).
        settings: ``PolicySettings`` or ``Settings``; defaults to ``PolicySettings()``.

    Returns:
        One ``NotificationStep`` per advisory step.
    """
    if settings is None:
        policy_settings = PolicySettings()
    elif isinstance(settings, Settings):
        policy_settings = settings.policy_settings(local_zone=_location_zone(location))
    else:
        policy_settings = settings

    state = PolicyState()
    results: list[NotificationStep] = []
    for step in steps:
        decided = decide(
            state,
            step.assessment,
            step.changes,
            policy_settings,
            step.assessment.as_of,
        )
        state = decided.state
        advisory = str(step.assessment.threats[0].advisory) if step.assessment.threats else ""
        results.append(
            NotificationStep(
                advisory=advisory,
                issued_at=step.assessment.as_of,
                assessment=step.assessment,
                changes=step.changes,
                decisions=decided.decisions,
                notification=decided.notification,
                confirm_at=decided.confirm_at,
            )
        )
    return tuple(results)
