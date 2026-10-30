// Per-device app preferences: language, theme, reduce motion. Stored in localStorage (spk.lang, spk.theme,
// spk.motion), resolved and written to <html lang / data-theme / data-motion>. CSS styles off those attributes;
// JS asks motionReduced(). js/boot.js applies the same values before first paint.

const KEYS = { lang: 'spk.lang', theme: 'spk.theme', motion: 'spk.motion' };
const ALLOWED = { lang: ['en', 'th'], theme: ['system', 'light', 'dark'], motion: ['system', 'on', 'off'] };
const DEFAULTS = { lang: 'en', theme: 'system', motion: 'system' };

const darkMq = matchMedia('(prefers-color-scheme: dark)');
const motionMq = matchMedia('(prefers-reduced-motion: reduce)');
const subs = new Set();
const root = document.documentElement;

function read(name) {
  let v = null;
  try { v = localStorage.getItem(KEYS[name]); } catch { /* private mode: defaults */ }
  return ALLOWED[name].includes(v) ? v : DEFAULTS[name];
}

/** Stored preference: get('lang') -> 'en'|'th', get('theme') -> 'system'|'light'|'dark', get('motion') -> 'system'|'on'|'off'. */
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

/** Run fn({lang, theme, motionReduced}) whenever any of them changes (setting, OS, or another tab). Returns unsubscribe. */
export function onChange(fn) { subs.add(fn); return () => subs.delete(fn); }

let last = '';
export function apply() {
  const state = { lang: read('lang'), theme: resolvedTheme(), motionReduced: motionReduced() };
  root.lang = state.lang;
  root.dataset.theme = state.theme;
  root.dataset.motion = state.motionReduced ? 'reduce' : 'full';
  document.querySelectorAll('meta[name="theme-color"]').forEach((m) => { m.content = state.theme === 'dark' ? '#0b1417' : '#e9f0ef'; m.removeAttribute('media'); });
  const sig = JSON.stringify(state);
  if (sig === last) return;
  last = sig;
  subs.forEach((f) => { try { f(state); } catch (e) { console.error(e); } });
}

darkMq.addEventListener('change', apply);
motionMq.addEventListener('change', apply);
window.addEventListener('storage', (e) => { if (!e.key || Object.values(KEYS).includes(e.key)) apply(); });
apply();
