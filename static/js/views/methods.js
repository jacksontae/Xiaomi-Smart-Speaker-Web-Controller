// Sign-in methods (boards Auth / T_Auth / D_Auth). Owners only (route min: admin).
// Server settings via GET/POST /settings: google_signin + google_client_id, passkey_signin,
// passkey_required_for_admins. Passwords are always on (the server has no switch for them). The server refuses
// "require a passkey" with 409 while passkeys can't work or an owner has none yet; the page explains which.
// The boards' client secret / redirect URI / allowed domains / test sign-in have no server side (Google Identity
// Services needs only the client ID), so they are not shown. The Google Cloud setup steps live in two info tips
// (section heading + client ID label) instead of text on the page; they show the origin to authorise.
import { h, icon, busy, helpLink, toast } from '../ui.js';
import { infoTip, copyRow } from '../infotip.js';
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
    'auth.cidErr': 'The client ID ends with .apps.googleusercontent.com',
    'auth.gTip': 'How to set up Sign in with Google', 'auth.gTipTitle': 'Set up in Google Cloud console',
    'auth.cidTip': 'Where to find the client ID', 'auth.cidTipTitle': 'Where the client ID comes from',
    'auth.g1': 'APIs & Services → OAuth consent screen: create it as External, with an app name and a support email. Add yourself and the members as test users, or publish the app.',
    'auth.g2': 'Credentials → Create credentials → OAuth client ID. Application type: Web application.',
    'auth.g3': 'Authorized JavaScript origins: add',
    'auth.g3b': 'Authorized redirect URIs: leave empty (not needed).',
    'auth.g4': 'Copy the Client ID (it ends with .apps.googleusercontent.com), paste it here, Save, then switch Sign in with Google on.',
    'auth.g5': 'Each member links Google in Account. Only linked accounts can sign in. No client secret is used or needed.',
    'auth.gWorks': 'Is it working? After you switch it on, the sign-in page shows "Continue with Google".',
    'auth.cid1': 'Google Cloud console → APIs & Services → Credentials → your OAuth client (type Web application).',
    'auth.cid2': 'Copy its Client ID. It ends with .apps.googleusercontent.com and isn\'t a secret.',
    'auth.cid3': 'The client secret and redirect URIs aren\'t used. Leave redirect URIs empty.',
    'auth.gTwo': 'This page is open on a different address than public_base_url. Google only accepts https:// origins (and http://localhost), so Sign in with Google only works on the https address.',
    'auth.gHttp': 'Google only accepts https:// origins (and http://localhost). Open the app on its https address (set public_base_url, for example https://speaker.example.com) and add that one instead.',
    'auth.gBoth': 'This page is open on a different address than public_base_url. Add both so Google sign-in works on either.',
    'auth.gReject': 'Google won\'t accept this one: it isn\'t https.',
    'auth.gWarn': 'Heads up:',
    'auth.pw': 'Password', 'auth.pwTitle': 'Username and password',
    'auth.pwSub': 'Always on. Members sign in with the username and password set in Members.',
    'auth.pk': 'Passkeys', 'auth.pkTitle': 'Sign in with a passkey',
    'auth.pkOn': 'On. Members add passkeys in Account and sign in with a fingerprint, face or device PIN.',
    'auth.pkOff': 'Off. Saved passkeys don\'t work until this is turned on again.',
    'auth.req': 'Require a passkey for owners',
    'auth.reqOn': 'On. Owners who have a passkey can sign in ONLY with it: their password and Google sign-in are refused. Operators and viewers are not affected.',
    'auth.reqOff': 'Off. When on, owners who have a passkey can sign in only with it (password and Google are refused).',
    'auth.reqAsk': 'Require a passkey for owners?',
    'auth.reqAskText': 'Owners who have a passkey will be able to sign in ONLY with it. Their password and Google sign-in will be refused, on every device. Make sure each owner can reach their passkey (phone or security key) first.',
    'auth.reqAskSave': 'It takes effect when you save this page.',
    'auth.reqYes': 'Require passkeys',
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
    'auth.cidErr': 'client ID ต้องลงท้ายด้วย .apps.googleusercontent.com',
    'auth.gTip': 'วิธีตั้งค่าเข้าสู่ระบบด้วย Google', 'auth.gTipTitle': 'ตั้งค่าใน Google Cloud console',
    'auth.cidTip': 'หา client ID ได้ที่ไหน', 'auth.cidTipTitle': 'client ID มาจากไหน',
    'auth.g1': 'APIs & Services → OAuth consent screen: สร้างแบบ External ใส่ชื่อแอปและอีเมลติดต่อ เพิ่มตัวเองและสมาชิกเป็น test users หรือกด publish แอป',
    'auth.g2': 'Credentials → Create credentials → OAuth client ID เลือก Application type เป็น Web application',
    'auth.g3': 'Authorized JavaScript origins: ใส่',
    'auth.g3b': 'Authorized redirect URIs: เว้นว่างไว้ (ไม่ต้องใช้)',
    'auth.g4': 'คัดลอก Client ID (ลงท้ายด้วย .apps.googleusercontent.com) มาวางที่นี่ กดบันทึก แล้วเปิดสวิตช์เข้าสู่ระบบด้วย Google',
    'auth.g5': 'สมาชิกแต่ละคนเชื่อม Google ในหน้าบัญชี เฉพาะบัญชีที่เชื่อมแล้วเท่านั้นที่เข้าได้ ไม่ใช้และไม่ต้องมี client secret',
    'auth.gWorks': 'ใช้ได้หรือยัง? พอเปิดแล้ว หน้าเข้าสู่ระบบจะมีปุ่ม "ดำเนินการต่อด้วย Google"',
    'auth.cid1': 'Google Cloud console → APIs & Services → Credentials → OAuth client ของคุณ (แบบ Web application)',
    'auth.cid2': 'คัดลอก Client ID ที่ลงท้ายด้วย .apps.googleusercontent.com ค่านี้ไม่ใช่ข้อมูลลับ',
    'auth.cid3': 'ไม่ใช้ client secret และ redirect URI ช่อง redirect URIs เว้นว่างไว้',
    'auth.gTwo': 'หน้านี้เปิดผ่านที่อยู่ที่ไม่ตรงกับ public_base_url Google รับเฉพาะ origin แบบ https:// (และ http://localhost) การเข้าสู่ระบบด้วย Google จึงใช้ได้เฉพาะที่อยู่ https',
    'auth.gHttp': 'Google รับเฉพาะ origin แบบ https:// (และ http://localhost) เปิดแอปผ่านที่อยู่ https (ตั้ง public_base_url เช่น https://speaker.example.com) แล้วใส่อันนั้นแทน',
    'auth.gBoth': 'หน้านี้เปิดผ่านที่อยู่ที่ไม่ตรงกับ public_base_url ใส่ทั้งสองอัน เพื่อให้เข้าด้วย Google ได้จากทั้งสองที่อยู่',
    'auth.gReject': 'Google ไม่รับอันนี้ เพราะไม่ใช่ https',
    'auth.gWarn': 'โปรดทราบ:',
    'auth.pw': 'รหัสผ่าน', 'auth.pwTitle': 'ชื่อผู้ใช้และรหัสผ่าน',
    'auth.pwSub': 'เปิดตลอด สมาชิกเข้าด้วยชื่อผู้ใช้และรหัสผ่านที่ตั้งในหน้าสมาชิก',
    'auth.pk': 'พาสคีย์', 'auth.pkTitle': 'เข้าสู่ระบบด้วยพาสคีย์',
    'auth.pkOn': 'เปิดอยู่ สมาชิกเพิ่มพาสคีย์ได้ในหน้าบัญชี แล้วเข้าด้วยลายนิ้วมือ ใบหน้า หรือ PIN ของเครื่อง',
    'auth.pkOff': 'ปิดอยู่ พาสคีย์ที่บันทึกไว้จะใช้ไม่ได้จนกว่าจะเปิดอีกครั้ง',
    'auth.req': 'เจ้าของต้องใช้พาสคีย์',
    'auth.reqOn': 'เปิดอยู่ เจ้าของที่มีพาสคีย์เข้าสู่ระบบได้ด้วยพาสคีย์เท่านั้น ระบบจะไม่รับรหัสผ่านและ Google ของเจ้าของ ผู้ดูแลและผู้ชมไม่ได้รับผลกระทบ',
    'auth.reqOff': 'ปิดอยู่ ถ้าเปิด เจ้าของที่มีพาสคีย์จะเข้าสู่ระบบได้ด้วยพาสคีย์เท่านั้น (ไม่รับรหัสผ่านและ Google)',
    'auth.reqAsk': 'ให้เจ้าของต้องใช้พาสคีย์ไหม',
    'auth.reqAskText': 'เจ้าของที่มีพาสคีย์จะเข้าสู่ระบบได้ด้วยพาสคีย์เท่านั้น ระบบจะไม่รับรหัสผ่านและ Google ของเจ้าของในทุกอุปกรณ์ ตรวจให้แน่ใจก่อนว่าเจ้าของทุกคนเข้าถึงพาสคีย์ของตัวเองได้ (มือถือหรือกุญแจความปลอดภัย)',
    'auth.reqAskSave': 'มีผลเมื่อกดบันทึกหน้านี้',
    'auth.reqYes': 'ต้องใช้พาสคีย์',
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

