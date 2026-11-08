import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { SCENARIOS, buildScenario } from './ai-script.js';
import { freeSlots } from './slots.js';

const biz = JSON.parse(readFileSync(new URL('./business.json', import.meta.url), 'utf8'));
const combo = biz.services.find((s) => s.id === 'combo');
const dates = [new Date(2026, 10, 9, 9), new Date(2026, 10, 13, 21), new Date(2026, 10, 14, 12), new Date(2026, 10, 15, 12)];

test('every scenario has client and bot lines', () => {
  for (const { id } of SCENARIOS) {
    const whos = buildScenario(id, biz, dates[0]).map((s) => s.who);
    assert.ok(whos.includes('client') && whos.includes('bot'), id);
  }
});

test('the times the demo offers are really free, at any moment of the week', () => {
  for (const now of dates) {
    const steps = buildScenario('book', biz, now);
    const [, dd, mm, yyyy, times] = steps[1].text.match(/(\d\d)\.(\d\d)\.(\d{4})\) → (.+)$/);
    const day = new Date(+yyyy, +mm - 1, +dd);
    const free = freeSlots(biz, day, combo.minutes, [], now).map((t) => t.toTimeString().slice(0, 5));
    for (const t of times.split(', ')) assert.ok(free.includes(t), `${t} on ${day}`);
    assert.ok(times.split(', ').every((t) => t >= '18:00'));
  }
});

test('the admin hears about a booking and about a question the bot cannot answer', () => {
  assert.ok(buildScenario('book', biz, dates[0]).some((s) => s.who === 'admin' && s.text.includes('Новая запись')));
  assert.ok(buildScenario('unknown', biz, dates[0]).some((s) => s.who === 'admin'));
});
