// Activity log (admin): newest first, grouped by day, "load more" pages with before_id.
import { h, icon, fmtTime, fmtDay } from '../ui.js';

const ACTION_TH = {
  login: 'เข้าสู่ระบบ', login_ok: 'เข้าสู่ระบบ', login_failed: 'เข้าสู่ระบบไม่สำเร็จ', logout: 'ออกจากระบบ', logout_all: 'ออกจากระบบทุกอุปกรณ์',
  say: 'ประกาศ', youtube: 'เล่น YouTube', play: 'เล่นลิงก์เสียง', stop: 'หยุดเล่น', pause: 'พัก', resume: 'เล่นต่อ',
  playlist_play: 'เล่นเพลย์ลิสต์', queue_skip: 'ข้ามรายการ', queue_next: 'ข้ามไปถัดไป', queue_prev: 'ย้อนกลับ', queue_jump: 'เลือกรายการในคิว', queue_clear: 'ล้างคิว',
  volume: 'ปรับเสียง', settings: 'แก้การตั้งค่า', settings_change: 'แก้การตั้งค่า', member_create: 'เพิ่มสมาชิก', member_update: 'แก้ไขสมาชิก', member_delete: 'ลบสมาชิก',
  password: 'เปลี่ยนรหัสผ่าน', password_change: 'เปลี่ยนรหัสผ่าน', setup: 'ตั้งค่าครั้งแรก', startup: 'บริการเริ่มทำงาน',
};
const ACTION_ICON = { say: 'announce', youtube: 'note', play: 'link', playlist_play: 'playlists', volume: 'vol-low', settings: 'settings', settings_change: 'settings', login: 'user', login_ok: 'user', login_failed: 'key', logout: 'logout', stop: 'stop', member_create: 'user', member_update: 'user', member_delete: 'user', password_change: 'key', queue_skip: 'playlists' };
const actorTh = (a) => (a === 'api-token' ? 'API token' : a === 'system' ? 'ระบบ' : a);
const PAGE = 50;

export default function activityView(ctx) {
  let lastId = null;
  let lastDay = null;
  const wrap = h('div', { class: 'panel glass act' }, h('div', { class: 'skeleton' }), h('div', { class: 'skeleton' }));
  const more = h('button', { class: 'btn wide', type: 'button', hidden: true, onclick: () => load() }, 'โหลดเพิ่ม');
  const node = h('div', {}, h('div', { class: 'page-head' }, h('h1', {}, 'ประวัติการใช้งาน')), wrap, more);
  let first = true;

  async function load() {
    more.classList.add('busy'); more.disabled = true;
    let rows;
    try {
      rows = await ctx.api(`/activity?limit=${PAGE}${lastId ? `&before_id=${lastId}` : ''}`);
    } catch (e) { ctx.fail(e); return; } finally { more.classList.remove('busy'); more.disabled = false; }
    if (first) { wrap.replaceChildren(); first = false; }
    if (!rows.length && !lastId) wrap.replaceChildren(h('div', { class: 'empty' }, icon('activity'), h('p', {}, 'ยังไม่มีประวัติการใช้งาน')));
    let ul = wrap.lastElementChild && wrap.lastElementChild.tagName === 'UL' ? wrap.lastElementChild : null;
    for (const r of rows) {
      const day = fmtDay(r.at);
      if (day !== lastDay) {
        lastDay = day;
        wrap.append(h('h2', { class: 'act-day' }, day));
        ul = h('ul', { class: 'list' });
        wrap.append(ul);
      }
      const key = r.action.replace(/ /g, '_');  // backend names use spaces ("login ok")
      const failed = /fail/.test(key);
      ul.append(h('li', { class: 'row', dataset: { id: r.id } },
        h('span', { class: 'thumb', style: failed ? { color: 'var(--danger)' } : null }, icon(ACTION_ICON[key] || 'activity')),
        h('span', { class: 'body' }, h('span', { class: 'title' }, `${actorTh(r.actor)}: ${ACTION_TH[key] || r.action}`),
          r.detail ? h('span', { class: 'sub' }, h('span', {}, r.detail)) : null),
        h('time', { dateTime: r.at }, fmtTime(r.at))));
    }
    if (rows.length) lastId = rows[rows.length - 1].id;
    more.hidden = rows.length < PAGE;
  }
  load();
  return { node };
}
