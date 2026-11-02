// Android kit: Material 3 pieces the Android look has and the glass look (iPhone/iPad/desktop) doesn't.
// Shared by the page teams (B: Playlists, Music, Schedule; C: Members, Settings, Account…). Off Android every
// function is a no-op that returns null, so those pages keep today's buttons and sheets with no extra branches.
// Styles: css/views/android-kit.css, fetched only on Android by kitCss() (route css lists stay as they are).
//
// ========================= ANDROID KIT API (read before using) =========================
//   import { kitCss, fab, replacedByFab, fullDialog, androidPhone } from '../android-kit.js';
//
//   await kitCss(ctx);   at the top of render, next to the view's own ctx.css(): loads android-kit.css on Android.
//
//   fab(ctx, { icon, label, onclick, replaces })  -> <button> | null
//     Extended FAB: 56 px, radius 16, primaryContainer, bottom-right above the nav pill and the Now Bar (and above a
//     snackbar while one shows). Shows on Android phones (< 744 px); tablets keep the page's own button.
//     Scrolling down shrinks it to the icon, scrolling up brings the label back (its accessible name stays the label).
//     icon: a sprite name ('plus') or an <svg> node. replaces: the page's own button for the same action, hidden on
//     Android phones only (see replacedByFab). While a FAB is up the page gets extra bottom padding so the last row
//     scrolls clear of it. It is removed when the view goes (ctx.onCleanup).
//
//   replacedByFab(el)  -> el. Marks a button the FAB stands in for (hidden on Android phones, shown everywhere else).
//     Use it for a button that is rebuilt after the FAB was made.
//
//   fullDialog(ctx, { title, save, build(body, dlg), onClose })  -> dlg | null
//     Full-screen dialog for long forms on Android phones (M3): a top bar with close (X), the title (it appears in the
//     bar once the big title scrolls under it) and a `save` button; body below scrolls. build() fills `body` and
//     calls dlg.bindForm(form): the bar's Save button then submits that form (the form's submit handler does the
//     work and calls dlg.close()). dlg = { close, body, dialog, saveBtn, setTitle, bindForm }.
//     Esc, X and the system back gesture close it (back pops one history entry, the way sheet.js does for sheets).
//     Returns null on tablets and off Android: use ctx.sheet() there.
//
//   androidPhone()  -> true on Android narrower than 744 px (where the FAB and the full-screen dialog apply).
// ===========================================================================================
import { h, icon, iconBtn, rehomeToasts } from './ui.js';
import { t } from './i18n.js';
import { isAndroid, motionReduced } from './prefs.js';
import { isPhone } from './sheet.js';

export const androidPhone = () => isAndroid() && isPhone();

/** Loads the kit's stylesheet on Android (cached, idempotent); resolves at once elsewhere. */
export function kitCss(ctx) {
  return isAndroid() ? ctx.css('views/android-kit.css') : Promise.resolve();
}

export function replacedByFab(el) {
  if (el) el.classList.add('ak-replaced');
  return el;
}

/* ---------- extended FAB ---------- */
export function fab(ctx, { icon: ic, label, onclick, replaces }) {
  if (!isAndroid()) return null;
  replacedByFab(replaces);
  const btn = h('button', { type: 'button', class: 'ak-fab', 'aria-label': label, onclick },
    typeof ic === 'string' ? icon(ic) : ic, h('span', { class: 'ak-fab-l', 'aria-hidden': 'true' }, label));
  document.body.append(btn);
  document.documentElement.toggleAttribute('data-fab', true);

  // shrink on scroll down, grow on scroll up (a few px of slack so a resting finger doesn't flicker it)
  let lastY = scrollY;
  const onScroll = () => {
    const y = scrollY;
    if (Math.abs(y - lastY) < 6) return;
    btn.classList.toggle('small', y > lastY && y > 24);
    lastY = y;
  };
  addEventListener('scroll', onScroll, { passive: true });

  // a snackbar shows above the nav pill where the FAB sits: lift the FAB over it while it is up (M3)
  const box = document.getElementById('toasts');
  const lift = () => {
    const n = box && box.parentNode === document.body && box.children.length ? box.offsetHeight : 0;
    btn.style.setProperty('--ak-lift', n ? `${n + 8}px` : '0px');
  };
  const mo = box ? new MutationObserver(lift) : null;
  if (mo) mo.observe(box, { childList: true });

  ctx.onCleanup(() => {
    removeEventListener('scroll', onScroll);
    if (mo) mo.disconnect();
    btn.remove();
    if (!document.querySelector('.ak-fab')) document.documentElement.removeAttribute('data-fab');
  });
  return btn;
}

