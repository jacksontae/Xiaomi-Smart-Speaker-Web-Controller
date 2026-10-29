// Small DOM toolkit: element builder, icons, toasts, sliding-lens segmented control, sheets, inline confirm.

export const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');

export function h(tag, props, ...kids) {
  const el = tag === 'svg' ? document.createElementNS('http://www.w3.org/2000/svg', 'svg') : document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.setAttribute('class', v);
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k in el && typeof el[k] !== 'function' && !k.includes('-') && tag !== 'svg') el[k] = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  append(el, kids);
  return el;
}
function append(el, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k == null || k === false) continue;
    el.append(k instanceof Node ? k : String(k));
  }
}

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

export function iconBtn(name, label, onclick, cls = '') {
  return h('button', { type: 'button', class: `iconbtn ${cls}`, 'aria-label': label, title: label, onclick }, icon(name, /play|pause|stop|next|prev/.test(name) ? 'fill' : ''));
}

/* ---------- formatting ---------- */
export function fmtDur(sec) {
  if (sec == null || !isFinite(sec)) return '';
  sec = Math.max(0, Math.round(sec));
  const hh = Math.floor(sec / 3600), mm = Math.floor((sec % 3600) / 60), ss = sec % 60;
  return hh ? `${hh}:${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}` : `${mm}:${String(ss).padStart(2, '0')}`;
}
export function fmtTotal(sec) {
  if (!sec) return '';
  const m = Math.round(sec / 60);
  return m >= 60 ? `${Math.floor(m / 60)} ชม. ${m % 60} นาที` : `${m} นาที`;
}
const rtf = new Intl.RelativeTimeFormat('th', { numeric: 'auto' });
export function fmtRel(iso) {
  if (!iso) return '';
  const d = (new Date(iso) - Date.now()) / 1000;
  const a = Math.abs(d);
  if (a < 60) return 'เมื่อสักครู่';
  if (a < 3600) return rtf.format(Math.round(d / 60), 'minute');
  if (a < 86400) return rtf.format(Math.round(d / 3600), 'hour');
  if (a < 86400 * 30) return rtf.format(Math.round(d / 86400), 'day');
  return new Date(iso).toLocaleDateString('th-TH', { day: 'numeric', month: 'short', year: 'numeric' });
}
export const fmtTime = (iso) => new Date(iso).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' });
export const fmtDay = (iso) => {
  const d = new Date(iso), t = new Date();
  const y = new Date(); y.setDate(t.getDate() - 1);
  if (d.toDateString() === t.toDateString()) return 'วันนี้';
  if (d.toDateString() === y.toDateString()) return 'เมื่อวาน';
  return d.toLocaleDateString('th-TH', { weekday: 'long', day: 'numeric', month: 'long' });
};
// Thai leading vowels (เ แ โ ใ ไ) are written before the consonant; skip them so the avatar shows a real letter.
export const initial = (name) => ((name || '?').trim().replace(/^[\u0E40-\u0E44]+/, '').charAt(0) || '?').toUpperCase();

/* ---------- toast ---------- */
export function toast(msg, kind = 'info', ms = 3800) {
  const box = document.getElementById('toasts');
  const t = h('div', { class: `toast glass-strong ${kind}`, role: kind === 'err' ? 'alert' : 'status' },
    icon(kind === 'err' ? 'info' : kind === 'ok' ? 'check' : 'info', 'sm'), h('span', {}, msg));
  box.append(t);
  while (box.children.length > 3) box.firstChild.remove();
  setTimeout(() => { t.classList.add('out'); setTimeout(() => t.remove(), 260); }, ms);
  return t;
}

/* ---------- sliding lens ---------- */
/** Move `lens` under `target` inside `container`. Axis 'x' uses width, 'y' uses height. */
export function placeLens(lens, target, { axis = 'x', animate = true } = {}) {
  if (!target) { lens.style.opacity = '0'; return; }
  lens.style.opacity = '1';
  if (!animate) lens.classList.add('no-anim');
  if (axis === 'x') {
    lens.style.setProperty('--x', `${target.offsetLeft}px`);
    lens.style.width = `${target.offsetWidth}px`;
  } else {
    lens.style.setProperty('--y', `${target.offsetTop}px`);
    lens.style.height = `${target.offsetHeight}px`;
  }
  if (!animate) { lens.offsetWidth; requestAnimationFrame(() => lens.classList.remove('no-anim')); }
}

