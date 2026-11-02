# src/weatherbot/services/ai/ledger.py
"""The Claude ledger: every request reserved before it is sent and settled after, under a cap.

``Ledger.reserve`` runs inside one ``BEGIN IMMEDIATE`` transaction, so two processes
(``serve``, ``brief``, ``ask``) take SQLite's write lock in turn and never pass the cap
together. It first marks a reservation older than 15 minutes, whose process died,
``abandoned`` at its ceiling; refuses every request while the newest ``pause`` or
``resume`` row is a pause; adds today's settled cost, today's open reservations, and this
request's ceiling; and refuses when that sum passes the cap plus today's allowances.
Otherwise it inserts a ``reserved`` row. ``Ledger.settle`` writes the outcome: the SDK's
usage priced from ``pricing.PRICES``, or the ceiling for a stream that ended without its
final message. ``pause``, ``resume``, and ``allow`` write zero-token control rows, because
the AI engine may write no other table. "Today" is the operator's local calendar day.
Once a settle or a control row is committed, the ``changed`` hook (the AI service's) hears
of it: the row's id, kind, status, and location, never its text.

The ledger runs on the AI engine (``guard.ai_engine``) and imports no SDK.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo
from typing import Final, Literal, get_args

from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from weatherbot.services.ai.errors import AiUnavailable
from weatherbot.services.ai.pricing import (
    MICRO_USD_PER_USD,
    PRICES_AS_OF,
    TokenUsage,
    cost_micro_usd,
)
from weatherbot.services.persistence.database import writing_session
from weatherbot.services.persistence.tables import AiCallRow

type CallKind = Literal["briefing", "summary", "chat", "narration"]
type ControlKind = Literal["allowance", "pause", "resume"]
type SettledStatus = Literal["ok", "failed", "incomplete", "declined"]
"""How a settled request ended; a row is also ``reserved``, ``abandoned``, or ``control``."""

CALL_KINDS: Final[tuple[CallKind, ...]] = get_args(CallKind.__value__)
CONTROL_KINDS: Final[tuple[ControlKind, ...]] = get_args(ControlKind.__value__)
ABANDON_AFTER: Final = timedelta(minutes=15)
MAX_ALLOWANCES_PER_DAY: Final = 3
MAX_REQUEST_ID_LENGTH: Final = 64


def micro_usd(usd: float) -> int:
    """Convert a dollar setting to integer micro-dollars.

    Args:
        usd: Dollars, as ``[ai] daily_cap_usd`` holds them.

    Returns:
        The amount in micro-dollars, rounded to the nearest one.
    """
    return round(usd * MICRO_USD_PER_USD)


@dataclass(frozen=True)
class Reservation:
    """A request's reserved row: what ``settle`` needs to finish it."""

    id: int
    kind: CallKind
    model: str
    ceiling_micro_usd: int
    day: str
    location: str | None = None


@dataclass(frozen=True)
class Outcome:
    """How a request ended, for ``settle``; never its prompt or its answer."""

    status: SettledStatus
    usage: TokenUsage = field(default_factory=TokenUsage)
    stop_reason: str | None = None
    refusal_category: str | None = None
    error_kind: str | None = None
    request_id: str | None = None


@dataclass(frozen=True)
class LedgerDay:
    """Today's spend against the cap."""

    day: str
    cap_micro_usd: int
    allowance_micro_usd: int
    spent_micro_usd: int
    """Settled requests and abandoned reservations, at their cost."""
    reserved_micro_usd: int
    """Open reservations, at their ceilings."""
    requests: int
    allowances: int
    paused: bool

    @property
    def limit_micro_usd(self) -> int:
        """The cap plus today's allowances."""
        return self.cap_micro_usd + self.allowance_micro_usd

    @property
    def headroom_micro_usd(self) -> int:
        """What today's limit leaves after spend and open reservations."""
        return self.limit_micro_usd - self.spent_micro_usd - self.reserved_micro_usd


