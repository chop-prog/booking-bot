"""Bookings in SQLite. Times are stored as UTC ISO strings, so they sort and compare correctly."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    client_name TEXT    NOT NULL,
    phone       TEXT    NOT NULL,
    service_id  TEXT    NOT NULL,
    starts_at   TEXT    NOT NULL,
    ends_at     TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'active',  -- active | cancelled
    reminded    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS bookings_time ON bookings (status, starts_at);
"""


class SlotTaken(Exception):
    """Someone else booked an overlapping time first."""


@dataclass(frozen=True)
class Booking:
    id: int
    user_id: int
    client_name: str
    phone: str
    service_id: str
    starts_at: datetime
    ends_at: datetime
    status: str


def _utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("naive datetime: pass an aware one")
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _row(r: sqlite3.Row) -> Booking:
    return Booking(id=r["id"], user_id=r["user_id"], client_name=r["client_name"], phone=r["phone"],
                   service_id=r["service_id"], starts_at=datetime.fromisoformat(r["starts_at"]),
                   ends_at=datetime.fromisoformat(r["ends_at"]), status=r["status"])


class Storage:
    def __init__(self, path: Path | str):
        # isolation_level=None: we open transactions ourselves, so the clash check and the insert are atomic.
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def busy(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
        """Active bookings that overlap [start, end)."""
        rows = self.db.execute(
            "SELECT starts_at, ends_at FROM bookings WHERE status = 'active' AND starts_at < ? AND ends_at > ?",
            (_utc(end), _utc(start))).fetchall()
        return [(datetime.fromisoformat(a), datetime.fromisoformat(b)) for a, b in rows]

    def book(self, user_id: int, client_name: str, phone: str, service_id: str,
             start: datetime, end: datetime, now: datetime) -> Booking:
        """Insert a booking, or raise SlotTaken if the time was taken while the client was choosing."""
        self.db.execute("BEGIN IMMEDIATE")  # takes the write lock: no one can book in between
        try:
            if self.busy(start, end):
                raise SlotTaken
            cur = self.db.execute(
                "INSERT INTO bookings (user_id, client_name, phone, service_id, starts_at, ends_at, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, client_name, phone, service_id, _utc(start), _utc(end), _utc(now)))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return self.get(cur.lastrowid)

    def get(self, booking_id: int) -> Booking:
        return _row(self.db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone())

    def upcoming_for_user(self, user_id: int, now: datetime) -> list[Booking]:
        rows = self.db.execute(
            "SELECT * FROM bookings WHERE user_id = ? AND status = 'active' AND starts_at > ? ORDER BY starts_at",
            (user_id, _utc(now))).fetchall()
        return [_row(r) for r in rows]

    def between(self, start: datetime, end: datetime) -> list[Booking]:
        rows = self.db.execute(
            "SELECT * FROM bookings WHERE status = 'active' AND starts_at >= ? AND starts_at < ? ORDER BY starts_at",
            (_utc(start), _utc(end))).fetchall()
        return [_row(r) for r in rows]

    def cancel(self, booking_id: int, user_id: int | None = None) -> Booking | None:
        """Cancel an active booking; with user_id, only that client's own. Returns it, or None if not allowed."""
        sql = "UPDATE bookings SET status = 'cancelled' WHERE id = ? AND status = 'active'"
        args: tuple = (booking_id,)
        if user_id is not None:
            sql += " AND user_id = ?"
            args += (user_id,)
        if self.db.execute(sql, args).rowcount == 0:
            return None
        return self.get(booking_id)

    def due_reminders(self, now: datetime, ahead_hours: int) -> list[Booking]:
        """Active, not yet reminded bookings that start within the next `ahead_hours`."""
        rows = self.db.execute(
            "SELECT * FROM bookings WHERE status = 'active' AND reminded = 0 AND starts_at > ? AND starts_at <= ?",
            (_utc(now), _utc(now + timedelta(hours=ahead_hours)))).fetchall()
        return [_row(r) for r in rows]

    def mark_reminded(self, booking_id: int) -> None:
        self.db.execute("UPDATE bookings SET reminded = 1 WHERE id = ?", (booking_id,))
