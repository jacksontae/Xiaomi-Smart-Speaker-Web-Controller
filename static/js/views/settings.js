// Speaker settings (boards Settings / T_Settings / D_Settings). Owner only. GET /settings, POST /settings (partial).
// Speaker (name, address, find on the LAN for the direct/Cast connection), Sound (default volume, announcement
// language, resume after announcements), Storage (YouTube cache), Connection (transport + relay health read-only,
// API token info, port). Language/appearance live in App settings (per device). One Save for the page.
// The API token can't be changed over the API (the server refuses); the page says where to rotate it.
import { h, icon, busy, segmented, toast } from '../ui.js';
import { register, t } from '../i18n.js';
import { errorText } from '../api.js';
import { caption, card, settingRow, switchInput, linkRow, tile, cIcon, phoneBack, fmtWhen } from '../c-kit.js';

register({
  en: {
    'set.speaker': 'Speaker', 'set.name': 'Speaker name', 'set.nameHelp': 'Shown in the app and in Activity.',
    'set.ip': 'Speaker address (IP)', 'set.ipHelp': 'The speaker\'s address on this network, like 192.0.2.10.',
    'set.connectedAt': (ip) => `Connected at ${ip}`, 'set.offline': 'Can\'t reach the speaker right now.',
    'set.checking': 'Checking the speaker…',
    'set.scan': 'Find speakers on the LAN', 'set.scanning': 'Looking for speakers…', 'set.scanAgain': 'Look again',
    'set.found': (n) => (n === 1 ? 'Found 1 speaker. Pick the one to use.' : `Found ${n} speakers. Pick the one to use.`),
    'set.foundNone': 'No speakers answered. Check that the speaker is on and on the same network as this computer.',
    'set.use': 'Use', 'set.inUse': 'In use',
    'set.willConnect': (ip) => `Connects to ${ip} when you save.`,
    'set.sound': 'Sound', 'set.keepVol': 'Leave the volume as it is', 'set.keepVolHelp': 'Playback starts at whatever volume the speaker is at.',
    'set.startVol': 'Volume when playback starts',
    'set.tts': 'Default announcement language', 'set.ttsHelp': 'Announcements can still pick another language each time.',
    'set.resume': 'Resume music after announcements', 'set.resumeHelp': 'Music pauses, the announcement plays, then music continues from the same spot.',
    'set.storage': 'Storage', 'set.cache': 'YouTube tracks kept on disk', 'set.cacheHelp': 'The most recent tracks stay saved so they replay instantly. Older ones are deleted.',
    'set.conn': 'Connection',
    'set.via': 'How the app reaches the speaker',
    'set.viaCast': 'Directly on this network (Google Cast)', 'set.viaMqtt': 'Through the ESP32 relay (MQTT)',
    'set.broker': 'Relay broker', 'set.tlsOn': 'encrypted (TLS)', 'set.tlsOff': 'not encrypted',
    'set.relay': 'Relay', 'set.relayOk': (w) => `Online, last heard ${w}`, 'set.relayOff': (w) => (w ? `Offline, last heard ${w}` : 'Offline, never heard from'),
    'set.brokerDown': 'The app can\'t reach the broker',
    'set.media': 'Address the speaker loads audio from', 'set.mediaLan': 'This computer\'s address on the LAN',
    'set.transportHelp': 'Changed in config.json on the computer running the service.',
    'set.token': 'API token', 'set.tokenHelp': 'For the ESP32 or scripts. View or change it with ./speakerctl token on the computer running the service.',
    'set.port': 'Port', 'set.portHelp': 'The service restarts by itself after a change.',
    'set.badPort': 'The port must be a number from 1024 to 65535.', 'set.badCache': 'Keep at least 1 track.',
    'set.badName': 'Give the speaker a name.', 'set.badIp': 'Enter an IP address like 192.0.2.10 or a hostname like speaker.example.com.',
    'set.device': 'On this device', 'set.app': 'App settings', 'set.appHelp': 'Language and appearance are set per device, not on the speaker.',
    'set.saved': 'Speaker settings saved', 'set.restarting': (p) => `Saved. The service is restarting on port ${p}; open the app at the new port.`,
    'set.lang.th': 'ไทย', 'set.lang.en': 'English', 'set.lang.ja': '日本語',
  },
  th: {
    'set.speaker': 'ลำโพง', 'set.name': 'ชื่อลำโพง', 'set.nameHelp': 'แสดงในแอปและในประวัติการใช้งาน',
    'set.ip': 'ที่อยู่ลำโพง (IP)', 'set.ipHelp': 'ที่อยู่ของลำโพงในเครือข่ายนี้ เช่น 192.0.2.10',
    'set.connectedAt': (ip) => `เชื่อมต่ออยู่ที่ ${ip}`, 'set.offline': 'ตอนนี้ติดต่อลำโพงไม่ได้',
    'set.checking': 'กำลังตรวจลำโพง…',
    'set.scan': 'ค้นหาลำโพงในวง LAN', 'set.scanning': 'กำลังค้นหาลำโพง…', 'set.scanAgain': 'ค้นหาอีกครั้ง',
    'set.found': (n) => `พบ ${n} เครื่องในวง LAN เลือกเครื่องที่จะใช้`,
    'set.foundNone': 'ไม่พบลำโพง ตรวจว่าลำโพงเปิดอยู่และต่อเครือข่ายเดียวกับเครื่องนี้',
    'set.use': 'ใช้เครื่องนี้', 'set.inUse': 'ใช้อยู่ตอนนี้',
    'set.willConnect': (ip) => `จะเชื่อมต่อที่ ${ip} เมื่อบันทึก`,
    'set.sound': 'เสียง', 'set.keepVol': 'ไม่เปลี่ยนระดับเสียงเอง', 'set.keepVolHelp': 'เริ่มเล่นที่ระดับเสียงที่ลำโพงตั้งไว้อยู่แล้ว',
    'set.startVol': 'ระดับเสียงตอนเริ่มเล่น',
    'set.tts': 'ภาษาประกาศเริ่มต้น', 'set.ttsHelp': 'ตอนประกาศยังเลือกภาษาอื่นได้ทุกครั้ง',
    'set.resume': 'เล่นเพลงต่อหลังประกาศ', 'set.resumeHelp': 'พักเพลง ประกาศ แล้วเล่นต่อจากจุดเดิม',
    'set.storage': 'พื้นที่เก็บ', 'set.cache': 'จำนวนเพลง YouTube ที่เก็บไว้', 'set.cacheHelp': 'เก็บเพลงล่าสุดไว้ เล่นซ้ำได้ทันที เพลงที่เก่ากว่าจะถูกลบ',
    'set.conn': 'การเชื่อมต่อ',
    'set.via': 'แอปติดต่อลำโพงทางไหน',
    'set.viaCast': 'ตรงในเครือข่ายนี้ (Google Cast)', 'set.viaMqtt': 'ผ่านตัวรีเลย์ ESP32 (MQTT)',
    'set.broker': 'โบรกเกอร์ของรีเลย์', 'set.tlsOn': 'เข้ารหัส (TLS)', 'set.tlsOff': 'ไม่เข้ารหัส',
    'set.relay': 'รีเลย์', 'set.relayOk': (w) => `ออนไลน์ ติดต่อล่าสุด${w}`, 'set.relayOff': (w) => (w ? `ออฟไลน์ ติดต่อล่าสุด${w}` : 'ออฟไลน์ ยังไม่เคยติดต่อ'),
    'set.brokerDown': 'แอปติดต่อโบรกเกอร์ไม่ได้',
    'set.media': 'ที่อยู่ที่ลำโพงใช้โหลดเสียง', 'set.mediaLan': 'ที่อยู่ของเครื่องนี้ในวง LAN',
    'set.transportHelp': 'เปลี่ยนได้ใน config.json บนเครื่องที่รัน service',
    'set.token': 'API token', 'set.tokenHelp': 'สำหรับ ESP32 หรือสคริปต์ ดูหรือเปลี่ยนด้วย ./speakerctl token บนเครื่องที่รัน service',
    'set.port': 'พอร์ต', 'set.portHelp': 'เปลี่ยนแล้ว service จะเริ่มใหม่เอง',
    'set.badPort': 'พอร์ตต้องเป็นตัวเลข 1024 ถึง 65535', 'set.badCache': 'ต้องเก็บอย่างน้อย 1 เพลง',
    'set.badName': 'ตั้งชื่อลำโพงก่อน', 'set.badIp': 'ใส่ IP เช่น 192.0.2.10 หรือชื่อโฮสต์ เช่น speaker.example.com',
    'set.device': 'บนอุปกรณ์นี้', 'set.app': 'ตั้งค่าแอป', 'set.appHelp': 'ภาษาและลักษณะของแอปตั้งแยกในแต่ละเครื่อง ไม่ได้ตั้งที่ลำโพง',
    'set.saved': 'บันทึกการตั้งค่าลำโพงแล้ว', 'set.restarting': (p) => `บันทึกแล้ว service กำลังเริ่มใหม่ที่พอร์ต ${p} เปิดแอปที่พอร์ตใหม่`,
    'set.lang.th': 'ไทย', 'set.lang.en': 'English', 'set.lang.ja': '日本語',
  },
});