/** Segmented control (radiogroup) whose glass lens slides to the chosen option. */
export function segmented({ options, value, onChange, label, cls = '' }) {
  const lens = h('div', { class: 'lens', 'aria-hidden': 'true' });
  const root = h('div', { class: `seg ${cls}`, role: 'radiogroup', 'aria-label': label }, lens);
  let current = value;
  const btns = options.map((o) => {
    const b = h('button', {
      type: 'button', role: 'radio', 'aria-checked': String(o.value === value), tabindex: o.value === value ? '0' : '-1',
      onclick: () => set(o.value, true, true),
    }, o.icon ? icon(o.icon, 'sm') : null, h('span', {}, o.label));
    b.dataset.value = o.value;
    root.append(b);
    return b;
  });
  root.addEventListener('keydown', (e) => {
    const i = btns.findIndex((b) => b.dataset.value === String(current));
    let n = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') n = (i + 1) % btns.length;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') n = (i - 1 + btns.length) % btns.length;
    if (n == null) return;
    e.preventDefault();
    set(options[n].value, true, true);
    btns[n].focus();
  });
  function set(v, notify, animate = true) {
    if (String(v) === String(current) && notify) return;
    current = v;
    btns.forEach((b) => {
      const on = b.dataset.value === String(v);
      b.setAttribute('aria-checked', String(on));
      b.tabIndex = on ? 0 : -1;
    });
    placeLens(lens, btns.find((b) => b.dataset.value === String(v)), { animate });
    if (notify && onChange) onChange(v);
  }
  const ro = new ResizeObserver(() => placeLens(lens, btns.find((b) => b.dataset.value === String(current)), { animate: false }));
  ro.observe(root);
  root.getValue = () => current;
  root.setValue = (v) => set(v, false);
  return root;
}

/* ---------- sheet ---------- */
const openSheets = [];
/**
 * Bottom sheet (phone) / centered card (wide). Springs up, swipe the header down to dismiss.
 * build(body, api) fills the content; returns { close, body, setTitle }.
 */
export function openSheet({ title, build, onClose, label }) {
  const titleEl = h('h2', { id: `sheet-t-${Date.now()}` }, title);
  const closeBtn = iconBtn('close', 'ปิด', () => close());
  const head = h('div', { class: 'sheet-head' }, h('div', { class: 'grabber', 'aria-hidden': 'true' }), h('div', { class: 'sheet-title' }, titleEl, closeBtn));
  const body = h('div', { class: 'sheet-body' });
  const panel = h('div', { class: 'sheet-panel glass-strong' }, head, body);
  const scrim = h('div', { class: 'sheet-scrim', onclick: () => close() });
  const dlg = h('dialog', { class: 'sheet', 'aria-labelledby': titleEl.id, 'aria-label': label }, scrim, panel);
  document.body.append(dlg);
  let closed = false;
  const api = { close, body, dialog: dlg, setTitle: (t) => { titleEl.textContent = t; } };
  build(body, api);
  dlg.addEventListener('cancel', (e) => { e.preventDefault(); close(); });
  dlg.showModal();
  openSheets.push(api);
  // focus first field if any, else the close button
  const first = body.querySelector('input:not([type=hidden]),textarea,select');
  (first && !matchMedia('(pointer: coarse)').matches ? first : closeBtn).focus({ preventScroll: true });
  requestAnimationFrame(() => requestAnimationFrame(() => dlg.classList.add('open')));

  // drag to dismiss
  let startY = 0, lastY = 0, lastT = 0, vel = 0, dragging = false;
  head.addEventListener('pointerdown', (e) => {
    if (e.target.closest('button')) return;
    dragging = true; startY = lastY = e.clientY; lastT = performance.now(); vel = 0;
    head.setPointerCapture(e.pointerId);
    dlg.classList.add('dragging');
  });
  head.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    const now = performance.now();
    vel = (e.clientY - lastY) / Math.max(1, now - lastT);
    lastY = e.clientY; lastT = now;
    let dy = e.clientY - startY;
    if (dy < 0) dy = -Math.sqrt(-dy) * 2; // rubber band upward
    const wide = matchMedia('(min-width: 760px)').matches;
    panel.style.transform = wide ? `translate(-50%, calc(-50% + ${dy}px))` : `translateY(${dy}px)`;
    scrim.style.opacity = String(Math.max(0, 1 - Math.max(0, dy) / (panel.offsetHeight * 1.2)));
  });
  const end = () => {
    if (!dragging) return;
    dragging = false;
    dlg.classList.remove('dragging');
    const dy = lastY - startY;
    panel.style.transform = '';
    scrim.style.opacity = '';
    if (dy > panel.offsetHeight * 0.25 || vel > 0.6) close();
  };
  head.addEventListener('pointerup', end);
  head.addEventListener('pointercancel', end);

  function close() {
    if (closed) return;
    closed = true;
    dlg.classList.remove('open');
    openSheets.splice(openSheets.indexOf(api), 1);
    const done = () => { dlg.close(); dlg.remove(); onClose && onClose(); };
    if (reduceMotion.matches) setTimeout(done, 160);
    else setTimeout(done, 380);
  }
  return api;
}
export function closeAllSheets() { [...openSheets].forEach((s) => s.close()); }

