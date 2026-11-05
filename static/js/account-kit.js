// Account pieces shared by views/account.js (phone Account page) and views/prefs.js (iPad/desktop
// "Account & app settings"): profile + display name, linked Google account, passkeys, app preferences.
// Server: GET /auth/state (fresh user + methods), PATCH /users/{me} (display name; owners only — there is no
// self-service name endpoint), POST/DELETE /me/google, GET/PATCH/DELETE /me/passkeys*, POST /me/passkeys(/options),
// GET /me/export (download my data), DELETE /me (delete my account).
import { h, icon, busy, segmented, toast, field, helpLink, tip } from './ui.js';
import { register, t, roleLabel } from './i18n.js';
import { errorText } from './api.js';
import { get as getPref, set as setPref, motionReduced, onChange as onPrefs } from './prefs.js';
import { googleCredential } from './signin.js';
import { createPasskey, createError, passkeyCapable, deviceName } from './passkey-offer.js';
import { glyph } from './icons.js';
import { caption, card, badge, tile, gMark, fmtDay, fmtWhen, toneStyle, initialOf, settingRow, linkRow, switchInput } from './kit.js';
import { hearing as hearTalkie, setHearing as setHearTalkie } from './talkie.js';

register({
  en: {
    'ca.username': (u) => `Username ${u}`, 'ca.displayName': 'Display name', 'ca.nameHelp': 'Shown to other members and in Activity.',
    'ca.nameSaved': 'Name saved', 'ca.errName': 'Enter a display name first', 'ca.editName': 'Edit display name',
    'ca.password': 'Password', 'ca.pwSub': 'Changing it signs out your other devices.',
    'ca.google': 'Google account', 'ca.gLinkedTitle': 'Linked Google account', 'ca.gNone': 'Not linked',
    'ca.gLink': 'Link', 'ca.gUnlink': 'Unlink', 'ca.gLinked': 'Google account linked', 'ca.gUnlinked': 'Google account unlinked',
    'ca.gUnlinkAsk': (e) => `Unlink ${e}? After this you sign in with your username and password.`,
    'ca.gOnly': 'Google is your only way to sign in, so it can\'t be unlinked yet. Set a password or add a passkey first.',
    'ca.gTaken': 'That Google account is already linked to another member.',
    'ca.gUnavailable': 'Google didn\'t load. Check the internet connection and try again.',
    'ca.gOff': 'Google sign-in is turned off. You can still unlink it.',
    'ca.gTitle': 'Link your Google account',
    'ca.passkeys': 'Passkeys', 'ca.pkNone': 'No passkeys yet', 'ca.pkAdd': 'Add passkey', 'ca.edit': 'Edit',
    'ca.editAria': (n) => `Edit passkey ${n}`,
    'ca.pkFoot': 'Sign in with your fingerprint, face or device PIN instead of a password.',
    'ca.pkNoSupport': 'This browser can\'t create a passkey here. Passkeys need the secure (https) address of this app.',
    'ca.pkWhy': 'Why', 'ca.pkSub': (c, u) => `Created ${c}, ${u ? `last used ${u}` : 'not used yet'}`,
    'ca.pkName': 'Name', 'ca.pkNameEmpty': 'Give the passkey a name first',
    'ca.pkRemove': 'Remove passkey', 'ca.pkRemoveBtn': 'Remove',
    'ca.pkRemoveAsk': (n) => `Remove ${n}? You can't sign in here with it anymore. Also delete it from the password manager on that device.`,
    'ca.pkLast': 'This passkey is your only way to sign in, so it can\'t be removed yet. Set a password or add another passkey first.',
    'ca.pkOwnerKeep': 'Owners have to keep at least one passkey while the owner requires them.',
    'ca.pkAdded': 'Passkey added', 'ca.pkRenamed': 'Passkey renamed', 'ca.pkRemoved': 'Passkey removed',
    'ca.lang': 'Language', 'ca.langHelp': 'App language. Announcements keep their own language.',
    'ca.theme': 'Appearance', 'ca.themeHelp': 'Applies right away on this device.',
    'ca.th.system': 'System', 'ca.th.light': 'Light', 'ca.th.dark': 'Dark',
    'ca.motion': 'Reduce motion', 'ca.m.system': 'Follow system', 'ca.m.on': 'On', 'ca.m.off': 'Off',
    'ca.mHelpSys': (on) => (on ? 'Your device asks for less motion, so animations are off.' : 'Your device allows motion, so animations are on.'),
    'ca.mHelpOn': 'Animations are off in this app.', 'ca.mHelpOff': 'Animations are on in this app.',
    'ca.tour': 'Show quick tour again', 'ca.tourSub': 'A short walk through Now playing and the main pages.',
    'ca.talkie': 'Hear Talkie on this device', 'ca.talkieSub': 'Play other members’ Walkie talks live while the Walkie is open here.',
    'ca.deviceOnly': 'Saved on this device only.',
    'ca.data': 'Your data',
    'ca.dl': 'Download my data', 'ca.dlSub': 'A JSON file of your profile, playlists, file list, followed shows and activity',
    'ca.dlBtn': 'Download', 'ca.dlDone': (f) => `Downloaded ${f}`,
    'ca.del': 'Delete my account', 'ca.delSub': 'Removes your account and everything personal. This can\'t be undone.',
    'ca.delBtn': 'Delete account…', 'ca.delTitle': 'Delete your account?',
    'ca.delGone': 'This removes for good: your sign-in on every device (password, passkeys, linked Google account), your personal playlists and files, followed shows and voice messages.',
    'ca.delStays': 'Shared playlists, files and schedules you made stay for everyone. Download your data first if you want a copy.',
    'ca.delType': (u) => `Type your username (${u}) to confirm`, 'ca.delWrong': 'That isn\'t your username.',
    'ca.deleted': 'Your account was deleted',
    'ca.lastTitle': 'Can\'t delete this account yet',
    'ca.last': 'You\'re the only owner. Make another member an owner first, then you can delete your account.',
    'ca.lastMembers': 'Open Members',
  },
  th: {
    'ca.username': (u) => `ชื่อผู้ใช้ ${u}`, 'ca.displayName': 'ชื่อที่แสดง', 'ca.nameHelp': 'สมาชิกคนอื่นเห็นชื่อนี้ และแสดงในประวัติการใช้งาน',
    'ca.nameSaved': 'บันทึกชื่อแล้ว', 'ca.errName': 'ใส่ชื่อที่แสดงก่อน', 'ca.editName': 'แก้ชื่อที่แสดง',
    'ca.password': 'รหัสผ่าน', 'ca.pwSub': 'เปลี่ยนแล้ว อุปกรณ์อื่นที่เข้าบัญชีนี้อยู่จะถูกออกจากระบบ',
    'ca.google': 'บัญชี Google', 'ca.gLinkedTitle': 'บัญชี Google ที่เชื่อมไว้', 'ca.gNone': 'ยังไม่ได้เชื่อม',
    'ca.gLink': 'เชื่อม', 'ca.gUnlink': 'เลิกเชื่อม', 'ca.gLinked': 'เชื่อมบัญชี Google แล้ว', 'ca.gUnlinked': 'เลิกเชื่อมบัญชี Google แล้ว',
    'ca.gUnlinkAsk': (e) => `เลิกเชื่อม ${e} ใช่ไหม หลังจากนี้เข้าสู่ระบบด้วยชื่อผู้ใช้และรหัสผ่าน`,
    'ca.gOnly': 'Google เป็นทางเดียวที่คุณใช้เข้าสู่ระบบ จึงยังเลิกเชื่อมไม่ได้ ตั้งรหัสผ่านหรือเพิ่มพาสคีย์ก่อน',
    'ca.gTaken': 'บัญชี Google นี้เชื่อมกับสมาชิกคนอื่นอยู่แล้ว',
    'ca.gUnavailable': 'โหลด Google ไม่ได้ ตรวจการต่ออินเทอร์เน็ตแล้วลองอีกครั้ง',
    'ca.gOff': 'ปิดการเข้าสู่ระบบด้วย Google อยู่ ยังเลิกเชื่อมได้',
    'ca.gTitle': 'เชื่อมบัญชี Google',
    'ca.passkeys': 'พาสคีย์', 'ca.pkNone': 'ยังไม่มีพาสคีย์', 'ca.pkAdd': 'เพิ่มพาสคีย์', 'ca.edit': 'แก้ไข',
    'ca.editAria': (n) => `แก้ไขพาสคีย์ ${n}`,
    'ca.pkFoot': 'เข้าสู่ระบบด้วยลายนิ้วมือ ใบหน้า หรือ PIN ของเครื่อง แทนการพิมพ์รหัสผ่าน',
    'ca.pkNoSupport': 'เบราว์เซอร์นี้สร้างพาสคีย์ที่นี่ไม่ได้ พาสคีย์ต้องใช้ที่อยู่แบบปลอดภัย (https) ของแอปนี้',
    'ca.pkWhy': 'ดูเหตุผลในคู่มือ', 'ca.pkSub': (c, u) => `สร้าง ${c} ${u ? `ใช้ล่าสุด${u}` : 'ยังไม่เคยใช้'}`,
    'ca.pkName': 'ชื่อ', 'ca.pkNameEmpty': 'ตั้งชื่อพาสคีย์ก่อน',
    'ca.pkRemove': 'ลบพาสคีย์', 'ca.pkRemoveBtn': 'ลบ',
    'ca.pkRemoveAsk': (n) => `ลบ ${n} ใช่ไหม จะใช้พาสคีย์นี้เข้าสู่ระบบที่นี่ไม่ได้อีก ลบออกจากที่เก็บรหัสผ่านในเครื่องนั้นด้วย`,
    'ca.pkLast': 'พาสคีย์นี้เป็นทางเดียวที่คุณใช้เข้าสู่ระบบ จึงยังลบไม่ได้ ตั้งรหัสผ่านหรือเพิ่มพาสคีย์อีกอันก่อน',
    'ca.pkOwnerKeep': 'เจ้าของต้องมีพาสคีย์อย่างน้อยหนึ่งอัน ระหว่างที่กำหนดให้ผู้ดูแลต้องใช้พาสคีย์',
    'ca.pkAdded': 'เพิ่มพาสคีย์แล้ว', 'ca.pkRenamed': 'เปลี่ยนชื่อพาสคีย์แล้ว', 'ca.pkRemoved': 'ลบพาสคีย์แล้ว',
    'ca.lang': 'ภาษา', 'ca.langHelp': 'ภาษาของแอป ประกาศใช้ภาษาของตัวเองแยกไว้',
    'ca.theme': 'ลักษณะ', 'ca.themeHelp': 'ใช้ทันทีบนอุปกรณ์นี้',
    'ca.th.system': 'ตามระบบ', 'ca.th.light': 'สว่าง', 'ca.th.dark': 'มืด',
    'ca.motion': 'ลดการเคลื่อนไหว', 'ca.m.system': 'ตามระบบ', 'ca.m.on': 'เปิด', 'ca.m.off': 'ปิด',
    'ca.mHelpSys': (on) => (on ? 'เครื่องนี้ตั้งให้ลดการเคลื่อนไหว ภาพเคลื่อนไหวจึงปิดอยู่' : 'เครื่องนี้ไม่ได้ลดการเคลื่อนไหว ภาพเคลื่อนไหวจึงเปิดอยู่'),
    'ca.mHelpOn': 'ภาพเคลื่อนไหวในแอปปิดอยู่', 'ca.mHelpOff': 'ภาพเคลื่อนไหวในแอปเปิดอยู่',
    'ca.tour': 'ดูทัวร์แนะนำอีกครั้ง', 'ca.tourSub': 'พาดูหน้าเล่นอยู่และหน้าหลักต่าง ๆ แบบสั้น ๆ',
    'ca.talkie': 'ฟังทอล์คกี้บนอุปกรณ์นี้', 'ca.talkieSub': 'เล่นเสียงวอล์กกี้ของสมาชิกคนอื่นสดๆ ขณะเปิดวอล์กกี้บนเครื่องนี้',
    'ca.deviceOnly': 'บันทึกไว้เฉพาะในอุปกรณ์นี้',
    'ca.data': 'ข้อมูลของคุณ',
    'ca.dl': 'ดาวน์โหลดข้อมูลของฉัน', 'ca.dlSub': 'ไฟล์ JSON ของโปรไฟล์ เพลย์ลิสต์ รายชื่อไฟล์ รายการที่ติดตาม และประวัติการใช้งานของคุณ',
    'ca.dlBtn': 'ดาวน์โหลด', 'ca.dlDone': (f) => `ดาวน์โหลด ${f} แล้ว`,
    'ca.del': 'ลบบัญชีของฉัน', 'ca.delSub': 'ลบบัญชีและทุกอย่างที่เป็นของคุณ ย้อนกลับไม่ได้',
    'ca.delBtn': 'ลบบัญชี…', 'ca.delTitle': 'ลบบัญชีของคุณไหม',
    'ca.delGone': 'สิ่งที่จะถูกลบถาวร: การเข้าสู่ระบบทุกแบบในทุกอุปกรณ์ (รหัสผ่าน พาสคีย์ บัญชี Google ที่ผูกไว้) เพลย์ลิสต์และไฟล์ส่วนตัว รายการที่ติดตาม และข้อความเสียง',
    'ca.delStays': 'เพลย์ลิสต์ ไฟล์ และตารางเวลาที่แชร์ไว้ยังอยู่ให้ทุกคนใช้ ถ้าอยากเก็บสำเนา ดาวน์โหลดข้อมูลก่อน',
    'ca.delType': (u) => `พิมพ์ชื่อผู้ใช้ของคุณ (${u}) เพื่อยืนยัน`, 'ca.delWrong': 'ชื่อผู้ใช้ไม่ตรงกับบัญชีของคุณ',
    'ca.deleted': 'ลบบัญชีของคุณแล้ว',
    'ca.lastTitle': 'ยังลบบัญชีนี้ไม่ได้',
    'ca.last': 'คุณเป็นเจ้าของคนเดียว ตั้งสมาชิกคนอื่นเป็นเจ้าของก่อน แล้วจึงลบบัญชีของคุณได้',
    'ca.lastMembers': 'ไปที่สมาชิก',
  },
});

