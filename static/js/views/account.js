// Account (phone; the avatar in the tab bar). Minimal for now: who you are, the owner pages that have no tab
// on phones, app settings, and the account actions (same rows as the iPad/desktop account menu).
// The full board (Account.dc.html: linked Google, passkeys, ...) is a later task.
import { h, icon, avatar } from '../ui.js';
import { t, roleLabel } from '../i18n.js';
import { ROUTES, href } from '../routes.js';

export function render(ctx) {
  const u = ctx.user;
  const row = (r) => h('a', { class: 'mi', href: href(r.id) }, h('span', { class: 'mic' }, icon(r.icon, 'xs')), h('span', { style: { flex: '1' } }, t(r.label)), icon('chev-right', 'xs'));
  const owner = ROUTES.filter((r) => r.section === 'admin' && ctx.can(r.min));
  const group = (...kids) => h('div', { class: 'list menu', style: { padding: '4px' } }, kids);
  return h('div', { class: 'page' },
    ctx.header({ title: t('nav.account') }),
    h('div', { class: 'row', style: { padding: '4px 0' } }, avatar(u, 'lg'),
      h('div', {}, h('p', { style: { fontSize: '18px', fontWeight: 700 } }, u.display_name),
        h('p', { class: 'small' }, `@${u.username}`), h('p', { class: 'small' }, roleLabel(u.role)))),
    owner.length ? group(owner.map(row)) : null,
    group(h('a', { class: 'mi', href: href('prefs') }, h('span', { class: 'mic' }, icon('settings', 'xs')), h('span', { style: { flex: '1' } }, t('nav.appSettings')), icon('chev-right', 'xs'))),
    group(ctx.accountItems()));
}
