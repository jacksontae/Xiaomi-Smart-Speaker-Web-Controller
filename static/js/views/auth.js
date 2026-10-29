// First-run setup and sign-in screens.
import { api, thaiError, waitText } from '../api.js';
import { h, field, busy } from '../ui.js';

function mark() {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 64 64');
  s.setAttribute('class', 'auth-mark');
  s.setAttribute('aria-hidden', 'true');
  const u = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  u.setAttribute('href', '#i-mark');
  s.append(u);
  return s;
}

export function renderLogin(ctx, done) {
  const user = h('input', { class: 'input', name: 'username', autocomplete: 'username', autocapitalize: 'none', spellcheck: false, required: true, enterKeyHint: 'next' });
  const pw = h('input', { class: 'input', name: 'password', type: 'password', autocomplete: 'current-password', required: true, enterKeyHint: 'go' });
  const err = h('p', { class: 'form-error', role: 'alert' });
  const btn = h('button', { class: 'btn primary wide', type: 'submit' }, 'เข้าสู่ระบบ');
  let lockTimer = null;
  const lock = (sec) => {
    clearInterval(lockTimer);
    let left = sec || 60;
    btn.disabled = true;
    const tick = () => {
      err.textContent = `ลองผิดหลายครั้งเกินไป ลองใหม่ได้ในอีก ${waitText(left)}`;
      if (--left < 0) { clearInterval(lockTimer); btn.disabled = false; err.textContent = ''; }
    };
    tick();
    lockTimer = setInterval(tick, 1000);
  };
  const form = h('form', {
    onsubmit: async (e) => {
      e.preventDefault();
      err.textContent = '';
      await busy(btn, async () => {
        try {
          const r = await api('/auth/login', { body: { username: user.value.trim().toLowerCase(), password: pw.value }, allow401: true });
          clearInterval(lockTimer);
          done(r.user);
        } catch (e2) {
          if (e2.status === 429) return lock(e2.retryAfter);
          err.textContent = thaiError(e2, null, { 401: 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง หรือบัญชีถูกปิดใช้งาน' });
          pw.select();
        }
      });
      if (lockTimer && err.textContent.startsWith('ลองผิด')) btn.disabled = true;
    },
  }, field('ชื่อผู้ใช้', user), field('รหัสผ่าน', pw), err, btn);
  setTimeout(() => user.focus(), 50);
  return h('div', { class: 'auth' }, h('main', { class: 'auth-card glass-strong' },
    mark(), h('h1', {}, 'เข้าสู่ระบบลำโพง'),
    h('p', { class: 'lead' }, 'ใช้บัญชีที่ผู้ดูแลสร้างให้ ถ้ายังไม่มีบัญชี ขอให้ผู้ดูแลเพิ่มคุณในหน้าสมาชิก'),
    form));
}

export function renderSetup(ctx, done) {
  const token = h('input', { class: 'input', type: 'password', autocomplete: 'off', required: true });
  const name = h('input', { class: 'input', autocomplete: 'name', required: true, placeholder: 'เช่น แจ็คสัน' });
  const user = h('input', { class: 'input', autocomplete: 'username', autocapitalize: 'none', spellcheck: false, required: true, pattern: '[a-z0-9._\\-]{3,32}', placeholder: 'เช่น jackson' });
  const pw = h('input', { class: 'input', type: 'password', autocomplete: 'new-password', minLength: 8, required: true });
  const err = h('p', { class: 'form-error', role: 'alert' });
  const btn = h('button', { class: 'btn primary wide', type: 'submit' }, 'สร้างบัญชีผู้ดูแล');
  user.addEventListener('input', () => { user.value = user.value.toLowerCase(); });
  const form = h('form', {
    onsubmit: async (e) => {
      e.preventDefault();
      err.textContent = '';
      if (!/^[a-z0-9._-]{3,32}$/.test(user.value)) { err.textContent = 'ชื่อผู้ใช้ใช้ได้เฉพาะ a–z ตัวเลข จุด ขีด ยาว 3–32 ตัว'; user.focus(); return; }
      if (pw.value.length < 8) { err.textContent = 'รหัสผ่านต้องยาวอย่างน้อย 8 ตัวอักษร'; pw.focus(); return; }
      await busy(btn, async () => {
        try {
          const r = await api('/auth/setup', { body: { api_token: token.value.trim(), username: user.value, display_name: name.value.trim(), password: pw.value }, allow401: true });
          done(r.user);
        } catch (e2) {
          if (e2.status === 409) { location.reload(); return; }
          err.textContent = thaiError(e2, null, { 401: 'API token ไม่ถูกต้อง คัดลอกจากคำสั่ง ./speakerctl token อีกครั้ง' });
        }
      });
    },
  },
  field('API token', token, h('span', {}, 'รัน ', h('span', { class: 'code' }, './speakerctl token'), ' บนเครื่องที่ติดตั้งบริการ แล้ววางค่าที่ได้ที่นี่')),
  field('ชื่อที่แสดง', name),
  field('ชื่อผู้ใช้', user, 'ตัวพิมพ์เล็ก a–z ตัวเลข จุด หรือขีด 3–32 ตัว'),
  field('รหัสผ่าน', pw, 'อย่างน้อย 8 ตัวอักษร'),
  err, btn);
  setTimeout(() => token.focus(), 50);
  return h('div', { class: 'auth' }, h('main', { class: 'auth-card glass-strong' },
    mark(), h('h1', {}, 'ตั้งค่าครั้งแรก'),
    h('p', { class: 'lead' }, 'สร้างบัญชีผู้ดูแลคนแรก จากนั้นเพิ่มสมาชิกคนอื่นได้ในหน้าสมาชิก'),
    form));
}