/** Fresh GET /auth/state (the user's Google link and passkeys change while the app runs); falls back to ctx.auth. */
export async function freshAuth(ctx) {
  try { return await ctx.api('/auth/state', { signal: ctx.signal }); } catch (e) { if (e.name === 'AbortError') throw e; return ctx.auth || {}; }
}

/** Avatar, name (with the pencil when ctx is given), username and role. */
export function profileHead(user, ctx) {
  return h('div', { class: 'ca-head' },
    h('span', { class: 'avatar lg', style: toneStyle(user.id), 'aria-hidden': 'true' }, initialOf(user.display_name)),
    h('div', { class: 'ca-head-tx' }, ctx ? nameLine(ctx, user) : h('p', { class: 'ca-name' }, user.display_name), h('p', { class: 'small' }, t('ca.username', user.username))),
    badge(roleLabel(user.role), user.role === 'admin' ? '' : 'plain'));
}

/** The name with a pencil beside it; any member renames themselves in a sheet (PATCH /me), like a passkey. */
export function nameLine(ctx, user) {
  const label = t('ca.editName');
  const pen = h('button', { type: 'button', class: 'iconbtn ca-pen', 'aria-label': label, onclick: () => editName(ctx, user) }, glyph('pencil'));
  tip(pen, label);
  return h('div', { class: 'ca-nameline' }, h('p', { class: 'ca-name' }, user.display_name), pen);
}

