// App entry: auth gate (GET /auth/state), shell, hash router with lazy views, /status polling, ambient mood,
// language/theme re-render. Views follow the contract documented in routes.js.
import { api, errorText, setUnauthorizedHandler } from './api.js';
import { t, roleLabel, onLang } from './i18n.js';
import { motionReduced, onChange as onPrefs } from './prefs.js';
import { h, icon, toast } from './ui.js';
import { openSheet, popover, closeAllSheets } from './sheet.js';
import { buildShell } from './shell.js';
import { RANK, ROUTES, parseHash } from './routes.js';

const POLL_MS = 4000;
const appEl = document.getElementById('app');
const SPEAKER_KEY = 'spk.lastSpeaker'; // last name /status reported, shown while the speaker is unreachable
const readLastSpeaker = () => { try { return localStorage.getItem(SPEAKER_KEY) || ''; } catch { return ''; } };
const state = { auth: null, user: null, status: null, statusErr: null, lastSpeaker: readLastSpeaker() };
let shell = null;
let view = null;   // { node, onStatus?, destroy? } + internal { abort, cleanups }
let pollTimer = 0;
let renderSeq = 0;

const can = (role) => !!state.user && RANK[state.user.role] >= RANK[role];

/* ---------- css loader for view-specific stylesheets ---------- */
// Relative to this module, so stylesheets come from the same versioned /static/<build>/ folder (see app.py).
const cssUrl = (path) => new URL(`../css/${path}`, import.meta.url).href;
const cssLoaded = new Map();
export function loadCss(path) {
  if (!cssLoaded.has(path)) {
    cssLoaded.set(path, new Promise((resolve) => {
      const l = h('link', { rel: 'stylesheet', href: cssUrl(path) });
      l.addEventListener('load', resolve);
      l.addEventListener('error', resolve);
      document.head.append(l);
    }));
  }
  return cssLoaded.get(path);
}

/* ---------- ctx ---------- */
function fail(e, overrides) {
  if (e && e.name === 'AbortError') return '';
  if (e && e.status === 401) return '';
  const msg = errorText(e, state.user, overrides);
  toast(msg, 'err');
  if (e && e.status === 503) refreshStatus();
  return msg;
}
function makeCtx(params = [], route = null) {
  const abort = new AbortController();
  const cleanups = [];
  return {
    ctx: {
      api, toast, fail, can, t, params, route,
      get user() { return state.user; },
      get auth() { return state.auth; },
      get status() { return state.status; },
      get statusError() { return state.statusErr; },
      signal: abort.signal,
      onCleanup: (fn) => cleanups.push(fn),
      header: (opts) => (shell ? shell.header(opts) : h('h1', {}, opts.title)),
      sheet: openSheet,
      popover,
      css: loadCss,
      go: (hash) => { location.hash = hash; },
      refreshStatus: () => refreshStatus(),
      motionReduced,
      accountItems: (close) => (shell ? shell.accountItems(close) : []),
      changePassword: () => shell && shell.changePassword(),
      signOut: (path = '/auth/logout') => signOut(path),
      /** Signed in (login/setup screens): start the app with this user. */
      signedIn: (user) => { state.user = user; startApp(); },
    },
    abort, cleanups,
  };
}

function unmountView() {
  if (!view) return;
  try { if (view.destroy) view.destroy(); } catch (e) { console.error(e); }
  view.abort.abort();
  view.cleanups.forEach((f) => { try { f(); } catch (e) { console.error(e); } });
  view = null;
}

/** Mount a view result into `host`. `mod.render(ctx)` may return a node, a view object, or a Promise of either.
 *  Resolves 'vt' when the swap ran as a view transition (a crossfade: no blank frame, the header stays put),
 *  true for a plain swap, false when a newer navigation won. */
async function mount(mod, host, made, seq, animate) {
  let v = await mod.render(made.ctx);
  if (seq !== renderSeq) { made.abort.abort(); if (v && v.destroy) v.destroy(); return false; }
  if (v instanceof Node) v = { node: v };
  view = { ...v, abort: made.abort, cleanups: made.cleanups };
  const swap = () => { host.replaceChildren(v.node); window.scrollTo(0, 0); };
  let how = true;
  if (animate && document.startViewTransition && !motionReduced() && host.firstElementChild) {
    // the old and new page headers share a name, so a header of the same shape stays still and only its text fades
    const name = (root) => { const hd = root && root.querySelector('.phd'); if (hd) hd.style.viewTransitionName = 'page-head'; return hd; };
    const oldHead = name(host.firstElementChild);
    try {
      const vt = document.startViewTransition(() => { if (oldHead) oldHead.style.viewTransitionName = ''; swap(); name(v.node); });
      vt.finished.finally(() => { const hd = v.node.querySelector('.phd'); if (hd) hd.style.viewTransitionName = ''; });
      vt.ready.catch(() => {}); // skipped (e.g. hidden tab): the DOM update still runs
      await vt.updateCallbackDone;
      how = 'vt';
    } catch { if (v.node.parentNode !== host) swap(); }
  } else swap();
  if (v.onStatus && (state.status || state.statusErr)) callStatus(v);
  return how;
}
function callStatus(v) {
  try { v.onStatus({ status: state.status, error: state.statusErr }); } catch (e) { console.error(e); }
}

