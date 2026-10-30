// Small building blocks shared by the owner/account pages (members, activity, settings, prefs, account, auth):
// grouped cards, setting rows with a switch, captions, badges, a few icons that aren't in the sprite yet, and
// date formats. Styles: css/views/c-common.css (each of those views loads it).
import { h } from './ui.js';

export { initial as initialOf } from './ui.js';
import { register, t, locale, fmtClock } from './i18n.js';

register({
  en: {
    'c.today': 'Today', 'c.yesterday': 'Yesterday',
    'c.todayAt': (c) => `today ${c}`, 'c.yesterdayAt': (c) => `yesterday ${c}`,
    'c.unsaved': 'Not saved yet', 'c.saved': 'Saved', 'c.on': 'On', 'c.off': 'Off',
  },
  th: {
    'c.today': 'วันนี้', 'c.yesterday': 'เมื่อวาน',
    'c.todayAt': (c) => `วันนี้ ${c}`, 'c.yesterdayAt': (c) => `เมื่อวาน ${c}`,
    'c.unsaved': 'ยังไม่ได้บันทึก', 'c.saved': 'บันทึกแล้ว', 'c.on': 'เปิด', 'c.off': 'ปิด',
  },
});

/* ---------- icons not in the index.html sprite yet (same 24px stroke style) ---------- */
const PATHS = {
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  clock: '<circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/>',
  list: '<path d="M5 7h14M5 12h14M5 17h9"/>',
  alert: '<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/>',
  'user-plus': '<circle cx="10" cy="8" r="3.5"/><path d="M3.5 20a6.5 6.5 0 0 1 11.5-4.2M18 14v6M15 17h6"/>',
  shield: '<path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z"/><path d="M9 12l2 2 4-4"/>',
  phone: '<rect x="7" y="3" width="10" height="18" rx="2.5"/><path d="M11 18h2"/>',
  scan: '<circle cx="12" cy="12" r="2"/><path d="M8.5 8.5a5 5 0 0 0 0 7M15.5 8.5a5 5 0 0 1 0 7M5.6 5.6a9 9 0 0 0 0 12.8M18.4 5.6a9 9 0 0 1 0 12.8"/>',
  volume: '<path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16.5 8.5a5 5 0 0 1 0 7"/>',
  music: '<circle cx="7" cy="17" r="3"/><path d="M10 17V5l10-2v12"/><circle cx="17" cy="15" r="3"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  gear: '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
};
/** cIcon('mic', 'sm') — inline SVG for icons the sprite doesn't have yet (lead: move these into index.html). */
export function cIcon(name, cls = '') {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', `icon ${cls}`.trim());
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  svg.innerHTML = PATHS[name] || '';
  return svg;
}

const G_MARK = '<svg class="icon xs g" viewBox="0 0 24 24" aria-hidden="true" style="stroke:none"><path fill="#4285F4" d="M21.6 12.23c0-.71-.06-1.4-.18-2.05H12v3.88h5.38a4.6 4.6 0 0 1-2 3.02v2.5h3.24c1.9-1.75 2.98-4.32 2.98-7.35z"/><path fill="#34A853" d="M12 22c2.7 0 4.97-.9 6.62-2.42l-3.24-2.5c-.9.6-2.04.95-3.38.95-2.6 0-4.8-1.75-5.59-4.11H3.07v2.58A10 10 0 0 0 12 22z"/><path fill="#FBBC05" d="M6.41 13.92A6 6 0 0 1 6.1 12c0-.67.11-1.31.31-1.92V7.5H3.07A10 10 0 0 0 2 12c0 1.61.39 3.14 1.07 4.5l3.34-2.58z"/><path fill="#EA4335" d="M12 5.98c1.47 0 2.79.5 3.82 1.5l2.87-2.87A9.6 9.6 0 0 0 12 2 10 10 0 0 0 3.07 7.5l3.34 2.58C7.2 7.73 9.4 5.98 12 5.98z"/></svg>';
/** The Google "G" (brand colours; only next to Google sign-in/account rows). */
export function gMark(cls = '') {
  const s = h('span', { class: `c-g ${cls}`.trim(), 'aria-hidden': 'true' });
  s.innerHTML = G_MARK;
  return s;
}

