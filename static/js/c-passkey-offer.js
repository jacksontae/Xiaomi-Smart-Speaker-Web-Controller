// Passkey creation (WebAuthn create()) plus the two prompts that follow a sign-in:
//   - the one-time offer after a password/Google sign-in on a passkey-capable device (boards Login/T_/D_ "offer":
//     Create passkey / Not now / Don't ask again; "Don't ask again" stores spk.pkOffer=never on this device);
//   - the "passkey_required" prompt: GET /auth/state says the owner requires admins to use a passkey and this
//     admin has none yet. Shown on every app start until they add one (no "don't ask again").
// app.js calls maybePrompt() when the app starts; account.js uses createPasskey() for "Add passkey".
import { h, icon, busy, toast } from './ui.js';
import { register, t } from './i18n.js';
import { openSheet } from './sheet.js';
import { errorText } from './api.js';
import { passkeySupported } from './signin.js';

register({
  en: {
    'pko.title': 'Sign in faster next time',
    'pko.body': (dev) => `Create a passkey and use ${dev} instead of typing your password on this device.`,
    'pko.create': 'Create passkey', 'pko.later': 'Not now', 'pko.never': 'Don\'t ask again',
    'pko.note': 'You can add or remove passkeys later in Account.',
    'pko.reqTitle': 'Add a passkey to keep signing in',
    'pko.reqBody': 'The owner requires a passkey for admin accounts. Create one on this device now; next time you sign in with it instead of your password.',
    'pko.reqLater': 'Later',
    'pko.added': 'Passkey added',
    'pko.cancelled': 'No passkey was created.',
    'pko.failed': 'This device couldn\'t create a passkey. Try again, or add one later in Account.',
    'pko.exists': 'This device already has a passkey for your account.',
    'pko.unlock.face': 'Face ID', 'pko.unlock.touch': 'Touch ID', 'pko.unlock.hello': 'Windows Hello',
    'pko.unlock.any': 'your fingerprint, face or device PIN',
  },
  th: {
    'pko.title': 'ครั้งหน้าเข้าสู่ระบบได้เร็วขึ้น',
    'pko.body': (dev) => `สร้างพาสคีย์ไว้ แล้วใช้ ${dev} แทนการพิมพ์รหัสผ่านบนเครื่องนี้`,
    'pko.create': 'สร้างพาสคีย์', 'pko.later': 'ไว้ทีหลัง', 'pko.never': 'ไม่ต้องถามอีก',
    'pko.note': 'เพิ่มหรือลบพาสคีย์ได้ภายหลังในหน้าบัญชี',
    'pko.reqTitle': 'เพิ่มพาสคีย์เพื่อเข้าสู่ระบบต่อได้',
    'pko.reqBody': 'เจ้าของกำหนดให้บัญชีผู้ดูแลต้องใช้พาสคีย์ สร้างพาสคีย์บนเครื่องนี้ไว้เลย ครั้งหน้าเข้าสู่ระบบด้วยพาสคีย์แทนรหัสผ่าน',
    'pko.reqLater': 'ไว้ทีหลัง',
    'pko.added': 'เพิ่มพาสคีย์แล้ว',
    'pko.cancelled': 'ยังไม่ได้สร้างพาสคีย์',
    'pko.failed': 'เครื่องนี้สร้างพาสคีย์ไม่สำเร็จ ลองอีกครั้ง หรือเพิ่มภายหลังในหน้าบัญชี',
    'pko.exists': 'เครื่องนี้มีพาสคีย์ของบัญชีคุณอยู่แล้ว',
    'pko.unlock.face': 'Face ID', 'pko.unlock.touch': 'Touch ID', 'pko.unlock.hello': 'Windows Hello',
    'pko.unlock.any': 'ลายนิ้วมือ ใบหน้า หรือ PIN ของเครื่อง',
  },
});

const OFFER_KEY = 'spk.pkOffer';

/* ---------- device naming ---------- */
const ua = () => navigator.userAgent || '';
/** A default passkey name for this device: "iPhone", "Chrome on Mac", "Windows Hello", ... */
export function deviceName() {
  const s = ua();
  if (/iPhone/.test(s)) return 'iPhone';
  if (/iPad/.test(s) || (/Macintosh/.test(s) && navigator.maxTouchPoints > 1)) return 'iPad';
  if (/Android/.test(s)) return 'Android';
  const browser = /Edg\//.test(s) ? 'Edge' : /Firefox\//.test(s) ? 'Firefox' : /Chrome\//.test(s) ? 'Chrome' : /Safari\//.test(s) ? 'Safari' : '';
  if (/Windows/.test(s)) return 'Windows Hello';
  const os = /Mac OS X|Macintosh/.test(s) ? 'Mac' : /Linux/.test(s) ? 'Linux' : '';
  if (browser && os) return `${browser} on ${os}`;
  return 'Passkey';
}
/** How this device unlocks a passkey, for the offer text. */
function unlockWord() {
  const s = ua();
  if (/iPhone|iPad/.test(s)) return t('pko.unlock.face');
  if (/Macintosh/.test(s)) return t('pko.unlock.touch');
  if (/Windows/.test(s)) return t('pko.unlock.hello');
  return t('pko.unlock.any');
}

/* ---------- WebAuthn create() ---------- */
const b64uToBuf = (s) => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(s.length / 4) * 4, '=')), (c) => c.charCodeAt(0)).buffer;
const bufToB64u = (b) => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