/* ---------- boot / auth gate ---------- */
setUnauthorizedHandler(() => {
  if (!state.user) return;
  state.user = null;
  stopPolling();
  closeAllSheets();
  toast(t('err.session'), 'err');
  boot();
});

async function boot() {
  stopPolling();
  if (!state.auth) warmRoute(parseHash().route); // first load: fetch the page's files while /auth/state is asked
  try {
    state.auth = await api('/auth/state', { allow401: true });
  } catch (e) {
    return showScreen(() => ({
      node: h('div', { class: 'page', style: { paddingTop: '20vh' } }, h('h1', { class: 'pt', style: { fontSize: '28px' } }, t('app.loadFailed')),
        h('p', { class: 'muted' }, errorText(e, null)),
        h('button', { class: 'btn primary big', style: { alignSelf: 'flex-start' }, onclick: () => location.reload() }, icon('refresh', 'sm'), t('app.retry'))),
    }));
  }
  state.user = state.auth.user || null;
  if (state.auth.needs_setup) return showScreen(() => import('./views/setup.js'));
  if (!state.user) return showScreen(() => import('./views/login.js'));
  startApp();
}

/** Full-screen pre-auth screens (login, setup, errors): no shell. */
let screenLoad = null;
async function showScreen(load) {
  screenLoad = load;
  unmountView();
  if (shell) { shell.destroy(); shell = null; }
  const seq = ++renderSeq;
  document.body.dataset.mood = 'idle';
  const res = load();
  const mod = res instanceof Promise ? await res : { render: () => res };
  const host = h('div', { class: 'screen' });
  appEl.replaceChildren(host);
  await mount(mod, host, makeCtx(), seq);
}

function startApp() {
  screenLoad = null;
  if (shell) shell.destroy();
  shell = buildShell({ user: state.user, api, onSignOut: signOut, onPickSpeaker: (s) => toast(t('spk.switched', s.name), 'ok') });
  appEl.replaceChildren(shell.el);
  applySpeakers();
  render(false);
  startPolling();
  prefetchRoutes();
  // passkey offer after a fresh sign-in / "passkey required" prompt (team C module; guards itself to once per load)
  import('./c-passkey-offer.js').then((m) => m.maybePrompt({ api, user: state.user, fresh: !(state.auth && state.auth.user) })).catch(() => {});
  // first-run quick tour: once per user per device, when the Now page is up and no sheet is open (tour.js)
  import('./tour.js').then((m) => m.maybeStart({ user: state.user })).catch(() => {});
}

async function signOut(path) {
  try { await api(path, { method: 'POST', allow401: true }); } catch (e) { if (e.status !== 401) { fail(e); throw e; } }
  state.user = null;
  state.status = null;
  closeAllSheets();
  history.replaceState(null, '', '#/');
  toast(t('acct.signedOut'), 'ok');
  boot();
}

/* ---------- router ---------- */
async function render(animate = true) {
  if (!state.user || !shell) return;
  const seq = ++renderSeq;
  const { route, params, unknown } = parseHash();
  if (unknown || !can(route.min)) {
    if (!unknown) toast(t('route.forbidden', roleLabel(route.min)), 'err');
    history.replaceState(null, '', '#/');
    return render(false);
  }
  shell.markRoute(route, animate && !motionReduced());
  (route.css || []).forEach(loadCss); // fetch the page's stylesheets alongside its module, not after it
  const done = pending(route, seq);
  let mod, ok;
  try {
    mod = await route.load();
    if (seq !== renderSeq) return;
    unmountView();
    closeAllSheets();
    ok = await mount(mod, shell.content, makeCtx(params, route), seq, animate);
  } catch (e) {
    console.error(e);
    // The module never reached the server (Brave Shields and ad blockers block some script names), the network
    // dropped, or this tab predates an update (its versioned files are gone): say so on the page, with a retry.
    if (seq !== renderSeq || !shell) return;
    unmountView();
    shell.content.replaceChildren(h('div', { class: 'page' }, h('p', { class: 'lead' }, t('err.module')),
      h('button', { class: 'btn primary', type: 'button', onclick: () => retryRoute() }, icon('refresh', 'sm'), t('app.retry'))));
    return;
  } finally {
    if (seq === renderSeq) done();
  }
  // a 401 while the page loaded signs out and tears the shell down
  if (!ok || !shell || seq !== renderSeq) return;
  document.title = `${t(route.label)} · ${t('app.name')}`;
  shell.onScroll();
  const page = shell.content.firstElementChild;
  // browsers without view transitions: a short fade that never starts from blank
  if (animate && page && ok !== 'vt' && !motionReduced()) { page.classList.remove('enter'); void page.offsetWidth; page.classList.add('enter'); }
}
window.addEventListener('hashchange', () => { if (shell) render(); });

