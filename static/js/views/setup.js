// First-time setup (board Setup): shown instead of Sign in while the server has no account yet. Creates the owner
// account with the API token from ./speakerctl token. On iPhone there is no card: the form sits on the backdrop.
import { h, field, passwordInput } from '../ui.js';
import { register, t } from '../i18n.js';
import { errorText } from '../api.js';
import { langToggle } from './login.js';

register({
  en: {
    'setup.title': 'First-time setup', 'setup.intro': 'Create the owner account. You can add other members later.',
    'setup.token': 'API token', 'setup.tokenHelp': 'To see it, run ./speakerctl token on the machine that runs the service.',
    'setup.tokenBad': 'Enter the token from ./speakerctl token', 'setup.tokenWrong': 'That API token is wrong. Copy it again from ./speakerctl token.',
    'setup.name': 'Display name', 'setup.nameErr': 'Enter the name other people will see',
    'setup.user': 'Username', 'setup.userHelp': 'a–z, numbers, dots and hyphens, 3–32 characters',
    'setup.pw': 'Password', 'setup.pwHelp': 'At least 8 characters',
    'setup.create': 'Create owner account', 'setup.creating': 'Creating…', 'setup.fix': 'Fix the fields in red, then try again.',
    'setup.haveAcc': 'Already have an account?', 'setup.signIn': 'Sign in',
    'setup.noAccYet': 'There\'s no account on this speaker yet. Create the owner account first.',
  },
  th: {
    'setup.title': 'ตั้งค่าครั้งแรก', 'setup.intro': 'สร้างบัญชีเจ้าของ แล้วค่อยเพิ่มสมาชิกคนอื่นทีหลัง',
    'setup.token': 'API token', 'setup.tokenHelp': 'ดูได้ด้วยคำสั่ง ./speakerctl token บนเครื่องที่รัน service',
    'setup.tokenBad': 'ใส่ token ที่ได้จากคำสั่ง ./speakerctl token', 'setup.tokenWrong': 'API token ไม่ถูกต้อง คัดลอกจากคำสั่ง ./speakerctl token อีกครั้ง',
    'setup.name': 'ชื่อที่แสดง', 'setup.nameErr': 'ใส่ชื่อที่จะให้คนอื่นเห็น',
    'setup.user': 'ชื่อผู้ใช้', 'setup.userHelp': 'a–z ตัวเลข จุด ขีด ยาว 3–32 ตัว',
    'setup.pw': 'รหัสผ่าน', 'setup.pwHelp': 'อย่างน้อย 8 ตัวอักษร',
    'setup.create': 'สร้างบัญชีเจ้าของ', 'setup.creating': 'กำลังสร้าง…', 'setup.fix': 'แก้ช่องที่เป็นสีแดงก่อน แล้วกดสร้างอีกครั้ง',
    'setup.haveAcc': 'มีบัญชีแล้ว', 'setup.signIn': 'เข้าสู่ระบบ',
    'setup.noAccYet': 'ลำโพงนี้ยังไม่มีบัญชี สร้างบัญชีเจ้าของก่อน',
  },
});

const draft = { token: '', name: '', user: '', pw: '' };
const USER_RE = /^[a-z0-9._-]{3,32}$/;

export async function render(ctx) {
  await ctx.css('auth.css');
  const token = passwordInput({ autocomplete: 'off', value: draft.token, oninput: () => { draft.token = token.input.value; check(token.input); } });
  const name = h('input', { class: 'input', autocomplete: 'name', value: draft.name, oninput: () => { draft.name = name.value; check(name); } });
  const user = h('input', {
    class: 'input', autocomplete: 'username', autocapitalize: 'none', spellcheck: false, value: draft.user,
    oninput: () => { user.value = user.value.toLowerCase(); draft.user = user.value; check(user); },
  });
  const pw = passwordInput({ autocomplete: 'new-password', value: draft.pw, oninput: () => { draft.pw = pw.input.value; check(pw.input); } });
  const tokenF = field(t('setup.token'), token.wrap, t('setup.tokenHelp'));
  const nameF = field(t('setup.name'), name, '');
  const userF = field(t('setup.user'), user, t('setup.userHelp'));
  const pwF = field(t('setup.pw'), pw.wrap, t('setup.pwHelp'));
  const err = h('p', { class: 'setup-err', role: 'alert' });
  const btn = h('button', { type: 'submit', class: 'btn primary big wide' }, t('setup.create'));
  let tried = false;

  const rules = [
    [token.input, tokenF, () => token.input.value.trim().length > 0, 'setup.tokenHelp', 'setup.tokenBad'],
    [name, nameF, () => name.value.trim().length > 0, null, 'setup.nameErr'],
    [user, userF, () => USER_RE.test(user.value), 'setup.userHelp', 'setup.userHelp'],
    [pw.input, pwF, () => pw.input.value.length >= 8, 'setup.pwHelp', 'setup.pwHelp'],
  ];
  function check(el) {
    if (!tried) return true;
    let ok = true;
    for (const [input, f, valid, okKey, badKey] of rules) {
      if (el && el !== input) { ok = ok && valid(); continue; }
      const good = valid();
      ok = ok && good;
      input.setAttribute('aria-invalid', String(!good));
      const hint = f.querySelector('.hint');
      hint.textContent = good ? (okKey ? t(okKey) : '') : t(badKey);
      hint.classList.toggle('err', !good);
    }
    if (ok) err.textContent = '';
    return ok;
  }

  const form = h('form', {
    novalidate: true,
    onsubmit: async (e) => {
      e.preventDefault();
      tried = true;
      if (!check()) { err.textContent = t('setup.fix'); rules.find((r) => !r[2]())[0].focus(); return; }
      err.textContent = '';
      btn.disabled = true; btn.classList.add('busy'); btn.lastChild.textContent = t('setup.creating');
      try {
        const r = await ctx.api('/auth/setup', { body: { api_token: token.input.value.trim(), username: user.value, display_name: name.value.trim(), password: pw.input.value }, allow401: true });
        Object.keys(draft).forEach((k) => { draft[k] = ''; });
        ctx.signedIn(r.user);
      } catch (e2) {
        btn.disabled = false; btn.classList.remove('busy'); btn.lastChild.textContent = t('setup.create');
        if (e2.status === 409) { location.reload(); return; } // someone finished setup meanwhile: sign in instead
        if (e2.status === 401) token.input.setAttribute('aria-invalid', 'true');
        err.textContent = errorText(e2, null, { 401: t('setup.tokenWrong') });
      }
    },
  },
  h('div', {}, h('h1', {}, t('setup.title')), h('p', { class: 'intro' }, t('setup.intro'))),
  tokenF, nameF, userF, pwF, btn, err);

  // The board keeps this link. While setup is pending there is no account, so it re-checks and says so.
  const signInBtn = h('button', {
    type: 'button', class: 'linkbtn',
    onclick: async () => {
      try {
        const st = await ctx.api('/auth/state', { allow401: true });
        if (!st.needs_setup) { location.reload(); return; }
      } catch { /* fall through */ }
      err.textContent = t('setup.noAccYet');
    },
  }, t('setup.signIn'));

  if (!matchMedia('(pointer: coarse)').matches) setTimeout(() => token.input.focus({ preventScroll: true }), 50);
  document.title = `${t('setup.title')} · ${t('app.name')}`;
  return h('div', { class: 'auth setup' },
    h('div', { class: 'auth-bloom', 'aria-hidden': 'true' }),
    langToggle(),
    h('div', { class: 'setup-col' }, form, h('p', { class: 'setup-foot' }, `${t('setup.haveAcc')} `, signInBtn)));
}