function creationOptions(json) {
  if (PublicKeyCredential.parseCreationOptionsFromJSON) return PublicKeyCredential.parseCreationOptionsFromJSON(json);
  return {
    ...json,
    challenge: b64uToBuf(json.challenge),
    user: { ...json.user, id: b64uToBuf(json.user.id) },
    excludeCredentials: (json.excludeCredentials || []).map((c) => ({ ...c, id: b64uToBuf(c.id) })),
  };
}
function attestationJson(c) {
  if (typeof c.toJSON === 'function') { try { return c.toJSON(); } catch { /* older Safari: encode by hand */ } }
  const r = c.response;
  return {
    id: c.id, rawId: bufToB64u(c.rawId), type: c.type, authenticatorAttachment: c.authenticatorAttachment || null,
    clientExtensionResults: c.getClientExtensionResults ? c.getClientExtensionResults() : {},
    response: {
      clientDataJSON: bufToB64u(r.clientDataJSON), attestationObject: bufToB64u(r.attestationObject),
      transports: r.getTransports ? r.getTransports() : [],
    },
  };
}

/** True when this server offers passkeys (auth.methods.passkey) and this browser can make one here. */
export function passkeyCapable(auth) {
  return !!(auth && auth.methods && auth.methods.passkey) && passkeySupported() && !!(navigator.credentials && navigator.credentials.create);
}

/**
 * Register a passkey for the signed-in member: POST /me/passkeys/options -> create() -> POST /me/passkeys.
 * Resolves the new passkey row. Rejects with DOMException (NotAllowedError = cancelled) or ApiError.
 */
export async function createPasskey(api, name = deviceName()) {
  const opts = await api('/me/passkeys/options', { body: {} });
  const publicKey = creationOptions(opts.publicKey || opts);
  const cred = await navigator.credentials.create({ publicKey });
  return api('/me/passkeys', { body: { credential: attestationJson(cred), name } });
}

/** Plain-language text for a failed createPasskey(); '' when the person just cancelled. */
export function createError(e, user) {
  if (!e) return t('pko.failed');
  if (e.name === 'NotAllowedError' || e.name === 'AbortError') return '';
  if (e.name === 'InvalidStateError') return t('pko.exists');
  if (e.status != null) return errorText(e, user, { 409: t('pko.exists') });
  return t('pko.failed');
}

/* ---------- prompts after sign-in ---------- */
const prompted = new WeakSet(); // once per signed-in user object (the app is rebuilt on a language switch)

function readNever() { try { return localStorage.getItem(OFFER_KEY) === 'never'; } catch { return false; } }
function writeNever() { try { localStorage.setItem(OFFER_KEY, 'never'); } catch { /* asks again next time */ } }

/**
 * Called by app.js when the app starts. fresh = the person just signed in on the login/setup screen (not a
 * reload with an existing session). Asks GET /auth/state itself so it sees the signed-in view of it.
 */
export async function maybePrompt({ api, user, fresh }) {
  if (!user || prompted.has(user)) return;
  prompted.add(user);
  let auth;
  try { auth = await api('/auth/state'); } catch { return; }
  if (!passkeyCapable(auth) || !auth.user) return;
  if (auth.passkey_required) { setTimeout(() => sheet({ api, user: auth.user, required: true }), 600); return; }
  if (fresh && !auth.user.has_passkey && !readNever()) setTimeout(() => sheet({ api, user: auth.user, required: false }), 700);
}

function sheet({ api, user, required }) {
  openSheet({
    label: t(required ? 'pko.reqTitle' : 'pko.title'),
    build(body, s) {
      const err = h('p', { class: 'form-error', role: 'alert' });
      const create = h('button', { type: 'button', class: 'btn primary big wide' }, t('pko.create'));
      create.addEventListener('click', () => busy(create, async () => {
        err.textContent = '';
        try {
          await createPasskey(api);
          s.close();
          toast(t('pko.added'), 'ok');
        } catch (e) {
          err.textContent = createError(e, user) || t('pko.cancelled');
        }
      }).catch(() => {}));
      const later = h('button', { type: 'button', class: 'linkbtn', onclick: () => s.close() }, t(required ? 'pko.reqLater' : 'pko.later'));
      const never = required ? null : h('button', { type: 'button', class: 'linkbtn c-muted-link', onclick: () => { writeNever(); s.close(); } }, t('pko.never'));
      body.classList.add('pko');
      body.append(
        h('span', { class: 'pko-ic', 'aria-hidden': 'true' }, icon('passkey', 'lg')),
        h('h2', { class: 'pko-h' }, t(required ? 'pko.reqTitle' : 'pko.title')),
        h('p', { class: 'muted pko-p' }, required ? t('pko.reqBody') : t('pko.body', unlockWord())),
        err, create,
        h('div', { class: 'pko-links' }, later, never),
        h('p', { class: 'small pko-p' }, t('pko.note')));
      injectCss();
    },
  });
}

// The sheet opens over any page, so its few rules ship with this module instead of a view stylesheet.
let cssDone = false;
function injectCss() {
  if (cssDone) return;
  cssDone = true;
  document.head.append(h('style', {}, `
.sheet-body.pko { align-items: center; text-align: center; }
.pko-ic { width: 56px; height: 56px; border-radius: 999px; background: var(--accent-tint); color: var(--accent); display: flex; align-items: center; justify-content: center; }
.pko-h { font-size: 22px; line-height: 1.35; font-weight: 700; }
.pko-p { max-width: 380px; }
.pko-links { display: flex; justify-content: space-between; gap: 8px; align-self: stretch; margin-top: -6px; }
.pko-links:has(> :only-child) { justify-content: center; }
.c-muted-link { color: var(--ink-2); }
`));
}
