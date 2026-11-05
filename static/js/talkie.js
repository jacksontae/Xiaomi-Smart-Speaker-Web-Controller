// Talkie client (WebSocket /talkie, see app.py): the walkie-talkie between the members of this server.
// The socket stays open on every page while signed in (app.js calls start/stop): it says who has the app open and
// brings other members' talks, which play here live through one <audio> wherever the member is in the app. The
// page (views/talkie.js) reads the state and talks through holdToTalk().
//
//   start({ user, go })   connect (again after a drop, with backoff); go(hash) navigates (the live pill's tap)
//   stop()                sign-out: close, forget, silence
//   onChange(fn)          fn(state) on every change; returns unsubscribe. state = { connected, me, online, live,
//                         clips, blocked, hearing, playing, playedRev }: live = { id, user_id, name, url } of someone else's
//                         talk, blocked = the browser refused to start the live audio (iOS before a first tap)
//   holdToTalk({ onState, onLevel })  -> { start(), stop(), destroy() }, one talk at a time (see there)
//   playClip(clip) / stopClip()       play a kept clip (one at a time, through its own <audio>)
//   listen()              start the live audio from a tap (after `blocked`)
//   played(id) / markPlayed(id)        "Not played yet" per device (localStorage)
//   hearing() / setHearing(on)         the "Hear Talkie on this device" switch (App settings), default on
//   setPageOpen(on)       the Talkie page is showing: it has its own banner, so the live pill hides
import { h, icon } from './ui.js';
import { register, t } from './i18n.js';
import { pickMime, micAllowedHere, micPermission, askMic, openMeter } from './talk-client.js';

register({
  en: {
    'tkg.talking': (x) => `${x} is talking…`, 'tkg.tap': 'Tap to listen', 'tkg.tapAria': (x) => `${x} is talking. Tap to listen`,
  },
  th: {
    'tkg.talking': (x) => `${x} กำลังพูด…`, 'tkg.tap': 'แตะเพื่อฟัง', 'tkg.tapAria': (x) => `${x} กำลังพูด แตะเพื่อฟัง`,
  },
});

const CHUNK_MS = 250;
const PING_MS = 25000;          // keeps proxies from closing an idle socket; the server re-checks the session on it
const RETRY_MS = [1000, 2000, 5000, 10000, 30000];
const HIDDEN_CLOSE_MS = 5 * 60 * 1000; // a tab hidden this long lets go of the socket until it is shown again
const STOP_WAIT_MS = 6000;      // after release, give up waiting for the server's "ended"
const HEAR_KEY = 'spk.talkieHear';
const PLAYED_KEY = 'spk.talkiePlayed';
const PLAYED_MAX = 200;

const read = (k) => { try { return localStorage.getItem(k); } catch { return null; } };
const write = (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } };

const state = { connected: false, me: null, online: [], live: null, clips: [], blocked: false, hearing: read(HEAR_KEY) !== 'off', playing: null, playedRev: 0 };
const subs = new Set();
let ws = null, user = null, go = () => {};
let retry = 0, retryTimer = 0, pingTimer = 0, hiddenTimer = 0;
let talker = null;       // the holdToTalk() whose talk is going on (gets ready/error/ended)
let pageOpen = false;

export function onChange(fn) { subs.add(fn); return () => subs.delete(fn); }
/** The current state (the same object onChange passes; read it, don't change it). */
export const snapshot = () => state;
function changed() {
  paintPill();
  subs.forEach((f) => { try { f(state); } catch (e) { console.error(e); } });
}

/* ---------- socket ---------- */
export function start(opts) {
  go = opts.go || go;
  if (user && opts.user && user.id === opts.user.id && ws) return; // a re-render (language): keep the connection
  stop();
  user = opts.user;
  connect();
}

export function stop() {
  user = null;
  clearTimeout(retryTimer); clearTimeout(hiddenTimer);
  disconnect();
  stopLive();
  stopClip();
  Object.assign(state, { me: null, online: [], live: null, clips: [], blocked: false });
  changed();
}