/* ---------- inline confirm (replaces window.confirm) ---------- */
export function inlineConfirm(anchor, { text, confirmLabel, onConfirm, danger = true }) {
  const old = anchor.nextElementSibling;
  if (old && old.classList.contains('confirm')) return;
  const cancel = h('button', { type: 'button', class: 'btn sm', onclick: () => done() }, 'ยกเลิก');
  const ok = h('button', {
    type: 'button', class: `btn sm ${danger ? 'danger' : 'primary'}`,
    onclick: async () => {
      ok.classList.add('busy'); ok.disabled = true; cancel.disabled = true;
      try { await onConfirm(); done(false); } catch { ok.classList.remove('busy'); ok.disabled = false; cancel.disabled = false; }
    },
  }, confirmLabel);
  const box = h('div', { class: 'confirm', role: 'group', 'aria-label': text }, h('p', {}, text), h('div', { class: 'btns' }, cancel, ok));
  anchor.hidden = true;
  anchor.after(box);
  cancel.focus({ preventScroll: true });
  box.scrollIntoView({ block: 'nearest', behavior: reduceMotion.matches ? 'auto' : 'smooth' });
  function done(restore = true) {
    box.remove();
    if (anchor.isConnected) { anchor.hidden = false; if (restore) anchor.focus(); }
  }
}

/* ---------- forms ---------- */
export function field(labelText, input, hint) {
  const id = input.id || `f-${Math.random().toString(36).slice(2, 8)}`;
  input.id = id;
  const hintEl = hint ? h('div', { class: 'hint', id: `${id}-hint` }, hint) : null;
  if (hintEl) input.setAttribute('aria-describedby', hintEl.id);
  return h('div', { class: 'field' }, h('label', { for: id }, labelText), input, hintEl);
}
export function switchRow(labelText, checked, onchange, hint) {
  const input = h('input', { type: 'checkbox', role: 'switch', checked, onchange });
  return h('label', { class: 'switch' }, h('span', {}, h('span', { style: { fontWeight: 600 } }, labelText), hint ? h('span', { class: 'hint', style: { display: 'block', fontSize: 'var(--fs-sm)', color: 'var(--ink-2)' } }, hint) : null), input);
}
export function setRangeFill(r) {
  const p = ((r.value - r.min) / (r.max - r.min)) * 100;
  r.style.setProperty('--p', `${p}%`);
}

/** Run an async action with a busy button; returns result or undefined on failure (error already toasted). */
export async function busy(btn, fn) {
  if (btn) { btn.classList.add('busy'); btn.disabled = true; }
  try { return await fn(); } finally { if (btn) { btn.classList.remove('busy'); btn.disabled = false; } }
}

export function thumbEl(src, fallbackIcon = 'note', cls = '') {
  if (src) {
    const img = h('img', { class: `thumb ${cls}`, src, alt: '', loading: 'lazy', decoding: 'async' });
    img.addEventListener('error', () => img.replaceWith(h('div', { class: `thumb ${cls}` }, icon(fallbackIcon))), { once: true });
    return img;
  }
  return h('div', { class: `thumb ${cls}` }, icon(fallbackIcon));
}
export const kindIcon = (k) => (k === 'tts' ? 'announce' : k === 'url' ? 'link' : 'note');
