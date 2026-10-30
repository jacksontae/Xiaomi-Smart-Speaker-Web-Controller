// First-run quick tour (boards Now / T_Now / D_Now): coach marks that spotlight the real controls on the Now page.
// Opens by itself once per signed-in user per device/app install (localStorage spk.tour.<userId> = TOUR_VERSION;
// bump TOUR_VERSION to show it again after a big change), and again from App settings or Help (replay()).
// Steps follow the screen (phone tab bar vs iPad/desktop sidebar) and the role; a step whose element isn't on
// screen is left out. Only Skip, Esc or Done close it: taps outside the card do nothing.
//
//   app.js:   import('./tour.js').then((m) => m.maybeStart({ user }))   after the shell is mounted
//   views:    import('../tour.js').then((m) => m.replay({ user: ctx.user }))
import { h } from './ui.js';
import { register, t } from './i18n.js';
import { api } from './api.js';
import { isPhone } from './sheet.js';
import { RANK } from './routes.js';

export const TOUR_VERSION = 1;
const KEY = 'spk.tour.';
const WAIT_MS = 400;     // how often we look for "Now page shown, nothing else open"
const SETTLE_MS = 1200;  // quiet time first, so the passkey offer (opened ~1 s after sign-in) goes first
const PAD = 6;           // spotlight padding around the element
const GAP = 14;          // space between the spotlight and the card

register({
  en: {
    'tour.label': 'Quick tour', 'tour.count': (i, n) => `${i} of ${n}`,
    'tour.back': 'Back', 'tour.next': 'Next', 'tour.skip': 'Skip', 'tour.done': 'Done',
    'tour.tabsT': 'Your pages', 'tour.tabsB': 'Switch pages here. The highlighted tab is the one you’re on.',
    'tour.navT': 'Your pages', 'tour.navB': 'Every page is in this list. The highlighted one is where you are.',
    'tour.navAdminB': 'Every page is in this list. Members, speaker settings and activity are in the lower group.',
    'tour.spkT': 'Your speaker',
    'tour.spkB': 'This is the speaker you’re controlling. If it says Offline next to the name, it can’t be reached, so nothing plays yet. Check its plug and Wi‑Fi first.',
    'tour.ctrlT': 'Play, pause and volume',
    'tour.ctrlB': 'The middle button pauses or resumes. The slider changes the volume on the speaker right away.',
    'tour.seeT': 'What’s playing',
    'tour.seeB': 'This page always shows what the speaker is playing, or that it’s quiet. The light on the speaker picture moves while it makes sound.',
    'tour.annT': 'Announce', 'tour.annB': 'Type a message and the speaker says it right away. Music pauses and picks up again afterwards.',
    'tour.annTalkT': 'Announce or talk live',
    'tour.annTalkB': 'Type a message for the speaker to read out, or pick Talk live and speak through it with your microphone.',
    'tour.musicT': 'Music', 'tour.musicB': 'Search YouTube, internet radio and podcasts, or play your own files.',
    'tour.meT': 'Account and help',
    'tour.meB': 'Tap your picture for your account, app settings and the help guide. You can replay this tour from there.',
    'tour.helpT': 'Help is here',
    'tour.helpB': 'Click ? for the help guide. Your name at the bottom of the menu opens your account and settings. You can replay this tour from Help.',
  },
  th: {
    'tour.label': 'ทัวร์แนะนำ', 'tour.count': (i, n) => `${i} จาก ${n}`,
    'tour.back': 'ย้อนกลับ', 'tour.next': 'ถัดไป', 'tour.skip': 'ข้าม', 'tour.done': 'เสร็จ',
    'tour.tabsT': 'หน้าต่าง ๆ', 'tour.tabsB': 'แตะเพื่อเปลี่ยนหน้า แท็บที่ไฮไลต์คือหน้าที่เปิดอยู่',
    'tour.navT': 'หน้าต่าง ๆ', 'tour.navB': 'ทุกหน้าอยู่ในรายการนี้ รายการที่ไฮไลต์คือหน้าที่เปิดอยู่',
    'tour.navAdminB': 'ทุกหน้าอยู่ในรายการนี้ สมาชิก ตั้งค่าลำโพง และกิจกรรม อยู่ในกลุ่มด้านล่าง',
    'tour.spkT': 'ลำโพงของคุณ',
    'tour.spkB': 'นี่คือลำโพงที่กำลังควบคุมอยู่ ถ้ามีคำว่าออฟไลน์ต่อท้ายชื่อ แปลว่าติดต่อลำโพงไม่ได้ สั่งไปก็ยังไม่มีเสียง ให้เช็กปลั๊กกับ Wi‑Fi ก่อน',
    'tour.ctrlT': 'เล่น พัก และปรับเสียง',
    'tour.ctrlB': 'ปุ่มกลางใช้พักหรือเล่นต่อ แถบเลื่อนปรับเสียงที่ลำโพงจริงทันที',
    'tour.seeT': 'กำลังเล่นอะไรอยู่',
    'tour.seeB': 'หน้านี้บอกเสมอว่าลำโพงกำลังเล่นอะไร หรือเงียบอยู่ ไฟบนรูปลำโพงจะวิ่งเมื่อมีเสียงออก',
    'tour.annT': 'ประกาศ', 'tour.annB': 'พิมพ์ข้อความแล้วลำโพงจะพูดทันที เพลงที่เล่นอยู่จะพักไว้ แล้วเล่นต่อเมื่อพูดจบ',
    'tour.annTalkT': 'ประกาศหรือพูดสด',
    'tour.annTalkB': 'พิมพ์ข้อความให้ลำโพงอ่าน หรือเลือก พูดสด แล้วพูดผ่านลำโพงด้วยไมโครโฟน',
    'tour.musicT': 'เพลง', 'tour.musicB': 'ค้นหาจาก YouTube วิทยุออนไลน์ และพอดแคสต์ หรือเล่นไฟล์ของคุณเอง',
    'tour.meT': 'บัญชีและคู่มือ',
    'tour.meB': 'แตะรูปโปรไฟล์เพื่อดูบัญชี ตั้งค่าแอป และคู่มือการใช้งาน เปิดทัวร์นี้อีกครั้งได้จากตรงนั้น',
    'tour.helpT': 'คู่มืออยู่ตรงนี้',
    'tour.helpB': 'คลิก ? เพื่อเปิดคู่มือ ชื่อของคุณด้านล่างเมนูใช้เปิดบัญชีและการตั้งค่า เปิดทัวร์นี้อีกครั้งได้จากคู่มือ',
  },
});

