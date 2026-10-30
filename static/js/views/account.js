// Account (board Account; phone: the avatar in the tab bar). Who you are, the owner pages that have no tab on
// phones, app settings + help, passkeys, and your account actions (password, Google, sign out everywhere / here).
// On iPad/desktop the same content is "Account & app settings" (views/prefs.js), so this renders that layout.
import { h, icon, busy } from '../ui.js';
import { register, t, roleLabel, lang } from '../i18n.js';
import { isPhone } from '../sheet.js';
import { caption, card, linkRow, tile, cIcon, toneOf, initialOf } from '../c-kit.js';
import { freshAuth, googleRow, passkeySection } from '../c-account.js';
import { large } from './prefs.js';

register({
  en: { 'acc.manage': 'Manage', 'acc.people': (n) => (n === 1 ? '1 person' : `${n} people`), 'acc.who': (u, r) => `${u} (${r})` },
  th: { 'acc.manage': 'จัดการ', 'acc.people': (n) => `${n} คน`, 'acc.who': (u, r) => `${u} (${r})` },
});

export async function render(ctx) {
  await ctx.css('views/c-common.css');
  ctx.css('views/prefs.css');
  const auth = await freshAuth(ctx);
  if (!isPhone()) return large(ctx, auth, t('nav.prefs'));
  const user = { ...ctx.user, ...(auth.user || {}) };
  const admin = ctx.can('admin');

  const head = h('div', { class: 'ca-head acc-head' },
    h('span', { class: 'avatar lg', style: { background: toneOf(user.id) }, 'aria-hidden': 'true' }, initialOf(user.display_name)),
    h('div', { class: 'ca-head-tx' }, h('p', { class: 'ca-name' }, user.display_name), h('p', { class: 'small' }, t('acc.who', user.username, roleLabel(user.role)))));

  let manage = null;
  if (admin) {
    const count = h('span', {});
    manage = [caption(t('acc.manage')), card(
      withValue(linkRow({ href: '#/members', title: t('nav.members'), lead: tile(icon('members')) }), count),
      linkRow({ href: '#/settings', title: t('nav.settings'), lead: tile(icon('settings'), 'lamp') }),
      linkRow({ href: '#/auth', title: t('nav.auth'), lead: tile(cIcon('shield')) }),
      linkRow({ href: '#/activity', title: t('nav.activity'), lead: tile(icon('activity'), 'lotus') }))];
    ctx.api('/users', { signal: ctx.signal }).then((u) => { count.textContent = t('acc.people', u.length); }).catch(() => {});
  }
  const general = card(
    linkRow({ href: '#/prefs', title: t('nav.appSettings'), value: lang() === 'th' ? 'ไทย' : 'English', lead: tile(cIcon('phone')) }),
    linkRow({ href: '#/help', title: t('nav.help'), lead: tile(icon('help')) }));

  const pk = passkeySection(ctx, auth);

  const row = (ic, label, onclick, tone = 'plain', cls = '') => h('button', { type: 'button', class: `c-row c-link ${cls}`.trim(), onclick },
    tile(icon(ic), tone), h('span', { class: 'c-row-tx' }, h('span', { class: 'c-title' }, label)), cls ? null : h('span', { class: 'c-chev', 'aria-hidden': 'true' }, '›'));
  const mine = card(
    row('key', t('acct.changePw'), () => ctx.changePassword()),
    googleRow(ctx, auth, user),
    row('devices', t('acct.signOutAll'), () => confirmAll(ctx)),
    row('logout', t('acct.signOut'), (e) => busy(e.currentTarget, () => ctx.signOut()).catch(() => {}), 'danger', 'danger'));

  return h('div', { class: 'page p-page' },
    ctx.header({ title: t('nav.account') }),
    head, manage, general,
    pk ? [caption(t('ca.passkeys')), pk.card, pk.note] : null,
    caption(t('acct.my')), mine);
}

function withValue(rowEl, valueEl) {
  valueEl.className = 'c-val';
  rowEl.insertBefore(valueEl, rowEl.querySelector('.c-chev'));
  return rowEl;
}

function confirmAll(ctx) {
  ctx.sheet({
    title: t('acct.signOutAll'),
    build(body, s) {
      const go = h('button', { type: 'button', class: 'btn danger big wide' }, t('acct.signOutAll'));
      go.addEventListener('click', () => busy(go, () => ctx.signOut('/auth/logout-all')).then(() => s.close(), () => {}));
      body.append(h('p', { class: 'muted' }, t('acct.signOutAllText')), go,
        h('button', { type: 'button', class: 'btn big wide', onclick: () => s.close() }, t('common.cancel')));
    },
  });
}
