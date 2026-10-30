// Shared bits for the Music, Playlists and Schedule pages (page team B): media rows and thumbs, the
// "Add to playlist" picker, the Add item sheet (all six item kinds), a play/stop tracker that follows /status,
// and delayed deletes with Undo. Views stay thin; anything two of them need lives here.
import { h, icon, field, busy, segmented, tip } from './ui.js';
import { register, t, lang, fmtDur } from './i18n.js';
import { errorText } from './api.js';
import { isPhone } from './sheet.js';
import { bicon } from './teamb-icons.js';

register({
  en: {
    'tb.kind.youtube': 'YouTube', 'tb.kind.url': 'Audio link', 'tb.kind.radio': 'Radio station, live',
    'tb.kind.podcast': 'Podcast episode', 'tb.kind.file': 'My file', 'tb.kind.tts': (l) => `Announcement in ${l}`,
    'tb.lang.th': 'Thai', 'tb.lang.en': 'English', 'tb.lang.ja': 'Japanese',
    'tb.items': (n, m) => (n === 1 ? `1 item${m ? `, ${m} min` : ''}` : `${n} items${m ? `, ${m} min` : ''}`),
    'tb.empty': 'Empty',
    'tb.playOn': (x) => `Play ${x} on the speaker`, 'tb.stopX': (x) => `Stop ${x}`, 'tb.loadingX': (x) => `Loading ${x}`,
    'tb.loading': 'Loading on the speaker…', 'tb.playing': 'Playing on the speaker', 'tb.live': 'Live on the speaker',
    'tb.stopped': 'Speaker stopped', 'tb.nowPlaying': (x) => `Speaker is playing ${x}`,
    'tb.addToPl': 'Add to playlist', 'tb.addX': (x) => `Add ${x} to a playlist`, 'tb.addedTo': (p) => `Added to ${p}`,
    'tb.newPl': 'New playlist', 'tb.plName': 'Playlist name', 'tb.namePh': 'e.g. Afternoon music',
    'tb.ytGone': 'YouTube couldn\'t find that video. It may be private or removed.',
    'tb.fileGone': 'That file isn\'t in My files any more.',
    'tb.nameErr': 'Give it a name first.', 'tb.create': 'Create', 'tb.createAdd': 'Create and add',
    'tb.noPl': 'No playlists yet. Name one below and the item goes straight in.',
    'tb.undo': 'Undo', 'tb.retry': 'Try again', 'tb.search': 'Search',
    'tb.searching': (q) => `Searching “${q}”…`, 'tb.resultsFor': (q) => `Results for “${q}”`,
    'tb.noMatch': (q) => `Nothing matches “${q}”.`, 'tb.typeFirst': 'Type something to search for first.',
    'tb.errRadio': 'Couldn\'t reach the radio directory. The server needs internet access; try again in a moment.',
    'tb.errPod': 'Couldn\'t reach the podcast directory. The server needs internet access; try again in a moment.',
    'tb.errFeed': 'Couldn\'t read that podcast feed. Check the link, or try again later.',
    'tb.errFeedLocal': 'That feed is on a private network. Use a podcast link from the internet.',
    // add item sheet (board AddItem)
    'add.title': (p) => `Add to ${p}`, 'add.type': 'Type',
    'add.yt': 'YouTube', 'add.radio': 'Radio', 'add.pod': 'Podcast', 'add.files': 'My files', 'add.url': 'Audio link', 'add.tts': 'Text',
    'add.ytLabel': 'Search YouTube', 'add.ytPh': 'Search or paste a YouTube link',
    'add.radioLabel': 'Search radio stations', 'add.radioPh': 'Search stations, e.g. jazz',
    'add.favs': 'Favourites', 'add.stations': 'Stations',
    'add.podLabel': 'Podcast name or RSS link', 'add.podPh': 'Podcast name or RSS link',
    'add.podShows': 'Shows', 'add.allShows': 'All shows', 'add.episodesOf': (x) => `Episodes: ${x}`,
    'add.filesLabel': 'Search your files', 'add.filesPh': 'Search your uploaded files', 'add.filesTitle': 'Uploaded files',
    'add.uploadMore': 'Upload files in Music', 'add.noFiles': 'No files uploaded yet.',
    'add.urlLabel': 'Audio file link', 'add.urlErr': 'Use a link that starts with http:// or https://',
    'add.displayName': 'Display name', 'add.displayPh': 'e.g. FM 95 radio',
    'add.urlHelp': 'Works with mp3 files and online radio that plays straight from a link.',
    'add.addLink': 'Add link', 'add.linkAdded': 'Link added',
    'add.text': 'Text', 'add.ttsPh': 'e.g. Welcome, we\'re open.', 'add.ttsErr': 'Type what the speaker should say first.',
    'add.voice': 'Voice language', 'add.addText': 'Add text', 'add.textAdded': 'Text added',
    'add.add': (x) => `Add ${x}`, 'add.added': (x) => `Added ${x}. Tap to remove.`,
    'add.count': (n) => (n === 1 ? '1 item added' : `${n} items added`), 'add.none': 'Nothing added yet',
    'add.done': 'Done',
  },
  th: {
    'tb.kind.youtube': 'YouTube', 'tb.kind.url': 'ลิงก์เสียง', 'tb.kind.radio': 'สถานีวิทยุ ถ่ายทอดสด',
    'tb.kind.podcast': 'ตอนพอดแคสต์', 'tb.kind.file': 'ไฟล์ของฉัน', 'tb.kind.tts': (l) => `ประกาศ ${l}`,
    'tb.lang.th': 'ภาษาไทย', 'tb.lang.en': 'ภาษาอังกฤษ', 'tb.lang.ja': 'ภาษาญี่ปุ่น',
    'tb.items': (n, m) => `${n} รายการ${m ? ` รวม ${m} นาที` : ''}`,
    'tb.empty': 'ยังว่าง',
    'tb.playOn': (x) => `เล่น ${x} ที่ลำโพง`, 'tb.stopX': (x) => `หยุดเล่น ${x}`, 'tb.loadingX': (x) => `กำลังโหลด ${x}`,
    'tb.loading': 'กำลังโหลดลงลำโพง…', 'tb.playing': 'กำลังเล่นที่ลำโพง', 'tb.live': 'กำลังถ่ายทอดสดที่ลำโพง',
    'tb.stopped': 'ลำโพงหยุดเล่นแล้ว', 'tb.nowPlaying': (x) => `ลำโพงกำลังเล่น ${x}`,
    'tb.addToPl': 'เพิ่มเข้าเพลย์ลิสต์', 'tb.addX': (x) => `เพิ่ม ${x} เข้าเพลย์ลิสต์`, 'tb.addedTo': (p) => `เพิ่มเข้า ${p} แล้ว`,
    'tb.newPl': 'เพลย์ลิสต์ใหม่', 'tb.plName': 'ชื่อเพลย์ลิสต์', 'tb.namePh': 'เช่น เพลงช่วงบ่าย',
    'tb.ytGone': 'ไม่พบวิดีโอนี้บน YouTube อาจถูกตั้งเป็นส่วนตัวหรือถูกลบไปแล้ว',
    'tb.fileGone': 'ไฟล์นี้ไม่อยู่ในไฟล์ของฉันแล้ว',
    'tb.nameErr': 'ตั้งชื่อก่อนสร้าง', 'tb.create': 'สร้าง', 'tb.createAdd': 'สร้างแล้วเพิ่ม',
    'tb.noPl': 'ยังไม่มีเพลย์ลิสต์ ตั้งชื่อด้านล่าง แล้วรายการนี้จะถูกเพิ่มเข้าไปเลย',
    'tb.undo': 'เลิกทำ', 'tb.retry': 'ลองอีกครั้ง', 'tb.search': 'ค้นหา',
    'tb.searching': (q) => `กำลังค้นหา “${q}”…`, 'tb.resultsFor': (q) => `ผลการค้นหา “${q}”`,
    'tb.noMatch': (q) => `ไม่มีรายการที่ตรงกับ “${q}”`, 'tb.typeFirst': 'พิมพ์คำที่จะค้นหาก่อน',
    'tb.errRadio': 'ติดต่อรายชื่อสถานีวิทยุไม่ได้ เซิร์ฟเวอร์ต้องต่ออินเทอร์เน็ต ลองใหม่อีกครั้ง',
    'tb.errPod': 'ติดต่อรายชื่อพอดแคสต์ไม่ได้ เซิร์ฟเวอร์ต้องต่ออินเทอร์เน็ต ลองใหม่อีกครั้ง',
    'tb.errFeed': 'อ่านฟีดพอดแคสต์นี้ไม่ได้ ตรวจลิงก์ หรือลองใหม่ภายหลัง',
    'tb.errFeedLocal': 'ฟีดนี้อยู่ในเครือข่ายภายใน ใช้ลิงก์พอดแคสต์จากอินเทอร์เน็ต',
    'add.title': (p) => `เพิ่มเข้า ${p}`, 'add.type': 'ประเภท',
    'add.yt': 'YouTube', 'add.radio': 'วิทยุ', 'add.pod': 'พอดแคสต์', 'add.files': 'ไฟล์ของฉัน', 'add.url': 'ลิงก์เสียง', 'add.tts': 'ข้อความ',
    'add.ytLabel': 'ค้นหา YouTube', 'add.ytPh': 'ค้นหา หรือวางลิงก์ YouTube',
    'add.radioLabel': 'ค้นหาสถานีวิทยุ', 'add.radioPh': 'ค้นหาสถานี เช่น jazz',
    'add.favs': 'รายการโปรด', 'add.stations': 'สถานี',
    'add.podLabel': 'ชื่อพอดแคสต์ หรือลิงก์ RSS', 'add.podPh': 'ชื่อพอดแคสต์ หรือลิงก์ RSS',
    'add.podShows': 'รายการ', 'add.allShows': 'รายการทั้งหมด', 'add.episodesOf': (x) => `ตอนของ ${x}`,
    'add.filesLabel': 'ค้นหาไฟล์', 'add.filesPh': 'ค้นหาไฟล์ที่อัปโหลดไว้', 'add.filesTitle': 'ไฟล์ที่อัปโหลดไว้',
    'add.uploadMore': 'อัปโหลดไฟล์ในหน้าเพลง', 'add.noFiles': 'ยังไม่มีไฟล์ที่อัปโหลด',
    'add.urlLabel': 'ลิงก์ไฟล์เสียง', 'add.urlErr': 'ใส่ลิงก์ที่ขึ้นต้นด้วย http:// หรือ https://',
    'add.displayName': 'ชื่อที่แสดง', 'add.displayPh': 'เช่น สถานีวิทยุ FM 95',
    'add.urlHelp': 'ใช้ได้กับไฟล์ mp3 หรือวิทยุออนไลน์ที่เปิดตรงจากลิงก์ได้',
    'add.addLink': 'เพิ่มลิงก์', 'add.linkAdded': 'เพิ่มลิงก์แล้ว',
    'add.text': 'ข้อความ', 'add.ttsPh': 'เช่น ยินดีต้อนรับ ร้านเปิดให้บริการแล้วค่ะ', 'add.ttsErr': 'พิมพ์ข้อความที่จะให้ลำโพงอ่านก่อน',
    'add.voice': 'ภาษาเสียงอ่าน', 'add.addText': 'เพิ่มข้อความ', 'add.textAdded': 'เพิ่มข้อความแล้ว',
    'add.add': (x) => `เพิ่ม ${x}`, 'add.added': (x) => `เพิ่ม ${x} แล้ว แตะเพื่อเอาออก`,
    'add.count': (n) => `เพิ่มแล้ว ${n} รายการ`, 'add.none': 'ยังไม่ได้เพิ่มรายการ',
    'add.done': 'เสร็จ',
  },
});