const $ = (sel) => document.querySelector(sel);
/** The element when it is on screen with a size (hidden / display:none elements don't count). */
const shown = (sel) => { const el = $(sel); return el && el.getClientRects().length && el.offsetWidth ? el : null; };
const nowShown = () => !!$('#view .now-page') && !$('#view .page-loading');
const blocked = () => !!$('dialog[open], .popover');

/* ---------- storage ---------- */
const keyOf = (user) => KEY + (user.id != null ? user.id : user.username);
/** True when this device can remember the tour (private modes may refuse writes). */
function storable() {
  try { localStorage.setItem(`${KEY}probe`, '1'); localStorage.removeItem(`${KEY}probe`); return true; } catch { return false; }
}
function seen(user) {
  try { return Number(localStorage.getItem(keyOf(user))) >= TOUR_VERSION; } catch { return true; }
}
function markSeen(user) { try { localStorage.setItem(keyOf(user), String(TOUR_VERSION)); } catch { /* not remembered */ } }

/* ---------- steps ---------- */
// sel: candidates, first one on screen wins. min: lowest role that sees it. text(el, info) -> [title, body] keys.
const ctrlText = (op) => (op && shown('.np-ctrls .np-transport, .np-ctrls .np-volume') ? ['tour.ctrlT', 'tour.ctrlB'] : ['tour.seeT', 'tour.seeB']);
const PHONE = [
  { id: 'tabs', sel: ['.tabbar'], text: () => ['tour.tabsT', 'tour.tabsB'] },
  { id: 'now', sel: ['.np-hero'], pick: (op) => (op && shown('.np-ctrls .np-transport, .np-ctrls .np-volume') ? '.np-ctrls' : '.np-hero'), text: (info) => ctrlText(info.op) },
  { id: 'announce', min: 'operator', sel: ['.tabbar [data-route="announce"]'], text: () => ['tour.annT', 'tour.annB'] },
  { id: 'music', min: 'operator', sel: ['.tabbar [data-route="music"]'], text: () => ['tour.musicT', 'tour.musicB'] },
  { id: 'account', sel: ['.me-btn'], text: () => ['tour.meT', 'tour.meB'] },
];
const LARGE = [
  { id: 'nav', sel: ['.sb'], text: (info) => ['tour.navT', info.admin ? 'tour.navAdminB' : 'tour.navB'] },
  { id: 'speaker', sel: ['#view .phd-r [data-spk="chip"]', '.sb-spk'], text: () => ['tour.spkT', 'tour.spkB'] },
  { id: 'now', sel: ['.np-col'], text: (info) => ctrlText(info.op) },
  { id: 'announce', min: 'operator', sel: ['.sbn [data-route="announce"]'], text: (info) => (info.talk ? ['tour.annTalkT', 'tour.annTalkB'] : ['tour.annT', 'tour.annB']) },
  { id: 'help', sel: ['#view .phd-r .help-btn', '.uchip'], text: () => ['tour.helpT', 'tour.helpB'] },
];
const targetOf = (step, info) => {
  if (step.pick) { const el = shown(step.pick(info.op)); if (el) return el; }
  for (const s of step.sel) { const el = shown(s); if (el) return el; }
  return null;
};