function editName(ctx, user) {
  ctx.sheet({
    title: t('ca.displayName'),
    build(body, s) {
      const input = h('input', { class: 'input', value: user.display_name, maxLength: 64, autocomplete: 'name' });
      const err = h('p', { class: 'form-error', role: 'alert' });
      const save = h('button', { type: 'submit', class: 'btn primary big wide' }, t('common.save'));
      const form = h('form', { novalidate: true, class: 'ca-form' }, field(t('ca.displayName'), input, t('ca.nameHelp')), err, save);
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        const v = input.value.trim();
        if (!v) { err.textContent = t('ca.errName'); input.setAttribute('aria-invalid', 'true'); input.focus(); return; }
        if (v === user.display_name) { s.close(); return; }
        busy(save, async () => {
          try {
            const nu = await ctx.api('/me', { method: 'PATCH', body: { display_name: v } });
            s.close();
            toast(t('ca.nameSaved'), 'ok');
            ctx.signedIn(Object.assign(ctx.user, nu)); // rebuilds the shell so the sidebar and this page show the new name
          } catch (e2) { err.textContent = errorText(e2, ctx.user); }
        });
      });
      body.append(form);
      requestAnimationFrame(() => { input.focus(); input.select(); });
    },
  });
}

/* ---------- Google ---------- */
/** Linked Google account row with Link/Unlink, or null when Google is off and nothing is linked. */
export function googleRow(ctx, auth, user, { title = t('ca.google') } = {}) {
  const on = !!(auth.methods && auth.methods.google && auth.google_client_id);
  if (!on && !user.google_email) return null;
  const sub = h('span', {});
  const msg = h('span', { class: 'c-sub err', role: 'alert' });
  const btn = h('button', { type: 'button', class: 'btn' });
  const row = settingRow({ title, sub: h('span', {}, sub, msg), control: btn, lead: tile(gMark(), 'plain'), cls: 'ca-g' });
  const paint = () => {
    sub.textContent = user.google_email || t('ca.gNone');
    btn.textContent = t(user.google_email ? 'ca.gUnlink' : 'ca.gLink');
    btn.className = user.google_email ? 'btn ca-danger' : 'btn tonal';
    btn.hidden = !user.google_email && !on;
    if (!on && user.google_email) msg.textContent = t('ca.gOff');
  };
  btn.addEventListener('click', () => { msg.textContent = ''; return user.google_email ? unlink() : link(); });
  async function link() {
    let sheet = null;
    await busy(btn, async () => {
      try {
        const credential = await googleCredential(auth.google_client_id, (renderInto, cancel) => {
          sheet = ctx.sheet({ title: t('ca.gTitle'), onClose: () => cancel(), build(body) { const slot = h('div', { class: 'gsi-slot' }); body.append(slot); requestAnimationFrame(() => renderInto(slot)); } });
        });
        if (sheet) sheet.close();
        const nu = await ctx.api('/me/google', { body: { credential } });
        user.google_email = nu.google_email;
        toast(t('ca.gLinked'), 'ok');
      } catch (e) {
        if (sheet) sheet.close();
        if (e.message === 'cancelled') return;
        if (e.message && e.message.startsWith('gsi-')) { msg.textContent = t('ca.gUnavailable'); return; }
        msg.textContent = e.status === 409 && /another/i.test(e.detail) ? t('ca.gTaken') : errorText(e, ctx.user);
      }
    }).catch(() => {});
    paint();
  }
  function unlink() {
    ctx.sheet({
      title: t('ca.gUnlink'),
      build(body, s) {
        const err = h('p', { class: 'form-error', role: 'alert' });
        const go = h('button', { type: 'button', class: 'btn danger big wide' }, t('ca.gUnlink'));
        go.addEventListener('click', () => busy(go, async () => {
          try {
            const nu = await ctx.api('/me/google', { method: 'DELETE' });
            user.google_email = nu.google_email;
            s.close();
            toast(t('ca.gUnlinked'), 'ok');
            paint();
          } catch (e) { err.textContent = e.status === 409 ? t('ca.gOnly') : errorText(e, ctx.user); }
        }));
        body.append(h('p', { class: 'muted' }, t('ca.gUnlinkAsk', user.google_email)), err, go,
          h('button', { type: 'button', class: 'btn big wide', onclick: () => s.close() }, t('common.cancel')));
      },
    });
  }
  paint();
  return row;
}

