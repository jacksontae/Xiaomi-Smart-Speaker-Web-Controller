// Info tips: a small (i) button that opens a short guide in an anchored panel. Hover opens it on a mouse
// (and it stays open while the pointer is over the button or the panel); click/tap/Enter pins it open and moves
// focus in. Esc, the close button, a tap outside or tabbing out closes it. One tip is open at a time.
// ui.js tip() is a plain label (pointer-events: none) and sheet.js popover() grabs focus on open, so neither fits
// a hover guide with a copy button inside. Styles: css/infotip.css (loaded on first use).
import { h, icon } from './ui.js';
import { register, t } from './i18n.js';

register({
  en: { 'tip.copy': 'Copy', 'tip.copied': 'Copied', 'tip.copyFail': 'Couldn\'t copy. Select the text and copy it.' },
  th: { 'tip.copy': 'คัดลอก', 'tip.copied': 'คัดลอกแล้ว', 'tip.copyFail': 'คัดลอกไม่ได้ เลือกข้อความแล้วคัดลอกเอง' },
});

const HOVER_IN = 120;
const HOVER_OUT = 240;
const GAP = 8;
const EDGE = 16;
const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]):not([type=hidden]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

let cssDone = false;
let seq = 0;
let cur = null; // { btn, panel, pinned, off() }
let inTimer = 0;
let outTimer = 0;

function ensureCss() {
  if (cssDone) return;
  cssDone = true;
  document.head.append(h('link', { rel: 'stylesheet', href: '/static/css/infotip.css' }));
}

/**
 * infoTip({ label, title, build(body) }) -> <button>. `label` is the button's aria-label, `title` the panel heading;
 * build fills the panel body each time it opens (so it can read live values such as location.origin).
 */
export function infoTip({ label, title, build, cls = '' }) {
  ensureCss();
  const btn = h('button', {
    type: 'button', class: `iconbtn infotip-btn ${cls}`.trim(), 'aria-label': label, 'aria-expanded': 'false', 'aria-haspopup': 'dialog',
  }, icon('info', 'sm'));
  const isOpen = () => !!cur && cur.btn === btn;
  btn.addEventListener('pointerenter', (e) => {
    if (e.pointerType !== 'mouse') return;
    clearTimeout(outTimer);
    if (!isOpen()) { clearTimeout(inTimer); inTimer = setTimeout(() => open(btn, title, build, false), HOVER_IN); }
  });
  btn.addEventListener('pointerleave', (e) => { if (e.pointerType === 'mouse') { clearTimeout(inTimer); hoverClose(); } });
  btn.addEventListener('click', () => {
    clearTimeout(inTimer);
    if (isOpen() && cur.pinned) closeTip(false);
    else if (isOpen()) pin();
    else open(btn, title, build, true);
  });
  btn.addEventListener('keydown', (e) => {
    // Tab from the button goes into the open panel (it lives at the end of <body>)
    if (e.key === 'Tab' && !e.shiftKey && isOpen()) { e.preventDefault(); pin(); firstIn(cur.panel).focus(); }
  });
  return btn;
}

function hoverClose() {
  clearTimeout(outTimer);
  outTimer = setTimeout(() => { if (cur && !cur.pinned) closeTip(false); }, HOVER_OUT);
}

function pin() {
  if (!cur) return;
  cur.pinned = true;
  cur.panel.classList.add('pinned');
  if (!cur.panel.contains(document.activeElement)) cur.panel.focus({ preventScroll: true });
}

const focusables = (root) => [...root.querySelectorAll(FOCUSABLE)].filter((el) => el.offsetParent !== null || el === document.activeElement);
const firstIn = (panel) => focusables(panel)[0] || panel;

function open(btn, title, build, pinned) {
  closeTip(false);
  const id = `itp${++seq}`;
  const closeBtn = h('button', { type: 'button', class: 'iconbtn infotip-x', 'aria-label': t('common.close'), onclick: () => closeTip(true) }, icon('close', 'xs'));
  const body = h('div', { class: 'infotip-body' });
  const panel = h('div', { class: 'infotip-pop', id, role: 'dialog', 'aria-labelledby': `${id}-t`, tabindex: '-1' },
    h('div', { class: 'infotip-head' }, h('h3', { id: `${id}-t` }, title), closeBtn), body);
  build(body);
  document.body.append(panel);
  btn.setAttribute('aria-expanded', 'true');
  btn.setAttribute('aria-controls', id);
  place(btn, panel);

  let raf = 0;
  const reflow = () => {
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => {
      if (!btn.isConnected) { closeTip(false); return; }
      const r = btn.getBoundingClientRect();
      if (r.bottom < 0 || r.top > innerHeight) closeTip(false); else place(btn, panel);
    });
  };
  const onDown = (e) => { if (!panel.contains(e.target) && !btn.contains(e.target)) closeTip(false); };
  const onKey = (e) => {
    if (e.key !== 'Escape') return;
    e.preventDefault();
    e.stopPropagation();
    const inside = panel.contains(document.activeElement) || document.activeElement === btn;
    closeTip(inside);
  };
  const onPanelKey = (e) => {
    if (e.key !== 'Tab') return;
    const list = focusables(panel);
    const first = list[0], last = list[list.length - 1];
    const a = document.activeElement;
    if (e.shiftKey && (a === panel || a === first)) { e.preventDefault(); closeTip(true); }
    else if (!e.shiftKey && (a === last || !list.length)) { e.preventDefault(); closeTip(false); focusAfter(btn); }
  };
  const onFocusOut = (e) => {
    const to = e.relatedTarget;
    if (to && !panel.contains(to) && to !== btn && cur && cur.pinned) closeTip(false);
  };
  const onEnter = () => clearTimeout(outTimer);
  const onLeave = (e) => { if (e.pointerType === 'mouse' && cur && !cur.pinned) hoverClose(); };
  panel.addEventListener('keydown', onPanelKey);
  panel.addEventListener('focusout', onFocusOut);
  panel.addEventListener('pointerenter', onEnter);
  panel.addEventListener('pointerleave', onLeave);
  // a click inside a hover-opened panel (e.g. Copy) keeps it open after the pointer leaves
  panel.addEventListener('pointerdown', () => { if (cur && !cur.pinned) { cur.pinned = true; panel.classList.add('pinned'); } });
  // armed a tick later (not by the opening tap); skipped if closed in between, else the listener would leak
  setTimeout(() => { if (cur && cur.panel === panel) document.addEventListener('pointerdown', onDown, true); });
  document.addEventListener('keydown', onKey, true);
  addEventListener('scroll', reflow, true);
  addEventListener('resize', reflow);
  addEventListener('hashchange', closeTipNow);
  cur = {
    btn, panel, pinned: false,
    off() {
      cancelAnimationFrame(raf);
      document.removeEventListener('pointerdown', onDown, true);
      document.removeEventListener('keydown', onKey, true);
      removeEventListener('scroll', reflow, true);
      removeEventListener('resize', reflow);
      removeEventListener('hashchange', closeTipNow);
    },
  };
  if (pinned) pin();
}

