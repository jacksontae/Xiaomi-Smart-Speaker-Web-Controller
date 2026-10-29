// Now playing: artwork, title, progress (ticks locally between polls), transport, volume, queue.
import { h, icon, iconBtn, fmtDur, setRangeFill, inlineConfirm, thumbEl, kindIcon } from '../ui.js';
import { ROLE_TH } from '../api.js';

const STATE_TH = { PLAYING: 'กำลังเล่น', PAUSED: 'พักไว้', BUFFERING: 'กำลังโหลด', IDLE: 'ว่าง', UNKNOWN: 'ว่าง' };
const REPEAT = { off: { next: 'all', icon: 'repeat', label: 'เล่นซ้ำ: ปิด' }, all: { next: 'one', icon: 'repeat', label: 'เล่นซ้ำ: ทั้งคิว' }, one: { next: 'off', icon: 'repeat-one', label: 'เล่นซ้ำ: เพลงเดียว' } };

export default function nowView(ctx) {
  const op = ctx.can('operator');
  let s = null; // last status
  let volHoldUntil = 0;
  let showAllQueue = false;
  let lastQueueKey = '';

  const dot = h('span', { class: 'dot' });
  const speakerLabel = h('span', {}, 'กำลังเชื่อมต่อลำโพง…');
  const chip = h('div', { class: 'chip glass', role: 'status' }, dot, speakerLabel);
  const top = h('div', { class: 'np-top' }, chip, ctx.can('viewer') && !op ? h('span', { class: 'badge' }, `${ROLE_TH.viewer}: ดูได้อย่างเดียว`) : null);

  const art = h('div', { class: 'np-art glass' });
  const title = h('h2', { class: 'np-title' }, ' ');
  const sub = h('div', { class: 'np-sub' });
  const info = h('div', { class: 'np-info', 'aria-live': 'polite' }, title, sub);

  const fill = h('i');
  const tPos = h('span'); const tDur = h('span');
  const progress = h('div', { class: 'progress' }, h('div', { class: 'bar', role: 'progressbar', 'aria-label': 'ตำแหน่งที่เล่น', 'aria-valuemin': '0' }, fill), h('div', { class: 'times' }, tPos, tDur));
  const bar = progress.firstChild;

  const prev = iconBtn('prev', 'เพลงก่อนหน้า', () => act('/queue/prev'));
  const playBtn = iconBtn('play', 'เล่นต่อ', () => togglePlay(), 'play');
  const next = iconBtn('next', 'เพลงถัดไป', () => act('/queue/next'));
  const stop = iconBtn('stop', 'หยุดและล้างคิว', () => act('/stop'));
  const transport = h('div', { class: 'transport glass' }, prev, playBtn, next, stop);

  const vol = h('input', { class: 'range', type: 'range', min: '0', max: '1', step: '0.01', value: '0.5', 'aria-label': 'ระดับเสียง', disabled: !op });
  const volOut = h('output', {}, '');
  const volume = h('div', { class: 'volume glass' }, icon('vol-low', 'sm'), vol, volOut);
  let volTimer = null, volLastSent = 0;
  const sendVol = () => { volLastSent = Date.now(); ctx.api('/volume', { body: { level: +vol.value } }).catch((e) => ctx.fail(e)); };
  vol.addEventListener('input', () => {
    volHoldUntil = Date.now() + 2500;
    setRangeFill(vol); volOut.textContent = `${Math.round(vol.value * 100)}%`;
    vol.setAttribute('aria-valuetext', `${Math.round(vol.value * 100)} เปอร์เซ็นต์`);
    clearTimeout(volTimer);
    const wait = Math.max(0, 300 - (Date.now() - volLastSent));
    volTimer = setTimeout(sendVol, wait);
  });

  const queueBox = h('section', { class: 'panel glass', 'aria-label': 'คิวเพลง' });
  const idleBox = h('div', { class: 'idle-actions' },
    h('a', { class: 'btn primary', href: '#/playlists' }, icon('playlists', 'sm'), 'เลือกเพลย์ลิสต์'),
    ctx.can('operator') ? h('a', { class: 'btn', href: '#/youtube' }, icon('search', 'sm'), 'ค้นหา YouTube') : null,
    ctx.can('operator') ? h('a', { class: 'btn', href: '#/announce' }, icon('announce', 'sm'), 'ประกาศ') : null);
  const retry = h('button', { class: 'btn primary', type: 'button', onclick: () => ctx.refreshStatus() }, icon('refresh', 'sm'), 'ลองเชื่อมต่ออีกครั้ง');

  const col = h('div', { class: 'np-col' }, info, idleBox, retry, progress, op ? transport : null, volume, queueBox);
  const node = h('div', { class: 'np' }, h('h1', { class: 'sr-only' }, 'กำลังเล่น'), top, art, col);

  async function act(path, body) {
    try { await ctx.api(path, { method: 'POST', body }); } catch (e) { ctx.fail(e); }
    ctx.refreshStatus();
  }
  async function togglePlay() {
    const st = s?.status?.media?.state;
    const playing = st === 'PLAYING' || st === 'BUFFERING';
    setPlayIcon(!playing);
    await act(playing ? '/pause' : '/resume');
  }
  function setPlayIcon(playing) {
    playBtn.replaceChildren(icon(playing ? 'pause' : 'play', 'fill'));
    playBtn.setAttribute('aria-label', playing ? 'พัก' : 'เล่นต่อ');
    playBtn.title = playBtn.getAttribute('aria-label');
  }

  let artKey = null;
  function setArt(kind, src) {
    const key = `${kind}|${src}`;
    if (key === artKey) return;
    artKey = key;
    const glyph = { idle: 'now', offline: 'offline', announce: 'announce', stream: 'wave', music: 'note' }[kind] || 'note';
    if (src) {
      const img = h('img', { src, alt: '' });
      img.addEventListener('error', () => art.replaceChildren(icon(glyph, 'glyph')), { once: true });
      art.replaceChildren(img);
    } else art.replaceChildren(icon(glyph, 'glyph'));
  }

  function renderQueue(q, media) {
    if (!q) { queueBox.hidden = true; lastQueueKey = ''; return; }
    queueBox.hidden = false;
    const key = JSON.stringify([q.index, q.shuffle, q.repeat, q.items.map((i) => i.id), showAllQueue, op]);
    if (key === lastQueueKey) return;
    lastQueueKey = key;
    const r = REPEAT[q.repeat] || REPEAT.off;
    const shuffleBtn = iconBtn('shuffle', q.shuffle ? 'สุ่มลำดับ: เปิด' : 'สุ่มลำดับ: ปิด', () => act2({ shuffle: !q.shuffle }), q.shuffle ? 'on' : '');
    shuffleBtn.setAttribute('aria-pressed', String(q.shuffle));
    const repeatBtn = iconBtn(r.icon, r.label, () => act2({ repeat: r.next }), q.repeat !== 'off' ? 'on' : '');
    const clearBtn = iconBtn('trash', 'ล้างคิว', () => inlineConfirm(clearBtn.closest('.panel-head'), {
      text: 'ล้างคิวและหยุดเล่น?', confirmLabel: 'ล้างคิว',
      onConfirm: async () => { try { await ctx.api('/queue/clear', { method: 'POST' }); } catch (e) { ctx.fail(e); throw e; } ctx.refreshStatus(); },
    }));
    const head = h('div', { class: 'panel-head' },
      h('div', {}, h('h2', {}, q.name || 'คิวเพลง'), h('div', { class: 'muted', style: { fontSize: 'var(--fs-sm)' } }, `รายการที่ ${q.index + 1} จาก ${q.length}`)),
      op ? h('div', { class: 'queue-tools' }, shuffleBtn, repeatBtn, clearBtn) : null);
    const upcoming = showAllQueue ? q.items.map((it, i) => [it, i]) : q.items.map((it, i) => [it, i]).slice(q.index, q.index + 5);
    const list = h('ol', { class: 'list' }, upcoming.map(([it, i]) => {
      const inner = [thumbEl(it.thumbnail, kindIcon(it.kind)),
        h('span', { class: 'body' }, h('span', { class: 'title' }, it.title), h('span', { class: 'sub' }, i === q.index ? h('span', {}, 'กำลังเล่น') : null, it.duration ? h('span', { class: 'num' }, fmtDur(it.duration)) : h('span', {}, it.kind === 'tts' ? 'ข้อความประกาศ' : 'ลิงก์เสียง')))];
      const cls = `row ${i === q.index ? 'current' : ''}`;
      return h('li', {}, op && i !== q.index
        ? h('button', { type: 'button', class: cls, onclick: () => act('/queue/jump', { index: i }), 'aria-label': `เล่น ${it.title}` }, inner)
        : h('div', { class: cls, 'aria-current': i === q.index ? 'true' : null }, inner));
    }));
    const more = q.items.length > 5 ? h('button', { type: 'button', class: 'btn quiet sm', onclick: () => { showAllQueue = !showAllQueue; renderQueue(q, media); } }, showAllQueue ? 'แสดงเฉพาะถัดไป' : `ดูทั้งคิว (${q.items.length})`) : null;
    queueBox.replaceChildren(...[head, list, more].filter(Boolean));
  }
  async function act2(body) {
    try { await ctx.api('/queue', { method: 'PATCH', body }); } catch (e) { ctx.fail(e); }
    ctx.refreshStatus();
  }

  function update(st) {
    s = st;
    const off = !!st.statusErr;
    dot.classList.toggle('off', off);
    retry.hidden = !off;
    if (off) {
      const is503 = st.statusErr.status === 503;
      speakerLabel.textContent = is503 ? 'ลำโพงไม่ตอบสนอง' : 'เชื่อมต่อเซิร์ฟเวอร์ไม่ได้';
      setArt('offline');
      title.textContent = is503 ? 'ติดต่อลำโพงไม่ได้' : 'เชื่อมต่อเซิร์ฟเวอร์ไม่ได้';
      sub.replaceChildren(h('span', {}, is503 ? 'ตรวจว่าลำโพงเปิดอยู่และต่อ Wi‑Fi วงเดียวกับเซิร์ฟเวอร์ แล้วลองอีกครั้ง' : 'ตรวจว่าเครื่องนี้ยังต่อเครือข่ายเดียวกับเซิร์ฟเวอร์'));
      progress.hidden = true; transport.hidden = true; volume.hidden = true; idleBox.hidden = true; queueBox.hidden = true;
      return;
    }
    const status = st.status;
    const m = status.media || {};
    speakerLabel.textContent = status.speaker;
    const active = ['PLAYING', 'PAUSED', 'BUFFERING'].includes(m.state);
    const announcing = active && m.title === 'Announcement';
    const q = status.queue;
    volume.hidden = false;
    if (!active) {
      setArt('idle');
      title.textContent = 'ลำโพงว่างอยู่';
      sub.replaceChildren(h('span', {}, op ? 'เลือกเพลย์ลิสต์ ค้นเพลงจาก YouTube หรือประกาศข้อความ' : 'ยังไม่มีอะไรเล่นอยู่ตอนนี้'));
      progress.hidden = true; transport.hidden = true; idleBox.hidden = !op;
    } else {
      idleBox.hidden = true; transport.hidden = false;
      setArt(announcing ? 'announce' : m.duration ? 'music' : 'stream', announcing ? null : m.thumbnail);
      title.textContent = announcing ? 'กำลังประกาศ' : (m.title || 'เสียงจากลิงก์');
      sub.replaceChildren(...[h('span', {}, STATE_TH[m.state] || ''),
        status.resume_pending ? h('span', {}, `ต่อด้วย ${status.resume_pending}`) : null,
        q ? h('span', {}, `จาก ${q.name}`) : null].filter(Boolean));
      progress.hidden = !m.duration;
      setPlayIcon(m.state !== 'PAUSED');
    }
    prev.hidden = next.hidden = !q;
    if (Date.now() > volHoldUntil) {
      vol.value = status.volume ?? 0;
      setRangeFill(vol);
      volOut.textContent = `${Math.round((status.volume ?? 0) * 100)}%`;
      vol.setAttribute('aria-valuetext', `${Math.round((status.volume ?? 0) * 100)} เปอร์เซ็นต์`);
    }
    renderQueue(q, m);
    tick();
  }

  function tick() {
    const m = s?.status?.media;
    if (!m || !m.duration || s.statusErr) return;
    let pos = m.position || 0;
    if (m.state === 'PLAYING') pos += (performance.now() - s.statusAt) / 1000;
    pos = Math.min(pos, m.duration);
    fill.style.width = `${(pos / m.duration) * 100}%`;
    tPos.textContent = fmtDur(pos);
    tDur.textContent = `-${fmtDur(m.duration - pos)}`;
    bar.setAttribute('aria-valuemax', String(Math.round(m.duration)));
    bar.setAttribute('aria-valuenow', String(Math.round(pos)));
    bar.setAttribute('aria-valuetext', `${fmtDur(pos)} จาก ${fmtDur(m.duration)}`);
  }
  const ticker = setInterval(tick, 500);

  progress.hidden = true; transport.hidden = true; volume.hidden = true; idleBox.hidden = true; queueBox.hidden = true; retry.hidden = true;
  setArt('idle');
  ctx.onStatus(update);
  return { node, destroy: () => clearInterval(ticker) };
}
