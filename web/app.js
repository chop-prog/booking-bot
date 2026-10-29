// Browser demo of the booking bot: the same menu, steps and texts, with bookings kept in memory.
import { bookableDays, freeSlots, normalizePhone } from './slots.js';

const WEEKDAYS_SHORT = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];
const MONTHS = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const chat = document.getElementById('chat');
const admin = document.getElementById('admin');
const composer = document.getElementById('composer');
const input = document.getElementById('input');

const rub = (n) => n.toLocaleString('ru-RU') + ' ₽';
const fmtDay = (d) => `${WEEKDAYS_SHORT[(d.getDay() + 6) % 7]}, ${d.getDate()} ${MONTHS[d.getMonth()]}`;
const hhmm = (d) => d.toTimeString().slice(0, 5);

let biz;
const bookings = []; // {service, start, end, name, phone}
let draft = null; // the booking being filled in
let waitingFor = null; // 'name' | 'phone' | null

function say(text, buttons = [], who = 'bot') {
  const m = document.createElement('div');
  m.className = 'msg' + (who === 'me' ? ' me' : '');
  m.textContent = text;
  chat.append(m);
  if (buttons.length) {
    const kb = document.createElement('div');
    kb.className = 'kb';
    for (const row of buttons) {
      const r = document.createElement('div');
      r.style.display = 'grid';
      r.style.gridTemplateColumns = `repeat(${row.length}, 1fr)`;
      r.style.gap = '5px';
      for (const [label, action] of row) {
        const b = document.createElement('button');
        b.type = 'button';
        b.textContent = label;
        b.addEventListener('click', () => {
          kb.querySelectorAll('button').forEach((x) => (x.disabled = true));
          say(label, [], 'me');
          action();
        });
        r.append(b);
      }
      kb.append(r);
    }
    chat.append(kb);
  }
  chat.scrollTop = chat.scrollHeight;
}

function notifyAdmin(text) {
  admin.querySelector('.muted')?.remove();
  const m = document.createElement('div');
  m.className = 'msg';
  m.textContent = text;
  admin.prepend(m);
}

const busyOn = (day) => bookings
  .filter((b) => b.start.toDateString() === day.toDateString())
  .map((b) => [b.start, b.end]);

function menu() {
  waitingFor = null;
  composer.hidden = true;
  say(`Здравствуйте! Это бот ${biz.name}.\nЗдесь можно записаться, посмотреть цены и свои записи.`, [
    [['📅 Записаться', chooseService]],
    [['💈 Услуги и цены', prices], ['🗂 Мои записи', mine]],
    [['❓ Вопросы', faq], ['📍 Контакты', contacts]],
  ]);
}

const back = [['← В меню', menu]];

function prices() {
  say('Услуги и цены\n\n' + biz.services.map((s) => `• ${s.name} — ${rub(s.price)} (${s.minutes} мин)`).join('\n'), [back]);
}
function faq() { say(biz.faq.map((f) => `${f.q}\n${f.a}`).join('\n\n'), [back]); }
function contacts() { say(`${biz.name}\n${biz.address}\n${biz.contacts}`, [back]); }

function mine() {
  const now = new Date();
  const list = bookings.filter((b) => b.start > now);
  if (!list.length) return say('У вас нет предстоящих записей.', [back]);
  say('Ваши записи\n\n' + list.map((b) => `• ${fmtDay(b.start)} в ${hhmm(b.start)} — ${b.service.name}`).join('\n'), [
    ...list.map((b) => [[`Отменить: ${fmtDay(b.start)} в ${hhmm(b.start)}`, () => cancel(b)]]),
    back,
  ]);
}

function cancel(b) {
  bookings.splice(bookings.indexOf(b), 1);
  notifyAdmin(`❌ Клиент отменил запись\n${fmtDay(b.start)} в ${hhmm(b.start)} — ${b.service.name}\n${b.name}, ${b.phone}`);
  say('Запись отменена.', [back]);
}

function chooseService() {
  say('Выберите услугу:', [...biz.services.map((s) => [[`${s.name} · ${rub(s.price)}`, () => chooseDay(s)]]), back]);
}

