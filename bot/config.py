"""Business settings from business.toml and secrets from environment variables."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    price: int
    minutes: int


@dataclass(frozen=True)
class Business:
    name: str
    address: str
    contacts: str
    tz: ZoneInfo
    days_ahead: int
    step_minutes: int
    min_lead_minutes: int
    remind_before_hours: int
    hours: dict[int, tuple[time, time] | None]  # weekday (0 = Monday) → open, close
    services: dict[str, Service]
    faq: list[tuple[str, str]]


def _time(text: str) -> time:
    h, m = text.split(":")
    return time(int(h), int(m))


def load_business(path: Path) -> Business:
    """Read and check business.toml; a mistake there should stop the bot at start, not mid-booking."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    hours: dict[int, tuple[time, time] | None] = {}
    for i, day in enumerate(WEEKDAYS):
        span = data["hours"].get(day, [])
        if not span:
            hours[i] = None
            continue
        start, end = _time(span[0]), _time(span[1])
        if start >= end:
            raise ValueError(f"{day}: opening time {span[0]} is not before closing time {span[1]}")
        hours[i] = (start, end)
    services = {}
    for s in data["services"]:
        service = Service(id=s["id"], name=s["name"], price=int(s["price"]), minutes=int(s["minutes"]))
        if service.id in services:
            raise ValueError(f"duplicate service id {service.id!r}")
        if service.minutes <= 0 or service.minutes % data["step_minutes"]:
            raise ValueError(f"{service.name}: duration must be a positive multiple of step_minutes")
        services[service.id] = service
    return Business(
        name=data["name"], address=data["address"], contacts=data["contacts"], tz=ZoneInfo(data["timezone"]),
        days_ahead=int(data["days_ahead"]), step_minutes=int(data["step_minutes"]),
        min_lead_minutes=int(data["min_lead_minutes"]), remind_before_hours=int(data["remind_before_hours"]),
        hours=hours, services=services, faq=[(f["q"], f["a"]) for f in data.get("faq", [])],
    )


@dataclass(frozen=True)
class Secrets:
    token: str
    admin_ids: frozenset[int]
    db_path: Path


def load_secrets() -> Secrets:
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Set BOT_TOKEN (get one from @BotFather). See README.")
    admins = frozenset(int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x)
    return Secrets(token=token, admin_ids=admins, db_path=Path(os.environ.get("DB_PATH", "bookings.sqlite3")))
