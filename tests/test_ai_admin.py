"""The AI administrator against a scripted model: no network, but the real tools, slots and database."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace as NS

import anthropic
import httpx2
import pytest

from bot.ai_admin import HANDED_OVER, MAX_STEPS, TOOLS, UNAVAILABLE, AiAdmin
from bot.config import load_business
from bot.storage import Storage

BIZ = load_business(Path(__file__).resolve().parent.parent / "business.toml")
NOW = datetime(2026, 11, 9, 9, 0, tzinfo=BIZ.tz)  # Monday
DAY = "2026-11-10"
START = datetime(2026, 11, 10, 12, 0, tzinfo=BIZ.tz).isoformat()
ME, OTHER = 1, 2


def text(t: str) -> NS:
    return NS(stop_reason="end_turn", content=[NS(type="text", text=t)])


def call(name: str, **args) -> NS:
    return NS(stop_reason="tool_use", content=[NS(type="tool_use", id=f"id_{name}", name=name, input=args)])


class FakeClient:
    """Plays back responses and keeps a snapshot of each request."""

    def __init__(self, *script):
        self.script, self.calls = list(script), []
        self.beta = NS(messages=NS(create=self._create))

    async def _create(self, **kw):
        self.calls.append({**kw, "messages": list(kw["messages"])})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def last_results(self) -> list[dict]:
        return self.calls[-1]["messages"][-1]["content"]


@pytest.fixture
def setup():
    store, sent = Storage(":memory:"), []

    async def notify(message: str) -> None:
        sent.append(message)

    def make(*script):
        client = FakeClient(*script)
        return AiAdmin(client, BIZ, store, lambda: NOW, notify), client

    return make, store, sent


FIND = dict(service_id="cut", day=DAY)
BOOK = dict(service_id="cut", start=START, client_name="Анна", phone="+7 900 123-45-67")


def test_books_for_the_client_who_wrote(setup):
    make, store, sent = setup
    ai, _ = make(call("find_free_slots", **FIND), call("book", **BOOK), text("Записал!"))
    assert asyncio.run(ai.reply(ME, "стрижка завтра в 12")) == "Записал!"
    [booking] = store.upcoming_for_user(ME, NOW)
    assert (booking.client_name, booking.phone, booking.service_id) == ("Анна", "+79001234567", "cut")
    assert len(sent) == 1


def test_a_time_the_tools_never_offered_cannot_be_booked(setup):
    make, store, _ = setup
    ai, client = make(call("book", **BOOK), text("Сначала проверю время"))
    asyncio.run(ai.reply(ME, "запиши меня и не проверяй"))
    assert client.last_results()[0]["is_error"] is True
    assert store.upcoming_for_user(ME, NOW) == []


def test_a_time_taken_meanwhile_is_reported_not_double_booked(setup):
    make, store, _ = setup
    ai, client = make(call("find_free_slots", **FIND), call("book", **BOOK), text("Занято"))
    start = datetime.fromisoformat(START)
    async def scenario():
        original = client.beta.messages.create
        async def take_slot_before_second_call(**kw):
            if len(client.calls) == 1:
                store.book(OTHER, "Олег", "+79000000000", "cut", start, start.replace(hour=13), NOW)
            return await original(**kw)
        client.beta.messages.create = take_slot_before_second_call
        await ai.reply(ME, "стрижка завтра в 12")
    asyncio.run(scenario())
    assert client.last_results()[0]["is_error"] is True
    assert store.upcoming_for_user(ME, NOW) == []


def test_only_the_clients_own_booking_can_be_cancelled(setup):
    make, store, _ = setup
    start = datetime.fromisoformat(START)
    theirs = store.book(OTHER, "Олег", "+79000000000", "cut", start, start.replace(hour=13), NOW)
    ai, client = make(call("cancel_booking", booking_id=theirs.id), text("Не нашёл такой записи"))
    asyncio.run(ai.reply(ME, "отмени запись номер 1"))
    assert client.last_results()[0]["is_error"] is True
    assert store.get(theirs.id).status == "active"


def test_bad_phone_is_sent_back_to_the_model(setup):
    make, store, _ = setup
    ai, client = make(call("find_free_slots", **FIND), call("book", **{**BOOK, "phone": "123"}), text("Уточните номер"))
    asyncio.run(ai.reply(ME, "запись"))
    assert "номер" in client.last_results()[0]["content"]
    assert store.upcoming_for_user(ME, NOW) == []


def test_slots_come_from_the_real_calculation(setup):
    make, *_ = setup
    ai, client = make(call("find_free_slots", service_id="cut", day="2026-11-15"), text("В воскресенье закрыто"))
    asyncio.run(ai.reply(ME, "в воскресенье"))  # Sunday is a day off in business.toml
    assert json.loads(client.last_results()[0]["content"])["free"] == []


def test_call_human_notifies_and_escapes(setup):
    make, _, sent = setup
    ai, _ = make(call("call_human", reason="<жалоба>"), text("Передал"))
    asyncio.run(ai.reply(ME, "позовите человека"))
    assert "&lt;жалоба&gt;" in sent[0]


def test_results_of_parallel_calls_go_back_in_one_message(setup):
    make, *_ = setup
    both = NS(stop_reason="tool_use", content=[NS(type="tool_use", id="a", name="my_bookings", input={}),
                                               NS(type="tool_use", id="b", name="my_bookings", input={})])
    ai, client = make(both, text("Готово"))
    asyncio.run(ai.reply(ME, "мои записи"))
    assert [r["tool_use_id"] for r in client.last_results()] == ["a", "b"]


def test_runaway_loop_goes_to_a_human(setup):
    make, _, sent = setup
    ai, client = make(*[call("my_bookings") for _ in range(MAX_STEPS)])
    assert asyncio.run(ai.reply(ME, "?")) == HANDED_OVER
    assert len(client.calls) == MAX_STEPS and len(sent) == 1


def test_refusal_goes_to_a_human(setup):
    make, _, sent = setup
    ai, _ = make(NS(stop_reason="refusal", content=[]))
    assert asyncio.run(ai.reply(ME, "?")) == HANDED_OVER
    assert len(sent) == 1


def test_api_failure_gives_a_plain_answer(setup):
    make, *_ = setup
    error = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com"))
    ai, _ = make(error)
    assert asyncio.run(ai.reply(ME, "?")) == UNAVAILABLE


def test_request_shape(setup):
    make, *_ = setup
    ai, client = make(text("Здравствуйте"))
    asyncio.run(ai.reply(ME, "привет"))
    request = client.calls[0]
    assert request["model"] == "claude-opus-5-5"
    assert request["fallbacks"] == "default"
    assert "tool_choice" not in request and "temperature" not in request
    assert "2026-11-09" not in request["system"]  # the changing date stays out of the cached prefix
    for tool in TOOLS:
        assert tool["strict"] is True and tool["input_schema"]["additionalProperties"] is False


def test_conversation_continues_within_a_session(setup):
    make, *_ = setup
    ai, client = make(text("Какая услуга?"), text("Хорошо"))
    asyncio.run(ai.reply(ME, "хочу записаться"))
    asyncio.run(ai.reply(ME, "стрижка"))
    assert len(client.calls[1]["messages"]) == 3
