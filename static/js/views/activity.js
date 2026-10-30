// Activity (boards Activity / T_Activity / D_Activity). Owner only. GET /activity?limit=&before_id= (newest first).
// Filters (All / Playback / Account / Failed) apply to what is loaded; "Show older" pages back by id.
// Phone/iPad: segmented filter on top; desktop: filter list on the left, time column on the left of each row.
import { h, icon, segmented, busy } from '../ui.js';
import { register, t, fmtClock } from '../i18n.js';
import { cIcon, tile, phoneBack, fmtDayHead, sameDay } from '../c-kit.js';

register({
  en: {
    'act.all': 'All', 'act.play': 'Playback', 'act.acct': 'Account', 'act.fail': 'Failed', 'act.filter': 'Show only',
    'act.older': 'Show older', 'act.noOlder': 'That\'s everything. Older entries aren\'t kept.',
    'act.empty': 'Nothing like this in the entries shown.', 'act.none': 'Nothing has happened yet.',
    'act.system': 'System',
    'act.say': 'Announced', 'act.play.url': 'Played an audio link', 'act.youtube': 'Played from YouTube',
    'act.volume': 'Changed the volume', 'act.stop': 'Stopped playback', 'act.playlist': 'Played a playlist',
    'act.skip': 'Skipped a track', 'act.schedRun': 'Played on schedule', 'act.schedMiss': 'Scheduled play failed',
    'act.schedNew': 'Added a schedule', 'act.schedEdit': 'Changed a schedule', 'act.schedDel': 'Deleted a schedule',
    'act.radioFav': 'Saved a station', 'act.radioUnfav': 'Removed a saved station',
    'act.fileUp': 'Uploaded a file', 'act.fileRename': 'Renamed a file', 'act.fileDel': 'Deleted a file',
    'act.talk': 'Talked live',
    'act.login': 'Signed in', 'act.loginFail': 'Sign-in failed', 'act.logout': 'Signed out',
    'act.pw': 'Changed their password', 'act.memNew': 'Added a member', 'act.memEdit': 'Changed a member', 'act.memDel': 'Deleted a member',
    'act.gLink': 'Linked a Google account', 'act.gUnlink': 'Unlinked a Google account',
    'act.pkAdd': 'Added a passkey', 'act.pkRename': 'Renamed a passkey', 'act.pkDel': 'Removed a passkey',
    'act.settings': 'Changed speaker settings',
    'act.d.from': (ip) => `From ${ip}`, 'act.d.gFrom': (ip) => `With Google, from ${ip}`, 'act.d.pkFrom': (ip) => `With a passkey, from ${ip}`,
    'act.d.setup': 'First-time setup', 'act.d.allDevices': 'On all devices',
  },
  th: {
    'act.all': 'ทั้งหมด', 'act.play': 'เล่นเสียง', 'act.acct': 'บัญชี', 'act.fail': 'ไม่สำเร็จ', 'act.filter': 'แสดงเฉพาะ',
    'act.older': 'ดูเก่ากว่านี้', 'act.noOlder': 'แสดงถึงรายการเก่าที่สุดแล้ว',
    'act.empty': 'ไม่มีรายการแบบนี้ในช่วงที่แสดงอยู่', 'act.none': 'ยังไม่มีรายการ',
    'act.system': 'ระบบ',
    'act.say': 'ประกาศ', 'act.play.url': 'เล่นลิงก์เสียง', 'act.youtube': 'เล่น YouTube',
    'act.volume': 'ปรับระดับเสียง', 'act.stop': 'หยุดเล่น', 'act.playlist': 'เล่นเพลย์ลิสต์',
    'act.skip': 'ข้ามเพลง', 'act.schedRun': 'เล่นตามเวลา', 'act.schedMiss': 'เล่นตามเวลาไม่สำเร็จ',
    'act.schedNew': 'เพิ่มการตั้งเวลา', 'act.schedEdit': 'แก้การตั้งเวลา', 'act.schedDel': 'ลบการตั้งเวลา',
    'act.radioFav': 'บันทึกสถานีวิทยุ', 'act.radioUnfav': 'เอาสถานีวิทยุออก',
    'act.fileUp': 'อัปโหลดไฟล์', 'act.fileRename': 'เปลี่ยนชื่อไฟล์', 'act.fileDel': 'ลบไฟล์',
    'act.talk': 'พูดสด',
    'act.login': 'เข้าสู่ระบบ', 'act.loginFail': 'เข้าสู่ระบบไม่สำเร็จ', 'act.logout': 'ออกจากระบบ',
    'act.pw': 'เปลี่ยนรหัสผ่าน', 'act.memNew': 'เพิ่มสมาชิก', 'act.memEdit': 'แก้ไขสมาชิก', 'act.memDel': 'ลบสมาชิก',
    'act.gLink': 'เชื่อมบัญชี Google', 'act.gUnlink': 'เลิกเชื่อมบัญชี Google',
    'act.pkAdd': 'เพิ่มพาสคีย์', 'act.pkRename': 'เปลี่ยนชื่อพาสคีย์', 'act.pkDel': 'ลบพาสคีย์',
    'act.settings': 'เปลี่ยนการตั้งค่าลำโพง',
    'act.d.from': (ip) => `จาก ${ip}`, 'act.d.gFrom': (ip) => `ด้วย Google จาก ${ip}`, 'act.d.pkFrom': (ip) => `ด้วยพาสคีย์ จาก ${ip}`,
    'act.d.setup': 'ตั้งค่าครั้งแรก', 'act.d.allDevices': 'ทุกอุปกรณ์',
  },
});

