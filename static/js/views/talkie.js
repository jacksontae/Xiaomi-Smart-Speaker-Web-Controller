// Talkie (prototypes .temp/proto-talkie and proto-talkie2 v3, owner-approved): the Announce route while "This device"
// is the music output. Two tabs (#/announce/walkie, #/announce/messages):
//   Walkie          hold to talk live to everyone in the room, one at a time, heard once and not kept. This tab is
//                   "in the room" only while its Walkie shows: only then is the walkie heard here. The members are
//                   square cards: in the room (the talker ringed, with moving bars once their voice arrives), then
//                   those online elsewhere, greyed ("Can't hear").
//   Voice messages  hold to record a message for everyone, kept for a day; play, and delete your own (with Undo).
// The connection, live audio and recorder are ../talkie.js; this file is only the page. There is no speaker side here:
// nothing goes to the speaker while this device plays the music, so announcing means switching the output back.
import { h, icon, segmented } from '../ui.js';
import { register, t, fmtRel, fmtDur } from '../i18n.js';
import { badge, toneOf, initialOf } from '../kit.js';
import { glyph } from '../icons.js';
import { isPhone } from '../sheet.js';
import { ibtn, deleteLater, isPending, undoDelete } from '../media-kit.js';
import * as talkie from '../talkie.js';

