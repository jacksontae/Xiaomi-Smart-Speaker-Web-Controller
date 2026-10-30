// Overlays. One API, platform idiom picked by width:
//   openSheet(): phone = bottom sheet you can drag down to dismiss; iPad/desktop = centred dialog (same content).
//   popover():   anchored menu/list for large screens (speaker picker, account menu). On phones use openSheet.
// Both: Esc closes, focus moves in and returns to the opener, background is inert (<dialog>.showModal for sheets).
import { h, iconBtn } from './ui.js';
import { t } from './i18n.js';
import { motionReduced } from './prefs.js';

export const isPhone = () => !matchMedia('(min-width: 744px)').matches;
const open = [];

/**
 * openSheet({ title, build(body, sheet), onClose, label })
 * build fills `body` (and may call sheet.close(), sheet.setTitle()). Returns { close, body, setTitle }.
 */
export function openSheet({ title, build, onClose, label }) {
  const opener = document.activeElement;
  const titleId = `sh${Date.now().toString(36)}`;
  const titleEl = h('h2', { id: titleId }, title || '');
  const closeBtn = iconBtn('close', t('common.close'), () => close(), 'sheet-close');
  const grab = h('div', { class: 'sheet-grab' }, h('span', { class: 'sheet-handle', 'aria-hidden': 'true' }), h('div', { class: 'sheet-head' }, titleEl, closeBtn));
  const body = h('div', { class: 'sheet-body' });
  const panel = h('div', { class: 'sheet' }, grab, body);
  const scrim = h('button', { type: 'button', class: 'ov-scrim', tabindex: '-1', 'aria-label': t('common.close'), onclick: () => close() });
  const dlg = h('dialog', { class: 'ov', 'aria-labelledby': title ? titleId : null, 'aria-label': label || null }, scrim, panel);
  document.body.append(dlg);
  let closed = false;
  const api = { close, body, dialog: dlg, setTitle: (s) => { titleEl.textContent = s; } };
  build(body, api);
  dlg.addEventListener('cancel', (e) => { e.preventDefault(); close(); });
  dlg.showModal();
  open.push(api);
  const first = body.querySelector('input:not([type=hidden]),textarea,select');
  (first && !matchMedia('(pointer: coarse)').matches ? first : closeBtn).focus({ preventScroll: true });
  dragToDismiss(grab, panel, scrim, close);

  function close() {
    if (closed) return;
    closed = true;
    open.splice(open.indexOf(api), 1);
    dlg.classList.add('closing');
    setTimeout(() => {
      dlg.close();
      dlg.remove();
      if (opener && opener.isConnected) opener.focus({ preventScroll: true });
      if (onClose) onClose();
    }, motionReduced() ? 0 : 200);
  }
  return api;
}

function dragToDismiss(grab, panel, scrim, close) {
  let y0 = 0, lastY = 0, lastT = 0, vel = 0, on = false;
  grab.addEventListener('pointerdown', (e) => {
    if (!isPhone() || e.target.closest('button,a,input')) return;
    on = true; y0 = lastY = e.clientY; lastT = performance.now(); vel = 0;
    grab.setPointerCapture(e.pointerId);
    panel.classList.add('dragging');
    panel.classList.remove('settle');
  });
  grab.addEventListener('pointermove', (e) => {
    if (!on) return;
    const now = performance.now();
    vel = (e.clientY - lastY) / Math.max(1, now - lastT);
    lastY = e.clientY; lastT = now;
    let dy = e.clientY - y0;
    if (dy < 0) dy = -Math.sqrt(-dy) * 2; // rubber band when pulled up
    panel.style.transform = `translateY(${dy}px)`;
    scrim.style.opacity = String(Math.max(0, 1 - Math.max(0, dy) / (panel.offsetHeight * 1.2)));
  });
  const end = () => {
    if (!on) return;
    on = false;
    panel.classList.remove('dragging');
    const dy = lastY - y0;
    if (dy > panel.offsetHeight * 0.25 || vel > 0.6) {
      panel.style.transform = `translateY(${Math.max(dy, 0)}px)`;
      requestAnimationFrame(() => { panel.classList.add('settle'); panel.style.transform = 'translateY(100%)'; });
      close();
      return;
    }
    panel.classList.add('settle');
    panel.style.transform = '';
    scrim.style.opacity = '';
  };
  grab.addEventListener('pointerup', end);
  grab.addEventListener('pointercancel', end);
}

export function closeAllSheets() { [...open].forEach((s) => s.close()); closePopover(); }

/* ---------- popover ---------- */
let pop = null;
/**
 * popover({ anchor, build(el, close), place: 'below'|'above'|'right', label, className })
 * Toggles: calling it again for the same anchor closes it. Sets aria-expanded on the anchor.
 */
export function popover({ anchor, build, place = 'below', label, className = '' }) {
  if (pop && pop.anchor === anchor) { closePopover(); return null; }
  closePopover();
  const el = h('div', { class: `popover ${className}`.trim(), role: 'dialog', 'aria-label': label });
  document.body.append(el);
  build(el, closePopover);
  const r = anchor.getBoundingClientRect();
  const w = el.offsetWidth, ht = el.offsetHeight;
  let left = r.left, top = r.bottom + 8;
  if (place === 'above') top = r.top - ht - 8;
  if (place === 'right') { left = r.right + 10; top = r.top; }
  if (place === 'below' && r.right - w > 16 && r.left + w > innerWidth - 16) left = r.right - w;
  el.style.left = `${Math.max(16, Math.min(left, innerWidth - w - 16))}px`;
  el.style.top = `${Math.max(16, Math.min(top, innerHeight - ht - 16))}px`;
  anchor.setAttribute('aria-expanded', 'true');
  const onDown = (e) => { if (!el.contains(e.target) && !anchor.contains(e.target)) closePopover(); };
  const onKey = (e) => { if (e.key === 'Escape') { e.preventDefault(); closePopover(true); } };
  setTimeout(() => document.addEventListener('pointerdown', onDown, true));
  document.addEventListener('keydown', onKey, true);
  pop = { el, anchor, onDown, onKey };
  const first = el.querySelector('[aria-selected="true"], a[href], button:not([disabled])');
  if (first) first.focus({ preventScroll: true });
  return el;
}
export function closePopover(refocus = false) {
  if (!pop) return;
  const { el, anchor, onDown, onKey } = pop;
  pop = null;
  document.removeEventListener('pointerdown', onDown, true);
  document.removeEventListener('keydown', onKey, true);
  anchor.setAttribute('aria-expanded', 'false');
  el.remove();
  if (refocus && anchor.isConnected) anchor.focus({ preventScroll: true });
}
