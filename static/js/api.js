// Thin fetch wrapper for the web-v2 contract: cookie session, JSON, X-Requested-With on writes.

export class ApiError extends Error {
  constructor(status, detail, retryAfter = null) {
    super(detail || `HTTP ${status}`);
    this.status = status;
    this.detail = detail || '';
    this.retryAfter = retryAfter;
  }
}

let onUnauthorized = null;
export function setUnauthorizedHandler(fn) { onUnauthorized = fn; }

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
    const err = new ApiError(r.status, data && data.detail, Number.isFinite(retry) ? retry : null);
    if (r.status === 401 && !allow401 && onUnauthorized) onUnauthorized(err);
    throw err;
  }
  return data;
}

export const ROLE_TH = { admin: 'ผู้ดูแล', operator: 'ผู้ควบคุม', viewer: 'ผู้ชม' };

export function waitText(sec) {
  if (!sec || sec < 60) return `${Math.max(1, sec || 30)} วินาที`;
  return `${Math.ceil(sec / 60)} นาที`;
}

/** Plain-Thai explanation for an ApiError. `ctx` lets callers override per status. */
export function thaiError(e, user, ctx = {}) {
  if (!(e instanceof ApiError)) return 'เกิดข้อผิดพลาดที่ไม่คาดคิด ลองโหลดหน้าใหม่';
  if (ctx[e.status]) return ctx[e.status];
  switch (e.status) {
    case 0: return 'เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ ตรวจว่าเครื่องนี้ยังต่อ Wi‑Fi วงเดียวกับลำโพง';
    case 401: return 'หมดเวลาการเข้าสู่ระบบ เข้าสู่ระบบอีกครั้ง';
    case 403:
      if (/header/i.test(e.detail)) return 'เบราว์เซอร์ส่งคำขอไม่ครบ ลองโหลดหน้าใหม่';
      return `บัญชีนี้เป็น${ROLE_TH[user?.role] || 'ผู้ใช้'} จึงทำรายการนี้ไม่ได้ ขอให้ผู้ดูแลปรับสิทธิ์ให้`;
    case 404: return 'ไม่พบรายการนี้ อาจถูกลบไปแล้ว';
    case 409: return `ทำรายการนี้ไม่ได้ในตอนนี้${e.detail ? ` (${e.detail})` : ''}`;
    case 400: case 422: return `ข้อมูลไม่ถูกต้อง${e.detail ? `: ${e.detail}` : ''}`;
    case 429: return `ลองหลายครั้งเกินไป รอ ${waitText(e.retryAfter)} แล้วลองใหม่`;
    case 502: return 'ดึงเสียงจาก YouTube ไม่สำเร็จ ลองอีกครั้งหรือเลือกรายการอื่น';
    case 503: return 'ติดต่อลำโพงไม่ได้ ตรวจว่าลำโพงเปิดอยู่และต่อเครือข่ายเดียวกัน';
    default: return 'เซิร์ฟเวอร์ขัดข้อง ลองใหม่อีกครั้ง';
  }
}