/* ---------- history back closes the dialog (mirrors sheet.js backCloses, own state key) ----------
   Opening pushes a same-address entry; history back pops it and popstate closes the dialogs above where history
   landed. Closing another way takes the entry back off with history.back(), unless the page moved on meanwhile. */
const backStack = []; // { id, close }
let backSeq = 0;
let backing = null;
function backCloses(close) {
  const entry = { id: ++backSeq, close };
  backStack.push(entry);
  const push = () => {
    if (!backStack.includes(entry)) return;
    try { history.pushState({ ...(history.state || {}), akOv: entry.id }, ''); } catch { /* no history: back leaves */ }
  };
  if (backing) backing.wait.then(push); else push();
  return () => {
    const i = backStack.indexOf(entry);
    if (i < 0) return; // closed by history back
    backStack.splice(i, 1);
    if (!history.state || history.state.akOv !== entry.id) return;
    let done;
    backing = { wait: new Promise((r) => { done = r; }) };
    backing.done = () => { backing = null; done(); };
    const b = backing;
    setTimeout(() => { if (backing === b) b.done(); }, 600);
    history.back();
  };
}
addEventListener('popstate', (e) => {
  if (backing) { backing.done(); return; }
  const at = (e.state && e.state.akOv) || 0;
  for (let i = backStack.length - 1; i >= 0; i--) {
    const en = backStack[i];
    if (en.id > at) { backStack.splice(i, 1); en.close(); }
  }
});

/* ---------- full-screen dialog ---------- */
let dlgSeq = 0;
export function fullDialog(ctx, { title, save, build, onClose }) {
  if (!androidPhone()) return null;
  const opener = document.activeElement;
  const id = `akd${++dlgSeq}`;
  const barTitle = h('span', { class: 'ak-full-bt', 'aria-hidden': 'true' }, title || '');
  const bigTitle = h('h2', { id: `${id}-t`, class: 'ak-full-t' }, title || '');
  const saveBtn = h('button', { type: 'submit', class: 'btn primary ak-full-save' }, save || t('common.save'));
  const closeBtn = iconBtn('close', t('common.close'), () => close(), 'ak-full-x');
  const bar = h('div', { class: 'ak-full-bar' }, closeBtn, barTitle, saveBtn);
  const body = h('div', { class: 'ak-full-body' });
  const panel = h('div', { class: 'ak-full-panel' }, bar, bigTitle, body);
  const dlg = h('dialog', { class: 'ov ak-full', 'aria-labelledby': bigTitle.id }, panel);
  document.body.append(dlg);
  let closed = false;
  const api = {
    close, body, dialog: dlg, saveBtn,
    setTitle: (s) => { barTitle.textContent = s; bigTitle.textContent = s; },
    bindForm(form) {
      if (!form.id) form.id = `${id}-f`;
      saveBtn.setAttribute('form', form.id);
    },
  };
  build(body, api);
  dlg.addEventListener('cancel', (e) => { e.preventDefault(); close(); });
  // the bar takes the title once the big one is under it
  panel.addEventListener('scroll', () => {
    bar.dataset.title = String(panel.scrollTop > bigTitle.offsetTop + bigTitle.offsetHeight / 2 - bar.offsetHeight);
    bar.dataset.under = String(panel.scrollTop > 4);
  }, { passive: true });
  dlg.showModal();
  closeBtn.focus({ preventScroll: true });
  const releaseBack = backCloses(close);
  ctx.onCleanup(close);

  function close() {
    if (closed) return;
    closed = true;
    releaseBack();
    dlg.classList.add('closing');
    rehomeToasts(dlg);
    setTimeout(() => {
      rehomeToasts(dlg);
      dlg.close();
      dlg.remove();
      if (opener && opener.isConnected) opener.focus({ preventScroll: true });
      if (onClose) onClose();
    }, motionReduced() ? 0 : 200);
  }
  return api;
}
