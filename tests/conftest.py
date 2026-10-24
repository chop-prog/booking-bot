"""Shared fixtures: the demo business config, an in-memory database, a frozen clock, and a fake Telegram."""

from __future__ import annotations

from datetime import datetime
from itertools import count
from pathlib import Path

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage, TelegramMethod
from aiogram.types import CallbackQuery, Chat, Contact, Message, Update, User

from bot.config import load_business
from bot.handlers import router
from bot.storage import Storage

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def biz():
    return load_business(ROOT / "business.toml")


@pytest.fixture
def store():
    return Storage(":memory:")


class Clock:
    """A clock tests can move: `clock.now = ...`."""

    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock(biz):
    return Clock(datetime(2026, 10, 26, 9, 0, tzinfo=biz.tz))  # Monday 09:00, before opening


class FakeSession(BaseSession):
    """Records every Bot API call instead of sending it, and answers like Telegram would."""

    def __init__(self):
        super().__init__()
        self.calls: list[TelegramMethod] = []
        self._ids = count(100)

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, (SendMessage, EditMessageText)):
            chat_id = getattr(method, "chat_id", None) or 1
            return Message(message_id=next(self._ids), date=datetime.now(), text=method.text,
                           chat=Chat(id=chat_id, type="private"))
        if isinstance(method, AnswerCallbackQuery):
            return True
        return True

    async def close(self):
        pass

    async def stream_content(self, *args, **kwargs):
        raise NotImplementedError
        yield b""


class TelegramChat:
    """Drives the bot like one client would: types messages, presses buttons, reads replies."""

    def __init__(self, dp: Dispatcher, bot: Bot, session: FakeSession, user_id: int = 1, first_name: str = "Иван"):
        self.dp, self.bot, self.session = dp, bot, session
        self.user = User(id=user_id, is_bot=False, first_name=first_name)
        self.chat = Chat(id=user_id, type="private")
        self._ids = count(1)

    def _message(self, **fields) -> Message:
        return Message(message_id=next(self._ids), date=datetime.now(), chat=self.chat, from_user=self.user, **fields)

    async def send(self, text: str) -> None:
        await self.dp.feed_update(self.bot, Update(update_id=next(self._ids), message=self._message(text=text)))

    async def share_contact(self, phone: str, user_id: int | None = None) -> None:
        contact = Contact(phone_number=phone, first_name=self.user.first_name,
                          user_id=self.user.id if user_id is None else user_id)
        await self.dp.feed_update(self.bot, Update(update_id=next(self._ids), message=self._message(contact=contact)))

    async def press(self, data: str) -> None:
        cb = CallbackQuery(id=str(next(self._ids)), from_user=self.user, chat_instance="test", data=data,
                           message=self._message(text="…"))
        await self.dp.feed_update(self.bot, Update(update_id=next(self._ids), callback_query=cb))

    # --- reading what the bot did ---

    def screens(self) -> list[TelegramMethod]:
        """What this client saw: messages sent or edited in their own chat."""
        return [c for c in self.session.calls
                if isinstance(c, (SendMessage, EditMessageText)) and c.chat_id == self.chat.id]

    @property
    def last(self) -> SendMessage | EditMessageText:
        return self.screens()[-1]

    def buttons(self) -> dict[str, str]:
        """Inline buttons of the last screen: text → callback data."""
        markup = self.last.reply_markup
        return {b.text: b.callback_data for row in getattr(markup, "inline_keyboard", []) for b in row}

    def alerts(self) -> list[str]:
        return [c.text for c in self.session.calls if isinstance(c, AnswerCallbackQuery) and c.text]

    def sent_to(self, chat_id: int) -> list[str]:
        return [c.text for c in self.session.calls if isinstance(c, SendMessage) and c.chat_id == chat_id]


ADMIN_ID = 999


# The router is a module-level singleton and can join only one Dispatcher, so tests share one
# and get fresh dependencies and a fresh FSM storage each time.
_dp = Dispatcher()
_dp.include_router(router)


@pytest.fixture
def telegram(biz, store, clock):
    session = FakeSession()
    bot = Bot("42:TEST", session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = _dp
    dp.fsm.storage = MemoryStorage()
    dp.workflow_data.update(biz=biz, store=store, admins=frozenset({ADMIN_ID}), clock=clock)

    def chat(user_id: int = 1, first_name: str = "Иван") -> TelegramChat:
        return TelegramChat(dp, bot, session, user_id, first_name)

    chat.session = session
    chat.bot = bot
    return chat
