// Live talk client (feat/live-talk protocol): browser mic -> MediaRecorder chunks -> WebSocket /talk.
//
//   const talk = liveTalk({ onState, onLevel });
//   talk.start({ chime: true });   // asks for the mic if needed, connects, streams
//   talk.stop();                   // ends (or cancels while still connecting)
//
// onState(state, info): 'asking' | 'connecting' | 'live' | 'ending' | 'idle' | 'denied' | 'http' | 'error'
//   idle  info = { ended: { reason, seconds } } after a talk, or { cancelled: true } when stopped before going live
//   error info = { code, detail, close } (server refusal or a broken connection)
// onLevel(0..1) ~20 times a second while the mic is open (RMS from a real AnalyserNode).
//
// Protocol: client {"type":"start","mime","chime","volume"} -> server {"type":"ready","id","max_seconds","format"}
// -> binary chunks -> server {"type":"live"} -> client {"type":"stop"} -> server {"type":"ended","reason","seconds"},
// close 1000. Refusals: {"type":"error","code","detail"} + close 4400/4401/4403/4409/4503. ping -> pong.

const CHUNK_MS = 250;
const PING_MS = 15000;
const END_WAIT_MS = 6000;
const CLOSE_CODES = { 4400: 'bad_request', 4401: 'unauthorized', 4403: 'forbidden', 4409: 'busy', 4503: 'unavailable' };

/** True when the page may use the microphone at all (https or localhost). */
export const micAllowedHere = () => !!(window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia);

/** Best recorder format this browser supports: Opus in WebM (Chrome/Firefox), else MP4/AAC (Safari). */
export function pickMime() {
  if (typeof MediaRecorder === 'undefined') return null;
  for (const m of ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']) {
    try { if (MediaRecorder.isTypeSupported(m)) return m; } catch { /* old Safari */ }
  }
  return '';
}

/** 'granted' | 'denied' | 'prompt' | 'unknown' (Safari < 16 and Firefox may not answer). */
export async function micPermission() {
  try {
    const p = await navigator.permissions.query({ name: 'microphone' });
    return p.state;
  } catch { return 'unknown'; }
}

/** Ask for the mic without talking (first hold on a phone: the finger has to leave the button to answer the prompt).
 *  Resolves 'granted' | 'denied' | 'error'. */
export async function askMic() {
  try {
    const s = await navigator.mediaDevices.getUserMedia({ audio: true });
    s.getTracks().forEach((tr) => tr.stop());
    return 'granted';
  } catch (e) {
    return e && (e.name === 'NotAllowedError' || e.name === 'SecurityError') ? 'denied' : 'error';
  }
}

