// Playlists: grid of covers; detail with play options, drag/keyboard reorder, add items (YouTube / URL / TTS).
import { h, icon, iconBtn, fmtDur, fmtTotal, fmtRel, thumbEl, kindIcon, openSheet, segmented, inlineConfirm, field, busy } from '../ui.js';
import { LANGS } from './announce.js';

const REPEAT_OPTS = [{ value: 'off', label: 'ไม่ซ้ำ' }, { value: 'all', label: 'ซ้ำทั้งหมด' }, { value: 'one', label: 'ซ้ำเพลงเดียว' }];

export default function playlistsView(ctx, params) {
  return params[0] ? detailView(ctx, +params[0]) : listView(ctx);
}

function cover(src, cls = '') {
  const box = h('div', { class: `pl-cover ${cls}` });
  if (src) {
    const img = h('img', { src, alt: '', loading: 'lazy' });
    img.addEventListener('error', () => box.replaceChildren(icon('playlists')), { once: true });
    box.append(img);
  } else box.append(icon('playlists'));
  return box;
}
const itemCount = (n) => `${n} รายการ`;

/* ---------- create playlist sheet ---------- */
export function createPlaylistSheet(ctx, onCreated) {
  openSheet({
    title: 'เพลย์ลิสต์ใหม่',
    build(body, sheet) {
      const name = h('input', { class: 'input', required: true, maxLength: 80, placeholder: 'เช่น เพลงเปิดร้านตอนเช้า' });
      const btn = h('button', { class: 'btn primary wide', type: 'submit' }, 'สร้างเพลย์ลิสต์');
      body.append(h('form', {
        onsubmit: async (e) => {
          e.preventDefault();
          if (!name.value.trim()) return name.focus();
          await busy(btn, async () => {
            try { const p = await ctx.api('/playlists', { body: { name: name.value.trim() } }); sheet.close(); onCreated(p); } catch (e2) { ctx.fail(e2); }
          });
        },
      }, field('ชื่อเพลย์ลิสต์', name), btn));
    },
  });
}

/* ---------- pick a playlist for an item (used by YouTube) ---------- */
export function pickPlaylistSheet(ctx, item) {
  openSheet({
    title: 'เพิ่มลงเพลย์ลิสต์',
    build(body, sheet) {
      body.append(h('p', { class: 'muted', style: { marginBottom: '12px' } }, item.title));
      const list = h('div', {}, h('div', { class: 'skeleton' }), h('div', { class: 'skeleton' }));
      body.append(list);
      const add = async (pl, btn) => busy(btn, async () => {
        try {
          await ctx.api(`/playlists/${pl.id}/items`, { body: { kind: item.kind, source: item.source } });
          ctx.toast(`เพิ่มลง “${pl.name}” แล้ว`, 'ok');
          sheet.close();
        } catch (e) { ctx.fail(e); }
      });
      ctx.api('/playlists').then((pls) => {
        const newBtn = h('button', { type: 'button', class: 'row', onclick: () => { sheet.close(); createPlaylistSheet(ctx, (p) => add(p)); } },
          h('div', { class: 'thumb' }, icon('plus')), h('span', { class: 'body' }, h('span', { class: 'title' }, 'สร้างเพลย์ลิสต์ใหม่')));
        list.replaceChildren(h('div', { class: 'list' }, newBtn, pls.map((pl) => {
          const b = h('button', { type: 'button', class: 'row', onclick: () => add(pl, b) },
            thumbEl(pl.cover, 'playlists'), h('span', { class: 'body' }, h('span', { class: 'title' }, pl.name), h('span', { class: 'sub' }, h('span', {}, itemCount(pl.item_count)))));
          return b;
        })));
      }).catch((e) => { ctx.fail(e); sheet.close(); });
    },
  });
}

