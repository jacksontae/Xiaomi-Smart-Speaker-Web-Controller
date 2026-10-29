// App shell: auth gate, navigation (glass tab bar / sidebar), /status polling, ambient backdrop, account sheet.
import { api, ApiError, setUnauthorizedHandler, thaiError, ROLE_TH } from './api.js';
import { h, icon, toast, placeLens, openSheet, closeAllSheets, reduceMotion, field, inlineConfirm, busy, initial } from './ui.js';
import { renderSetup, renderLogin } from './views/auth.js';

const ROUTES = [
  { id: 'now', label: 'เล่นอยู่', icon: 'now', min: 'viewer', tab: true, load: () => import('./views/now.js') },
  { id: 'announce', label: 'ประกาศ', icon: 'announce', min: 'viewer', tab: true, load: () => import('./views/announce.js') },
  { id: 'youtube', label: 'YouTube', icon: 'search', min: 'operator', tab: true, load: () => import('./views/youtube.js') },
  { id: 'playlists', label: 'เพลย์ลิสต์', icon: 'playlists', min: 'viewer', tab: true, load: () => import('./views/playlists.js') },
  { id: 'members', label: 'สมาชิก', icon: 'members', min: 'admin', load: () => import('./views/members.js') },
  { id: 'settings', label: 'ตั้งค่าลำโพง', icon: 'settings', min: 'admin', load: () => import('./views/settings.js') },
  { id: 'activity', label: 'ประวัติการใช้งาน', icon: 'activity', min: 'admin', load: () => import('./views/activity.js') },
];
const RANK = { viewer: 0, operator: 1, admin: 2 };
const POLL_MS = 4000;

const appEl = document.getElementById('app');
const state = { user: null, status: null, statusErr: null, statusAt: 0 };
const statusSubs = new Set();
let view = null; // { destroy?, onStatus? }
let viewSubs = [];
let pollTimer = null;
let shell = null;
let lastRouteIndex = 0;

const can = (role) => !!state.user && RANK[state.user.role] >= RANK[role];

/* ---------- ctx handed to views ---------- */
const ctx = {
  api,
  toast,
  can,
  get user() { return state.user; },
  get status() { return state.status; },
  get statusErr() { return state.statusErr; },
  get statusAt() { return state.statusAt; },
  /** Show an error toast in plain Thai; returns the message. */
  fail(e, overrides) {
    if (e instanceof ApiError && e.status === 401) return '';
    const msg = thaiError(e, state.user, overrides);
    toast(msg, 'err', 5200);
    if (e instanceof ApiError && e.status === 503) refreshStatus();
    return msg;
  },
  onStatus(fn) { viewSubs.push(fn); statusSubs.add(fn); if (state.status || state.statusErr) fn(state); },
  refreshStatus: () => refreshStatus(),
  go(hash) { location.hash = hash; },
  setUser(u) { state.user = u; buildShell(); render(); },
  openAccount: () => openAccount(),
};

/* ---------- boot ---------- */
setUnauthorizedHandler(() => {
  if (!state.user) return;
  state.user = null;
  stopPolling();
  closeAllSheets();
  toast('หมดเวลาการเข้าสู่ระบบ เข้าสู่ระบบอีกครั้ง', 'err');
  showLogin();
});

async function boot() {
  let st;
  try {
    st = await api('/auth/state', { allow401: true });
  } catch (e) {
    appEl.replaceChildren(h('div', { class: 'auth' }, h('div', { class: 'auth-card glass-strong' },
      h('h1', {}, 'เปิดแอปไม่ได้'), h('p', { class: 'lead' }, thaiError(e, null)),
      h('button', { class: 'btn primary wide', onclick: () => location.reload() }, icon('refresh', 'sm'), 'ลองอีกครั้ง'))));
    return;
  }
  if (st.needs_setup) return showSetup();
  if (!st.user) return showLogin();
  state.user = st.user;
  startApp();
}

