// Overlays. One API, platform idiom picked by width:
//   openSheet(): phone = bottom sheet you can drag down to dismiss; iPad/desktop = centred dialog (same content).
//   popover():   anchored menu/list for large screens (speaker picker, account menu). On phones use openSheet.
// Both: Esc closes, focus moves in and returns to the opener, background is inert (<dialog>.showModal for sheets).
// Android look: the system back gesture/button closes the top sheet or popover instead of leaving the page.
import { h, iconBtn, rehomeToasts } from './ui.js';
import { t } from './i18n.js';
import { motionReduced, isAndroid } from './prefs.js';

export const isPhone = () => !matchMedia('(min-width: 744px)').matches;
const open = [];

/* ---------- Android back: one same-address history entry per open overlay ----------
   Opening pushes an entry (no hashchange: the address doesn't change). History back pops it: popstate closes every
   overlay above the entry history landed on. Closing any other way (X, scrim, drag, Esc) takes the entry back off
   with history.back(), unless the page moved on meanwhile (a link inside the sheet), when it is left alone.
   The glass look (iOS/desktop) keeps today's behaviour: back leaves the page. */
const backStack = []; // { id, close }
let backSeq = 0;
let backing = null;   // { done } while our own history.back() is on its way (pushes wait for it)
function backCloses(close) {
  if (!isAndroid()) return () => {};
  const entry = { id: ++backSeq, close };
  backStack.push(entry);
  const push = () => {
    if (!backStack.includes(entry)) return; // closed before the entry went in
    try { history.pushState({ ...(history.state || {}), spkOv: entry.id }, ''); } catch { /* no history: back leaves */ }
  };
  if (backing) backing.wait.then(push); else push();
  return () => {
    const i = backStack.indexOf(entry);
    if (i < 0) return; // closed by history back
    backStack.splice(i, 1);
    if (!history.state || history.state.spkOv !== entry.id) return;
    let done;
    backing = { wait: new Promise((r) => { done = r; }) };
    backing.done = () => { backing = null; done(); };
    const b = backing;
    setTimeout(() => { if (backing === b) b.done(); }, 600); // never stall later pushes
    history.back();
  };
}
addEventListener('popstate', (e) => {
  if (backing) { backing.done(); return; } // our own back after a close
  const at = (e.state && e.state.spkOv) || 0;
  for (let i = backStack.length - 1; i >= 0; i--) {
    const en = backStack[i];
    if (en.id > at) { backStack.splice(i, 1); en.close(); }
  }
});

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
  const releaseBack = backCloses(close);

  function close() {
    if (closed) return;
    closed = true;
    releaseBack();
    open.splice(open.indexOf(api), 1);
    dlg.classList.add('closing');
    rehomeToasts(dlg);
    setTimeout(() => {
      rehomeToasts(dlg); // a toast shown during the closing animation may have moved in again
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
  const me = { el, anchor, onDown, onKey, releaseBack: backCloses(() => { if (pop === me) closePopover(); }) };
  // armed a tick later so the opening click doesn't close it; skip if it was closed in between (else the listener
  // leaks and the next pointerdown anywhere, even inside the next popover, closes that one)
  setTimeout(() => { if (pop === me) document.addEventListener('pointerdown', onDown, true); });
  document.addEventListener('keydown', onKey, true);
  pop = me;
  const first = el.querySelector('[aria-selected="true"], a[href], button:not([disabled])');
  if (first) first.focus({ preventScroll: true });
  return el;
}
export function closePopover(refocus = false) {
  if (!pop) return;
  const { el, anchor, onDown, onKey, releaseBack } = pop;
  pop = null;
  releaseBack();
  document.removeEventListener('pointerdown', onDown, true);
  document.removeEventListener('keydown', onKey, true);
  anchor.setAttribute('aria-expanded', 'false');
  el.remove();
  if (refocus && anchor.isConnected) anchor.focus({ preventScroll: true });
}
