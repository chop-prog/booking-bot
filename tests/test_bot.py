"""The whole conversation, driven through a fake Telegram (see conftest.py)."""

from datetime import datetime, timedelta

import pytest

from bot import reminders
from conftest import ADMIN_ID

pytestmark = pytest.mark.asyncio


async def book_haircut(chat, time_label="10:00", day_label="пн, 26 окт"):
    await chat.send("/start")
    await chat.press(chat.buttons()["📅 Записаться"])
    await chat.press(chat.buttons()["Мужская стрижка · 1 500 ₽"])
    await chat.press(chat.buttons()[day_label])
    await chat.press(chat.buttons()[time_label])
    await chat.send("Иван")
    await chat.send("8 900 123 45 67")


async def test_start_shows_menu(telegram):
    chat = telegram()
    await chat.send("/start")
    assert "Здравствуйте, Иван!" in chat.last.text
    assert list(chat.buttons()) == ["📅 Записаться", "💈 Услуги и цены", "🗂 Мои записи", "❓ Вопросы", "📍 Контакты"]


async def test_prices_and_back(telegram):
    chat = telegram()
    await chat.send("/start")
    await chat.press(chat.buttons()["💈 Услуги и цены"])
    assert "Мужская стрижка — 1 500 ₽ (60 мин)" in chat.last.text
    await chat.press(chat.buttons()["← В меню"])
    assert "📅 Записаться" in chat.buttons()


async def test_full_booking_notifies_the_admin(telegram, store, biz):
    chat = telegram()
    await book_haircut(chat)
    assert "Проверьте запись" in chat.last.text and "+79001234567" in chat.last.text
    await chat.press(chat.buttons()["✅ Подтвердить"])
    assert "Готово! Вы записаны: пн, 26 окт в 10:00 — Мужская стрижка" in chat.last.text
    [admin_msg] = chat.sent_to(ADMIN_ID)
    assert "Новая запись" in admin_msg and "Иван, +79001234567" in admin_msg
    [b] = store.upcoming_for_user(1, datetime(2026, 10, 26, 9, tzinfo=biz.tz))
    assert b.ends_at - b.starts_at == timedelta(minutes=60)


async def test_taken_time_disappears_for_the_next_client(telegram):
    first = telegram(user_id=1)
    await book_haircut(first)
    await first.press(first.buttons()["✅ Подтвердить"])

    second = telegram(user_id=2, first_name="Пётр")
    await second.send("/start")
    await second.press(second.buttons()["📅 Записаться"])
    await second.press(second.buttons()["Мужская стрижка · 1 500 ₽"])
    await second.press(second.buttons()["пн, 26 окт"])
    times = second.buttons()
    assert "10:00" not in times and "10:30" not in times  # 10:30 would overlap the 10:00–11:00 haircut
    assert "11:00" in times


async def test_race_for_the_same_time_offers_another(telegram):
    a, b = telegram(user_id=1), telegram(user_id=2, first_name="Пётр")
    await book_haircut(a)
    await book_haircut(b)  # both are on the confirmation screen for 10:00
    await a.press(a.buttons()["✅ Подтвердить"])
    await b.press(b.buttons()["✅ Подтвердить"])
    assert "это время заняли" in b.last.text
    assert "11:00" in b.buttons()


async def test_phone_is_validated(telegram):
    chat = telegram()
    await chat.send("/start")
    await chat.press(chat.buttons()["📅 Записаться"])
    await chat.press(chat.buttons()["Оформление бороды · 900 ₽"])
    await chat.press(chat.buttons()["пн, 26 окт"])
    await chat.press(chat.buttons()["10:00"])
    await chat.send("Иван")
    await chat.send("не скажу")
    assert "Не похоже на номер" in chat.last.text
    await chat.share_contact("+79001112233", user_id=555)  # someone else's contact
    assert "свой номер" in chat.last.text
    await chat.share_contact("79001112233")
    assert "Проверьте запись" in chat.last.text and "+79001112233" in chat.last.text


async def test_my_bookings_and_cancel(telegram, store, biz):
    chat = telegram()
    await book_haircut(chat)
    await chat.press(chat.buttons()["✅ Подтвердить"])
    await chat.press(chat.buttons()["🗂 Мои записи"])
    assert "пн, 26 окт в 10:00 — Мужская стрижка" in chat.last.text
    await chat.press(chat.buttons()["Отменить: пн, 26 окт в 10:00"])
    assert "Запись отменена" in chat.alerts()
    assert "нет предстоящих записей" in chat.last.text
    assert any("отменил" in m for m in chat.sent_to(ADMIN_ID))


async def test_declining_creates_nothing(telegram, store, biz):
    chat = telegram()
    await book_haircut(chat)
    await chat.press(chat.buttons()["Отмена"])
    assert "запись не создана" in chat.last.text
    assert store.upcoming_for_user(1, datetime(2026, 10, 26, 9, tzinfo=biz.tz)) == []


async def test_admin_schedule_is_admin_only(telegram):
    client = telegram()
    await book_haircut(client)
    await client.press(client.buttons()["✅ Подтвердить"])
    calls = len(client.screens())
    await client.send("/today")
    assert len(client.screens()) == calls  # silently ignored for clients
    admin = telegram(user_id=ADMIN_ID, first_name="Админ")
    await admin.send("/today")
    assert "Сегодня: 1" in admin.last.text and "Иван, +79001234567" in admin.last.text


async def test_reminder_is_sent_once(telegram, store, biz, clock):
    chat = telegram()
    await book_haircut(chat, time_label="12:00")
    await chat.press(chat.buttons()["✅ Подтвердить"])
    clock.now = datetime(2026, 10, 26, 8, 30, tzinfo=biz.tz)
    assert await reminders.send_due(telegram.bot, biz, store, clock) == 0  # 3.5 h before: too early
    clock.now = datetime(2026, 10, 26, 9, 30, tzinfo=biz.tz)
    assert await reminders.send_due(telegram.bot, biz, store, clock) == 1
    assert await reminders.send_due(telegram.bot, biz, store, clock) == 0
    assert any("Напоминаем" in m for m in chat.sent_to(1))


async def test_unknown_text_points_to_start(telegram):
    chat = telegram()
    await chat.send("привет")
    assert "/start" in chat.last.text
