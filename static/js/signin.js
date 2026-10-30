// Sign-in methods beyond the password, offered only when GET /auth/state says so:
//   methods: { password, google, passkey }, google_client_id. Absent `methods` = password only (older server).
// Google: Google Identity Services (loaded from accounts.google.com only when Google is on and the button is used),
//   ID token -> POST /auth/google { credential } -> { user }.
// Passkey: POST /auth/passkey/options -> WebAuthn get() -> POST /auth/passkey/verify -> { user }.
import { api } from './api.js';
import { h } from './ui.js';
import { lang } from './i18n.js';

export function methodsOf(auth) {
  const m = auth && auth.methods;
  if (!m) return { password: true, google: false, passkey: false };
  return { password: !!m.password, google: !!m.google && !!auth.google_client_id, passkey: !!m.passkey && passkeySupported() };
}

/* ---------- Google ---------- */
const GSI_SRC = 'https://accounts.google.com/gsi/client';
let gsiLoading = null;
function loadGsi() {
  if (window.google && window.google.accounts && window.google.accounts.id) return Promise.resolve(window.google.accounts.id);
  if (!gsiLoading) {
    gsiLoading = new Promise((resolve, reject) => {
      const s = h('script', { src: GSI_SRC, async: true });
      const timer = setTimeout(() => reject(new Error('gsi-timeout')), 10000);
      s.onload = () => { clearTimeout(timer); resolve(window.google.accounts.id); };
      s.onerror = () => { clearTimeout(timer); gsiLoading = null; reject(new Error('gsi-load')); };
      document.head.append(s);
    });
  }
  return gsiLoading;
}

/**
 * Ask Google for an ID token. Tries the One Tap / FedCM prompt first; when the browser can't show it
 * (cooldown, blocked third-party cookies), calls `fallback(renderInto)` so the caller can show Google's own
 * button in a sheet: renderInto(el) draws it. Resolves with the credential (JWT) or rejects (cancelled).
 */
export async function googleCredential(clientId, fallback) {
  const gid = await loadGsi();
  return new Promise((resolve, reject) => {
    let done = false;
    const finish = (fn, v) => { if (!done) { done = true; fn(v); } };
    gid.initialize({
      client_id: clientId,
      callback: (r) => finish(resolve, r.credential),
      ux_mode: 'popup', auto_select: false, cancel_on_tap_outside: true, use_fedcm_for_prompt: true,
      itp_support: true, context: 'signin',
    });
    gid.prompt((n) => {
      const notShown = (n.isNotDisplayed && n.isNotDisplayed()) || (n.isSkippedMoment && n.isSkippedMoment());
      if (!notShown || done) return;
      fallback((el) => gid.renderButton(el, {
        type: 'standard', theme: document.documentElement.dataset.theme === 'dark' ? 'filled_black' : 'outline',
        size: 'large', shape: 'pill', text: 'continue_with', locale: lang(), width: Math.min(360, el.clientWidth || 320),
      }), () => finish(reject, new Error('cancelled')));
    });
  });
}

export const googleSignIn = (credential) => api('/auth/google', { body: { credential }, allow401: true });

/* ---------- passkeys (WebAuthn) ---------- */
export function passkeySupported() {
  return !!(window.PublicKeyCredential && window.isSecureContext && navigator.credentials && navigator.credentials.get);
}

const b64uToBuf = (s) => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(s.length / 4) * 4, '=')), (c) => c.charCodeAt(0)).buffer;
const bufToB64u = (b) => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

function requestOptions(json) {
  if (PublicKeyCredential.parseRequestOptionsFromJSON) return PublicKeyCredential.parseRequestOptionsFromJSON(json);
  return { ...json, challenge: b64uToBuf(json.challenge), allowCredentials: (json.allowCredentials || []).map((c) => ({ ...c, id: b64uToBuf(c.id) })) };
}
function credentialJson(c) {
  if (typeof c.toJSON === 'function') { try { return c.toJSON(); } catch { /* Safari < 17.4: encode by hand */ } }
  const r = c.response;
  return {
    id: c.id, rawId: bufToB64u(c.rawId), type: c.type, authenticatorAttachment: c.authenticatorAttachment || null,
    clientExtensionResults: c.getClientExtensionResults ? c.getClientExtensionResults() : {},
    response: {
      clientDataJSON: bufToB64u(r.clientDataJSON), authenticatorData: bufToB64u(r.authenticatorData),
      signature: bufToB64u(r.signature), userHandle: r.userHandle ? bufToB64u(r.userHandle) : null,
    },
  };
}

/** Full passkey sign-in. Resolves { user }. Rejects with DOMException NotAllowedError when the person cancels. */
export async function passkeySignIn() {
  const opts = await api('/auth/passkey/options', { body: {}, allow401: true });
  const publicKey = requestOptions(opts.publicKey || opts);
  const cred = await navigator.credentials.get({ publicKey });
  const body = { credential: credentialJson(cred) };
  if (opts.state) body.state = opts.state; // server-issued handle for the challenge, if it uses one
  return api('/auth/passkey/verify', { body, allow401: true });
}
