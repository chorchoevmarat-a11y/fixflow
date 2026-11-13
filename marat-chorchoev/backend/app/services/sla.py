"""Business-time SLA clock.

The clock counts *business seconds*: time inside the organization's opening intervals,
excluding configured holidays, evaluated in the organization's IANA timezone.

State kept on the request (all derived from the append-only ``sla_events`` history):

* ``sla_budget_seconds``   total budget for the current priority
* ``sla_consumed_seconds`` business seconds consumed up to ``sla_running_since``
* ``sla_running_since``    instant the clock was last started; NULL while paused/stopped
* ``sla_due_at``           instant the remaining budget reaches zero (running clock)
* ``sla_at_risk_at``       instant the remaining budget reaches 25% of the total
* ``sla_overdue_from``     first instant the remaining budget is *below* zero
* ``sla_stopped_at`` / ``sla_final_state``  frozen outcome once work completes or is canceled

Keeping the three instants on the row makes ON_TRACK / AT_RISK / OVERDUE filterable and
countable in SQL with exactly the same answer the Python code gives.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, and_, case

from app.models.models import Priority, ServiceRequest, SlaEvent, SlaState

SLA_BUDGET_HOURS: dict[str, int] = {Priority.HIGH: 8, Priority.NORMAL: 24, Priority.LOW: 48}
_MAX_DAYS = 3660


def budget_seconds_for(priority: str) -> int:
    return SLA_BUDGET_HOURS[priority] * 3600


@dataclass(frozen=True, slots=True)
class Calendar:
    tz: ZoneInfo
    hours: dict[int, tuple[tuple[time, time], ...]]
    holidays: frozenset[date]

    def intervals(self, day: date) -> list[tuple[datetime, datetime]]:
        if day in self.holidays:
            return []
        return [
            (datetime.combine(day, opens, self.tz), datetime.combine(day, closes, self.tz))
            for opens, closes in sorted(self.hours.get(day.weekday(), ()))
        ]

    @property
    def has_hours(self) -> bool:
        return any(self.hours.values())


def business_seconds_between(cal: Calendar, start: datetime, end: datetime) -> int:
    """Business seconds in the half-open interval [start, end)."""
    if end <= start:
        return 0
    total = 0.0
    day = start.astimezone(cal.tz).date()
    last = end.astimezone(cal.tz).date()
    while day <= last:
        for opens, closes in cal.intervals(day):
            lo = max(opens, start)
            hi = min(closes, end)
            if hi > lo:
                total += (hi - lo).total_seconds()
        day += timedelta(days=1)
    return round(total)


def add_business_seconds(cal: Calendar, start: datetime, seconds: int) -> datetime | None:
    """Earliest instant at which ``seconds`` business seconds have elapsed since ``start``.

    Returns None when the calendar never opens (the budget can never be consumed).
    """
    if seconds <= 0:
        return start.astimezone(UTC)
    if not cal.has_hours:
        return None
    remaining = float(seconds)
    day = start.astimezone(cal.tz).date()
    for _ in range(_MAX_DAYS):
        for opens, closes in cal.intervals(day):
            lo = max(opens, start)
            if lo >= closes:
                continue
            available = (closes - lo).total_seconds()
            if remaining <= available:
                return (lo + timedelta(seconds=remaining)).astimezone(UTC)
            remaining -= available
        day += timedelta(days=1)
    return None


def next_business_instant(cal: Calendar, instant: datetime) -> datetime | None:
    """``instant`` if business time is running then, otherwise the next opening instant."""
    if not cal.has_hours:
        return None
    day = instant.astimezone(cal.tz).date()
    for _ in range(_MAX_DAYS):
        for opens, closes in cal.intervals(day):
            if instant < closes:
                return max(opens, instant).astimezone(UTC)
        day += timedelta(days=1)
    return None


# ---------------------------------------------------------------------------
# Operations on a request
# ---------------------------------------------------------------------------


def _sync(req: ServiceRequest, cal: Calendar, now: datetime) -> None:
    """Fold business time elapsed since the clock was started into ``consumed``."""
    if req.sla_running_since is not None:
        req.sla_consumed_seconds += business_seconds_between(cal, req.sla_running_since, now)
        req.sla_running_since = now


def _schedule(req: ServiceRequest, cal: Calendar, now: datetime) -> None:
    """Recompute the due / at-risk / overdue instants for a running clock."""
    remaining = req.sla_budget_seconds - req.sla_consumed_seconds
    if remaining > 0:
        req.sla_due_at = add_business_seconds(cal, now, remaining)
        req.sla_overdue_from = (
            next_business_instant(cal, req.sla_due_at) if req.sla_due_at is not None else None
        )
    elif req.sla_overdue_from is None or req.sla_overdue_from > now:
        # The budget is already exhausted (for example after a priority increase).
        req.sla_due_at = now
        req.sla_overdue_from = now
    until_risk = remaining - req.sla_budget_seconds // 4
    req.sla_at_risk_at = add_business_seconds(cal, now, until_risk) if until_risk > 0 else now


def _event(req: ServiceRequest, kind: str, now: datetime, detail: str | None = None) -> SlaEvent:
    return SlaEvent(
        org_id=req.org_id,
        request_id=req.id,
        kind=kind,
        occurred_at=now,
        budget_seconds=req.sla_budget_seconds,
        consumed_seconds=req.sla_consumed_seconds,
        due_at=req.sla_due_at,
        detail=detail,
    )


def start(req: ServiceRequest, cal: Calendar, now: datetime) -> SlaEvent:
    req.sla_budget_seconds = budget_seconds_for(req.priority)
    req.sla_consumed_seconds = 0
    req.sla_running_since = now
    _schedule(req, cal, now)
    return _event(req, "STARTED", now, f"priority {req.priority}")


def is_paused(req: ServiceRequest) -> bool:
    return req.sla_running_since is None and req.sla_stopped_at is None


def pause(req: ServiceRequest, cal: Calendar, now: datetime, detail: str) -> SlaEvent | None:
    if req.sla_stopped_at is not None or req.sla_running_since is None:
        return None
    _sync(req, cal, now)
    req.sla_running_since = None
    if req.sla_budget_seconds - req.sla_consumed_seconds >= 0:
        req.sla_due_at = None
        req.sla_at_risk_at = None
        req.sla_overdue_from = None
    return _event(req, "PAUSED", now, detail)


def resume(req: ServiceRequest, cal: Calendar, now: datetime, detail: str) -> SlaEvent | None:
    if req.sla_stopped_at is not None or req.sla_running_since is not None:
        return None
    req.sla_running_since = now
    _schedule(req, cal, now)
    return _event(req, "RESUMED", now, detail)


def stop(req: ServiceRequest, cal: Calendar, now: datetime, detail: str) -> SlaEvent | None:
    """Freeze the outcome (completion or cancellation)."""
    if req.sla_stopped_at is not None:
        return None
    final = state_of(req, now)
    _sync(req, cal, now)
    req.sla_running_since = None
    req.sla_stopped_at = now
    req.sla_final_state = final
    return _event(req, "STOPPED", now, f"{detail}; outcome {final}")


def change_priority(req: ServiceRequest, cal: Calendar, now: datetime, priority: str) -> SlaEvent:
    """New total budget minus the business time already consumed (SLA-05)."""
    old = req.priority
    req.priority = priority
    if req.sla_stopped_at is None:
        _sync(req, cal, now)
        req.sla_budget_seconds = budget_seconds_for(priority)
        if req.sla_running_since is not None:
            _schedule(req, cal, now)
    return _event(req, "PRIORITY_CHANGED", now, f"{old} -> {priority}")


def recalculate(
    req: ServiceRequest, old: Calendar, new: Calendar, now: datetime
) -> SlaEvent | None:
    """Business calendar changed: bank consumption under the old rules, plan under the new."""
    if req.sla_stopped_at is not None or req.sla_running_since is None:
        return None
    _sync(req, old, now)
    _schedule(req, new, now)
    return _event(req, "CALENDAR_CHANGED", now)


def state_of(req: ServiceRequest, now: datetime) -> str:
    if req.sla_stopped_at is not None:
        return req.sla_final_state or SlaState.ON_TRACK
    if req.sla_running_since is None:
        remaining = req.sla_budget_seconds - req.sla_consumed_seconds
        if remaining < 0:
            return SlaState.OVERDUE
        return SlaState.AT_RISK if remaining * 4 <= req.sla_budget_seconds else SlaState.ON_TRACK
    if req.sla_overdue_from is not None and now > req.sla_overdue_from:
        return SlaState.OVERDUE
    if req.sla_at_risk_at is not None and now >= req.sla_at_risk_at:
        return SlaState.AT_RISK
    return SlaState.ON_TRACK


def sla_state_expr(now: datetime) -> ColumnElement[str]:
    """SQL twin of :func:`state_of`, for filtering and counting."""
    r = ServiceRequest
    paused_remaining = r.sla_budget_seconds - r.sla_consumed_seconds
    return case(
        (r.sla_stopped_at.is_not(None), r.sla_final_state),
        (
            r.sla_running_since.is_(None),
            case(
                (paused_remaining < 0, SlaState.OVERDUE.value),
                (paused_remaining * 4 <= r.sla_budget_seconds, SlaState.AT_RISK.value),
                else_=SlaState.ON_TRACK.value,
            ),
        ),
        (and_(r.sla_overdue_from.is_not(None), r.sla_overdue_from < now), SlaState.OVERDUE.value),
        (and_(r.sla_at_risk_at.is_not(None), r.sla_at_risk_at <= now), SlaState.AT_RISK.value),
        else_=SlaState.ON_TRACK.value,
    )


def snapshot(req: ServiceRequest, cal: Calendar, now: datetime) -> dict:
    consumed = req.sla_consumed_seconds
    if req.sla_running_since is not None:
        consumed += business_seconds_between(cal, req.sla_running_since, now)
    remaining = req.sla_budget_seconds - consumed
    return {
        "state": state_of(req, now),
        "budget_seconds": req.sla_budget_seconds,
        "consumed_seconds": consumed,
        "remaining_seconds": remaining,
        "due_at": req.sla_due_at.isoformat() if req.sla_due_at else None,
        "paused": is_paused(req),
        "stopped_at": req.sla_stopped_at.isoformat() if req.sla_stopped_at else None,
        "escalated_at": req.sla_escalated_at.isoformat() if req.sla_escalated_at else None,
    }