/* ---------- passkeys ---------- */
/** { card, note } for the Passkeys section, or null when the server doesn't offer passkeys. */
export function passkeySection(ctx, auth) {
  if (!(auth.methods && auth.methods.passkey)) return null;
  const canCreate = passkeyCapable(auth);
  const list = h('div', { class: 'ca-pks' });
  const addErr = h('p', { class: 'form-error ca-pad', role: 'alert' });
  const add = canCreate ? h('button', { type: 'button', class: 'c-row c-link ca-add' }, h('span', { class: 'c-tile plain', 'aria-hidden': 'true' }, icon('plus', 'sm')), h('span', { class: 'c-title' }, t('ca.pkAdd'))) : null;
  let keys = [];
  if (add) {
    add.addEventListener('click', () => busy(add, async () => {
      addErr.textContent = '';
      try {
        await createPasskey(ctx.api, deviceName());
        toast(t('ca.pkAdded'), 'ok');
        await load();
      } catch (e) { addErr.textContent = createError(e, ctx.user); }
    }).catch(() => {}));
  }
  const box = card(list, add, addErr);
  const note = canCreate ? h('p', { class: 'c-note' }, t('ca.pkFoot'))
    : h('p', { class: 'c-note' }, t('ca.pkNoSupport'), ' ', helpLink('passkey', t('ca.pkWhy')));

  function rowOf(p) {
    const edit = h('button', { type: 'button', class: 'btn', 'aria-label': t('ca.editAria', p.name), onclick: () => editKey(p) }, t('ca.edit'));
    return settingRow({ title: p.name, sub: t('ca.pkSub', fmtDay(p.created_at), p.last_used_at ? fmtWhen(p.last_used_at) : ''), control: edit, lead: tile(icon('passkey')) });
  }
  function draw() {
    list.replaceChildren(...(keys.length ? keys.map(rowOf) : [h('p', { class: 'c-row c-sub' }, t('ca.pkNone'))]));
  }
  async function load() {
    try { keys = await ctx.api('/me/passkeys', { signal: ctx.signal }); } catch (e) { ctx.fail(e); }
    draw();
  }
  function editKey(p) {
    ctx.sheet({
      title: p.name,
      build(body, s) {
        const name = h('input', { class: 'input', value: p.name, maxLength: 64 });
        const err = h('p', { class: 'form-error', role: 'alert' });
        const save = h('button', { type: 'submit', class: 'btn primary big wide' }, t('common.save'));
        const form = h('form', { novalidate: true, class: 'ca-form' }, field(t('ca.pkName'), name), err, save);
        form.addEventListener('submit', (e) => {
          e.preventDefault();
          const v = name.value.trim();
          if (!v) { err.textContent = t('ca.pkNameEmpty'); name.setAttribute('aria-invalid', 'true'); return; }
          if (v === p.name) { s.close(); return; }
          busy(save, async () => {
            try {
              await ctx.api(`/me/passkeys/${p.id}`, { method: 'PATCH', body: { name: v } });
              s.close(); toast(t('ca.pkRenamed'), 'ok'); load();
            } catch (e2) { err.textContent = errorText(e2, ctx.user); }
          });
        });
        const rmErr = h('p', { class: 'form-error', role: 'alert' });
        const rm = h('button', { type: 'button', class: 'btn big wide ca-danger' }, t('ca.pkRemove'));
        const confirm = h('div', { class: 'c-confirm', hidden: true });
        const yes = h('button', { type: 'button', class: 'btn danger' }, t('ca.pkRemoveBtn'));
        const no = h('button', { type: 'button', class: 'btn', onclick: () => { confirm.hidden = true; rm.hidden = false; } }, t('common.cancel'));
        confirm.append(h('p', {}, t('ca.pkRemoveAsk', p.name)), h('div', { class: 'c-actions' }, yes, no));
        rm.addEventListener('click', () => { rm.hidden = true; confirm.hidden = false; no.focus(); });
        yes.addEventListener('click', () => busy(yes, async () => {
          try {
            await ctx.api(`/me/passkeys/${p.id}`, { method: 'DELETE' });
            s.close(); toast(t('ca.pkRemoved'), 'ok'); load();
          } catch (e) {
            rmErr.textContent = e.status === 409 ? (/owner/i.test(e.detail) ? t('ca.pkOwnerKeep') : t('ca.pkLast')) : errorText(e, ctx.user);
          }
        }));
        body.append(form, rm, confirm, rmErr);
      },
    });
  }
  load();
  return { card: box, note };
}