function chooseDay(service) {
  const now = new Date();
  const days = bookableDays(biz, now).filter((d) => freeSlots(biz, d, service.minutes, busyOn(d), now).length);
  if (!days.length) return say(`На ближайшие ${biz.days_ahead} дн. свободного времени нет`, [back]);
  const rows = [];
  for (let i = 0; i < days.length; i += 3) rows.push(days.slice(i, i + 3).map((d) => [fmtDay(d), () => chooseTime(service, d)]));
  say(`${service.name} · ${rub(service.price)}\nВыберите день:`, [...rows, [['← Услуги', chooseService]]]);
}

function chooseTime(service, day) {
  const slots = freeSlots(biz, day, service.minutes, busyOn(day), new Date());
  const rows = [];
  for (let i = 0; i < slots.length; i += 4) rows.push(slots.slice(i, i + 4).map((t) => [hhmm(t), () => askName(service, t)]));
  say(`${service.name}, ${fmtDay(day)}\nВыберите время:`, [...rows, [['← Дни', () => chooseDay(service)]]]);
}

function askName(service, start) {
  draft = { service, start, end: new Date(start.getTime() + service.minutes * 60_000) };
  waitingFor = 'name';
  composer.hidden = false;
  input.placeholder = 'Ваше имя';
  input.focus();
  say(`Время: ${fmtDay(start)} в ${hhmm(start)}\n\nКак вас зовут?`);
}

composer.addEventListener('submit', (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  say(text, [], 'me');
  if (waitingFor === 'name') {
    if (text.length < 2 || text.length > 50) return say('Напишите имя, от 2 до 50 символов.');
    draft.name = text;
    waitingFor = 'phone';
    input.placeholder = '+7 900 123-45-67';
    say('Напишите номер телефона, например +7 900 123-45-67.');
  } else if (waitingFor === 'phone') {
    const phone = normalizePhone(text);
    if (!phone) return say('Не похоже на номер мобильного. Пример: +7 900 123-45-67.');
    draft.phone = phone;
    waitingFor = null;
    composer.hidden = true;
    const s = draft.service;
    say(`Проверьте запись\n\nУслуга: ${s.name}\nКогда: ${fmtDay(draft.start)} в ${hhmm(draft.start)}\nДлительность: ${s.minutes} мин\nСтоимость: ${rub(s.price)}\nИмя: ${draft.name}\nТелефон: ${phone}`,
      [[['✅ Подтвердить', confirm], ['Отмена', () => { draft = null; say('Хорошо, запись не создана.', [back]); }]]]);
  }
});

function confirm() {
  const b = draft;
  draft = null;
  // The same guard as the bot's database transaction: the slot may have been taken meanwhile.
  if (!freeSlots(biz, b.start, b.service.minutes, busyOn(b.start), new Date()).some((t) => t.getTime() === b.start.getTime())) {
    return say('Пока вы оформляли запись, это время заняли. Выберите другое:', [[['Выбрать время', () => chooseTime(b.service, b.start)]]]);
  }
  bookings.push(b);
  notifyAdmin(`🆕 Новая запись\n${fmtDay(b.start)} в ${hhmm(b.start)} — ${b.service.name}\n${b.name}, ${b.phone}`);
  say(`✅ Готово! Вы записаны: ${fmtDay(b.start)} в ${hhmm(b.start)} — ${b.service.name}.\n${biz.address}\n\nНапомним за ${biz.remind_before_hours} ч.`, [back]);
}

async function start() {
  biz = await (await fetch('business.json')).json();
  document.getElementById('biz-name').textContent = biz.name;
  // One booking already exists, so the time grid shows a real gap like a working day would.
  const now = new Date();
  const day = bookableDays(biz, now).find((d) => freeSlots(biz, d, 60, [], now).length > 4);
  if (day) {
    const [first, , , , fifth] = freeSlots(biz, day, 60, [], now);
    const s = fifth || first;
    bookings.push({ service: biz.services[0], start: s, end: new Date(s.getTime() + 3_600_000), name: 'Олег', phone: '+79000000000' });
  }
  menu();
}

start();