@dataclass(frozen=True)
class LedgerEntry:
    """One ledger row as the surfaces show it: no prompt, no answer, no credential."""

    id: int
    kind: str
    model: str | None
    location_name: str | None
    status: str
    day: str
    started_at: datetime
    finished_at: datetime | None
    ceiling_micro_usd: int
    cost_micro_usd: int | None
    allowance_micro_usd: int
    usage: TokenUsage
    stop_reason: str | None
    refusal_category: str | None
    error_kind: str | None
    request_id: str | None


@dataclass(frozen=True)
class KindTotals:
    """One kind of request's count, tokens, and cost on one day."""

    kind: str
    requests: int
    usage: TokenUsage
    cost_micro_usd: int


@dataclass(frozen=True)
class LedgerChange:
    """A committed settle or control row: what a page needs to refetch, never its text."""

    call_id: int
    kind: str
    status: str
    location: str | None


type LedgerHook = Callable[[LedgerChange], None]


class AllowanceRefusedError(ValueError):
    """An allowance the ledger refuses; the message is fixed text."""


class AllowancesExhaustedError(AllowanceRefusedError):
    """Today's allowances are used up: a fourth is refused."""


def _entry(row: AiCallRow) -> LedgerEntry:
    return LedgerEntry(
        id=row.id,
        kind=row.kind,
        model=row.model,
        location_name=row.location_name,
        status=row.status,
        day=row.day,
        started_at=row.started_at,
        finished_at=row.finished_at,
        ceiling_micro_usd=row.ceiling_micro_usd,
        cost_micro_usd=row.cost_micro_usd,
        allowance_micro_usd=row.allowance_micro_usd,
        usage=TokenUsage(
            input_tokens=row.input_tokens,
            cache_write_5m_tokens=row.cache_write_5m_tokens,
            cache_write_1h_tokens=row.cache_write_1h_tokens,
            cache_read_tokens=row.cache_read_tokens,
            output_tokens=row.output_tokens,
        ),
        stop_reason=row.stop_reason,
        refusal_category=row.refusal_category,
        error_kind=row.error_kind,
        request_id=row.request_id,
    )


