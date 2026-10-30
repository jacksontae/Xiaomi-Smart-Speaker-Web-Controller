// Strings: English default, Thai switchable (prefs 'lang', localStorage spk.lang). Every user-visible string goes
// through t(key). Glossary: prototype proto/I18N.md (Now playing, Announce, Music, Playlists, Members, Sign in, ...).
//
// Core strings (shell, auth, errors) live below. A view registers its own strings next to its code so
// engineers don't collide in one big file:
//
//   import { register, t } from '../i18n.js';
//   register({
//     en: { 'music.title': 'Music', 'music.results': (n) => `${n} results` },
//     th: { 'music.title': 'เพลง', 'music.results': (n) => `${n} รายการ` },
//   });
//   t('music.results', 3)
//
// Keys are namespaced by view ('now.', 'music.', ...). A value is a string, or a function for counts/variables.
// Missing Thai falls back to English; a missing key renders the key itself (easy to spot in screenshots).
// User content (titles, names, announcement text) is never translated. No polite particles in UI chrome.

import { get as getPref, onChange } from './prefs.js';

const dict = { en: {}, th: {} };

export function register(d) {
  for (const lang of Object.keys(dict)) Object.assign(dict[lang], d[lang] || {});
}

export const lang = () => getPref('lang');
export const locale = () => (lang() === 'th' ? 'th-TH-u-ca-gregory' : 'en-GB');

export function t(key, ...args) {
  const v = dict[lang()][key] ?? dict.en[key];
  if (v == null) { console.warn('i18n: missing', key); return key; }
  return typeof v === 'function' ? v(...args) : v;
}

/** Re-run fn when the language changes (shell and views are re-rendered by app.js; this is for long-lived bits). */
export function onLang(fn) {
  let cur = lang();
  return onChange((s) => { if (s.lang !== cur) { cur = s.lang; fn(cur); } });
}

/* ---------- formatting: follows the app language, 24 h clock, Gregorian years ---------- */
export function fmtDate(d = new Date()) {
  // "Thursday, 29 October" / "วันพฤหัสบดี 29 ตุลาคม"
  const wd = d.toLocaleDateString(locale(), { weekday: 'long' });
  const dm = d.toLocaleDateString(locale(), { day: 'numeric', month: 'long' });
  return lang() === 'th' ? `วัน${wd.replace(/^วัน/, '')} ${dm}` : `${wd}, ${dm}`;
}
export const fmtClock = (d = new Date()) => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
export function fmtDur(sec) {
  if (sec == null || !isFinite(sec)) return '';
  sec = Math.max(0, Math.round(sec));
  const hh = Math.floor(sec / 3600), mm = Math.floor((sec % 3600) / 60), ss = sec % 60;
  return hh ? `${hh}:${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}` : `${mm}:${String(ss).padStart(2, '0')}`;
}
export function fmtRel(iso) {
  if (!iso) return '';
  const rtf = new Intl.RelativeTimeFormat(locale(), { numeric: 'auto' });
  const s = (new Date(iso) - Date.now()) / 1000, a = Math.abs(s);
  if (a < 60) return t('time.justNow');
  if (a < 3600) return rtf.format(Math.round(s / 60), 'minute');
  if (a < 86400) return rtf.format(Math.round(s / 3600), 'hour');
  if (a < 86400 * 30) return rtf.format(Math.round(s / 86400), 'day');
  return new Date(iso).toLocaleDateString(locale(), { day: 'numeric', month: 'short', year: 'numeric' });
}
export const roleLabel = (role) => t(`role.${role}`);

