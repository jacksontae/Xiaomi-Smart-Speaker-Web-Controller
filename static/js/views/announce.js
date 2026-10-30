// Announce (boards Announce / T_Announce / D_Announce): "Announce now" (text to speech with language, optional
// volume and quick phrases) and "Talk live" (browser mic streamed to the speaker, see ../a-talk.js).
// "Schedule" is a link to #/schedule (its own page). #/announce/talk opens Talk live directly.
// Talk live only shows when the server offers it (GET /talk/status -> { available: true }) and for operators.
import { h, icon, iconBtn, field, segmented, busy } from '../ui.js';
import { register, t, lang as appLang } from '../i18n.js';
import { isPhone } from '../sheet.js';
import { aicon } from '../a-icons.js';
import { liveTalk, micPermission, askMic, micAllowedHere } from '../a-talk.js';
import { modeSwitch } from '../a-modeswitch.js';

register({
  en: {
    'ann.talk': 'Talk live',
    'ann.textLabel': 'Text to announce',
    'ann.textPh': 'Type a message, e.g. Meeting in 5 minutes, please come to the main room',
    'ann.textPhShort': 'Type a message, e.g. Meeting in 5 minutes',
    'ann.emptyErr': 'Type a message first, or tap a quick phrase below.',
    'ann.emptyErrWide': 'Type a message first, or click a quick phrase on the right.',
    'ann.langAria': 'Announcement language',
    'ann.cta': 'Announce', 'ann.ctaBusy': 'Announcing…',
    'ann.volume': 'Volume', 'ann.volCurrent': 'Same as now', 'ann.volReset': 'Use the current volume',
    'ann.volHint': 'Only for this announcement. The speaker goes back to its volume afterwards.',
    'ann.said': (x) => `Announced “${x}”`,
    'ann.saidResume': (x, y) => `Announced “${x}”. “${y}” picks up again afterwards.`,
    'ann.quick': 'Quick phrases', 'ann.edit': 'Edit', 'ann.done': 'Done', 'ann.addPhrase': 'Add phrase',
    'ann.newPhrase': 'New phrase', 'ann.newPhrasePh': 'e.g. Closing in 15 minutes', 'ann.add': 'Add',
    'ann.hintIdle': 'Tap a phrase to announce it right away', 'ann.hintIdleWide': 'Click a phrase to announce it right away',
    'ann.hintEdit': 'Tap × to delete a phrase', 'ann.hintEditWide': 'Click × to delete a phrase',
    'ann.hintView': 'Phrases your team saved',
    'ann.noPhrases': 'No quick phrases yet.',
    'ann.sayAria': (x) => `Announce ${x}`, 'ann.delAria': (x) => `Delete ${x}`,
    'ann.deleted': (x) => `Deleted “${x}”`, 'ann.undo': 'Undo',
    'ann.viewer': 'Your account is a Viewer, so you can see the phrases but not announce. Ask the owner to change your role.',
    // live talk
    'talk.pReady': 'Ready', 'talk.pConnecting': 'Connecting…', 'talk.pLive': 'On air', 'talk.pEnding': 'Ending…',
    'talk.pBlocked': 'Mic blocked', 'talk.pError': 'Not connected', 'talk.pAsking': 'Waiting for permission',
    'talk.holdToTalk': 'Hold to talk', 'talk.holdSub': 'Slide up to lock and talk hands-free',
    'talk.clickToTalk': 'Click to talk', 'talk.clickSub': 'Click again when you’re done. People hear you about 2⁠–⁠5 seconds later.',
    'talk.connecting': 'Connecting to the speaker…', 'talk.connectingSub': 'Music pauses first',
    'talk.releaseToEnd': 'Release to end', 'talk.tapToEnd': 'Tap to end', 'talk.clickToEnd': 'Click to end',
    'talk.liveSub': 'People will hear you about 2⁠–⁠5 seconds later.',
    'talk.ending': 'Ending…', 'talk.endingSub': 'The music picks up again in a moment',
    'talk.askingLbl': 'Allow the microphone to talk', 'talk.askingSub': 'Your browser is asking',
    'talk.micStartHold': 'Talk live. Hold to talk, or tap to start', 'talk.micStart': 'Start talking live', 'talk.micStop': 'End live talk',
    'talk.slideLock': 'Slide up to lock', 'talk.handsFree': 'Hands-free, tap to end',
    'talk.kbdPre': 'Press', 'talk.kbdStart': 'to start talking', 'talk.kbdEnd': 'to end',
    'talk.level': 'Mic level', 'talk.timerAria': (x) => `On air for ${x}`,
    'talk.chime': 'Chime before and after', 'talk.chimeHelp': 'A short tone so people know to listen',
    'talk.musicRow': 'Music pauses while you talk', 'talk.musicHelp': 'It picks up again afterwards, like after an announcement',
    'talk.noBack': 'The speaker can’t send sound back', 'talk.noBackHelp': 'You won’t hear people near the speaker',
    'talk.twoWay': 'Two-way talk', 'talk.twoWaySub': 'Needs extra hardware',
    'talk.twoWayBody': 'Two-way talk needs an add-on mic (ESP32 + microphone) next to the speaker. The speaker’s own microphone can’t be used by other apps.',
    'talk.later': 'Coming later',
    'talk.deniedTitle': 'The microphone is blocked',
    'talk.deniedBody': (host) => `To talk live, allow the microphone for ${host} in your browser, then try again.`,
    'talk.howAllow': 'How to allow', 'talk.tryAgain': 'Try again', 'talk.howTitle': 'Allow the microphone',
    'talk.howIos': ['In Safari, tap aA on the left of the address bar.', 'Tap Website Settings.', 'Set Microphone to Allow.', 'Come back here and tap Try again.'],
    'talk.howIosHome': 'Opened the app from your Home Screen? Open the Settings app, find Safari, then Microphone.',
    'talk.howDesk': ['Click the site settings icon to the left of the address bar.', 'Find Microphone and switch it on, or set it to Allow.', 'Come back here and click Try again. No need to reload.'],
    'talk.howDeskOther': (host) => `Using Safari on a Mac? Choose Safari > Settings for ${host}, then set Microphone to Allow.`,
    'talk.httpTitle': 'Talk live needs the secure address',
    'talk.httpBody': (url) => `Browsers only let a page use the microphone over https. This page is open at ${url}.`,
    'talk.openSecure': (url) => `Open ${url}`,
    'talk.askOwner': 'Ask the owner for the https address of this app.',
    'talk.errTitle': 'Speaker didn’t respond', 'talk.errBody': 'Nothing went out. Check that the speaker is on and online, then try again.',
    'talk.offlineHelp': 'Speaker offline?',
    'talk.busyTitle': 'Someone else is talking', 'talk.busyBody': 'Wait until they finish, then try again.',
    'talk.noMicTitle': 'No microphone found', 'talk.noMicBody': 'Plug in or turn on a microphone, then try again.',
    'talk.micFailTitle': 'The microphone didn’t start', 'talk.micFailBody': 'Close other apps that use the microphone, then try again.',
    'talk.unsupTitle': 'This browser can’t record audio', 'talk.unsupBody': 'Open the app in a current version of Safari, Chrome or Firefox.',
    'talk.unavailTitle': 'Talk live is off right now', 'talk.unavailBody': 'The server can’t take a live talk at the moment. Try an announcement instead.',
    'talk.talked': (x) => `Talked live for ${x}`,
    'talk.endMax': (x) => `Talked live for ${x}. That’s the longest one talk can be.`,
    'talk.endIdle': (x) => `Talked live for ${x}. It stopped because the mic went quiet.`,
    'talk.endInterrupted': (x) => `Talked live for ${x}. Something else started playing on the speaker.`,
    'talk.endDropped': 'The connection dropped, so the live talk ended.',
    'talk.holdLonger': 'Keep holding the button while you talk',
    'talk.cancelled': 'Cancelled. Nothing went out.',
    'talk.micAllowed': 'Microphone allowed. Hold the button to talk.',
  },
  th: {
    'ann.talk': 'พูดสด',
    'ann.textLabel': 'ข้อความที่จะประกาศ',
    'ann.textPh': 'พิมพ์ข้อความ เช่น ประชุมใน 5 นาที เชิญที่ห้องประชุมใหญ่',
    'ann.textPhShort': 'พิมพ์ข้อความ เช่น ประชุมใน 5 นาที',
    'ann.emptyErr': 'พิมพ์ข้อความก่อน หรือแตะประโยคด่วนด้านล่าง',
    'ann.emptyErrWide': 'พิมพ์ข้อความก่อน หรือคลิกประโยคด่วนทางขวา',
    'ann.langAria': 'ภาษาที่ใช้ประกาศ',
    'ann.cta': 'ประกาศ', 'ann.ctaBusy': 'กำลังประกาศ…',
    'ann.volume': 'ระดับเสียง', 'ann.volCurrent': 'เท่าที่ตั้งอยู่', 'ann.volReset': 'ใช้ระดับเสียงปัจจุบัน',
    'ann.volHint': 'ใช้เฉพาะประกาศนี้ ประกาศจบแล้วลำโพงกลับไปใช้ระดับเสียงเดิม',
    'ann.said': (x) => `ประกาศแล้ว “${x}”`,
    'ann.saidResume': (x, y) => `ประกาศแล้ว “${x}” จากนั้น “${y}” จะเล่นต่อ`,
    'ann.quick': 'ประโยคด่วน', 'ann.edit': 'แก้ไข', 'ann.done': 'เสร็จ', 'ann.addPhrase': 'เพิ่มประโยค',
    'ann.newPhrase': 'ประโยคใหม่', 'ann.newPhrasePh': 'เช่น ปิดร้านใน 15 นาที', 'ann.add': 'เพิ่ม',
    'ann.hintIdle': 'แตะประโยคเพื่อประกาศทันที', 'ann.hintIdleWide': 'คลิกประโยคเพื่อประกาศทันที',
    'ann.hintEdit': 'แตะ × เพื่อลบประโยค', 'ann.hintEditWide': 'คลิก × เพื่อลบประโยค',
    'ann.hintView': 'ประโยคที่ทีมบันทึกไว้',
    'ann.noPhrases': 'ยังไม่มีประโยคด่วน',
    'ann.sayAria': (x) => `ประกาศ ${x}`, 'ann.delAria': (x) => `ลบ ${x}`,
    'ann.deleted': (x) => `ลบ “${x}” แล้ว`, 'ann.undo': 'เลิกทำ',
    'ann.viewer': 'บัญชีนี้เป็นผู้ชม ดูประโยคด่วนได้แต่ประกาศไม่ได้ ขอให้เจ้าของปรับสิทธิ์ให้',
    'talk.pReady': 'พร้อม', 'talk.pConnecting': 'กำลังเชื่อมต่อ…', 'talk.pLive': 'ออกอากาศ', 'talk.pEnding': 'กำลังจบ…',
    'talk.pBlocked': 'ไมค์ถูกปิดกั้น', 'talk.pError': 'เชื่อมต่อไม่ได้', 'talk.pAsking': 'รอการอนุญาต',
    'talk.holdToTalk': 'กดค้างเพื่อพูด', 'talk.holdSub': 'เลื่อนขึ้นเพื่อล็อก แล้วพูดได้โดยไม่ต้องกดค้าง',
    'talk.clickToTalk': 'คลิกเพื่อพูด', 'talk.clickSub': 'คลิกอีกครั้งเมื่อพูดจบ คนที่ข้างลำโพงจะได้ยินช้ากว่าประมาณ 2⁠–⁠5 วินาที',
    'talk.connecting': 'กำลังเชื่อมต่อลำโพง…', 'talk.connectingSub': 'เพลงจะพักก่อน',
    'talk.releaseToEnd': 'ปล่อยนิ้วเพื่อจบ', 'talk.tapToEnd': 'แตะเพื่อจบ', 'talk.clickToEnd': 'คลิกเพื่อจบ',
    'talk.liveSub': 'คนที่ข้างลำโพงจะได้ยินช้ากว่าประมาณ 2⁠–⁠5 วินาที',
    'talk.ending': 'กำลังจบ…', 'talk.endingSub': 'เพลงจะเล่นต่อในอีกครู่เดียว',
    'talk.askingLbl': 'อนุญาตไมโครโฟนเพื่อพูด', 'talk.askingSub': 'เบราว์เซอร์กำลังถาม',
    'talk.micStartHold': 'พูดสด กดค้างเพื่อพูด หรือแตะเพื่อเริ่ม', 'talk.micStart': 'เริ่มพูดสด', 'talk.micStop': 'จบการพูดสด',
    'talk.slideLock': 'เลื่อนขึ้นเพื่อล็อก', 'talk.handsFree': 'ไม่ต้องกดค้าง แตะเพื่อจบ',
    'talk.kbdPre': 'กด', 'talk.kbdStart': 'เพื่อเริ่มพูด', 'talk.kbdEnd': 'เพื่อจบ',
    'talk.level': 'ระดับเสียงไมค์', 'talk.timerAria': (x) => `ออกอากาศมา ${x}`,
    'talk.chime': 'เสียงสัญญาณก่อนและหลังพูด', 'talk.chimeHelp': 'เสียงสั้น ๆ ให้คนรู้ว่ากำลังจะมีคนพูด',
    'talk.musicRow': 'เพลงจะพักระหว่างพูด', 'talk.musicHelp': 'แล้วเล่นต่อเมื่อพูดจบ เหมือนหลังประกาศ',
    'talk.noBack': 'ลำโพงส่งเสียงกลับมาไม่ได้', 'talk.noBackHelp': 'คุณจะไม่ได้ยินคนที่อยู่ข้างลำโพง',
    'talk.twoWay': 'คุยสองทาง', 'talk.twoWaySub': 'ต้องมีอุปกรณ์เสริม',
    'talk.twoWayBody': 'ถ้าจะคุยสองทาง ต้องมีไมค์เสริม (ESP32 + ไมโครโฟน) วางไว้ข้างลำโพง ไมค์ในตัวลำโพงไม่เปิดให้แอปอื่นใช้',
    'talk.later': 'จะมาในภายหลัง',
    'talk.deniedTitle': 'ไมโครโฟนถูกปิดกั้น',
    'talk.deniedBody': (host) => `ถ้าจะพูดสด ให้อนุญาตให้ ${host} ใช้ไมโครโฟนในเบราว์เซอร์ แล้วลองอีกครั้ง`,
    'talk.howAllow': 'วิธีอนุญาต', 'talk.tryAgain': 'ลองอีกครั้ง', 'talk.howTitle': 'อนุญาตไมโครโฟน',
    'talk.howIos': ['ใน Safari แตะ aA ทางซ้ายของช่องที่อยู่เว็บ', 'แตะ การตั้งค่าเว็บไซต์', 'ตั้ง ไมโครโฟน เป็น อนุญาต', 'กลับมาที่หน้านี้ แล้วแตะ ลองอีกครั้ง'],
    'talk.howIosHome': 'ถ้าเปิดแอปจากไอคอนบนหน้าจอโฮม ให้เปิดแอปตั้งค่า หา Safari แล้วแตะ ไมโครโฟน',
    'talk.howDesk': ['คลิกไอคอนการตั้งค่าเว็บไซต์ทางซ้ายของช่องที่อยู่เว็บ', 'หา ไมโครโฟน แล้วเปิด หรือตั้งเป็น อนุญาต', 'กลับมาที่หน้านี้ แล้วคลิก ลองอีกครั้ง ไม่ต้องโหลดหน้าใหม่'],
    'talk.howDeskOther': (host) => `ถ้าใช้ Safari บน Mac เลือกเมนู Safari > การตั้งค่าสำหรับ ${host} แล้วตั้ง ไมโครโฟน เป็น อนุญาต`,
    'talk.httpTitle': 'พูดสดต้องใช้ที่อยู่ที่ปลอดภัย',
    'talk.httpBody': (url) => `เบราว์เซอร์ให้หน้าเว็บใช้ไมโครโฟนได้เฉพาะแบบ https ตอนนี้หน้านี้เปิดอยู่ที่ ${url}`,
    'talk.openSecure': (url) => `เปิด ${url}`,
    'talk.askOwner': 'ขอที่อยู่แบบ https ของแอปนี้จากเจ้าของ',
    'talk.errTitle': 'ลำโพงไม่ตอบ', 'talk.errBody': 'ยังไม่มีเสียงออกไป ตรวจว่าลำโพงเปิดอยู่และออนไลน์ แล้วลองอีกครั้ง',
    'talk.offlineHelp': 'ลำโพงออฟไลน์?',
    'talk.busyTitle': 'มีคนอื่นพูดอยู่', 'talk.busyBody': 'รอให้พูดจบก่อน แล้วลองอีกครั้ง',
    'talk.noMicTitle': 'ไม่พบไมโครโฟน', 'talk.noMicBody': 'เสียบหรือเปิดไมโครโฟน แล้วลองอีกครั้ง',
    'talk.micFailTitle': 'เปิดไมโครโฟนไม่ได้', 'talk.micFailBody': 'ปิดแอปอื่นที่ใช้ไมโครโฟนอยู่ แล้วลองอีกครั้ง',
    'talk.unsupTitle': 'เบราว์เซอร์นี้อัดเสียงไม่ได้', 'talk.unsupBody': 'เปิดแอปด้วย Safari, Chrome หรือ Firefox รุ่นใหม่',
    'talk.unavailTitle': 'ตอนนี้พูดสดไม่ได้', 'talk.unavailBody': 'เซิร์ฟเวอร์ยังรับการพูดสดไม่ได้ในตอนนี้ ลองใช้ประกาศแทน',
    'talk.talked': (x) => `พูดสดไป ${x}`,
    'talk.endMax': (x) => `พูดสดไป ${x} ครบเวลาสูงสุดของการพูดหนึ่งครั้งแล้ว`,
    'talk.endIdle': (x) => `พูดสดไป ${x} หยุดเองเพราะไมค์เงียบไปนาน`,
    'talk.endInterrupted': (x) => `พูดสดไป ${x} มีรายการอื่นเริ่มเล่นที่ลำโพง`,
    'talk.endDropped': 'การเชื่อมต่อหลุด การพูดสดจึงจบลง',
    'talk.holdLonger': 'กดปุ่มค้างไว้ตลอดที่พูด',
    'talk.cancelled': 'ยกเลิกแล้ว ไม่มีเสียงออกไป',
    'talk.micAllowed': 'อนุญาตไมโครโฟนแล้ว กดปุ่มค้างไว้เพื่อพูด',
  },
});

