// Now playing (boards Now / T_Now / D_Now): the 3D speaker mirrors the real state, then title + status line,
// progress (ticks locally between polls), transport, volume and the queue with shuffle/repeat.
// Idle, offline and announcing states come from /status; owners also see the ESP32 relay's health when the
// server reports `relay` (mqtt transport). There is no seek endpoint, so the progress bar is display only.
import { h, icon, iconBtn, tip } from '../ui.js';
import { register, t, fmtDur, fmtRel } from '../i18n.js';
import { speaker3d } from '../speaker3d.js';
import { aicon } from '../a-icons.js';

register({
  en: {
    'now.idleTitle': 'Nothing playing',
    'now.idleLine': 'Stopped. The speaker isn\'t playing anything.',
    'now.idleHint': 'Pick a playlist or some music, or make an announcement.',
    'now.offTitle': 'Can\'t reach the speaker',
    'now.offLine': 'Nothing will play until it\'s back. Check that it\'s plugged in and on the same Wi‑Fi.',
    'now.offServer': 'Can\'t reach the server. Check that this device is on the same network.',
    'now.retry': 'Try again',
    'now.offHelp': 'Speaker is offline',
    'now.checking': 'Checking the speaker…',
    'now.playingFrom': (pl) => `Playing from the playlist ${pl}`,
    'now.playing': 'Playing',
    'now.loading': 'Loading…',
    'now.paused': 'Paused. Press play to continue where you left off.',
    'now.pausedView': 'Paused',
    'now.announcing': 'The speaker is announcing.',
    'now.announcingResume': 'The speaker is announcing. The music picks up again afterwards.',
    'now.announcingThen': (x) => `The speaker is announcing. “${x}” picks up again afterwards.`,
    'now.announcement': 'Announcement',
    'now.live': 'Live',
    'now.kind.youtube': 'Song', 'now.kind.radio': 'Radio', 'now.kind.podcast': 'Podcast', 'now.kind.file': 'My files',
    'now.kind.url': 'Audio link', 'now.kind.tts': 'Announcement',
    'now.prev': 'Previous', 'now.next': 'Next', 'now.play': 'Play', 'now.pause': 'Pause', 'now.stop': 'Stop',
    'now.stopTip': 'Stop and clear the queue',
    'now.volume': 'Volume',
    'now.volText': (n) => `${n} percent`,
    'now.progress': 'Position',
    'now.progressText': (a, b) => `${a} of ${b}`,
    'now.queue': 'Queue',
    'now.position': (i, n) => `Item ${i} of ${n}`,
    'now.shuffleOn': 'Shuffle: on', 'now.shuffleOff': 'Shuffle: off',
    'now.repeatOff': 'Repeat: off', 'now.repeatAll': 'Repeat all', 'now.repeatOne': 'Repeat this item',
    'now.subPlaying': (d) => (d ? `Playing, ${d}` : 'Playing'),
    'now.subPaused': (d) => (d ? `Paused, ${d}` : 'Paused'),
    'now.playItem': (x) => `Play ${x}`,
    'now.showAll': (n) => `Show all ${n}`,
    'now.showNext': 'Show only what\'s next',
    'now.lastItem': 'That was the last item in the queue',
    'now.goPlaylists': 'Playlists', 'now.goMusic': 'Find music', 'now.goAnnounce': 'Announce',
    'now.relay': 'Relay',
    'now.relayOnline': 'Online', 'now.relayOffline': 'Offline',
    'now.relaySeen': (x) => `Last heard ${x}`,
    'now.relayNever': 'Not heard from yet',
    'now.relayBroker': 'Can\'t reach the MQTT broker',
    'now.relaySpeakerErr': (e) => `The relay can't reach the speaker${e ? ` (${e})` : ''}`,
    'now.relaySignal': (n) => `Wi‑Fi signal ${n} dBm`,
    'now.relayFw': (v) => `Firmware ${v}`,
  },
  th: {
    'now.idleTitle': 'ไม่ได้เล่นอะไร',
    'now.idleLine': 'หยุดแล้ว ลำโพงไม่ได้เล่นอะไร',
    'now.idleHint': 'เลือกเพลย์ลิสต์หรือเพลง หรือจะประกาศก็ได้',
    'now.offTitle': 'ติดต่อลำโพงไม่ได้',
    'now.offLine': 'จะยังไม่มีเสียงจนกว่าลำโพงกลับมา ตรวจว่าเสียบปลั๊กอยู่และต่อ Wi‑Fi วงเดียวกัน',
    'now.offServer': 'เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ ตรวจว่าเครื่องนี้ต่อเครือข่ายเดียวกัน',
    'now.retry': 'ลองอีกครั้ง',
    'now.offHelp': 'ลำโพงออฟไลน์',
    'now.checking': 'กำลังตรวจลำโพง…',
    'now.playingFrom': (pl) => `กำลังเล่น จากเพลย์ลิสต์ ${pl}`,
    'now.playing': 'กำลังเล่น',
    'now.loading': 'กำลังโหลด…',
    'now.paused': 'พักไว้ กดเล่นเพื่อเล่นต่อจากจุดเดิม',
    'now.pausedView': 'พักไว้',
    'now.announcing': 'ลำโพงกำลังประกาศ',
    'now.announcingResume': 'ลำโพงกำลังประกาศ เพลงจะเล่นต่อหลังจบ',
    'now.announcingThen': (x) => `ลำโพงกำลังประกาศ “${x}” จะเล่นต่อหลังจบ`,
    'now.announcement': 'ข้อความประกาศ',
    'now.live': 'สด',
    'now.kind.youtube': 'เพลง', 'now.kind.radio': 'วิทยุ', 'now.kind.podcast': 'พอดแคสต์', 'now.kind.file': 'ไฟล์ของฉัน',
    'now.kind.url': 'ลิงก์เสียง', 'now.kind.tts': 'ข้อความประกาศ',
    'now.prev': 'ก่อนหน้า', 'now.next': 'ถัดไป', 'now.play': 'เล่น', 'now.pause': 'พัก', 'now.stop': 'หยุด',
    'now.stopTip': 'หยุดและล้างคิว',
    'now.volume': 'ระดับเสียง',
    'now.volText': (n) => `${n} เปอร์เซ็นต์`,
    'now.progress': 'ตำแหน่งที่เล่น',
    'now.progressText': (a, b) => `${a} จาก ${b}`,
    'now.queue': 'คิว',
    'now.position': (i, n) => `รายการที่ ${i} จาก ${n}`,
    'now.shuffleOn': 'สุ่ม: เปิด', 'now.shuffleOff': 'สุ่ม: ปิด',
    'now.repeatOff': 'เล่นวน: ปิด', 'now.repeatAll': 'เล่นวนทั้งหมด', 'now.repeatOne': 'เล่นวนรายการนี้',
    'now.subPlaying': (d) => (d ? `กำลังเล่น ${d}` : 'กำลังเล่น'),
    'now.subPaused': (d) => (d ? `พักไว้ ${d}` : 'พักไว้'),
    'now.playItem': (x) => `เล่น ${x}`,
    'now.showAll': (n) => `ดูทั้งหมด ${n} รายการ`,
    'now.showNext': 'ดูเฉพาะรายการถัดไป',
    'now.lastItem': 'นี่คือรายการสุดท้ายในคิวแล้ว',
    'now.goPlaylists': 'เพลย์ลิสต์', 'now.goMusic': 'หาเพลง', 'now.goAnnounce': 'ประกาศ',
    'now.relay': 'ตัวรีเลย์',
    'now.relayOnline': 'ออนไลน์', 'now.relayOffline': 'ออฟไลน์',
    'now.relaySeen': (x) => `ติดต่อล่าสุด ${x}`,
    'now.relayNever': 'ยังไม่เคยติดต่อมา',
    'now.relayBroker': 'เชื่อมต่อ MQTT broker ไม่ได้',
    'now.relaySpeakerErr': (e) => `ตัวรีเลย์ติดต่อลำโพงไม่ได้${e ? ` (${e})` : ''}`,
    'now.relaySignal': (n) => `สัญญาณ Wi‑Fi ${n} dBm`,
    'now.relayFw': (v) => `เฟิร์มแวร์ ${v}`,
  },
});

