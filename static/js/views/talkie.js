// Talkie (prototype .temp/proto-talkie, owner-approved): the Announce route while "This device" is the music output.
// Hold to talk; everyone with the app open hears it live; the talk is kept as a clip for a day ("Recent").
// The connection, live audio and recorder are ../talkie.js; this file is only the page. Operators and owners get
// a Talkie | Speaker switch at the top: Speaker is the usual Announce page (announce.js passes it in as `speaker`).
import { h, icon, segmented } from '../ui.js';
import { register, t, fmtRel, fmtDur } from '../i18n.js';
import { badge, toneOf, initialOf } from '../kit.js';
import { glyph } from '../icons.js';
import * as talkie from '../talkie.js';

register({
  en: {
    'tk.modeAria': 'Talk to', 'tk.modeTalkie': 'Talkie', 'tk.modeSpeaker': 'Speaker',
    'tk.online': (n) => `${n} online`, 'tk.onlineAria': (names) => `Online: ${names}`, 'tk.connecting': 'Connecting…',
    'tk.isLive': (x) => `${x} is talking…`, 'tk.tap': 'Tap to listen', 'tk.muted': 'Talkie sound is off on this device',
    'tk.hold': 'Hold to talk', 'tk.holdKbd': 'Hold Space to talk', 'tk.release': 'Release to send', 'tk.opening': 'Opening the microphone…',
    'tk.sending': 'Sending…', 'tk.busy': 'Wait until they finish', 'tk.asking': 'Allow the microphone to talk',
    'tk.help': 'Everyone with the app open hears you live; others can play it back for 24 h.',
    'tk.youLive': (x) => `You are live ${x}`, 'tk.pttAria': 'Talk to everyone. Hold to talk',
    'tk.recent': 'Recent', 'tk.empty': 'No messages in the last 24 hours.', 'tk.you': 'You', 'tk.unheard': 'Not played yet',
    'tk.play': (x) => `Play the message from ${x}`, 'tk.stop': 'Stop',
    'tk.sent': 'Sent. Everyone can play it back for 24 hours.', 'tk.short': 'Too short to keep. Hold the button while you talk.',
    'tk.cancelled': 'Nothing went out. Hold the button while you talk.', 'tk.allowed': 'Microphone allowed. Hold the button to talk.',
    'tk.endMax': 'That’s the longest one message can be, so it was sent.', 'tk.dropped': 'The connection dropped, so the message ended.',
    'tk.eBusy': 'Someone else started talking first. Wait until they finish.',
    'tk.eOffline': 'Not connected. Trying again…', 'tk.eDenied': (host) => `The microphone is blocked. Allow it for ${host} in your browser, then try again.`,
    'tk.eHttp': 'Talkie needs the app’s https address: browsers only allow the microphone there.',
    'tk.eNoMic': 'No microphone found. Plug in or turn on a microphone, then try again.',
    'tk.eMic': 'The microphone didn’t start. Close other apps that use it, then try again.',
    'tk.eUnsup': 'This browser can’t record audio. Use a current Safari, Chrome or Firefox.',
    'tk.eServer': 'The server can’t take a message right now. Try again in a moment.',
  },
  th: {
    'tk.modeAria': 'พูดกับ', 'tk.modeTalkie': 'ทอล์คกี้', 'tk.modeSpeaker': 'ลำโพง',
    'tk.online': (n) => `ออนไลน์ ${n} คน`, 'tk.onlineAria': (names) => `ออนไลน์: ${names}`, 'tk.connecting': 'กำลังเชื่อมต่อ…',
    'tk.isLive': (x) => `${x} กำลังพูด…`, 'tk.tap': 'แตะเพื่อฟัง', 'tk.muted': 'ปิดเสียงทอล์คกี้บนอุปกรณ์นี้อยู่',
    'tk.hold': 'กดค้างเพื่อพูด', 'tk.holdKbd': 'กด Space ค้างเพื่อพูด', 'tk.release': 'ปล่อยเพื่อส่ง', 'tk.opening': 'กำลังเปิดไมโครโฟน…',
    'tk.sending': 'กำลังส่ง…', 'tk.busy': 'รอให้พูดจบก่อน', 'tk.asking': 'อนุญาตไมโครโฟนเพื่อพูด',
    'tk.help': 'ทุกคนที่เปิดแอปอยู่ได้ยินทันที คนอื่นฟังย้อนหลังได้ 24 ชม.',
    'tk.youLive': (x) => `คุณกำลังพูด ${x}`, 'tk.pttAria': 'พูดกับทุกคน กดค้างเพื่อพูด',
    'tk.recent': 'ล่าสุด', 'tk.empty': 'ไม่มีข้อความใน 24 ชั่วโมงที่ผ่านมา', 'tk.you': 'คุณ', 'tk.unheard': 'ยังไม่ได้ฟัง',
    'tk.play': (x) => `เล่นข้อความจาก ${x}`, 'tk.stop': 'หยุด',
    'tk.sent': 'ส่งแล้ว ทุกคนฟังย้อนหลังได้ 24 ชั่วโมง', 'tk.short': 'สั้นเกินไป ไม่ได้เก็บไว้ กดปุ่มค้างไว้ตลอดที่พูด',
    'tk.cancelled': 'ยังไม่มีเสียงออกไป กดปุ่มค้างไว้ตลอดที่พูด', 'tk.allowed': 'อนุญาตไมโครโฟนแล้ว กดปุ่มค้างไว้เพื่อพูด',
    'tk.endMax': 'ครบความยาวสูงสุดของข้อความหนึ่งครั้งแล้ว จึงส่งไปเลย', 'tk.dropped': 'การเชื่อมต่อหลุด ข้อความจึงจบลง',
    'tk.eBusy': 'มีคนเริ่มพูดก่อน รอให้พูดจบก่อน',
    'tk.eOffline': 'ยังไม่ได้เชื่อมต่อ กำลังลองใหม่…', 'tk.eDenied': (host) => `ไมโครโฟนถูกปิดกั้น ให้อนุญาตให้ ${host} ใช้ไมโครโฟนในเบราว์เซอร์ แล้วลองอีกครั้ง`,
    'tk.eHttp': 'ทอล์คกี้ต้องเปิดแอปด้วยที่อยู่ https เบราว์เซอร์ให้ใช้ไมโครโฟนได้เฉพาะแบบนั้น',
    'tk.eNoMic': 'ไม่พบไมโครโฟน เสียบหรือเปิดไมโครโฟน แล้วลองอีกครั้ง',
    'tk.eMic': 'เปิดไมโครโฟนไม่ได้ ปิดแอปอื่นที่ใช้ไมโครโฟนอยู่ แล้วลองอีกครั้ง',
    'tk.eUnsup': 'เบราว์เซอร์นี้อัดเสียงไม่ได้ ใช้ Safari, Chrome หรือ Firefox รุ่นใหม่',
    'tk.eServer': 'ตอนนี้เซิร์ฟเวอร์ยังรับข้อความไม่ได้ ลองใหม่อีกครู่',
  },
});

