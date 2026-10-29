// Free time slots for the browser demo: the same rules as bot/slots.py, in local time.
// Kept free of DOM code so node:test can check it against the same cases as the Python tests.

export const WEEKDAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];

const toMinutes = (hhmm) => {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
};

/** Monday-based weekday index (0 = Monday), like Python's date.weekday(). */
export const weekday = (date) => (date.getDay() + 6) % 7;

/** Half-open intervals: a booking ending at 11:00 does not clash with one starting at 11:00. */
export const overlaps = (aStart, aEnd, bStart, bEnd) => aStart < bEnd && bStart < aEnd;

/**
 * Start times (Date) on `day` where a service of `minutes` fits before closing,
 * starts no earlier than now + lead time, and clashes with nothing in `busy` ([start, end] Dates).
 */
export function freeSlots(biz, day, minutes, busy, now) {
  const span = biz.hours[WEEKDAYS[weekday(day)]];
  if (!span || span.length === 0) return [];
  const base = new Date(day.getFullYear(), day.getMonth(), day.getDate());
  const at = (mins) => new Date(base.getTime() + mins * 60_000);
  const open = toMinutes(span[0]);
  const close = toMinutes(span[1]);
  const earliest = new Date(now.getTime() + biz.min_lead_minutes * 60_000);
  const out = [];
  for (let t = open; t + minutes <= close; t += biz.step_minutes) {
    const start = at(t);
    const end = at(t + minutes);
    if (start >= earliest && !busy.some(([b0, b1]) => overlaps(start, end, b0, b1))) out.push(start);
  }
  return out;
}

/** Today and the next days_ahead − 1 days, skipping days the business is closed. */
export function bookableDays(biz, now) {
  const days = [];
  for (let i = 0; i < biz.days_ahead; i++) {
    const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + i);
    const span = biz.hours[WEEKDAYS[weekday(d)]];
    if (span && span.length) days.push(d);
  }
  return days;
}

/** A Russian mobile in +7XXXXXXXXXX form, or null — same rule as bot/ui.py. */
export function normalizePhone(text) {
  let digits = String(text).replace(/\D/g, '');
  if (digits.length === 11 && '78'.includes(digits[0])) digits = digits.slice(1);
  return digits.length === 10 && digits[0] === '9' ? '+7' + digits : null;
}