function showSetup() {
  unmountView();
  shell = null;
  appEl.replaceChildren(renderSetup(ctx, (u) => { state.user = u; startApp(); }));
  setMood('idle');
}
function showLogin() {
  unmountView();
  shell = null;
  appEl.replaceChildren(renderLogin(ctx, (u) => { state.user = u; startApp(); }));
  setMood('idle');
}
function startApp() {
  buildShell();
  render();
  startPolling();
}

/* ---------- shell ---------- */
function buildShell() {
  const routes = ROUTES.filter((r) => can(r.min));
  const tabs = routes.filter((r) => r.tab);
  const tabLens = h('div', { class: 'lens', 'aria-hidden': 'true' });
  const tabbar = h('nav', { class: 'tabbar glass', 'aria-label': 'เมนูหลัก' }, tabLens,
    tabs.map((r) => h('a', { class: 'tab', href: `#/${r.id === 'now' ? '' : r.id}`, dataset: { route: r.id } }, icon(r.icon), h('span', {}, r.label))));
  tabbar.addEventListener('pointerdown', (e) => { if (e.target.closest('.tab')) tabbar.classList.add('pressing'); });
  const unpress = () => tabbar.classList.remove('pressing');
  tabbar.addEventListener('pointerup', unpress);
  tabbar.addEventListener('pointercancel', unpress);
  tabbar.addEventListener('pointerleave', unpress);
  const dockBtn = h('button', { type: 'button', class: 'dock-btn glass', 'aria-label': `บัญชีและเมนูอื่น (${state.user.display_name})`, onclick: () => openAccount() },
    h('span', { class: 'avatar', 'aria-hidden': 'true' }, initial(state.user.display_name)));
  const dock = h('div', { class: 'tabdock' }, tabbar, dockBtn);

  const sideLens = h('div', { class: 'lens', 'aria-hidden': 'true' });
  const link = (r) => h('a', { class: 'side-link', href: `#/${r.id === 'now' ? '' : r.id}`, dataset: { route: r.id } }, icon(r.icon), h('span', {}, r.label));
  const main = routes.filter((r) => r.min !== 'admin');
  const admin = routes.filter((r) => r.min === 'admin');
  const sideNav = h('nav', { class: 'side-nav', 'aria-label': 'เมนูหลัก' }, sideLens, main.map(link),
    admin.length ? [h('div', { class: 'side-sep', role: 'separator' }), admin.map(link)] : null);
  const speakerName = h('small', {}, 'กำลังเชื่อมต่อ…');
  const sidebar = h('aside', { class: 'sidebar glass' },
    h('div', { class: 'side-brand' }, brandMark(), h('div', {}, 'ลำโพง', speakerName)),
    sideNav,
    h('div', { class: 'side-foot' }, h('button', { type: 'button', class: 'side-link', onclick: () => openAccount() },
      h('span', { class: 'avatar', 'aria-hidden': 'true' }, initial(state.user.display_name)),
      h('span', { class: 'who' }, state.user.display_name, h('small', {}, ROLE_TH[state.user.role])))));
  const content = h('main', { class: 'content', id: 'view', tabindex: '-1' });
  appEl.replaceChildren(h('div', { class: 'shell' }, sidebar, content, dock));
  shell = { content, tabbar, tabLens, sideNav, sideLens, dockBtn, speakerName, firstPlace: true };
}
new ResizeObserver(() => markNav(false)).observe(document.body);

function brandMark() {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 64 64');
  s.setAttribute('aria-hidden', 'true');
  const u = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  u.setAttribute('href', '#i-mark');
  s.append(u);
  return s;
}

function markNav(animate = true) {
  if (!shell) return;
  const id = parseHash().route.id;
  for (const a of appEl.querySelectorAll('[data-route]')) {
    if (a.dataset.route === id) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  }
  placeLens(shell.tabLens, shell.tabbar.querySelector('[aria-current]'), { animate });
  placeLens(shell.sideLens, shell.sideNav.querySelector('[aria-current]'), { axis: 'y', animate });
  shell.dockBtn.classList.toggle('on', !shell.tabbar.querySelector('[aria-current]'));
}

/* ---------- router ---------- */
function parseHash() {
  const parts = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean);
  const route = ROUTES.find((r) => r.id === (parts[0] || 'now')) || ROUTES[0];
  return { route, params: parts.slice(1) };
}