/* ---------- your data ---------- */
/** "Your data": download my data, delete my account. [caption, card]; phone rows open on tap (Account page),
 *  iPad/desktop rows have buttons (Account & app settings). */
export function dataSection(ctx, user, { phone = false } = {}) {
  let rows;
  if (phone) {
    const row = (ic, title, sub, tone, cls, onclick) => h('button', { type: 'button', class: `c-row c-link ${cls}`.trim(), onclick },
      tile(ic, tone), h('span', { class: 'c-row-tx' }, h('span', { class: 'c-title' }, title), h('span', { class: 'c-sub' }, sub)),
      h('span', { class: 'c-chev', 'aria-hidden': 'true' }, '›'));
    rows = [
      row(glyph('download'), t('ca.dl'), t('ca.dlSub'), 'plain', '', (e) => downloadMine(ctx, e.currentTarget)),
      row(glyph('trash'), t('ca.del'), t('ca.delSub'), 'danger', 'danger', () => confirmDelete(ctx, user))];
  } else {
    const dl = h('button', { type: 'button', class: 'btn' }, glyph('download'), t('ca.dlBtn'));
    dl.addEventListener('click', () => downloadMine(ctx, dl));
    const del = h('button', { type: 'button', class: 'btn ca-danger', onclick: () => confirmDelete(ctx, user) }, t('ca.delBtn'));
    rows = [settingRow({ title: t('ca.dl'), sub: t('ca.dlSub'), control: dl }),
      settingRow({ title: t('ca.del'), sub: t('ca.delSub'), control: del, cls: 'danger' })];
  }
  return [caption(t('ca.data')), card(...rows)];
}