const TTS = ['th', 'en', 'ja'];
const IPV4 = /^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$/;
const HOST = /^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$/i;
/** IPv4 or a DNS hostname; an all-digits-and-dots value must be a real IPv4 address. */
const validAddress = (v) => (/^[\d.]+$/.test(v) ? IPV4.test(v) : HOST.test(v));

export function render(ctx) {
  ctx.css('views/c-common.css');
  ctx.css('views/settings.css');
  let saved = null;   // last GET/POST result
  let draft = {};     // changed keys only
  const err = h('p', { class: 'form-error', role: 'alert' });
  const dirtyNote = h('span', { class: 'small', hidden: true }, t('c.unsaved'));
  const saveBtn = h('button', { type: 'button', class: 'btn primary', disabled: true, onclick: () => save() }, t('common.save'));
  const left = h('div', { class: 'c-col' });
  const right = h('div', { class: 'c-col' });
  const bottomSave = h('button', { type: 'button', class: 'btn primary big wide c-phone-only', disabled: true, onclick: () => save() }, t('common.save'));
  const node = h('div', { class: 'page s-page' },
    phoneBack(ctx.header({ title: t('nav.settings'), back: { href: '#/account', label: t('nav.account') }, actions: h('div', { class: 'c-save c-large-only' }, dirtyNote, saveBtn) })),
    err, h('div', { class: 'c-cols c-reorder' }, left, right), bottomSave);
  let statusLine = null;
  let relayLine = null;
  // inline field errors (built with the speaker card); server 422s naming a field land here too
  const fieldErr = {
    speaker_name: h('p', { class: 'small form-error', id: 's-name-err' }),
    speaker_ip: h('p', { class: 'small form-error', id: 's-ip-err' }),
  };
  const fieldInput = {};
  function showFieldErr(k, msg) {
    fieldErr[k].textContent = msg || '';
    const input = fieldInput[k];
    if (!input) return;
    if (msg) { input.setAttribute('aria-invalid', 'true'); input.setAttribute('aria-describedby', fieldErr[k].id); }
    else { input.removeAttribute('aria-invalid'); input.removeAttribute('aria-describedby'); }
  }

  const val = (k) => (k in draft ? draft[k] : saved[k]);
  function set(k, v) {
    if (JSON.stringify(v) === JSON.stringify(saved[k])) delete draft[k]; else draft[k] = v;
    paintDirty();
  }
  // the draft is the source of truth for Save (busy() re-enables buttons when it finishes, so repaint after it)
  function paintDirty() {
    const dirty = Object.keys(draft).length > 0;
    saveBtn.disabled = !dirty; bottomSave.disabled = !dirty; dirtyNote.hidden = !dirty;
  }

  function build() {
    const isCast = saved.transport === 'cast';
    /* speaker */
    const name = h('input', { class: 'input', value: val('speaker_name'), maxLength: 64, oninput: () => { showFieldErr('speaker_name', ''); set('speaker_name', name.value.trim()); } });
    fieldInput.speaker_name = name;
    showFieldErr('speaker_name', '');
    statusLine = h('p', { class: 'small', role: 'status' }, t('set.checking'));
    const speakerKids = [h('div', { class: 'c-stack' }, h('label', { class: 'c-title', for: 's-name' }, t('set.name')), Object.assign(name, { id: 's-name' }), statusLine, fieldErr.speaker_name)];
    if (isCast) {
      const ip = h('input', { class: 'input', id: 's-ip', value: val('speaker_ip'), inputMode: 'decimal', autocomplete: 'off', spellcheck: false, oninput: () => { showFieldErr('speaker_ip', ''); set('speaker_ip', ip.value.trim()); } });
      fieldInput.speaker_ip = ip;
      showFieldErr('speaker_ip', '');
      const found = h('div', { class: 's-found', 'aria-live': 'polite' });
      const scan = h('button', { type: 'button', class: 'btn tonal wide' }, cIcon('scan', 'sm'), t('set.scan'));
      scan.addEventListener('click', () => busy(scan, async () => {
        found.replaceChildren(h('p', { class: 'small' }, t('set.scanning')));
        try {
          const list = await ctx.api('/speakers', { signal: ctx.signal });
          found.replaceChildren(h('p', { class: 'small' }, list.length ? t('set.found', list.length) : t('set.foundNone')),
            ...list.map((s) => {
              const cur = s.ip === val('speaker_ip');
              const use = h('button', { type: 'button', class: 'btn', disabled: cur }, t(cur ? 'set.inUse' : 'set.use'));
              use.addEventListener('click', () => {
                name.value = s.name; ip.value = s.ip;
                showFieldErr('speaker_name', ''); showFieldErr('speaker_ip', '');
                set('speaker_name', s.name); set('speaker_ip', s.ip);
                found.replaceChildren(h('p', { class: 'small' }, t('set.willConnect', s.ip)));
              });
              return settingRow({ title: s.name, sub: [s.ip, s.model].filter(Boolean).join(', '), control: use, lead: h('span', { class: 'c-tile plain', 'aria-hidden': 'true' }, icon('speaker', 'sm')), cls: 's-dev' });
            }));
          scan.lastChild.textContent = t('set.scanAgain');
        } catch (e) { found.replaceChildren(h('p', { class: 'small form-error' }, errorText(e, ctx.user))); }
      }));
      speakerKids.push(h('div', { class: 'c-stack' }, h('label', { class: 'c-title', for: 's-ip' }, t('set.ip')), ip, fieldErr.speaker_ip, h('p', { class: 'small' }, t('set.ipHelp')), scan, found));
    }
    const speakerCard = card(...speakerKids);

    /* sound */
    const keep = val('default_volume') == null;
    let lastVol = val('default_volume') ?? 0.35;
    const pct = h('span', { class: 's-pct' }, `${Math.round(lastVol * 100)}%`);
    const range = h('input', { type: 'range', class: 'c-range', min: 0, max: 100, step: 1, value: Math.round(lastVol * 100), disabled: keep, 'aria-label': t('set.startVol') });
    range.addEventListener('input', () => { lastVol = range.value / 100; pct.textContent = `${range.value}%`; set('default_volume', lastVol); });
    const volBlock = h('div', { class: 'c-stack s-vol', hidden: keep }, h('div', { class: 's-volhead' }, h('span', { class: 'c-title' }, t('set.startVol')), pct), range);
    const keepSw = switchInput(keep, (on) => { range.disabled = on; volBlock.hidden = on; set('default_volume', on ? null : lastVol); });
    const ttsOpts = [...TTS, ...(TTS.includes(val('tts_lang')) ? [] : [val('tts_lang')])].map((v) => ({ value: v, label: TTS.includes(v) ? t(`set.lang.${v}`) : v, lang: v }));
    const tts = segmented({ label: t('set.tts'), value: val('tts_lang'), options: ttsOpts, onChange: (v) => set('tts_lang', v) });
    const resume = switchInput(val('resume_after_say'), (on) => set('resume_after_say', on));
    const soundCard = card(
      settingRow({ title: t('set.keepVol'), sub: t('set.keepVolHelp'), control: keepSw }),
      volBlock,
      h('div', { class: 'c-seg-wrap' }, h('span', { class: 'c-title' }, t('set.tts')), tts, h('span', { class: 'c-sub' }, t('set.ttsHelp'))),
      settingRow({ title: t('set.resume'), sub: t('set.resumeHelp'), control: resume }));

    /* storage */
    const cache = h('input', { class: 'input c-num', type: 'number', min: 1, max: 999, step: 1, value: val('cache_keep'), inputMode: 'numeric' });
    cache.addEventListener('input', () => set('cache_keep', parseInt(cache.value, 10)));
    const storageCard = card(settingRow({ title: t('set.cache'), sub: t('set.cacheHelp'), control: cache }));

    /* connection */
    const port = h('input', { class: 'input c-num', type: 'number', min: 1024, max: 65535, step: 1, value: val('port'), inputMode: 'numeric' });
    port.addEventListener('input', () => set('port', parseInt(port.value, 10)));
    const m = saved.mqtt || {};
    relayLine = isCast ? null : h('span', {}, '');
    const connRows = [
      settingRow({ title: t('set.via'), sub: h('span', {}, t(isCast ? 'set.viaCast' : 'set.viaMqtt'), h('br'), t('set.transportHelp')) }),
      isCast ? null : settingRow({ title: t('set.broker'), sub: `${m.host || '—'}:${m.port || ''}, ${t(m.tls ? 'set.tlsOn' : 'set.tlsOff')}` }),
      isCast ? null : settingRow({ title: t('set.relay'), sub: relayLine }),
      settingRow({ title: t('set.media'), sub: saved.public_base_url || t('set.mediaLan') }),
      settingRow({ title: t('set.token'), sub: t('set.tokenHelp') }),
      settingRow({ title: t('set.port'), sub: t('set.portHelp'), control: port }),
    ];
    const connCard = card(...connRows);

    const appCard = card(linkRow({ href: '#/prefs', title: t('set.app'), sub: t('set.appHelp'), lead: tile(cIcon('phone'), 'plain') }));

    // phone/iPad read top to bottom in board order (speaker, sound, storage, connection); desktop has two columns
    const sec = (order, ...kids) => h('section', { class: 'c-col', style: { order } }, kids);
    left.replaceChildren(sec(1, caption(t('set.speaker')), speakerCard), sec(4, caption(t('set.conn')), connCard));
    right.replaceChildren(sec(2, caption(t('set.sound')), soundCard), sec(3, caption(t('set.storage')), storageCard), sec(5, caption(t('set.device')), appCard));
    paintStatus();
  }

  function paintStatus() {
    if (!statusLine) return;
    const s = ctx.status, e = ctx.statusError;
    statusLine.className = e ? 'small form-error' : 'small';
    statusLine.textContent = e ? t('set.offline') : s ? (s.ip ? t('set.connectedAt', s.ip) : '') : t('set.checking');
    if (relayLine) {
      const r = s && s.relay;
      if (!r) relayLine.textContent = e ? t('set.offline') : '—';
      else if (!r.broker_connected) relayLine.textContent = t('set.brokerDown');
      else relayLine.textContent = r.online ? t('set.relayOk', fmtWhen(r.last_seen)) : t('set.relayOff', r.last_seen ? fmtWhen(r.last_seen) : '');
    }
  }

  async function save() {
    err.textContent = '';
    const bad = [];
    if ('speaker_name' in draft && !draft.speaker_name) bad.push(['speaker_name', t('set.badName')]);
    if ('speaker_ip' in draft && !validAddress(draft.speaker_ip)) bad.push(['speaker_ip', t('set.badIp')]);
    Object.keys(fieldErr).forEach((k) => showFieldErr(k, ''));
    if (bad.length) {
      bad.forEach(([k, msg]) => showFieldErr(k, msg));
      err.textContent = bad[0][1];
      fieldInput[bad[0][0]]?.focus();
      return;
    }
    if ('port' in draft && !(draft.port >= 1024 && draft.port <= 65535)) { err.textContent = t('set.badPort'); return; }
    if ('cache_keep' in draft && !(draft.cache_keep >= 1)) { err.textContent = t('set.badCache'); return; }
    const body = { ...draft };
    await busy(saveBtn, () => busy(bottomSave, async () => {
      try {
        const r = await ctx.api('/settings', { body });
        saved = r.settings;
        draft = {};
        toast(r.restart ? t('set.restarting', saved.port) : t('set.saved'), 'ok', { ms: r.restart ? 9000 : 3800 });
        build();
        ctx.refreshStatus();
      } catch (e) {
        err.textContent = errorText(e, ctx.user);
        // the server validates too (422): put its detail under the field it names
        const d = e.status === 422 ? e.detail || '' : '';
        const k = /speaker_ip|\bip\b|address|host/i.test(d) ? 'speaker_ip' : /speaker_name|name/i.test(d) ? 'speaker_name' : null;
        if (k) showFieldErr(k, e.detail);
      }
    }));
    paintDirty();
  }

  ctx.api('/settings', { signal: ctx.signal }).then((s) => { saved = s; build(); }).catch((e) => { err.textContent = ctx.fail(e); });
  return { node, onStatus: paintStatus };
}
