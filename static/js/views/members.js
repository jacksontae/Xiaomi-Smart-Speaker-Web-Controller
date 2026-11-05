// Members (boards Members / MemberEdit / T_Members / D_Members). Owner only.
// Phone: list, "+" in the header, tap a member = edit sheet. iPad: list with chevrons, edit opens as a dialog.
// Desktop: list on the left, the selected member's editor on the right.
// Android (A_Members / A_MemberEdit / AT_Members): Add member is a FAB and the editor a full-screen dialog on phones;
// tablets in landscape (>= 960 px) get the list | editor panes.
// Server: GET/POST /users, PATCH/DELETE /users/{id}. Guards come back as 409 (yourself, last enabled owner).
// Google accounts and passkeys are linked by each member in their own Account page, so here they are read-only.
import { h, append, icon, iconBtn, field, passwordInput, busy, segmented, tip, toast, headerSub } from '../ui.js';
import { register, t, roleLabel } from '../i18n.js';
import { errorText } from '../api.js';
import { card, badge, linkRow, tile, switchInput, settingRow, phoneBack, fmtWhen, gMark, toneStyle, initialOf } from '../kit.js';
import { isAndroid } from '../prefs.js';
import { kitCss, fab, fullDialog } from '../android-kit.js';
import { glyph } from '../icons.js';

