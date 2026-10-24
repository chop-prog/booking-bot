"""Texts, formatting and keyboards. Kept apart from handlers so wording can change without touching logic."""

from __future__ import annotations

import re
from datetime import date, datetime
from html import escape

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .config import Business
from .storage import Booking

WEEKDAYS_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


class Menu(CallbackData, prefix="m"):
    action: str  # book | prices | mine | faq | contacts | home


class PickService(CallbackData, prefix="s"):
    service: str


class PickDay(CallbackData, prefix="d"):
    service: str
    day: str  # ISO date


class PickTime(CallbackData, prefix="t"):
    service: str
    ts: int  # unix seconds


class Confirm(CallbackData, prefix="c"):
    ok: bool


class CancelBooking(CallbackData, prefix="x"):
    id: int


# ---------- formatting ----------

def rub(price: int) -> str:
    return f"{price:,}".replace(",", " ") + " ₽"


def fmt_day(d: date) -> str:
    return f"{WEEKDAYS_SHORT[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}"


def fmt_when(dt: datetime, biz: Business) -> str:
    local = dt.astimezone(biz.tz)
    return f"{fmt_day(local.date())} в {local:%H:%M}"


def normalize_phone(text: str) -> str | None:
    """A Russian mobile in +7XXXXXXXXXX form, or None if it does not look like one."""
    digits = re.sub(r"\D", "", text)
    if len(digits) == 11 and digits[0] in "78":
        digits = digits[1:]
    if len(digits) == 10 and digits[0] == "9":
        return "+7" + digits
    return None


def booking_line(b: Booking, biz: Business) -> str:
    service = biz.services.get(b.service_id)
    name = service.name if service else b.service_id
    return f"{fmt_when(b.starts_at, biz)} — {escape(name)}"


# ---------- texts ----------

def welcome(biz: Business, first_name: str) -> str:
    return (f"Здравствуйте, {escape(first_name)}! Это бот <b>{escape(biz.name)}</b>.\n\n"
            "Здесь можно записаться, посмотреть цены и свои записи.")


def prices(biz: Business) -> str:
    lines = [f"• {escape(s.name)} — {rub(s.price)} ({s.minutes} мин)" for s in biz.services.values()]
    return "<b>Услуги и цены</b>\n\n" + "\n".join(lines)


def faq(biz: Business) -> str:
    if not biz.faq:
        return "Пока здесь пусто."
    return "\n\n".join(f"<b>{escape(q)}</b>\n{escape(a)}" for q, a in biz.faq)


def contacts(biz: Business) -> str:
    return f"<b>{escape(biz.name)}</b>\n{escape(biz.address)}\n{escape(biz.contacts)}"


def summary(biz: Business, service_id: str, start: datetime, name: str, phone: str) -> str:
    s = biz.services[service_id]
    return (f"<b>Проверьте запись</b>\n\n"
            f"Услуга: {escape(s.name)}\nКогда: {fmt_when(start, biz)}\n"
            f"Длительность: {s.minutes} мин\nСтоимость: {rub(s.price)}\n"
            f"Имя: {escape(name)}\nТелефон: {phone}")


def admin_new(biz: Business, b: Booking) -> str:
    return (f"🆕 Новая запись #{b.id}\n{booking_line(b, biz)}\n"
            f"{escape(b.client_name)}, {b.phone}")


def admin_cancelled(biz: Business, b: Booking) -> str:
    return f"❌ Клиент отменил запись #{b.id}\n{booking_line(b, biz)}\n{escape(b.client_name)}, {b.phone}"


def reminder(biz: Business, b: Booking) -> str:
    return (f"Напоминаем: {booking_line(b, biz)}.\n{escape(biz.address)}\n\n"
            "Если не получается прийти, отмените запись в «Мои записи».")


# ---------- keyboards ----------

def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Записаться", callback_data=Menu(action="book"))
    kb.button(text="💈 Услуги и цены", callback_data=Menu(action="prices"))
    kb.button(text="🗂 Мои записи", callback_data=Menu(action="mine"))
    kb.button(text="❓ Вопросы", callback_data=Menu(action="faq"))
    kb.button(text="📍 Контакты", callback_data=Menu(action="contacts"))
    kb.adjust(1, 2, 2)
    return kb.as_markup()


def _nav(kb: InlineKeyboardBuilder, text: str, data: CallbackData) -> InlineKeyboardMarkup:
    """A navigation button on its own last row."""
    kb.row(InlineKeyboardButton(text=text, callback_data=data.pack()))
    return kb.as_markup()


def back_home(kb: InlineKeyboardBuilder | None = None) -> InlineKeyboardMarkup:
    return _nav(kb or InlineKeyboardBuilder(), "← В меню", Menu(action="home"))


def services_kb(biz: Business) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in biz.services.values():
        kb.button(text=f"{s.name} · {rub(s.price)}", callback_data=PickService(service=s.id))
    kb.adjust(1)
    return back_home(kb)


def days_kb(service_id: str, days: list[date]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for d in days:
        kb.button(text=fmt_day(d), callback_data=PickDay(service=service_id, day=d.isoformat()))
    kb.adjust(3)
    return _nav(kb, "← Услуги", Menu(action="book"))


def times_kb(biz: Business, service_id: str, slots: list[datetime]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in slots:
        kb.button(text=t.astimezone(biz.tz).strftime("%H:%M"), callback_data=PickTime(service=service_id, ts=int(t.timestamp())))
    kb.adjust(4)
    return _nav(kb, "← Дни", PickService(service=service_id))


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 Отправить мой номер", request_contact=True)]],
                               resize_keyboard=True, one_time_keyboard=True)


def confirm_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data=Confirm(ok=True))
    kb.button(text="Отмена", callback_data=Confirm(ok=False))
    return kb.as_markup()


def my_bookings_kb(bookings: list[Booking], biz: Business) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for b in bookings:
        kb.button(text=f"Отменить: {fmt_when(b.starts_at, biz)}", callback_data=CancelBooking(id=b.id))
    kb.adjust(1)
    return back_home(kb)