export const TTS_LANGS = ['th', 'en', 'ja'];
const LANG_NATIVE = { th: 'ไทย', en: 'English', ja: '日本語' };
export const langNative = (code) => LANG_NATIVE[code] || code;
export const langName = (code) => (TTS_LANGS.includes(code) ? t(`tb.lang.${code}`) : code || '');

/* ---------- formatting ---------- */
export const minutes = (sec) => (sec ? Math.max(1, Math.round(sec / 60)) : 0);
export function playlistMeta(p) {
  const n = p.item_count ?? (p.items || []).length;
  if (!n) return t('tb.empty');
  const total = p.total_duration ?? (p.items || []).reduce((s, i) => s + (i.duration || 0), 0);
  // always "items": the list summary doesn't know the kinds, and list row and detail must read the same
  return t('tb.items', n, minutes(total));
}
export function kindSub(item) {
  return item.kind === 'tts' ? t('tb.kind.tts', langName(item.lang)) : t(`tb.kind.${item.kind}`);
}
export const isUrl = (s) => /^https?:\/\/\S+$/i.test((s || '').trim());
/** 512 KB / 1.4 MB / 2 GB: sizes for people, not engineers. */
export function size(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1048576).toFixed(bytes < 10 * 1048576 ? 1 : 0)} MB`;
  return `${+(bytes / 1024 ** 3).toFixed(1)} GB`;
}

/* ---------- small DOM pieces ---------- */
const KIND_ICON = { youtube: 'yt', url: 'link', tts: 'announce', radio: 'radio', podcast: 'mic', file: 'file', playlist: 'playlists' };
/** Square-ish thumb tinted by kind; an image (YouTube, radio favicon, podcast art) covers it when it loads. */
export function thumb(kind, { img, badge, wide = false } = {}) {
  const el = h('span', { class: `tb-th k-${kind}${wide ? ' wide' : ''}`, 'aria-hidden': 'true' }, bicon(KIND_ICON[kind] || kind, 'sm'));
  if (img) {
    const im = h('img', { src: img, alt: '', loading: 'lazy', decoding: 'async', referrerPolicy: 'no-referrer' });
    im.addEventListener('load', () => el.classList.add('has-img'));
    im.addEventListener('error', () => im.remove());
    el.append(im);
  }
  if (badge) el.append(h('span', { class: 'tb-dur' }, badge));
  return el;
}
/** List row: thumb, title (2 lines) + sub, trailing actions. */
export function mediaRow({ th, title, sub, actions = [], cls = '', props = {} }) {
  const subEl = h('span', { class: 'tb-s' }, sub || '');
  const row = h('div', { class: `tb-row ${cls}`.trim(), ...props }, th,
    h('span', { class: 'tb-tx' }, h('span', { class: 'tb-t' }, title), subEl),
    h('span', { class: 'tb-act' }, actions));
  row.sub = subEl;
  return row;
}
/** Round 44px button. kind: 'primary' (filled play) | 'soft' (grey). */
export function roundBtn(name, label, onclick, kind = 'soft') {
  const b = h('button', { type: 'button', class: `tb-rb ${kind}`, 'aria-label': label, onclick }, bicon(name, 'sm'));
  tip(b, label);
  return b;
}
/** Icon-only button using the team icons (aria-label + tooltip, like ui.iconBtn). */
export function ibtn(name, label, onclick, cls = '') {
  const b = h('button', { type: 'button', class: `iconbtn ${cls}`.trim(), 'aria-label': label, onclick }, bicon(name));
  tip(b, label);
  return b;
}
export function setRound(b, name, label) {
  b.replaceChildren(bicon(name, 'sm'));
  b.setAttribute('aria-label', label);
  tip(b, label);
}
/** Inline error with an optional retry button (role=alert so it is read out). */
export function errBox(msg, retry) {
  return h('div', { class: 'tb-err', role: 'alert' }, icon('info', 'sm'), h('span', {}, msg),
    retry ? h('button', { type: 'button', class: 'linkbtn', onclick: retry }, icon('refresh', 'xs'), t('tb.retry')) : null);
}
export const note = (text, cls = '') => h('p', { class: `tb-note ${cls}`.trim() }, text);
export const sectionLabel = (text, extra) => h('div', { class: 'tb-sec' }, h('h2', {}, text), extra || null);
export const spinnerLine = (text) => h('p', { class: 'tb-note tb-loading', role: 'status' }, h('span', { class: 'tb-spin', 'aria-hidden': 'true' }), text);

/** Search field + button in one form. onSearch(q) runs on submit. Returns { form, input }. */
export function searchForm({ label, placeholder, button = t('tb.search'), value = '', onSearch, inputmode = 'search' }) {
  const input = h('input', { class: 'input', type: 'search', placeholder, value, 'aria-label': label, enterKeyHint: 'search', inputMode: inputmode, autocomplete: 'off', spellcheck: false });
  const btn = h('button', { type: 'submit', class: 'btn primary' }, button);
  const form = h('form', { class: 'tb-search', role: 'search', onsubmit: (e) => { e.preventDefault(); onSearch(input.value.trim(), btn); } }, input, btn);
  return { form, input, btn };
}

/** Error text for music-source failures (502 from the server = the internet directory failed). */
export function sourceError(e, user, what) {
  const map = { radio: 'tb.errRadio', podcast: 'tb.errPod', feed: 'tb.errFeed' };
  if (what === 'feed' && e && e.status === 400 && /public internet|private/i.test(e.detail || '')) return t('tb.errFeedLocal');
  if (e && e.status === 502 && map[what]) return t(map[what]);
  return errorText(e, user);
}

/** Error text for a refused playlist-item add: a 404 about the item's source says what is missing. */
export function itemError(e, user) {
  if (e && e.status === 404 && /youtube/i.test(e.detail || '')) return t('tb.ytGone');
  if (e && e.status === 404 && /file/i.test(e.detail || '')) return t('tb.fileGone');
  return errorText(e, user);
}

/* ---------- play / stop tracking ---------- */
const ACTIVE = ['PLAYING', 'BUFFERING', 'PAUSED'];
/**
 * playTracker(ctx): remembers what this page started on the speaker, so its row can show "Playing on the speaker"
 * and a Stop button, and forgets it once /status says the speaker stopped or moved on to something else.
 * tracker.bind(key, update) registers a row; update(state) gets null | 'loading' | 'playing'.
 */
export function playTracker(ctx) {
  let cur = null; // { key, title, since }
  const rows = new Map();
  const notify = () => {
    for (const [key, fns] of rows) {
      const live = fns.filter((f) => !f.node || f.node.isConnected);
      if (!live.length) { rows.delete(key); continue; }
      rows.set(key, live);
      live.forEach((f) => f(cur && cur.key === key ? cur.phase : null));
    }
  };
  return {
    state: (key) => (cur && cur.key === key ? cur.phase : null),
    bind(key, update, node) {
      update.node = node;
      rows.set(key, [...(rows.get(key) || []), update]);
      update(cur && cur.key === key ? cur.phase : null);
    },
    async play(key, title, run, btn) {
      const prev = cur;
      cur = { key, title, phase: 'loading', since: Date.now() };
      notify();
      try {
        const r = await run();
        if (cur && cur.key === key) {
          cur = { key, title: (r && r.title) || title, phase: 'playing', since: Date.now() };
          notify();
          ctx.refreshStatus();
        }
      } catch (e) {
        if (cur && cur.key === key) { cur = prev && prev.phase === 'playing' ? prev : null; notify(); }
        ctx.fail(e);
      }
      if (btn) btn.focus({ preventScroll: true });
    },
    async stop() {
      try {
        await ctx.api('/stop', { method: 'POST' });
        cur = null;
        notify();
        ctx.toast(t('tb.stopped'), 'ok');
        ctx.refreshStatus();
      } catch (e) { ctx.fail(e); }
    },
    onStatus({ status, error }) {
      if (!cur || cur.phase !== 'playing' || error || !status) return;
      if (Date.now() - cur.since < 8000) return; // the speaker takes a moment to report the new media
      const m = status.media || {};
      const same = !m.title || !cur.title || m.title.toLowerCase().includes(cur.title.toLowerCase().slice(0, 24)) || cur.title.toLowerCase().includes(m.title.toLowerCase().slice(0, 24));
      if (!ACTIVE.includes(m.state) || !same) { cur = null; notify(); }
    },
  };
}
export const mediaActive = (status) => !!(status && status.media && ACTIVE.includes(status.media.state));

/** Wires a play button + its row's sub line to the tracker. */
export function trackPlay(tracker, key, { btn, row, title, idleSub, live = false }) {
  tracker.bind(key, (state) => {
    row.classList.toggle('on', !!state);
    btn.classList.toggle('busy', state === 'loading');
    btn.disabled = state === 'loading';
    if (state === 'playing') setRound(btn, 'stop', t('tb.stopX', title));
    else if (state === 'loading') setRound(btn, 'play', t('tb.loadingX', title));
    else setRound(btn, 'play', t('tb.playOn', title));
    row.sub.textContent = state === 'loading' ? t('tb.loading') : state === 'playing' ? t(live ? 'tb.live' : 'tb.playing') : idleSub;
  }, row);
}

/* ---------- delayed deletes with Undo ---------- */
// Module-level so a delete survives the page re-rendering (e.g. deleting a playlist goes back to the list).
// The DELETE is sent when the Undo window ends, when the tab is hidden/closed (keepalive), or by flush().
const pending = new Map(); // key -> { path, timer, onDone, onError }
function sendDelete(key, keepalive = false) {
  const p = pending.get(key);
  if (!p) return Promise.resolve();
  clearTimeout(p.timer);
  pending.delete(key);
  return fetch(p.path, { method: 'DELETE', keepalive, credentials: 'same-origin', headers: { 'X-Requested-With': 'speaker-web', Accept: 'application/json' } })
    .then((r) => {
      if (!r.ok && r.status !== 404) throw Object.assign(new Error(`HTTP ${r.status}`), { status: r.status });
      if (p.onDone) p.onDone();
    })
    .catch((e) => { if (p.onError) p.onError(e); });
}
/** Hide-now, delete-later. Returns nothing; use isPending(key) to filter lists while it waits. */
export function deleteLater(key, path, { ms = 6000, onDone, onError } = {}) {
  if (pending.has(key)) return;
  pending.set(key, { path, onDone, onError, timer: setTimeout(() => sendDelete(key), ms) });
}
export const isPending = (key) => pending.has(key);
export function undoDelete(key) {
  const p = pending.get(key);
  if (!p) return false;
  clearTimeout(p.timer);
  pending.delete(key);
  return true;
}
/** Send the waiting deletes whose key starts with prefix now (before a reorder, say). */
export function flushDeletes(prefix = '') {
  return Promise.all([...pending.keys()].filter((k) => k.startsWith(prefix)).map((k) => sendDelete(k)));
}
addEventListener('pagehide', () => [...pending.keys()].forEach((k) => sendDelete(k, true)));

/* ---------- "Add to playlist" picker (Music page + buttons) ---------- */
/**
 * pickPlaylist(ctx, item): item is a POST /playlists/{id}/items body ({ kind, source, title, ... }).
 * Sheet on phones, dialog on larger screens: tap a playlist to add, or name a new one.
 */
export function pickPlaylist(ctx, item) {
  ctx.sheet({
    title: t('tb.addToPl'),
    build(body, sheet) {
      const list = h('div', { class: 'list tb-list' });
      const err = h('p', { class: 'form-error', role: 'alert' });
      body.append(h('p', { class: 'tb-note tb-clip' }, item.title || ''), list, err);
      const name = h('input', { class: 'input', placeholder: t('tb.namePh'), maxLength: 100, enterKeyHint: 'done' });
      const create = h('button', { type: 'submit', class: 'btn tonal' }, icon('plus', 'sm'), t('tb.createAdd'));
      let made = null; // playlist created by "Create and add" whose item add hasn't succeeded yet
      const form = h('form', {
        class: 'tb-newpl', novalidate: true,
        onsubmit: (e) => {
          e.preventDefault();
          if (!name.value.trim()) { name.setAttribute('aria-invalid', 'true'); err.textContent = t('tb.nameErr'); name.focus(); return; }
          name.removeAttribute('aria-invalid');
          err.textContent = '';
          busy(create, async () => {
            const wanted = name.value.trim();
            // a playlist left over from a failed try (its clean-up failed too) is reused, never created twice
            try {
              if (!made) made = await ctx.api('/playlists', { body: { name: wanted } });
              else if (made.name !== wanted) made = await ctx.api(`/playlists/${made.id}`, { method: 'PATCH', body: { name: wanted } });
            } catch (e2) { err.textContent = errorText(e2, ctx.user); return; }
            try {
              await ctx.api(`/playlists/${made.id}/items`, { body: item });
              sheet.close();
              ctx.toast(t('tb.addedTo', made.name), 'ok');
              made = null;
            } catch (e2) {
              err.textContent = itemError(e2, ctx.user);
              // don't leave an empty playlist behind
              try { await ctx.api(`/playlists/${made.id}`, { method: 'DELETE' }); made = null; } catch { /* reused on retry */ }
            }
          });
        },
      }, field(t('tb.newPl'), name), create);
      body.append(form);
      list.append(spinnerLine(''));
      ctx.api('/playlists').then((pls) => {
        list.replaceChildren();
        if (!pls.length) { list.replaceWith(note(t('tb.noPl'))); return; }
        for (const p of pls) {
          const row = h('button', {
            type: 'button', class: 'tb-row tb-pick',
            onclick: () => busy(row, async () => {
              try {
                await ctx.api(`/playlists/${p.id}/items`, { body: item });
                sheet.close();
                ctx.toast(t('tb.addedTo', p.name), 'ok');
              } catch (e) { err.textContent = itemError(e, ctx.user); }
            }),
          }, thumb('playlist'), h('span', { class: 'tb-tx' }, h('span', { class: 'tb-t' }, p.name), h('span', { class: 'tb-s' }, playlistMeta(p))), icon('plus', 'sm tb-pick-ic'));
          list.append(row);
        }
      }).catch((e) => list.replaceWith(errBox(errorText(e, ctx.user))));
    },
  });
}

/* ---------- Add item sheet (board AddItem): six kinds ---------- */
const MODES = ['yt', 'radio', 'pod', 'files', 'url', 'tts'];
let lastMode = 'yt';
/**
 * addItemSheet(ctx, playlist, onChange): adds items one by one (each add is saved right away; tapping the check
 * removes it again). onChange() runs when the sheet closes after something changed.
 */
export function addItemSheet(ctx, playlist, onChange) {
  const added = new Map(); // key -> item id on the server
  let changed = false;
  ctx.sheet({
    title: t('add.title', playlist.name),
    onClose: () => { if (changed && onChange) onChange(); },
    build(body, sheet) {
      sheet.dialog.classList.add('tb-addsheet');
      const panel = h('div', { class: 'tb-addpanel' });
      const count = h('span', { class: 'tb-count', role: 'status' }, t('add.none'));
      const chips = h('div', { class: 'tb-chips', role: 'radiogroup', 'aria-label': t('add.type') });
      const chipBtns = MODES.map((m) => h('button', { type: 'button', class: 'tb-chip', role: 'radio', dataset: { mode: m }, onclick: () => show(m, true) }, t(`add.${m}`)));
      chips.append(...chipBtns);
      chips.addEventListener('keydown', (e) => {
        const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
        if (!step) return;
        e.preventDefault();
        const i = (MODES.indexOf(lastMode) + step + MODES.length) % MODES.length;
        show(MODES[i], true);
        chipBtns[i].focus();
      });
      const foot = h('div', { class: 'tb-addfoot' }, count, h('button', { type: 'button', class: 'btn primary', onclick: () => sheet.close() }, t('add.done')));
      body.append(chips, panel, foot);

      const setCount = () => { count.textContent = added.size ? t('add.count', added.size) : t('add.none'); };
      /** Toggle button for one result: add, or remove again. */
      const toggle = (key, title, makeItem) => {
        const b = h('button', { type: 'button', class: 'tb-rb soft' });
        const paint = () => {
          const on = added.has(key);
          b.classList.toggle('on', on);
          setRound(b, on ? 'check' : 'plus', on ? t('add.added', title) : t('add.add', title));
        };
        b.addEventListener('click', () => busy(b, async () => {
          try {
            if (added.has(key)) {
              await ctx.api(`/playlists/${playlist.id}/items/${added.get(key)}`, { method: 'DELETE' });
              added.delete(key);
            } else {
              const it = await ctx.api(`/playlists/${playlist.id}/items`, { body: makeItem() });
              added.set(key, it.id);
            }
            changed = true;
            setCount();
          } catch (e) { ctx.fail(e); }
          paint();
        }));
        paint();
        return b;
      };

      function show(mode, focus) {
        lastMode = mode;
        chipBtns.forEach((b) => { const on = b.dataset.mode === mode; b.setAttribute('aria-checked', String(on)); b.tabIndex = on ? 0 : -1; });
        const sel = chipBtns[MODES.indexOf(mode)];
        if (sel.scrollIntoView) sel.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: ctx.motionReduced() ? 'auto' : 'smooth' });
        panel.replaceChildren(PANELS[mode]());
        if (focus && !matchMedia('(pointer: coarse)').matches) {
          const first = panel.querySelector('input,textarea');
          if (first) first.focus({ preventScroll: true });
        }
      }

      const results = () => h('div', { class: 'tb-results' });
      const PANELS = {
        yt() {
          const out = results();
          const { form } = searchForm({
            label: t('add.ytLabel'), placeholder: t('add.ytPh'),
            onSearch: (q, btn) => {
              if (!q) { out.replaceChildren(note(t('tb.typeFirst'))); return; }
              out.replaceChildren(spinnerLine(t('tb.searching', q)));
              busy(btn, () => ctx.api(`/youtube/search?q=${encodeURIComponent(q)}&limit=10`).then((list) => {
                if (!list.length) { out.replaceChildren(note(t('tb.noMatch', q))); return; }
                out.replaceChildren(note(t('tb.resultsFor', q), 'tb-cap'), h('div', { class: 'list tb-list' }, list.map((v) => mediaRow({
                  th: thumb('youtube', { img: v.thumbnail, badge: fmtDur(v.duration), wide: true }), title: v.title, sub: v.channel || '',
                  actions: [toggle(`yt:${v.video_id}`, v.title, () => ({ kind: 'youtube', source: v.video_id, title: v.title }))],
                }))));
              }).catch((e) => out.replaceChildren(errBox(errorText(e, ctx.user), () => form.requestSubmit()))));
            },
          });
          return h('div', { class: 'tb-pane' }, form, out);
        },
        radio() {
          const out = results();
          const favBox = h('div');
          const stationRow = (s, fav) => mediaRow({
            th: thumb('radio', { img: s.favicon }), title: s.name, sub: [s.tags && s.tags.split(',').slice(0, 2).join(', '), s.country].filter(Boolean).join(', '),
            actions: [toggle(`radio:${s.uuid || s.url}`, s.name, () => (s.uuid
              ? { kind: 'radio', source: s.uuid, title: s.name }
              : { kind: 'radio', source: s.url, title: s.name, thumbnail: s.favicon, content_type: s.content_type }))],
          });
          ctx.api('/radio/favorites').then((favs) => {
            if (favs.length) favBox.replaceChildren(sectionLabel(t('add.favs')), h('div', { class: 'list tb-list' }, favs.map((f) => stationRow(f, true))));
          }).catch(() => {});
          const { form } = searchForm({
            label: t('add.radioLabel'), placeholder: t('add.radioPh'),
            onSearch: (q, btn) => {
              out.replaceChildren(spinnerLine(t('tb.searching', q || '…')));
              busy(btn, () => ctx.api(`/radio/search?q=${encodeURIComponent(q)}&limit=20`).then((list) => {
                if (!list.length) { out.replaceChildren(note(t('tb.noMatch', q))); return; }
                out.replaceChildren(sectionLabel(t('add.stations')), h('div', { class: 'list tb-list' }, list.map((s) => stationRow(s, false))));
              }).catch((e) => out.replaceChildren(errBox(sourceError(e, ctx.user, 'radio'), () => form.requestSubmit()))));
            },
          });
          return h('div', { class: 'tb-pane' }, form, favBox, out);
        },
        pod() {
          const out = results();
          let shows = null, lastQ = '';
          const episodes = (show) => {
            out.replaceChildren(spinnerLine(t('tb.searching', show.title || show.feed_url)));
            ctx.api(`/podcasts/episodes?feed=${encodeURIComponent(show.feed_url)}&limit=30`).then((feed) => {
              const back = shows ? h('button', { type: 'button', class: 'linkbtn', onclick: () => listShows(lastQ) }, icon('back', 'xs'), t('add.allShows')) : null;
              const title = feed.title || show.title || '';
              out.replaceChildren(back || '', sectionLabel(t('add.episodesOf', title)), feed.episodes.length ? h('div', { class: 'list tb-list' }, feed.episodes.map((ep) => mediaRow({
                th: thumb('podcast', { img: ep.thumbnail }), title: ep.title, sub: epMeta(ep),
                actions: [toggle(`pod:${ep.url}`, ep.title, () => ({ kind: 'podcast', source: ep.url, title: ep.title.slice(0, 200), duration: ep.duration, thumbnail: ep.thumbnail, content_type: ep.content_type }))],
              }))) : note(t('tb.noMatch', title)));
            }).catch((e) => out.replaceChildren(errBox(sourceError(e, ctx.user, 'feed'), () => episodes(show))));
          };
          const listShows = (q) => {
            out.replaceChildren(sectionLabel(t('add.podShows')), h('div', { class: 'list tb-list' }, shows.map((s) => {
              const r = mediaRow({ th: thumb('podcast', { img: s.artwork }), title: s.title, sub: s.author || '', actions: [icon('chev-right', 'sm tb-chev')], cls: 'tb-tap', props: { role: 'button', tabindex: '0' } });
              r.addEventListener('click', () => episodes(s));
              r.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); episodes(s); } });
              return r;
            })));
            if (!shows.length) out.replaceChildren(note(t('tb.noMatch', q)));
          };
          const { form } = searchForm({
            label: t('add.podLabel'), placeholder: t('add.podPh'),
            onSearch: (q, btn) => {
              if (!q) { out.replaceChildren(note(t('tb.typeFirst'))); return; }
              if (isUrl(q)) { shows = null; episodes({ feed_url: q, title: '' }); return; }
              lastQ = q;
              out.replaceChildren(spinnerLine(t('tb.searching', q)));
              busy(btn, () => ctx.api(`/podcasts/search?q=${encodeURIComponent(q)}&limit=15`).then((list) => { shows = list; listShows(q); })
                .catch((e) => out.replaceChildren(errBox(sourceError(e, ctx.user, 'podcast'), () => form.requestSubmit()))));
            },
          });
          return h('div', { class: 'tb-pane' }, form, out);
        },
        files() {
          const out = results();
          let files = [];
          const input = h('input', { class: 'input', type: 'search', placeholder: t('add.filesPh'), 'aria-label': t('add.filesLabel'), autocomplete: 'off' });
          const paint = () => {
            const q = input.value.trim().toLowerCase();
            const list = files.filter((f) => !q || f.title.toLowerCase().includes(q) || (f.original_name || '').toLowerCase().includes(q));
            if (!files.length) { out.replaceChildren(note(t('add.noFiles'))); return; }
            if (!list.length) { out.replaceChildren(note(t('tb.noMatch', input.value.trim()))); return; }
            out.replaceChildren(sectionLabel(t('add.filesTitle')), h('div', { class: 'list tb-list' }, list.map((f) => mediaRow({
              th: thumb('file'), title: f.title, sub: fileMeta(f),
              actions: [toggle(`file:${f.id}`, f.title, () => ({ kind: 'file', source: String(f.id) }))],
            }))));
          };
          input.addEventListener('input', paint);
          out.append(spinnerLine(''));
          ctx.api('/files').then((r) => { files = r.items; paint(); }).catch((e) => out.replaceChildren(errBox(errorText(e, ctx.user))));
          const more = h('a', { class: 'linkbtn', href: '#/music/files', onclick: () => sheet.close() }, bicon('upload', 'xs'), t('add.uploadMore'));
          return h('div', { class: 'tb-pane' }, input, out, more);
        },
        url() {
          const url = h('input', { class: 'input', type: 'url', inputMode: 'url', placeholder: 'https://', autocomplete: 'off', spellcheck: false });
          const name = h('input', { class: 'input', placeholder: t('add.displayPh'), maxLength: 200 });
          const err = h('p', { class: 'form-error', role: 'alert' });
          const btn = h('button', { type: 'submit', class: 'btn tonal wide' }, icon('plus', 'sm'), t('add.addLink'));
          const urlF = field(t('add.urlLabel'), url, t('add.urlHelp'));
          return h('form', {
            class: 'tb-pane', novalidate: true,
            onsubmit: (e) => {
              e.preventDefault();
              const u = url.value.trim();
              if (!isUrl(u)) { url.setAttribute('aria-invalid', 'true'); err.textContent = t('add.urlErr'); url.focus(); return; }
              url.removeAttribute('aria-invalid');
              err.textContent = '';
              const title = name.value.trim() || decodeURIComponent(u.split(/[?#]/)[0].split('/').filter(Boolean).pop() || u).slice(0, 200);
              busy(btn, async () => {
                try {
                  const it = await ctx.api(`/playlists/${playlist.id}/items`, { body: { kind: 'url', source: u, title } });
                  added.set(`url:${it.id}`, it.id); changed = true; setCount();
                  url.value = ''; name.value = '';
                  err.textContent = '';
                  ctx.toast(t('add.linkAdded'), 'ok');
                } catch (e2) { err.textContent = itemError(e2, ctx.user); }
              });
            },
          }, urlF, field(t('add.displayName'), name), err, btn);
        },
        tts() {
          const text = h('textarea', { class: 'input tb-ta', rows: 3, maxLength: 1000, placeholder: t('add.ttsPh') });
          let voice = (ctx.status && ctx.status.tts_lang) || (lang() === 'th' ? 'th' : 'en');
          if (!TTS_LANGS.includes(voice)) voice = 'th';
          const seg = segmented({ label: t('add.voice'), value: voice, options: TTS_LANGS.map((l) => ({ value: l, label: langNative(l), lang: l })), onChange: (v) => { voice = v; } });
          const err = h('p', { class: 'form-error', role: 'alert' });
          const btn = h('button', { type: 'submit', class: 'btn tonal wide' }, icon('plus', 'sm'), t('add.addText'));
          return h('form', {
            class: 'tb-pane', novalidate: true,
            onsubmit: (e) => {
              e.preventDefault();
              if (!text.value.trim()) { text.setAttribute('aria-invalid', 'true'); err.textContent = t('add.ttsErr'); text.focus(); return; }
              text.removeAttribute('aria-invalid');
              err.textContent = '';
              busy(btn, async () => {
                try {
                  const it = await ctx.api(`/playlists/${playlist.id}/items`, { body: { kind: 'tts', source: text.value.trim(), lang: voice } });
                  added.set(`tts:${it.id}`, it.id); changed = true; setCount();
                  text.value = '';
                  ctx.toast(t('add.textAdded'), 'ok');
                } catch (e2) { err.textContent = errorText(e2, ctx.user); }
              });
            },
          }, field(t('add.text'), text), h('div', { class: 'field' }, h('span', {}, t('add.voice')), seg), err, btn);
        },
      };
      show(lastMode, !isPhone());
    },
  });
}

export function epMeta(ep) {
  const d = ep.published ? new Date(ep.published).toLocaleDateString(lang() === 'th' ? 'th-TH-u-ca-gregory' : 'en-GB', { day: 'numeric', month: 'short' }) : '';
  const m = ep.duration ? (lang() === 'th' ? `ยาว ${minutes(ep.duration)} นาที` : `${minutes(ep.duration)} min`) : '';
  return [d, m].filter(Boolean).join(lang() === 'th' ? ' ' : ', ');
}
export function fileMeta(f) {
  const d = f.duration ? fmtDur(f.duration) : '';
  return lang() === 'th' ? [d && `ยาว ${d}`, `ขนาด ${size(f.size)}`].filter(Boolean).join(' ') : [d, size(f.size)].filter(Boolean).join(', ');
}
