// "This device" output: music plays in this browser (one <audio> element) instead of on the speaker.
// Per browser: the choice lives in localStorage spk.output ('device' | 'speaker') and changes nothing anyone else
// hears. Pages keep calling the same playback API (POST /youtube, /playlists/{id}/play, /queue/next, /volume, ...);
// app.js offers each call to intercept() first, which answers it here while this device is the output. The server
// only hands out playable links (POST /local/resolve) and never contacts the speaker for them. Every member may
// use it, viewers too. What a person starts here is logged once (POST /local/played, see logStart), and radio a
// browser can't fetch itself goes through the server's relay (proxy_url, see viaProxy).
// Announcements, live talk and schedules never pass through here: they always play on the speaker.
import { api, ApiError } from './api.js';
import { register, t } from './i18n.js';
import { toast } from './ui.js';

register({
  en: {
    'out.device': 'This device',
    'out.deviceSub': 'Music plays here. Announcements stay on the speaker',
    'out.nowDevice': 'Music now plays on this device. Announcements still go to the speaker',
    'out.tapPlay': 'Tap play to start on this device',
    'out.cantPlay': 'This device can\'t play that item',
    'out.ytNotSaved': 'That YouTube track isn\'t saved on the server yet. Ask someone who can control the speaker to play it once.',
    'out.cantStream': 'This device can\'t play that stream. Some radio links only work on the speaker',
    'out.skipped': (x) => `Couldn't play ${x}; skipped to the next item`,
    'out.queueFailed': 'None of the remaining items could be played on this device',
    'out.untitled': 'Audio',
  },
  th: {
    'out.device': 'อุปกรณ์นี้',
    'out.deviceSub': 'เพลงเล่นที่เครื่องนี้ ส่วนประกาศยังออกที่ลำโพง',
    'out.nowDevice': 'ตอนนี้เพลงเล่นที่อุปกรณ์นี้ ส่วนประกาศยังออกที่ลำโพง',
    'out.tapPlay': 'แตะเล่นเพื่อเริ่มเล่นที่อุปกรณ์นี้',
    'out.cantPlay': 'อุปกรณ์นี้เล่นรายการนี้ไม่ได้',
    'out.ytNotSaved': 'เพลง YouTube นี้ยังไม่ได้เก็บไว้ที่ server ให้คนที่ควบคุมลำโพงได้เปิดเล่นสักครั้งก่อน',
    'out.cantStream': 'อุปกรณ์นี้เล่นสตรีมนี้ไม่ได้ ลิงก์วิทยุบางสถานีเล่นได้เฉพาะที่ลำโพง',
    'out.skipped': (x) => `เล่น ${x} ไม่ได้ ข้ามไปรายการถัดไปแล้ว`,
    'out.queueFailed': 'อุปกรณ์นี้เล่นรายการที่เหลือไม่ได้เลย',
    'out.untitled': 'เสียง',
  },
});

const KEY = 'spk.output';
const VOL_KEY = 'spk.localVol';
const read = (k) => { try { return localStorage.getItem(k); } catch { return null; } };
const write = (k, v) => { try { localStorage.setItem(k, v); } catch { /* not remembered */ } };

let output = read(KEY) === 'device' ? 'device' : 'speaker';
const listeners = new Set();
let emitTimer = 0;
/** Tell app.js something changed; timeupdate fires often, so position-only changes wait a moment. */
function emit(soon = false) {
  if (soon && emitTimer) return;
  clearTimeout(emitTimer);
  emitTimer = setTimeout(() => { emitTimer = 0; listeners.forEach((fn) => { try { fn(); } catch (e) { console.error(e); } }); }, soon ? 1000 : 0);
}

export const isDevice = () => output === 'device';
export function onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); }
/** 'device' | 'speaker'. Leaving this device stops what it plays (the speaker is not touched either way). */
export function setOutput(value) {
  output = value === 'device' ? 'device' : 'speaker';
  write(KEY, output);
  if (output !== 'device') stop();
  emit();
}