register({
  en: {
    'app.name': 'Speaker',
    'app.loadFailed': 'The app couldn\'t start',
    'app.retry': 'Try again',
    'app.loading': 'Loading…',
    'app.needsJs': 'This page needs JavaScript.',
    'lang.label': 'Language',
    'nav.main': 'Main menu',
    'nav.now': 'Now playing', 'tab.now': 'Now',
    'nav.announce': 'Announce',
    'nav.music': 'Music',
    'nav.playlists': 'Playlists',
    'nav.members': 'Members',
    'nav.settings': 'Speaker settings',
    'nav.activity': 'Activity',
    'nav.account': 'Account',
    'nav.prefs': 'Account & app settings',
    'nav.appSettings': 'App settings',
    'nav.auth': 'Sign-in methods',
    'nav.help': 'Help',
    'nav.back': 'Back',
    'role.viewer': 'Viewer', 'role.operator': 'Operator', 'role.admin': 'Owner',
    'acct.my': 'My account',
    'acct.aria': (name, role) => `Account: ${name}, ${role}`,
    'acct.changePw': 'Change password',
    'acct.signOut': 'Sign out',
    'acct.signOutAll': 'Sign out of all devices',
    'acct.signOutAllText': 'Signs out every device using this account, including this one.',
    'acct.signedOut': 'Signed out',
    'pw.current': 'Current password', 'pw.new': 'New password', 'pw.confirm': 'Type the new password again',
    'pw.rule': 'At least 8 characters. Other devices signed in to this account will be signed out.',
    'pw.errCur': 'Enter your current password first', 'pw.errLen': 'New password needs at least 8 characters',
    'pw.errMatch': 'The new passwords don\'t match', 'pw.wrongCur': 'Current password is wrong',
    'pw.save': 'Change password', 'pw.changed': 'Password changed',
    'spk.label': 'Speaker', 'spk.pick': 'Choose a speaker', 'spk.offline': 'Offline', 'spk.online': 'Online',
    'spk.connecting': 'Connecting…', 'spk.why': 'Can\'t reach it right now', 'spk.switched': (n) => `Now controlling ${n}`,
    'spk.unknown': 'Speaker',
    'common.close': 'Close', 'common.cancel': 'Cancel', 'common.save': 'Save', 'common.done': 'Done',
    'common.or': 'or', 'common.showPw': 'Show password', 'common.hidePw': 'Hide password', 'common.help': 'Help',
    'common.confirm': 'Confirm',
    'time.justNow': 'just now',
    'ph.soon': 'This page is being rebuilt for the new app.',
    'route.forbidden': (role) => `This page is for ${role}s and above`,
    'err.unexpected': 'Something went wrong. Reload the page and try again.',
    'err.network': 'Can\'t reach the server. Check your internet connection and try again.',
    'err.module': 'This page didn\'t load. Check your connection. If you use Brave Shields or an ad blocker, allow this site, then try again.',
    'err.session': 'You were signed out. Sign in again.',
    'err.header': 'The browser sent an incomplete request. Reload the page.',
    'err.forbidden': (role) => `Your account is a ${role}, so you can't do this. Ask the owner to change your role.`,
    'err.notFound': 'Not found. It may have been deleted.',
    'err.conflict': (d) => `Can't do this right now${d ? ` (${d})` : ''}`,
    'err.invalid': (d) => `That isn't valid${d ? `: ${d}` : ''}`,
    'err.tooMany': (w) => `Too many tries. Wait ${w} and try again.`,
    'err.youtube': 'Couldn\'t get the audio from YouTube. Try again or pick something else.',
    'err.speaker': 'Can\'t reach the speaker. Check that it\'s on and on the same network.',
    'err.server': 'The server had a problem. Try again.',
    'wait.sec': (n) => `${n} ${n === 1 ? 'second' : 'seconds'}`,
    'wait.min': (n) => `${n} ${n === 1 ? 'minute' : 'minutes'}`,
  },
  th: {
    'app.name': 'ลำโพง',
    'app.loadFailed': 'เปิดแอปไม่ได้',
    'app.retry': 'ลองอีกครั้ง',
    'app.loading': 'กำลังโหลด…',
    'app.needsJs': 'หน้านี้ต้องเปิดใช้ JavaScript',
    'lang.label': 'ภาษา',
    'nav.main': 'เมนูหลัก',
    'nav.now': 'เล่นอยู่', 'tab.now': 'เล่นอยู่',
    'nav.announce': 'ประกาศ',
    'nav.music': 'เพลง',
    'nav.playlists': 'เพลย์ลิสต์',
    'nav.members': 'สมาชิก',
    'nav.settings': 'ตั้งค่าลำโพง',
    'nav.activity': 'ประวัติการใช้งาน',
    'nav.account': 'บัญชี',
    'nav.prefs': 'บัญชีและการตั้งค่าแอป',
    'nav.appSettings': 'ตั้งค่าแอป',
    'nav.auth': 'วิธีเข้าสู่ระบบ',
    'nav.help': 'คู่มือการใช้งาน',
    'nav.back': 'กลับ',
    'role.viewer': 'ผู้ชม', 'role.operator': 'ผู้ควบคุม', 'role.admin': 'เจ้าของ',
    'acct.my': 'บัญชีของฉัน',
    'acct.aria': (name, role) => `บัญชี ${name} ${role}`,
    'acct.changePw': 'เปลี่ยนรหัสผ่าน',
    'acct.signOut': 'ออกจากระบบ',
    'acct.signOutAll': 'ออกจากระบบทุกอุปกรณ์',
    'acct.signOutAllText': 'ออกจากระบบทุกเครื่องที่ใช้บัญชีนี้ รวมถึงเครื่องนี้',
    'acct.signedOut': 'ออกจากระบบแล้ว',
    'pw.current': 'รหัสผ่านปัจจุบัน', 'pw.new': 'รหัสผ่านใหม่', 'pw.confirm': 'พิมพ์รหัสผ่านใหม่อีกครั้ง',
    'pw.rule': 'อย่างน้อย 8 ตัวอักษร อุปกรณ์อื่นที่เข้าบัญชีนี้อยู่จะถูกออกจากระบบ',
    'pw.errCur': 'ใส่รหัสผ่านปัจจุบันก่อน', 'pw.errLen': 'รหัสผ่านใหม่ต้องมีอย่างน้อย 8 ตัว',
    'pw.errMatch': 'รหัสผ่านใหม่สองช่องไม่ตรงกัน', 'pw.wrongCur': 'รหัสผ่านปัจจุบันไม่ถูกต้อง',
    'pw.save': 'เปลี่ยนรหัสผ่าน', 'pw.changed': 'เปลี่ยนรหัสผ่านแล้ว',
    'spk.label': 'ลำโพง', 'spk.pick': 'เลือกลำโพง', 'spk.offline': 'ออฟไลน์', 'spk.online': 'ออนไลน์',
    'spk.connecting': 'กำลังเชื่อมต่อ…', 'spk.why': 'ตอนนี้ติดต่อลำโพงนี้ไม่ได้', 'spk.switched': (n) => `กำลังควบคุม ${n}`,
    'spk.unknown': 'ลำโพง',
    'common.close': 'ปิด', 'common.cancel': 'ยกเลิก', 'common.save': 'บันทึก', 'common.done': 'เสร็จ',
    'common.or': 'หรือ', 'common.showPw': 'แสดงรหัสผ่าน', 'common.hidePw': 'ซ่อนรหัสผ่าน', 'common.help': 'คู่มือการใช้งาน',
    'common.confirm': 'ยืนยัน',
    'time.justNow': 'เมื่อสักครู่',
    'ph.soon': 'หน้านี้กำลังทำใหม่สำหรับแอปเวอร์ชันใหม่',
    'route.forbidden': (role) => `หน้านี้สำหรับ${role}ขึ้นไป`,
    'err.unexpected': 'เกิดข้อผิดพลาด ลองโหลดหน้าใหม่',
    'err.network': 'เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ ตรวจการเชื่อมต่ออินเทอร์เน็ตแล้วลองอีกครั้ง',
    'err.module': 'โหลดหน้านี้ไม่ได้ ตรวจการเชื่อมต่อ ถ้าใช้ Brave Shields หรือตัวบล็อกโฆษณา ให้อนุญาตเว็บนี้ แล้วลองอีกครั้ง',
    'err.session': 'หมดเวลาการเข้าสู่ระบบ เข้าสู่ระบบอีกครั้ง',
    'err.header': 'เบราว์เซอร์ส่งคำขอไม่ครบ ลองโหลดหน้าใหม่',
    'err.forbidden': (role) => `บัญชีนี้เป็น${role} จึงทำรายการนี้ไม่ได้ ขอให้เจ้าของปรับสิทธิ์ให้`,
    'err.notFound': 'ไม่พบรายการนี้ อาจถูกลบไปแล้ว',
    'err.conflict': (d) => `ทำรายการนี้ไม่ได้ในตอนนี้${d ? ` (${d})` : ''}`,
    'err.invalid': (d) => `ข้อมูลไม่ถูกต้อง${d ? `: ${d}` : ''}`,
    'err.tooMany': (w) => `ลองหลายครั้งเกินไป รอ ${w} แล้วลองใหม่`,
    'err.youtube': 'ดึงเสียงจาก YouTube ไม่สำเร็จ ลองอีกครั้งหรือเลือกรายการอื่น',
    'err.speaker': 'ติดต่อลำโพงไม่ได้ ตรวจว่าลำโพงเปิดอยู่และต่อเครือข่ายเดียวกัน',
    'err.server': 'เซิร์ฟเวอร์ขัดข้อง ลองใหม่อีกครั้ง',
    'wait.sec': (n) => `${n} วินาที`,
    'wait.min': (n) => `${n} นาที`,
  },
});
