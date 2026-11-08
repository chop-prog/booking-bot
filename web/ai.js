// Plays the scripted conversations from ai-script.js.
import { SCENARIOS, buildScenario } from './ai-script.js';

const chat = document.getElementById('chat');
const admin = document.getElementById('admin');
const bar = document.getElementById('scenarios');
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
const wait = (ms) => new Promise((r) => setTimeout(r, reduced ? 0 : ms));
let biz;
let run = 0; // a newer scenario makes the older one stop

function bubble(parent, cls, text) {
  const m = document.createElement('div');
  m.className = cls;
  m.textContent = text;
  parent.append(m);
  chat.scrollTop = chat.scrollHeight;
  return m;
}

async function play(id) {
  const mine = ++run;
  chat.replaceChildren();
  admin.replaceChildren();
  for (const b of bar.children) b.setAttribute('aria-pressed', String(b.dataset.id === id));
  for (const step of buildScenario(id, biz, new Date())) {
    if (step.who === 'bot') {
      const typing = bubble(chat, 'msg typing', 'печатает…');
      await wait(900);
      typing.remove();
      if (mine !== run) return;
    } else {
      await wait(step.who === 'client' ? 700 : 450);
      if (mine !== run) return;
    }
    if (step.who === 'admin') bubble(admin, 'msg', step.text);
    else bubble(chat, { client: 'msg me', bot: 'msg', tool: 'tool' }[step.who], step.text);
  }
}

biz = await (await fetch('business.json')).json();
document.getElementById('biz-name').textContent = biz.name;
for (const s of SCENARIOS) {
  const b = document.createElement('button');
  b.type = 'button';
  b.dataset.id = s.id;
  b.textContent = s.title;
  b.addEventListener('click', () => play(s.id));
  bar.append(b);
}
play('book');