/* ---------- layout pieces ---------- */
/** Section caption above a card ("Sound", "Passkeys"). */
export const caption = (text, id) => h('h2', { class: 'c-cap', id }, text);
/** Grouped glass card; children are rows. */
export const card = (...kids) => h('div', { class: 'c-card' }, kids);
/** Tinted icon tile (tone: accent | lamp | lotus | danger | plain). */
export const tile = (iconEl, tone = 'accent') => h('span', { class: `c-tile ${tone}`, 'aria-hidden': 'true' }, iconEl);
/** Small status badge ("Owner", "Disabled"). */
export const badge = (text, tone = '') => h('span', { class: `c-badge ${tone}`.trim() }, text);

let seq = 0;
/**
 * A row with a title, an optional line under it and a control on the right.
 * settingRow({ title, sub, control, lead }) -> element; an input/select `control` gets aria-labelledby/-describedby,
 * a button only aria-describedby (it keeps its own name).
 */
export function settingRow({ title, sub, control, lead, cls = '' }) {
  const id = `cr${++seq}`;
  const subEl = sub != null ? h('span', { class: 'c-sub', id: `${id}-s` }, sub) : null;
  if (control && control.matches && control.matches('input,select')) {
    control.setAttribute('aria-labelledby', `${id}-t`);
    if (subEl) control.setAttribute('aria-describedby', subEl.id);
  } else if (control && control.matches && control.matches('button')) {
    // a button keeps its own name ("Edit", "Use"); the row only describes what it acts on
    control.setAttribute('aria-describedby', [`${id}-t`, subEl && subEl.id].filter(Boolean).join(' '));
  }
  return h('div', { class: `c-row ${cls}`.trim() }, lead || null,
    h('div', { class: 'c-row-tx' }, h('span', { class: 'c-title', id: `${id}-t` }, title), subEl),
    control || null);
}

/** <input type=checkbox role=switch class=switch>. onChange(checked). */
export function switchInput(checked, onChange, props = {}) {
  const el = h('input', { type: 'checkbox', role: 'switch', class: 'switch', checked: !!checked, ...props });
  el.addEventListener('change', () => onChange && onChange(el.checked));
  return el;
}

/** A link row (icon tile, title, optional value, chevron). */
export function linkRow({ href, title, sub, value, lead, onclick }) {
  return h(href ? 'a' : 'button', { class: 'c-row c-link', href, type: href ? null : 'button', onclick },
    lead || null,
    h('span', { class: 'c-row-tx' }, h('span', { class: 'c-title' }, title), sub ? h('span', { class: 'c-sub' }, sub) : null),
    value ? h('span', { class: 'c-val' }, value) : null,
    h('span', { class: 'c-chev', 'aria-hidden': 'true' }, '›'));
}

/** The page header's back link is for phones only (on iPad/desktop these pages live in the sidebar). */
export function phoneBack(headerEl) {
  const b = headerEl.querySelector('.phd-back');
  if (b) b.classList.add('c-phone-only');
  return headerEl;
}

/* ---------- dates (app language, 24 h) ---------- */
const sameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
/** "3 Oct" / "3 ต.ค." (+ year when not this year). */
export function fmtDay(iso) {
  const d = new Date(iso), now = new Date();
  return d.toLocaleDateString(locale(), { day: 'numeric', month: 'short', year: d.getFullYear() === now.getFullYear() ? undefined : 'numeric' });
}
/** "today 08:12", "yesterday 18:20", "21 Oct". */
export function fmtWhen(iso) {
  if (!iso) return '';
  const d = new Date(iso), now = new Date();
  const y = new Date(now); y.setDate(now.getDate() - 1);
  if (sameDay(d, now)) return t('c.todayAt', fmtClock(d));
  if (sameDay(d, y)) return t('c.yesterdayAt', fmtClock(d));
  return fmtDay(iso);
}
/** Day heading for grouped lists: Today, Yesterday, "Tuesday 27 Oct". */
export function fmtDayHead(d) {
  const now = new Date();
  const y = new Date(now); y.setDate(now.getDate() - 1);
  if (sameDay(d, now)) return t('c.today');
  if (sameDay(d, y)) return t('c.yesterday');
  return d.toLocaleDateString(locale(), { weekday: 'long', day: 'numeric', month: 'short', year: d.getFullYear() === now.getFullYear() ? undefined : 'numeric' });
}
export { sameDay };

/* ---------- members ---------- */
const AVATAR_TONES = ['#2f5f6a', '#a3365a', '#5a6b8c', '#6b5a2f', '#3d6b4f', '#6a4c7d'];
/** Avatar background per member, stable by id. */
export const toneOf = (id) => AVATAR_TONES[(Number(id) || 0) % AVATAR_TONES.length];
