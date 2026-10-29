// Announce: compose text, pick a language, tap a quick phrase to announce it.
import { h, icon, segmented, busy } from '../ui.js';

export const LANGS = [
  { value: 'th', label: 'ไทย' },
  { value: 'en', label: 'English' },
  { value: 'zh-CN', label: '中文' },
  { value: 'ja', label: '日本語' },
];
const langLabel = (v) => (LANGS.find((l) => l.value === v) || { label: v }).label;
const MAX = 1000;

function savedLang() { try { return localStorage.getItem('speakerLang'); } catch { return null; } }
function saveLang(v) { try { localStorage.setItem('speakerLang', v); } catch { /* private mode */ } }

export default function announceView(ctx) {
  const op = ctx.can('operator');
  let lang = savedLang() || 'th';
  let phrases = [];
  let editing = false;

  const text = h('textarea', { class: 'textarea', id: 'say-text', rows: 4, maxLength: MAX, placeholder: 'พิมพ์ข้อความ เช่น ประชุมใน 5 นาที เชิญที่ห้องประชุมใหญ่', disabled: !op });
  const counter = h('span', { class: 'counter num', 'aria-live': 'off' }, `0/${MAX}`);
  const langSeg = segmented({ options: LANGS, value: lang, label: 'ภาษาที่ใช้อ่าน', onChange: (v) => { lang = v; saveLang(v); } });
  const sayBtn = h('button', { class: 'btn primary', type: 'submit', disabled: !op }, icon('announce', 'sm'), 'ประกาศ');
  const saveBtn = h('button', { class: 'btn quiet', type: 'button', disabled: !op, onclick: () => addPhrase() }, icon('plus', 'sm'), 'บันทึกเป็นวลีด่วน');
  text.addEventListener('input', () => { counter.textContent = `${text.value.length}/${MAX}`; });

  const compose = h('form', {
    class: 'panel glass',
    onsubmit: async (e) => { e.preventDefault(); if (!text.value.trim()) { text.focus(); return; } await say(text.value.trim(), lang, sayBtn); },
  },
  h('label', { for: 'say-text', class: 'field-label', style: { display: 'block', marginBottom: '8px' } }, 'ข้อความที่จะประกาศ'),
  text,
  h('div', { style: { margin: '12px 0 0' } }, langSeg),
  h('div', { class: 'compose-actions' }, saveBtn, h('div', { class: 'send' }, counter, sayBtn)));

  const editBtn = h('button', { class: 'btn quiet sm', type: 'button', 'aria-pressed': 'false', onclick: () => { editing = !editing; editBtn.setAttribute('aria-pressed', String(editing)); editBtn.textContent = editing ? 'เสร็จ' : 'แก้ไข'; draw(); } }, 'แก้ไข');
  const list = h('div', { class: 'phrases', role: 'list' });
  const phrasePanel = h('section', { class: 'panel glass', 'aria-labelledby': 'ph-h' },
    h('div', { class: 'panel-head' }, h('div', {}, h('h2', { id: 'ph-h' }, 'วลีด่วน'), h('p', { class: 'muted', style: { fontSize: 'var(--fs-sm)' } }, op ? 'แตะเพื่อประกาศทันที' : 'วลีที่ทีมบันทึกไว้')), op ? editBtn : null),
    list);

  const node = h('div', {},
    h('div', { class: 'page-head' }, h('h1', {}, 'ประกาศ')),
    op ? null : h('div', { class: 'note' }, icon('info'), h('span', {}, 'บัญชีผู้ชมดูวลีได้ แต่ประกาศไม่ได้ ขอสิทธิ์ผู้ควบคุมจากผู้ดูแล')),
    compose, phrasePanel);

  async function say(t, lg, btn) {
    return busy(btn, async () => {
      try {
        const r = await ctx.api('/say', { body: { text: t, lang: lg } });
        ctx.toast(r && r.will_resume ? `ประกาศแล้ว จากนั้นจะเล่น “${r.will_resume}” ต่อ` : 'ประกาศแล้ว', 'ok');
        ctx.refreshStatus();
        return true;
      } catch (e) { ctx.fail(e); return false; }
    });
  }

  async function addPhrase() {
    const t = text.value.trim();
    if (!t) { text.focus(); ctx.toast('พิมพ์ข้อความก่อน แล้วค่อยบันทึกเป็นวลีด่วน'); return; }
    await busy(saveBtn, async () => {
      try {
        const p = await ctx.api('/phrases', { body: { text: t, lang } });
        phrases.push(p); draw();
        ctx.toast('บันทึกวลีด่วนแล้ว', 'ok');
      } catch (e) { ctx.fail(e); }
    });
  }

  async function removePhrase(p) {
    try {
      await ctx.api(`/phrases/${p.id}`, { method: 'DELETE' });
    } catch (e) { ctx.fail(e); return; }
    phrases = phrases.filter((x) => x.id !== p.id);
    draw();
    const t = ctx.toast(`ลบ “${p.text.slice(0, 30)}” แล้ว`, 'ok', 6000);
    t.append(h('button', {
      class: 'btn quiet sm', type: 'button',
      onclick: async () => {
        t.remove();
        try { const np = await ctx.api('/phrases', { body: { text: p.text, lang: p.lang } }); phrases.push(np); draw(); } catch (e) { ctx.fail(e); }
      },
    }, 'เลิกทำ'));
  }

  function draw() {
    if (!phrases.length) {
      list.replaceChildren(h('div', { class: 'empty', style: { width: '100%' } }, icon('announce'), h('p', {}, op ? 'ยังไม่มีวลีด่วน พิมพ์ข้อความด้านบนแล้วกด “บันทึกเป็นวลีด่วน”' : 'ยังไม่มีวลีด่วน')));
      return;
    }
    list.replaceChildren(...phrases.map((p) => {
      const chip = h(op && !editing ? 'button' : 'div', {
        type: op && !editing ? 'button' : null, class: 'phrase glass',
        title: p.created_by ? `บันทึกโดย ${p.created_by}` : null,
        onclick: op && !editing ? async () => {
          chip.classList.remove('sent');
          if (await say(p.text, p.lang, chip)) { void chip.offsetWidth; chip.classList.add('sent'); }
        } : null,
      }, h('span', {}, p.text), p.lang !== 'th' ? h('span', { class: 'lang' }, langLabel(p.lang)) : null);
      const wrap = h('div', { class: 'phrase-wrap', role: 'listitem' }, chip);
      if (editing) wrap.append(h('button', { type: 'button', class: 'phrase-del', 'aria-label': `ลบวลี ${p.text}`, onclick: () => removePhrase(p) }, icon('close')));
      return wrap;
    }));
  }

  list.append(h('div', { class: 'skeleton', style: { width: '100%' } }));
  ctx.api('/phrases').then((r) => { phrases = r || []; draw(); }).catch((e) => { ctx.fail(e); list.replaceChildren(); });
  if (!savedLang()) {
    // Default to the service's TTS language (from /status, readable by every role) until the user picks one.
    let applied = false;
    ctx.onStatus((s) => {
      const l = s.status && s.status.tts_lang;
      if (!applied && l && LANGS.some((x) => x.value === l)) { applied = true; lang = l; langSeg.setValue(l); }
    });
  }
  return { node };
}