const WAVE_N = 28;
const MAX_FACES = 5;
const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
let side = 'talkie'; // Talkie | Speaker for operators, kept while the app is open

/** The Announce route on "This device". speaker(top) builds the usual Announce page with `top` under its header. */
export async function talkieView(ctx, { speaker }) {
  await Promise.all([ctx.css('views/talkie.css'), ctx.css('views/common.css')]);
  const op = ctx.can('operator');
  const host = h('div', { class: 'tw-host' });
  let current = null; // the page shown: { node, onStatus?, destroy? }

  const toggle = () => segmented({
    options: [{ value: 'talkie', label: t('tk.modeTalkie') }, { value: 'speaker', label: t('tk.modeSpeaker') }],
    value: side, label: t('tk.modeAria'), cls: 'tw-side', onChange: (v) => { side = v; show(); },
  });

  async function show() {
    if (current && current.destroy) current.destroy();
    current = side === 'speaker' && op ? await speaker(toggle()) : buildTalkie(ctx, op ? toggle() : null);
    host.replaceChildren(current.node);
    if (current.onStatus && (ctx.status || ctx.statusError)) current.onStatus({ status: ctx.status, error: ctx.statusError });
  }
  await show();
  ctx.onCleanup(() => { if (current && current.destroy) current.destroy(); });
  return { node: host, onStatus: (s) => { if (current && current.onStatus) current.onStatus(s); } };
}