/* ---------- start / wait ---------- */
let lastUser = null;
let waiter = 0;
let tour = null; // the open tour

/** app.js, after the shell is mounted for a signed-in user: open the tour once, when the Now page is up. */
export function maybeStart({ user }) {
  lastUser = user;
  if (tour) { tour.user = user; tour.rebuilt(); return; } // language change rebuilt the shell under the tour
  if (!user || !storable() || seen(user)) return;
  waitForNow(user, false);
}

/** "Show quick tour again" (App settings, Help): go to Now and start at step 1. */
export function replay({ user } = {}) {
  const u = user || lastUser;
  if (!u) return;
  if (tour) tour.close(false);
  if (!/^#\/?$/.test(location.hash || '#/')) location.hash = '#/';
  waitForNow(u, true);
}

function waitForNow(user, forced) {
  clearTimeout(waiter);
  let quietSince = 0;
  const tick = () => {
    if (lastUser !== user || !$('.shell')) return; // signed out / someone else signed in
    if (tour) return;
    if (!forced && seen(user)) return;
    const ok = nowShown() && !blocked() && document.visibilityState === 'visible';
    if (!ok) quietSince = 0;
    else if (!quietSince) quietSince = Date.now();
    if (ok && Date.now() - quietSince >= (forced ? 0 : SETTLE_MS)) { open(user); return; }
    waiter = setTimeout(tick, WAIT_MS);
  };
  waiter = setTimeout(tick, forced ? 60 : WAIT_MS);
}

/* ---------- the tour ---------- */
let cssReady = null;
function loadCss() {
  if (!cssReady) {
    cssReady = new Promise((resolve) => {
      const l = h('link', { rel: 'stylesheet', href: new URL('../css/tour.css', import.meta.url).href });
      l.addEventListener('load', resolve);
      l.addEventListener('error', resolve);
      document.head.append(l);
    });
  }
  return cssReady;
}

async function open(user) {
  const info = { op: RANK[user.role] >= RANK.operator, admin: RANK[user.role] >= RANK.admin, talk: false };
  const phone = isPhone();
  const [, talk] = await Promise.all([loadCss(), info.op && !phone ? api('/talk/status').then((s) => !!(s && s.available), () => false) : false]);
  info.talk = talk;
  if (tour || lastUser !== user || !nowShown()) return;
  const steps = (phone ? PHONE : LARGE).filter((s) => (!s.min || RANK[user.role] >= RANK[s.min]) && targetOf(s, info));
  if (!steps.length) return;
  build(user, info, steps); // sets `tour`
}

function build(user, info, steps) {
  const appEl = document.getElementById('app');
  const opener = document.activeElement;
  let i = 0;
  let target = null;
  let raf = 0;

  const block = h('div', { class: 'tour-block' }); // swallows taps outside the card: only Skip/Esc/Done close
  const ring = h('div', { class: 'tour-ring', 'aria-hidden': 'true' });
  const arrow = h('span', { class: 'tour-arrow', 'aria-hidden': 'true' });
  const count = h('p', { class: 'tour-count' });
  const title = h('h2', { class: 'tour-title', id: 'tour-title' });
  const body = h('p', { class: 'tour-body', id: 'tour-body' });
  const dots = h('div', { class: 'tour-dots', 'aria-hidden': 'true' }, steps.map(() => h('span', { class: 'tour-dot' })));
  const skipB = h('button', { type: 'button', class: 'tour-skip', onclick: () => close(true) });
  const backB = h('button', { type: 'button', class: 'btn tour-back', onclick: () => go(i - 1, -1) });
  const nextB = h('button', { type: 'button', class: 'btn primary tour-next', onclick: () => (i === steps.length - 1 ? close(true) : go(i + 1, 1)) });
  const card = h('div', { class: 'tour-card', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'tour-title', 'aria-describedby': 'tour-body', tabindex: '-1' },
    arrow, h('div', { class: 'tour-text', 'aria-live': 'polite', 'aria-atomic': 'true' }, count, title, body),
    h('div', { class: 'tour-foot' }, dots, h('span', { class: 'tour-gap' }), skipB, backB, nextB));
  const root = h('div', { class: 'tour', dataset: { step: '' } }, block, ring, card);
  document.body.append(root);
  if (appEl) appEl.inert = true;

  function labels() {
    card.setAttribute('aria-label', t('tour.label'));
    skipB.textContent = t('tour.skip');
    backB.textContent = t('tour.back');
  }

  /** Show step n (dir: which way to look when its element has gone: 1 forward, -1 back). */
  function go(n, dir = 1) {
    for (let k = n; k >= 0 && k < steps.length; k += dir) {
      const el = targetOf(steps[k], info);
      if (el) { i = k; target = el; return paint(true); }
    }
    if (dir > 0) close(true); // nothing left to show
    else if (target && target.isConnected) paint(true);
  }

  function paint(focus) {
    labels();
    const step = steps[i];
    const [tk, bk] = step.text(info);
    root.dataset.step = step.id;
    count.textContent = t('tour.count', i + 1, steps.length);
    title.textContent = t(tk);
    body.textContent = t(bk);
    [...dots.children].forEach((d, k) => d.classList.toggle('on', k === i));
    backB.hidden = i === 0;
    nextB.textContent = t(i === steps.length - 1 ? 'tour.done' : 'tour.next');
    if (focus) reveal();
    place();
    if (focus) card.focus({ preventScroll: true });
  }

  /** Scroll the page so the element sits in view (instant: no animated moves). */
  function reveal() {
    const r = target.getBoundingClientRect();
    if (r.top < 80 || r.bottom > innerHeight - 120) target.scrollIntoView({ block: 'center', behavior: 'instant' });
  }

  function place() {
    if (tour !== api0) return;
    if (!target || !target.isConnected || !target.getClientRects().length) {
      const el = targetOf(steps[i], info);
      if (!el) return go(i + 1, 1);
      target = el;
    }
    const W = document.documentElement.clientWidth, H = innerHeight;
    const r = target.getBoundingClientRect();
    const pad = steps[i].id === 'nav' || steps[i].id === 'now' ? PAD + 2 : PAD;
    // spotlight, kept inside the window
    const x = Math.max(2, r.left - pad), y = Math.max(2, r.top - pad);
    const w = Math.min(W - 2, r.right + pad) - x, hh = Math.min(H - 2, r.bottom + pad) - y;
    const rad = parseFloat(getComputedStyle(target).borderTopLeftRadius) || 0;
    Object.assign(ring.style, { left: `${x}px`, top: `${y}px`, width: `${w}px`, height: `${hh}px`, borderRadius: `${Math.min(rad + pad, Math.min(w, hh) / 2)}px` });
    // card: below, above, right or left of the spotlight, whichever fits first; else pinned to the bottom
    const cw = Math.min(340, W - 32);
    card.style.width = `${cw}px`;
    const ch = card.offsetHeight;
    const cx = x + w / 2, cy = y + hh / 2;
    const clampX = (v) => Math.max(16, Math.min(W - 16 - cw, v));
    const clampY = (v) => Math.max(16, Math.min(H - 16 - ch, v));
    let side, left, top;
    if (y + hh + GAP + ch <= H - 16) { side = 'below'; left = clampX(cx - cw / 2); top = y + hh + GAP; }
    else if (y - GAP - ch >= 16) { side = 'above'; left = clampX(cx - cw / 2); top = y - GAP - ch; }
    else if (x + w + GAP + cw <= W - 16) { side = 'right'; left = x + w + GAP; top = clampY(cy - ch / 2); }
    else if (x - GAP - cw >= 16) { side = 'left'; left = x - GAP - cw; top = clampY(cy - ch / 2); }
    else { side = 'over'; left = clampX(cx - cw / 2); top = H - 16 - ch; }
    Object.assign(card.style, { left: `${left}px`, top: `${top}px` });
    card.dataset.side = side;
    arrow.hidden = side === 'over';
    const ax = Math.max(18, Math.min(cw - 32, cx - left - 7));
    const ay = Math.max(18, Math.min(ch - 32, cy - top - 7));
    Object.assign(arrow.style, side === 'below' || side === 'above' ? { left: `${ax}px`, top: '' } : { top: `${ay}px`, left: '' });
  }
  const later = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => (tour ? place() : null)); };

  /* pause while a sheet/dialog is open (passkey offer), close when signed out or the page changes */
  let paused = false;
  const watch = setInterval(() => {
    if (!$('.shell')) return close(false);
    const b = blocked();
    if (b !== paused) {
      paused = b;
      root.hidden = b;
      if (!b) { paint(false); card.focus({ preventScroll: true }); }
    }
    if (!b) later();
  }, 500);

  function onKey(e) {
    if (paused) return;
    if (e.key === 'Escape') { e.preventDefault(); close(true); return; }
    if (e.key === 'ArrowRight') { e.preventDefault(); nextB.click(); return; }
    if (e.key === 'ArrowLeft') { e.preventDefault(); if (i > 0) go(i - 1, -1); return; }
    if (e.key === 'Tab') { // keep focus in the card
      const f = [...card.querySelectorAll('button')].filter((b) => !b.hidden);
      const at = f.indexOf(document.activeElement);
      e.preventDefault();
      const n = at < 0 ? (e.shiftKey ? f.length - 1 : 0) : (at + (e.shiftKey ? -1 : 1) + f.length) % f.length;
      f[n].focus();
    }
  }
  const onFocus = (e) => { if (!paused && !card.contains(e.target)) card.focus({ preventScroll: true }); };
  const onHash = () => { if (!/^#\/?$/.test(location.hash || '#/')) close(true); };
  const ro = new ResizeObserver(later);
  ro.observe(document.documentElement);
  document.addEventListener('keydown', onKey, true);
  document.addEventListener('focusin', onFocus, true);
  window.addEventListener('resize', later);
  window.addEventListener('scroll', later, { passive: true });
  window.addEventListener('hashchange', onHash);
  if (window.visualViewport) visualViewport.addEventListener('resize', later);

  function close(remember) {
    if (tour !== api0) return;
    tour = null;
    if (remember) markSeen(user);
    clearInterval(watch);
    cancelAnimationFrame(raf);
    ro.disconnect();
    document.removeEventListener('keydown', onKey, true);
    document.removeEventListener('focusin', onFocus, true);
    window.removeEventListener('resize', later);
    window.removeEventListener('scroll', later);
    window.removeEventListener('hashchange', onHash);
    if (window.visualViewport) visualViewport.removeEventListener('resize', later);
    if (appEl) appEl.inert = false;
    root.remove();
    const back = opener && opener.isConnected && opener !== document.body ? opener : document.getElementById('view');
    if (back) back.focus({ preventScroll: true });
  }

  const api0 = {
    user, close,
    /** The shell was rebuilt (language change): find the elements again and redo the text. */
    rebuilt() { target = null; setTimeout(() => { if (tour === api0 && nowShown()) paint(true); }, 300); },
  };
  tour = api0;
  go(0, 1);
  return api0;
}
