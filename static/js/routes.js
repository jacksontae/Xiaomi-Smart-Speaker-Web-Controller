// Route table + the views contract. Hash routes: #/ (now), #/announce, #/playlists/12, ...
//
// ======================= VIEWS CONTRACT (read before adding a page) =======================
// A view is an ES module in js/views/<id>.js, loaded lazily the first time its route opens:
//
//   import { h } from '../ui.js';
//   import { register, t } from '../i18n.js';
//   register({ en: { 'music.empty': 'Search for a song' }, th: { 'music.empty': 'ค้นหาเพลง' } });
//
//   export function render(ctx) {
//     const list = h('div', { class: 'list' });
//     const node = h('div', { class: 'page' }, ctx.header({ title: t('nav.music') }), list);
//     ctx.api('/queue', { signal: ctx.signal }).then(fill).catch((e) => ctx.fail(e));
//     return {
//       node,                                   // required: the page element (use class "page" for the column)
//       onStatus({ status, error }) { ... },    // optional: every /status poll (~4 s) and once right away
//       destroy() { ... },                      // optional: clear timers/listeners (ctx.signal aborts by itself)
//     };
//   }
//
// ctx (built fresh for every render, see app.js):
//   ctx.api(path, opts)        fetch wrapper (api.js). 401 signs out by itself.
//   ctx.fail(err, overrides)   shows a plain-language error toast; returns the text. Use errorText() for inline errors.
//   ctx.toast(msg, kind, opts) toasts: only when the effect happens elsewhere (on the speaker).
//   ctx.user / ctx.can(role)   signed-in user; can('operator') etc. Hide what the role can't do.
//   ctx.auth                   GET /auth/state result (methods: { password, google, passkey }, google_client_id).
//   ctx.status / ctx.statusError  latest /status (may be null: the speaker can be offline; render that gracefully).
//   ctx.params                 hash segments after the route id (#/playlists/12 -> ['12']).
//   ctx.header({ title, back, actions })  page header: big title (+ speaker chip and Help on iPad/desktop);
//                              on phones its title also becomes the pinned top bar title when scrolled.
//   ctx.sheet({ title, build }) bottom sheet on phones, dialog on iPad/desktop (sheet.js).
//   ctx.popover({ anchor, build })  anchored menu on large screens (use ctx.sheet on phones; sheet.isPhone()).
//   ctx.go('#/members')        navigate. ctx.refreshStatus() polls now (after a command).
//   ctx.signal                 AbortSignal, aborted when the view is destroyed (pass it to ctx.api).
//   ctx.onCleanup(fn)          run fn on destroy.
//   ctx.motionReduced()        skip JS-driven animation when true (CSS already follows <html data-motion>).
// Strings: always t('key') with keys registered in the view (i18n.js). Language/theme changes re-render the view.
// Layout: the shell provides phone tab bar / top bar and the iPad/desktop sidebar; the page only fills .page.
// Styles: shared tokens/components in css/base.css; page-only rules go in css/views/<id>.css, loaded with
//   ctx.css('views/<id>.css') at the top of render (cached, idempotent).
// ===========================================================================================

export const RANK = { viewer: 0, operator: 1, admin: 2 };

// section: 'main' = tab bar (phone) + top group of the sidebar; 'admin' = lower sidebar group (phone: Account page);
// 'none' = reachable by link only. tab: the label in the phone tab bar. parent: the nav item to highlight instead.
export const ROUTES = [
  { id: 'now', label: 'nav.now', tab: 'tab.now', icon: 'now', min: 'viewer', section: 'main', chip: true, load: () => import('./views/now.js') },
  { id: 'announce', label: 'nav.announce', tab: 'nav.announce', icon: 'announce', min: 'viewer', section: 'main', load: () => import('./views/announce.js') },
  { id: 'music', label: 'nav.music', tab: 'nav.music', icon: 'music', min: 'operator', section: 'main', load: () => import('./views/music.js') },
  { id: 'playlists', label: 'nav.playlists', tab: 'nav.playlists', icon: 'playlists', min: 'viewer', section: 'main', load: () => import('./views/playlists.js') },
  { id: 'schedule', label: 'sched.title', icon: 'announce', min: 'viewer', section: 'none', parent: 'announce', load: () => import('./views/schedule.js') },
  { id: 'members', label: 'nav.members', icon: 'members', min: 'admin', section: 'admin', load: () => import('./views/members.js') },
  { id: 'settings', label: 'nav.settings', icon: 'settings', min: 'admin', section: 'admin', load: () => import('./views/settings.js') },
  { id: 'activity', label: 'nav.activity', icon: 'activity', min: 'admin', section: 'admin', load: () => import('./views/activity.js') },
  { id: 'auth', label: 'nav.auth', icon: 'lock', min: 'admin', section: 'none', load: () => import('./views/auth.js') },
  { id: 'account', label: 'nav.account', icon: 'user', min: 'viewer', section: 'none', load: () => import('./views/account.js') },
  { id: 'prefs', label: 'nav.prefs', icon: 'user', min: 'viewer', section: 'none', load: () => import('./views/prefs.js') },
  { id: 'help', label: 'nav.help', icon: 'help', min: 'viewer', section: 'none', load: () => import('./views/help.js') },
];

export const href = (id, ...params) => `#/${id === 'now' ? '' : [id, ...params].join('/')}`;

export function parseHash(hash = location.hash) {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent);
  const route = ROUTES.find((r) => r.id === (parts[0] || 'now'));
  return route ? { route, params: parts.slice(1) } : { route: ROUTES[0], params: [], unknown: true };
}
