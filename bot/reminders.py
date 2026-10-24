"""Background task: remind clients a few hours before their visit."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from . import ui
from .config import Business
from .handlers import Clock
from .storage import Storage

log = logging.getLogger(__name__)


async def send_due(bot: Bot, biz: Business, store: Storage, clock: Clock) -> int:
    """Send every reminder that is due now; each booking is reminded once. Returns how many were sent."""
    sent = 0
    for b in store.due_reminders(clock(), biz.remind_before_hours):
        try:
            await bot.send_message(b.user_id, ui.reminder(biz, b))
            sent += 1
        except TelegramAPIError as e:  # the client blocked the bot: nothing to retry
            log.warning("reminder for booking %s failed: %s", b.id, e)
        store.mark_reminded(b.id)
    return sent


async def run(bot: Bot, biz: Business, store: Storage, clock: Clock, every: float = 60) -> None:
    while True:
        try:
            await send_due(bot, biz, store, clock)
        except Exception:  # never let one bad minute stop reminders for good
            log.exception("reminder loop")
        await asyncio.sleep(every)