const PAGE = 50;
const sprite = (n) => () => icon(n);
const own = (n) => () => cIcon(n);
// action -> label key, icon, tile tone, filter group (play | acct | fail)
const KINDS = {
  say: ['act.say', sprite('announce'), 'accent', 'play'],
  play: ['act.play.url', own('music'), 'lotus', 'play'],
  youtube: ['act.youtube', own('music'), 'lotus', 'play'],
  volume: ['act.volume', own('volume'), 'accent', 'play'],
  stop: ['act.stop', own('stop'), 'plain', 'play'],
  'playlist play': ['act.playlist', own('list'), 'lotus', 'play'],
  'queue skip': ['act.skip', own('music'), 'plain', 'play'],
  'schedule run': ['act.schedRun', own('clock'), 'lamp', 'play'],
  'schedule missed': ['act.schedMiss', own('alert'), 'danger', 'fail'],
  'schedule create': ['act.schedNew', own('clock'), 'lamp', 'play'],
  'schedule update': ['act.schedEdit', own('clock'), 'lamp', 'play'],
  'schedule delete': ['act.schedDel', own('clock'), 'lamp', 'play'],
  'radio favourite': ['act.radioFav', own('music'), 'lotus', 'play'],
  'radio unfavourite': ['act.radioUnfav', own('music'), 'lotus', 'play'],
  'file upload': ['act.fileUp', own('music'), 'lotus', 'play'],
  'file rename': ['act.fileRename', own('music'), 'lotus', 'play'],
  'file delete': ['act.fileDel', own('music'), 'lotus', 'play'],
  talk: ['act.talk', own('mic'), 'accent', 'play'],
  'login ok': ['act.login', own('user'), 'plain', 'acct'],
  'login failed': ['act.loginFail', sprite('key'), 'danger', 'fail'],
  logout: ['act.logout', sprite('logout'), 'plain', 'acct'],
  'password change': ['act.pw', sprite('key'), 'plain', 'acct'],
  'member create': ['act.memNew', own('user-plus'), 'accent', 'acct'],
  'member update': ['act.memEdit', sprite('members'), 'accent', 'acct'],
  'member delete': ['act.memDel', sprite('members'), 'accent', 'acct'],
  'google link': ['act.gLink', own('link'), 'plain', 'acct'],
  'google unlink': ['act.gUnlink', own('link'), 'plain', 'acct'],
  'passkey add': ['act.pkAdd', sprite('passkey'), 'accent', 'acct'],
  'passkey rename': ['act.pkRename', sprite('passkey'), 'accent', 'acct'],
  'passkey remove': ['act.pkDel', sprite('passkey'), 'accent', 'acct'],
  'settings change': ['act.settings', sprite('settings'), 'plain', 'acct'],
};
function kindOf(action) {
  const k = KINDS[action] || (/^talk/.test(action) ? KINDS.talk : null);
  if (k) return { label: t(k[0]), icon: k[1](), tone: k[2], group: /fail|missed|error/.test(action) ? 'fail' : k[3] };
  return { label: action, icon: sprite('activity')(), tone: 'plain', group: /fail|missed|error/.test(action) ? 'fail' : 'play' };
}
/** Server detail text is English; the common sign-in ones get the app language. */
function detailOf(e) {
  const d = e.detail || '';
  if (e.action === 'say' && d) return `“${d}”`;
  if (e.action === 'login ok') {
    let m;
    if ((m = d.match(/^with a passkey from (.+)$/))) return t('act.d.pkFrom', m[1]);
    if ((m = d.match(/^with Google from (.+)$/))) return t('act.d.gFrom', m[1]);
    if ((m = d.match(/^from (.+)$/))) return t('act.d.from', m[1]);
    if (d === 'first-run setup') return t('act.d.setup');
  }
  if (e.action === 'logout' && d === 'all sessions') return t('act.d.allDevices');
  return d;
}

