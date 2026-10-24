"""Draw the README cover from a real run of the bot.

Runs the booking flow through the same fake Telegram the tests use, records what the client typed and
what the bot answered, and lays three moments of it out as Telegram-like chat screens in assets/cover.html.
Nothing in the picture is typed by hand: change a text in bot/ui.py and the cover changes with it.

    python tools/render_demo.py      # then screenshot assets/cover.html
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from aiogram import Bot  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402

import conftest  # noqa: E402
from bot.config import load_business  # noqa: E402
from bot.storage import Storage  # noqa: E402


class Recorder:
    """Wraps a TelegramChat and keeps a transcript: ('me', text) and ('bot', html, buttons)."""

    def __init__(self, chat):
        self.chat, self.log, self._seen = chat, [], 0

    def _collect(self):
        screens = self.chat.screens()
        for s in screens[self._seen:]:
            markup = s.reply_markup
            rows = [[b.text for b in row] for row in getattr(markup, "inline_keyboard", [])]
            if not rows and getattr(markup, "keyboard", None):
                rows = [[b.text for b in row] for row in markup.keyboard]
            self.log.append(("bot", s.text, rows))
        self._seen = len(screens)

    async def send(self, text):
        self.log.append(("me", text, []))
        await self.chat.send(text)
        self._collect()

    async def press(self, label):
        await self.chat.press(self.chat.buttons()[label])
        self._collect()


async def record() -> tuple[list, list]:
    biz = load_business(ROOT / "business.toml")
    store = Storage(":memory:")
    clock = conftest.Clock(datetime(2026, 10, 26, 9, 0, tzinfo=biz.tz))
    session = conftest.FakeSession()
    bot = Bot("42:DEMO", session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = conftest._dp
    dp.fsm.storage = MemoryStorage()
    dp.workflow_data.update(biz=biz, store=store, admins=frozenset({conftest.ADMIN_ID}), clock=clock)
    # Someone already booked 12:00, so the time grid shows a gap like a real day would.
    store.book(7, "Олег", "+79000000000", "cut", datetime(2026, 10, 26, 12, tzinfo=biz.tz),
               datetime(2026, 10, 26, 13, tzinfo=biz.tz), clock())
    client = Recorder(conftest.TelegramChat(dp, bot, session, user_id=1, first_name="Анна"))
    await client.send("/start")
    await client.press("📅 Записаться")
    await client.press("Стрижка + борода · 2 200 ₽")
    await client.press("пн, 26 окт")
    await client.press("13:00")
    await client.send("Анна")
    await client.send("+7 900 123-45-67")
    await client.press("✅ Подтвердить")
    admin = [("bot", text, []) for text in conftest.TelegramChat(dp, bot, session, user_id=conftest.ADMIN_ID).sent_to(conftest.ADMIN_ID)]
    return client.log, admin


def bubble(entry) -> str:
    who, text, rows = entry
    body = escape(text) if who == "me" else text
    html = f'<div class="msg {who}">{body.replace(chr(10), "<br>")}</div>'
    if rows and who == "bot":
        html += '<div class="kb">' + "".join(
            '<div class="row">' + "".join(f"<span>{escape(b)}</span>" for b in row) + "</div>" for row in rows) + "</div>"
    return html


def screen(title: str, entries: list) -> str:
    return f"""<section class="phone"><header><b>{title}</b><small>бот</small></header>
<div class="chat">{"".join(bubble(e) for e in entries)}</div></section>"""


def page(log: list, admin: list) -> str:
    bot_msgs = [e for e in log if e[0] == "bot"]
    first = [log[0], bot_msgs[0], bot_msgs[1]]                       # /start → menu → services
    times = [bot_msgs[3]]                                           # the time grid with 12:00 taken
    done = [bot_msgs[-3], bot_msgs[-1]]                             # summary, then «Готово»
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Бот записи клиентов</title>
<style>
* {{ box-sizing: border-box; }}
body {{ margin: 0; width: 1440px; height: 900px; background: linear-gradient(135deg, #17212b, #0e1621 60%, #1b2836);
  font: 15px/1.4 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: #e9eef3; display: flex; flex-direction: column; padding: 46px 56px; }}
h1 {{ margin: 0 0 6px; font-size: 40px; letter-spacing: -0.02em; }}
p.lead {{ margin: 0 0 28px; color: #8ea3b6; font-size: 19px; }}
.row3 {{ display: flex; gap: 28px; flex: 1; min-height: 0; }}
.phone {{ flex: 1; background: #0e1621; border: 1px solid #243447; border-radius: 22px; overflow: hidden; display: flex; flex-direction: column; }}
.phone header {{ background: #17212b; padding: 14px 18px; display: flex; flex-direction: column; border-bottom: 1px solid #243447; }}
.phone header small {{ color: #6c8aa5; }}
.chat {{ padding: 16px; display: flex; flex-direction: column; gap: 8px; overflow: hidden; justify-content: flex-end; flex: 1; }}
.msg {{ max-width: 88%; padding: 9px 13px; border-radius: 14px; background: #182533; align-self: flex-start; }}
.msg.me {{ background: #2b5278; align-self: flex-end; }}
.kb {{ display: flex; flex-direction: column; gap: 5px; max-width: 88%; }}
.kb .row {{ display: flex; gap: 5px; }}
.kb span {{ flex: 1; text-align: center; background: rgba(90, 140, 190, .22); border-radius: 9px; padding: 7px 6px; font-size: 13.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.admin {{ margin-top: auto; border-top: 1px dashed #2f4256; padding-top: 10px; color: #8ea3b6; font-size: 13px; }}
</style></head><body>
<h1>Telegram-бот для записи клиентов</h1>
<p class="lead">Свободное время считается само · напоминания · уведомления администратору · Python, aiogram, SQLite</p>
<div class="row3">
{screen("Барбершоп «Бритва»", first)}
{screen("Выбор времени", times)}
{screen("Запись готова", done)}
</div></body></html>"""


def main() -> None:
    log, admin = asyncio.run(record())
    out = ROOT / "assets" / "cover.html"
    out.parent.mkdir(exist_ok=True)
    html = page(log, admin)
    # The admin notification goes under the last screen.
    note = "".join(f'<div class="msg">{t.replace(chr(10), "<br>")}</div>' for _, t, _ in admin)
    html = html.replace('</div></section>\n</div></body>', f'<div class="admin">Администратору приходит:</div>{note}</div></section>\n</div></body>', 1)
    out.write_text(html, encoding="utf-8")
    print("wrote", out.relative_to(ROOT), "from", len(log), "steps")


if __name__ == "__main__":
    main()