/** A small deterministic waveform for a clip (no real levels are stored): bar heights from its id. */
function bars(id) {
  let x = 0;
  for (const c of id) x = (x * 31 + c.charCodeAt(0)) >>> 0;
  return Array.from({ length: WAVE_N }, () => { x = (x * 1103515245 + 12345) >>> 0; return 4 + (x >>> 16) % 17; });
}

function face(person, size = '') {
  return h('span', { class: `avatar tw-av ${size}`.trim(), 'aria-hidden': 'true', style: { background: toneOf(person.user_id ?? person.id) } }, initialOf(person.name));
}

function buildTalkie(ctx, toggleEl) {
  const head = ctx.header({ title: t('nav.talkie') });
  const cleanups = [];

  /* ----- who is here ----- */
  const faces = h('span', { class: 'tw-faces', 'aria-hidden': 'true' });
  const count = h('span', { class: 'small tw-count' });
  const onlineRow = h('div', { class: 'tw-online' }, faces, count);

  /* ----- someone else talking ----- */
  const liveName = h('strong', { class: 'tw-live-t' });
  const liveFace = h('span', { class: 'tw-live-av' });
  const tapBtn = h('button', { type: 'button', class: 'btn tw-tap', onclick: () => talkie.listen() }, icon('speaker', 'sm'), t('tk.tap'));
  const banner = h('div', { class: 'tw-live', role: 'status', hidden: true }, liveFace, liveName,
    h('span', { class: 'tw-bars', 'aria-hidden': 'true' }, h('i'), h('i'), h('i'), h('i'), h('i')), tapBtn);

  /* ----- push to talk ----- */
  const status = h('p', { class: 'tw-status', role: 'status' });
  const ptt = h('button', { type: 'button', class: 'tw-ptt', 'aria-label': t('tk.pttAria'), 'aria-describedby': 'tw-help' }, glyph('mic', 'tw-mic'));
  const label = h('p', { class: 'tw-label' });
  const help = h('p', { class: 'small tw-help', id: 'tw-help' }, t('tk.help'));
  const errBox = h('p', { class: 'tw-err', role: 'alert', hidden: true });
  const stage = h('div', { class: 'tw-stage' }, status, h('div', { class: 'tw-pttwrap' }, ptt), label, errBox, help);
  const talkCard = h('section', { class: 'c-card tw-card', 'aria-label': t('nav.talkie') }, stage);

  /* ----- recent clips ----- */
  const list = h('div', { class: 'c-card tw-list', role: 'list' });
  const recent = h('section', { class: 'tw-recent', 'aria-labelledby': 'tw-rec' }, h('h2', { class: 'tw-cap', id: 'tw-rec' }, t('tk.recent')), list);

  const node = h('div', { class: 'page tw-page' }, head, toggleEl, onlineRow, banner, talkCard, recent);

  let st = 'idle', info = {}, startAt = 0, timer = 0, keyHeld = false, holding = false;
  const ctl = talkie.holdToTalk({
    onState: (s, i) => onState(s, i),
    onLevel: (v) => ptt.style.setProperty('--lv', v.toFixed(2)),
  });

  function onState(s, i) {
    const prev = st;
    st = s; info = i || {};
    if (s === 'live' && prev !== 'live') { startAt = Date.now(); clearInterval(timer); timer = setInterval(paintStatus, 250); }
    if (s !== 'live') { clearInterval(timer); timer = 0; }
    if (s === 'idle' && info.ended) {
      const e = info.ended;
      if (e.reason === 'disconnected') ctx.toast(t('tk.dropped'), 'err');
      else if (!e.clip) ctx.toast(t('tk.short'), 'info');
      else ctx.toast(t(e.reason === 'max_length' ? 'tk.endMax' : 'tk.sent'), 'ok');
    }
    if (s === 'idle' && info.cancelled) ctx.toast(t('tk.cancelled'), 'info');
    if (s === 'idle' && info.allowed) ctx.toast(t('tk.allowed'), 'info');
    if (s === 'error' && info.code === 'busy') { st = 'idle'; ctx.toast(t('tk.eBusy'), 'info'); }
    paint();
  }

  /* ----- input: hold with a finger, the mouse, or Space/Enter ----- */
  const down = () => { if (!holding && !someoneElse()) { holding = true; ctl.start(); } };
  const up = () => { if (holding) { holding = false; ctl.stop(); } };
  ptt.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    if (e.cancelable) e.preventDefault(); // no text selection, no focus jump, no long-press menu
    try { ptt.setPointerCapture(e.pointerId); } catch { /* still works without */ }
    down();
  });
  ptt.addEventListener('pointerup', up);
  ptt.addEventListener('pointercancel', up);
  ptt.addEventListener('lostpointercapture', up);
  ptt.addEventListener('contextmenu', (e) => e.preventDefault());
  const isKey = (e) => e.code === 'Space' || e.key === ' ' || e.key === 'Enter';
  const typing = (e) => e.target && e.target.closest && e.target.closest('input,textarea,select,a,[contenteditable],dialog')
    || (e.target && e.target !== ptt && e.target.closest && e.target.closest('button')) || document.querySelector('dialog[open]');
  const onKeyDown = (e) => {
    if (!isKey(e) || (e.key === 'Enter' && e.target !== ptt) || typing(e)) return;
    e.preventDefault();
    if (e.repeat || keyHeld) return;
    keyHeld = true;
    down();
  };
  const onKeyUp = (e) => { if (keyHeld && isKey(e)) { e.preventDefault(); keyHeld = false; up(); } };
  const onBlur = () => { if (keyHeld) { keyHeld = false; up(); } };
  document.addEventListener('keydown', onKeyDown);
  document.addEventListener('keyup', onKeyUp);
  window.addEventListener('blur', onBlur);
  cleanups.push(() => { document.removeEventListener('keydown', onKeyDown); document.removeEventListener('keyup', onKeyUp); window.removeEventListener('blur', onBlur); });

  let lastState = null;
  const someoneElse = () => !!(lastState && lastState.live); // talkie.js only reports other members' talks

  /* ----- painting ----- */
  function paintStatus() {
    status.hidden = st !== 'live';
    if (st === 'live') status.textContent = `● ${t('tk.youLive', mmss((Date.now() - startAt) / 1000))}`;
  }
  function paint() {
    const s = lastState || {};
    const blocked = !!s.live;
    const touch = matchMedia('(pointer: coarse)').matches;
    talkCard.dataset.state = blocked && st === 'idle' ? 'busy' : st;
    paintStatus();
    ptt.disabled = (blocked && st === 'idle') || st === 'sending' || st === 'asking' || (!s.connected && st === 'idle');
    ptt.setAttribute('aria-pressed', String(st === 'live' || st === 'opening'));
    const L = { live: 'tk.release', opening: 'tk.opening', sending: 'tk.sending', asking: 'tk.asking' }[st];
    label.textContent = t(L || (blocked ? 'tk.busy' : !s.connected ? 'tk.connecting' : touch ? 'tk.hold' : 'tk.holdKbd'));
    const E = { denied: () => t('tk.eDenied', location.host), http: () => t('tk.eHttp') }[st]
      || (st === 'error' && (() => t({ offline: 'tk.eOffline', dropped: 'tk.dropped', no_mic: 'tk.eNoMic', mic_failed: 'tk.eMic',
        unsupported: 'tk.eUnsup' }[info.code] || 'tk.eServer')));
    errBox.hidden = !E;
    errBox.textContent = E ? E() : '';
  }

  function paintOnline(s) {
    const people = s.online || [];
    faces.replaceChildren(...people.slice(0, MAX_FACES).map((p) => face(p, 'sm')));
    if (people.length > MAX_FACES) faces.append(h('span', { class: 'avatar tw-av sm tw-more' }, `+${people.length - MAX_FACES}`));
    count.replaceChildren(h('span', { class: 'tw-dot', 'aria-hidden': 'true' }), s.connected ? t('tk.online', people.length) : t('tk.connecting'));
    onlineRow.setAttribute('aria-label', t('tk.onlineAria', people.map((p) => p.name).join(', ')));
    onlineRow.setAttribute('role', 'group');
  }

  function paintLive(s) {
    banner.hidden = !s.live;
    if (!s.live) return;
    liveFace.replaceChildren(face(s.live));
    liveName.textContent = t('tk.isLive', s.live.name);
    tapBtn.hidden = !s.blocked;
    banner.classList.toggle('muted', !s.hearing && !s.blocked);
    banner.title = !s.hearing ? t('tk.muted') : '';
  }

  /* ----- recent ----- */
  const rows = new Map(); // clip id -> { row, paint(progress) }
  function paintList(s) {
    const clips = s.clips || [];
    if (!clips.length) { rows.clear(); list.replaceChildren(h('p', { class: 'small tw-empty' }, t('tk.empty'))); return; }
    list.replaceChildren(...clips.map((c) => clipRow(c, s)));
  }
  function clipRow(c, s) {
    const mine = c.user_id === s.me;
    const who = mine ? t('tk.you') : c.name;
    const wave = h('span', { class: 'tw-wave', 'aria-hidden': 'true' }, bars(c.id).map((ht) => h('i', { style: { height: `${ht}px` } })));
    const playing = s.playing === c.id;
    const btn = h('button', {
      type: 'button', class: 'tw-play', 'aria-pressed': String(playing), 'aria-label': playing ? t('tk.stop') : t('tk.play', who),
      onclick: () => { if (playing) talkie.stopClip(); else talkie.playClip(c, (p) => progress(c.id, p)); },
    }, glyph(playing ? 'pause' : 'play', 'sm'));
    const unheard = !mine && !talkie.played(c.id) ? badge(t('tk.unheard')) : null;
    const row = h('div', { class: 'tw-row', role: 'listitem', dataset: { id: c.id } }, face(c),
      h('div', { class: 'tw-row-tx' },
        h('div', { class: 'tw-row-top' }, h('strong', {}, who), h('span', { class: 'small' }, fmtRel(c.created_at)), unheard),
        h('div', { class: 'tw-row-wave' }, wave, h('span', { class: 'small tw-len' }, fmtDur(c.seconds)))),
      btn);
    rows.set(c.id, { wave });
    return row;
  }
  function progress(id, p) {
    const r = rows.get(id);
    if (!r) return;
    const n = p == null ? 0 : Math.round(p * WAVE_N);
    r.wave.childNodes.forEach((b, i) => b.classList.toggle('on', i < n));
  }

  function onTalkie(s) {
    const listChanged = !lastState || ['clips', 'playing', 'me', 'playedRev'].some((k) => lastState[k] !== s[k]);
    lastState = { ...s };
    paintOnline(s);
    paintLive(s);
    if (listChanged) paintList(s);
    paint();
  }
  cleanups.push(talkie.onChange(onTalkie));
  // relative times ("2 min ago") move on: once a minute is plenty
  const relTimer = setInterval(() => { if (lastState) paintList(lastState); }, 60000);
  cleanups.push(() => clearInterval(relTimer));
  talkie.setPageOpen(true);
  cleanups.push(() => talkie.setPageOpen(false));
  onTalkie(talkie.snapshot());

  return {
    node,
    destroy() { clearInterval(timer); ctl.destroy(); cleanups.forEach((f) => f()); },
  };
}