/* ---------- play order: a port of player.py's Queue (same summary shape as GET /queue) ---------- */
class LocalQueue {
  constructor(items, { playlistId = null, name = '', start = 0, shuffle = false, repeat = 'off' } = {}) {
    this.items = items.slice();
    this.playlistId = playlistId;
    this.name = name;
    this.repeat = repeat;
    this.order = this.items.map((_, i) => i);
    this.pos = start;
    this.shuffle = false;
    this.failures = 0;
    if (shuffle) this.setShuffle(true);
  }
  get current() { return this.items[this.order[this.pos]]; }
  shuffled(first = null) {
    const rest = this.items.map((_, i) => i).filter((i) => i !== first);
    for (let i = rest.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [rest[i], rest[j]] = [rest[j], rest[i]]; }
    return first === null ? rest : [first, ...rest];
  }
  setShuffle(on) {
    const current = this.order[this.pos];
    if (on) { this.order = this.shuffled(current); this.pos = 0; } else { this.order = this.items.map((_, i) => i); this.pos = current; }
    this.shuffle = on;
  }
  advance(auto) {
    if (auto && this.repeat === 'one') return true;
    if (this.pos + 1 < this.items.length) { this.pos += 1; return true; }
    if (this.repeat === 'off') return false;
    if (this.shuffle && this.items.length > 1) {
      const last = this.order[this.pos];
      const order = this.shuffled();
      if (order[0] === last) [order[0], order[order.length - 1]] = [order[order.length - 1], order[0]];
      this.order = order;
    }
    this.pos = 0;
    return true;
  }
  back() {
    if (this.pos > 0) this.pos -= 1;
    else if (this.repeat !== 'off') this.pos = this.items.length - 1;
  }
  peekNext() {
    if (this.repeat === 'one') return this.current;
    if (this.pos + 1 < this.items.length) return this.items[this.order[this.pos + 1]];
    return this.repeat === 'all' ? this.items[this.order[0]] : null;
  }
  summary() {
    return { playlist_id: this.playlistId, name: this.name, index: this.pos, length: this.items.length, shuffle: this.shuffle,
      repeat: this.repeat, items: this.order.map((i) => this.items[i]), local: true };
  }
}

/* ---------- the audio element ---------- */
let audio = null;
let queue = null;     // LocalQueue, or null for one item started from Music
let item = null;      // what is loaded: the item merged with its resolved link
let phase = 'IDLE';   // IDLE | BUFFERING | PLAYING | PAUSED (the speaker's words, so pages read it like /status)
let gen = 0;          // bumped by every load so a slow resolve can't start a stale item
let starting = false; // a load is waiting for play(): its failure is handled there, not by the error event
let retried = false;  // one fresh link per item when a long pause outlived the signed one (6 h)
const prefetched = new Map(); // item key -> resolve promise for the next queue item (YouTube downloads take a while)
let toLog = null;     // { name } a play someone just started: logged when it first sounds (queue moves aren't)

// Volume can't be set from a web page on iPhone/iPad (the hardware buttons do it): hide the slider there.
const volumeWorks = (() => { try { const a = document.createElement('audio'); a.volume = 0.5; return a.volume === 0.5; } catch { return false; } })();

