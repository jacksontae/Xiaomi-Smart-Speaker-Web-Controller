// Settings (admin): speaker choice + discovery, default volume, TTS language, behaviour, port, cache.
import { h, icon, segmented, switchRow, field, busy, setRangeFill } from '../ui.js';
import { LANGS } from './announce.js';
import { thaiError } from '../api.js';

export default function settingsView(ctx) {
  let cfg = null;
  const body = h('div', {}, h('div', { class: 'skeleton', style: { minHeight: '220px' } }));
  const node = h('div', {}, h('div', { class: 'page-head' }, h('h1', {}, 'ตั้งค่าลำโพง')), body);

  function build() {
    const speaker = h('select', { class: 'select' });
    const opt = (ip, name, model) => h('option', { value: ip, dataset: { name } }, `${name} (${ip}${model ? `, ${model}` : ''})`);
    speaker.append(opt(cfg.speaker_ip, cfg.speaker_name));
    const scan = h('button', { class: 'btn', type: 'button' }, icon('radar', 'sm'), 'ค้นหาลำโพง');
    const scanNote = h('p', { class: 'hint', 'aria-live': 'polite' });
    scan.onclick = () => busy(scan, async () => {
      scanNote.textContent = 'กำลังค้นหาลำโพงในเครือข่าย ใช้เวลาประมาณ 5 วินาที';
      try {
        const list = await ctx.api('/speakers');
        const cur = speaker.value;
        speaker.replaceChildren(...list.map((s) => opt(s.ip, s.name, s.model)));
        if (!list.some((s) => s.ip === cfg.speaker_ip)) speaker.prepend(opt(cfg.speaker_ip, cfg.speaker_name));
        speaker.value = cur;
        scanNote.textContent = list.length ? `พบลำโพง ${list.length} เครื่อง เลือกจากรายการด้านบน` : 'ไม่พบลำโพง ตรวจว่าลำโพงเปิดอยู่และต่อ Wi‑Fi วงเดียวกัน';
      } catch (e) { scanNote.textContent = ''; ctx.fail(e); }
    });

    let keep = cfg.default_volume === null;
    const vol = h('input', { class: 'range', type: 'range', min: '0', max: '1', step: '0.05', value: String(cfg.default_volume ?? 0.3), 'aria-label': 'ระดับเสียงเริ่มต้น', disabled: keep });
    const volOut = h('output', { style: { minWidth: '3.2em', textAlign: 'right', fontWeight: 650 } });
    const syncVol = () => { setRangeFill(vol); volOut.textContent = keep ? 'ไม่เปลี่ยน' : `${Math.round(vol.value * 100)}%`; };
    vol.addEventListener('input', syncVol);
    const keepRow = switchRow('ใช้ระดับเสียงที่ลำโพงตั้งอยู่', keep, (e) => { keep = e.target.checked; vol.disabled = keep; syncVol(); });
    syncVol();

    let lang = cfg.tts_lang;
    const langSeg = segmented({ options: LANGS.some((l) => l.value === lang) ? LANGS : [...LANGS, { value: lang, label: lang }], value: lang, label: 'ภาษาเริ่มต้นของการประกาศ', onChange: (v) => { lang = v; } });
    let resume = cfg.resume_after_say;
    const resumeRow = switchRow('เล่นเพลงต่อหลังประกาศจบ', resume, (e) => { resume = e.target.checked; }, 'ถ้ากำลังเล่น YouTube อยู่ จะกลับไปเล่นต่อจากจุดเดิม');
    const cache = h('input', { class: 'input', type: 'number', inputMode: 'numeric', min: '1', value: String(cfg.cache_keep) });
    const port = h('input', { class: 'input', type: 'number', inputMode: 'numeric', min: '1024', max: '65535', value: String(cfg.port) });
    const base = h('input', { class: 'input', type: 'url', inputMode: 'url', value: cfg.public_base_url || '', placeholder: 'ตรวจหาอัตโนมัติ' });
    const err = h('p', { class: 'form-error', role: 'alert' });
    const save = h('button', { class: 'btn primary', type: 'submit' }, 'บันทึกการตั้งค่า');

    const form = h('form', {
      onsubmit: async (e) => {
        e.preventDefault();
        err.textContent = '';
        const o = speaker.selectedOptions[0];
        const next = {
          speaker_ip: speaker.value, speaker_name: o ? o.dataset.name : cfg.speaker_name,
          default_volume: keep ? null : +vol.value, tts_lang: lang, resume_after_say: resume,
          cache_keep: +cache.value, port: +port.value, public_base_url: base.value.trim() || null,
        };
        const changes = Object.fromEntries(Object.entries(next).filter(([k, v]) => v !== cfg[k]));
        if (!Object.keys(changes).length) { ctx.toast('ไม่มีอะไรเปลี่ยน'); return; }
        if (changes.port !== undefined && (changes.port < 1024 || changes.port > 65535)) { err.textContent = 'พอร์ตต้องอยู่ระหว่าง 1024 ถึง 65535'; return port.focus(); }
        await busy(save, async () => {
          try {
            const r = await ctx.api('/settings', { body: changes });
            if (r.restart) {
              ctx.toast(`บันทึกแล้ว บริการกำลังเริ่มใหม่ที่พอร์ต ${changes.port} จะพาไปหน้าใหม่ใน 5 วินาที`, 'ok', 6000);
              setTimeout(() => { location.port = String(changes.port); }, 5000);
              return;
            }
            cfg = r.settings;
            ctx.toast('บันทึกการตั้งค่าแล้ว', 'ok');
            ctx.refreshStatus();
          } catch (e2) { err.textContent = thaiError(e2, ctx.user); }
        });
      },
    },
    h('section', { class: 'panel glass' }, h('div', { class: 'panel-head' }, h('h2', {}, 'ลำโพง')),
      field('ลำโพงที่ใช้', speaker), h('div', { style: { display: 'grid', gap: '6px', justifyItems: 'start', marginTop: '-6px' } }, scan, scanNote)),
    h('section', { class: 'panel glass' }, h('div', { class: 'panel-head' }, h('h2', {}, 'เสียงและการประกาศ')),
      h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'ระดับเสียงเริ่มต้นตอนประกาศหรือเล่น'), h('div', { style: { display: 'flex', alignItems: 'center', gap: '12px' } }, vol, volOut)),
      keepRow,
      h('div', { class: 'field', style: { marginTop: '12px' } }, h('span', { class: 'field-label' }, 'ภาษาเริ่มต้นของการประกาศ'), langSeg),
      resumeRow),
    h('section', { class: 'panel glass' }, h('div', { class: 'panel-head' }, h('h2', {}, 'ขั้นสูง')),
      field('จำนวนเพลง YouTube ที่เก็บไว้ในเครื่อง', cache, 'เพลงที่เก็บไว้เล่นซ้ำได้ทันทีโดยไม่ต้องดาวน์โหลดใหม่'),
      field('พอร์ตของบริการ', port, 'เปลี่ยนแล้วบริการจะเริ่มใหม่ และที่อยู่หน้านี้จะเปลี่ยนตาม'),
      field('ที่อยู่ที่ลำโพงใช้ดึงเสียง', base, 'เว้นว่างไว้ ยกเว้นลำโพงเล่นเสียงไม่ได้เพราะตรวจที่อยู่ผิด เช่น http://192.168.2.10:8090')),
    err,
    h('div', { style: { display: 'flex', justifyContent: 'flex-end' } }, save));
    body.replaceChildren(form);
  }

  ctx.api('/settings').then((r) => { cfg = r; build(); }).catch((e) => { ctx.fail(e); body.replaceChildren(); });
  return { node };
}
