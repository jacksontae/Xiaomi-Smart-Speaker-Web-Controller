// Pieces shared by the About, Privacy and Licenses pages (views/about.js, privacy.js, licenses.js). Those pages open
// signed in (from Account) and signed out (from the sign-in page's footer, see app.js): signed out there is no shell,
// so the page brings its own header and padding. Styles: css/views/policy.css.
import { h, icon } from './ui.js';
import { register, t } from './i18n.js';
import { linkRow } from './kit.js';

register({
  en: { 'pp.signIn': 'Sign in', 'pp.newTab': '(opens in a new tab)' },
  th: { 'pp.signIn': 'เข้าสู่ระบบ', 'pp.newTab': '(เปิดในแท็บใหม่)' },
});

export const REPO = 'https://github.com/jacksontae/Xiaomi-Smart-Speaker-Web-Controller';
export const REPO_LABEL = 'github.com/jacksontae/Xiaomi-Smart-Speaker-Web-Controller';

/** GET /about: { version, build } for anyone, plus { server: { speaker, transport, owner_contact } } signed in. */
export const aboutInfo = (ctx) => ctx.api('/about', { signal: ctx.signal });

/**
 * The page: the shell's header signed in; signed out a plain header (no speaker chip or Help: there is no shell)
 * and the screen padding around the column. back = { href, label }; phoneOnly hides the back link on iPad/desktop.
 */
export function policyPage(ctx, { title, back, phoneOnly = false }, ...kids) {
  if (ctx.user) {
    const head = ctx.header({ title, back });
    if (phoneOnly) { const b = head.querySelector('.phd-back'); if (b) b.classList.add('c-phone-only'); }
    return h('div', { class: 'page narrow pp-page' }, head, kids);
  }
  document.title = `${title} · ${t('app.name')}`;
  const head = h('header', { class: 'phd' }, h('div', { class: 'phd-l', style: { minWidth: 0 } },
    h('a', { class: 'phd-back', href: back.href }, icon('back', 'sm'), h('span', { class: 'phd-back-tx' }, back.label)),
    h('h1', { class: 'pt' }, title)));
  return h('div', { class: 'pp-screen' }, h('div', { class: 'page narrow pp-page' }, head, kids));
}

/** Back link of a signed-out page: to the sign-in screen. */
export const signInBack = () => ({ href: '#/', label: t('pp.signIn') });

/** A link that leaves the app: opens in a new tab, never sends this page's address. */
export const extLink = (href, ...kids) => h('a', { href, target: '_blank', rel: 'noopener noreferrer' }, kids);
export const extMark = () => h('span', { class: 'pp-ext', 'aria-hidden': 'true' }, '↗');

/** A link row that leaves the app: ↗ in place of the chevron. */
export function extRow({ href, title, sub, lead }) {
  const r = linkRow({ href, title, sub, lead });
  r.querySelector('.c-chev').replaceWith(extMark());
  r.setAttribute('target', '_blank');
  r.setAttribute('rel', 'noopener noreferrer');
  r.setAttribute('aria-label', `${title}, ${sub || ''} ${t('pp.newTab')}`.replace(/\s+/g, ' '));
  return r;
}

/** Label on the left, value on the right (wraps under it on narrow screens). */
export const kv = (lead, label, value) => h('div', { class: 'c-row pp-kv' }, lead,
  h('span', { class: 'c-row-tx' }, h('span', { class: 'c-title' }, label)), h('span', { class: 'c-val pp-v' }, value));

/** Small print under a card. */
export const fine = (text, cls = '') => h('p', { class: `pp-fine ${cls}`.trim() }, text);

/** The owner's contact as the owner typed it: an email becomes a mail link, a web address a link, else plain text. */
export function contactEl(text, cls = 'pp-mail') {
  if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text)) return h('a', { class: cls, href: `mailto:${text}` }, text);
  if (/^https?:\/\/\S+$/i.test(text)) { const a = extLink(text, text); a.className = cls; return a; }
  return h('span', { class: `${cls} pp-plain` }, text);
}