// iOS only lets a page start sound from a tap. The first tap plays this silent clip on the element, which unlocks
// it for the real link that arrives after the server answers.
const SILENT = (() => {
  const n = 800, b = new Uint8Array(44 + n), v = new DataView(b.buffer);
  const s = (o, x) => [...x].forEach((c, i) => { b[o + i] = c.charCodeAt(0); });
  s(0, 'RIFF'); v.setUint32(4, 36 + n, true); s(8, 'WAVEfmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true);
  v.setUint16(22, 1, true); v.setUint32(24, 8000, true); v.setUint32(28, 8000, true); v.setUint16(32, 1, true);
  v.setUint16(34, 8, true); s(36, 'data'); v.setUint32(40, n, true); b.fill(128, 44);
  return `data:audio/wav;base64,${btoa(String.fromCharCode(...b))}`;
})();
const silent = () => !!audio && audio.src.startsWith('data:');

function el() {
  if (audio) return audio;
  audio = document.createElement('audio');
  audio.id = 'local-audio';
  audio.preload = 'auto';
  audio.hidden = true;
  const vol = parseFloat(read(VOL_KEY));
  if (volumeWorks && vol >= 0 && vol <= 1) audio.volume = vol;
  audio.addEventListener('playing', () => { if (silent()) return; setPhase('PLAYING'); if (queue) queue.failures = 0; logStart(); prefetchNext(); });
  audio.addEventListener('waiting', () => { if (!silent() && item) setPhase('BUFFERING'); });
  audio.addEventListener('pause', () => { if (!silent() && item && !audio.ended && phase !== 'BUFFERING') setPhase('PAUSED'); });
  audio.addEventListener('ended', () => { if (!silent()) finished(); });
  audio.addEventListener('error', () => { if (!silent() && item && audio.src && !starting) failed(); });
  audio.addEventListener('timeupdate', () => { if (!silent()) { positionState(); emit(true); } });
  audio.addEventListener('durationchange', () => { if (!silent()) { positionState(); emit(); } });
  audio.addEventListener('volumechange', () => { write(VOL_KEY, String(audio.volume)); emit(true); });
  document.body.append(audio);
  mediaSessionHandlers();
  return audio;
}
function unlock() {
  unlocked = true;
  const a = el();
  if (a.src && !silent()) return;
  a.src = SILENT;
  a.play().catch(() => {});
}
// Pages may await something (a pending delete, a playlist fetch) between the tap and the play call, which iOS no
// longer counts as the tap. So the first tap or key press anywhere, while this device is the output, unlocks it.
let unlocked = false;
const unlockOnTap = () => { if (isDevice() && !unlocked) unlock(); };
document.addEventListener('click', unlockOnTap, true);
document.addEventListener('keydown', unlockOnTap, true);
function setPhase(p) { phase = p; if ('mediaSession' in navigator) navigator.mediaSession.playbackState = p === 'PLAYING' ? 'playing' : p === 'PAUSED' ? 'paused' : 'none'; emit(); }

const itemKey = (it) => JSON.stringify([it.kind, it.source]);
function resolveBody(it) {
  const body = { kind: it.kind, source: String(it.source) };
  for (const k of ['title', 'lang', 'thumbnail', 'duration', 'content_type']) if (it[k] != null && it[k] !== '') body[k] = it[k];
  return body;
}
function resolve(it) {
  const key = itemKey(it);
  const early = prefetched.get(key);
  prefetched.delete(key);
  return early || api('/local/resolve', { body: resolveBody(it) });
}
function prefetchNext() {
  const next = queue && queue.peekNext();
  if (!next || next.kind !== 'youtube' || prefetched.has(itemKey(next))) return;
  const p = api('/local/resolve', { body: resolveBody(next) });
  p.catch(() => prefetched.delete(itemKey(next)));
  prefetched.set(itemKey(next), p);
}

/** Activity entry for a play someone started (playItem / playList), once, when it first makes sound. */
function logStart() {
  if (!toLog) return;
  const title = toLog.name || (item && item.title) || t('out.untitled');
  toLog = null;
  api('/local/played', { body: { title } }).catch(() => {}); // the music matters more than the log line
}

/**
 * Play the item's own link, or this server's relay of it when the browser can't fetch or decode it itself:
 * an http:// stream on an https:// page (mixed content: iPhone Safari refuses it), or a type it doesn't know.
 */
function viaProxy(got) {
  if (!got.proxy_url) return false;
  if (location.protocol === 'https:' && /^http:/i.test(got.url)) return true;
  return !!got.content_type && el().canPlayType(got.content_type) === '';
}

/** Load `it` and start it. Resolves once it is playing (or waiting for a tap); rejects when it can't be played. */
async function load(it, at = 0) {
  const a = el();
  const g = ++gen;
  item = { ...it };
  retried = at > 0;
  setPhase('BUFFERING');
  let got;
  try { got = await resolve(it); } catch (e) {
    if (g !== gen) return;
    // viewers only get YouTube tracks the server already saved (app.py local_resolve)
    if (e && e.status === 403 && it.kind === 'youtube') throw Object.assign(new ApiError(403, t('out.ytNotSaved')), { local: true });
    throw e;
  }
  if (g !== gen) return;
  item = { ...it, ...got, title: got.title || it.title || null, thumbnail: got.thumbnail || it.thumbnail || null };
  item.proxied = viaProxy(got);
  for (;;) {
    a.src = item.proxied ? got.proxy_url : got.url;
    if (at) a.currentTime = at;
    metadata();
    starting = true;
    const started = a.play();
    started.catch(() => {});
    try {
      // a slow stream may take long to start: stop waiting after 15 s and let the element's events take over
      await Promise.race([started, new Promise((ok) => { setTimeout(ok, 15000); })]);
      return;
    } catch (e) {
      if (g !== gen) return;
      if (e && e.name === 'NotAllowedError') { setPhase('PAUSED'); toast(t('out.tapPlay'), 'info'); return; }
      if (e && e.name === 'AbortError') return; // replaced by another load
      if (got.proxy_url && !item.proxied) { item.proxied = true; continue; } // try once more through the relay
      throw Object.assign(new ApiError(415, t(it.kind === 'radio' ? 'out.cantStream' : 'out.cantPlay')), { local: true });
    } finally {
      if (g === gen) starting = false;
    }
  }
}
/** Play the queue's current item, stepping past items that fail like the server does. */
async function loadQueue() {
  const q = queue;
  for (;;) {
    try { await load(q.current); return; } catch (e) {
      if (q !== queue) return;
      if (e && e.status === 401) throw e;
      q.failures += 1;
      if (q.failures >= q.items.length || !q.advance(false)) { clear(); throw e; }
    }
  }
}
function finished() {
  if (queue && queue.advance(true)) { loadQueue().catch(() => toast(t('out.queueFailed'), 'err')); return; }
  clear();
}
function failed() {
  const pos = audio.currentTime;
  if (item.proxy_url && !item.proxied && pos < 1) { // the direct link failed to start: try the relay once
    item.proxied = true;
    audio.src = item.proxy_url;
    audio.play().catch(() => {});
    return;
  }
  if (!retried && pos > 1) { load(item, pos).catch(() => failed()); return; } // the signed link most likely expired
  if (queue && queue.failures + 1 < queue.items.length && queue.advance(false)) {
    queue.failures += 1;
    toast(t('out.skipped', item.title || ''), 'err');
    loadQueue().catch(() => toast(t('out.queueFailed'), 'err'));
    return;
  }
  toast(item && item.live ? t('out.cantStream') : t('out.cantPlay'), 'err');
  clear();
}
function clear() {
  gen++;
  toLog = null;
  queue = null;
  item = null;
  prefetched.clear();
  if (audio) { audio.pause(); audio.removeAttribute('src'); audio.load(); }
  if ('mediaSession' in navigator) navigator.mediaSession.metadata = null;
  setPhase('IDLE');
}

/* ---------- Media Session: lock screen / control centre / headset buttons ---------- */
function metadata() {
  if (!('mediaSession' in navigator) || !item || typeof MediaMetadata === 'undefined') return;
  const artwork = item.thumbnail ? [{ src: item.thumbnail, sizes: '480x360' }] : [{ src: '/static/icon-512.png', sizes: '512x512', type: 'image/png' }];
  navigator.mediaSession.metadata = new MediaMetadata({ title: item.title || t('out.untitled'), artist: queue ? queue.name : '', album: t('out.device'), artwork });
}
function positionState() {
  if (!('mediaSession' in navigator) || !navigator.mediaSession.setPositionState) return;
  const d = audio.duration;
  try {
    if (Number.isFinite(d) && d > 0) navigator.mediaSession.setPositionState({ duration: d, position: Math.min(audio.currentTime, d), playbackRate: audio.playbackRate || 1 });
  } catch { /* some browsers refuse while metadata loads */ }
}
function mediaSessionHandlers() {
  if (!('mediaSession' in navigator)) return;
  const on = (name, fn) => { try { navigator.mediaSession.setActionHandler(name, fn); } catch { /* not supported here */ } };
  on('play', () => resume());
  on('pause', () => pause());
  on('stop', () => stop());
  on('previoustrack', () => { if (queue) prev().catch(() => {}); else seek(0); });
  on('nexttrack', () => { if (queue) next().catch(() => {}); });
  on('seekto', (d) => seek(d.seekTime));
  on('seekbackward', (d) => seek(audio.currentTime - (d.seekOffset || 10)));
  on('seekforward', (d) => seek(audio.currentTime + (d.seekOffset || 10)));
}

/* ---------- controls (also used directly by the Now page: seek) ---------- */
export function playItem(it) {
  unlock();
  queue = null;
  toLog = {};
  const g = gen + 1;
  return load(it).catch((e) => { if (g === gen) clear(); throw e; });
}
export function playList(items, opts) {
  if (!items.length) return Promise.reject(new ApiError(400, 'The playlist is empty'));
  unlock();
  queue = new LocalQueue(items, opts);
  toLog = { name: opts && opts.name };
  return loadQueue().then(() => queue && queue.summary());
}
export function pause() { if (audio && item) { audio.pause(); setPhase('PAUSED'); } }
export function resume() {
  if (!audio || !item) return;
  audio.play().catch((e) => { if (e && e.name === 'NotAllowedError') toast(t('out.tapPlay'), 'info'); });
}
export function stop() { if (item || queue) clear(); }
export function seek(sec) {
  if (!audio || !item || item.live || !Number.isFinite(audio.duration)) return;
  audio.currentTime = Math.max(0, Math.min(sec, audio.duration - 0.25));
  positionState();
  emit();
}
export function setVolume(level) { if (volumeWorks) el().volume = Math.max(0, Math.min(1, level)); }
function needQueue() { if (!queue) throw new ApiError(404, 'Nothing is queued'); return queue; }
export async function next() {
  const q = needQueue();
  if (!q.advance(false)) throw new ApiError(409, 'Already at the last item');
  unlock();
  await loadQueue();
  return q.summary();
}
export async function prev() {
  const q = needQueue();
  q.back();
  unlock();
  await loadQueue();
  return q.summary();
}
export async function jump(index) {
  const q = needQueue();
  if (!(index >= 0 && index < q.items.length)) throw new ApiError(400, 'index is out of range');
  q.pos = index;
  unlock();
  await loadQueue();
  return q.summary();
}
function patchQueue({ shuffle, repeat } = {}) {
  const q = needQueue();
  if (shuffle != null && shuffle !== q.shuffle) q.setShuffle(shuffle);
  if (repeat) q.repeat = repeat;
  prefetched.clear();
  prefetchNext();
  emit();
  return q.summary();
}

/** What /status would say if this device were the speaker; `server` is the real /status (or null). */
export function status(server, speakerName = '') {
  const d = audio && Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : item && item.duration;
  return {
    local: true,
    speaker: t('out.device'),
    real_speaker: (server && server.speaker) || speakerName,
    volume: volumeWorks ? (audio ? audio.volume : parseFloat(read(VOL_KEY)) || 1) : null,
    muted: false,
    media: {
      title: item ? item.title : null,
      state: phase,
      duration: item && !item.live && d ? d : null,
      position: audio && item ? audio.currentTime : null,
      thumbnail: item ? item.thumbnail : null,
    },
    resume_pending: null,
    tts_lang: server && server.tts_lang,
    queue: queue ? queue.summary() : null,
    talking: null,
  };
}
export const playingHere = () => isDevice() && ['PLAYING', 'BUFFERING', 'PAUSED'].includes(phase);

/* ---------- the API calls this device answers itself ---------- */
const videoId = (q) => { const m = /[?&]v=([A-Za-z0-9_-]{11})/.exec(q || '') || /^([A-Za-z0-9_-]{11})$/.exec((q || '').trim()); return m ? m[1] : null; };
const ROUTES = [
  ['POST', /^\/youtube$/, (b) => playItem({ kind: 'youtube', source: videoId(b.query) || b.query, title: b.title }).then(() => ({ ok: true, title: item && item.title }))],
  ['POST', /^\/radio\/play$/, (b) => playItem({ kind: 'radio', source: b.url || b.uuid, title: b.name, thumbnail: b.favicon, content_type: b.content_type })
    .then(() => ({ ok: true, title: item && item.title }))],
  ['POST', /^\/podcasts\/play$/, (b) => playItem({ kind: 'podcast', source: b.url, title: b.title, thumbnail: b.thumbnail, content_type: b.content_type })
    .then(() => ({ ok: true, title: item && item.title }))],
  ['POST', /^\/files\/(\d+)\/play$/, (b, id) => playItem({ kind: 'file', source: id }).then(() => ({ ok: true, title: item && item.title }))],
  ['POST', /^\/play$/, (b) => playItem({ kind: 'url', source: b.url, content_type: b.content_type }).then(() => ({ ok: true }))],
  ['POST', /^\/playlists\/(\d+)\/play$/, async (b, id) => {
    unlock(); // before the await: iOS counts the tap only until then
    const p = await api(`/playlists/${id}`);
    if (p.items.length && !(b.start_index >= 0 && b.start_index < p.items.length) && b.start_index != null) throw new ApiError(400, 'start_index is out of range');
    return playList(p.items, { playlistId: p.id, name: p.name, start: b.start_index || 0, shuffle: !!b.shuffle, repeat: b.repeat || 'off' });
  }],
  ['POST', /^\/pause$/, () => { pause(); return { ok: true }; }],
  ['POST', /^\/resume$/, () => { resume(); return { ok: true }; }],
  ['POST', /^\/(stop|queue\/clear)$/, () => { stop(); return { ok: true }; }],
  ['POST', /^\/volume$/, (b) => { setVolume(+b.level); return { ok: true }; }],
  ['POST', /^\/queue\/next$/, () => next()],
  ['POST', /^\/queue\/prev$/, () => prev()],
  ['POST', /^\/queue\/jump$/, (b) => jump(+b.index)],
  ['PATCH', /^\/queue$/, (b) => patchQueue(b)],
  ['GET', /^\/queue$/, () => (queue ? queue.summary() : null)],
];
/**
 * intercept(path, opts): a Promise when this device answers the call, undefined when it goes to the server.
 * Runs synchronously up to the first await, so a play started from a tap still counts as the tap (iOS).
 */
export function intercept(path, { method, body } = {}) {
  if (!isDevice()) return undefined;
  const m = method || (body !== undefined ? 'POST' : 'GET');
  const clean = path.split('?')[0];
  for (const [verb, re, fn] of ROUTES) {
    const hit = verb === m && re.exec(clean);
    if (hit) {
      try { return Promise.resolve(fn(body || {}, hit[1])); } catch (e) { return Promise.reject(e); }
    }
  }
  return undefined;
}
