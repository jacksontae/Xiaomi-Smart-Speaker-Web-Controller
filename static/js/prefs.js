// Per-device app preferences: language, theme, reduce motion, look. Stored in localStorage (spk.lang, spk.theme,
// spk.motion, spk.os), resolved and written to <html lang / data-theme / data-motion / data-os>. CSS styles off those
// attributes; JS asks motionReduced() / isAndroid(). js/boot.js applies the same values before first paint.

const KEYS = { lang: 'spk.lang', theme: 'spk.theme', motion: 'spk.motion', os: 'spk.os' };
const ALLOWED = { lang: ['en', 'th'], theme: ['system', 'light', 'dark'], motion: ['system', 'on', 'off'], os: ['auto', 'android', 'ios'] };
const DEFAULTS = { lang: 'en', theme: 'system', motion: 'system', os: 'auto' };

const darkMq = matchMedia('(prefers-color-scheme: dark)');
const motionMq = matchMedia('(prefers-reduced-motion: reduce)');
const subs = new Set();
const root = document.documentElement;

function read(name) {
  let v = null;
  try { v = localStorage.getItem(KEYS[name]); } catch { /* private mode: defaults */ }
  return ALLOWED[name].includes(v) ? v : DEFAULTS[name];
}

/** Stored preference: get('lang') -> 'en'|'th', get('theme') -> 'system'|'light'|'dark', get('motion') -> 'system'|'on'|'off',
 *  get('os') -> 'auto'|'android'|'ios' (the look). */
export function get(name) { return read(name); }

/** Save a preference, apply it right away and tell subscribers. */
export function set(name, value) {
  if (!ALLOWED[name] || !ALLOWED[name].includes(value)) throw new Error(`bad ${name}: ${value}`);
  try { localStorage.setItem(KEYS[name], value); } catch { /* still applies for this page */ }
  apply();
}

export const resolvedTheme = () => { const t = read('theme'); return t === 'system' ? (darkMq.matches ? 'dark' : 'light') : t; };
/** True when animation should be skipped: the app setting, or the OS setting when the app follows the system. */
export function motionReduced() { const m = read('motion'); return m === 'on' || (m === 'system' && motionMq.matches); }

/** The device runs Android (Chrome's client hints, else the user agent). */
const androidDevice = () => (navigator.userAgentData && navigator.userAgentData.platform === 'Android') || /Android/i.test(navigator.userAgent);
/** True when the app wears the Android look: the 'os' setting, or an Android device when it is 'auto'. */
export function isAndroid() { const o = read('os'); return o === 'android' || (o === 'auto' && androidDevice()); }

/** css/android.css: loaded only for the Android look (boot.js adds it before first paint; this covers a later switch). */
function androidCss() {
  if (document.getElementById('android-css')) return;
  document.head.append(Object.assign(document.createElement('link'), { rel: 'stylesheet', id: 'android-css', href: new URL('../css/android.css', import.meta.url).href }));
}

/** Run fn({lang, theme, motionReduced, android}) whenever any of them changes (setting, OS, or another tab). Returns unsubscribe. */
export function onChange(fn) { subs.add(fn); return () => subs.delete(fn); }

let last = '';
export function apply() {
  const state = { lang: read('lang'), theme: resolvedTheme(), motionReduced: motionReduced(), android: isAndroid() };
  root.lang = state.lang;
  root.dataset.theme = state.theme;
  root.dataset.motion = state.motionReduced ? 'reduce' : 'full';
  if (state.android) { androidCss(); root.dataset.os = 'android'; } else delete root.dataset.os;
  // the browser/status bar colour: the page background of the current look (Android: M3 surface)
  const bar = state.android ? (state.theme === 'dark' ? '#0e1415' : '#f2f5f5') : (state.theme === 'dark' ? '#0b1417' : '#e9f0ef');
  document.querySelectorAll('meta[name="theme-color"]').forEach((m) => { m.content = bar; m.removeAttribute('media'); });
  const sig = JSON.stringify(state);
  if (sig === last) return;
  last = sig;
  subs.forEach((f) => { try { f(state); } catch (e) { console.error(e); } });
}

darkMq.addEventListener('change', apply);
motionMq.addEventListener('change', apply);
window.addEventListener('storage', (e) => { if (!e.key || Object.values(KEYS).includes(e.key)) apply(); });
apply();
