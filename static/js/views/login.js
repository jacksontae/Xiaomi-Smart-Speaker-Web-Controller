// Sign in (boards Login / T_Login / D_Login). Order: title, username, password, "Forgot password" right-aligned
// under the password, Sign in, "or", Continue with Google, Sign in with a passkey. Google and passkey only when
// the server offers them. No link to first-time setup: a fresh server opens Setup instead (app.js).
import { h, icon, field, passwordInput } from '../ui.js';
import { register, t, lang, fmtDate, fmtClock } from '../i18n.js';
import { set as setPref } from '../prefs.js';
import { errorText, waitText } from '../api.js';
import { methodsOf, googleCredential, googleSignIn, passkeySignIn } from '../signin.js';
import { speaker3d } from '../speaker3d.js';

register({
  en: {
    'login.title': 'Sign in', 'login.user': 'Username', 'login.pw': 'Password', 'login.go': 'Sign in', 'login.going': 'Signing in…',
    'login.forgot': 'Forgot password',
    'login.forgotHelp': 'Ask the owner to set a new password for you on the Members page, then sign in with it.',
    'login.empty': 'Enter your username and password first.',
    'login.bad': 'Wrong username or password.',
    'login.pkNeeded': 'Owners sign in with a passkey here. Use your passkey to sign in.',
    'login.disabled': 'This account is turned off. Ask the owner to turn it back on.',
    'login.lock': (w) => `Too many wrong tries. You can try again in ${w}.`,
    'login.google': 'Continue with Google', 'login.gNotMember': 'This Google account isn\'t a member here. Ask the owner to invite you.',
    'login.gUnavailable': 'Google sign-in didn\'t load. Check the internet connection, or sign in with your password.',
    'login.gTitle': 'Continue with Google',
    'login.pk': 'Sign in with a passkey', 'login.pkCancelled': 'Passkey sign-in cancelled.',
    'login.pkFailed': 'That passkey didn\'t work here. Try again or use your password.',
    'login.clock': 'Date and time',
  },
  th: {
    'login.title': 'เข้าสู่ระบบ', 'login.user': 'ชื่อผู้ใช้', 'login.pw': 'รหัสผ่าน', 'login.go': 'เข้าสู่ระบบ', 'login.going': 'กำลังเข้าสู่ระบบ…',
    'login.forgot': 'ลืมรหัสผ่าน',
    'login.forgotHelp': 'ให้เจ้าของตั้งรหัสใหม่ให้ในหน้าสมาชิก แล้วเข้าสู่ระบบด้วยรหัสนั้น',
    'login.empty': 'ใส่ชื่อผู้ใช้และรหัสผ่านก่อน',
    'login.bad': 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง',
    'login.pkNeeded': 'เจ้าของต้องเข้าสู่ระบบด้วยพาสคีย์ ใช้พาสคีย์ของคุณเพื่อเข้าสู่ระบบ',
    'login.disabled': 'บัญชีนี้ถูกปิดใช้งาน ขอให้เจ้าของเปิดให้อีกครั้ง',
    'login.lock': (w) => `ลองผิดหลายครั้งเกินไป ลองใหม่ได้ในอีก ${w}`,
    'login.google': 'ดำเนินการต่อด้วย Google', 'login.gNotMember': 'บัญชี Google นี้ยังไม่ได้เป็นสมาชิกที่นี่ ขอให้เจ้าของเชิญคุณก่อน',
    'login.gUnavailable': 'โหลดการเข้าสู่ระบบด้วย Google ไม่ได้ ตรวจการต่ออินเทอร์เน็ต หรือเข้าสู่ระบบด้วยรหัสผ่าน',
    'login.gTitle': 'ดำเนินการต่อด้วย Google',
    'login.pk': 'เข้าสู่ระบบด้วยพาสคีย์', 'login.pkCancelled': 'ยกเลิกการเข้าสู่ระบบด้วยพาสคีย์แล้ว',
    'login.pkFailed': 'ใช้พาสคีย์นี้ที่นี่ไม่ได้ ลองอีกครั้งหรือใช้รหัสผ่าน',
    'login.clock': 'วันและเวลา',
  },
});

// Survives a language switch (the screen is rebuilt); never stored anywhere.
const draft = { user: '', pw: '', forgot: false };