register({
  en: {
    // the header's context line (Android)
    'mem.ctxAll': (n) => (n === 1 ? '1 person, active' : `${n} people, all active`),
    'mem.ctxOff': (n, o) => `${n} people, ${o} disabled`,
    'mem.add': 'Add member', 'mem.addShort': 'Add', 'mem.you': '(you)', 'mem.list': 'Members',
    'mem.lastActive': (w) => `Last active ${w}`, 'mem.never': 'Hasn\'t signed in yet', 'mem.cantSign': 'Can\'t sign in anymore',
    'mem.password': 'Password', 'mem.hasPk': 'Has a passkey', 'mem.noPk': 'No passkey yet', 'mem.disabled': 'Disabled',
    'mem.edit': 'Edit member', 'mem.username': 'Username', 'mem.usernameLine': (u) => `Username ${u}`,
    'mem.displayName': 'Display name', 'mem.namePh': 'e.g. Wipa Kaewmanee', 'mem.userPh': 'e.g. wipa',
    'mem.role': 'Role', 'mem.startPw': 'Starting password', 'mem.min8': 'At least 8 characters',
    'mem.help.viewer': 'Can see what\'s playing and skip tracks in the speaker\'s queue. On their own device they can play music and keep private playlists. Can\'t start, stop or announce on the speaker.',
    'mem.help.operator': 'Can announce, play music, change the volume, edit playlists and schedule.',
    'mem.help.admin': 'Can do everything, including members, speaker settings and Activity.',
    'mem.selfRole': 'You can\'t change your own role. Ask another owner.',
    'mem.signIn': 'Sign-in',
    'mem.viaPw': (u) => `Signs in with the username ${u} and a password.`,
    'mem.viaGoogle': (e) => `Can also sign in with Google (${e}).`,
    'mem.selfLinks': 'Members link Google and add passkeys themselves in Account.',
    'mem.resetNote': 'Members link Google and add passkeys themselves in Account. Remove one here if a phone is lost or the Google account isn’t theirs any more; they get signed out of every device.',
    'mem.gLine': (e) => `Google · ${e}`, 'mem.pkLine': (n, w) => `Passkey ${n} · ${w}`,
    'mem.pkUsed': (w) => `last used ${w}`, 'mem.pkNever': 'not used yet',
    'mem.unlink': 'Unlink', 'mem.remove': 'Remove', 'mem.keepIt': 'Keep',
    'mem.gAsk': (n) => `Unlink Google from ${n}? ${n} gets signed out of every device, can still sign in with the password, and can link Google again in Account.`,
    'mem.pkAsk': (n, pk) => `Remove the ${pk} passkey from ${n}? ${n} gets signed out of every device and can add a new passkey in Account.`,
    'mem.gDone': (n) => `Unlinked Google from ${n} and signed them out of every device.`,
    'mem.pkDone': (n, pk) => `Removed ${n}’s ${pk} passkey and signed them out of every device.`,
    'mem.errOnlyWay': 'That’s their only way to sign in. Set a new password for them first.',
    'mem.disable': 'Disable account', 'mem.disableOff': 'Blocks sign-in and signs them out of every device right away.',
    'mem.disableOn': 'Disabled. They can\'t sign in until you turn this off.',
    'mem.setPw': 'Set a new password', 'mem.setPwBtn': 'Set new password', 'mem.newPwPh': 'New password, at least 8 characters',
    'mem.setPwHelp': 'They get signed out of every device, then sign in again with this password.',
    'mem.pwDone': 'New password set. They were signed out of every device.',
    'mem.delete': 'Delete member', 'mem.keep': 'Keep',
    'mem.delAsk': (n) => `Delete ${n}? Their past activity stays, but the account is gone.`,
    'mem.deleted': (n) => `${n} deleted`, 'mem.added': (n) => `${n} added`, 'mem.saved': 'Saved',
    'mem.errName': 'Enter a display name first', 'mem.errUser': 'Enter a username first', 'mem.errPw': 'The password needs at least 8 characters',
    'mem.errTaken': 'That username is already taken. Pick another.',
    'mem.errSelf': 'You can\'t disable yourself or change your own role.',
    'mem.errSelfDel': 'You can\'t delete your own account.',
    'mem.errLastAdmin': 'This is the last owner who can sign in. Make someone else an owner first.',
    'mem.methods': 'Sign-in methods', 'mem.methodsSub': 'Google, passkeys and passwords. Only owners change these.',
    'mem.methodsAll': 'Google, passkeys and password, for everyone here',
    'mem.pick': 'Pick a member on the left to edit.',
    'mem.empty': 'No members yet.',
    'mem.yours': 'Your account', 'mem.others': 'Other people',
  },
  th: {
    'mem.ctxAll': (n) => (n === 1 ? '1 คน ใช้งานได้' : `${n} คน ใช้งานได้ทุกคน`),
    'mem.ctxOff': (n, o) => `${n} คน ปิดใช้งานอยู่ ${o} คน`,
    'mem.add': 'เพิ่มสมาชิก', 'mem.addShort': 'เพิ่ม', 'mem.you': '(คุณ)', 'mem.list': 'รายชื่อสมาชิก',
    'mem.lastActive': (w) => `เข้าใช้ล่าสุด${w}`, 'mem.never': 'ยังไม่เคยเข้าใช้', 'mem.cantSign': 'เข้าระบบไม่ได้แล้ว',
    'mem.password': 'รหัสผ่าน', 'mem.hasPk': 'มีพาสคีย์', 'mem.noPk': 'ยังไม่มีพาสคีย์', 'mem.disabled': 'ปิดใช้งาน',
    'mem.edit': 'แก้ไขสมาชิก', 'mem.username': 'ชื่อผู้ใช้', 'mem.usernameLine': (u) => `ชื่อผู้ใช้ ${u}`,
    'mem.displayName': 'ชื่อที่แสดง', 'mem.namePh': 'เช่น วิภา แก้วมณี', 'mem.userPh': 'เช่น wipa',
    'mem.role': 'บทบาท', 'mem.startPw': 'รหัสผ่านเริ่มต้น', 'mem.min8': 'อย่างน้อย 8 ตัว',
    'mem.help.viewer': 'ดูว่ากำลังเล่นอะไร และข้ามเพลงในคิวของลำโพงได้ ฟังเพลงและทำเพลย์ลิสต์ส่วนตัวได้ที่เครื่องตัวเอง แต่สั่งเล่น หยุด หรือประกาศที่ลำโพงไม่ได้',
    'mem.help.operator': 'ประกาศ เล่นเพลง ปรับเสียง แก้เพลย์ลิสต์ และตั้งเวลาได้',
    'mem.help.admin': 'ทำได้ทุกอย่าง รวมถึงจัดการสมาชิก ตั้งค่าลำโพง และดูประวัติ',
    'mem.selfRole': 'เปลี่ยนบทบาทของตัวเองไม่ได้ ให้เจ้าของคนอื่นเปลี่ยนให้',
    'mem.signIn': 'การเข้าสู่ระบบ',
    'mem.viaPw': (u) => `เข้าด้วยชื่อผู้ใช้ ${u} และรหัสผ่าน`,
    'mem.viaGoogle': (e) => `เข้าด้วย Google ได้ด้วย (${e})`,
    'mem.selfLinks': 'สมาชิกเชื่อม Google และเพิ่มพาสคีย์เองได้ในหน้าบัญชี',
    'mem.resetNote': 'สมาชิกเชื่อม Google และเพิ่มพาสคีย์เองได้ในหน้าบัญชี · ลบที่นี่ได้เมื่อโทรศัพท์หายหรือบัญชี Google ไม่ใช่ของเขาแล้ว สมาชิกจะออกจากระบบทุกเครื่อง',
    'mem.gLine': (e) => `Google · ${e}`, 'mem.pkLine': (n, w) => `พาสคีย์ ${n} · ${w}`,
    'mem.pkUsed': (w) => `ใช้ล่าสุด${w}`, 'mem.pkNever': 'ยังไม่เคยใช้',
    'mem.unlink': 'ยกเลิกการเชื่อม', 'mem.remove': 'ลบ', 'mem.keepIt': 'เก็บไว้',
    'mem.gAsk': (n) => `ยกเลิกการเชื่อม Google ของ ${n}? ${n} จะถูกออกจากระบบทุกเครื่อง ยังเข้าด้วยรหัสผ่านได้ และเชื่อม Google ใหม่เองได้ในหน้าบัญชี`,
    'mem.pkAsk': (n, pk) => `ลบพาสคีย์ ${pk} ของ ${n}? ${n} จะถูกออกจากระบบทุกเครื่อง และเพิ่มพาสคีย์ใหม่เองได้ในหน้าบัญชี`,
    'mem.gDone': (n) => `ยกเลิกการเชื่อม Google ของ ${n} แล้ว ออกจากระบบทุกเครื่องแล้ว`,
    'mem.pkDone': (n, pk) => `ลบพาสคีย์ ${pk} ของ ${n} แล้ว ออกจากระบบทุกเครื่องแล้ว`,
    'mem.errOnlyWay': 'นี่เป็นทางเดียวที่สมาชิกเข้าระบบได้ ตั้งรหัสผ่านใหม่ให้ก่อน',
    'mem.disable': 'ปิดใช้งานบัญชี', 'mem.disableOff': 'เข้าระบบไม่ได้ และออกจากระบบทุกเครื่องทันที',
    'mem.disableOn': 'ปิดใช้งานแล้ว เข้าระบบไม่ได้จนกว่าจะเปิดอีกครั้ง',
    'mem.setPw': 'ตั้งรหัสผ่านใหม่ให้', 'mem.setPwBtn': 'ตั้งรหัสผ่านใหม่', 'mem.newPwPh': 'รหัสผ่านใหม่ อย่างน้อย 8 ตัว',
    'mem.setPwHelp': 'สมาชิกจะถูกออกจากระบบทุกเครื่อง แล้วเข้าใหม่ด้วยรหัสนี้',
    'mem.pwDone': 'ตั้งรหัสผ่านใหม่แล้ว ออกจากระบบทุกเครื่องแล้ว',
    'mem.delete': 'ลบสมาชิก', 'mem.keep': 'ไม่ลบ',
    'mem.delAsk': (n) => `ลบ ${n} ใช่ไหม ประวัติการใช้งานเดิมยังอยู่ แต่บัญชีจะหายไป`,
    'mem.deleted': (n) => `ลบ ${n} แล้ว`, 'mem.added': (n) => `เพิ่ม ${n} แล้ว`, 'mem.saved': 'บันทึกแล้ว',
    'mem.errName': 'ใส่ชื่อที่แสดงก่อน', 'mem.errUser': 'ใส่ชื่อผู้ใช้ก่อน', 'mem.errPw': 'รหัสผ่านต้องมีอย่างน้อย 8 ตัว',
    'mem.errTaken': 'ชื่อผู้ใช้นี้มีคนใช้แล้ว เลือกชื่ออื่น',
    'mem.errSelf': 'ปิดใช้งานหรือเปลี่ยนบทบาทของตัวเองไม่ได้',
    'mem.errSelfDel': 'ลบบัญชีของตัวเองไม่ได้',
    'mem.errLastAdmin': 'นี่คือเจ้าของคนสุดท้ายที่เข้าระบบได้ ตั้งคนอื่นเป็นเจ้าของก่อน',
    'mem.methods': 'วิธีเข้าสู่ระบบ', 'mem.methodsSub': 'Google พาสคีย์ และรหัสผ่าน เฉพาะเจ้าของเปลี่ยนได้',
    'mem.methodsAll': 'Google พาสคีย์ และรหัสผ่าน สำหรับทุกคนที่นี่',
    'mem.pick': 'เลือกสมาชิกทางซ้ายเพื่อแก้ไข',
    'mem.empty': 'ยังไม่มีสมาชิก',
    'mem.yours': 'บัญชีของคุณ', 'mem.others': 'คนอื่นในบ้าน',
  },
});

