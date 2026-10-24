"""Which start times are free. Pure functions: no Telegram, no database, easy to test."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta

from .config import Business


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """Half-open intervals: a booking ending at 11:00 does not clash with one starting at 11:00."""
    return a_start < b_end and b_start < a_end


def free_slots(biz: Business, day: date, minutes: int, busy: Iterable[tuple[datetime, datetime]],
               now: datetime) -> list[datetime]:
    """Start times on `day` where a service of `minutes` fits before closing and clashes with nothing busy."""
    span = biz.hours[day.weekday()]
    if span is None:
        return []
    open_at = datetime.combine(day, span[0], biz.tz)
    close_at = datetime.combine(day, span[1], biz.tz)
    earliest = now + timedelta(minutes=biz.min_lead_minutes)
    length, step = timedelta(minutes=minutes), timedelta(minutes=biz.step_minutes)
    busy = list(busy)
    out = []
    t = open_at
    while t + length <= close_at:
        if t >= earliest and not any(overlaps(t, t + length, b0, b1) for b0, b1 in busy):
            out.append(t)
        t += step
    return out


def bookable_days(biz: Business, now: datetime) -> list[date]:
    """Today and the next days_ahead − 1 days, skipping days the business is closed."""
    today = now.astimezone(biz.tz).date()
    days = (today + timedelta(days=i) for i in range(biz.days_ahead))
    return [d for d in days if biz.hours[d.weekday()] is not None]