/* ---------- list ---------- */
function listView(ctx) {
  const op = ctx.can('operator');
  const grid = h('div', { class: 'pl-grid' }, [1, 2, 3, 4].map(() => h('div', { class: 'skeleton', style: { aspectRatio: '0.8' } })));
  const newBtn = op ? h('button', { class: 'btn primary', type: 'button', onclick: () => createPlaylistSheet(ctx, (p) => ctx.go(`#/playlists/${p.id}`)) }, icon('plus', 'sm'), 'สร้าง') : null;
  const node = h('div', {}, h('div', { class: 'page-head' }, h('h1', {}, 'เพลย์ลิสต์'), h('div', { class: 'actions' }, newBtn)), grid);
  ctx.api('/playlists').then((pls) => {
    if (!pls.length) {
      grid.replaceWith(h('div', { class: 'panel glass empty' }, icon('playlists'), h('h2', {}, 'ยังไม่มีเพลย์ลิสต์'),
        h('p', {}, op ? 'สร้างเพลย์ลิสต์แรก แล้วเพิ่มเพลงจาก YouTube ลิงก์เสียง หรือข้อความประกาศ' : 'เมื่อทีมสร้างเพลย์ลิสต์ จะเห็นได้ที่นี่'),
        op ? h('button', { class: 'btn primary', type: 'button', onclick: () => newBtn.click() }, icon('plus', 'sm'), 'สร้างเพลย์ลิสต์') : null));
      return;
    }
    grid.replaceChildren(...pls.map((pl) => h('a', { class: 'pl-card glass', href: `#/playlists/${pl.id}` },
      cover(pl.cover), h('div', { class: 'name' }, pl.name),
      h('div', { class: 'meta' }, itemCount(pl.item_count), pl.total_duration ? h('span', {}, `, ${fmtTotal(pl.total_duration)}`) : null))));
  }).catch((e) => { ctx.fail(e); grid.replaceChildren(); });
  return { node };
}