/** Origins Google accepts for a Web client: https, or http on localhost. */
function googleOk(origin) {
  try {
    const u = new URL(origin);
    return u.protocol === 'https:' || (u.protocol === 'http:' && u.hostname === 'localhost');
  } catch { return false; }
}

/** The page's own origin, plus public_base_url's when it differs. */
function originsFor(base) {
  const list = [location.origin];
  try { if (base) { const o = new URL(base).origin; if (o !== location.origin) list.push(o); } } catch { /* bad URL: ignore */ }
  return list;
}

/** Copy rows for the JavaScript origins to authorise, with the https warning when it applies. */
function originsBlock(base) {
  const list = originsFor(base);
  const rows = list.map((o) => copyRow(o, googleOk(o) ? null : t('auth.gReject')));
  let warn = null;
  if (list.length > 1) warn = list.every(googleOk) ? t('auth.gBoth') : t('auth.gTwo');
  else if (!googleOk(list[0])) warn = t('auth.gHttp');
  return { rows, warn: warn && h('p', { class: 'infotip-warn' }, h('strong', {}, t('auth.gWarn')), ' ', warn) };
}

/** Full setup guide (section tip): consent screen, Web client, origin, client ID, members. */
function googleGuide(body, base) {
  const { rows, warn } = originsBlock(base);
  body.append(
    h('ol', { class: 'infotip-steps' },
      h('li', {}, t('auth.g1')),
      h('li', {}, t('auth.g2')),
      h('li', {}, t('auth.g3'), rows, h('div', { class: 'infotip-muted', style: { marginTop: '6px' } }, t('auth.g3b'))),
      h('li', {}, t('auth.g4')),
      h('li', {}, t('auth.g5'))),
    warn,
    h('p', { class: 'infotip-muted' }, t('auth.gWorks')));
}