/** A page not ready within ~120 ms gets a slim progress bar at the top, and its header with placeholder rows in
 *  place of the old page, so a slow connection never looks frozen. Returns the function that clears the bar. */
const PENDING_MS = 120;
const progress = h('div', { class: 'navprog', 'aria-hidden': 'true' });
document.body.append(progress);
function pending(route, seq) {
  const timer = setTimeout(() => {
    if (seq !== renderSeq || !shell) return;
    progress.classList.add('on');
    unmountView();
    closeAllSheets();
    const rows = [0, 1, 2].map(() => h('div', { class: 'skel-row' }, h('span', { class: 'skel-dot' }), h('span', { class: 'skel-line' })));
    shell.content.replaceChildren(h('div', { class: 'page page-loading', 'aria-busy': 'true' },
      shell.header({ title: t(route.label) }), h('div', { class: 'skel', role: 'status', 'aria-label': t('app.loading') }, rows)));
    window.scrollTo(0, 0);
  }, PENDING_MS);
  return () => { clearTimeout(timer); progress.classList.remove('on'); };
}

/** Retry after a failed page load: a fresh copy of the app when it was updated meanwhile, else the same page. */
async function retryRoute() {
  try {
    const html = await (await fetch('/', { cache: 'no-store' })).text();
    if (!html.includes(new URL('..', import.meta.url).pathname)) { location.reload(); return; }
  } catch { /* offline: try the page again below */ }
  render(false);
}

/** Once signed in, fetch the other pages' modules and stylesheets while the browser is idle, so the first visit
 *  to each page needs no round trip (files under /static/<build>/ are cached for good). */
function prefetchRoutes() {
  const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 1500));
  const todo = parseHash().route;
  const queue = ROUTES.filter((r) => r !== todo && can(r.min));
  const next = () => {
    const r = queue.shift();
    if (r && state.user) warmRoute(r).finally(() => idle(next, { timeout: 2000 }));
  };
  idle(next, { timeout: 2000 });
}
/** Fetch (and cache) a route's module and stylesheets without showing it. */
function warmRoute(r) {
  (r.css || []).filter((p) => !cssLoaded.has(p)).forEach((p) => fetch(cssUrl(p), { priority: 'low' }).then((res) => res.blob()).catch(() => {}));
  return r.load().catch(() => {});
}

/* ---------- status polling ---------- */
async function refreshStatus() {
  if (!state.user) return;
  try {
    state.status = await api('/status');
    state.statusErr = null;
    if (state.status && state.status.speaker && state.status.speaker !== state.lastSpeaker) {
      state.lastSpeaker = state.status.speaker;
      try { localStorage.setItem(SPEAKER_KEY, state.lastSpeaker); } catch { /* not remembered */ }
    }
  } catch (e) {
    if (e.status === 401) return;
    state.statusErr = e;
  }
  applyMood();
  applySpeakers();
  if (view && view.onStatus) callStatus(view);
}
function startPolling() {
  stopPolling();
  const tick = async () => {
    if (document.visibilityState === 'visible') await refreshStatus();
    if (state.user) pollTimer = setTimeout(tick, state.statusErr ? POLL_MS * 2 : POLL_MS);
  };
  tick();
}
function stopPolling() { clearTimeout(pollTimer); pollTimer = 0; }
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && state.user && shell) startPolling();
  else stopPolling();
});

/** Speaker list for the picker. The server controls one speaker today; the shell shows a picker once it reports more. */
function applySpeakers() {
  if (!shell) return;
  const s = state.status;
  const name = (s && s.speaker) || state.lastSpeaker || '';
  shell.setSpeakers([{ id: 'main', name, online: !state.statusErr && !!s, current: true, checking: !s && !state.statusErr }]);
}

/** Ambient backdrop mood: idle | play (music) | say (announcement) | off (speaker unreachable). */
function applyMood() {
  let mood = 'idle';
  if (state.statusErr) mood = 'off';
  else if (state.status) {
    const m = state.status.media || {};
    if (['PLAYING', 'BUFFERING', 'PAUSED'].includes(m.state)) mood = m.title === 'Announcement' ? 'say' : 'play';
  }
  document.body.dataset.mood = mood;
}

/* ---------- language / theme changes ---------- */
onLang(() => {
  if (shell) startApp();
  else if (screenLoad) showScreen(screenLoad); // login/setup keep their typed values (module-level drafts)
});
onPrefs(() => { if (shell) shell.onScroll(); });

boot();