/** GET /me/export saved as a file. The server's attachment name (speaker-my-data-YYYY-MM-DD.json) is made here
 *  again: a fetched body isn't a navigation, so the browser never sees its Content-Disposition. */
function downloadMine(ctx, btn) {
  return busy(btn, async () => {
    try {
      const data = await ctx.api('/me/export');
      const name = `speaker-my-data-${new Date().toLocaleDateString('en-CA')}.json`;
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
      const a = h('a', { href: url, download: name, hidden: true });
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
      toast(t('ca.dlDone', name), 'ok');
    } catch (e) { ctx.fail(e); }
  }).catch(() => {});
}

/** Type your username to enable the red button; then DELETE /me signs out here (the server already ended every
 *  session). The only owner gets a sheet that points to Members instead. */
function confirmDelete(ctx, user) {
  const username = user.username;
  ctx.sheet({
    title: t('ca.delTitle'),
    build(body, s) {
      const input = h('input', { class: 'input', autocomplete: 'off', autocapitalize: 'none', spellcheck: false });
      const err = h('p', { class: 'form-error', role: 'alert' });
      const go = h('button', { type: 'button', class: 'btn danger big wide', disabled: true }, t('ca.del'));
      const typed = () => input.value.trim().toLowerCase();
      input.addEventListener('input', () => {
        go.disabled = typed() !== username;
        err.textContent = '';
        input.removeAttribute('aria-invalid');
      });
      go.addEventListener('click', () => busy(go, async () => {
        try {
          await ctx.api('/me', { method: 'DELETE', body: { confirm: typed() } });
        } catch (e) {
          if (e.status === 409) { s.close(); lastOwner(ctx); return; }
          if (e.status === 400) { err.textContent = t('ca.delWrong'); input.setAttribute('aria-invalid', 'true'); input.focus(); return; }
          err.textContent = errorText(e, ctx.user);
          return;
        }
        await ctx.signOut(null, t('ca.deleted'));
      }).catch(() => {}));
      body.append(h('p', {}, t('ca.delGone')), h('p', { class: 'muted' }, t('ca.delStays')),
        field(t('ca.delType', username), input), err, go,
        h('button', { type: 'button', class: 'btn big wide', onclick: () => s.close() }, t('common.cancel')));
    },
  });
}

