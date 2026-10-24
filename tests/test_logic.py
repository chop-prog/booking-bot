from datetime import date, datetime, timedelta

import pytest

from bot.config import load_business
from bot.slots import bookable_days, free_slots, overlaps
from bot.storage import SlotTaken
from bot.ui import fmt_day, normalize_phone, rub

MONDAY = date(2026, 10, 26)


def at(biz, day, hh, mm=0):
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=biz.tz)


def test_config_loads_demo_business(biz):
    assert biz.services["cut"].price == 1500
    assert biz.hours[6] is None  # closed on Sunday
    assert biz.hours[4][1].hour == 21


def test_config_rejects_bad_durations(tmp_path):
    bad = (tmp_path / "b.toml")
    bad.write_text("""
name = "x"\naddress = "x"\ncontacts = "x"\ntimezone = "Europe/Moscow"
days_ahead = 7\nstep_minutes = 30\nmin_lead_minutes = 60\nremind_before_hours = 3
[hours]\nmon = ["10:00", "20:00"]
[[services]]\nid = "a"\nname = "A"\nprice = 1\nminutes = 45
""", encoding="utf-8")
    with pytest.raises(ValueError, match="multiple of step_minutes"):
        load_business(bad)


def test_overlaps_is_half_open(biz):
    assert not overlaps(at(biz, MONDAY, 10), at(biz, MONDAY, 11), at(biz, MONDAY, 11), at(biz, MONDAY, 12))
    assert overlaps(at(biz, MONDAY, 10), at(biz, MONDAY, 11, 30), at(biz, MONDAY, 11), at(biz, MONDAY, 12))


def test_free_slots_fit_before_closing(biz):
    slots = free_slots(biz, MONDAY, 90, [], now=at(biz, MONDAY, 6))
    assert slots[0] == at(biz, MONDAY, 10)
    assert slots[-1] == at(biz, MONDAY, 18, 30)  # 18:30 + 90 min = 20:00, closing time
    assert len(slots) == 18


def test_free_slots_skip_busy_time(biz):
    busy = [(at(biz, MONDAY, 12), at(biz, MONDAY, 13))]
    slots = free_slots(biz, MONDAY, 60, busy, now=at(biz, MONDAY, 6))
    assert at(biz, MONDAY, 11) in slots          # ends exactly when the busy one starts
    assert at(biz, MONDAY, 11, 30) not in slots  # would run into it
    assert at(biz, MONDAY, 12, 30) not in slots
    assert at(biz, MONDAY, 13) in slots


def test_free_slots_respect_lead_time(biz):
    slots = free_slots(biz, MONDAY, 30, [], now=at(biz, MONDAY, 14, 10))
    assert slots[0] == at(biz, MONDAY, 15, 30)  # 14:10 + 60 min lead → first step at 15:30


def test_closed_day_has_no_slots_and_is_not_offered(biz):
    sunday = MONDAY + timedelta(days=6)
    assert free_slots(biz, sunday, 30, [], now=at(biz, MONDAY, 6)) == []
    days = bookable_days(biz, at(biz, MONDAY, 9))
    assert sunday not in days and len(days) == 6


def test_booking_conflicts_are_rejected(biz, store):
    now = at(biz, MONDAY, 9)
    store.book(1, "Иван", "+79001234567", "cut", at(biz, MONDAY, 10), at(biz, MONDAY, 11), now)
    with pytest.raises(SlotTaken):
        store.book(2, "Пётр", "+79007654321", "beard", at(biz, MONDAY, 10, 30), at(biz, MONDAY, 11), now)
    store.book(2, "Пётр", "+79007654321", "beard", at(biz, MONDAY, 11), at(biz, MONDAY, 11, 30), now)
    assert len(store.between(at(biz, MONDAY, 0), at(biz, MONDAY, 23))) == 2


def test_cancel_frees_the_slot_and_checks_the_owner(biz, store):
    now = at(biz, MONDAY, 9)
    b = store.book(1, "Иван", "+79001234567", "cut", at(biz, MONDAY, 10), at(biz, MONDAY, 11), now)
    assert store.cancel(b.id, user_id=2) is None  # someone else's booking
    assert store.cancel(b.id, user_id=1).status == "cancelled"
    assert store.cancel(b.id, user_id=1) is None  # already cancelled
    assert store.busy(at(biz, MONDAY, 10), at(biz, MONDAY, 11)) == []


def test_reminders_are_due_once_inside_the_window(biz, store):
    now = at(biz, MONDAY, 9)
    soon = store.book(1, "Иван", "+79001234567", "cut", at(biz, MONDAY, 11), at(biz, MONDAY, 12), now)
    store.book(2, "Пётр", "+79007654321", "cut", at(biz, MONDAY, 15), at(biz, MONDAY, 16), now)
    assert [b.id for b in store.due_reminders(now, 3)] == [soon.id]
    store.mark_reminded(soon.id)
    assert store.due_reminders(now, 3) == []


@pytest.mark.parametrize("text, phone", [
    ("+7 900 123-45-67", "+79001234567"),
    ("89001234567", "+79001234567"),
    ("9001234567", "+79001234567"),
    ("+7 (495) 123-45-67", None),  # a landline: no SMS, no Telegram
    ("123", None),
    ("", None),
])
def test_normalize_phone(text, phone):
    assert normalize_phone(text) == phone


def test_formatting():
    assert rub(12500) == "12 500 ₽"
    assert fmt_day(MONDAY) == "пн, 26 окт"