register({
  en: {
    'tk.modes': 'Talkie mode', 'tk.walkie': 'Walkie', 'tk.msgs': 'Voice messages', 'tk.liveAria': 'Someone is talking on Walkie',
    'tk.isLive': (x) => `${x} is talking…`, 'tk.tap': 'Tap to listen', 'tk.connecting': 'Connecting…',
    'tk.hold': 'Hold to talk', 'tk.holdKbd': 'Hold Space to talk', 'tk.release': 'Release to send', 'tk.releaseW': 'Release to stop',
    'tk.opening': 'Opening the microphone…', 'tk.sending': 'Sending…', 'tk.busy': 'Wait until they finish', 'tk.asking': 'Allow the microphone to talk',
    'tk.help': 'Plays live to everyone in the room, one person at a time. Heard once, not kept.',
    'tk.youLive': (x) => `You are live ${x}`, 'tk.pttAria': 'Talk to everyone. Hold to talk',
    'tk.room': (n) => `In the room · ${n}`, 'tk.listening': 'Listening', 'tk.talking': 'Talking', 'tk.away': 'Can’t hear',
    'tk.showAll': (n) => `Show ${n} more`,
    'tk.rec': 'Hold to record a message', 'tk.recHelp': 'Left for everyone, not played live. Kept for 24 h; play it as often as you like.',
    'tk.recording': (x) => `Recording ${x}`,
    'tk.recent': 'Last 24 hours', 'tk.empty': 'No messages in the last 24 hours.', 'tk.you': 'You', 'tk.unheard': 'Not played yet',
    'tk.play': (x) => `Play the message from ${x}`, 'tk.stop': 'Stop',
    'tk.more': 'Message options', 'tk.delete': 'Delete', 'tk.deleted': 'Voice message deleted', 'tk.undo': 'Undo',
    'tk.sent': 'Sent. Everyone can play it back for 24 hours.', 'tk.short': 'Too short to keep. Hold the button while you talk.',
    'tk.cancelled': 'Nothing went out. Hold the button while you talk.', 'tk.allowed': 'Microphone allowed. Hold the button to talk.',
    'tk.endMax': 'That’s the longest one message can be, so it was sent.', 'tk.endMaxW': 'That’s the longest one talk can be, so it ended.',
    'tk.dropped': 'The connection dropped, so the message ended.',
    'tk.eBusy': 'Someone else started talking first. Wait until they finish.',
    'tk.eOffline': 'Not connected. Trying again…', 'tk.eDenied': (host) => `The microphone is blocked. Allow it for ${host} in your browser, then try again.`,
    'tk.eHttp': 'Talkie needs the app’s https address: browsers only allow the microphone there.',
    'tk.eNoMic': 'No microphone found. Plug in or turn on a microphone, then try again.',
    'tk.eMic': 'The microphone didn’t start. Close other apps that use it, then try again.',
    'tk.eUnsup': 'This browser can’t record audio. Use a current Safari, Chrome or Firefox.',
    'tk.eServer': 'The server can’t take a message right now. Try again in a moment.',
  },
  th: {
    'tk.modes': 'โหมดทอล์คกี้', 'tk.walkie': 'วอล์กกี้', 'tk.msgs': 'ข้อความเสียง', 'tk.liveAria': 'มีคนกำลังพูดในวอล์กกี้',
    'tk.isLive': (x) => `${x} กำลังพูด…`, 'tk.tap': 'แตะเพื่อฟัง', 'tk.connecting': 'กำลังเชื่อมต่อ…',
    'tk.hold': 'กดค้างเพื่อพูด', 'tk.holdKbd': 'กด Space ค้างเพื่อพูด', 'tk.release': 'ปล่อยเพื่อส่ง', 'tk.releaseW': 'ปล่อยเพื่อหยุดพูด',
    'tk.opening': 'กำลังเปิดไมโครโฟน…', 'tk.sending': 'กำลังส่ง…', 'tk.busy': 'รอให้พูดจบก่อน', 'tk.asking': 'อนุญาตไมโครโฟนเพื่อพูด',
    'tk.help': 'ทุกคนในห้องได้ยินสดทันที พูดได้ทีละคน ฟังครั้งเดียวแล้วหายไป ไม่เก็บไว้',
    'tk.youLive': (x) => `คุณกำลังพูด ${x}`, 'tk.pttAria': 'พูดกับทุกคน กดค้างเพื่อพูด',
    'tk.room': (n) => `ในห้อง · ${n} คน`, 'tk.listening': 'กำลังฟัง', 'tk.talking': 'กำลังพูด', 'tk.away': 'ไม่ได้ยิน',
    'tk.showAll': (n) => `ดูอีก ${n} คน`,
    'tk.rec': 'กดค้างเพื่ออัดข้อความ', 'tk.recHelp': 'ฝากไว้ให้ทุกคน ไม่เล่นสด เก็บไว้ 24 ชม. กดฟังกี่ครั้งก็ได้',
    'tk.recording': (x) => `กำลังอัด ${x}`,
    'tk.recent': '24 ชั่วโมงที่ผ่านมา', 'tk.empty': 'ไม่มีข้อความใน 24 ชั่วโมงที่ผ่านมา', 'tk.you': 'คุณ', 'tk.unheard': 'ยังไม่ได้ฟัง',
    'tk.play': (x) => `เล่นข้อความจาก ${x}`, 'tk.stop': 'หยุด',
    'tk.more': 'ตัวเลือกข้อความ', 'tk.delete': 'ลบ', 'tk.deleted': 'ลบข้อความเสียงแล้ว', 'tk.undo': 'เลิกทำ',
    'tk.sent': 'ส่งแล้ว ทุกคนฟังย้อนหลังได้ 24 ชั่วโมง', 'tk.short': 'สั้นเกินไป ไม่ได้เก็บไว้ กดปุ่มค้างไว้ตลอดที่พูด',
    'tk.cancelled': 'ยังไม่มีเสียงออกไป กดปุ่มค้างไว้ตลอดที่พูด', 'tk.allowed': 'อนุญาตไมโครโฟนแล้ว กดปุ่มค้างไว้เพื่อพูด',
    'tk.endMax': 'ครบความยาวสูงสุดของข้อความหนึ่งครั้งแล้ว จึงส่งไปเลย', 'tk.endMaxW': 'ครบความยาวสูงสุดของการพูดหนึ่งครั้งแล้ว จึงจบลง',
    'tk.dropped': 'การเชื่อมต่อหลุด ข้อความจึงจบลง',
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
const PHONE_CARDS = 6; // a phone shows this many member cards at most (the last one "+N") until it is tapped
const UNDO_MS = 5000;
const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const first = (name) => String(name || '').split(' ')[0];
/** The Announce route on "This device". */
export async function talkieView(ctx) {
  await Promise.all([ctx.css('views/talkie.css'), ctx.css('views/common.css')]);
  const page = buildTalkie(ctx, ctx.params[0] === 'messages' ? 'messages' : 'walkie');
  ctx.onCleanup(() => page.destroy());
  return { node: page.node };
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

const liveBars = (cls = '') => h('span', { class: `tw-bars ${cls}`.trim(), 'aria-hidden': 'true' }, h('i'), h('i'), h('i'), h('i'), h('i'));

function buildTalkie(ctx, tab0) {
  const head = ctx.header({ title: t('nav.talkie') });
  const cleanups = [];
  let tab = tab0;

  /* ----- tabs: a speaker on Walkie while someone talks there, the unread count on Voice messages ----- */
  const liveMark = h('span', { class: 'tw-livebadge', role: 'img', 'aria-label': t('tk.liveAria'), hidden: true }, glyph('volume', 'xs'));
  const unreadMark = h('span', { class: 'tw-unread', role: 'img', hidden: true });
  const tabs = segmented({
    label: t('tk.modes'), cls: 'tw-tabs', value: tab, onChange: (v) => setTab(v),
    options: [
      { value: 'walkie', label: [h('span', {}, t('tk.walkie')), liveMark] },
      { value: 'messages', label: [h('span', {}, t('tk.msgs')), unreadMark] },
    ],
  });

  /* ----- Walkie: the browser blocked the live audio ----- */
  const liveName = h('strong', { class: 'tw-live-t' });
  const liveFace = h('span', { class: 'tw-live-av' });
  const tapBtn = h('button', { type: 'button', class: 'btn tw-tap', onclick: () => talkie.listen() }, icon('speaker', 'sm'), t('tk.tap'));
  const banner = h('div', { class: 'tw-live', role: 'status', hidden: true }, liveFace, liveName, liveBars(), tapBtn);

  /* ----- Walkie: push to talk ----- */
  const status = h('p', { class: 'tw-status', role: 'status' });
  const ptt = h('button', { type: 'button', class: 'tw-ptt', 'aria-label': t('tk.pttAria'), 'aria-describedby': 'tw-help' }, glyph('mic', 'tw-mic'));
  const label = h('p', { class: 'tw-label' });
  const help = h('p', { class: 'small tw-help', id: 'tw-help' }, t('tk.help'));
  const errBox = h('p', { class: 'tw-err', role: 'alert', hidden: true });
  const stage = h('div', { class: 'tw-stage' }, status, h('div', { class: 'tw-pttwrap' }, ptt), label, errBox, help);
  const talkCard = h('section', { class: 'c-card tw-card', 'aria-label': t('tk.walkie') }, stage);

  /* ----- Walkie: who is in the room ----- */
  const roomCap = h('h2', { class: 'tw-cap', id: 'tw-roomcap' });
  const grid = h('div', { class: 'tw-grid', role: 'list' });
  const roomBox = h('section', { class: 'tw-room', 'aria-labelledby': 'tw-roomcap' }, roomCap, grid);

  /* ----- Voice messages: hold to record ----- */
  const rec = h('button', { type: 'button', class: 'tw-rec', 'aria-label': t('tk.rec'), 'aria-describedby': 'tw-rechelp' }, glyph('mic', 'tw-rec-mic'));
  const recLabel = h('p', { class: 'tw-reclabel' });
  const recHelp = h('p', { class: 'small', id: 'tw-rechelp' });
  const recErr = h('p', { class: 'tw-err', role: 'alert', hidden: true });
  const recBar = h('section', { class: 'c-card tw-recbar' }, rec, h('div', { class: 'tw-rectx' }, recLabel, recHelp, recErr));

  /* ----- Voice messages: the last day's ----- */
  const list = h('div', { class: 'c-card tw-list', role: 'list' });
  const recent = h('section', { class: 'tw-recent', 'aria-labelledby': 'tw-rec' }, h('h2', { class: 'tw-cap', id: 'tw-rec' }, t('tk.recent')), list);

  const node = h('div', { class: 'page tw-page' }, head, tabs, banner, talkCard, roomBox, recBar, recent);

  /* ----- holding a button: the Walkie's (live) or Voice messages' (kept) ----- */
  let timer = 0, keyHeld = false, lastState = null;
  const someoneElse = () => !!(lastState && lastState.live); // talkie.js only reports other members' talks
  function control(mode, btn) {
    const c = { mode, btn, st: 'idle', info: {}, startAt: 0, holding: false };
    c.ctl = talkie.holdToTalk({ mode, onState: (s, i) => onState(c, s, i), onLevel: (v) => btn.style.setProperty('--lv', v.toFixed(2)) });
    c.down = () => { if (!c.holding && !(mode === 'walkie' && someoneElse())) { c.holding = true; c.ctl.start(); } };
    c.up = () => { if (c.holding) { c.holding = false; c.ctl.stop(); } };
    btn.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      if (e.cancelable) e.preventDefault(); // no text selection, no focus jump, no long-press menu
      try { btn.setPointerCapture(e.pointerId); } catch { /* still works without */ }
      c.down();
    });
    btn.addEventListener('pointerup', c.up);
    btn.addEventListener('pointercancel', c.up);
    btn.addEventListener('lostpointercapture', c.up);
    btn.addEventListener('contextmenu', (e) => e.preventDefault());
    return c;
  }
  const walkie = control('walkie', ptt);
  const message = control('message', rec);
  const active = () => (tab === 'walkie' ? walkie : message);

  function onState(c, s, i) {
    const prev = c.st;
    c.st = s; c.info = i || {};
    if (s === 'live' && prev !== 'live') c.startAt = Date.now();
    const live = walkie.st === 'live' || message.st === 'live';
    if (live && !timer) timer = setInterval(paintClock, 250);
    if (!live) { clearInterval(timer); timer = 0; }
    const info = c.info;
    if (s === 'idle' && info.ended) {
      const e = info.ended;
      if (e.reason === 'disconnected') ctx.toast(t('tk.dropped'), 'err');
      else if (c.mode === 'walkie') { if (e.reason === 'max_length') ctx.toast(t('tk.endMaxW'), 'info'); } // heard once: nothing kept
      else if (!e.clip) ctx.toast(t('tk.short'), 'info');
      else ctx.toast(t(e.reason === 'max_length' ? 'tk.endMax' : 'tk.sent'), 'ok');
    }
    if (s === 'idle' && info.cancelled) ctx.toast(t('tk.cancelled'), 'info');
    if (s === 'idle' && info.allowed) ctx.toast(t('tk.allowed'), 'info');
    if (s === 'error' && info.code === 'busy') { c.st = 'idle'; ctx.toast(t('tk.eBusy'), 'info'); }
    paint();
  }

  /* ----- input: hold with a finger, the mouse, or Space/Enter (the open tab's button) ----- */
  const isKey = (e) => e.code === 'Space' || e.key === ' ' || e.key === 'Enter';
  const typing = (e) => e.target && e.target.closest && e.target.closest('input,textarea,select,a,[contenteditable],dialog')
    || (e.target && e.target !== active().btn && e.target.closest && e.target.closest('button')) || document.querySelector('dialog[open]');
  const onKeyDown = (e) => {
    if (!isKey(e) || (e.key === 'Enter' && e.target !== active().btn) || typing(e)) return;
    e.preventDefault();
    if (e.repeat || keyHeld) return;
    keyHeld = true;
    active().down();
  };
  const onKeyUp = (e) => { if (keyHeld && isKey(e)) { e.preventDefault(); keyHeld = false; active().up(); } };
  const onBlur = () => { if (keyHeld) { keyHeld = false; active().up(); } };
  document.addEventListener('keydown', onKeyDown);
  document.addEventListener('keyup', onKeyUp);
  window.addEventListener('blur', onBlur);
  cleanups.push(() => { document.removeEventListener('keydown', onKeyDown); document.removeEventListener('keyup', onKeyUp); window.removeEventListener('blur', onBlur); });

  /* ----- tabs ----- */
  function setTab(v) {
    if (v === tab) return;
    // a talk going on ends with its tab (leaving the room ends a walkie talk on the server too)
    keyHeld = false;
    [walkie, message].forEach((c) => { c.holding = false; c.ctl.stop(); });
    tab = v;
    talkie.setRoom(tab === 'walkie');
    const want = `#/announce/${tab}`;
    if (location.hash !== want && location.hash.startsWith('#/announce')) history.replaceState(null, '', want);
    showTab();
    paint();
  }
  function showTab() {
    const w = tab === 'walkie';
    talkCard.hidden = !w; roomBox.hidden = !w;
    recBar.hidden = w; recent.hidden = w;
    node.dataset.tab = tab;
  }

  /* ----- painting ----- */
  const errText = (c) => ({ denied: () => t('tk.eDenied', location.host), http: () => t('tk.eHttp') }[c.st]
    || (c.st === 'error' && (() => t({ offline: 'tk.eOffline', dropped: 'tk.dropped', no_mic: 'tk.eNoMic', mic_failed: 'tk.eMic',
      unsupported: 'tk.eUnsup' }[c.info.code] || 'tk.eServer'))));
  let myCardStatus = null; // my card's status line, for the clock while I talk
  function paintClock() {
    status.hidden = walkie.st !== 'live';
    if (walkie.st === 'live') {
      const at = mmss((Date.now() - walkie.startAt) / 1000);
      status.textContent = `● ${t('tk.youLive', at)}`;
      if (myCardStatus) myCardStatus.textContent = `${t('tk.talking')} ${at}`;
    }
    if (message.st === 'live') recLabel.textContent = `● ${t('tk.recording', mmss((Date.now() - message.startAt) / 1000))}`;
  }
  function paint() {
    const s = lastState || {};
    const blocked = !!s.live;
    const touch = matchMedia('(pointer: coarse)').matches;
    const st = walkie.st;
    talkCard.dataset.state = blocked && st === 'idle' ? 'busy' : st;
    ptt.disabled = (blocked && st === 'idle') || st === 'sending' || st === 'asking' || (!s.connected && st === 'idle');
    ptt.setAttribute('aria-pressed', String(st === 'live' || st === 'opening'));
    const L = { live: 'tk.releaseW', opening: 'tk.opening', sending: 'tk.sending', asking: 'tk.asking' }[st];
    label.textContent = t(L || (blocked ? 'tk.busy' : !s.connected ? 'tk.connecting' : touch ? 'tk.hold' : 'tk.holdKbd'));
    const E = errText(walkie);
    errBox.hidden = !E;
    errBox.textContent = E ? E() : '';

    const ms = message.st;
    recBar.dataset.state = ms;
    rec.disabled = ms === 'sending' || ms === 'asking' || (!s.connected && ms === 'idle');
    rec.setAttribute('aria-pressed', String(ms === 'live' || ms === 'opening'));
    const R = { opening: 'tk.opening', sending: 'tk.sending', asking: 'tk.asking' }[ms];
    recLabel.textContent = t(R || (!s.connected && ms === 'idle' ? 'tk.connecting' : 'tk.rec'));
    recHelp.textContent = t(ms === 'live' ? 'tk.release' : 'tk.recHelp');
    const RE = errText(message);
    recErr.hidden = !RE;
    recErr.textContent = RE ? RE() : '';
    paintRoom(s);
    paintClock();
  }

  function paintBanner(s) {
    // the live audio is shown on the cards; this only asks for a tap when the browser blocked it
    banner.hidden = !(s.live && s.blocked && tab === 'walkie');
    if (banner.hidden) return;
    liveFace.replaceChildren(face(s.live));
    liveName.textContent = t('tk.isLive', s.live.name);
  }

  function paintTabs(s) {
    liveMark.hidden = !(s.live && tab !== 'walkie');
    const n = talkie.unread(s);
    unreadMark.hidden = !n;
    unreadMark.textContent = String(n);
    unreadMark.setAttribute('aria-label', t('tkg.unread', n));
  }

  /* ----- the room: me, the talker, the others in the room, then those who can't hear ----- */
  let expanded = false, roomSig = '';
  const phoneMq = matchMedia('(max-width: 743px)');
  const onMq = () => { roomSig = ''; paint(); };
  phoneMq.addEventListener('change', onMq);
  cleanups.push(() => phoneMq.removeEventListener('change', onMq));
  function paintRoom(s) {
    const me = s.me ?? ctx.user.id;
    const online = s.online || [];
    const mine = online.find((p) => p.id === me) || { id: me, name: ctx.user.display_name };
    // talking: me while I talk; someone else once their voice plays here (or right away when it can't play here)
    const talker = walkie.st === 'live' ? me
      : s.heard ? s.heard.user_id : s.live && (!s.hearing || s.blocked) ? s.live.user_id : null;
    const others = online.filter((p) => p.id !== me);
    const rank = (p) => (p.id === talker ? 0 : p.in_room ? 1 : 2);
    const people = [{ ...mine, in_room: true }, ...others.sort((a, b) => rank(a) - rank(b))];
    const cut = phoneMq.matches && !expanded && people.length > PHONE_CARDS ? PHONE_CARDS - 1 : people.length;
    const sig = JSON.stringify([people.map((p) => [p.id, p.name, p.in_room]), talker, cut]);
    if (sig === roomSig) return;
    roomSig = sig;
    roomCap.textContent = t('tk.room', people.filter((p) => p.in_room).length);
    myCardStatus = null;
    const cards = people.slice(0, cut).map((p) => {
      const isMe = p.id === me, talking = p.id === talker;
      const st = h('span', { class: 'small tw-pc-st' }, talking ? t('tk.talking') : p.in_room ? t('tk.listening') : t('tk.away'));
      if (isMe && talking) myCardStatus = st;
      const cls = ['tw-pc', talking && 'talking', isMe && 'me', !p.in_room && 'away'].filter(Boolean).join(' ');
      const who = isMe ? t('tk.you') : p.name;
      return h('div', { class: cls, role: 'listitem', 'aria-label': `${who}: ${st.textContent}`, dataset: { id: p.id } },
        h('span', { class: 'tw-pc-avw' }, face(p, 'tw-pc-av'), talking ? liveBars('tw-pc-bars') : null),
        h('strong', { class: 'tw-pc-n' }, isMe ? who : first(p.name)), st);
    });
    if (cut < people.length) {
      const n = people.length - cut;
      cards.push(h('div', { role: 'listitem', class: 'tw-pc-morew' },
        h('button', { type: 'button', class: 'tw-pc tw-pc-more', 'aria-label': t('tk.showAll', n), onclick: () => { expanded = true; roomSig = ''; paint(); } },
          h('span', { class: 'tw-pc-plus', 'aria-hidden': 'true' }, `+${n}`))));
    }
    grid.replaceChildren(...cards);
  }

  /* ----- voice messages ----- */
  const key = (id) => `tk:${id}`;
  const rows = new Map(); // clip id -> { wave }
  function paintList(s) {
    const clips = (s.clips || []).filter((c) => !isPending(key(c.id)));
    rows.clear();
    if (!clips.length) { list.replaceChildren(h('p', { class: 'small tw-empty' }, t('tk.empty'))); return; }
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
    // only the author deletes a message: the others get a spacer so the play buttons line up
    const more = mine ? ibtn('more', t('tk.more'), (e) => clipMenu(c, e.currentTarget), 'tw-more') : h('span', { class: 'tw-more-sp', 'aria-hidden': 'true' });
    const row = h('div', { class: 'tw-row', role: 'listitem', dataset: { id: c.id } }, face(c),
      h('div', { class: 'tw-row-tx' },
        h('div', { class: 'tw-row-top' }, h('strong', {}, who), h('span', { class: 'small' }, fmtRel(c.created_at)), unheard),
        h('div', { class: 'tw-row-wave' }, wave, h('span', { class: 'small tw-len' }, fmtDur(c.seconds)))),
      btn, more);
    rows.set(c.id, { wave });
    return row;
  }
  function progress(id, p) {
    const r = rows.get(id);
    if (!r) return;
    const n = p == null ? 0 : Math.round(p * WAVE_N);
    r.wave.childNodes.forEach((b, i) => b.classList.toggle('on', i < n));
  }
  function clipMenu(c, anchor) {
    const rows2 = (close) => h('div', { class: 'menu' },
      h('button', { type: 'button', class: 'mi danger', onclick: () => { close(); remove(c); } },
        h('span', { class: 'mic' }, glyph('trash', 'xs')), h('span', {}, t('tk.delete'))));
    if (isPhone()) ctx.sheet({ title: t('tk.more'), build: (body, sheet) => body.append(h('div', { class: 'list tb-menu' }, rows2(() => sheet.close()))) });
    else ctx.popover({ anchor, label: t('tk.more'), className: 'tb-pop', build: (el, close) => el.append(rows2(close)) });
  }
  /** Gone at once; the DELETE goes when the Undo has had its time (media-kit's deleteLater). */
  function remove(c) {
    if (talkie.snapshot().playing === c.id) talkie.stopClip();
    deleteLater(key(c.id), `/talkie/clips/${encodeURIComponent(c.id)}`, {
      ms: UNDO_MS,
      onError: (e) => { ctx.fail(e); if (node.isConnected && lastState) paintList(lastState); },
    });
    if (lastState) paintList(lastState);
    ctx.toast(t('tk.deleted'), 'info', { ms: UNDO_MS, action: { label: t('tk.undo'), run: () => { if (undoDelete(key(c.id)) && node.isConnected && lastState) paintList(lastState); } } });
  }

  function onTalkie(s) {
    const listChanged = !lastState || ['clips', 'playing', 'me', 'playedRev'].some((k) => lastState[k] !== s[k]);
    lastState = { ...s };
    paintBanner(s);
    paintTabs(s);
    if (listChanged) paintList(s);
    paint();
  }
  cleanups.push(talkie.onChange(onTalkie));
  // relative times ("2 min ago") move on: once a minute is plenty
  const relTimer = setInterval(() => { if (lastState) paintList(lastState); }, 60000);
  cleanups.push(() => clearInterval(relTimer));
  talkie.setRoom(tab === 'walkie');
  cleanups.push(() => talkie.setRoom(false));
  showTab();
  onTalkie(talkie.snapshot());

  return {
    node,
    destroy() { clearInterval(timer); walkie.ctl.destroy(); message.ctl.destroy(); cleanups.forEach((f) => f()); },
  };
}