function lastOwner(ctx) {
  ctx.sheet({
    title: t('ca.lastTitle'),
    build(body, s) {
      body.append(h('div', { class: 'c-confirm' }, h('p', { class: 'form-error', role: 'alert' }, t('ca.last'))),
        h('a', { class: 'btn primary big wide', href: '#/members' }, t('ca.lastMembers')),
        h('button', { type: 'button', class: 'btn big wide', onclick: () => s.close() }, t('common.close')));
    },
  });
}

/* ---------- app preferences (per device) ---------- */
/** Language, appearance and reduce-motion controls, each as { title, control, help } pieces in one card. */
export function appPrefsCard(ctx, { split = false } = {}) {
  const block = (title, control, help) => h('div', { class: 'c-seg-wrap' }, h('span', { class: 'c-title' }, title), control, help);
  const langSeg = segmented({
    label: t('ca.lang'), value: getPref('lang'),
    options: [{ value: 'en', label: 'English', lang: 'en' }, { value: 'th', label: 'ไทย', lang: 'th' }],
    onChange: (v) => setPref('lang', v),
  });
  const themeSeg = segmented({
    label: t('ca.theme'), value: getPref('theme'),
    options: ['system', 'light', 'dark'].map((v) => ({ value: v, label: t(`ca.th.${v}`) })),
    onChange: (v) => setPref('theme', v),
  });
  const mHelp = h('span', { class: 'c-sub', role: 'status' });
  const paintM = () => {
    const m = getPref('motion');
    mHelp.textContent = m === 'system' ? t('ca.mHelpSys', motionReduced()) : t(m === 'on' ? 'ca.mHelpOn' : 'ca.mHelpOff');
  };
  const motionSeg = segmented({
    label: t('ca.motion'), value: getPref('motion'),
    options: ['system', 'on', 'off'].map((v) => ({ value: v, label: t(`ca.m.${v}`) })),
    onChange: (v) => { setPref('motion', v); paintM(); },
  });
  paintM();
  ctx.onCleanup(onPrefs(paintM));
  const blocks = [
    block(t('ca.lang'), langSeg, h('span', { class: 'c-sub' }, t('ca.langHelp'))),
    block(t('ca.theme'), themeSeg, h('span', { class: 'c-sub' }, t('ca.themeHelp'))),
    block(t('ca.motion'), motionSeg, mHelp),
  ];
  // replay the first-run quick tour on the Now page (js/tour.js)
  const tourRow = linkRow({ title: t('ca.tour'), sub: t('ca.tourSub'), onclick: () => import('./tour.js').then((m) => m.replay({ user: ctx.user })) });
  tourRow.classList.add('c-tour');
  // Talkie (talkie.js): other members' walkie talks play here live (with the Walkie open) unless this is off
  const talkieRow = settingRow({ title: t('ca.talkie'), sub: t('ca.talkieSub'), control: switchInput(hearTalkie(), setHearTalkie) });
  return split ? [...blocks.map((b) => card(b)), card(talkieRow), card(tourRow)] : [card(...blocks, talkieRow, tourRow)];
}
