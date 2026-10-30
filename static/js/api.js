// Thin fetch wrapper for the server contract: cookie session, JSON, X-Requested-With on writes.
import { t, roleLabel } from './i18n.js';

export class ApiError extends Error {
  constructor(status, detail, retryAfter = null) {
    super(detail || `HTTP ${status}`);
    this.status = status;
    this.detail = detail || '';
    this.retryAfter = retryAfter;
  }
}

let onUnauthorized = null;
/** app.js registers this: a 401 on any call (unless allow401) means the session ended. */
export function setUnauthorizedHandler(fn) { onUnauthorized = fn; }

/**
 * api('/status') GETs; api('/say', { body }) POSTs JSON; pass { method } for PUT/PATCH/DELETE.
 * Throws ApiError (status 0 = network). 204 resolves to null.
 */
export async function api(path, { method, body, signal, allow401 = false } = {}) {
  const m = method || (body !== undefined ? 'POST' : 'GET');
  const headers = { Accept: 'application/json' };
  if (m !== 'GET') headers['X-Requested-With'] = 'speaker-web';
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let r;
  try {
    r = await fetch(path, {
      method: m, headers, signal, credentials: 'same-origin', cache: 'no-store',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new ApiError(0, 'network');
  }
  if (r.status === 204) return null;
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    const retry = parseInt(r.headers.get('Retry-After') || '', 10);
    const detail = data && (typeof data.detail === 'string' ? data.detail : '');
    const err = new ApiError(r.status, detail, Number.isFinite(retry) ? retry : null);
    if (r.status === 401 && !allow401 && onUnauthorized) onUnauthorized(err);
    throw err;
  }
  return data;
}

export function waitText(sec) {
  if (!sec || sec < 60) return t('wait.sec', Math.max(1, sec || 30));
  return t('wait.min', Math.ceil(sec / 60));
}

/** Plain-language explanation of an error in the app language. `overrides` maps status -> text. */
export function errorText(e, user, overrides = {}) {
  if (!(e instanceof ApiError)) return t('err.unexpected');
  if (overrides[e.status]) return overrides[e.status];
  switch (e.status) {
    case 0: return t('err.network');
    case 401: return t('err.session');
    case 403:
      if (/header/i.test(e.detail)) return t('err.header');
      return t('err.forbidden', user ? roleLabel(user.role) : '');
    case 404: return t('err.notFound');
    case 409: return t('err.conflict', e.detail);
    case 400: case 422: return t('err.invalid', e.detail);
    case 429: return t('err.tooMany', waitText(e.retryAfter));
    case 502: return t('err.youtube');
    case 503: return t('err.speaker');
    default: return t('err.server');
  }
}