const ROLES = ['viewer', 'operator', 'admin'];
// list | editor panes: desktop, and Android tablets in landscape (the same 960 px team B's pages use)
const desk = () => matchMedia(isAndroid() ? '(min-width: 960px)' : '(min-width: 1280px)').matches;

/** Server guard messages -> plain language. */
function memErr(e, user) {
  const d = (e && e.detail) || '';
  if (e && e.status === 409) {
    if (/last enabled admin/i.test(d)) return t('mem.errLastAdmin');
    if (/yourself/i.test(d) && /delete/i.test(d)) return t('mem.errSelfDel');
    if (/yourself/i.test(d)) return t('mem.errSelf');
    if (/taken/i.test(d)) return t('mem.errTaken');
    if (/only way to sign in/i.test(d)) return t('mem.errOnlyWay');
  }
  return errorText(e, user);
}

export function render(ctx) {
  ctx.css('views/common.css');
  ctx.css('views/members.css');
  kitCss(ctx);
  const me = ctx.user;
  let users = [];
  let selected = null; // desktop: id shown in the pane

  const android = isAndroid();
  const list = h('div', { class: 'c-card m-list', role: 'list', 'aria-label': t(android ? 'mem.others' : 'mem.list') });
  // Android (A_Members / AT_Members): the signed-in user gets their own card, everyone else a second one
  const mine = android ? h('div', { class: 'c-card m-mine', role: 'list', 'aria-label': t('mem.yours') }) : null;
  const sl = (key) => h('h2', { class: 'm-sl' }, t(key));
  const lists = android ? [sl('mem.yours'), mine, sl('mem.others'), list] : [list];
  const pane = h('section', { class: 'c-card m-pane', 'aria-label': t('mem.edit') }, h('p', { class: 'c-empty' }, t('mem.pick')));
  const plus = iconBtn('plus', t('mem.add'), () => addMember(), 'glassy c-phone-only');
  const actions = [
    h('a', { class: 'btn m-desk-only', href: '#/auth' }, icon('lock', 'sm'), t('mem.methods')),
    h('button', { type: 'button', class: 'btn primary c-large-only', onclick: () => addMember() }, icon('plus', 'sm'), t('mem.add')),
    plus,
  ];
  const methods = card(linkRow({ href: '#/auth', title: t('mem.methods'), sub: t('mem.methodsSub'), lead: tile(icon('lock'), 'plain') }));
  methods.classList.add('m-methods');
  // Android tablets (AT_Members): the same link is a row of the Your account card; members.css picks one by width
  const mineMethods = android ? h('div', { class: 'm-mine-methods', role: 'listitem' },
    linkRow({ href: '#/auth', title: t('mem.methods'), sub: t('mem.methodsAll'), lead: tile(icon('lock'), 'plain') })) : null;
  const head = phoneBack(ctx.header({ title: t('nav.members'), back: { href: '#/account', label: t('nav.account') }, actions }));
  const node = h('div', { class: 'page m-page' },
    head,
    h('div', { class: 'm-grid' }, h('div', { class: 'm-left' }, ...lists, methods), pane));
  fab(ctx, { icon: glyph('user-plus'), label: t('mem.add'), onclick: () => addMember(), replaces: plus });

  function load() {
    return ctx.api('/users', { signal: ctx.signal }).then((r) => {
      users = r;
      if (selected == null || !users.some((u) => u.id === selected)) selected = (users.find((u) => u.id !== me.id) || users[0] || {}).id ?? null;
      fill();
    }).catch((e) => ctx.fail(e));
  }

  function rowOf(u) {
    const self = u.id === me.id;
    const methodsLine = [];
    if (u.google_email) methodsLine.push(h('span', { class: 'm-meth' }, gMark(), u.google_email));
    else methodsLine.push(h('span', { class: 'm-meth' }, icon('key', 'xs'), t('mem.password')));
    if (u.has_passkey) {
      const pk = h('span', { class: 'm-meth m-pk', role: 'img', 'aria-label': t('mem.hasPk') }, icon('passkey', 'xs'));
      tip(pk, t('mem.hasPk'));
      methodsLine.push(pk);
    }
    const seen = u.disabled ? t('mem.cantSign') : u.last_login_at ? t('mem.lastActive', fmtWhen(u.last_login_at)) : t('mem.never');
    const right = u.disabled ? badge(t('mem.disabled'), 'danger') : u.role === 'admin' ? badge(roleLabel('admin')) : badge(roleLabel(u.role), 'plain');
    const b = h('button', {
      type: 'button', class: 'm-row', role: 'listitem', 'aria-current': desk() && u.id === selected ? 'true' : null,
      onclick: () => open(u.id),
    },
    h('span', { class: 'avatar', style: toneStyle(u.id), 'aria-hidden': 'true' }, initialOf(u.display_name)),
    h('span', { class: 'm-tx' },
      h('span', { class: 'm-name' }, u.display_name, self ? ` ${t('mem.you')}` : ''),
      h('span', { class: 'm-seen' }, h('b', {}, u.username), ' ', seen),
      h('span', { class: 'm-meths' }, methodsLine)),
    right, h('span', { class: 'm-chev', 'aria-hidden': 'true' }, icon('chev-right', 'sm')));
    return b;
  }

  function paintList() {
    const off = users.filter((u) => u.disabled).length;
    headerSub(head, !users.length ? '' : off ? t('mem.ctxOff', users.length, off) : t('mem.ctxAll', users.length));
    const shown = android ? users.filter((u) => u.id !== me.id) : users;
    list.replaceChildren(...(shown.length ? shown.map(rowOf) : [h('p', { class: 'c-empty' }, t('mem.empty'))]));
    if (!android) return;
    const self = users.find((u) => u.id === me.id);
    mine.replaceChildren(...(self ? [rowOf(self), mineMethods] : []));
    mine.hidden = !self;
    mine.previousElementSibling.hidden = !self;
  }

  function fill() {
    paintList();
    const u = users.find((x) => x.id === selected);
    pane.replaceChildren(u ? editor(u, {}) : h('p', { class: 'c-empty' }, t('mem.pick')));
  }

  function open(id) {
    selected = id;
    if (desk()) { fill(); const f = pane.querySelector('input'); if (f) f.focus({ preventScroll: true }); return; }
    const u = users.find((x) => x.id === id);
    // Android phones: full-screen dialog with Save in its top bar (the editor's own Save button is hidden there)
    const dlg = fullDialog(ctx, { title: u.display_name, build: (body, d) => {
      const ed = editor(u, { sheet: d });
      d.saveBtn.type = 'button';
      d.saveBtn.addEventListener('click', () => ed.querySelector('.m-save .btn').click());
      body.append(ed);
    } });
    if (!dlg) ctx.sheet({ title: u.display_name, build: (body, s) => body.append(editor(u, { sheet: s })) });
  }

  function replaceUser(nu) {
    users = users.map((u) => (u.id === nu.id ? nu : u));
    fill();
  }

  /* ---------- the editor (sheet on phone/iPad, pane on desktop) ---------- */
  function editor(u, { sheet }) {
    const self = u.id === me.id;
    const err = h('p', { class: 'form-error', role: 'alert' });
    const wrap = h('div', { class: 'm-ed' });

    const nameIn = h('input', { class: 'input', value: u.display_name, maxLength: 64, autocomplete: 'off' });
    let role = u.role;
    const roleHelp = h('p', { class: 'small' }, t(`mem.help.${role}`));
    const roleCtl = self
      ? h('div', {}, h('p', { class: 'm-role-self' }, roleLabel(u.role)), h('p', { class: 'small' }, t('mem.selfRole')))
      : segmented({ label: t('mem.role'), value: role, options: ROLES.map((r) => ({ value: r, label: roleLabel(r) })), onChange: (v) => { role = v; roleHelp.textContent = t(`mem.help.${v}`); } });
    const save = h('button', { type: 'button', class: 'btn primary' }, t('common.save'));
    save.addEventListener('click', () => {
      const name = nameIn.value.trim();
      if (!name) { err.textContent = t('mem.errName'); nameIn.setAttribute('aria-invalid', 'true'); nameIn.focus(); return; }
      nameIn.removeAttribute('aria-invalid');
      const body = {};
      if (name !== u.display_name) body.display_name = name;
      if (!self && role !== u.role) body.role = role;
      if (!Object.keys(body).length) { if (sheet) sheet.close(); return; }
      err.textContent = '';
      busy(save, async () => {
        try {
          const nu = await ctx.api(`/users/${u.id}`, { method: 'PATCH', body });
          if (sheet) { sheet.close(); toast(t('mem.saved'), 'ok'); } // the desktop pane shows the change in place
          replaceUser(nu);
        } catch (e) { err.textContent = memErr(e, me); }
      });
    });

    const head = sheet ? null : h('div', { class: 'm-ed-head' },
      h('span', { class: 'avatar lg', style: toneStyle(u.id), 'aria-hidden': 'true' }, initialOf(u.display_name)),
      h('div', { class: 'm-ed-ht' }, h('p', { class: 'm-ed-name' }, u.display_name), h('p', { class: 'small' }, t('mem.usernameLine', u.username))),
      isAndroid() ? save : null);

    /* sign-in: read-only for yourself (Account changes those); for others, Unlink Google / Remove a passkey */
    const passkeyOn = (ctx.auth && ctx.auth.methods && ctx.auth.methods.passkey) || u.has_passkey;
    const signIn = self
      ? h('div', { class: 'm-sec' }, h('p', { class: 'm-lab' }, t('mem.signIn')),
        h('ul', { class: 'm-facts' },
          h('li', {}, icon('key', 'xs'), t('mem.viaPw', u.username)),
          u.google_email ? h('li', {}, gMark(), t('mem.viaGoogle', u.google_email)) : null,
          passkeyOn ? h('li', {}, icon('passkey', 'xs'), t(u.has_passkey ? 'mem.hasPk' : 'mem.noPk')) : null),
        h('p', { class: 'small' }, t('mem.selfLinks')))
      : resetSec(u, passkeyOn);

    /* disable */
    let disableRow = null;
    if (!self) {
      const dErr = h('span', { class: 'c-sub err', role: 'alert' });
      const sub = h('span', {}, t(u.disabled ? 'mem.disableOn' : 'mem.disableOff'));
      const sw = switchInput(u.disabled, async (on) => {
        dErr.textContent = '';
        sw.disabled = true;
        try {
          const nu = await ctx.api(`/users/${u.id}`, { method: 'PATCH', body: { disabled: on } });
          Object.assign(u, nu);
          sub.textContent = t(on ? 'mem.disableOn' : 'mem.disableOff');
          users = users.map((x) => (x.id === nu.id ? nu : x));
          paintList();
        } catch (e) { sw.checked = !on; dErr.textContent = memErr(e, me); }
        sw.disabled = false;
      });
      disableRow = settingRow({ title: t('mem.disable'), sub: h('span', {}, sub, ' ', dErr), control: sw, cls: 'm-flat' });
    }

    /* new password */
    const pw = passwordInput({ autocomplete: 'new-password', placeholder: t('mem.newPwPh'), 'aria-label': t('mem.setPw') });
    const pwNote = h('p', { class: 'small', role: 'status' }, t('mem.setPwHelp'));
    const pwBtn = h('button', { type: 'button', class: 'btn tonal' }, t('mem.setPwBtn'));
    pwBtn.addEventListener('click', () => {
      if (pw.input.value.length < 8) { pwNote.textContent = t('mem.errPw'); pwNote.className = 'small form-error'; pw.input.setAttribute('aria-invalid', 'true'); pw.input.focus(); return; }
      pw.input.removeAttribute('aria-invalid');
      busy(pwBtn, async () => {
        try {
          await ctx.api(`/users/${u.id}`, { method: 'PATCH', body: { password: pw.input.value } });
          pw.input.value = '';
          pwNote.className = 'small';
          pwNote.textContent = t('mem.pwDone');
        } catch (e) { pwNote.className = 'small form-error'; pwNote.textContent = memErr(e, me); }
      });
    });
    const pwSec = h('div', { class: 'm-sec' }, h('p', { class: 'm-lab' }, t('mem.setPw')), h('div', { class: 'c-inline m-pw' }, pw.wrap, pwBtn), pwNote);

    /* delete */
    let delSec = null;
    if (!self) {
      const delErr = h('p', { class: 'form-error', role: 'alert' });
      const delBtn = h('button', { type: 'button', class: 'btn m-del' }, t('mem.delete'));
      const confirm = h('div', { class: 'c-confirm', hidden: true });
      const yes = h('button', { type: 'button', class: 'btn danger' }, t('mem.delete'));
      const no = h('button', { type: 'button', class: 'btn', onclick: () => { confirm.hidden = true; delBtn.hidden = false; delBtn.focus(); } }, t('mem.keep'));
      confirm.append(h('p', {}, t('mem.delAsk', u.display_name)), h('div', { class: 'c-actions' }, yes, no));
      delBtn.addEventListener('click', () => { delBtn.hidden = true; confirm.hidden = false; no.focus(); });
      yes.addEventListener('click', () => busy(yes, async () => {
        try {
          await ctx.api(`/users/${u.id}`, { method: 'DELETE' });
          toast(t('mem.deleted', u.display_name), 'ok');
          if (sheet) sheet.close();
          users = users.filter((x) => x.id !== u.id);
          if (selected === u.id) selected = (users.find((x) => x.id !== me.id) || users[0] || {}).id ?? null;
          fill();
        } catch (e) { delErr.textContent = memErr(e, me); }
      }));
      delSec = h('div', { class: 'm-sec' }, delBtn, confirm, delErr);
    }

    append(wrap, [
      head,
      field(t('mem.displayName'), nameIn),
      h('div', { class: 'm-sec' }, h('p', { class: 'm-lab' }, t('mem.role')), roleCtl, self ? null : roleHelp),
      // Android tablet pane: Save sits in the head, next to the name (AT_Members)
      h('div', { class: 'm-save' }, err, head && isAndroid() ? null : save),
      signIn, disableRow, pwSec, delSec]);
    return wrap;
  }

  /* Sign-in methods of another member, each Google / passkey row with its own remove button and an inline confirm
     (the Delete member pattern). Removing one signs them out of every device; their password keeps working. */
  function resetSec(u, passkeyOn) {
    const facts = h('ul', { class: 'm-facts m-reset' }, h('li', {}, icon('key', 'xs'), h('span', { class: 'm-ft' }, t('mem.viaPw', u.username))));
    const rErr = h('p', { class: 'form-error', role: 'alert' });
    const confirm = h('li', { class: 'm-cf' });
    let open = null; // the row whose confirm is showing
    const closeConfirm = () => { if (!open) return; open.btn.hidden = false; confirm.remove(); open = null; };
    const row = (mark, text, label, ask, run) => {
      const btn = h('button', { type: 'button', class: 'btn m-del' }, label);
      const li = h('li', {}, mark, h('span', { class: 'm-ft' }, text), btn);
      btn.addEventListener('click', () => {
        closeConfirm();
        rErr.textContent = '';
        const yes = h('button', { type: 'button', class: 'btn danger' }, label);
        const no = h('button', { type: 'button', class: 'btn', onclick: () => { closeConfirm(); btn.focus(); } }, t('mem.keepIt'));
        yes.addEventListener('click', () => busy(yes, async () => {
          try { await run(li); closeConfirm(); } catch (e) { rErr.textContent = memErr(e, me); }
        }));
        confirm.replaceChildren(h('div', { class: 'c-confirm' }, h('p', {}, ask), h('div', { class: 'c-actions' }, yes, no)));
        btn.hidden = true;
        li.after(confirm);
        open = { btn };
        no.focus();
      });
      return li;
    };
    const touch = (nu) => { Object.assign(u, nu); users = users.map((x) => (x.id === u.id ? { ...x, ...nu } : x)); paintList(); };
    if (u.google_email) {
      facts.append(row(gMark(), t('mem.gLine', u.google_email), t('mem.unlink'), t('mem.gAsk', u.display_name), async (li) => {
        const nu = await ctx.api(`/users/${u.id}/google`, { method: 'DELETE' });
        li.remove();
        touch(nu);
        toast(t('mem.gDone', u.display_name), 'ok');
      }));
    }
    const pkSlot = h('li', { hidden: !passkeyOn }, icon('passkey', 'xs'), h('span', { class: 'm-ft' }, t(u.has_passkey ? 'mem.hasPk' : 'mem.noPk')));
    facts.append(pkSlot);
    if (u.has_passkey) {
      ctx.api(`/users/${u.id}/passkeys`).then((list) => {
        let left = list.length;
        const rows = list.map((p) => {
          const when = p.last_used_at ? t('mem.pkUsed', fmtWhen(p.last_used_at)) : t('mem.pkNever');
          return row(icon('passkey', 'xs'), t('mem.pkLine', p.name, when), t('mem.remove'), t('mem.pkAsk', u.display_name, p.name), async (li) => {
            await ctx.api(`/users/${u.id}/passkeys/${p.id}`, { method: 'DELETE' });
            li.remove();
            left -= 1;
            if (!left) { pkSlot.lastChild.textContent = t('mem.noPk'); pkSlot.hidden = false; }
            touch({ has_passkey: left > 0 });
            toast(t('mem.pkDone', u.display_name, p.name), 'ok');
          });
        });
        if (rows.length) { pkSlot.hidden = true; pkSlot.after(...rows); }
      }).catch((e) => { rErr.textContent = memErr(e, me); });
    }
    return h('div', { class: 'm-sec' }, h('p', { class: 'm-lab' }, t('mem.signIn')), facts, rErr, h('p', { class: 'small' }, t('mem.resetNote')));
  }

  /* ---------- add member ---------- */
  function addMember() {
    // Android phones: a full-screen dialog whose top-bar button submits the form; elsewhere a sheet / dialog
    const opts = {
      title: t('mem.add'),
      save: t('mem.addShort'),
      build(body, s) {
        const name = h('input', { class: 'input', placeholder: t('mem.namePh'), maxLength: 64, autocomplete: 'off' });
        const user = h('input', { class: 'input', placeholder: t('mem.userPh'), autocapitalize: 'none', spellcheck: false, autocomplete: 'off', maxLength: 32 });
        const pw = passwordInput({ autocomplete: 'new-password', placeholder: t('mem.min8') });
        let role = 'operator';
        const help = h('p', { class: 'small' }, t(`mem.help.${role}`));
        const seg = segmented({ label: t('mem.role'), value: role, options: ROLES.map((r) => ({ value: r, label: roleLabel(r) })), onChange: (v) => { role = v; help.textContent = t(`mem.help.${v}`); } });
        const err = h('p', { class: 'form-error', role: 'alert' });
        const go = h('button', { type: 'submit', class: 'btn primary big wide' }, t('mem.add'));
        const form = h('form', { class: 'm-add', novalidate: true }, field(t('mem.displayName'), name), field(t('mem.username'), user),
          field(t('mem.startPw'), pw.wrap), h('div', { class: 'm-sec' }, h('p', { class: 'm-lab' }, t('mem.role')), seg, help), err, go);
        if (s.bindForm) { s.bindForm(form); go.hidden = true; }
        form.addEventListener('submit', (e) => {
          e.preventDefault();
          const u = user.value.trim().toLowerCase();
          const bad = !name.value.trim() ? [name, 'mem.errName'] : !u ? [user, 'mem.errUser'] : pw.input.value.length < 8 ? [pw.input, 'mem.errPw'] : null;
          [name, user, pw.input].forEach((x) => x.removeAttribute('aria-invalid'));
          if (bad) { err.textContent = t(bad[1]); bad[0].setAttribute('aria-invalid', 'true'); bad[0].focus(); return; }
          err.textContent = '';
          busy(s.saveBtn || go, async () => {
            try {
              const nu = await ctx.api('/users', { body: { display_name: name.value.trim(), username: u, password: pw.input.value, role } });
              s.close();
              toast(t('mem.added', nu.display_name), 'ok');
              users = [...users, nu];
              selected = nu.id;
              fill();
            } catch (e2) {
              err.textContent = memErr(e2, me);
              if (e2.status === 409) user.setAttribute('aria-invalid', 'true');
            }
          });
        });
        body.append(form);
      },
    };
    if (!fullDialog(ctx, opts)) ctx.sheet(opts);
  }

  load();
  return { node };
}