export function liveTalk({ onState = () => {}, onLevel = () => {} } = {}) {
  let state = 'idle';
  let stream = null, audio = null, levelTimer = 0;
  let ws = null, rec = null, pingTimer = 0, endTimer = 0;
  let ended = null;      // { reason, seconds } once the server said so
  let refused = null;    // { code, detail } from a server error frame
  let wentLive = false;
  let gen = 0;           // bumps on every start/cleanup so late callbacks from an old session are ignored

  const set = (s, info) => { state = s; onState(s, info || {}); };

  function cleanup() {
    gen += 1;
    clearInterval(levelTimer); clearInterval(pingTimer); clearTimeout(endTimer);
    levelTimer = pingTimer = endTimer = 0;
    try { if (rec && rec.state !== 'inactive') rec.stop(); } catch { /* already stopped */ }
    rec = null;
    if (ws) {
      ws.onopen = ws.onmessage = ws.onclose = ws.onerror = null;
      try { if (ws.readyState <= 1) ws.close(1000); } catch { /* closed */ }
      ws = null;
    }
    if (stream) { stream.getTracks().forEach((tr) => tr.stop()); stream = null; }
    if (audio) { audio.close().catch(() => {}); audio = null; }
    onLevel(0);
  }

  function meter() {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      audio = new Ctx();
      const src = audio.createMediaStreamSource(stream);
      const an = audio.createAnalyser();
      an.fftSize = 1024;
      src.connect(an);
      const buf = new Float32Array(an.fftSize);
      levelTimer = setInterval(() => {
        an.getFloatTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
        const rms = Math.sqrt(sum / buf.length);
        onLevel(Math.min(1, Math.sqrt(rms) * 1.6)); // perceptual-ish: quiet speech still moves the bar
      }, 50);
    } catch { /* no Web Audio: the talk still works, the meter stays flat */ }
  }

  async function start({ chime = true, volume = null } = {}) {
    if (state !== 'idle' && state !== 'error' && state !== 'denied') return;
    if (!micAllowedHere()) { set('http'); return; }
    const mime = pickMime();
    if (mime === null) { set('error', { code: 'unsupported' }); return; }
    const my = ++gen;
    ended = refused = null;
    wentLive = false;
    set((await micPermission()) === 'granted' ? 'connecting' : 'asking'); // the mic can take a moment to open
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    } catch (e) {
      if (my !== gen) return;
      stream = null;
      if (e && (e.name === 'NotAllowedError' || e.name === 'SecurityError')) set('denied');
      else set('error', { code: e && e.name === 'NotFoundError' ? 'no_mic' : 'mic_failed' });
      return;
    }
    if (my !== gen) { stream.getTracks().forEach((tr) => tr.stop()); return; } // cancelled while the prompt was up
    if (state !== 'connecting') set('connecting');
    meter();
    try {
      rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    } catch {
      cleanup(); set('error', { code: 'unsupported' }); return;
    }
    rec.ondataavailable = (ev) => { if (ev.data && ev.data.size && ws && ws.readyState === 1) ws.send(ev.data); };
    ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/talk`);
    ws.binaryType = 'arraybuffer';
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: 'start', mime: rec.mimeType || mime, chime: !!chime, volume }));
      pingTimer = setInterval(() => { if (ws && ws.readyState === 1) ws.send(JSON.stringify({ type: 'ping' })); }, PING_MS);
    };
    ws.onmessage = (ev) => {
      if (typeof ev.data !== 'string') return;
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.type === 'ready') { try { rec.start(CHUNK_MS); } catch { /* recorder gone */ } }
      else if (msg.type === 'live') { wentLive = true; if (state === 'connecting') set('live'); }
      else if (msg.type === 'ended') ended = { reason: msg.reason || 'stopped', seconds: msg.seconds || 0, detail: msg.detail || '' };
      else if (msg.type === 'error') refused = { code: msg.code || 'error', detail: msg.detail || '' };
    };
    ws.onclose = (ev) => finish(ev.code);
    ws.onerror = () => { /* onclose follows with the code */ };
  }

  function finish(code) {
    const wasCancel = state === 'idle';
    const info = ended;
    const why = refused || (CLOSE_CODES[code] ? { code: CLOSE_CODES[code], detail: '' } : null);
    cleanup();
    if (wasCancel) return;
    if (why) { set('error', { ...why, close: code }); return; }
    if (info && ['speaker_error', 'transcoder_error'].includes(info.reason)) { set('error', { code: info.reason, detail: info.detail || '' }); return; }
    if (info) { set('idle', { ended: info }); return; }
    // closed without an "ended" frame: a dropped connection
    if (wentLive || state === 'ending') set('idle', { ended: { reason: 'disconnected', seconds: 0 } });
    else set('error', { code: 'disconnected', close: code });
  }

  function stop() {
    if (state === 'asking') { cleanup(); set('idle', { cancelled: true }); return; }
    if (state === 'connecting' && !wentLive) {
      // nothing went out yet: drop it
      if (ws && ws.readyState === 1) { try { ws.send(JSON.stringify({ type: 'stop' })); } catch { /* closing */ } }
      cleanup();
      set('idle', { cancelled: true });
      return;
    }
    if (state !== 'live') return;
    set('ending');
    const my = gen;
    try { if (rec && rec.state === 'recording') rec.stop(); } catch { /* stopped */ } // flushes the last chunk first
    setTimeout(() => { if (my === gen && ws && ws.readyState === 1) ws.send(JSON.stringify({ type: 'stop' })); }, 60);
    endTimer = setTimeout(() => { if (my === gen) finish(1000); }, END_WAIT_MS);
  }

  return {
    start, stop,
    get state() { return state; },
    /** Leave the page: end whatever is going on without telling the UI. */
    destroy() {
      if (ws && ws.readyState === 1) { try { ws.send(JSON.stringify({ type: 'stop' })); } catch { /* closing */ } }
      onState = () => {};
      cleanup();
    },
  };
}
