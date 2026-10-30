// Sign-in methods (boards Auth / T_Auth / D_Auth). Owners only (route min: admin).
// Server settings via GET/POST /settings: google_signin + google_client_id, passkey_signin,
// passkey_required_for_admins. Passwords are always on (the server has no switch for them). The server refuses
// "require a passkey" with 409 while passkeys can't work or an owner has none yet; the page explains which.
// The boards' client secret / redirect URI / allowed domains / test sign-in have no server side (Google Identity
// Services needs only the client ID), so they are not shown.
import { h, icon, busy, helpLink, toast } from '../ui.js';
import { register, t } from '../i18n.js';
import { errorText } from '../api.js';
import { isPhone } from '../sheet.js';
import { caption, card, settingRow, switchInput, tile, gMark, linkRow } from '../c-kit.js';

register({
  en: {
    'auth.google': 'Google', 'auth.gTitle': 'Sign in with Google',
    'auth.gOn': 'On. The sign-in page shows "Continue with Google" to members who linked their Google account.',
    'auth.gOff': 'Off. People only see the username and password form.',
    'auth.gNeedId': 'Add the OAuth client ID below to turn this on.',
    'auth.cid': 'OAuth client ID',
    'auth.cidHelp': 'From the Google Cloud console (OAuth client of type "Web application"). Not a secret.',
    'auth.cidErr': 'The client ID ends with .apps.googleusercontent.com',
    'auth.gWho': 'Only members can sign in with Google: each one links their own Google account in Account first.',
    'auth.pw': 'Password', 'auth.pwTitle': 'Username and password',
    'auth.pwSub': 'Always on. Members sign in with the username and password set in Members.',
    'auth.pk': 'Passkeys', 'auth.pkTitle': 'Sign in with a passkey',
    'auth.pkOn': 'On. Members add passkeys in Account and sign in with a fingerprint, face or device PIN.',
    'auth.pkOff': 'Off. Saved passkeys don\'t work until this is turned on again.',
    'auth.req': 'Require a passkey for owners',
    'auth.reqOn': 'On. Owners who have a passkey can only sign in with it. Others still use a password or Google.',
    'auth.reqOff': 'Off. Owners can also use a password or Google.',
    'auth.reqNeedsPk': 'Turn on passkey sign-in first.',
    'auth.secure': (u) => `Passkeys work on ${u}. On other addresses, like the plain LAN address, the passkey button is hidden.`,
    'auth.insecure': 'Passkeys need a secure address: set public_base_url in config.json to an https:// address (for example https://speaker.example.com). Until then the passkey button stays hidden.',
    'auth.why': 'Read more in Help',
    'auth.errMissing': (names) => `Every owner needs a passkey first. Still missing: ${names}. They can add one in Account.`,
    'auth.errUnavail': 'Passkeys can\'t work on this setup yet: they need passkey sign-in on and an https:// address.',
    'auth.errNeedId': 'Sign in with Google needs the OAuth client ID.',
    'auth.who': 'Who uses what', 'auth.useG': 'Google', 'auth.useP': 'Password', 'auth.useK': 'Passkey',
    'auth.nobody': 'Nobody yet', 'auth.manage': 'Manage members',
    'auth.saved': 'Sign-in methods saved',
  },
  th: {
    'auth.google': 'Google', 'auth.gTitle': 'เข้าสู่ระบบด้วย Google',
    'auth.gOn': 'เปิดอยู่ หน้าเข้าสู่ระบบแสดง "ดำเนินการต่อด้วย Google" ให้สมาชิกที่เชื่อมบัญชี Google แล้ว',
    'auth.gOff': 'ปิดอยู่ หน้าเข้าสู่ระบบมีแค่ชื่อผู้ใช้และรหัสผ่าน',
    'auth.gNeedId': 'ใส่ OAuth client ID ด้านล่างก่อนจึงจะเปิดได้',
    'auth.cid': 'OAuth client ID',
    'auth.cidHelp': 'จาก Google Cloud console (OAuth client แบบ "Web application") ไม่ใช่ข้อมูลลับ',
    'auth.cidErr': 'client ID ต้องลงท้ายด้วย .apps.googleusercontent.com',
    'auth.gWho': 'เฉพาะสมาชิกเท่านั้นที่เข้าด้วย Google ได้ แต่ละคนต้องเชื่อมบัญชี Google ของตัวเองในหน้าบัญชีก่อน',
    'auth.pw': 'รหัสผ่าน', 'auth.pwTitle': 'ชื่อผู้ใช้และรหัสผ่าน',
    'auth.pwSub': 'เปิดตลอด สมาชิกเข้าด้วยชื่อผู้ใช้และรหัสผ่านที่ตั้งในหน้าสมาชิก',
    'auth.pk': 'พาสคีย์', 'auth.pkTitle': 'เข้าสู่ระบบด้วยพาสคีย์',
    'auth.pkOn': 'เปิดอยู่ สมาชิกเพิ่มพาสคีย์ได้ในหน้าบัญชี แล้วเข้าด้วยลายนิ้วมือ ใบหน้า หรือ PIN ของเครื่อง',
    'auth.pkOff': 'ปิดอยู่ พาสคีย์ที่บันทึกไว้จะใช้ไม่ได้จนกว่าจะเปิดอีกครั้ง',
    'auth.req': 'เจ้าของต้องใช้พาสคีย์',
    'auth.reqOn': 'เปิดอยู่ เจ้าของที่มีพาสคีย์เข้าได้ด้วยพาสคีย์เท่านั้น คนอื่นยังใช้รหัสผ่านหรือ Google ได้',
    'auth.reqOff': 'ปิดอยู่ เจ้าของใช้รหัสผ่านหรือ Google ได้ด้วย',
    'auth.reqNeedsPk': 'เปิดการเข้าสู่ระบบด้วยพาสคีย์ก่อน',
    'auth.secure': (u) => `พาสคีย์ใช้ได้ที่ ${u} ถ้าเปิดผ่านที่อยู่อื่น เช่นที่อยู่ในวงแลนแบบธรรมดา ปุ่มพาสคีย์จะไม่แสดง`,
    'auth.insecure': 'พาสคีย์ต้องใช้ที่อยู่แบบปลอดภัย ตั้ง public_base_url ใน config.json เป็นที่อยู่ https:// (เช่น https://speaker.example.com) ระหว่างนี้ปุ่มพาสคีย์จะไม่แสดง',
    'auth.why': 'อ่านเพิ่มในคู่มือ',
    'auth.errMissing': (names) => `เจ้าของทุกคนต้องมีพาสคีย์ก่อน ยังขาด: ${names} เพิ่มได้ในหน้าบัญชี`,
    'auth.errUnavail': 'ยังใช้พาสคีย์กับการตั้งค่านี้ไม่ได้ ต้องเปิดการเข้าสู่ระบบด้วยพาสคีย์และใช้ที่อยู่ https://',
    'auth.errNeedId': 'การเข้าสู่ระบบด้วย Google ต้องใส่ OAuth client ID',
    'auth.who': 'ใครใช้วิธีไหน', 'auth.useG': 'Google', 'auth.useP': 'รหัสผ่าน', 'auth.useK': 'พาสคีย์',
    'auth.nobody': 'ยังไม่มีใคร', 'auth.manage': 'จัดการสมาชิก',
    'auth.saved': 'บันทึกวิธีเข้าสู่ระบบแล้ว',
  },
});