class Ledger:
    """The per-call ledger and the daily cap, shared by every process through the database."""

    def __init__(
        self,
        engine: Engine,
        *,
        cap_micro_usd: int,
        now: Callable[[], datetime],
        local_zone: tzinfo | None = None,
        changed: LedgerHook | None = None,
    ) -> None:
        """Create the ledger.

        Args:
            engine: The AI engine.
            cap_micro_usd: The daily cap, ``[ai] daily_cap_usd`` in micro-dollars.
            now: The clock.
            local_zone: The operator's time zone; the machine's when omitted.
            changed: Hears of each committed settle and control row.
        """
        self._engine = engine
        self._cap = cap_micro_usd
        self._now = now
        self._zone = local_zone
        self._changed = changed

    @property
    def cap_micro_usd(self) -> int:
        """The daily cap, before allowances."""
        return self._cap

    def day_of(self, instant: datetime) -> str:
        """Name an instant's local calendar day.

        Args:
            instant: An aware instant.

        Returns:
            ``YYYY-MM-DD`` in the operator's zone.
        """
        local = instant.astimezone(self._zone) if self._zone else instant.astimezone()
        return local.date().isoformat()

    def _day(self, session: Session, day: str) -> LedgerDay:
        today = AiCallRow.day == day
        spent = session.scalar(
            select(func.coalesce(func.sum(AiCallRow.cost_micro_usd), 0)).where(
                today, AiCallRow.status != "reserved"
            )
        )
        reserved = session.scalar(
            select(func.coalesce(func.sum(AiCallRow.ceiling_micro_usd), 0)).where(
                today, AiCallRow.status == "reserved"
            )
        )
        allowance = session.scalar(
            select(func.coalesce(func.sum(AiCallRow.allowance_micro_usd), 0)).where(
                today, AiCallRow.kind == "allowance"
            )
        )
        allowances = session.scalar(
            select(func.count()).where(today, AiCallRow.kind == "allowance")
        )
        requests = session.scalar(select(func.count()).where(today, AiCallRow.kind.in_(CALL_KINDS)))
        newest_switch = session.scalar(
            select(AiCallRow.kind)
            .where(AiCallRow.kind.in_(("pause", "resume")))
            .order_by(AiCallRow.id.desc())
            .limit(1)
        )
        return LedgerDay(
            day=day,
            cap_micro_usd=self._cap,
            allowance_micro_usd=int(allowance or 0),
            spent_micro_usd=int(spent or 0),
            reserved_micro_usd=int(reserved or 0),
            requests=int(requests or 0),
            allowances=int(allowances or 0),
            paused=newest_switch == "pause",
        )

    def reserve(
        self,
        kind: CallKind,
        model: str,
        location: str | None,
        prompt_version: str | None,
        ceiling: int,
    ) -> Reservation:
        """Reserve a request's ceiling under today's cap, or refuse it.

        Args:
            kind: The product the request makes.
            model: The model it runs on.
            location: The location it is about, by name; ``None`` for none.
            prompt_version: The frozen prompt's SHA-256, when one applies.
            ceiling: The most the request can cost, in micro-dollars.

        Returns:
            The reservation, for ``settle``.

        Raises:
            AiUnavailable: ``paused`` while the pause holds, or ``capped`` when the ceiling
                would pass today's limit.
        """
        now = self._now()
        day = self.day_of(now)
        with writing_session(self._engine) as session:
            session.execute(
                update(AiCallRow)
                .where(AiCallRow.status == "reserved", AiCallRow.started_at < now - ABANDON_AFTER)
                .values(
                    status="abandoned",
                    finished_at=now,
                    cost_micro_usd=AiCallRow.ceiling_micro_usd,
                    error_kind="abandoned",
                )
            )
            today = self._day(session, day)
            if today.paused:
                raise AiUnavailable(reason="paused")
            if today.spent_micro_usd + today.reserved_micro_usd + ceiling > today.limit_micro_usd:
                raise AiUnavailable(reason="capped")
            row = AiCallRow(
                kind=kind,
                model=model,
                prompt_version=prompt_version,
                location_name=location,
                status="reserved",
                day=day,
                started_at=now,
                ceiling_micro_usd=ceiling,
                prices_as_of=PRICES_AS_OF,
            )
            session.add(row)
            session.flush()
            return Reservation(row.id, kind, model, ceiling, day, location)

    def settle(self, reservation: Reservation, outcome: Outcome) -> None:
        """Write a request's outcome: its usage, its cost, and how it ended.

        An ``incomplete`` request settles at its ceiling, because the tokens it was billed
        for are unknown; every other outcome is priced from its usage.

        Args:
            reservation: The request's reservation.
            outcome: How it ended.
        """
        cost = cost_micro_usd(reservation.model, outcome.usage)
        if outcome.status == "incomplete":
            cost = max(cost, reservation.ceiling_micro_usd)
        request_id = outcome.request_id[:MAX_REQUEST_ID_LENGTH] if outcome.request_id else None
        with writing_session(self._engine) as session:
            session.execute(
                update(AiCallRow)
                .where(AiCallRow.id == reservation.id)
                .values(
                    status=outcome.status,
                    finished_at=self._now(),
                    cost_micro_usd=cost,
                    input_tokens=outcome.usage.input_tokens,
                    cache_write_5m_tokens=outcome.usage.cache_write_5m_tokens,
                    cache_write_1h_tokens=outcome.usage.cache_write_1h_tokens,
                    cache_read_tokens=outcome.usage.cache_read_tokens,
                    output_tokens=outcome.usage.output_tokens,
                    stop_reason=outcome.stop_reason,
                    refusal_category=outcome.refusal_category,
                    error_kind=outcome.error_kind,
                    request_id=request_id,
                )
            )
        self._notify(
            LedgerChange(reservation.id, reservation.kind, outcome.status, reservation.location)
        )

    def _notify(self, change: LedgerChange) -> None:
        if self._changed is not None:
            self._changed(change)

    def today(self) -> LedgerDay:
        """Read today's spend, open reservations, allowances, and the pause.

        Returns:
            Today, in the operator's zone.
        """
        with Session(self._engine) as session:
            return self._day(session, self.day_of(self._now()))

    def recent(self, limit: int) -> tuple[LedgerEntry, ...]:
        """Read the newest rows, newest first.

        Args:
            limit: How many.

        Returns:
            The rows.
        """
        with Session(self._engine) as session:
            rows: Sequence[AiCallRow] = session.scalars(
                select(AiCallRow).order_by(AiCallRow.id.desc()).limit(limit)
            ).all()
            return tuple(_entry(row) for row in rows)

    def entry(self, call_id: int) -> LedgerEntry | None:
        """Read one row.

        Args:
            call_id: Its id.

        Returns:
            The row, or ``None``.
        """
        with Session(self._engine) as session:
            row = session.get(AiCallRow, call_id)
            return _entry(row) if row is not None else None

    def by_kind(self) -> tuple[KindTotals, ...]:
        """Total today's requests by kind: their count, tokens, and cost.

        Returns:
            One entry per kind of request that ran today, in ``CALL_KINDS`` order.
        """
        day = self.day_of(self._now())
        columns = (
            func.count(),
            func.coalesce(func.sum(AiCallRow.input_tokens), 0),
            func.coalesce(func.sum(AiCallRow.cache_write_5m_tokens), 0),
            func.coalesce(func.sum(AiCallRow.cache_write_1h_tokens), 0),
            func.coalesce(func.sum(AiCallRow.cache_read_tokens), 0),
            func.coalesce(func.sum(AiCallRow.output_tokens), 0),
            func.coalesce(func.sum(AiCallRow.cost_micro_usd), 0),
        )
        with Session(self._engine) as session:
            rows = session.execute(
                select(AiCallRow.kind, *columns)
                .where(AiCallRow.day == day, AiCallRow.kind.in_(CALL_KINDS))
                .group_by(AiCallRow.kind)
            ).all()
        found = {
            str(kind): KindTotals(
                kind=str(kind),
                requests=int(count),
                usage=TokenUsage(int(given), int(write_5m), int(write_1h), int(cached), int(out)),
                cost_micro_usd=int(cost or 0),
            )
            for kind, count, given, write_5m, write_1h, cached, out, cost in rows
        }
        return tuple(found[kind] for kind in CALL_KINDS if kind in found)

    def _control(self, kind: ControlKind, allowance: int = 0) -> None:
        now = self._now()
        with writing_session(self._engine) as session:
            if kind == "allowance":
                today = self._day(session, self.day_of(now))
                if today.allowances >= MAX_ALLOWANCES_PER_DAY:
                    message = f"at most {MAX_ALLOWANCES_PER_DAY} allowances a day"
                    raise AllowancesExhaustedError(message)
            row = AiCallRow(
                kind=kind,
                status="control",
                day=self.day_of(now),
                started_at=now,
                finished_at=now,
                ceiling_micro_usd=0,
                cost_micro_usd=0,
                allowance_micro_usd=allowance,
                prices_as_of=PRICES_AS_OF,
            )
            session.add(row)
            session.flush()
            call_id = row.id
        self._notify(LedgerChange(call_id, kind, "control", None))

    def pause(self) -> None:
        """Pause AI: every request is refused until ``resume``."""
        self._control("pause")

    def resume(self) -> None:
        """Lift the pause."""
        self._control("resume")

    def allow(self, amount_micro_usd: int) -> None:
        """Raise today's limit by an allowance: at most one day's cap, three times a day.

        Args:
            amount_micro_usd: The allowance, in micro-dollars.

        Raises:
            AllowanceRefusedError: The amount is not positive or passes one day's cap;
                ``AllowancesExhaustedError`` when it would be today's fourth allowance.
        """
        if amount_micro_usd <= 0:
            message = "an allowance must be more than zero"
            raise AllowanceRefusedError(message)
        if amount_micro_usd > self._cap:
            message = "an allowance is at most one day's cap"
            raise AllowanceRefusedError(message)
        self._control("allowance", amount_micro_usd)
