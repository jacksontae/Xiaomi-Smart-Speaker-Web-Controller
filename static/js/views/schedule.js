// Schedule (boards T_Schedule / D_Schedule; on iPhone the Announce page's "Schedule" mode links here).
// Scheduled announcements and playlists: list grouped Today / Coming up / Off with on/off switches, next run,
// last result (missed / failed shown in red); editor for name, message + voice or playlist + shuffle, time,
// repeat days or a one-off date, own volume; test it now; delete. Phones and iPad edit in a sheet, desktop in a
// side panel. Times are the speaker's (server's) time zone, which GET /schedules reports. Viewers read only.
import { h, icon, field, busy, segmented, tip } from '../ui.js';
import { register, t, locale } from '../i18n.js';
import { errorText } from '../api.js';
import { bicon } from '../teamb-icons.js';
import { errBox, note, spinnerLine, playlistMeta, TTS_LANGS, langNative } from '../teamb-common.js';

register({
  en: {
    'sched.title': 'Schedule', 'sched.mode': 'Announce mode', 'sched.annNow': 'Announce now', 'sched.schedule': 'Schedule',
    'sched.clock': (tm, zone) => `Speaker time now ${tm} (${zone})`, 'sched.new': 'New schedule', 'sched.edit': 'Edit schedule',
    'sched.list': 'Scheduled announcements', 'sched.none': 'Nothing scheduled yet.',
    'sched.noneOp': 'Nothing scheduled yet. Set an announcement for opening time, or a playlist for lunch.',
    'sched.pickHint': 'Pick an item on the left to edit it, or make a new one.',
    'sched.today': 'Today', 'sched.later': 'Coming up', 'sched.off': 'Off',
    'sched.soon': (m) => `in ${m} min`, 'sched.turnOn': (x) => `Turn on ${x}`, 'sched.editX': (x, tm) => `Edit ${x} at ${tm}`,
    'sched.missed': (w) => `Didn’t play ${w}: the server was off or busy at that time`,
    'sched.failed': (w, why) => `Didn’t play ${w}: ${why}`, 'sched.played': (w) => `Played ${w}`,
    'sched.deletedPl': 'its playlist was deleted', 'sched.noAnswer': 'the speaker didn’t respond',
    'sched.name': 'Name', 'sched.namePh': 'e.g. Morning opening', 'sched.nameErr': 'Give it a name before saving',
    'sched.what': 'What to play', 'sched.say': 'Announce a message', 'sched.pl': 'Play a playlist',
    'sched.msg': 'Message to announce', 'sched.msgPh': 'e.g. We are open, welcome', 'sched.textErr': 'Type the message to announce',
    'sched.voice': 'Language', 'sched.pickPl': 'Playlist', 'sched.plErr': 'Choose a playlist', 'sched.noPl': 'There are no playlists yet.',
    'sched.makePl': 'Make one in Playlists', 'sched.shuffle': 'Shuffle songs',
    'sched.time': 'Time', 'sched.playsAt': 'Plays at', 'sched.timeErr': 'Pick a time',
    'sched.repeat': 'Repeat', 'sched.days': 'Days to play', 'sched.date': 'Date', 'sched.dateErr': 'Pick a date',
    'sched.every': 'Every day', 'sched.wk': 'Mon–Fri', 'sched.ms': 'Mon–Sat', 'sched.we': 'Sat–Sun', 'sched.once': 'Once',
    'sched.onceOn': (d) => `Once, ${d}`,
    'sched.rsDaily': 'Plays every day at this time', 'sched.rsWk': 'Plays Monday to Friday', 'sched.rsMs': 'Plays Monday to Saturday',
    'sched.rsWe': 'Plays Saturday and Sunday', 'sched.rsNone': 'Pick at least one day',
    'sched.rsOnce': (d) => `Plays once on ${d}, then turns itself off`, 'sched.rsCustom': (l) => `Plays every ${l}`,
    'sched.volume': 'Volume', 'sched.ownVol': 'Set a volume for this one only',
    'sched.defVol': 'Uses the speaker’s normal volume (change it in Speaker settings)', 'sched.volPct': (p) => `${p}%`,
    'sched.nextOff': 'Off, nothing coming up', 'sched.next': (w) => `Next: ${w}`, 'sched.lastNever': 'Not played yet',
    'sched.last': (w, ok) => `Last time: ${w}${ok ? ', played fine' : ''}`,
    'sched.save': 'Save', 'sched.saved': 'Saved', 'sched.test': 'Test it now', 'sched.testing': 'Testing…',
    'sched.tsSay': 'The speaker is announcing it now', 'sched.tsPl': (p) => `The speaker is playing ${p}`,
    'sched.del': 'Delete this schedule', 'sched.delAsk': (n) => `Delete “${n}”? This can’t be undone.`, 'sched.delYes': 'Delete',
    'sched.keep': 'Keep', 'sched.deleted': (n) => `Deleted ${n}`,
    'sched.todayAt': (tm) => `today ${tm}`, 'sched.tomorrow': 'tomorrow', 'sched.nextShort': (d) => `(next ${d})`, 'sched.tomorrowAt': (tm) => `tomorrow ${tm}`, 'sched.yesterdayAt': (tm) => `yesterday ${tm}`,
    'sched.dateAt': (d, tm) => `${d} ${tm}`,
    'sched.dShort': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
    'sched.dFull': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
    'sched.listSep': ', ',
  },
  th: {
    'sched.title': 'ตั้งเวลา', 'sched.mode': 'โหมดประกาศ', 'sched.annNow': 'ประกาศเลย', 'sched.schedule': 'ตั้งเวลา',
    'sched.clock': (tm, zone) => `เวลาของลำโพงตอนนี้ ${tm} น. (${zone})`, 'sched.new': 'ตั้งเวลาใหม่', 'sched.edit': 'แก้ไขเวลา',
    'sched.list': 'รายการตั้งเวลา', 'sched.none': 'ยังไม่มีรายการตั้งเวลา',
    'sched.noneOp': 'ยังไม่มีรายการตั้งเวลา ลองตั้งประกาศตอนเปิดร้าน หรือเพลย์ลิสต์ช่วงพักเที่ยง',
    'sched.pickHint': 'เลือกรายการทางซ้ายเพื่อแก้ไข หรือตั้งเวลาใหม่',
    'sched.today': 'วันนี้', 'sched.later': 'ถัดไป', 'sched.off': 'ปิดอยู่',
    'sched.soon': (m) => `อีก ${m} นาที`, 'sched.turnOn': (x) => `เปิดใช้ ${x}`, 'sched.editX': (x, tm) => `แก้ไข ${x} เวลา ${tm}`,
    'sched.missed': (w) => `${w} ไม่ได้เล่น: ตอนนั้นเซิร์ฟเวอร์ปิดอยู่หรือไม่ว่าง`,
    'sched.failed': (w, why) => `${w} เล่นไม่ได้: ${why}`, 'sched.played': (w) => `เล่นแล้ว ${w}`,
    'sched.deletedPl': 'เพลย์ลิสต์ของรายการนี้ถูกลบไปแล้ว', 'sched.noAnswer': 'ลำโพงไม่ตอบ',
    'sched.name': 'ชื่อ', 'sched.namePh': 'เช่น เปิดร้านตอนเช้า', 'sched.nameErr': 'ใส่ชื่อรายการก่อนบันทึก',
    'sched.what': 'จะให้เล่นอะไร', 'sched.say': 'ประกาศข้อความ', 'sched.pl': 'เล่นเพลย์ลิสต์',
    'sched.msg': 'ข้อความที่จะประกาศ', 'sched.msgPh': 'เช่น ร้านเปิดแล้วค่ะ ยินดีต้อนรับ', 'sched.textErr': 'พิมพ์ข้อความที่จะให้ประกาศ',
    'sched.voice': 'ภาษา', 'sched.pickPl': 'เพลย์ลิสต์', 'sched.plErr': 'เลือกเพลย์ลิสต์', 'sched.noPl': 'ยังไม่มีเพลย์ลิสต์',
    'sched.makePl': 'สร้างในหน้าเพลย์ลิสต์', 'sched.shuffle': 'สุ่มลำดับเพลง',
    'sched.time': 'เวลา', 'sched.playsAt': 'เล่นตอน', 'sched.timeErr': 'เลือกเวลา',
    'sched.repeat': 'ทำซ้ำ', 'sched.days': 'วันที่ให้เล่น', 'sched.date': 'วันที่', 'sched.dateErr': 'เลือกวันที่',
    'sched.every': 'ทุกวัน', 'sched.wk': 'จ–ศ', 'sched.ms': 'จ–ส', 'sched.we': 'ส–อา', 'sched.once': 'ครั้งเดียว',
    'sched.onceOn': (d) => `ครั้งเดียว ${d}`,
    'sched.rsDaily': 'เล่นซ้ำทุกวันตามเวลานี้', 'sched.rsWk': 'เล่นวันจันทร์ถึงศุกร์', 'sched.rsMs': 'เล่นวันจันทร์ถึงเสาร์',
    'sched.rsWe': 'เล่นวันเสาร์และอาทิตย์', 'sched.rsNone': 'เลือกอย่างน้อยหนึ่งวัน',
    'sched.rsOnce': (d) => `เล่นครั้งเดียว ${d} แล้วปิดรายการนี้ให้อัตโนมัติ`, 'sched.rsCustom': (l) => `เล่นทุกวัน${l}`,
    'sched.volume': 'ระดับเสียง', 'sched.ownVol': 'ตั้งระดับเสียงเฉพาะรายการนี้',
    'sched.defVol': 'ใช้ระดับเสียงปกติของลำโพง (ตั้งได้ในหน้าตั้งค่าลำโพง)', 'sched.volPct': (p) => `${p}%`,
    'sched.nextOff': 'ปิดอยู่ ยังไม่มีรอบถัดไป', 'sched.next': (w) => `ครั้งถัดไป ${w} น.`, 'sched.lastNever': 'ยังไม่เคยเล่น',
    'sched.last': (w, ok) => `ครั้งล่าสุด ${w} น.${ok ? ' เล่นได้ปกติ' : ''}`,
    'sched.save': 'บันทึก', 'sched.saved': 'บันทึกแล้ว', 'sched.test': 'ทดสอบเล่นตอนนี้', 'sched.testing': 'กำลังทดสอบ…',
    'sched.tsSay': 'ลำโพงกำลังประกาศข้อความนี้', 'sched.tsPl': (p) => `ลำโพงกำลังเล่น ${p}`,
    'sched.del': 'ลบรายการนี้', 'sched.delAsk': (n) => `ลบ “${n}” ใช่ไหม ลบแล้วกู้คืนไม่ได้`, 'sched.delYes': 'ลบ',
    'sched.keep': 'ไม่ลบ', 'sched.deleted': (n) => `ลบ ${n} แล้ว`,
    'sched.todayAt': (tm) => `วันนี้ ${tm}`, 'sched.tomorrow': 'พรุ่งนี้', 'sched.nextShort': (d) => `(รอบถัดไป ${d})`, 'sched.tomorrowAt': (tm) => `พรุ่งนี้ ${tm}`, 'sched.yesterdayAt': (tm) => `เมื่อวาน ${tm}`,
    'sched.dateAt': (d, tm) => `${d} ${tm}`,
    'sched.dShort': ['จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส', 'อา'],
    'sched.dFull': ['จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์', 'อาทิตย์'],
    'sched.listSep': ' ',
  },
});