const ACTIVE = ['PLAYING', 'PAUSED', 'BUFFERING'];
const KIND_ICON = { youtube: 'note', radio: 'radio', podcast: 'podcast', file: 'file', url: 'link' };
const REPEAT_NEXT = { off: 'all', all: 'one', one: 'off' };
const QUEUE_PEEK = 6; // rows shown from the current item before "Show all"

const kindIcon = (kind, cls) => (kind === 'tts' ? icon('announce', cls) : aicon(KIND_ICON[kind] || 'note', cls));

export async function render(ctx) {
  await Promise.all([ctx.css('speaker3d.css'), ctx.css('views/now.css')]); // styled before first paint
  const op = ctx.can('operator');
  const admin = ctx.can('admin');
  let st = null;          // latest /status (null while offline)
  let err = null;         // latest status error
  let statusAt = 0;       // performance.now() of the last poll, for the local progress tick
  let volHoldUntil = 0;   // ignore polled volume while the user drags
  let showAll = false;
  let queueKey = '';

  /* ----- hero: 3D speaker + artwork/title/status ----- */
  const spk = speaker3d({ state: 'spk-idle spk-breathe' });
  const art = h('div', { class: 'np-art', hidden: true });
  const kindEl = h('p', { class: 'np-kind' });
  const title = h('h2', { class: 'np-title' }, t('now.checking'));
  const line = h('p', { class: 'np-line', role: 'status' });
  const meta = h('div', { class: 'np-meta' }, art, h('div', { class: 'np-tx' }, kindEl, title, line));

  /* ----- progress (display only) ----- */
  const fill = h('span', { class: 'np-fill' });
  const bar = h('div', { class: 'np-bar', role: 'progressbar', 'aria-label': t('now.progress'), 'aria-valuemin': '0' }, fill);
  const tPos = h('span'), tLeft = h('span');
  const prog = h('div', { class: 'np-prog', hidden: true }, bar, h('div', { class: 'np-times' }, tPos, tLeft));
  const liveTag = h('p', { class: 'np-livetag', hidden: true }, h('span', { 'aria-hidden': 'true' }), t('now.live'));

  /* ----- transport ----- */
  const ctl = (name, label, fn, cls = '') => {
    const b = h('button', { type: 'button', class: `np-b ${cls}`.trim(), 'aria-label': label, onclick: fn }, aicon(name, 'lg'));
    tip(b, label);
    return b;
  };
  const prevB = ctl('prev', t('now.prev'), () => act('/queue/prev'));
  const playB = ctl('pause', t('now.pause'), () => togglePlay(), 'np-main');
  const nextB = ctl('next', t('now.next'), () => act('/queue/next', undefined, { 409: t('now.lastItem') }));
  const stopB = ctl('stop', t('now.stopTip'), () => act('/stop'));
  const transport = h('div', { class: 'np-transport glass', hidden: true }, prevB, playB, nextB, stopB);

  /* ----- volume (operators drag; viewers see the level) ----- */
  const volOut = h('output', { class: 'np-volout' });
  let volCtl;
  if (op) {
    volCtl = h('input', { class: 'np-range', type: 'range', min: '0', max: '100', step: '1', value: '0', 'aria-label': t('now.volume') });
    let timer = 0, lastSent = 0;
    const send = () => { lastSent = Date.now(); ctx.api('/volume', { body: { level: +volCtl.value / 100 } }).catch((e) => ctx.fail(e)); };
    volCtl.addEventListener('input', () => {
      volHoldUntil = Date.now() + 2500;
      paintVol(+volCtl.value);
      clearTimeout(timer);
      timer = setTimeout(send, Math.max(0, 250 - (Date.now() - lastSent)));
    });
    ctx.onCleanup(() => clearTimeout(timer));
  } else {
    volCtl = h('div', { class: 'np-meter', role: 'meter', 'aria-label': t('now.volume'), 'aria-valuemin': '0', 'aria-valuemax': '100' }, h('span'));
  }
  const volume = h('div', { class: 'np-volume glass', hidden: true }, aicon('vol-low', 'sm'), volCtl, volOut);
  function paintVol(pct) {
    volOut.textContent = `${pct}%`;
    volCtl.style.setProperty('--p', `${pct}%`);
    if (op) { volCtl.value = String(pct); volCtl.setAttribute('aria-valuetext', t('now.volText', pct)); } else volCtl.setAttribute('aria-valuenow', String(pct));
  }

  /* ----- idle / offline actions ----- */
  const go = (href, ic, label, primary) => h('a', { class: `btn ${primary ? 'primary' : 'tonal'}`, href }, ic, label);
  const idleActs = h('div', { class: 'np-acts', hidden: true },
    op ? [go('#/playlists', icon('playlists', 'sm'), t('now.goPlaylists'), true), go('#/music', icon('music', 'sm'), t('now.goMusic')),
      go('#/announce', icon('announce', 'sm'), t('now.goAnnounce'))] : null);
  const retryB = h('button', { type: 'button', class: 'btn primary', onclick: () => { retryB.disabled = true; ctx.refreshStatus(); setTimeout(() => { retryB.disabled = false; }, 1500); } }, icon('refresh', 'sm'), t('now.retry'));
  const offActs = h('div', { class: 'np-acts', hidden: true }, retryB, h('a', { class: 'btn tonal', href: '#/help/offline' }, icon('help', 'sm'), t('now.offHelp')));

  /* ----- queue ----- */
  const queueBox = h('section', { class: 'np-queue', hidden: true, 'aria-labelledby': 'np-qh' });

  /* ----- relay (owner, mqtt transport) ----- */
  const relayBox = h('section', { class: 'np-relay list', hidden: true, 'aria-label': t('now.relay') });

  const mainCol = h('div', { class: 'np-col' },
    h('div', { class: 'np-hero' }, h('div', { class: 'np-stage' }, spk.el), meta),
    prog, liveTag, h('div', { class: 'np-ctrls' }, transport, volume), idleActs, offActs);
  const node = h('div', { class: 'page now-page' }, ctx.header({ title: t('nav.now') }),
    h('div', { class: 'np-grid' }, mainCol, h('div', { class: 'np-side' }, queueBox, relayBox)));

  /* ----- commands ----- */
  async function act(path, body, overrides) {
    try {
      await ctx.api(path, { method: 'POST', body });
      spk.flash('spk-success');
    } catch (e) {
      ctx.fail(e, overrides);
      spk.flash('spk-error');
    }
    ctx.refreshStatus();
  }
  function togglePlay() {
    const s = st && st.media && st.media.state;
    const playing = s === 'PLAYING' || s === 'BUFFERING';
    setPlayIcon(!playing); // answer the tap now; the next poll confirms
    act(playing ? '/pause' : '/resume');
  }
  function setPlayIcon(playing) {
    const label = t(playing ? 'now.pause' : 'now.play');
    playB.replaceChildren(aicon(playing ? 'pause' : 'play', 'lg'));
    playB.setAttribute('aria-label', label);
    tip(playB, label);
  }
  async function patchQueue(body) {
    try { await ctx.api('/queue', { method: 'PATCH', body }); } catch (e) { ctx.fail(e); }
    queueKey = '';
    ctx.refreshStatus();
  }

  /* ----- rendering from /status ----- */
  function setArt(src) {
    if (!src) { art.hidden = true; art.replaceChildren(); return; }
    if (art.dataset.src === src) { art.hidden = false; return; }
    art.dataset.src = src;
    const img = h('img', { src, alt: '', loading: 'lazy', referrerpolicy: 'no-referrer' });
    img.addEventListener('error', () => { art.hidden = true; }, { once: true });
    art.replaceChildren(img);
    art.hidden = false;
  }

  function showOffline(e) {
    spk.setState('spk-off');
    kindEl.textContent = '';
    title.textContent = t('now.offTitle');
    line.textContent = e && e.status === 0 ? t('now.offServer') : t('now.offLine');
    setArt(null);
    prog.hidden = liveTag.hidden = transport.hidden = volume.hidden = idleActs.hidden = queueBox.hidden = true;
    offActs.hidden = false;
    queueKey = '';
  }

  function update() {
    if (err || !st) { if (err) showOffline(err); return; }
    offActs.hidden = true;
    const m = st.media || {};
    const q = st.queue;
    const active = ACTIVE.includes(m.state);
    const announcing = active && m.title === 'Announcement';
    const cur = q && q.items[q.index];

    if (!active) {
      spk.setState('spk-idle spk-breathe');
      kindEl.textContent = '';
      title.textContent = t('now.idleTitle');
      line.textContent = op ? t('now.idleHint') : t('now.idleLine');
      setArt(null);
      prog.hidden = liveTag.hidden = transport.hidden = true;
      idleActs.hidden = !op;
    } else {
      idleActs.hidden = true;
      spk.setState(m.state === 'BUFFERING' ? 'spk-listening' : m.state === 'PAUSED' ? 'spk-idle' : 'spk-speaking');
      const kind = announcing ? 'tts' : cur ? cur.kind : null;
      kindEl.textContent = kind ? t(`now.kind.${kind}`) : '';
      title.textContent = announcing ? t('now.announcement') : (m.title || (cur && cur.title) || t('now.kind.url'));
      line.textContent = statusLine(m, q, announcing);
      setArt(announcing ? null : m.thumbnail || (cur && cur.thumbnail));
      transport.hidden = !op;
      prevB.hidden = nextB.hidden = !q;
      setPlayIcon(m.state !== 'PAUSED');
      prog.hidden = !m.duration;
      liveTag.hidden = !!m.duration || announcing || m.state !== 'PLAYING';
    }

    // volume: hidden while the speaker doesn't report one
    volume.hidden = st.volume == null;
    if (st.volume != null && Date.now() > volHoldUntil) paintVol(Math.round(st.volume * 100));

    renderQueue(q, m);
    tick();
  }

  function statusLine(m, q, announcing) {
    if (announcing) {
      if (st.resume_pending) return t('now.announcingThen', st.resume_pending);
      return q ? t('now.announcingResume') : t('now.announcing');
    }
    if (m.state === 'BUFFERING') return t('now.loading');
    if (m.state === 'PAUSED') return op ? t('now.paused') : t('now.pausedView');
    return q && q.name ? t('now.playingFrom', q.name) : t('now.playing');
  }

  function renderQueue(q, m) {
    if (!q || !q.items || !q.items.length) { queueBox.hidden = true; queueKey = ''; return; }
    queueBox.hidden = false;
    const key = JSON.stringify([q.index, q.shuffle, q.repeat, q.items.map((i) => i.id), showAll, m.state]);
    if (key === queueKey) return;
    queueKey = key;

    const tools = [];
    if (op) {
      const sh = iconBtn('shuffle', '', () => patchQueue({ shuffle: !q.shuffle }), 'np-tool');
      sh.replaceChildren(aicon('shuffle', 'sm'));
      sh.setAttribute('aria-pressed', String(!!q.shuffle));
      sh.setAttribute('aria-label', t(q.shuffle ? 'now.shuffleOn' : 'now.shuffleOff'));
      tip(sh, sh.getAttribute('aria-label'));
      const rep = q.repeat || 'off';
      const rLabel = t({ off: 'now.repeatOff', all: 'now.repeatAll', one: 'now.repeatOne' }[rep]);
      const rp = iconBtn('repeat', rLabel, () => patchQueue({ repeat: REPEAT_NEXT[rep] }), 'np-tool');
      rp.replaceChildren(aicon(rep === 'one' ? 'repeat-one' : 'repeat', 'sm'));
      rp.setAttribute('aria-pressed', String(rep !== 'off'));
      tools.push(sh, rp);
    }
    const head = h('div', { class: 'np-qhead' },
      h('div', { style: { minWidth: 0 } }, h('h2', { id: 'np-qh', class: 'np-qname' }, q.name || t('now.queue')),
        h('p', { class: 'small' }, t('now.position', q.index + 1, q.length))),
      tools.length ? h('div', { class: 'np-tools' }, tools) : null);

    const rows = q.items.map((it, i) => [it, i]);
    const shown = showAll ? rows : rows.slice(q.index, q.index + QUEUE_PEEK);
    const playing = m.state === 'PLAYING' || m.state === 'BUFFERING';
    const list = h('ol', { class: 'np-list list' }, shown.map(([it, i]) => {
      const isCur = i === q.index && ACTIVE.includes(m.state);
      const dur = it.duration ? fmtDur(it.duration) : '';
      let sub = it.kind === 'tts' ? t('now.announcement') : it.kind === 'radio' ? t('now.kind.radio') : dur || t(`now.kind.${it.kind}`);
      if (isCur) sub = t(playing ? 'now.subPlaying' : 'now.subPaused', dur);
      const thumb = it.thumbnail && it.kind !== 'tts'
        ? h('span', { class: 'np-thumb img' }, h('img', { src: it.thumbnail, alt: '', loading: 'lazy', referrerpolicy: 'no-referrer' }))
        : h('span', { class: 'np-thumb' }, kindIcon(it.kind, 'sm'));
      const inner = [thumb, h('span', { class: 'np-rtx' }, h('span', { class: 'np-rt' }, it.title), h('span', { class: 'np-rs' }, sub))];
      const cls = `np-row${isCur ? ' cur' : ''}`;
      return h('li', {}, op && !isCur
        ? h('button', { type: 'button', class: cls, 'aria-label': t('now.playItem', it.title), onclick: () => act('/queue/jump', { index: i }) }, inner)
        : h('div', { class: cls, 'aria-current': isCur ? 'true' : null }, inner));
    }));
    const more = q.items.length > QUEUE_PEEK || q.index > 0
      ? h('button', { type: 'button', class: 'linkbtn np-more', 'aria-expanded': String(showAll), onclick: () => { showAll = !showAll; queueKey = ''; renderQueue(q, m); } },
        showAll ? t('now.showNext') : t('now.showAll', q.items.length))
      : null;
    queueBox.replaceChildren(head, list, more);
  }

  function tick() {
    const m = st && st.media;
    if (err || !m || !m.duration || prog.hidden) return;
    let pos = m.position || 0;
    if (m.state === 'PLAYING') pos += (performance.now() - statusAt) / 1000;
    pos = Math.min(pos, m.duration);
    fill.style.width = `${(pos / m.duration) * 100}%`;
    tPos.textContent = fmtDur(pos);
    tLeft.textContent = `-${fmtDur(m.duration - pos)}`;
    bar.setAttribute('aria-valuemax', String(Math.round(m.duration)));
    bar.setAttribute('aria-valuenow', String(Math.round(pos)));
    bar.setAttribute('aria-valuetext', t('now.progressText', fmtDur(pos), fmtDur(m.duration)));
  }
  const ticker = setInterval(tick, 500);

  /* ----- relay health: from /status, or from the error body when the speaker is unreachable ----- */
  let relayFetchAt = 0;
  function renderRelay(r) {
    if (!admin || !r) { relayBox.hidden = true; return; }
    relayBox.hidden = false;
    const ok = r.broker_connected && r.online;
    const rows = [
      h('div', { class: 'row np-rhead' }, aicon('wifi', 'sm'), h('span', { class: 'np-rlbl' }, t('now.relay')),
        h('span', { class: ok ? 'np-ok' : 'np-bad' }, t(ok ? 'now.relayOnline' : 'now.relayOffline'))),
    ];
    const notes = [];
    if (!r.broker_connected) notes.push(t('now.relayBroker'));
    else if (r.online && r.speaker_connected === false) notes.push(t('now.relaySpeakerErr', r.speaker_error));
    notes.push(r.last_seen ? t('now.relaySeen', fmtRel(r.last_seen)) : t('now.relayNever'));
    if (r.rssi != null) notes.push(t('now.relaySignal', r.rssi));
    if (r.firmware_version) notes.push(t('now.relayFw', r.firmware_version));
    rows.push(h('div', { class: 'row np-rnotes' }, h('ul', {}, notes.map((n) => h('li', {}, n)))));
    relayBox.replaceChildren(...rows);
  }
  async function relayFromError() {
    if (!admin || Date.now() - relayFetchAt < 12000) return;
    relayFetchAt = Date.now();
    try {
      const r = await fetch('/status', { credentials: 'same-origin', cache: 'no-store', signal: ctx.signal, headers: { Accept: 'application/json' } });
      const data = await r.json().catch(() => null);
      renderRelay(data && data.relay);
    } catch { /* still unreachable; keep what we showed */ }
  }

  return {
    node,
    onStatus({ status, error }) {
      st = status && !error ? status : st;
      err = error || null;
      statusAt = performance.now();
      if (!error) renderRelay(status && status.relay);
      else relayFromError();
      update();
    },
    destroy() { clearInterval(ticker); },
  };
}
