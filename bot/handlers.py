"""The conversation: menu, booking step by step, «my bookings», and admin commands.

Dependencies come from the Dispatcher (see __main__.py): biz, store, admins and clock. Tests pass fakes
the same way, so the whole flow runs without Telegram.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from . import ui
from .config import Business
from .slots import bookable_days, free_slots
from .storage import SlotTaken, Storage

log = logging.getLogger(__name__)
router = Router()
Clock = Callable[[], datetime]


class Booking(StatesGroup):
    name = State()
    phone = State()
    confirm = State()


def day_slots(biz: Business, store: Storage, service_id: str, day: date, now: datetime) -> list[datetime]:
    start = datetime.combine(day, datetime.min.time(), biz.tz)
    busy = store.busy(start, start + timedelta(days=1))
    return free_slots(biz, day, biz.services[service_id].minutes, busy, now)


async def notify_admins(bot: Bot, admins: frozenset[int], text: str) -> None:
    for chat_id in admins:
        try:
            await bot.send_message(chat_id, text)
        except TelegramAPIError as e:  # an admin who blocked the bot must not break a client's booking
            log.warning("cannot notify admin %s: %s", chat_id, e)


# ---------- menu ----------

@router.message(CommandStart())
async def start(message: Message, state: FSMContext, biz: Business) -> None:
    await state.clear()
    await message.answer(ui.welcome(biz, message.from_user.first_name), reply_markup=ui.main_menu())


@router.callback_query(ui.Menu.filter(F.action == "home"))
async def home(cb: CallbackQuery, state: FSMContext, biz: Business) -> None:
    await state.clear()
    await cb.message.edit_text(ui.welcome(biz, cb.from_user.first_name), reply_markup=ui.main_menu())
    await cb.answer()


@router.callback_query(ui.Menu.filter(F.action.in_({"prices", "faq", "contacts"})))
async def info(cb: CallbackQuery, callback_data: ui.Menu, biz: Business) -> None:
    text = {"prices": ui.prices, "faq": ui.faq, "contacts": ui.contacts}[callback_data.action](biz)
    await cb.message.edit_text(text, reply_markup=ui.back_home())
    await cb.answer()


# ---------- booking ----------

@router.callback_query(ui.Menu.filter(F.action == "book"))
async def choose_service(cb: CallbackQuery, state: FSMContext, biz: Business) -> None:
    await state.clear()
    await cb.message.edit_text("Выберите услугу:", reply_markup=ui.services_kb(biz))
    await cb.answer()


@router.callback_query(ui.PickService.filter())
async def choose_day(cb: CallbackQuery, callback_data: ui.PickService, biz: Business, store: Storage,
                     clock: Clock) -> None:
    service = biz.services.get(callback_data.service)
    if service is None:  # a button from before the price list changed
        await cb.answer("Эта услуга больше недоступна", show_alert=True)
        return
    now = clock()
    days = [d for d in bookable_days(biz, now) if day_slots(biz, store, service.id, d, now)]
    if not days:
        await cb.message.edit_text(f"На ближайшие {biz.days_ahead} дн. свободного времени нет 😔",
                                   reply_markup=ui.back_home())
    else:
        await cb.message.edit_text(f"<b>{service.name}</b> · {ui.rub(service.price)}\nВыберите день:",
                                   reply_markup=ui.days_kb(service.id, days))
    await cb.answer()


@router.callback_query(ui.PickDay.filter())
async def choose_time(cb: CallbackQuery, callback_data: ui.PickDay, biz: Business, store: Storage,
                      clock: Clock) -> None:
    service = biz.services.get(callback_data.service)
    if service is None:
        await cb.answer("Эта услуга больше недоступна", show_alert=True)
        return
    day = date.fromisoformat(callback_data.day)
    slots = day_slots(biz, store, service.id, day, clock())
    if not slots:
        await cb.answer("На этот день всё занято, выберите другой", show_alert=True)
        return
    await cb.message.edit_text(f"<b>{service.name}</b>, {ui.fmt_day(day)}\nВыберите время:",
                               reply_markup=ui.times_kb(biz, service.id, slots))
    await cb.answer()


@router.callback_query(ui.PickTime.filter())
async def ask_name(cb: CallbackQuery, callback_data: ui.PickTime, state: FSMContext, biz: Business,
                   store: Storage, clock: Clock) -> None:
    start = datetime.fromtimestamp(callback_data.ts, biz.tz)
    if callback_data.service not in biz.services or start not in day_slots(biz, store, callback_data.service, start.date(), clock()):
        await cb.answer("Это время уже недоступно, выберите другое", show_alert=True)
        return
    await state.set_state(Booking.name)
    await state.update_data(service=callback_data.service, ts=callback_data.ts)
    await cb.message.edit_text(f"Время: {ui.fmt_when(start, biz)}\n\nКак вас зовут?")
    await cb.answer()


@router.message(Booking.name, F.text)
async def ask_phone(message: Message, state: FSMContext) -> None:
    name = " ".join(message.text.split())
    if not 2 <= len(name) <= 50:
        await message.answer("Напишите имя, от 2 до 50 символов.")
        return
    await state.update_data(name=name)
    await state.set_state(Booking.phone)
    await message.answer("Отправьте номер телефона кнопкой ниже или напишите его, например +7 900 123-45-67.",
                         reply_markup=ui.phone_kb())


@router.message(Booking.phone)
async def ask_confirm(message: Message, state: FSMContext, biz: Business) -> None:
    if message.contact:
        if message.contact.user_id not in (None, message.from_user.id):
            await message.answer("Отправьте, пожалуйста, свой номер.")
            return
        phone = ui.normalize_phone(message.contact.phone_number)
    else:
        phone = ui.normalize_phone(message.text or "")
    if phone is None:
        await message.answer("Не похоже на номер мобильного. Пример: +7 900 123-45-67.")
        return
    await state.update_data(phone=phone)
    await state.set_state(Booking.confirm)
    data = await state.get_data()
    await message.answer("Номер получен ✓", reply_markup=ReplyKeyboardRemove())
    start = datetime.fromtimestamp(data["ts"], biz.tz)
    await message.answer(ui.summary(biz, data["service"], start, data["name"], phone), reply_markup=ui.confirm_kb())


@router.callback_query(ui.Confirm.filter(), Booking.confirm)
async def finish(cb: CallbackQuery, callback_data: ui.Confirm, state: FSMContext, bot: Bot, biz: Business,
                 store: Storage, admins: frozenset[int], clock: Clock) -> None:
    data = await state.get_data()
    await state.clear()
    if not callback_data.ok:
        await cb.message.edit_text("Хорошо, запись не создана.", reply_markup=ui.main_menu())
        await cb.answer()
        return
    service = biz.services.get(data["service"])
    start = datetime.fromtimestamp(data["ts"], biz.tz)
    now = clock()
    try:
        if service is None or start not in day_slots(biz, store, service.id, start.date(), now):
            raise SlotTaken
        booking = store.book(cb.from_user.id, data["name"], data["phone"], service.id,
                             start, start + timedelta(minutes=service.minutes), now)
    except SlotTaken:
        # Someone took the time while this client was typing their name: offer the times still free.
        slots = day_slots(biz, store, data["service"], start.date(), now) if service else []
        markup = ui.times_kb(biz, service.id, slots) if slots else ui.back_home()
        await cb.message.edit_text("Пока вы оформляли запись, это время заняли 😔 Выберите другое:", reply_markup=markup)
        await cb.answer()
        return
    await cb.message.edit_text(
        f"✅ Готово! Вы записаны: {ui.booking_line(booking, biz)}.\n{biz.address}\n\n"
        f"Напомним за {biz.remind_before_hours} ч.", reply_markup=ui.main_menu())
    await cb.answer("Записали!")
    await notify_admins(bot, admins, ui.admin_new(biz, booking))


@router.callback_query(ui.Confirm.filter())
async def stale_confirm(cb: CallbackQuery) -> None:
    await cb.answer("Эта запись уже оформлена или устарела. Начните заново: /start", show_alert=True)


# ---------- my bookings ----------

async def show_mine(cb: CallbackQuery, biz: Business, store: Storage, clock: Clock) -> None:
    mine = store.upcoming_for_user(cb.from_user.id, clock())
    if not mine:
        await cb.message.edit_text("У вас нет предстоящих записей.", reply_markup=ui.back_home())
        return
    lines = "\n".join(f"• {ui.booking_line(b, biz)}" for b in mine)
    await cb.message.edit_text(f"<b>Ваши записи</b>\n\n{lines}", reply_markup=ui.my_bookings_kb(mine, biz))


@router.callback_query(ui.Menu.filter(F.action == "mine"))
async def mine(cb: CallbackQuery, biz: Business, store: Storage, clock: Clock) -> None:
    await show_mine(cb, biz, store, clock)
    await cb.answer()


@router.callback_query(ui.CancelBooking.filter())
async def cancel(cb: CallbackQuery, callback_data: ui.CancelBooking, bot: Bot, biz: Business, store: Storage,
                 admins: frozenset[int], clock: Clock) -> None:
    booking = store.cancel(callback_data.id, user_id=cb.from_user.id)
    if booking is None:
        await cb.answer("Запись не найдена или уже отменена", show_alert=True)
    else:
        await cb.answer("Запись отменена")
        await notify_admins(bot, admins, ui.admin_cancelled(biz, booking))
    await show_mine(cb, biz, store, clock)


# ---------- admin ----------

@router.message(Command("today", "week"))
async def schedule(message: Message, biz: Business, store: Storage, admins: frozenset[int], clock: Clock) -> None:
    if message.from_user.id not in admins:
        return  # clients do not even learn the command exists
    now = clock().astimezone(biz.tz)
    start = datetime.combine(now.date(), datetime.min.time(), biz.tz)
    days = 1 if message.text.startswith("/today") else 7
    bookings = store.between(start, start + timedelta(days=days))
    if not bookings:
        await message.answer("Записей нет.")
        return
    lines = [f"#{b.id} {ui.booking_line(b, biz)}\n    {b.client_name}, {b.phone}" for b in bookings]
    title = "Сегодня" if days == 1 else "На 7 дней"
    await message.answer(f"<b>{title}: {len(bookings)}</b>\n\n" + "\n".join(lines))


@router.message()
async def fallback(message: Message) -> None:
    await message.answer("Нажмите /start, чтобы открыть меню.")