const G_MARK = '<svg class="g" viewBox="0 0 24 24" aria-hidden="true"><path fill="#4285F4" d="M21.6 12.23c0-.71-.06-1.4-.18-2.05H12v3.88h5.38a4.6 4.6 0 0 1-2 3.02v2.5h3.24c1.9-1.75 2.98-4.32 2.98-7.35z"/><path fill="#34A853" d="M12 22c2.7 0 4.97-.9 6.62-2.42l-3.24-2.5c-.9.6-2.04.95-3.38.95-2.6 0-4.8-1.75-5.59-4.11H3.07v2.58A10 10 0 0 0 12 22z"/><path fill="#FBBC05" d="M6.41 13.92A6 6 0 0 1 6.1 12c0-.67.11-1.31.31-1.92V7.5H3.07A10 10 0 0 0 2 12c0 1.61.39 3.14 1.07 4.5l3.34-2.58z"/><path fill="#EA4335" d="M12 5.98c1.47 0 2.79.5 3.82 1.5l2.87-2.87A9.6 9.6 0 0 0 12 2 10 10 0 0 0 3.07 7.5l3.34 2.58C7.2 7.73 9.4 5.98 12 5.98z"/></svg>';
const gMark = () => { const s = h('span', { 'aria-hidden': 'true', style: { display: 'contents' } }); s.innerHTML = G_MARK; return s; };

/** EN | ไทย switch shared by Login and Setup. */
export function langToggle() {
  const b = (code, label) => h('button', { type: 'button', lang: code, 'aria-pressed': String(lang() === code), onclick: () => setPref('lang', code) }, label);
  return h('div', { class: 'lang-toggle', role: 'group', 'aria-label': t('lang.label') }, b('en', 'EN'), h('span', { 'aria-hidden': 'true' }, '|'), b('th', 'ไทย'));
}

