// Small DOM toolkit shared by every view: element builder, icons, fields, buttons, toasts, tooltips, help links,
// segmented control. Sheets/dialogs/popovers live in sheet.js. No framework: views build DOM with h().
import { t } from './i18n.js';
import { motionReduced } from './prefs.js';

/**
 * h('button', { class: 'btn', onclick, 'aria-label': 'x' }, child, [children], 'text')
 * Props: class, style (object), dataset (object), on* (listener), DOM properties, else attributes.
 */
export function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k in el && typeof el[k] !== 'function' && !k.includes('-')) el[k] = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  append(el, kids);
  return el;
}
export function append(el, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k == null || k === false) continue;
    el.append(k instanceof Node ? k : String(k));
  }
  return el;
}

/** <svg class="icon"> using a symbol from the sprite in index.html (#i-<name>). */
export function icon(name, cls = '') {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', `icon ${cls}`.trim());
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', `#i-${name}`);
  svg.append(use);
  return svg;
}

/** Icon-only button: always has an aria-label and a tooltip with the same text. */
export function iconBtn(name, label, onclick, cls = '') {
  const b = h('button', { type: 'button', class: `iconbtn ${cls}`.trim(), 'aria-label': label, onclick }, icon(name));
  tip(b, label);
  return b;
}

// Thai leading vowels (เ แ โ ใ ไ) are written before the consonant; skip them so the avatar shows a real letter.
export const initial = (name) => ((name || '?').trim().replace(/^[เ-ไ]+/, '').charAt(0) || '?').toUpperCase();
export const avatar = (user, cls = '') => h('span', { class: `avatar ${cls}`.trim(), 'aria-hidden': 'true' }, initial(user && user.display_name));

/* ---------- fields ---------- */
let fieldSeq = 0;
/** Label + control + optional hint (described-by). Returns the wrapper; the control keeps its own reference. */
export function field(labelText, control, hint) {
  const input = control.matches('input,textarea,select') ? control : control.querySelector('input,textarea,select');
  const id = input.id || `f${++fieldSeq}`;
  input.id = id;
  const hintEl = hint != null ? h('span', { class: 'hint', id: `${id}-hint` }, hint) : null;
  if (hintEl) input.setAttribute('aria-describedby', hintEl.id);
  return h('div', { class: 'field' }, h('label', { for: id }, labelText), control, hintEl);
}

/** Password input with a show/hide eye button. Returns { wrap, input }. */
export function passwordInput(props = {}) {
  const input = h('input', { class: 'input', type: 'password', spellcheck: false, autocapitalize: 'none', ...props });
  const eye = h('button', { type: 'button', class: 'iconbtn eye', 'aria-pressed': 'false', 'aria-label': t('common.showPw') }, icon('eye'));
  eye.addEventListener('click', () => {
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    eye.setAttribute('aria-pressed', String(show));
    eye.setAttribute('aria-label', t(show ? 'common.hidePw' : 'common.showPw'));
    eye.replaceChildren(icon(show ? 'eye-off' : 'eye'));
  });
  return { wrap: h('span', { class: 'pw' }, input, eye), input };
}

/** Run an async action with a busy button (disabled + spinner + aria-busy). Rethrows. */
export async function busy(btn, fn) {
  if (btn) { btn.classList.add('busy'); btn.disabled = true; btn.setAttribute('aria-busy', 'true'); }
  try { return await fn(); } finally { if (btn) { btn.classList.remove('busy'); btn.disabled = false; btn.removeAttribute('aria-busy'); } }
}

/* ---------- toast ---------- */
const TOAST_MAX = 3;
/**
 * toast('Announced', 'ok') — use when the effect happens elsewhere (on the speaker) or a page changes under you.
 * kind: 'info' | 'ok' | 'err'. action: { label, run } adds one button (e.g. Undo).
 * Every toast goes away by itself (2-10 s), on a tap, or when newer ones push it out (TOAST_MAX on screen).
 * While a sheet is open the toast host moves into that <dialog> (the modal top layer would otherwise cover it,
 * dimmed and untappable); sheet.js moves it back to <body> when the sheet closes.
 */
export function toast(msg, kind = 'info', { ms = 3800, action } = {}) {
  const box = document.getElementById('toasts');
  const host = [...document.querySelectorAll('dialog.ov[open]:not(.closing)')].pop() || document.body;
  if (box.parentNode !== host) host.append(box);
  const el = h('div', { class: `toast ${kind}`, role: kind === 'err' ? 'alert' : 'status' },
    icon(kind === 'err' ? 'info' : kind === 'ok' ? 'check' : 'speaker', 'sm'), h('span', {}, msg),
    action ? h('button', { type: 'button', onclick: (e) => { e.stopPropagation(); action.run(); dismiss(); } }, action.label) : null);
  el.addEventListener('click', () => dismiss());
  box.append(el);
  while (box.children.length > TOAST_MAX) box.firstChild.remove();
  const life = Math.min(Math.max(kind === 'err' ? 5200 : 2000, Number(ms) || 0), 10000);
  const timer = setTimeout(dismiss, life);
  let gone = false;
  function dismiss() {
    if (gone) return;
    gone = true;
    clearTimeout(timer);
    el.classList.add('out');
    setTimeout(() => el.remove(), motionReduced() ? 0 : 240);
  }
  return dismiss;
}
/** sheet.js calls this before a <dialog> is removed: the toast host must not leave the page with it. */
export function rehomeToasts(dlg) {
  const box = document.getElementById('toasts');
  if (box && dlg.contains(box)) {
    const next = [...document.querySelectorAll('dialog.ov[open]:not(.closing)')].filter((d) => d !== dlg).pop();
    (next || document.body).append(box);
  }
}