const closeTipNow = () => closeTip(false);

/** Close the open info tip; refocus moves focus back to its button. */
export function closeTip(refocus = false) {
  clearTimeout(outTimer);
  if (!cur) return;
  const { btn, panel, off } = cur;
  cur = null;
  off();
  btn.setAttribute('aria-expanded', 'false');
  btn.removeAttribute('aria-controls');
  panel.remove();
  if (refocus && btn.isConnected) btn.focus({ preventScroll: true });
}

/** Below the button (above when there's more room there), clamped to the viewport with a 16px gutter. */
function place(btn, panel) {
  const r = btn.getBoundingClientRect();
  const below = innerHeight - r.bottom - GAP - EDGE;
  const above = r.top - GAP - EDGE;
  const up = below < 220 && above > below;
  panel.style.maxHeight = `${Math.max(160, up ? above : below)}px`;
  const w = panel.offsetWidth, ht = panel.offsetHeight;
  const left = Math.max(EDGE, Math.min(r.left + r.width / 2 - 28, innerWidth - w - EDGE));
  panel.style.left = `${left}px`;
  panel.style.top = `${up ? r.top - GAP - ht : r.bottom + GAP}px`;
  panel.classList.toggle('up', up);
}

/** Focus the next focusable element after `el` in page order (skips the panel, which sits at the end). */
function focusAfter(el) {
  const list = focusables(document.body);
  const i = list.indexOf(el);
  (list[i + 1] || el).focus({ preventScroll: false });
}

/* ---------- copy ---------- */
/**
 * Copy text to the clipboard. The async Clipboard API needs a secure context (https or localhost); on a plain
 * http LAN address fall back to a hidden textarea + execCommand. Returns true when it worked.
 */
export async function copyText(text, host = document.body) {
  if (navigator.clipboard && window.isSecureContext) {
    try { await navigator.clipboard.writeText(text); return true; } catch { /* fall through */ }
  }
  const ta = h('textarea', { class: 'sr-only', readonly: true, 'aria-hidden': 'true', tabindex: '-1' });
  ta.value = text;
  host.append(ta);
  ta.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch { ok = false; }
  ta.remove();
  return ok;
}

/** A value in monospace with a Copy button that says "Copied" for a moment. */
export function copyRow(text, note) {
  const live = h('span', { class: 'sr-only', 'aria-live': 'polite' });
  const code = h('code', { class: 'infotip-code' }, text);
  const label = h('span', {}, t('tip.copy'));
  let timer = 0;
  const btn = h('button', { type: 'button', class: 'infotip-copybtn', 'aria-label': `${t('tip.copy')} ${text}` }, icon('check', 'xs'), label);
  btn.addEventListener('click', async () => {
    const ok = await copyText(text, btn.parentElement);
    clearTimeout(timer);
    btn.classList.toggle('done', ok);
    label.textContent = ok ? t('tip.copied') : t('tip.copy');
    live.textContent = ok ? t('tip.copied') : t('tip.copyFail');
    if (!ok) getSelection().selectAllChildren(code);
    timer = setTimeout(() => { btn.classList.remove('done'); label.textContent = t('tip.copy'); live.textContent = ''; }, 1800);
  });
  return h('div', { class: 'infotip-copy' }, h('div', { class: 'infotip-copyline' }, code, btn), note ? h('span', { class: 'infotip-note' }, note) : null, live);
}