const CID_RE = /^[A-Za-z0-9.-]+\.apps\.googleusercontent\.com$/;

/** Same rule as passkeys.relying_party(): https (or http://localhost) on a domain name. */
function secureBase(url) {
  if (!url) return false;
  try {
    const u = new URL(url);
    if (/^[\d.]+$/.test(u.hostname) || u.hostname.includes(':') || u.hostname.startsWith('[')) return false;
    return u.protocol === 'https:' || u.hostname === 'localhost';
  } catch { return false; }
}

function settingsErr(e, user, users = []) {
  const d = (e && e.detail) || '';
  if (e && e.status === 409) {
    const m = d.match(/missing: (.+)$/);
    // the server lists usernames; show the names members know each other by
    const named = (u) => (users.find((x) => x.username === u) || {}).display_name || u;
    if (m) return t('auth.errMissing', m[1].split(', ').map(named).join(', '));
    if (/aren't available|Passkeys/i.test(d)) return t('auth.errUnavail');
  }
  if (e && e.status === 422) {
    if (/google_signin needs/i.test(d)) return t('auth.errNeedId');
    if (/google_client_id/i.test(d)) return t('auth.cidErr');
  }
  return errorText(e, user);
}

export function render(ctx) {
  ctx.css('views/c-common.css');
  let saved = null;
  let draft = {};
  let users = [];
  let reqErrEl = null;
  const err = h('p', { class: 'form-error', role: 'alert' });
  const dirtyNote = h('span', { class: 'small', hidden: true }, t('c.unsaved'));
  const saveBtn = h('button', { type: 'button', class: 'btn primary', disabled: true, onclick: () => save() }, t('common.save'));
  const bottomSave = h('button', { type: 'button', class: 'btn primary big wide c-phone-only', disabled: true, onclick: () => save() }, t('common.save'));
  const left = h('div', { class: 'c-col' });
  const right = h('div', { class: 'c-col' });
  const back = isPhone() ? { href: '#/account', label: t('nav.account') } : { href: '#/members', label: t('nav.members') };
  const node = h('div', { class: 'page' },
    ctx.header({ title: t('nav.auth'), back, actions: h('div', { class: 'c-save c-large-only' }, dirtyNote, saveBtn) }),
    err, h('div', { class: 'c-cols' }, left, right), bottomSave);

  const val = (k) => (k in draft ? draft[k] : saved[k]);
  function set(k, v) {
    if (JSON.stringify(v) === JSON.stringify(saved[k])) delete draft[k]; else draft[k] = v;
    const dirty = Object.keys(draft).length > 0;
    saveBtn.disabled = !dirty; bottomSave.disabled = !dirty; dirtyNote.hidden = !dirty;
  }

  function build() {
    /* Google */
    const gSub = h('span', {});
    const cid = h('input', { class: 'input', id: 'a-cid', value: val('google_client_id') || '', spellcheck: false, autocapitalize: 'none', autocomplete: 'off', placeholder: '1234-abc.apps.googleusercontent.com' });
    const cidErr = h('p', { class: 'small form-error', role: 'alert' });
    const gSw = switchInput(val('google_signin'), (on) => { set('google_signin', on); paintG(); });
    const paintG = () => {
      const id = cid.value.trim();
      const okId = CID_RE.test(id);
      gSw.disabled = !okId && !gSw.checked;
      gSub.textContent = gSw.checked ? t('auth.gOn') : okId ? t('auth.gOff') : `${t('auth.gOff')} ${t('auth.gNeedId')}`;
    };
    cid.addEventListener('input', () => {
      const id = cid.value.trim();
      cidErr.textContent = id && !CID_RE.test(id) ? t('auth.cidErr') : '';
      cid.toggleAttribute('aria-invalid', !!cidErr.textContent);
      if (!id || CID_RE.test(id)) set('google_client_id', id || null);
      paintG();
    });
    paintG();
    const gCard = card(
      settingRow({ title: t('auth.gTitle'), sub: gSub, control: gSw, lead: tile(gMark(), 'plain') }),
      h('div', { class: 'c-stack' }, h('label', { class: 'c-title', for: 'a-cid' }, t('auth.cid')), cid, cidErr, h('p', { class: 'small' }, t('auth.cidHelp'))),
      h('p', { class: 'c-row c-sub' }, t('auth.gWho')));

    /* password */
    const pwCard = card(settingRow({ title: t('auth.pwTitle'), sub: t('auth.pwSub'), lead: tile(icon('lock'), 'plain') }));

    /* passkeys */
    const pkSub = h('span', {});
    const reqSub = h('span', {});
    const reqErr = h('span', { class: 'c-sub err', role: 'alert' });
    const reqSw = switchInput(val('passkey_required_for_admins'), (on) => { set('passkey_required_for_admins', on); paintPk(); });
    const pkSw = switchInput(val('passkey_signin'), (on) => { set('passkey_signin', on); paintPk(); });
    const paintPk = () => {
      pkSub.textContent = pkSw.checked ? t('auth.pkOn') : t('auth.pkOff');
      reqSw.disabled = !pkSw.checked && !reqSw.checked;
      reqSub.textContent = !pkSw.checked && !reqSw.checked ? `${t('auth.reqOff')} ${t('auth.reqNeedsPk')}` : reqSw.checked ? t('auth.reqOn') : t('auth.reqOff');
    };
    paintPk();
    const base = saved.public_base_url;
    const secure = secureBase(base);
    const pkCard = card(
      settingRow({ title: t('auth.pkTitle'), sub: pkSub, control: pkSw, lead: tile(icon('passkey')) }),
      settingRow({ title: t('auth.req'), sub: h('span', {}, reqSub, ' ', reqErr), control: reqSw }),
      h('p', { class: 'c-row c-sub a-secure' }, h('span', {}, secure ? t('auth.secure', base) : t('auth.insecure'), ' ', helpLink('passkey', t('auth.why')))));
    reqErrEl = reqErr;

    left.replaceChildren(caption(t('auth.google')), gCard, caption(t('auth.pw')), pwCard);
    right.replaceChildren(caption(t('auth.pk')), pkCard, caption(t('auth.who')), whoCard());
  }

  function whoCard() {
    const active = users.filter((u) => !u.disabled);
    const line = (label, list) => settingRow({ title: label, sub: list.length ? list.map((u) => u.display_name).join(', ') : t('auth.nobody'), control: h('span', { class: 'c-val c-count' }, String(list.length)) });
    return card(
      line(t('auth.useG'), active.filter((u) => u.google_email)),
      line(t('auth.useP'), active),
      line(t('auth.useK'), active.filter((u) => u.has_passkey)),
      linkRow({ href: '#/members', title: t('auth.manage') }));
  }

  async function save() {
    err.textContent = '';
    const body = { ...draft };
    await busy(saveBtn, () => busy(bottomSave, async () => {
      try {
        const r = await ctx.api('/settings', { body });
        saved = r.settings;
        draft = {};
        set('google_signin', saved.google_signin);
        toast(t('auth.saved'), 'ok');
        build();
      } catch (e) {
        const msg = settingsErr(e, ctx.user, users);
        if ('passkey_required_for_admins' in body && e.status === 409 && reqErrEl) reqErrEl.textContent = msg;
        err.textContent = msg;
      }
    }));
  }

  Promise.all([ctx.api('/settings', { signal: ctx.signal }), ctx.api('/users', { signal: ctx.signal }).catch(() => [])])
    .then(([s, u]) => { saved = s; users = u; build(); })
    .catch((e) => { err.textContent = ctx.fail(e); });
  return { node };
}