function unmountView() {
  if (view && view.destroy) view.destroy();
  viewSubs.forEach((f) => statusSubs.delete(f));
  viewSubs = [];
  view = null;
}

let renderSeq = 0;
async function render() {
  if (!state.user || !shell) return;
  const seq = ++renderSeq;
  const { route, params } = parseHash();
  if (!can(route.min)) {
    toast(`หน้านี้สำหรับ${ROLE_TH[route.min]}ขึ้นไป`, 'err');
    location.hash = '#/';
    return;
  }
  const mod = await route.load();
  if (seq !== renderSeq) return;
  const idx = ROUTES.indexOf(route) * 10 + params.length;
  const dir = idx >= lastRouteIndex ? 'fwd' : 'back';
  lastRouteIndex = idx;
  document.documentElement.dataset.dir = dir;
  const swap = () => {
    unmountView();
    const v = mod.default(ctx, params);
    view = v;
    shell.content.replaceChildren(v.node);
    window.scrollTo(0, 0);
    document.title = `${route.label} — ลำโพง`;
  };
  const first = shell.firstPlace;
  shell.firstPlace = false;
  markNav(!first);
  if (!first && document.startViewTransition && !reduceMotion.matches) {
    shell.content.classList.add('vt');
    const vt = document.startViewTransition(swap);
    vt.finished.finally(() => shell.content.classList.remove('vt'));
  } else {
    swap();
    if (!first && !reduceMotion.matches) {
      shell.content.style.setProperty('--enter-x', dir === 'fwd' ? '24px' : '-24px');
      shell.content.classList.remove('enter'); void shell.content.offsetWidth; shell.content.classList.add('enter');
    }
  }
}
window.addEventListener('hashchange', () => { closeAllSheets(); render(); });

/* ---------- status polling ---------- */
async function refreshStatus() {
  if (!state.user) return;
  try {
    state.status = await api('/status');
    state.statusErr = null;
  } catch (e) {
    if (e.status === 401) return;
    state.statusErr = e;
  }
  state.statusAt = performance.now();
  applyAmbient();
  if (shell) {
    shell.speakerName.textContent = state.statusErr
      ? (state.statusErr.status === 503 ? 'ติดต่อลำโพงไม่ได้' : 'เชื่อมต่อไม่ได้')
      : state.status.speaker;
  }
  statusSubs.forEach((f) => { try { f(state); } catch (err) { console.error(err); } });
}
function startPolling() {
  stopPolling();
  const tick = async () => {
    if (document.visibilityState === 'visible') await refreshStatus();
    pollTimer = setTimeout(tick, state.statusErr ? POLL_MS * 2 : POLL_MS);
  };
  tick();
}
function stopPolling() { clearTimeout(pollTimer); pollTimer = null; }
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && state.user && shell) startPolling();
  else stopPolling();
});

/* ---------- ambient backdrop ---------- */
const amb = document.getElementById('ambient');
const ambImg = amb.querySelector('.amb-art');
let ambSrc = null;
function setMood(m) {
  amb.querySelectorAll('.mood').forEach((el) => el.classList.toggle('on', el.dataset.mood === m));
}
function setArt(src) {
  if (src === ambSrc) return;
  ambSrc = src;
  ambImg.classList.remove('on');
  if (!src) return;
  const pre = new Image();
  pre.onload = () => {
    if (ambSrc !== src) return;
    const c = ambImg.getContext('2d');
    c.clearRect(0, 0, ambImg.width, ambImg.height);
    c.filter = 'blur(3px) saturate(170%)'; // ignored where unsupported; the upscale still softens it
    c.drawImage(pre, -6, -6, ambImg.width + 12, ambImg.height + 12);
    ambImg.classList.add('on');
  };
  pre.src = src;
}
function applyAmbient() {
  if (state.statusErr) { setArt(null); return setMood('offline'); }
  const m = state.status.media || {};
  const active = ['PLAYING', 'PAUSED', 'BUFFERING'].includes(m.state);
  setArt(active ? m.thumbnail : null);
  if (active && m.title === 'Announcement') setMood('announce');
  else setMood(active ? 'music' : 'idle');
}