export function render(ctx) {
  ctx.css('views/c-common.css');
  ctx.css('views/activity.css');
  const FILTERS = ['all', 'play', 'acct', 'fail'];
  const label = { all: t('act.all'), play: t('act.play'), acct: t('act.acct'), fail: t('act.fail') };
  let entries = [];
  let filter = 'all';
  let done = false;
  let loading = false;

  const seg = segmented({ label: t('act.filter'), value: filter, options: FILTERS.map((f) => ({ value: f, label: label[f] })), onChange: (v) => setFilter(v), cls: 'a-seg' });
  const side = h('div', { class: 'a-side', role: 'radiogroup', 'aria-label': t('act.filter') },
    FILTERS.map((f) => h('button', { type: 'button', role: 'radio', 'aria-checked': String(f === filter), dataset: { f }, onclick: () => setFilter(f) }, label[f])));
  const feed = h('div', { class: 'a-feed', 'aria-live': 'polite' });
  const more = h('button', { type: 'button', class: 'btn tonal big a-more', onclick: () => loadMore(more) }, t('act.older'));
  const endNote = h('p', { class: 'small a-end', hidden: true }, t('act.noOlder'));
  const node = h('div', { class: 'page a-page' },
    phoneBack(ctx.header({ title: t('nav.activity'), back: { href: '#/account', label: t('nav.account') } })),
    seg, h('div', { class: 'a-grid' }, side, h('div', { class: 'a-main' }, feed, more, endNote)));

  function setFilter(f) {
    filter = f;
    seg.setValue(f);
    side.querySelectorAll('button').forEach((b) => b.setAttribute('aria-checked', String(b.dataset.f === f)));
    draw();
  }

  function rowOf(e) {
    const k = kindOf(e.action);
    const who = e.actor === 'system' ? t('act.system') : e.actor;
    const time = h('time', { class: 'a-time', datetime: e.at }, fmtClock(new Date(e.at)));
    const d = detailOf(e);
    return h('li', { class: `a-row${k.group === 'fail' ? ' fail' : ''}` },
      time, tile(k.icon, k.tone),
      h('div', { class: 'a-tx' }, h('p', { class: 'a-title' }, `${who}: ${k.label}`), d ? h('p', { class: 'a-detail' }, d) : null));
  }

  function draw() {
    const shown = entries.filter((e) => filter === 'all' || kindOf(e.action).group === filter);
    const groups = [];
    for (const e of shown) {
      const d = new Date(e.at);
      const last = groups[groups.length - 1];
      if (last && sameDay(last.day, d)) last.items.push(e); else groups.push({ day: d, items: [e] });
    }
    feed.replaceChildren(...(groups.length
      ? groups.map((g) => h('section', { class: 'a-day' }, h('h2', { class: 'c-cap' }, fmtDayHead(g.day)), h('ul', { class: 'c-card a-list' }, g.items.map(rowOf))))
      : loading ? [] : [h('p', { class: 'c-card c-empty' }, entries.length ? t('act.empty') : t('act.none'))]));
    more.hidden = done || !entries.length;
    endNote.hidden = !done || !entries.length;
  }

  async function fetchPage() {
    const before = entries.length ? `&before_id=${entries[entries.length - 1].id}` : '';
    const page = await ctx.api(`/activity?limit=${PAGE}${before}`, { signal: ctx.signal });
    entries = entries.concat(page);
    done = page.length < PAGE;
    draw();
  }
  function loadMore(btn) {
    busy(btn, () => fetchPage().catch((e) => ctx.fail(e))).then(() => {
      const next = feed.querySelectorAll('.a-row');
      if (next.length && !ctx.motionReduced()) btn.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    });
  }

  loading = true;
  fetchPage().catch((e) => ctx.fail(e)).finally(() => { loading = false; draw(); });
  return { node };
}