/* ---------- detail ---------- */
function detailView(ctx, id) {
  const op = ctx.can('operator');
  let pl = null;
  let editing = false;
  let shuffle = false;
  let repeat = 'off';
  let playingId = null;
  let dragging = false;

  const back = h('a', { class: 'btn quiet back', href: '#/playlists' }, icon('back', 'sm'), 'เพลย์ลิสต์');
  const hero = h('div', { class: 'pl-hero' }, h('div', { class: 'skeleton', style: { aspectRatio: '1' } }), h('div', {}));
  const live = h('p', { class: 'sr-only', 'aria-live': 'polite' });
  const listEl = h('ol', { class: 'list items' });
  const itemsPanel = h('section', { class: 'panel glass', 'aria-label': 'รายการในเพลย์ลิสต์' }, h('div', { class: 'skeleton' }), h('div', { class: 'skeleton' }));

  const playBtn = h('button', { class: 'btn primary', type: 'button', onclick: () => play(0, playBtn) }, icon('play', 'fill sm'), 'เล่น');
  const shuffleBtn = h('button', { class: 'btn', type: 'button', 'aria-pressed': 'false', onclick: () => { shuffle = !shuffle; shuffleBtn.setAttribute('aria-pressed', String(shuffle)); } }, icon('shuffle', 'sm'), h('span', {}, 'สุ่มลำดับ'));
  const repeatSeg = segmented({ options: REPEAT_OPTS, value: repeat, label: 'การเล่นซ้ำ', onChange: (v) => { repeat = v; } });
  const playRow = op ? h('div', { class: 'pl-play' }, playBtn, shuffleBtn, repeatSeg) : null;

  const editBtn = h('button', { class: 'btn quiet sm', type: 'button', 'aria-pressed': 'false', onclick: () => { editing = !editing; editBtn.setAttribute('aria-pressed', String(editing)); editBtn.textContent = editing ? 'เสร็จ' : 'จัดเรียง'; drawItems(); } }, 'จัดเรียง');
  const addBtn = h('button', { class: 'btn sm', type: 'button', onclick: () => addItemSheet() }, icon('plus', 'sm'), 'เพิ่ม');
  const moreBtn = iconBtn('more', 'ตั้งชื่อใหม่หรือลบเพลย์ลิสต์', () => optionsSheet());

  const node = h('div', {}, h('div', { class: 'page-head' }, back, op ? h('div', { class: 'actions' }, moreBtn) : null), hero, playRow, itemsPanel, live);

  async function load() {
    try { pl = await ctx.api(`/playlists/${id}`); } catch (e) { ctx.fail(e); if (e.status === 404) ctx.go('#/playlists'); return; }
    drawHero(); drawItems();
  }
  function drawHero() {
    const total = pl.items.reduce((a, i) => a + (i.duration || 0), 0);
    hero.replaceChildren(cover(pl.items.find((i) => i.thumbnail)?.thumbnail),
      h('div', {}, h('h1', {}, pl.name), h('p', { class: 'muted' }, itemCount(pl.items.length), total ? `, ${fmtTotal(total)}` : ''), h('p', { class: 'muted', style: { fontSize: 'var(--fs-sm)' } }, `แก้ไขล่าสุด ${fmtRel(pl.updated_at)}`)));
    playBtn.disabled = !pl.items.length;
    document.title = `${pl.name} — ลำโพง`;
  }

  function drawItems() {
    listEl.classList.toggle('editing', editing);
    const head = h('div', { class: 'panel-head' }, h('h2', {}, 'รายการ'), op ? h('div', { class: 'actions', style: { display: 'flex', gap: '6px' } }, pl.items.length > 1 ? editBtn : null, addBtn) : null);
    if (!pl.items.length) {
      itemsPanel.replaceChildren(head, h('div', { class: 'empty' }, icon('note'), h('p', {}, op ? 'ยังไม่มีรายการ กด “เพิ่ม” เพื่อใส่เพลงจาก YouTube ลิงก์เสียง หรือข้อความประกาศ' : 'ยังไม่มีรายการ')));
      return;
    }
    listEl.replaceChildren(...pl.items.map((it, i) => itemRow(it, i)));
    itemsPanel.replaceChildren(head, listEl);
  }

  function itemRow(it, i) {
    const sub = h('span', { class: 'sub' }, h('span', {}, it.kind === 'tts' ? 'ข้อความประกาศ' : it.kind === 'url' ? 'ลิงก์เสียง' : 'YouTube'), it.duration ? h('span', { class: 'num' }, fmtDur(it.duration)) : null, it.id === playingId ? h('span', {}, 'กำลังเล่น') : null);
    const li = h('li', { class: `row ${it.id === playingId ? 'current' : ''}`, dataset: { id: it.id } });
    if (op && !editing) li.append(h('button', { type: 'button', class: 'play-hit', 'aria-label': `เล่นจาก ${it.title}`, onclick: () => play(i) }));
    if (editing) {
      const grip = h('span', { class: 'iconbtn plain grip', 'aria-hidden': 'true', title: 'ลากเพื่อย้าย' }, icon('grip'));
      grip.addEventListener('pointerdown', (e) => startDrag(e, li, grip));
      li.append(grip);
    }
    li.append(thumbEl(it.thumbnail, kindIcon(it.kind)), h('span', { class: 'body' }, h('span', { class: 'title' }, it.title), sub));
    if (editing) {
      const up = iconBtn('up', `เลื่อนขึ้น: ${it.title}`, () => moveItem(i, i - 1, 'up'));
      const down = iconBtn('down', `เลื่อนลง: ${it.title}`, () => moveItem(i, i + 1, 'down'));
      up.disabled = i === 0; down.disabled = i === pl.items.length - 1;
      const del = iconBtn('trash', `ลบ ${it.title}`, () => inlineConfirm(li, {
        text: `ลบ “${it.title}” ออกจากเพลย์ลิสต์?`, confirmLabel: 'ลบ',
        onConfirm: async () => {
          try { await ctx.api(`/playlists/${id}/items/${it.id}`, { method: 'DELETE' }); } catch (e) { ctx.fail(e); throw e; }
          pl.items = pl.items.filter((x) => x.id !== it.id); drawHero(); drawItems();
          live.textContent = `ลบ ${it.title} แล้ว`;
        },
      }));
      li.append(h('span', { class: 'trail' }, up, down, del));
    }
    return li;
  }

  async function saveOrder(prevItems) {
    try { await ctx.api(`/playlists/${id}/order`, { method: 'PUT', body: { item_ids: pl.items.map((i) => i.id) } }); } catch (e) {
      ctx.fail(e); pl.items = prevItems; drawItems(); load();
    }
  }
  function moveItem(from, to, focusDir) {
    if (to < 0 || to >= pl.items.length || from === to) return;
    const prevItems = [...pl.items];
    const [it] = pl.items.splice(from, 1);
    pl.items.splice(to, 0, it);
    drawItems();
    live.textContent = `ย้าย ${it.title} ไปลำดับที่ ${to + 1}`;
    if (focusDir) {
      const row = listEl.children[to];
      const btn = row && row.querySelector(`[aria-label^="${focusDir === 'up' ? 'เลื่อนขึ้น' : 'เลื่อนลง'}"]`);
      (btn && !btn.disabled ? btn : row.querySelector('.trail button:not(:disabled)'))?.focus();
    }
    saveOrder(prevItems);
  }

  function startDrag(e, li, grip) {
    e.preventDefault();
    const rows = [...listEl.children];
    const from = rows.indexOf(li);
    const rects = rows.map((r) => { const b = r.getBoundingClientRect(); return { top: b.top + scrollY, h: b.height }; });
    const startY = e.pageY;
    let to = from;
    grip.setPointerCapture(e.pointerId);
    li.classList.add('dragging');
    dragging = true;
    const onMove = (ev) => {
      if (ev.clientY < 90) scrollBy(0, -10); else if (ev.clientY > innerHeight - 110) scrollBy(0, 10);
      const dy = ev.pageY - startY;
      li.style.transform = `translateY(${dy}px)`;
      const center = rects[from].top + rects[from].h / 2 + dy;
      to = from;
      for (let i = from + 1; i < rects.length; i++) if (center > rects[i].top + rects[i].h / 2) to = i;
      if (to === from) for (let i = from - 1; i >= 0; i--) if (center < rects[i].top + rects[i].h / 2) to = i;
      rows.forEach((r, i) => {
        if (i === from) return;
        let shift = 0;
        if (from < to && i > from && i <= to) shift = -rects[from].h;
        if (to < from && i >= to && i < from) shift = rects[from].h;
        r.style.transform = shift ? `translateY(${shift}px)` : '';
      });
    };
    const onUp = () => {
      grip.removeEventListener('pointermove', onMove);
      grip.removeEventListener('pointerup', onUp);
      grip.removeEventListener('pointercancel', onUp);
      rows.forEach((r) => { r.style.transform = ''; });
      li.classList.remove('dragging');
      dragging = false;
      if (to !== from) moveItem(from, to);
    };
    grip.addEventListener('pointermove', onMove);
    grip.addEventListener('pointerup', onUp);
    grip.addEventListener('pointercancel', onUp);
  }

  async function play(index, btn) {
    try {
      await busy(btn, () => ctx.api(`/playlists/${id}/play`, { body: { start_index: index, shuffle, repeat } }));
      ctx.toast(`กำลังเล่น “${pl.name}”`, 'ok');
      ctx.refreshStatus();
    } catch (e) { ctx.fail(e, { 409: 'เพลย์ลิสต์นี้ยังไม่มีรายการให้เล่น' }); }
  }

  function optionsSheet() {
    openSheet({
      title: 'ตัวเลือกเพลย์ลิสต์',
      build(body, sheet) {
        const name = h('input', { class: 'input', value: pl.name, required: true, maxLength: 80 });
        const save = h('button', { class: 'btn primary', type: 'submit' }, 'บันทึกชื่อ');
        const del = h('button', {
          class: 'btn wide', type: 'button', style: { color: 'var(--danger)' },
          onclick: () => inlineConfirm(del, {
            text: `ลบเพลย์ลิสต์ “${pl.name}” และรายการทั้งหมด ${pl.items.length} รายการ? ลบแล้วกู้คืนไม่ได้`, confirmLabel: 'ลบเพลย์ลิสต์',
            onConfirm: async () => {
              try { await ctx.api(`/playlists/${id}`, { method: 'DELETE' }); } catch (e) { ctx.fail(e); throw e; }
              sheet.close(); ctx.toast('ลบเพลย์ลิสต์แล้ว', 'ok'); ctx.go('#/playlists');
            },
          }),
        }, icon('trash', 'sm'), 'ลบเพลย์ลิสต์');
        body.append(h('form', {
          onsubmit: async (e) => {
            e.preventDefault();
            await busy(save, async () => {
              try { await ctx.api(`/playlists/${id}`, { method: 'PATCH', body: { name: name.value.trim() } }); pl.name = name.value.trim(); drawHero(); sheet.close(); ctx.toast('บันทึกชื่อแล้ว', 'ok'); } catch (e2) { ctx.fail(e2); }
            });
          },
        }, field('ชื่อเพลย์ลิสต์', name), save), h('div', { class: 'divider' }), del);
      },
    });
  }

  function addItemSheet() {
    openSheet({
      title: 'เพิ่มรายการ',
      build(body) {
        const panes = { youtube: ytPane(), url: urlPane(), tts: ttsPane() };
        const seg = segmented({
          options: [{ value: 'youtube', label: 'YouTube', icon: 'search' }, { value: 'url', label: 'ลิงก์เสียง', icon: 'link' }, { value: 'tts', label: 'ข้อความ', icon: 'announce' }],
          value: 'youtube', label: 'ชนิดรายการ', cls: 'lg',
          onChange: (v) => { Object.entries(panes).forEach(([k, p]) => { p.hidden = k !== v; }); panes[v].querySelector('input,textarea')?.focus(); },
        });
        panes.url.hidden = true; panes.tts.hidden = true;
        body.append(h('div', { style: { marginBottom: '16px' } }, seg), panes.youtube, panes.url, panes.tts);
      },
    });
  }
  async function addItem(payload, btn) {
    return busy(btn, async () => {
      try {
        const it = await ctx.api(`/playlists/${id}/items`, { body: payload });
        pl.items.push(it); drawHero(); drawItems();
        ctx.toast(`เพิ่ม “${it.title}” แล้ว`, 'ok');
        return it;
      } catch (e) { ctx.fail(e); return null; }
    });
  }
  function ytPane() {
    const q = h('input', { class: 'input', type: 'search', enterKeyHint: 'search', placeholder: 'ค้นหา หรือวางลิงก์ YouTube', 'aria-label': 'ค้นหา YouTube' });
    const go = h('button', { class: 'btn primary', type: 'submit' }, 'ค้นหา');
    const res = h('ul', { class: 'list', style: { marginTop: '12px' } });
    return h('form', {
      onsubmit: async (e) => {
        e.preventDefault();
        const v = q.value.trim();
        if (!v) return q.focus();
        if (/^https?:\/\//i.test(v)) { if (await addItem({ kind: 'youtube', source: v }, go)) q.value = ''; return; }
        try {
          const r = await busy(go, () => ctx.api(`/youtube/search?q=${encodeURIComponent(v)}&limit=8`));
          res.replaceChildren(...r.map((x) => {
            const add = iconBtn('plus', `เพิ่ม ${x.title}`, async () => { if (await addItem({ kind: 'youtube', source: x.video_id }, add)) { add.replaceChildren(icon('check')); add.disabled = true; add.setAttribute('aria-label', `เพิ่ม ${x.title} แล้ว`); } });
            return h('li', { class: 'row' }, thumbEl(x.thumbnail, 'note', 'wide'), h('div', { class: 'body' }, h('div', { class: 'title' }, x.title), h('div', { class: 'sub' }, h('span', {}, x.channel || ''), x.duration ? h('span', { class: 'num' }, fmtDur(x.duration)) : null)), h('div', { class: 'trail' }, add));
          }));
          if (!r.length) res.replaceChildren(h('li', { class: 'empty' }, 'ไม่พบผลลัพธ์ ลองคำอื่น'));
        } catch (e2) { ctx.fail(e2); }
      },
    }, h('div', { style: { display: 'flex', gap: '10px' } }, q, go), res);
  }
  function urlPane() {
    const url = h('input', { class: 'input', type: 'url', inputMode: 'url', placeholder: 'https://…/audio.mp3', required: true });
    const title = h('input', { class: 'input', required: true, placeholder: 'เช่น สถานีวิทยุ FM 95' });
    const go = h('button', { class: 'btn primary wide', type: 'submit' }, 'เพิ่มลิงก์');
    return h('form', {
      onsubmit: async (e) => {
        e.preventDefault();
        if (await addItem({ kind: 'url', source: url.value.trim(), title: title.value.trim() }, go)) { url.value = ''; title.value = ''; }
      },
    }, field('ลิงก์ไฟล์เสียง', url, 'ลิงก์ที่เปิดแล้วได้ไฟล์เสียงโดยตรง เช่น .mp3 หรือสตรีมวิทยุ'), field('ชื่อที่แสดง', title), go);
  }
  function ttsPane() {
    const text = h('textarea', { class: 'textarea', maxLength: 1000, required: true, placeholder: 'เช่น ยินดีต้อนรับ ร้านเปิดให้บริการแล้วค่ะ' });
    let lang = 'th';
    const seg = segmented({ options: LANGS, value: lang, label: 'ภาษาที่ใช้อ่าน', onChange: (v) => { lang = v; } });
    const go = h('button', { class: 'btn primary wide', type: 'submit' }, 'เพิ่มข้อความ');
    return h('form', {
      onsubmit: async (e) => {
        e.preventDefault();
        if (await addItem({ kind: 'tts', source: text.value.trim(), lang }, go)) text.value = '';
      },
    }, field('ข้อความที่จะอ่าน', text), h('div', { style: { marginBottom: '16px' } }, seg), go);
  }

  ctx.onStatus((st) => {
    const q = st.status && st.status.queue;
    const nid = q && q.playlist_id === id ? q.items[q.index]?.id : null;
    if (nid !== playingId) { playingId = nid; if (pl && !dragging && !listEl.parentElement?.querySelector('.confirm')) drawItems(); }
  });
  load();
  return { node };
}