/* ---------- account sheet ---------- */
function openAccount() {
  const u = state.user;
  openSheet({
    title: 'บัญชีของฉัน',
    build(body, sheet) {
      body.append(h('div', { class: 'who-card' },
        h('span', { class: 'avatar lg', 'aria-hidden': 'true' }, initial(u.display_name)),
        h('div', { class: 'body' }, h('h3', {}, u.display_name), h('div', { class: 'muted' }, `@${u.username}`),
          h('span', { class: `badge ${u.role === 'admin' ? 'admin' : ''}`, style: { marginTop: '4px' } }, ROLE_TH[u.role]))));
      const adminRoutes = ROUTES.filter((r) => r.min === 'admin' && can(r.min));
      if (adminRoutes.length && !matchMedia('(min-width: 760px)').matches) {
        body.append(h('nav', { class: 'menu', 'aria-label': 'สำหรับผู้ดูแล' }, adminRoutes.map((r) =>
          h('a', { class: 'row no-thumb', href: `#/${r.id}`, onclick: () => sheet.close() }, icon(r.icon), h('span', { class: 'body' }, r.label), icon('chev', 'sm')))));
      }
      // change password
      const cur = h('input', { class: 'input', type: 'password', autocomplete: 'current-password', required: true });
      const nw = h('input', { class: 'input', type: 'password', autocomplete: 'new-password', minLength: 8, required: true });
      const err = h('p', { class: 'form-error', role: 'alert' });
      const save = h('button', { class: 'btn primary', type: 'submit' }, 'เปลี่ยนรหัสผ่าน');
      const form = h('form', {
        onsubmit: async (e) => {
          e.preventDefault();
          err.textContent = '';
          if (nw.value.length < 8) { err.textContent = 'รหัสผ่านใหม่ต้องยาวอย่างน้อย 8 ตัวอักษร'; nw.focus(); return; }
          await busy(save, async () => {
            try {
              await api('/auth/password', { body: { current: cur.value, new: nw.value }, allow401: true });
              toast('เปลี่ยนรหัสผ่านแล้ว อุปกรณ์อื่นถูกออกจากระบบ', 'ok');
              form.reset();
            } catch (e2) {
              err.textContent = thaiError(e2, u, { 401: 'รหัสผ่านปัจจุบันไม่ถูกต้อง' });
            }
          });
        },
      }, h('h3', { style: { marginBottom: '10px' } }, 'เปลี่ยนรหัสผ่าน'),
      field('รหัสผ่านปัจจุบัน', cur), field('รหัสผ่านใหม่', nw, 'อย่างน้อย 8 ตัวอักษร อุปกรณ์อื่นที่เข้าสู่ระบบอยู่จะถูกออกจากระบบ'), err, save);
      body.append(form, h('div', { class: 'divider' }));
      const out = h('button', { class: 'btn wide', type: 'button', onclick: () => busy(out, () => signOut('/auth/logout')) }, icon('logout', 'sm'), 'ออกจากระบบ');
      const outAll = h('button', {
        class: 'btn quiet wide', type: 'button',
        onclick: () => inlineConfirm(outAll, { text: 'ออกจากระบบทุกอุปกรณ์ที่ใช้บัญชีนี้ รวมถึงเครื่องนี้?', confirmLabel: 'ออกทั้งหมด', onConfirm: () => signOut('/auth/logout-all') }),
      }, 'ออกจากระบบทุกอุปกรณ์');
      body.append(h('div', { style: { display: 'grid', gap: '8px' } }, out, outAll));
    },
  });
}

async function signOut(path) {
  try { await api(path, { method: 'POST', allow401: true }); } catch (e) { if (e.status !== 401) { ctx.fail(e); throw e; } }
  state.user = null;
  state.status = null;
  stopPolling();
  closeAllSheets();
  location.hash = '#/';
  showLogin();
  toast('ออกจากระบบแล้ว', 'ok');
}

boot();
