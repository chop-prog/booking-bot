"""Run the bot: ``python -m bot`` with BOT_TOKEN (and optionally ADMIN_IDS) set."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from . import reminders
from .config import load_business, load_secrets
from .handlers import router
from .storage import Storage

ROOT = Path(__file__).resolve().parent.parent


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    biz = load_business(Path(os.environ.get("BUSINESS_FILE", ROOT / "business.toml")))
    secrets = load_secrets()
    store = Storage(secrets.db_path)

    def clock() -> datetime:
        return datetime.now(biz.tz)

    bot = Bot(secrets.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage(), biz=biz, store=store, admins=secrets.admin_ids, clock=clock)
    dp.include_router(router)
    await bot.set_my_commands([BotCommand(command="start", description="Меню и запись")])
    reminder_task = asyncio.create_task(reminders.run(bot, biz, store, clock))  # keep a reference: tasks are weak
    logging.info("%s: bot started, admins: %s", biz.name, sorted(secrets.admin_ids) or "none")
    try:
        await dp.start_polling(bot)
    finally:
        reminder_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