const MAX = 1000;
const LANGS = [{ value: 'th', label: 'ไทย', lang: 'th' }, { value: 'en', label: 'English', lang: 'en' }, { value: 'ja', label: '日本語', lang: 'ja' }];
const LANG_TAG = { th: 'TH', en: 'EN', ja: 'JA' };
const WAVE_N = 24;
const LOCK_PX = 56;
const LANG_KEY = 'spk.annLang';
const CHIME_KEY = 'spk.talkChime';
const read = (k) => { try { return localStorage.getItem(k); } catch { return null; } };
const write = (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } };
const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const wideMq = matchMedia('(min-width: 1280px)');
const coarse = () => matchMedia('(pointer: coarse)').matches;
const isIos = () => /iP(hone|ad|od)/.test(navigator.userAgent) || (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1);

export async function render(ctx) {
  await Promise.all([ctx.css('views/announce.css'), ctx.css('views/a-modeswitch.css')]);
  const op = ctx.can('operator');
  let mode = 'say';
  let talkAvail = false;
  let talkInfo = null; // GET /talk/status body

  /* ---------- mode switch: Announce now | Talk live | Schedule (shared with the Schedule page) ---------- */
  const sw = modeSwitch(ctx, {
    current: 'say',
    onPick: (m) => { if (m === 'schedule') return false; setMode(m); return true; },
    onTalk: (info) => {
      talkInfo = info;
      talkAvail = sw.talkAvailable();
      if (talkAvail && ctx.params[0] === 'talk' && mode !== 'talk') setMode('talk');
      if (!talkAvail && mode === 'talk') setMode('say');
      if (talkUi) talkUi.repaint();
    },
  });

  const mainCol = h('div', { class: 'ann-main' });
  const sideCol = h('div', { class: 'ann-side' });
  const node = h('div', { class: 'page ann-page' }, ctx.header({ title: t('nav.announce'), actions: sw.headActs }), sw.slot,
    h('div', { class: 'ann-grid' }, mainCol, sideCol));

  /* ================= Announce now ================= */
  const say = buildSay();
  const phrases = buildPhrases();

  function buildSay() {
    if (!op) return null;
    let lng = read(LANG_KEY) || (ctx.status && ctx.status.tts_lang) || 'th';
    const opts = LANGS.some((l) => l.value === lng) ? LANGS : [...LANGS, { value: lng, label: lng }];
    const text = h('textarea', { class: 'input ann-text', rows: 4, maxLength: MAX, placeholder: t(wideMq.matches ? 'ann.textPhShort' : 'ann.textPh') });
    const err = h('p', { class: 'form-error', role: 'alert' });
    const count = h('span', { class: 'ann-count', 'aria-hidden': 'true' }, `0/${MAX}`);
    const langSeg = segmented({ options: opts, value: lng, label: t('ann.langAria'), cls: 'ann-lang', onChange: (v) => { lng = v; write(LANG_KEY, v); } });
    const btn = h('button', { type: 'submit', class: 'btn primary big ann-cta' }, icon('announce', 'sm'), h('span', {}, t('ann.cta')));

    // optional volume just for this announcement (POST /say volume); untouched = the speaker's current volume
    let vol = null;
    const volOut = h('output', { class: 'ann-volout' }, t('ann.volCurrent'));
    const volIn = h('input', { class: 'ann-range', type: 'range', min: '0', max: '100', step: '5', value: '50', 'aria-label': t('ann.volume') });
    const volReset = iconBtn('refresh', t('ann.volReset'), () => setVol(null), 'ann-volreset');
    function setVol(v) {
      vol = v;
      volReset.hidden = v == null;
      volHint.hidden = v == null;
      volOut.textContent = v == null ? t('ann.volCurrent') : `${v}%`;
      const shown = v == null ? Math.round(((ctx.status && ctx.status.volume) || 0.5) * 100) : v;
      volIn.value = String(shown);
      volIn.style.setProperty('--p', `${shown}%`);
      volIn.classList.toggle('unset', v == null);
      volIn.setAttribute('aria-valuetext', v == null ? t('ann.volCurrent') : `${v}%`);
    }
    volIn.addEventListener('input', () => setVol(+volIn.value));
    const volRow = h('div', { class: 'ann-vol' }, h('span', { class: 'ann-vollbl', 'aria-hidden': 'true' }, aicon('vol-low', 'sm'), t('ann.volume')), volIn, volOut, volReset);
    // the hint is page text (shown once a volume is picked), not a hover label: touch has no hover
    const volHint = h('p', { class: 'small ann-volhint', id: `avh${Date.now().toString(36)}`, hidden: true }, t('ann.volHint'));
    volIn.setAttribute('aria-describedby', volHint.id);
    setVol(null);

    text.addEventListener('input', () => {
      count.textContent = `${text.value.length}/${MAX}`;
      if (err.textContent) { err.textContent = ''; text.removeAttribute('aria-invalid'); }
    });
    const form = h('form', {
      class: 'ann-card', novalidate: true,
      onsubmit: async (e) => {
        e.preventDefault();
        const v = text.value.trim();
        if (!v) {
          err.textContent = t(wideMq.matches ? 'ann.emptyErrWide' : 'ann.emptyErr');
          text.setAttribute('aria-invalid', 'true');
          text.focus();
          return;
        }
        btn.lastChild.textContent = t('ann.ctaBusy');
        const ok = await speak(v, lng, btn);
        btn.lastChild.textContent = t('ann.cta');
        if (ok) { text.value = ''; count.textContent = `0/${MAX}`; }
      },
    },
    field(t('ann.textLabel'), text), err,
    h('div', { class: 'ann-foot' }, langSeg, count, btn),
    volRow, volHint);
    return { form, lang: () => lng, volume: () => (vol == null ? null : vol / 100), setLangFromStatus(l) { if (!read(LANG_KEY) && l && opts.some((o) => o.value === l)) { lng = l; langSeg.setValue(l); } } };
  }

  async function speak(text, lng, btn) {
    return busy(btn, async () => {
      try {
        const body = { text, lang: lng };
        const v = say && say.volume();
        if (v != null) body.volume = v;
        const r = await ctx.api('/say', { body });
        const short = text.length > 60 ? `${text.slice(0, 57)}…` : text;
        ctx.toast(r && r.will_resume ? t('ann.saidResume', short, r.will_resume) : t('ann.said', short), 'ok');
        ctx.refreshStatus();
        return true;
      } catch (e) { ctx.fail(e); return false; }
    });
  }

  function buildPhrases() {
    let list = [];
    let editing = false;
    let adding = false;
    const editBtn = h('button', { type: 'button', class: 'linkbtn ann-edit', 'aria-pressed': 'false', hidden: true, onclick: () => { editing = !editing; adding = false; draw(); } }, t('ann.edit'));
    const chips = h('div', { class: 'ann-chips', role: 'list' });
    const hint = h('p', { class: 'small ann-hint' });
    const box = h('section', { class: 'ann-phrases', 'aria-labelledby': 'ann-ph' },
      h('div', { class: 'ann-phead' }, h('h2', { id: 'ann-ph' }, t('ann.quick')), op ? editBtn : null), chips, hint);
    const wide = () => !coarse();

    function draw() {
      editBtn.hidden = !op || !list.length;
      editBtn.textContent = t(editing ? 'ann.done' : 'ann.edit');
      editBtn.setAttribute('aria-pressed', String(editing));
      const def = (ctx.status && ctx.status.tts_lang) || 'th';
      const items = list.map((p) => {
        const tag = p.lang && p.lang !== def ? h('span', { class: 'ann-tag', lang: 'en' }, LANG_TAG[p.lang] || p.lang.toUpperCase()) : null;
        const label = h('span', { class: 'ann-ctx', lang: p.lang || null }, p.text);
        let chip;
        if (op && !editing) {
          chip = h('button', { type: 'button', class: 'ann-chip', 'aria-label': t('ann.sayAria', p.text), onclick: () => speak(p.text, p.lang, chip) }, label, tag);
        } else {
          chip = h('span', { class: 'ann-chip static' }, label, tag);
        }
        const del = editing ? h('button', { type: 'button', class: 'ann-del', 'aria-label': t('ann.delAria', p.text), onclick: () => remove(p) }, icon('close', 'xs')) : null;
        return h('div', { role: 'listitem', class: `ann-chipw${editing ? ' editing' : ''}` }, chip, del);
      });
      if (op && !editing) items.push(adding ? addForm() : h('div', { role: 'listitem' }, h('button', { type: 'button', class: 'ann-chip add', onclick: () => { adding = true; draw(); } }, icon('plus', 'xs'), t('ann.addPhrase'))));
      if (!list.length && !op) items.push(h('p', { class: 'small' }, t('ann.noPhrases')));
      chips.replaceChildren(...items);
      hint.textContent = !op ? (list.length ? t('ann.hintView') : '') : !list.length ? t('ann.noPhrases')
        : editing ? t(wide() ? 'ann.hintEditWide' : 'ann.hintEdit') : t(wide() ? 'ann.hintIdleWide' : 'ann.hintIdle');
      const inp = chips.querySelector('input');
      if (inp) inp.focus();
    }
    function addForm() {
      const inp = h('input', { class: 'input ann-newin', maxLength: MAX, placeholder: t('ann.newPhrasePh'), 'aria-label': t('ann.newPhrase') });
      const ok = h('button', { type: 'submit', class: 'btn primary' }, t('ann.add'));
      const f = h('form', {
        class: 'ann-addform', role: 'listitem',
        onsubmit: async (e) => {
          e.preventDefault();
          const v = inp.value.trim();
          if (!v) { adding = false; draw(); return; }
          await busy(ok, async () => {
            try {
              const p = await ctx.api('/phrases', { body: { text: v, lang: say ? say.lang() : undefined } });
              list.push(p);
              adding = false;
              draw();
            } catch (e2) { ctx.fail(e2); }
          });
        },
      }, inp, ok, h('button', { type: 'button', class: 'btn quiet', onclick: () => { adding = false; draw(); } }, t('common.cancel')));
      inp.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); adding = false; draw(); } });
      return f;
    }
    async function remove(p) {
      try { await ctx.api(`/phrases/${p.id}`, { method: 'DELETE' }); } catch (e) { ctx.fail(e); return; }
      list = list.filter((x) => x.id !== p.id);
      if (!list.length) editing = false;
      draw();
      ctx.toast(t('ann.deleted', p.text.length > 30 ? `${p.text.slice(0, 28)}…` : p.text), 'ok', {
        ms: 6000,
        action: { label: t('ann.undo'), run: async () => {
          try { list.push(await ctx.api('/phrases', { body: { text: p.text, lang: p.lang } })); draw(); } catch (e) { ctx.fail(e); }
        } },
      });
    }
    ctx.api('/phrases', { signal: ctx.signal }).then((r) => { list = r || []; draw(); }).catch((e) => { ctx.fail(e); draw(); });
    return { box, redraw: draw };
  }

  /* ================= Talk live ================= */
  let talkUi = null;
  function buildTalk() {
    let state = 'idle';
    let info = {};
    let locked = false, holding = false, hold = null, suppressClick = 0;
    let startAt = 0, timerT = 0, waveT = 0, level = 0, endingSecs = 0;
    let chime = read(CHIME_KEY) !== 'off';
    let twoWay = false;
    const wave = Array.from({ length: WAVE_N }, () => 0.06);
    const talk = liveTalk({
      onState: (s, i) => { onTalkState(s, i); },
      onLevel: (v) => { level = v; meterFill.style.width = `${Math.round(v * 100)}%`; meterFill.dataset.l = v > 0.85 ? 'hot' : v > 0.6 ? 'warm' : ''; meter.setAttribute('aria-valuenow', String(Math.round(v * 100))); },
    });

    // ----- card -----
    const pill = h('span', { class: 'tk-pill' }, h('span', { class: 'tk-dot', 'aria-hidden': 'true' }), h('span', {}));
    const timer = h('span', { class: 'tk-timer', hidden: true });
    const waveEl = h('div', { class: 'tk-wave', 'aria-hidden': 'true' }, wave.map(() => h('span')));
    const meterFill = h('span');
    const meter = h('div', { class: 'tk-meter', role: 'meter', 'aria-label': t('talk.level'), 'aria-valuemin': '0', 'aria-valuemax': '100', 'aria-valuenow': '0' }, meterFill);
    const lockSlot = h('div', { class: 'tk-lockslot' });
    const ring = h('span', { class: 'tk-ring', 'aria-hidden': 'true' });
    const ptt = h('button', { type: 'button', class: 'tk-ptt', 'aria-pressed': 'false', 'aria-describedby': 'tk-lbl' }, ring, aicon('mic'));
    const lbl = h('span', { class: 'tk-lbl', role: 'status' });
    const sub = h('span', { class: 'small tk-sub' });
    const kbd = h('p', { class: 'small tk-kbd' });
    const stage = h('div', { class: 'tk-stage' }, waveEl,
      h('div', { class: 'tk-levelrow' }, h('span', { class: 'small' }, t('talk.level')), meter),
      lockSlot, ptt, h('div', { id: 'tk-lbl', class: 'tk-lblbox' }, lbl, sub), kbd);
    const msg = h('div', { class: 'tk-msg', hidden: true });
    const card = h('section', { class: 'ann-card tk-card', 'aria-labelledby': 'tk-h' },
      h('h2', { id: 'tk-h', class: 'sr-only' }, t('ann.talk')),
      h('div', { class: 'tk-top' }, pill, timer), stage, msg);

    // ----- options -----
    const chimeSw = h('input', { type: 'checkbox', class: 'switch', role: 'switch', checked: chime, 'aria-label': t('talk.chime') });
    chimeSw.addEventListener('change', () => { chime = chimeSw.checked; write(CHIME_KEY, chime ? 'on' : 'off'); });
    const line = (title, help, extra) => [h('span', { class: 'tk-ltx' }, h('span', { class: 'tk-lt' }, title), h('span', { class: 'small' }, help)), extra];
    const musicHref = ctx.can('admin') ? '#/settings' : '#/help/queue';
    const twoBody = h('div', { class: 'tk-twobody', id: 'tk-two', hidden: true },
      h('p', { class: 'small' }, t('talk.twoWayBody')), h('p', { class: 'tk-later' }, aicon('clock', 'xs'), t('talk.later')));
    const twoBtn = h('button', { type: 'button', class: 'tk-line tk-twobtn', 'aria-expanded': 'false', 'aria-controls': 'tk-two',
      onclick: () => { twoWay = !twoWay; twoBtn.setAttribute('aria-expanded', String(twoWay)); twoBody.hidden = !twoWay; } },
    line(t('talk.twoWay'), t('talk.twoWaySub'), icon('chev-right', 'sm tk-chev')));
    const options = h('div', { class: 'tk-opts' },
      h('div', { class: 'tk-group' },
        h('label', { class: 'tk-line' }, line(t('talk.chime'), t('talk.chimeHelp'), chimeSw)),
        h('a', { class: 'tk-line', href: musicHref }, line(t('talk.musicRow'), t('talk.musicHelp'), icon('chev-right', 'sm tk-chev'))),
        h('a', { class: 'tk-line', href: '#/help/talk' }, line(t('talk.noBack'), t('talk.noBackHelp'), icon('chev-right', 'sm tk-chev')))),
      h('div', { class: 'tk-group' }, twoBtn, twoBody));

    // ----- input: touch/pen = hold (slide up to lock); mouse/keyboard = click to toggle; Space toggles -----
    ptt.addEventListener('pointerdown', (e) => {
      if (e.pointerType === 'mouse') return;
      if (e.cancelable) e.preventDefault();
      suppressClick = performance.now() + 700;
      if (['live', 'connecting', 'asking'].includes(state)) { hold = null; end('tap'); return; }
      if (!['idle', 'error'].includes(state)) return;
      hold = { id: e.pointerId, y0: e.clientY };
      try { ptt.setPointerCapture(e.pointerId); } catch { /* ignore */ }
      begin('hold');
    });
    ptt.addEventListener('pointermove', (e) => {
      if (!hold || e.pointerId !== hold.id || locked) return;
      if (hold.y0 - e.clientY > LOCK_PX && (state === 'live' || state === 'connecting')) { hold = null; locked = true; holding = false; paint(); }
    });
    const up = (e) => {
      if (!hold || e.pointerId !== hold.id) return;
      hold = null;
      suppressClick = performance.now() + 700;
      if (!locked) end('release');
    };
    ptt.addEventListener('pointerup', up);
    ptt.addEventListener('pointercancel', up);
    ptt.addEventListener('contextmenu', (e) => e.preventDefault());
    ptt.addEventListener('click', () => {
      if (performance.now() < suppressClick) return;
      if (['live', 'connecting', 'asking'].includes(state)) end('tap');
      else if (['idle', 'error'].includes(state)) begin('tap');
    });
    const onKey = (e) => {
      if (mode !== 'talk' || (e.code !== 'Space' && e.key !== ' ')) return;
      const tg = e.target;
      if (tg && tg.closest && tg.closest('input,textarea,select,button,a,[contenteditable],dialog')) return;
      if (document.querySelector('dialog[open]')) return;
      e.preventDefault();
      if (e.repeat) return;
      if (['live', 'connecting', 'asking'].includes(state)) end('tap');
      else if (['idle', 'error'].includes(state)) begin('tap');
    };
    document.addEventListener('keydown', onKey);

    async function begin(via) {
      locked = via !== 'hold';
      holding = via === 'hold';
      if (via === 'hold' && micAllowedHere() && (await micPermission()) === 'prompt') {
        // the finger has to leave the button to answer the browser, so only ask now
        hold = null; holding = false;
        onTalkState('asking', {});
        const r = await askMic();
        if (r === 'granted') { onTalkState('idle', {}); ctx.toast(t('talk.micAllowed'), 'info'); } else onTalkState(r === 'denied' ? 'denied' : 'error', { code: 'mic_failed' });
        return;
      }
      if (via === 'hold' && !hold) return; // released while we checked
      talk.start({ chime, volume: null });
    }
    function end(how) {
      if (state === 'asking' && talk.state !== 'asking') return; // askMic prompt: the browser owns it
      if (state === 'connecting' || state === 'asking') {
        talk.stop();
        ctx.toast(t(how === 'release' ? 'talk.holdLonger' : 'talk.cancelled'), 'info');
        return;
      }
      talk.stop();
    }

    function onTalkState(s, i) {
      const prev = state;
      state = s; info = i || {};
      if (s === 'live' && prev !== 'live') { startAt = Date.now(); clearInterval(timerT); timerT = setInterval(paintTimer, 250); }
      if (s === 'ending') endingSecs = Math.max(1, Math.floor((Date.now() - startAt) / 1000));
      if (s !== 'live' && s !== 'ending') { clearInterval(timerT); timerT = 0; }
      if (s === 'idle' || s === 'error' || s === 'denied' || s === 'http') { locked = false; holding = false; hold = null; }
      if (s === 'idle' && info.ended) {
        const e = info.ended;
        const x = mmss(e.seconds || endingSecs || 0);
        const key = { max_length: 'talk.endMax', idle: 'talk.endIdle', interrupted: 'talk.endInterrupted', disconnected: 'talk.endDropped' }[e.reason] || 'talk.talked';
        ctx.toast(t(key, x), e.reason === 'disconnected' ? 'err' : 'ok');
        ctx.refreshStatus();
      }
      paint();
    }
    function paintTimer() {
      const secs = state === 'ending' ? endingSecs : Math.floor((Date.now() - startAt) / 1000);
      timer.textContent = mmss(secs);
      timer.setAttribute('aria-label', t('talk.timerAria', mmss(secs)));
    }
    waveT = setInterval(() => {
      if (state !== 'live' && state !== 'connecting') { if (wave.some((v) => v > 0.07)) { wave.fill(0.06); paintWave(); } return; }
      wave.shift(); wave.push(Math.max(0.06, level)); paintWave();
    }, 110);
    function paintWave() { waveEl.childNodes.forEach((n, i) => { n.style.height = `${Math.max(4, Math.round(wave[i] * 52))}px`; }); }

    function paint() {
      const live = state === 'live';
      const active = live || state === 'connecting';
      const touch = coarse();
      card.dataset.state = state;
      const P = { idle: 'talk.pReady', asking: 'talk.pAsking', connecting: 'talk.pConnecting', live: 'talk.pLive', ending: 'talk.pEnding',
        denied: 'talk.pBlocked', http: 'talk.pBlocked', error: 'talk.pError' };
      pill.lastChild.textContent = t(P[state]);
      timer.hidden = !(live || state === 'ending');
      if (!timer.hidden) paintTimer();
      const onStage = ['idle', 'asking', 'connecting', 'live', 'ending'].includes(state);
      stage.hidden = !onStage;
      msg.hidden = onStage;
      if (!onStage) { paintMsg(); return; }

      waveEl.classList.toggle('live', live);
      ptt.setAttribute('aria-pressed', String(active));
      ptt.setAttribute('aria-label', t(active ? 'talk.micStop' : touch ? 'talk.micStartHold' : 'talk.micStart'));
      ptt.disabled = state === 'ending';
      ptt.replaceChildren(ring, aicon(active ? 'stop' : 'mic', active ? 'tk-stopic' : 'tk-micic'));
      let L = touch ? 'talk.holdToTalk' : 'talk.clickToTalk', S = touch ? 'talk.holdSub' : 'talk.clickSub';
      if (state === 'connecting') { L = 'talk.connecting'; S = 'talk.connectingSub'; }
      if (live) { L = touch ? (locked ? 'talk.tapToEnd' : 'talk.releaseToEnd') : 'talk.clickToEnd'; S = 'talk.liveSub'; }
      if (state === 'ending') { L = 'talk.ending'; S = 'talk.endingSub'; }
      if (state === 'asking') { L = 'talk.askingLbl'; S = 'talk.askingSub'; }
      lbl.textContent = t(L);
      sub.textContent = t(S);
      lockSlot.replaceChildren(...[
        active && holding && !locked ? h('span', { class: 'tk-lock' }, aicon('arrow-up', 'xs'), t('talk.slideLock')) : null,
        active && locked && touch ? h('span', { class: 'tk-lock on' }, icon('lock', 'xs'), t('talk.handsFree')) : null].filter(Boolean));
      kbd.hidden = touch || !['idle', 'live'].includes(state);
      kbd.replaceChildren(t('talk.kbdPre'), ' ', h('kbd', {}, 'Space'), ' ', t(live ? 'talk.kbdEnd' : 'talk.kbdStart'));
      meter.parentElement.classList.toggle('off', !live);
    }

    function paintMsg() {
      const host = location.host;
      const box = (ic, title, body, acts) => [h('span', { class: 'tk-msgic', 'aria-hidden': 'true' }, ic), h('h3', {}, title), h('p', { class: 'muted' }, body),
        acts && acts.length ? h('div', { class: 'tk-acts' }, acts) : null];
      const tryBtn = (primary = true) => h('button', { type: 'button', class: `btn ${primary ? 'primary' : 'tonal'}`, onclick: () => { onTalkState('idle', {}); begin('tap'); } }, t('talk.tryAgain'));
      if (state === 'http') msg.removeAttribute('role'); else msg.setAttribute('role', 'alert');
      if (state === 'http') {
        const secure = secureUrl();
        msg.replaceChildren(...box(aicon('unlock'), t('talk.httpTitle'), t('talk.httpBody', location.origin),
          [secure ? h('a', { class: 'btn primary', href: `${secure}/#/announce/talk` }, t('talk.openSecure', secure)) : h('p', { class: 'small' }, t('talk.askOwner'))]));
      } else if (state === 'denied') {
        msg.replaceChildren(...box(aicon('mic-off'), t('talk.deniedTitle'), t('talk.deniedBody', host),
          [h('button', { type: 'button', class: 'btn tonal', 'aria-haspopup': 'dialog', onclick: howTo }, t('talk.howAllow')), tryBtn()]));
      } else {
        const c = info.code;
        let ti = 'talk.errTitle', bo = 'talk.errBody', speakerish = true;
        if (c === 'busy') { ti = 'talk.busyTitle'; bo = null; speakerish = false; }
        else if (c === 'no_mic') { ti = 'talk.noMicTitle'; bo = 'talk.noMicBody'; speakerish = false; }
        else if (c === 'mic_failed') { ti = 'talk.micFailTitle'; bo = 'talk.micFailBody'; speakerish = false; }
        else if (c === 'unsupported') { ti = 'talk.unsupTitle'; bo = 'talk.unsupBody'; speakerish = false; }
        else if (c === 'forbidden' || c === 'unauthorized') { ti = 'talk.pError'; bo = null; speakerish = false; }
        else if (c === 'bad_request') { ti = 'talk.unavailTitle'; bo = 'talk.unavailBody'; speakerish = false; }
        let body = bo ? t(bo) : info.detail || t('talk.busyBody');
        if (c === 'forbidden') body = t('err.forbidden', t(`role.${ctx.user.role}`));
        if (c === 'unauthorized') body = t('err.session');
        if (c === 'busy' && info.detail) body = `${info.detail}. ${t('talk.busyBody')}`.replace('.. ', '. ');
        msg.replaceChildren(...box(aicon(speakerish ? 'vol-x' : 'mic-off'), t(ti), body,
          [c === 'unsupported' || c === 'forbidden' ? null : tryBtn(), speakerish ? h('a', { class: 'btn tonal', href: '#/help/offline' }, t('talk.offlineHelp')) : null].filter(Boolean)));
      }
    }

    function howTo() {
      ctx.sheet({
        title: t('talk.howTitle'),
        build(body, sheet) {
          const ios = isIos();
          body.append(h('ol', { class: 'tk-steps' }, t(ios ? 'talk.howIos' : 'talk.howDesk').map((s) => h('li', {}, s))),
            h('p', { class: 'small' }, ios ? t('talk.howIosHome') : t('talk.howDeskOther', location.host)),
            h('button', { type: 'button', class: 'btn primary big wide', onclick: () => { sheet.close(); onTalkState('idle', {}); begin('tap'); } }, t('talk.tryAgain')));
        },
      });
    }

    if (!micAllowedHere()) state = 'http';
    paint();
    return {
      card, options,
      stopIfActive() { if (['live', 'connecting', 'asking'].includes(state)) end('tap'); },
      repaint: paint,
      destroy() { clearInterval(timerT); clearInterval(waveT); document.removeEventListener('keydown', onKey); talk.destroy(); },
    };
  }
  ctx.onCleanup(() => { if (talkUi) talkUi.destroy(); });

  function secureUrl() {
    const u = (talkInfo && (talkInfo.secure_url || talkInfo.public_base_url)) || secureUrl.fromSettings;
    return u && /^https:\/\//.test(u) ? u.replace(/\/$/, '') : null;
  }

  /* ---------- layout per mode ---------- */
  function setMode(m) {
    if (m === 'talk' && !talkAvail) m = 'say';
    if (mode === 'talk' && m !== 'talk' && talkUi) talkUi.stopIfActive();
    mode = m;
    sw.set(m);
    if (m === 'talk') {
      if (!talkUi) talkUi = buildTalk();
      mainCol.replaceChildren(talkUi.card);
      sideCol.replaceChildren(talkUi.options);
    } else {
      mainCol.replaceChildren(op ? say.form : h('p', { class: 'ann-note' }, icon('info', 'sm'), h('span', {}, t('ann.viewer'))));
      sideCol.replaceChildren(phrases.box);
    }
    node.dataset.mode = m;
    const want = m === 'talk' ? '#/announce/talk' : '#/announce';
    if (location.hash !== want && location.hash.startsWith('#/announce')) history.replaceState(null, '', want);
  }
  setMode('say');

  // Talk live: the switch asks /talk/status (operators only: the socket refuses viewers) and calls onTalk
  if (op && ctx.can('admin') && !micAllowedHere()) {
    ctx.api('/settings', { signal: ctx.signal }).then((st) => { secureUrl.fromSettings = st && st.public_base_url; if (talkUi) talkUi.repaint(); }).catch(() => {});
  }

  return {
    node,
    onStatus({ status }) { if (status && say) say.setLangFromStatus(status.tts_lang); },
  };
}
