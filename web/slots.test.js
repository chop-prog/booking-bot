// The browser demo must follow the same rules as the bot: these mirror tests/test_logic.py.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { freeSlots, bookableDays, overlaps, normalizePhone } from './slots.js';

const biz = JSON.parse(readFileSync(new URL('./business.json', import.meta.url), 'utf8'));
const MONDAY = new Date(2026, 9, 26);
const at = (h, m = 0, day = MONDAY) => new Date(day.getFullYear(), day.getMonth(), day.getDate(), h, m);
const hhmm = (d) => d.toTimeString().slice(0, 5);

test('half-open intervals do not clash at the boundary', () => {
  assert.equal(overlaps(at(10), at(11), at(11), at(12)), false);
  assert.equal(overlaps(at(10), at(11, 30), at(11), at(12)), true);
});

test('slots fit before closing', () => {
  const slots = freeSlots(biz, MONDAY, 90, [], at(6));
  assert.equal(hhmm(slots[0]), '10:00');
  assert.equal(hhmm(slots.at(-1)), '18:30');
  assert.equal(slots.length, 18);
});

test('busy time is skipped', () => {
  const slots = freeSlots(biz, MONDAY, 60, [[at(12), at(13)]], at(6)).map(hhmm);
  assert.ok(slots.includes('11:00'));
  assert.ok(!slots.includes('11:30'));
  assert.ok(!slots.includes('12:30'));
  assert.ok(slots.includes('13:00'));
});

test('lead time is respected', () => {
  assert.equal(hhmm(freeSlots(biz, MONDAY, 30, [], at(14, 10))[0]), '15:30');
});

test('closed days are not offered', () => {
  const sunday = new Date(2026, 10, 1); // the Sunday after MONDAY
  assert.equal(freeSlots(biz, sunday, 30, [], at(6)).length, 0);
  assert.equal(bookableDays(biz, at(9)).length, 6);
});

test('phones are normalised like in the bot', () => {
  assert.equal(normalizePhone('+7 900 123-45-67'), '+79001234567');
  assert.equal(normalizePhone('89001234567'), '+79001234567');
  assert.equal(normalizePhone('+7 (495) 123-45-67'), null);
  assert.equal(normalizePhone('123'), null);
});