export async function render(ctx) {
  await ctx.css('auth.css');
  await ctx.css('speaker3d.css');
  const methods = methodsOf(ctx.auth);
  const timers = [];
  const spk = speaker3d({ state: 'spk-idle spk-breathe' });

  /* clock */
  const dateEl = h('p', { class: 'auth-date' });
  const clockEl = h('p', { class: 'auth-clock' });
  const tick = () => { const d = new Date(); dateEl.textContent = fmtDate(d); clockEl.textContent = fmtClock(d); };
  tick();
  timers.push(setInterval(tick, 1000));
  const hero = h('section', { class: 'auth-hero', 'aria-label': t('login.clock') }, dateEl, clockEl);

  /* form */
  const err = h('p', { class: 'form-error', role: 'alert' });
  const note = h('p', { class: 'auth-note', role: 'status' });
  const formChildren = [h('h1', {}, t('login.title'))];
  let userIn, pw, submit, fields;
  if (methods.password) {
    userIn = h('input', { class: 'input', name: 'username', autocomplete: methods.passkey ? 'username webauthn' : 'username', autocapitalize: 'none', spellcheck: false, enterKeyHint: 'next', value: draft.user, oninput: () => { draft.user = userIn.value; } });
    pw = passwordInput({ name: 'password', autocomplete: 'current-password', enterKeyHint: 'go', value: draft.pw, oninput: () => { draft.pw = pw.input.value; } });
    const help = h('p', { class: 'forgot-help', id: 'forgot-help', hidden: !draft.forgot }, t('login.forgotHelp'));
    const forgot = h('button', {
      type: 'button', class: 'linkbtn', 'aria-expanded': String(draft.forgot), 'aria-controls': 'forgot-help',
      onclick: () => { draft.forgot = !draft.forgot; help.hidden = !draft.forgot; forgot.setAttribute('aria-expanded', String(draft.forgot)); },
    }, t('login.forgot'));
    fields = h('div', { class: 'auth-fields' }, field(t('login.user'), userIn), field(t('login.pw'), pw.wrap), h('div', { class: 'forgot-row' }, forgot));
    submit = h('button', { type: 'submit', class: 'btn primary big wide' }, t('login.go'));
    formChildren.push(fields, help, err, submit);
  } else {
    formChildren.push(err);
  }
  if (methods.password && (methods.google || methods.passkey)) formChildren.push(h('p', { class: 'auth-or' }, t('common.or')));
  if (methods.google) {
    const g = h('button', { type: 'button', class: 'alt-btn', onclick: () => google(g) }, gMark(), t('login.google'));
    formChildren.push(g);
  }
  if (methods.passkey) {
    const p = h('button', { type: 'button', class: 'alt-btn', onclick: () => passkey(p) }, icon('passkey', 'pk'), t('login.pk'));
    formChildren.push(p);
  }
  formChildren.push(note);
  const form = h('form', { class: 'auth-form', novalidate: true, onsubmit: (e) => { e.preventDefault(); passwordLogin(); } }, formChildren);

  const lg = h('div', { class: 'auth-lg' }, h('div', { class: 'auth-top-gap' }), hero, h('div', { class: 'auth-mid-gap' }), form);
  const root = h('div', { class: 'auth' },
    h('div', { class: 'auth-bloom', 'aria-hidden': 'true' }), h('div', { class: 'auth-glow', 'aria-hidden': 'true' }),
    langToggle(), h('div', { class: 'auth-col' }, lg));

  // one model per page: in the hero on phone/iPad, above the form on desktop (D_Login)
  const desk = matchMedia('(min-width: 1280px)');
  const placeSpk = () => { if (desk.matches) form.prepend(spk.el); else hero.prepend(spk.el); };
  placeSpk();
  desk.addEventListener('change', placeSpk);

  /* behaviour */
  let locked = false;
  function setBusy(on, btn = submit) {
    if (btn) { btn.disabled = on; btn.classList.toggle('busy', on); if (btn === submit) btn.lastChild.textContent = t(on ? 'login.going' : 'login.go'); }
    spk.setState(on ? 'spk-listening' : locked ? 'spk-off' : 'spk-idle spk-breathe');
  }
  function showError(msg, invalid = []) {
    err.textContent = msg;
    note.textContent = '';
    [userIn, pw && pw.input].forEach((el) => el && el.setAttribute('aria-invalid', String(invalid.includes(el))));
    spk.flash('spk-error');
    if (fields && !ctx.motionReduced()) { fields.classList.remove('shake'); void fields.offsetWidth; fields.classList.add('shake'); }
  }
  function lock(sec) {
    let left = sec || 300;
    locked = true;
    submit.disabled = true;
    spk.setState('spk-off');
    const step = () => {
      err.textContent = t('login.lock', waitText(left));
      if (--left < 0) { clearInterval(timer); locked = false; submit.disabled = false; err.textContent = ''; spk.setState('spk-idle spk-breathe'); }
    };
    const timer = setInterval(step, 1000);
    timers.push(timer);
    step();
  }
  function success(user) {
    draft.user = ''; draft.pw = ''; draft.forgot = false;
    spk.flash('spk-success');
    if (ctx.motionReduced()) { ctx.signedIn(user); return; }
    setTimeout(() => root.classList.add('leaving'), 450);
    setTimeout(() => ctx.signedIn(user), 750);
  }
  async function passwordLogin() {
    if (locked) return;
    const u = userIn.value.trim().toLowerCase();
    if (!u || !pw.input.value) { showError(t('login.empty'), [!u ? userIn : pw.input]); (!u ? userIn : pw.input).focus(); return; }
    err.textContent = '';
    setBusy(true);
    try {
      const r = await ctx.api('/auth/login', { body: { username: u, password: pw.input.value }, allow401: true });
      setBusy(false);
      success(r.user);
    } catch (e) {
      setBusy(false);
      if (e.status === 429) { lock(e.retryAfter); return; }
      const disabled = e.status === 401 && /disabled/i.test(e.detail);
      showError(errorText(e, null, { 401: t(disabled ? 'login.disabled' : 'login.bad'), 403: t('login.pkNeeded') }), e.status === 401 && !disabled ? [pw.input] : []);
      pw.input.select();
    }
  }
  async function google(btn) {
    err.textContent = ''; note.textContent = '';
    let sheet = null;
    setBusy(true, btn);
    try {
      const credential = await googleCredential(ctx.auth.google_client_id, (renderInto, cancel) => {
        setBusy(false, btn);
        sheet = ctx.sheet({
          title: t('login.gTitle'), onClose: () => cancel(),
          build(body) { const slot = h('div', { class: 'gsi-slot' }); body.append(slot); requestAnimationFrame(() => renderInto(slot)); },
        });
      });
      if (sheet) sheet.close();
      setBusy(true, btn);
      const r = await googleSignIn(credential);
      setBusy(false, btn);
      success(r.user);
    } catch (e) {
      setBusy(false, btn);
      if (sheet) sheet.close();
      if (e.message === 'cancelled') return;
      if (e.message && e.message.startsWith('gsi-')) { showError(t('login.gUnavailable')); return; }
      showError(errorText(e, null, { 401: t('login.gNotMember'), 403: t('login.pkNeeded') }));
    }
  }
  async function passkey(btn) {
    err.textContent = ''; note.textContent = '';
    setBusy(true, btn);
    try {
      const r = await passkeySignIn();
      setBusy(false, btn);
      success(r.user);
    } catch (e) {
      setBusy(false, btn);
      if (e && (e.name === 'NotAllowedError' || e.name === 'AbortError')) { note.textContent = t('login.pkCancelled'); return; }
      showError(e && e.status != null ? errorText(e, null, { 401: t('login.pkFailed') }) : t('login.pkFailed'));
    }
  }

  if (userIn && !matchMedia('(pointer: coarse)').matches) setTimeout(() => (draft.user ? pw.input : userIn).focus({ preventScroll: true }), 950);
  document.title = `${t('login.title')} · ${t('app.name')}`;
  return {
    node: root,
    destroy() { timers.forEach(clearInterval); desk.removeEventListener('change', placeSpk); },
  };
}