/* ---------- tooltip ---------- */
let tipEl = null;
let tipTimer = 0;
let tipWatch = 0;
/**
 * tip(el, 'Shuffle') shows a small label on mouse hover (after 500 ms) or keyboard focus. On touch there is no
 * hover: the label shows only when its control is tapped (a long press used to open labels that stuck, because iOS
 * sends pointercancel instead of pointerup). It hides on leave, blur, a mouse click, any other tap, scroll, Esc, a
 * route change, after a few seconds, or when its control leaves the page (re-render).
 * For icon-only controls the text should equal the aria-label. Returns el.
 */
export function tip(el, text) {
  el.dataset.tip = text;
  if (el.dataset.tipBound) return el;
  el.dataset.tipBound = '1';
  const show = (life = 6000) => {
    hideTip();
    if (!el.isConnected) return;
    tipEl = h('div', { class: 'tip', role: 'tooltip' }, el.dataset.tip);
    document.body.append(tipEl);
    const r = el.getBoundingClientRect(), w = tipEl.offsetWidth, ht = tipEl.offsetHeight;
    const left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), innerWidth - w - 8);
    const top = r.top - ht - 8 > 8 ? r.top - ht - 8 : r.bottom + 8;
    tipEl.style.left = `${left}px`;
    tipEl.style.top = `${top}px`;
    const born = Date.now();
    tipWatch = setInterval(() => { if (!el.isConnected || Date.now() - born > life) hideTip(); }, 250);
  };
  el.addEventListener('pointerenter', (e) => { if (e.pointerType === 'mouse') { clearTimeout(tipTimer); tipTimer = setTimeout(() => show(), 500); } });
  el.addEventListener('focus', () => { if (el.matches(':focus-visible') && !touchLast) show(); });
  el.addEventListener('pointerleave', (e) => { if (e.pointerType === 'mouse') hideTip(); });
  el.addEventListener('blur', hideTip);
  el.addEventListener('click', () => { if (touchLast) show(3000); else hideTip(); });
  return el;
}
export function hideTip() {
  clearTimeout(tipTimer);
  clearInterval(tipWatch);
  if (tipEl) { tipEl.remove(); tipEl = null; }
}
// the last input was a touch: focus moved by a tap must not open a label
let touchLast = false;
addEventListener('pointerdown', (e) => { touchLast = e.pointerType !== 'mouse'; if (tipEl) hideTip(); }, true);
addEventListener('keydown', (e) => { touchLast = false; if (e.key === 'Escape' && tipEl) hideTip(); }, true);
addEventListener('scroll', () => { if (tipEl) hideTip(); }, { capture: true, passive: true });
addEventListener('hashchange', hideTip);

/** Link to a Help topic: helpLink('passkey', t('login.pkWhy')) -> <a href="#/help/passkey">. */
export function helpLink(topic, label) {
  return h('a', { class: 'help-link', href: `#/help${topic ? `/${topic}` : ''}` }, icon('help', 'xs'), label);
}

/* ---------- segmented control ---------- */
/**
 * segmented({ options: [{ value, label }], value, onChange, label }) -> radiogroup element with a sliding thumb.
 * Arrow keys move the selection. el.setValue(v) updates without notifying.
 */
export function segmented({ options, value, onChange, label, cls = '' }) {
  const thumb = h('span', { class: 'seg-thumb', 'aria-hidden': 'true' });
  const root = h('div', { class: `seg ${cls}`.trim(), role: 'radiogroup', 'aria-label': label }, thumb);
  let current = value;
  const btns = options.map((o) => h('button', {
    type: 'button', role: 'radio', lang: o.lang, dataset: { value: String(o.value) }, onclick: () => set(o.value, true),
  }, o.label));
  root.append(...btns);
  root.addEventListener('keydown', (e) => {
    const i = btns.findIndex((b) => b.dataset.value === String(current));
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
    if (!step) return;
    e.preventDefault();
    const n = (i + step + btns.length) % btns.length;
    set(options[n].value, true);
    btns[n].focus();
  });
  function place(animate) {
    const b = btns.find((x) => x.dataset.value === String(current));
    if (!b) return;
    thumb.classList.toggle('no-anim', !animate);
    thumb.style.width = `${b.offsetWidth}px`;
    thumb.style.setProperty('--x', `${b.offsetLeft}px`);
  }
  function set(v, notify) {
    const changed = String(v) !== String(current);
    current = v;
    btns.forEach((b) => {
      const on = b.dataset.value === String(v);
      b.setAttribute('aria-checked', String(on));
      b.tabIndex = on ? 0 : -1;
    });
    place(true);
    if (notify && changed && onChange) onChange(v);
  }
  set(value, false);
  new ResizeObserver(() => place(false)).observe(root);
  root.getValue = () => current;
  root.setValue = (v) => set(v, false);
  return root;
}