const ALL = [0, 1, 2, 3, 4, 5, 6];
const PRESETS = { every: ALL, wk: [0, 1, 2, 3, 4], we: [5, 6] };
const same = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);
const isDesk = () => matchMedia('(min-width: 1280px)').matches;

/* ---------- time zone helpers: everything shown in the server's zone ---------- */
function zoned(ms, tz) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
    timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(new Date(ms)).map((p) => [p.type, p.value]));
  return { date: `${parts.year}-${parts.month}-${parts.day}`, time: `${parts.hour}:${parts.minute}` };
}
const addDays = (ymd, n) => { const d = new Date(`${ymd}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
function dateLabel(ymd) {
  const d = new Date(`${ymd}T12:00:00Z`);
  return d.toLocaleDateString(locale(), { timeZone: 'UTC', weekday: 'short', day: 'numeric', month: 'short' });
}
function zoneName(tz) {
  try {
    const p = new Intl.DateTimeFormat(locale(), { timeZone: tz, timeZoneName: 'long' }).formatToParts(new Date()).find((x) => x.type === 'timeZoneName');
    return p ? p.value : tz;
  } catch { return tz; }
}

export async function render(ctx) {
  await Promise.all([ctx.css('views/teamb.css'), ctx.css('views/schedule.css')]);
  const op = ctx.can('operator');
  const desk = isDesk();
  let data = null, playlists = [], offset = 0, selected = null; // selected: schedule id | 'new' (desktop)
  const now = () => Date.now() + offset;

  const mode = (cls) => segmented({
    label: t('sched.mode'), cls: `sc-mode ${cls}`, value: 'schedule',
    options: [{ value: 'now', label: t('sched.annNow') }, { value: 'schedule', label: t('sched.schedule') }],
    onChange: (v) => { if (v === 'now') ctx.go('#/announce'); },
  });
  const clock = h('p', { class: 'small sc-clock' });
  const newBtn = op ? h('button', { type: 'button', class: 'btn primary', onclick: () => openEditor(null) }, icon('plus', 'sm'), t('sched.new')) : null;
  const listEl = h('div', { class: 'sc-list', 'aria-label': t('sched.list') });
  const pane = h('div', { class: 'sc-pane glass' });
  const node = h('div', { class: `page sc${desk ? ' sc-desk' : ''}` },
    ctx.header({ title: t('nav.announce'), actions: mode('sc-mode-lg') }),
    mode('sc-mode-ph'),
    h('div', { class: 'sc-bar' }, clock, newBtn),
    desk ? h('div', { class: 'sc-split' }, listEl, pane) : listEl);

  async function load() {
    try {
      const [s, pls] = await Promise.all([ctx.api('/schedules', { signal: ctx.signal }), ctx.api('/playlists', { signal: ctx.signal }).catch(() => [])]);
      data = s;
      playlists = pls;
      offset = Date.parse(s.now) - Date.now();
    } catch (e) {
      if (e.name !== 'AbortError') listEl.replaceChildren(errBox(errorText(e, ctx.user), load));
      return;
    }
    paint();
  }
  const plName = (pid) => (playlists.find((p) => p.id === pid) || {}).name;

  function daysText(s) {
    if (!s.days.length) return t('sched.onceOn', s.date ? dateLabel(s.date) : '');
    if (same(s.days, ALL)) return t('sched.every');
    if (same(s.days, PRESETS.wk)) return t('sched.wk');
    if (same(s.days, [0, 1, 2, 3, 4, 5])) return t('sched.ms');
    if (same(s.days, PRESETS.we)) return t('sched.we');
    return s.days.map((d) => t('sched.dShort')[d]).join(t('sched.listSep'));
  }
  function when(iso) {
    const z = zoned(Date.parse(iso), data.timezone);
    const today = zoned(now(), data.timezone).date;
    if (z.date === today) return t('sched.todayAt', z.time);
    if (z.date === addDays(today, 1)) return t('sched.tomorrowAt', z.time);
    if (z.date === addDays(today, -1)) return t('sched.yesterdayAt', z.time);
    return t('sched.dateAt', dateLabel(z.date), z.time);
  }
  const isToday = (iso) => zoned(Date.parse(iso), data.timezone).date === zoned(now(), data.timezone).date;
  function nextDay(iso) {
    const d = zoned(Date.parse(iso), data.timezone).date;
    return d === addDays(zoned(now(), data.timezone).date, 1) ? t('sched.tomorrow') : dateLabel(d);
  }
  function resultLine(s) {
    if (!s.last_result) return null;
    if (s.last_result === 'ok') return s.last_run ? h('span', { class: 'sc-last' }, t('sched.played', when(s.last_run))) : null;
    const w = s.last_run ? when(s.last_run) : '';
    const why = /no longer exists/i.test(s.last_result) ? t('sched.deletedPl')
      : /not responding|unreachable|timeout|timed out|can't reach|connection/i.test(s.last_result) ? t('sched.noAnswer') : s.last_result;
    return h('span', { class: 'sc-fail' }, s.last_result === 'missed' ? t('sched.missed', w || t('sched.lastNever')) : t('sched.failed', w, why));
  }

  function paint() {
    if (!data) return;
    clock.textContent = t('sched.clock', zoned(now(), data.timezone).time, zoneName(data.timezone));
    const today = zoned(now(), data.timezone).date;
    const groups = { today: [], later: [], off: [] };
    for (const s of data.items) {
      if (!s.enabled || !s.next_run) groups.off.push(s);
      else if (zoned(Date.parse(s.next_run), data.timezone).date === today) groups.today.push(s);
      else groups.later.push(s);
    }
    if (!data.items.length) {
      listEl.replaceChildren(h('div', { class: 'sc-empty glass' }, bicon('clock', 'lg'), note(t(op ? 'sched.noneOp' : 'sched.none'))));
      if (desk && selected !== 'new') { selected = null; paintPane(); }
      return;
    }
    listEl.replaceChildren(...['today', 'later', 'off'].filter((k) => groups[k].length).map((k) => h('section', { class: 'sc-group' },
      h('h2', { class: 'sc-gh' }, t(`sched.${k}`)), h('div', { class: 'list tb-list' }, groups[k].map(row)))));
    if (desk) {
      if (selected !== 'new' && !data.items.some((s) => s.id === selected)) selected = null;
      if (!pane.dataset.for || pane.dataset.for !== String(selected)) paintPane();
    }
  }
  function row(s) {
    const isSay = s.action === 'say';
    const mins = s.enabled && s.next_run ? Math.round((Date.parse(s.next_run) - now()) / 60000) : null;
    const sub = h('span', { class: 'tb-s sc-sub' }, bicon(isSay ? 'announce' : 'playlists', 'xs'),
      h('span', {}, isSay ? daysText(s) : `${plName(s.playlist_id) || '—'}, ${daysText(s)}`),
      s.enabled && s.next_run && s.days.length && (mins == null || mins > 60) && !isToday(s.next_run) ? h('span', { class: 'sc-nextday' }, t('sched.nextShort', nextDay(s.next_run))) : null,
      mins != null && mins >= 0 && mins <= 60 ? h('b', { class: 'sc-soon' }, t('sched.soon', Math.max(1, mins))) : null);
    const r = h('div', { class: `tb-row sc-row${s.enabled ? '' : ' off'}${desk && selected === s.id ? ' sel' : ''}` },
      op ? h('button', { type: 'button', class: 'tb-stretch', 'aria-label': t('sched.editX', s.name, s.time), onclick: () => openEditor(s) }) : null,
      h('span', { class: 'sc-time' }, s.time),
      h('span', { class: 'tb-tx' }, h('span', { class: 'tb-t' }, s.name), sub, resultLine(s)));
    if (op) {
      const sw = h('input', { type: 'checkbox', class: 'switch', checked: s.enabled, role: 'switch', 'aria-label': t('sched.turnOn', s.name) });
      sw.addEventListener('change', async () => {
        sw.disabled = true;
        try {
          const upd = await ctx.api(`/schedules/${s.id}`, { method: 'PATCH', body: { enabled: sw.checked } });
          Object.assign(s, upd);
          paint();
        } catch (e) { sw.checked = !sw.checked; ctx.fail(e); }
        sw.disabled = false;
      });
      r.append(h('span', { class: 'tb-act' }, sw));
    }
    return r;
  }

  /* ----- editor placement: desktop panel or sheet ----- */
  function openEditor(s) {
    if (desk) { selected = s ? s.id : 'new'; paint(); paintPane(true); return; }
    ctx.sheet({
      title: t(s ? 'sched.edit' : 'sched.new'),
      build(body, sheet) {
        sheet.dialog.classList.add('sc-sheet');
        body.append(editor(s, { done: () => sheet.close() }));
      },
    });
  }
  function paintPane(focus) {
    pane.dataset.for = String(selected);
    if (!selected) { pane.replaceChildren(h('p', { class: 'tb-note sc-hint' }, t('sched.pickHint'))); return; }
    const s = selected === 'new' ? null : data.items.find((x) => x.id === selected);
    pane.replaceChildren(h('div', { class: 'sc-ph' }, h('h2', {}, t(s ? 'sched.edit' : 'sched.new'))), editor(s, { done: () => {} }));
    if (focus) { const f = pane.querySelector('input'); if (f) f.focus({ preventScroll: true }); }
    listEl.querySelectorAll('.sc-row').forEach((r) => r.classList.remove('sel'));
  }

  /* ----- the editor form ----- */
  function editor(s, { done }) {
    const today = zoned(now(), data.timezone).date;
    const f = s ? { ...s, days: [...s.days] } : {
      name: '', enabled: true, action: 'say', text: '', lang: (ctx.status && ctx.status.tts_lang) || 'th', playlist_id: playlists[0] ? playlists[0].id : null,
      shuffle: false, volume: null, time: '', days: [...ALL], date: today,
    };
    if (!TTS_LANGS.includes(f.lang || '')) f.lang = f.lang || 'th';
    let once = !f.days.length;
    if (once && !f.date) f.date = today;
    let dirty = false;
    const touch = () => { dirty = true; };
    const err = h('p', { class: 'form-error', role: 'alert' });

    const name = h('input', { class: 'input', value: f.name, placeholder: t('sched.namePh'), maxLength: 100, oninput: () => { f.name = name.value; touch(); } });
    const whatSeg = segmented({ label: t('sched.what'), value: f.action, options: [{ value: 'say', label: t('sched.say') }, { value: 'playlist', label: t('sched.pl') }], onChange: (v) => { f.action = v; touch(); paintWhat(); } });
    const whatBox = h('div', { class: 'sc-what' });
    function paintWhat() {
      if (f.action === 'say') {
        const ta = h('textarea', { class: 'input tb-ta', rows: 3, maxLength: 1000, placeholder: t('sched.msgPh'), value: f.text || '', oninput: () => { f.text = ta.value; touch(); } });
        ta.value = f.text || '';
        const langs = TTS_LANGS.includes(f.lang) ? TTS_LANGS : [...TTS_LANGS, f.lang];
        const voice = segmented({ label: t('sched.voice'), value: f.lang, options: langs.map((l) => ({ value: l, label: langNative(l), lang: l })), onChange: (v) => { f.lang = v; touch(); } });
        whatBox.replaceChildren(field(t('sched.msg'), ta), h('div', { class: 'field' }, h('span', {}, t('sched.voice')), voice));
      } else if (!playlists.length) {
        whatBox.replaceChildren(h('div', { class: 'tb-note' }, t('sched.noPl'), ' ', h('a', { href: '#/playlists' }, t('sched.makePl'))));
      } else {
        const sel = h('select', { class: 'input', onchange: () => { f.playlist_id = Number(sel.value); touch(); } },
          h('option', { value: '' }, '—'), playlists.map((p) => h('option', { value: String(p.id), selected: p.id === f.playlist_id }, `${p.name} (${playlistMeta(p)})`)));
        if (f.playlist_id && !playlists.some((p) => p.id === f.playlist_id)) f.playlist_id = null;
        sel.value = f.playlist_id ? String(f.playlist_id) : '';
        const shuf = h('input', { type: 'checkbox', class: 'switch', checked: !!f.shuffle, onchange: () => { f.shuffle = shuf.checked; touch(); } });
        whatBox.replaceChildren(field(t('sched.pickPl'), sel), h('label', { class: 'sc-swrow' }, h('span', {}, t('sched.shuffle')), shuf));
      }
    }
    paintWhat();

    const time = h('input', { class: 'input sc-timein', type: 'time', value: f.time, step: 60, oninput: () => { f.time = time.value; touch(); } });
    const date = h('input', { class: 'input sc-datein', type: 'date', value: f.date || today, min: today, oninput: () => { f.date = date.value; touch(); paintRepeat(); } });
    const presets = h('div', { class: 'tb-chips sc-presets', role: 'group', 'aria-label': t('sched.repeat') });
    const dayBox = h('div', { class: 'sc-days', role: 'group', 'aria-label': t('sched.days') });
    const dateRow = field(t('sched.date'), date);
    const summary = h('p', { class: 'small sc-summary', 'aria-live': 'polite' });
    const presetBtn = (key, label) => h('button', { type: 'button', class: 'tb-chip', dataset: { k: key }, onclick: () => {
      if (key === 'once') once = true; else { once = false; f.days = [...PRESETS[key]]; }
      touch(); paintRepeat();
    } }, label);
    presets.append(presetBtn('every', t('sched.every')), presetBtn('wk', t('sched.wk')), presetBtn('we', t('sched.we')), presetBtn('once', t('sched.once')));
    const dayBtns = ALL.map((d) => {
      const b = h('button', { type: 'button', class: 'sc-day', 'aria-label': t('sched.dFull')[d], onclick: () => {
        f.days = f.days.includes(d) ? f.days.filter((x) => x !== d) : [...f.days, d].sort();
        touch(); paintRepeat();
      } }, t('sched.dShort')[d]);
      tip(b, t('sched.dFull')[d]);
      return b;
    });
    dayBox.append(...dayBtns);
    function paintRepeat() {
      const key = once ? 'once' : Object.keys(PRESETS).find((k) => same(f.days, PRESETS[k])) || null;
      presets.querySelectorAll('.tb-chip').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.k === key)));
      dayBox.hidden = once;
      dateRow.hidden = !once;
      dayBtns.forEach((b, d) => b.setAttribute('aria-pressed', String(f.days.includes(d))));
      summary.classList.toggle('err', !once && !f.days.length);
      summary.textContent = once ? t('sched.rsOnce', f.date ? dateLabel(f.date) : '…')
        : !f.days.length ? t('sched.rsNone')
          : same(f.days, ALL) ? t('sched.rsDaily') : same(f.days, PRESETS.wk) ? t('sched.rsWk') : same(f.days, [0, 1, 2, 3, 4, 5]) ? t('sched.rsMs')
            : same(f.days, PRESETS.we) ? t('sched.rsWe') : t('sched.rsCustom', f.days.map((d) => t('sched.dFull')[d]).join(t('sched.listSep')));
    }
    paintRepeat();

    const volOn = h('input', { type: 'checkbox', class: 'switch', checked: f.volume != null });
    const volOut = h('output', { class: 'sc-volv' });
    const vol = h('input', { type: 'range', class: 'sc-range', min: 0, max: 100, step: 5, value: Math.round((f.volume ?? 0.5) * 100), 'aria-label': t('sched.volume') });
    const volRow = h('div', { class: 'sc-volrow' }, vol, volOut);
    const volHint = h('p', { class: 'small' }, t('sched.defVol'));
    const paintVol = () => {
      volRow.hidden = !volOn.checked;
      volHint.hidden = volOn.checked;
      volOut.textContent = t('sched.volPct', vol.value);
      f.volume = volOn.checked ? Number(vol.value) / 100 : null;
    };
    volOn.addEventListener('change', () => { touch(); paintVol(); });
    vol.addEventListener('input', () => { touch(); paintVol(); });
    paintVol();

    const info = s ? h('div', { class: 'small sc-info' },
      h('p', {}, s.enabled && s.next_run ? t('sched.next', when(s.next_run)) : t('sched.nextOff')),
      h('p', {}, s.last_run ? t('sched.last', when(s.last_run), s.last_result === 'ok') : t('sched.lastNever')),
      s.last_result && s.last_result !== 'ok' ? resultLine(s) : null) : null;

    function body() {
      const b = { name: f.name.trim(), enabled: s ? f.enabled : true, action: f.action, time: f.time, volume: f.volume };
      if (f.action === 'say') Object.assign(b, { text: (f.text || '').trim(), lang: f.lang, playlist_id: null, shuffle: false });
      else Object.assign(b, { playlist_id: f.playlist_id, shuffle: !!f.shuffle, text: null });
      if (once) Object.assign(b, { days: [], date: f.date }); else Object.assign(b, { days: f.days, date: null });
      return b;
    }
    function check() {
      [name, time, date].forEach((x) => x.removeAttribute('aria-invalid'));
      const bad = (el, key) => { if (el) { el.setAttribute('aria-invalid', 'true'); el.focus(); } err.textContent = t(key); return false; };
      if (!f.name.trim()) return bad(name, 'sched.nameErr');
      if (f.action === 'say' && !(f.text || '').trim()) return bad(whatBox.querySelector('textarea'), 'sched.textErr');
      if (f.action === 'playlist' && !f.playlist_id) return bad(whatBox.querySelector('select'), 'sched.plErr');
      if (!f.time) return bad(time, 'sched.timeErr');
      if (once && !f.date) return bad(date, 'sched.dateErr');
      if (!once && !f.days.length) return bad(dayBtns[0], 'sched.rsNone');
      err.textContent = '';
      return true;
    }
    const saveBtn = op ? h('button', { type: 'submit', class: `btn primary${desk ? '' : ' big wide'}` }, t('sched.save')) : null;
    async function save(e) {
      e.preventDefault();
      if (!check()) return;
      await busy(saveBtn, async () => {
        try {
          const saved = s ? await ctx.api(`/schedules/${s.id}`, { method: 'PATCH', body: body() }) : await ctx.api('/schedules', { body: body() });
          dirty = false;
          if (desk) selected = saved.id;
          pane.dataset.for = '';
          done();
          await load();
          if (desk) { const b = pane.querySelector('button[type=submit]'); if (b) { b.textContent = t('sched.saved'); setTimeout(() => { if (b.isConnected) b.textContent = t('sched.save'); }, 1600); } }
        } catch (x) { err.textContent = errorText(x, ctx.user); }
      });
    }

    const testBtn = op ? h('button', { type: 'button', class: 'btn tonal wide sc-test' }, bicon('play', 'sm'), t('sched.test')) : null;
    if (testBtn) testBtn.addEventListener('click', () => {
      const b = body();
      if (b.action === 'say' && !b.text) { check(); return; }
      if (b.action === 'playlist' && !b.playlist_id) { check(); return; }
      busy(testBtn, async () => {
        try {
          if (s && !dirty) await ctx.api(`/schedules/${s.id}/run`, { method: 'POST' });
          else if (b.action === 'say') await ctx.api('/say', { body: { text: b.text, lang: b.lang, volume: b.volume } });
          else {
            const p = playlists.find((x) => x.id === b.playlist_id);
            await ctx.api(`/playlists/${b.playlist_id}/play`, { body: { shuffle: b.shuffle, start_index: b.shuffle && p && p.item_count ? Math.floor(Math.random() * p.item_count) : 0 } });
          }
          ctx.toast(b.action === 'say' ? t('sched.tsSay') : t('sched.tsPl', plName(b.playlist_id) || ''), 'ok');
          ctx.refreshStatus();
          if (s && !dirty) load();
        } catch (x) { ctx.fail(x); }
      });
    });

    const delBox = h('div', { class: 'sc-del' });
    const paintDel = (asking) => {
      if (!s || !op) return;
      if (!asking) { delBox.replaceChildren(h('button', { type: 'button', class: 'linkbtn sc-delbtn', onclick: () => { paintDel(true); delBox.querySelector('.btn')?.focus(); } }, bicon('trash', 'xs'), t('sched.del'))); return; }
      const yes = h('button', { type: 'button', class: 'btn danger', onclick: () => busy(yes, async () => {
        try {
          await ctx.api(`/schedules/${s.id}`, { method: 'DELETE' });
          if (desk) selected = null;
          pane.dataset.for = '';
          done();
          ctx.toast(t('sched.deleted', s.name), 'ok');
          load();
        } catch (x) { ctx.fail(x); }
      }) }, t('sched.delYes'));
      delBox.replaceChildren(h('p', { class: 'small' }, t('sched.delAsk', s.name)), h('div', { class: 'sc-delask' }, yes, h('button', { type: 'button', class: 'btn', onclick: () => paintDel(false) }, t('sched.keep'))));
    };
    paintDel(false);

    const form = h('form', { class: 'sc-form', novalidate: true, onsubmit: save },
      field(t('sched.name'), name),
      h('div', { class: 'field' }, h('span', {}, t('sched.what')), whatSeg),
      whatBox,
      h('div', { class: 'field' }, h('span', {}, t('sched.time')), h('label', { class: 'sc-timerow' }, h('span', {}, t('sched.playsAt')), time)),
      h('div', { class: 'field' }, h('span', {}, t('sched.repeat')), presets, dayBox, dateRow, summary),
      h('div', { class: 'field' }, h('span', {}, t('sched.volume')), h('div', { class: 'sc-volbox' }, h('label', { class: 'sc-swrow' }, h('span', {}, t('sched.ownVol')), volOn), volRow, volHint)),
      info, err, saveBtn, testBtn, delBox);
    return form;
  }

  const tick = setInterval(() => { if (data) paint(); }, 30000); // clock line and "in 5 min" 
  const refresh = setInterval(() => { if (document.visibilityState === 'visible' && !node.querySelector('.sc-form:focus-within')) load(); }, 60000);
  ctx.onCleanup(() => { clearInterval(tick); clearInterval(refresh); });

  listEl.append(spinnerLine(''));
  if (desk) paintPane();
  load();
  return { node };
}