function connect() {
  if (!user || ws || typeof WebSocket === 'undefined') return;
  clearTimeout(retryTimer);
  const sock = ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/talkie`);
  sock.binaryType = 'arraybuffer';
  sock.onmessage = (ev) => { if (ws === sock && typeof ev.data === 'string') receive(ev.data); };
  sock.onclose = (ev) => {
    if (ws !== sock) return;
    ws = null;
    clearInterval(pingTimer);
    state.connected = false;
    if (talker) talker.dropped();
    changed();
    // signed out or not allowed: the app's own 401 handling takes over; otherwise come back
    if (user && ![4401, 4403].includes(ev.code) && document.visibilityState === 'visible') {
      retryTimer = setTimeout(connect, RETRY_MS[Math.min(retry, RETRY_MS.length - 1)]);
      retry += 1;
    }
  };
  sock.onerror = () => { /* onclose follows */ };
  clearInterval(pingTimer);
  pingTimer = setInterval(() => send({ type: 'ping' }), PING_MS);
}

function disconnect() {
  clearInterval(pingTimer);
  if (ws) {
    const sock = ws;
    ws = null;
    sock.onmessage = sock.onclose = sock.onerror = null;
    try { sock.close(1000); } catch { /* closed */ }
  }
  if (talker) talker.dropped();
  state.connected = false;
}

function send(msg) {
  if (!ws || ws.readyState !== 1) return false;
  try { ws.send(typeof msg === 'string' || msg instanceof Blob ? msg : JSON.stringify(msg)); return true; } catch { return false; }
}

function receive(text) {
  let msg;
  try { msg = JSON.parse(text); } catch { return; }
  if (msg.type === 'hello') {
    retry = 0;
    Object.assign(state, { connected: true, me: msg.me, online: msg.online || [], clips: msg.clips || [] });
    setLive(msg.live && msg.live.user_id !== msg.me ? msg.live : null);
  } else if (msg.type === 'online') {
    state.online = msg.online || [];
  } else if (msg.type === 'live') {
    setLive(msg);
  } else if (msg.type === 'ended') {
    if (msg.clip) {
      state.clips = [msg.clip, ...state.clips.filter((c) => c.id !== msg.clip.id)];
      if (msg.user_id === state.me) markPlayed(msg.id, false);
    }
    if (state.live && state.live.id === msg.id) {
      state.live = null;
      // the stream ends by itself once played out; only a blocked one is dropped (nothing will play it now)
      if (state.blocked) { stopLive(); state.blocked = false; }
    }
    if (talker && talker.id === msg.id) talker.ended(msg);
  } else if (msg.type === 'ready' || msg.type === 'error') {
    if (talker) talker.reply(msg);
    return;
  } else {
    return; // pong
  }
  changed();
}

document.addEventListener('visibilitychange', () => {
  clearTimeout(hiddenTimer);
  if (document.visibilityState === 'visible') {
    if (user && !ws) { retry = 0; connect(); }
  } else if (!talker) {
    hiddenTimer = setTimeout(() => { if (user && !talker && document.visibilityState !== 'visible') { disconnect(); changed(); } }, HIDDEN_CLOSE_MS);
  }
});

/* ---------- live audio (someone else talking) ---------- */
let liveAudio = null;
const liveEl = () => {
  if (!liveAudio) {
    liveAudio = new Audio();
    liveAudio.preload = 'none';
    // heard live here: its clip counts as played ("Not played yet" is for those who missed it)
    liveAudio.addEventListener('playing', () => { if (liveAudio.dataset.id) markPlayed(liveAudio.dataset.id); });
    liveAudio.addEventListener('ended', () => { stopLive(); changed(); });
    liveAudio.addEventListener('error', () => { if (liveAudio.dataset.id) { stopLive(); changed(); } });
  }
  return liveAudio;
};

function setLive(live) {
  state.live = live;
  if (!live) return;
  stopClip();
  if (state.hearing) playLive(live);
}

function playLive(live) {
  const a = liveEl();
  a.dataset.id = live.id;
  a.src = live.url;
  state.blocked = false;
  a.play().catch((e) => {
    if (a.dataset.id !== live.id) return;
    // autoplay refused (iOS until the first tap, or a browser policy): offer a tap instead of staying silent
    if (e && e.name === 'NotAllowedError') { state.blocked = true; changed(); }
  });
}

function stopLive() {
  if (!liveAudio) return;
  liveAudio.dataset.id = '';
  liveAudio.removeAttribute('src');
  try { liveAudio.load(); } catch { /* nothing loaded */ }
}

/** Start the live audio from a tap (the browser blocked it before); after the talk ended, its clip instead. */
export function listen() {
  state.blocked = false;
  if (state.live) playLive(state.live);
  changed();
}

/* ---------- kept clips ---------- */
let clipAudio = null;
let clipCb = null;
/** Play `clip`; onProgress(fraction | null) while it plays (null = stopped). Stops any other clip. */
export function playClip(clip, onProgress = () => {}) {
  stopClip();
  if (!clipAudio) {
    clipAudio = new Audio();
    clipAudio.addEventListener('timeupdate', () => { if (clipCb && clipAudio.duration) clipCb(clipAudio.currentTime / clipAudio.duration); });
    clipAudio.addEventListener('ended', () => stopClip());
    clipAudio.addEventListener('error', () => stopClip());
  }
  clipCb = onProgress;
  state.playing = clip.id;
  clipAudio.src = clip.url;
  clipAudio.play().catch(() => stopClip());
  markPlayed(clip.id, false);
  changed();
}
export function stopClip() {
  if (!clipAudio || !state.playing) return;
  const cb = clipCb;
  clipCb = null;
  state.playing = null;
  clipAudio.pause();
  clipAudio.removeAttribute('src');
  if (cb) cb(null);
  changed();
}

/* ---------- "Not played yet" (this device) ---------- */
let playedIds = null;
const playedSet = () => {
  if (!playedIds) { try { playedIds = new Set(JSON.parse(read(PLAYED_KEY) || '[]')); } catch { playedIds = new Set(); } }
  return playedIds;
};
export const played = (id) => playedSet().has(id);
export function markPlayed(id, notify = true) {
  const s = playedSet();
  if (s.has(id)) return;
  s.add(id);
  write(PLAYED_KEY, JSON.stringify([...s].slice(-PLAYED_MAX)));
  state.playedRev += 1;
  if (notify) changed();
}

/* ---------- the "Hear Talkie on this device" switch ---------- */
export const hearing = () => state.hearing;
export function setHearing(on) {
  state.hearing = !!on;
  write(HEAR_KEY, on ? 'on' : 'off');
  if (!on) { stopLive(); state.blocked = false; } else if (state.live) playLive(state.live);
  changed();
}

/* ---------- live pill: someone is talking (on every page but Talkie) ---------- */
let pill = null;
export function setPageOpen(on) { pageOpen = on; paintPill(); }
function paintPill() {
  const live = state.live;
  const show = !!live && !!user && !pageOpen && (state.hearing || state.blocked);
  if (!show) { if (pill) pill.hidden = true; return; }
  if (!pill) {
    pill = h('button', { type: 'button', class: 'tw-pill', hidden: true, onclick: () => { if (state.blocked) listen(); else go('#/announce'); } });
    document.body.append(pill);
  }
  pill.hidden = false;
  pill.classList.toggle('blocked', state.blocked);
  pill.setAttribute('aria-label', state.blocked ? t('tkg.tapAria', live.name) : t('tkg.talking', live.name));
  pill.replaceChildren(h('span', { class: 'tw-bars', 'aria-hidden': 'true' }, h('i'), h('i'), h('i'), h('i')),
    h('span', { class: 'tw-pill-t' }, t('tkg.talking', live.name)),
    state.blocked ? h('span', { class: 'tw-pill-tap' }, icon('speaker', 'xs'), t('tkg.tap')) : null);
}

/* ---------- talking ---------- */
/**
 * holdToTalk({ onState, onLevel }) -> { start(), stop(), destroy() }
 * onState(state, info): 'idle' | 'asking' | 'opening' | 'live' | 'sending' | 'denied' | 'http' | 'error'
 *   idle info = { ended: { reason, clip } } after a talk, { cancelled: true } when released before it went out,
 *   or { allowed: true } after the first-time microphone prompt; error info = { code, detail }
 *   (busy, offline, no_mic, mic_failed, unsupported, bad_request, unavailable, transcoder_error, dropped).
 * The recorder starts as soon as the mic is open and its first chunks wait for the server's "ready", so the first
 * word isn't cut. Releasing sends what was recorded, then {"type": "stop"}.
 */
export function holdToTalk({ onState = () => {}, onLevel = () => {} } = {}) {
  let st = 'idle';
  let stream = null, closeMeter = null, rec = null, queue = [], ready = false, released = false;
  let gen = 0, stopTimer = 0;
  const me = {
    id: null,
    reply(msg) {
      if (msg.type === 'ready') {
        me.id = msg.id;
        ready = true;
        queue.forEach((c) => send(c));
        queue = [];
        if (released) finishRecording();
        else set('live', { maxSeconds: msg.max_seconds });
      } else {
        cleanup();
        set('error', { code: msg.code || 'error', detail: msg.detail || '' });
      }
    },
    ended(msg) { cleanup(); set('idle', { ended: { reason: msg.reason, clip: msg.clip } }); },
    dropped() { if (st !== 'idle') { cleanup(); set('error', { code: 'dropped' }); } },
  };
  const set = (s, info) => { st = s; onState(s, info || {}); };

  function cleanup() {
    gen += 1;
    clearTimeout(stopTimer);
    if (talker === me) talker = null;
    me.id = null;
    if (rec) { rec.ondataavailable = rec.onstop = null; try { if (rec.state !== 'inactive') rec.stop(); } catch { /* stopped */ } rec = null; }
    if (stream) { stream.getTracks().forEach((tr) => tr.stop()); stream = null; }
    if (closeMeter) { closeMeter(); closeMeter = null; }
    queue = []; ready = false; released = false;
  }

  async function start() {
    if (!['idle', 'error', 'denied'].includes(st)) return;
    if (!micAllowedHere()) { set('http'); return; }
    const mime = pickMime();
    if (mime === null) { set('error', { code: 'unsupported' }); return; }
    if (!ws || ws.readyState !== 1 || !state.connected) { set('error', { code: 'offline' }); return; }
    if (talker) return;
    if ((await micPermission()) === 'prompt') {
      // the finger has to leave the button to answer the browser: ask now, talk on the next press
      set('asking');
      const r = await askMic();
      if (r === 'granted') set('idle', { allowed: true });
      else set(r === 'denied' ? 'denied' : 'error', { code: 'mic_failed' });
      return;
    }
    const my = ++gen;
    released = false;
    talker = me;
    set('opening');
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    } catch (e) {
      if (my !== gen) return;
      stream = null;
      cleanup();
      if (e && (e.name === 'NotAllowedError' || e.name === 'SecurityError')) set('denied');
      else set('error', { code: e && e.name === 'NotFoundError' ? 'no_mic' : 'mic_failed' });
      return;
    }
    if (my !== gen) { stream.getTracks().forEach((tr) => tr.stop()); stream = null; return; } // released meanwhile
    closeMeter = openMeter(stream, (v) => onLevel(v));
    try {
      rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    } catch {
      cleanup(); set('error', { code: 'unsupported' }); return;
    }
    rec.ondataavailable = (ev) => {
      if (!ev.data || !ev.data.size) return;
      if (ready) send(ev.data); else queue.push(ev.data);
    };
    rec.onstop = () => { if (my === gen && ready) setTimeout(() => { if (my === gen) send({ type: 'stop' }); }, 0); };
    if (!send({ type: 'start', mime: rec.mimeType || mime })) { cleanup(); set('error', { code: 'offline' }); return; }
    rec.start(CHUNK_MS);
  }

  /** Stop recording: the last chunk comes out first (dataavailable, then stop), then the server is told. */
  function finishRecording() {
    set('sending');
    const my = gen;
    if (closeMeter) { closeMeter(); closeMeter = null; }
    try { if (rec && rec.state === 'recording') rec.stop(); else send({ type: 'stop' }); } catch { send({ type: 'stop' }); }
    if (stream) { stream.getTracks().forEach((tr) => tr.stop()); stream = null; }
    stopTimer = setTimeout(() => { if (my === gen) { cleanup(); set('idle', { ended: { reason: 'stopped', clip: null } }); } }, STOP_WAIT_MS);
  }

  function stop() {
    if (st === 'asking') return; // the browser's prompt is up; it ends by itself
    if (st === 'opening') {
      if (!rec || !ready) {
        released = true;
        if (!rec) { cleanup(); set('idle', { cancelled: true }); return; } // the mic never opened: nothing went out
        // the start went out but no "ready" yet: send what was recorded once it comes
        set('sending');
        try { if (rec.state === 'recording') rec.stop(); } catch { /* stopped */ }
        if (stream) { stream.getTracks().forEach((tr) => tr.stop()); stream = null; }
        if (closeMeter) { closeMeter(); closeMeter = null; }
        const my = gen;
        stopTimer = setTimeout(() => { if (my === gen) { cleanup(); set('idle', { ended: { reason: 'stopped', clip: null } }); } }, STOP_WAIT_MS);
        return;
      }
    }
    if (st === 'live') finishRecording();
  }

  return {
    start, stop,
    get state() { return st; },
    /** Leave the page: end the talk without telling the UI. */
    destroy() {
      if (talker === me && ready) send({ type: 'stop' });
      onState = () => {};
      onLevel = () => {};
      cleanup();
    },
  };
}
