// App settings (boards Prefs / T_Prefs / D_Prefs). Everyone.
// Phone: per-device app settings only (language, appearance, reduce motion) + a link to Speaker settings for owners.
// iPad/desktop: "Account & app settings": the account (profile, password, Google, passkeys, sign-in methods link
// for owners) next to the app settings. Preferences use prefs.js and apply app-wide right away.
import { h, icon } from '../ui.js';
import { register, t, roleLabel } from '../i18n.js';
import { isPhone } from '../sheet.js';
import { caption, card, settingRow, linkRow, tile, cIcon, phoneBack } from '../c-kit.js';
import { freshAuth, profileHead, nameEditor, googleRow, passkeySection, appPrefsCard } from '../c-account.js';

register({
  en: {
    'pref.account': 'Account', 'pref.app': 'App', 'pref.speaker': 'Speaker',
    'pref.speakerSub': 'Volume, announcement language and connection',
    'pref.deviceNote': 'These settings are for you on this device only.',
    'pref.methodsSub': 'Google, passkeys and passwords for everyone',
    'pref.pwSub': 'Changing it signs out your other devices.',
  },
  th: {
    'pref.account': 'บัญชี', 'pref.app': 'แอป', 'pref.speaker': 'ลำโพง',
    'pref.speakerSub': 'ระดับเสียง ภาษาประกาศ และการเชื่อมต่อ',
    'pref.deviceNote': 'การตั้งค่าเหล่านี้ใช้กับคุณบนเครื่องนี้เท่านั้น',
    'pref.methodsSub': 'Google พาสคีย์ และรหัสผ่านของทุกคน',
    'pref.pwSub': 'เปลี่ยนแล้ว อุปกรณ์อื่นที่เข้าบัญชีนี้อยู่จะถูกออกจากระบบ',
  },
});

export async function render(ctx) {
  const fresh = isPhone() ? null : freshAuth(ctx); // ask the server while the stylesheet loads, not after
  ctx.css('views/prefs.css');
  await ctx.css('views/c-common.css');
  if (!fresh) return phone(ctx);
  return large(ctx, await fresh, t('nav.prefs'));
}

function phone(ctx) {
  return h('div', { class: 'page p-page' },
    phoneBack(ctx.header({ title: t('nav.appSettings'), back: { href: '#/account', label: t('nav.account') } })),
    h('p', { class: 'c-note p-lead' }, t('ca.deviceOnly')),
    appPrefsCard(ctx, { split: true }),
    ctx.can('admin') ? [caption(t('pref.speaker')), card(linkRow({ href: '#/settings', title: t('nav.settings'), sub: t('pref.speakerSub'), lead: tile(icon('settings'), 'lamp') }))] : null);
}

/** iPad/desktop layout; account.js reuses it when #/account is opened on a large screen. */
export function large(ctx, auth, title) {
  const user = { ...ctx.user, ...(auth.user || {}) };
  const pwBtn = h('button', { type: 'button', class: 'btn', onclick: () => ctx.changePassword() }, t('acct.changePw'));
  const acctCard = card(
    h('div', { class: 'c-pad' }, profileHead(user), nameEditor(ctx, user)),
    settingRow({ title: t('ca.password'), sub: t('pref.pwSub'), control: pwBtn }),
    googleRow(ctx, auth, user, { title: t('ca.gLinkedTitle') }));
  const pk = passkeySection(ctx, auth);
  const left = h('div', { class: 'c-col' },
    caption(t('pref.account')), acctCard,
    pk ? [caption(t('ca.passkeys')), pk.card, pk.note] : null,
    ctx.can('admin') ? [caption(roleLabel('admin')), card(linkRow({ href: '#/auth', title: t('nav.auth'), sub: t('pref.methodsSub'), lead: tile(icon('lock'), 'plain') }))] : null);
  const right = h('div', { class: 'c-col' }, caption(t('pref.app')), appPrefsCard(ctx), h('p', { class: 'c-note' }, t('pref.deviceNote')),
    ctx.can('admin') ? [caption(t('pref.speaker')), card(linkRow({ href: '#/settings', title: t('nav.settings'), sub: t('pref.speakerSub'), lead: tile(cIcon('gear'), 'lamp') }))] : null);
  return h('div', { class: 'page p-page' }, ctx.header({ title }), h('div', { class: 'c-cols' }, left, right));
}