/** Short guide next to the client ID field: where to copy it from and the origin the client must allow. */
function cidGuide(body, base) {
  const { rows, warn } = originsBlock(base);
  body.append(
    h('ol', { class: 'infotip-steps' },
      h('li', {}, t('auth.cid1')),
      h('li', {}, t('auth.g3'), rows),
      h('li', {}, t('auth.cid2')),
      h('li', {}, t('auth.cid3'))),
    warn);
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
    paintDirty();
  }
  // the draft is the source of truth for Save (busy() re-enables buttons when it finishes, so repaint after it)
  function paintDirty() {
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
    const base = saved.public_base_url;
    const gTip = infoTip({ label: t('auth.gTip'), title: t('auth.gTipTitle'), build: (b) => googleGuide(b, base) });
    const cidTip = infoTip({ label: t('auth.cidTip'), title: t('auth.cidTipTitle'), build: (b) => cidGuide(b, base) });
    const gCard = card(
      settingRow({ title: t('auth.gTitle'), sub: gSub, control: gSw, lead: tile(gMark(), 'plain') }),
      h('div', { class: 'c-stack' }, h('div', { class: 'infotip-row' }, h('label', { class: 'c-title', for: 'a-cid' }, t('auth.cid')), cidTip), cid, cidErr));

    /* password */
    const pwCard = card(settingRow({ title: t('auth.pwTitle'), sub: t('auth.pwSub'), lead: tile(icon('lock'), 'plain') }));

    /* passkeys */
    const pkSub = h('span', {});
    const reqSub = h('span', {});
    const reqErr = h('span', { class: 'c-sub err', role: 'alert' });
    const reqSw = switchInput(val('passkey_required_for_admins'), (on) => {
      if (!on) { set('passkey_required_for_admins', false); paintPk(); return; }
      // turning it on locks owners out of password and Google: confirm first (the switch waits for the answer)
      reqSw.checked = false;
      confirmRequire(() => { reqSw.checked = true; set('passkey_required_for_admins', true); paintPk(); });
    });
    const pkSw = switchInput(val('passkey_signin'), (on) => { set('passkey_signin', on); paintPk(); });
    const paintPk = () => {
      pkSub.textContent = pkSw.checked ? t('auth.pkOn') : t('auth.pkOff');
      reqSw.disabled = !pkSw.checked && !reqSw.checked;
      reqSub.textContent = !pkSw.checked && !reqSw.checked ? `${t('auth.reqOff')} ${t('auth.reqNeedsPk')}` : reqSw.checked ? t('auth.reqOn') : t('auth.reqOff');
    };
    paintPk();
    const secure = secureBase(base);
    const pkCard = card(
      settingRow({ title: t('auth.pkTitle'), sub: pkSub, control: pkSw, lead: tile(icon('passkey')) }),
      settingRow({ title: t('auth.req'), sub: h('span', {}, reqSub, ' ', reqErr), control: reqSw }),
      h('p', { class: 'c-row c-sub a-secure' }, h('span', {}, secure ? t('auth.secure', base) : t('auth.insecure'), ' ', helpLink('passkey', t('auth.why')))));
    reqErrEl = reqErr;

    const gCap = h('div', { class: 'infotip-row infotip-caprow' }, caption(t('auth.google')), gTip);
    left.replaceChildren(gCap, gCard, caption(t('auth.pw')), pwCard);
    right.replaceChildren(caption(t('auth.pk')), pkCard, caption(t('auth.who')), whoCard());
  }

  function confirmRequire(yes) {
    ctx.sheet({
      title: t('auth.reqAsk'),
      build(body, sheet) {
        body.append(h('p', {}, t('auth.reqAskText')), h('p', { class: 'small' }, t('auth.reqAskSave')),
          h('button', { type: 'button', class: 'btn primary big wide', onclick: () => { sheet.close(); yes(); } }, t('auth.reqYes')),
          h('button', { type: 'button', class: 'btn big wide', onclick: () => sheet.close() }, t('common.cancel')));
      },
    });
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
        toast(t('auth.saved'), 'ok');
        build();
      } catch (e) {
        const msg = settingsErr(e, ctx.user, users);
        if ('passkey_required_for_admins' in body && e.status === 409 && reqErrEl) reqErrEl.textContent = msg;
        err.textContent = msg;
      }
    }));
    paintDirty();
  }

  Promise.all([ctx.api('/settings', { signal: ctx.signal }), ctx.api('/users', { signal: ctx.signal }).catch(() => [])])
    .then(([s, u]) => { saved = s; users = u; build(); })
    .catch((e) => { err.textContent = ctx.fail(e); });
  return { node };
}
