// Small building blocks shared by the owner/account pages (members, activity, settings, prefs, account, auth):
// grouped cards, setting rows with a switch, captions, badges, a few icons that aren't in the sprite yet, and
// date formats. Styles: css/views/common.css (each of those views loads it).
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
/** The inline style of a member's avatar: their tone, with white letters (every tone is dark; the theme's
 *  --on-avatar goes with its own --avatar, which is light on Android). */
export const toneStyle = (id) => ({ background: toneOf(id), color: '#fff' });
