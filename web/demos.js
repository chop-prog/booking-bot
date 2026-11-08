// Personal demos: ?b=<slug> shows the bot with one business's services and hours from demos.json.
import { WEEKDAYS } from './slots.js';

export const DEMO_NOTICE = (name) => `Пример для ${name}. Это не официальный сервис заведения: записи никуда не отправляются. Услуги и часы взяты из открытых каталогов, цены и длительность могут отличаться.`;

/** The entry for a slug, or null. Own properties only, so ?b=constructor finds nothing. */
export function findDemo(demos, slug) {
  return slug && Object.hasOwn(demos, slug) ? demos[slug] : null;
}

/** The base config with one business's details on top. `daily` fills every weekday, `hours` overrides single days. */
export function demoConfig(base, entry) {
  const hours = Object.fromEntries(WEEKDAYS.map((d) => [d, entry.daily]));
  return {
    ...base,
    name: entry.name,
    address: entry.address,
    contacts: 'Телефон и мессенджеры подставим ваши',
    services: entry.services,
    faq: [
      { q: 'Как отменить или перенести запись?', a: 'Откройте «Мои записи» и нажмите «Отменить». Потом запишитесь на новое время.' },
      { q: 'Бот напомнит о записи?', a: `Да, за ${base.remind_before_hours} ч до визита.` },
    ],
    hours: { ...hours, ...entry.hours },
  };
}
