// Playlists (boards Playlists / PlaylistDetail / AddItem + T_ and D_ variants).
// #/playlists = the list; #/playlists/12 = one playlist. Phones and iPad show them as two pages; desktop (>= 1280px)
// shows list and detail side by side and switches the selection in place.
// Operators: create, rename, delete (with Undo), add items of every kind, reorder (drag the handle; on touch also
// Reorder mode with up/down), item menu (play from here, move to top, remove with Undo), play / shuffle / repeat.
// Viewers see the same lists read-only.
import { h, icon, field, busy, tip, append } from '../ui.js';
import { register, t, fmtDur } from '../i18n.js';
import { errorText } from '../api.js';
import { isPhone } from '../sheet.js';
import { bicon } from '../teamb-icons.js';
import {
  thumb, roundBtn, setRound, errBox, note, spinnerLine, playlistMeta, kindSub, addItemSheet, mediaActive,
  deleteLater, isPending, undoDelete, flushDeletes, ibtn,
} from '../teamb-common.js';

register({
  en: {
    'pl.new': 'New playlist', 'pl.newShort': 'New', 'pl.createPl': 'Create playlist', 'pl.name': 'Playlist name',
    'pl.namePh': 'e.g. Afternoon music', 'pl.nameErr': 'Give it a name first.',
    'pl.none': 'No playlists yet.', 'pl.noneOp': 'No playlists yet. Make one for each part of the day, then add songs, radio or announcements.',
    'pl.addItemsTo': (x) => `Add items to ${x}`, 'pl.open': (x) => `Open ${x}`,
    'pl.playAll': 'Play all', 'pl.stop': 'Stop', 'pl.shuffle': 'Shuffle', 'pl.addItem': 'Add item', 'pl.reorder': 'Reorder',
    'pl.done': 'Done', 'pl.rename': 'Rename', 'pl.saveName': 'Save name', 'pl.more': (x) => `More for ${x}`,
    'pl.delete': 'Delete playlist', 'pl.deleted': (x) => `Deleted ${x}`, 'pl.items': 'Playlist items',
    'pl.emptyList': 'No items in this playlist yet.', 'pl.pickHint': 'Pick a playlist to see what’s in it.',
    'pl.playHere': 'Play from here', 'pl.moveTop': 'Move to top', 'pl.remove': 'Remove from playlist',
    'pl.playFrom': (x) => `Play from ${x}`, 'pl.options': (x) => `Options for ${x}`,
    'pl.up': (x) => `Move ${x} up`, 'pl.down': (x) => `Move ${x} down`, 'pl.drag': (x) => `Drag to move ${x}. Arrow keys move it too.`,
    'pl.moved': (x, n) => `${x} moved to position ${n}`, 'pl.removed': (x) => `Removed ${x}`,
    'pl.shuffleOff': 'Shuffle off. Playing in order.', 'pl.shuffleOn': 'Shuffle on', 'pl.shuffling': (x) => `Shuffling ${x} on the speaker`,
    'pl.repeat.off': 'Repeat: off', 'pl.repeat.all': 'Repeat: whole playlist', 'pl.repeat.one': 'Repeat: one item',
    'pl.repeatHint': 'Tap to change. Used the next time you press Play all.',
    'pl.nowPlaying': (x) => `Speaker is playing ${x}`,
  },
  th: {
    'pl.new': 'สร้างเพลย์ลิสต์', 'pl.newShort': 'สร้าง', 'pl.createPl': 'สร้างเพลย์ลิสต์', 'pl.name': 'ชื่อเพลย์ลิสต์',
    'pl.namePh': 'เช่น เพลงช่วงบ่าย', 'pl.nameErr': 'ตั้งชื่อก่อนสร้าง',
    'pl.none': 'ยังไม่มีเพลย์ลิสต์', 'pl.noneOp': 'ยังไม่มีเพลย์ลิสต์ สร้างไว้สำหรับแต่ละช่วงของวัน แล้วเพิ่มเพลง วิทยุ หรือประกาศเข้าไป',
    'pl.addItemsTo': (x) => `เพิ่มรายการเข้า ${x}`, 'pl.open': (x) => `เปิด ${x}`,
    'pl.playAll': 'เล่นทั้งหมด', 'pl.stop': 'หยุด', 'pl.shuffle': 'สุ่มเล่น', 'pl.addItem': 'เพิ่มรายการ', 'pl.reorder': 'จัดเรียง',
    'pl.done': 'เสร็จ', 'pl.rename': 'เปลี่ยนชื่อ', 'pl.saveName': 'บันทึกชื่อ', 'pl.more': (x) => `เพิ่มเติมสำหรับ ${x}`,
    'pl.delete': 'ลบเพลย์ลิสต์', 'pl.deleted': (x) => `ลบ ${x} แล้ว`, 'pl.items': 'รายการในเพลย์ลิสต์',
    'pl.emptyList': 'เพลย์ลิสต์นี้ยังไม่มีรายการ', 'pl.pickHint': 'เลือกเพลย์ลิสต์เพื่อดูรายการข้างใน',
    'pl.playHere': 'เล่นจากรายการนี้', 'pl.moveTop': 'ย้ายขึ้นบนสุด', 'pl.remove': 'เอาออกจากเพลย์ลิสต์',
    'pl.playFrom': (x) => `เล่นจาก ${x}`, 'pl.options': (x) => `ตัวเลือก ${x}`,
    'pl.up': (x) => `ย้าย ${x} ขึ้น`, 'pl.down': (x) => `ย้าย ${x} ลง`, 'pl.drag': (x) => `ลากเพื่อย้าย ${x} หรือกดลูกศรขึ้นลง`,
    'pl.moved': (x, n) => `ย้าย ${x} ไปลำดับที่ ${n} แล้ว`, 'pl.removed': (x) => `เอา ${x} ออกแล้ว`,
    'pl.shuffleOff': 'ปิดสุ่มเล่นแล้ว เล่นตามลำดับ', 'pl.shuffleOn': 'เปิดสุ่มเล่นแล้ว', 'pl.shuffling': (x) => `สุ่มเล่น ${x} ที่ลำโพง`,
    'pl.repeat.off': 'เล่นซ้ำ: ปิด', 'pl.repeat.all': 'เล่นซ้ำ: ทั้งเพลย์ลิสต์', 'pl.repeat.one': 'เล่นซ้ำ: รายการเดียว',
    'pl.repeatHint': 'แตะเพื่อเปลี่ยน ใช้ตอนกด เล่นทั้งหมด ครั้งถัดไป',
    'pl.nowPlaying': (x) => `ลำโพงกำลังเล่น ${x}`,
  },
});

const REPEATS = ['off', 'all', 'one'];
const repeatPref = new Map(); // playlist id -> repeat mode for the next Play all (this tab only)
const listeners = new Set(); // repaint functions of mounted lists (Undo of a playlist delete)
const isDesk = () => matchMedia('(min-width: 1280px)').matches;
const canOp = (ctx) => ctx.can('operator');

export async function render(ctx) {
  await Promise.all([ctx.css('views/teamb.css'), ctx.css('views/playlists.css')]);
  const id = parseInt(ctx.params[0], 10) || null;
  if (id && !isDesk()) return detailPage(ctx, id);
  return listPage(ctx, id);
}

/* ======================= list (+ desktop detail panel) ======================= */
function listPage(ctx, selected) {
  const desk = isDesk();
  const listEl = h('div', { class: 'list tb-list pl-list', role: 'list' });
  const box = h('div', { class: 'pl-listcol' }, listEl);
  const pane = h('div', { class: 'pl-pane glass' });
  let playlists = null, status = ctx.status, detail = null;
  const newBtn = canOp(ctx) ? h('button', { type: 'button', class: 'btn primary', onclick: () => createPlaylist(ctx, (p) => {
    if (desk) { selected = p.id; history.replaceState(null, '', `#/playlists/${p.id}`); load(); } else ctx.go(`#/playlists/${p.id}`);
  }) }, icon('plus', 'sm'), h('span', { class: 'pl-new-l' }, t('pl.new')), h('span', { class: 'pl-new-s' }, t('pl.newShort'))) : null;
  const node = h('div', { class: `page pl${desk ? ' pl-desk' : ''}` }, ctx.header({ title: t('nav.playlists'), actions: newBtn }),
    desk ? h('div', { class: 'pl-split' }, box, pane) : box);

  async function load() {
    try {
      playlists = await ctx.api('/playlists', { signal: ctx.signal });
    } catch (e) {
      if (e.name !== 'AbortError') listEl.replaceChildren(errBox(errorText(e, ctx.user), load));
      return;
    }
    paint();
  }
  function visible() { return (playlists || []).filter((p) => !isPending(`pl:${p.id}`)); }
  function paint() {
    if (!playlists) { listEl.replaceChildren(spinnerLine('')); return; }
    const list = visible();
    if (!list.length) {
      listEl.replaceChildren(h('div', { class: 'pl-empty' }, note(t(canOp(ctx) ? 'pl.noneOp' : 'pl.none'))));
      if (desk) { pane.replaceChildren(); detail = null; }
      return;
    }
    if (desk && (!selected || !list.some((p) => p.id === selected))) selected = list[0].id;
    listEl.replaceChildren(...list.map(listRow));
    if (desk && (!detail || detail.id !== selected)) openDetail(selected);
  }
  function listRow(p) {
    const meta = playlistMeta(p);
    const sub = h('span', { class: 'tb-s' }, meta);
    const link = h('a', {
      class: 'tb-stretch', href: `#/playlists/${p.id}`, 'aria-label': t('pl.open', p.name),
      'aria-current': desk && p.id === selected ? 'true' : null,
      onclick: (e) => { if (!desk) return; e.preventDefault(); selected = p.id; history.replaceState(null, '', `#/playlists/${p.id}`); paint(); },
    });
    const row = h('div', { class: `tb-row pl-row${desk && p.id === selected ? ' sel' : ''}`, role: 'listitem' }, link,
      thumb('playlist'), h('span', { class: 'tb-tx' }, h('span', { class: 'tb-t' }, p.name), sub));
    if (!p.item_count) row.querySelector('.tb-th').classList.add('dim');
    if (canOp(ctx)) {
      const act = h('span', { class: 'tb-act' });
      if (p.item_count) {
        const btn = roundBtn('play', t('tb.playOn', p.name), async () => {
          const playing = playingThis(status, p.id);
          await busy(btn, async () => {
            try {
              if (playing) { await ctx.api('/stop', { method: 'POST' }); ctx.toast(t('tb.stopped'), 'ok'); } else {
                await ctx.api(`/playlists/${p.id}/play`, { body: { start_index: 0, shuffle: false, repeat: repeatPref.get(p.id) || 'off' } });
                ctx.toast(t('pl.nowPlaying', p.name), 'ok');
              }
            } catch (e) { ctx.fail(e); }
          });
          ctx.refreshStatus();
        }, 'tint');
        const upd = () => {
          const on = playingThis(status, p.id);
          setRound(btn, on ? 'stop' : 'play', on ? t('tb.stopX', p.name) : t('tb.playOn', p.name));
          sub.textContent = on ? t('tb.playing') : meta;
          row.classList.toggle('on', on);
        };
        btn.upd = upd;
        upd();
        act.append(btn);
      } else {
        act.append(roundBtn('plus', t('pl.addItemsTo', p.name), () => addItemSheet(ctx, p, () => {
          load();
          if (detail && detail.id === p.id) detail.reload(); // the open desktop pane shows this playlist: refresh it
        }), 'tint'));
      }
      row.append(act);
    }
    return row;
  }
  function openDetail(pid) {
    if (detail && detail.destroy) detail.destroy();
    detail = detailView(ctx, pid, {
      embedded: true,
      onChanged: load,
      onDeleted: () => { selected = null; paint(); },
    });
    pane.replaceChildren(detail.node);
    if (status || ctx.statusError) detail.onStatus({ status, error: ctx.statusError });
  }

  const repaint = () => paint();
  listeners.add(repaint);
  ctx.onCleanup(() => { listeners.delete(repaint); if (detail && detail.destroy) detail.destroy(); });
  if (desk) pane.append(note(t('pl.pickHint'), 'pl-hint'));
  paint();
  load();
  return {
    node,
    onStatus(s) {
      status = s.status;
      listEl.querySelectorAll('.tb-rb').forEach((b) => b.upd && b.upd());
      if (detail) detail.onStatus(s);
    },
  };
}

function playingThis(status, pid) {
  const q = status && status.queue;
  return !!(q && q.playlist_id === pid && mediaActive(status));
}

function createPlaylist(ctx, done) {
  nameSheet(ctx, { title: t('pl.createPl'), button: t('pl.createPl'), value: '', save: async (name) => {
    const p = await ctx.api('/playlists', { body: { name } });
    done(p);
  } });
}
/** Sheet with one name field (create / rename). save(name) may throw: the error shows inline. */
function nameSheet(ctx, { title, button, value, save }) {
  ctx.sheet({
    title,
    build(body, sheet) {
      const input = h('input', { class: 'input', value, placeholder: t('pl.namePh'), maxLength: 100, enterKeyHint: 'done', autocomplete: 'off' });
      const err = h('p', { class: 'form-error', role: 'alert' });
      const btn = h('button', { type: 'submit', class: 'btn primary big wide' }, button);
      body.append(h('form', {
        class: 'tb-form', novalidate: true,
        onsubmit: (e) => {
          e.preventDefault();
          const v = input.value.trim();
          if (!v) { input.setAttribute('aria-invalid', 'true'); err.textContent = t('pl.nameErr'); input.focus(); return; }
          input.removeAttribute('aria-invalid');
          busy(btn, async () => {
            try { await save(v); sheet.close(); } catch (x) { err.textContent = errorText(x, ctx.user); }
          });
        },
      }, field(t('pl.name'), input), err, btn));
    },
  });
}

/* ======================= detail ======================= */
function detailPage(ctx, id) {
  const holder = h('div', { class: 'page pl pl-detail' });
  const d = detailView(ctx, id, {
    embedded: false,
    header: (name, actions) => ctx.header({ title: name, back: { href: '#/playlists', label: t('nav.playlists') }, actions }),
    onDeleted: () => ctx.go('#/playlists'),
  });
  holder.append(d.node);
  return { node: holder, onStatus: (s) => d.onStatus(s), destroy: () => d.destroy && d.destroy() };
}

function detailView(ctx, id, { embedded, header, onChanged, onDeleted }) {
  const op = canOp(ctx);
  const node = h('div', { class: 'pl-dv' });
  const itemsEl = h('div', { class: 'list tb-list pl-items', role: 'list', 'aria-label': t('pl.items') });
  const live = h('p', { class: 'sr-only', 'aria-live': 'polite' });
  let p = null, status = ctx.status, reorder = false, dragging = false;
  const ac = new AbortController();
  const changed = () => { if (onChanged) onChanged(); };

  async function load() {
    try {
      p = await ctx.api(`/playlists/${id}`, { signal: ac.signal });
    } catch (e) {
      if (e.name === 'AbortError') return;
      node.replaceChildren(header ? header('', null) : '', errBox(errorText(e, ctx.user), load));
      return;
    }
    build();
  }
  const items = () => p.items.filter((it) => !isPending(`it:${id}:${it.id}`));

  /* ----- static parts ----- */
  let hero, playBtn, shufBtn, repBtn, reorderBtn, metaEl;
  function build() {
    const name = p.name;
    metaEl = h('p', { class: 'pl-meta' });
    const nameEl = h(embedded ? 'h2' : 'h1', { class: 'pl-name' }, name);
    const allTts = p.items.length && p.items.every((i) => i.kind === 'tts');
    hero = h('div', { class: 'pl-hero' }, h('span', { class: `pl-cover${p.items.length ? '' : ' dim'}`, 'aria-hidden': 'true' }, icon(allTts ? 'announce' : 'playlists', 'lg')),
      h('div', { class: 'pl-hero-tx' }, nameEl, metaEl));
    const more = op ? ibtn('more', t('pl.more', name), (e) => moreMenu(e.currentTarget), 'pl-more') : null;
    const kids = [];
    if (!embedded) {
      const hd = header(name, more);
      hd.classList.add('pl-hd');
      kids.push(hd);
    }
    kids.push(embedded && more ? h('div', { class: 'pl-hero-row' }, hero, more) : hero);
    if (op) {
      playBtn = h('button', { type: 'button', class: 'btn primary big pl-play', onclick: () => playAll() });
      shufBtn = h('button', { type: 'button', class: 'btn tonal big pl-shuf', onclick: () => shuffle() }, bicon('shuffle', 'sm'), t('pl.shuffle'));
      repBtn = h('button', { type: 'button', class: 'tb-rb soft pl-rep', onclick: () => cycleRepeat() });
      reorderBtn = h('button', { type: 'button', class: 'linkbtn', 'aria-pressed': 'false', onclick: () => setReorder(!reorder) }, t('pl.reorder'));
      kids.push(h('div', { class: 'pl-ctl' },
        h('div', { class: 'pl-btns' }, playBtn, shufBtn, repBtn),
        h('div', { class: 'pl-links' },
          h('button', { type: 'button', class: 'linkbtn', onclick: () => addItemSheet(ctx, p, () => { reloadItems(); changed(); }) }, icon('plus', 'sm'), t('pl.addItem')),
          reorderBtn,
          h('button', { type: 'button', class: 'linkbtn', onclick: () => rename() }, t('pl.rename')))));
    }
    kids.push(itemsEl, live);
    node.replaceChildren(...kids);
    paintItems();
    paintControls();
  }

  async function reloadItems() {
    try { p = await ctx.api(`/playlists/${id}`, { signal: ac.signal }); } catch (e) { if (e.name !== 'AbortError') ctx.fail(e); return; }
    if (node.isConnected) build();
  }

  /* ----- play state ----- */
  const queue = () => (status && status.queue && status.queue.playlist_id === id ? status.queue : null);
  function paintControls() {
    const list = items();
    metaEl.textContent = playlistMeta({ ...p, items: list, item_count: list.length, total_duration: undefined });
    if (!op) return;
    const q = queue();
    const playing = !!q && mediaActive(status);
    playBtn.replaceChildren(bicon(playing ? 'stop' : 'play', 'sm'), playing ? t('pl.stop') : t('pl.playAll'));
    playBtn.disabled = !list.length && !playing;
    shufBtn.disabled = !list.length;
    shufBtn.setAttribute('aria-pressed', String(!!(q && q.shuffle)));
    const rep = q ? q.repeat : repeatPref.get(id) || 'off';
    repBtn.replaceChildren(bicon(rep === 'one' ? 'repeat-one' : 'repeat', 'sm'));
    repBtn.setAttribute('aria-label', t(`pl.repeat.${rep}`));
    repBtn.setAttribute('aria-pressed', String(rep !== 'off'));
    tip(repBtn, q ? t(`pl.repeat.${rep}`) : `${t(`pl.repeat.${rep}`)}. ${t('pl.repeatHint')}`);
    reorderBtn.hidden = list.length < 2;
    // highlight the item the speaker is on
    const cur = q && playing && q.items[q.index];
    itemsEl.querySelectorAll('.pl-it').forEach((r) => {
      const on = !!cur && Number(r.dataset.id) === cur.id;
      r.classList.toggle('on', on);
      const sub = r.querySelector('.tb-s');
      sub.textContent = on ? t('tb.playing') : sub.dataset.idle;
    });
  }
  async function start(body, okMsg) {
    try {
      await flushDeletes(`it:${id}:`); // start_index counts the items the server still has
      await ctx.api(`/playlists/${id}/play`, { body: { start_index: 0, shuffle: false, repeat: repeatPref.get(id) || 'off', ...body } });
      ctx.toast(okMsg, 'ok');
    } catch (e) { ctx.fail(e); }
    ctx.refreshStatus();
  }
  function playAll() {
    const q = queue();
    busy(playBtn, async () => {
      if (q && mediaActive(status)) {
        try { await ctx.api('/stop', { method: 'POST' }); ctx.toast(t('tb.stopped'), 'ok'); } catch (e) { ctx.fail(e); }
        ctx.refreshStatus();
      } else await start({}, t('pl.nowPlaying', p.name));
    });
  }
  function shuffle() {
    const q = queue();
    busy(shufBtn, async () => {
      if (q) {
        try {
          const r = await ctx.api('/queue', { method: 'PATCH', body: { shuffle: !q.shuffle } });
          status = { ...status, queue: r };
          ctx.toast(t(r.shuffle ? 'pl.shuffleOn' : 'pl.shuffleOff'), 'ok');
          paintControls();
        } catch (e) { ctx.fail(e); }
        ctx.refreshStatus();
      } else {
        const n = items().length;
        await start({ shuffle: true, start_index: Math.floor(Math.random() * n) }, t('pl.shuffling', p.name));
      }
    });
  }
  async function cycleRepeat() {
    const q = queue();
    const cur = q ? q.repeat : repeatPref.get(id) || 'off';
    const next = REPEATS[(REPEATS.indexOf(cur) + 1) % REPEATS.length];
    repeatPref.set(id, next);
    if (q) {
      try {
        const r = await ctx.api('/queue', { method: 'PATCH', body: { repeat: next } });
        status = { ...status, queue: r };
      } catch (e) { ctx.fail(e); }
    }
    paintControls();
  }

  /* ----- items ----- */
  function paintItems() {
    const list = items();
    if (!list.length) {
      itemsEl.replaceChildren(h('div', { class: 'pl-empty' }, note(t('pl.emptyList')),
        op ? h('button', { type: 'button', class: 'btn tonal', onclick: () => addItemSheet(ctx, p, () => { reloadItems(); changed(); }) }, icon('plus', 'sm'), t('pl.addItem')) : null));
      return;
    }
    itemsEl.classList.toggle('reorder', reorder);
    itemsEl.replaceChildren(...list.map((it, i) => itemRow(it, i, list.length)));
    if (metaEl) paintControls();
  }
  function itemRow(it, i, n) {
    const subText = kindSub(it);
    const sub = h('span', { class: 'tb-s', dataset: { idle: subText } }, subText);
    const row = h('div', { class: 'tb-row pl-it', role: 'listitem', dataset: { id: String(it.id) } });
    if (op && !reorder) row.append(h('button', { type: 'button', class: 'tb-stretch', 'aria-label': t('pl.playFrom', it.title), onclick: () => playFrom(it) }));
    if (op) {
      const grip = h('button', { type: 'button', class: 'pl-grip', 'aria-label': t('pl.drag', it.title) }, bicon('grip', 'sm'));
      tip(grip, t('pl.drag', it.title));
      grip.addEventListener('pointerdown', (e) => startDrag(e, row, grip));
      grip.addEventListener('keydown', (e) => {
        const step = { ArrowUp: -1, ArrowDown: 1 }[e.key];
        if (!step) return;
        e.preventDefault();
        moveBy(it, step, true);
      });
      row.append(grip);
    }
    append(row, [h('span', { class: 'pl-idx', 'aria-hidden': 'true' }, String(i + 1)),
      thumb(it.kind, { img: it.kind === 'tts' ? null : it.thumbnail }),
      h('span', { class: 'tb-tx' }, h('span', { class: 'tb-t' }, it.title), sub),
      it.duration ? h('span', { class: 'pl-dur' }, fmtDur(it.duration)) : null]);
    if (op) {
      const act = h('span', { class: 'tb-act' });
      if (reorder) {
        const up = ibtn('up', t('pl.up', it.title), () => moveBy(it, -1, true));
        const down = ibtn('down', t('pl.down', it.title), () => moveBy(it, 1, true));
        up.disabled = i === 0;
        down.disabled = i === n - 1;
        act.append(up, down);
      } else {
        act.append(ibtn('more', t('pl.options', it.title), (e) => itemMenu(it, e.currentTarget)));
      }
      row.append(act);
    }
    return row;
  }
  function setReorder(on) {
    reorder = on;
    reorderBtn.textContent = t(on ? 'pl.done' : 'pl.reorder');
    reorderBtn.setAttribute('aria-pressed', String(on));
    paintItems();
  }
  function playFrom(it) {
    const i = items().findIndex((x) => x.id === it.id);
    start({ start_index: i }, t('pl.nowPlaying', it.title));
  }
  function itemMenu(it, anchor) {
    const list = items();
    const i = list.findIndex((x) => x.id === it.id);
    const rows = (close) => {
      const mi = (ic, label, fn, cls = '') => h('button', { type: 'button', class: `mi ${cls}`.trim(), onclick: () => { close(); fn(); } },
        h('span', { class: 'mic' }, bicon(ic, 'xs')), h('span', {}, label));
      return h('div', { class: 'menu' },
        mi('play', t('pl.playHere'), () => playFrom(it)),
        i > 0 ? mi('top', t('pl.moveTop'), () => moveTo(it, 0)) : null,
        mi('trash', t('pl.remove'), () => removeItem(it), 'danger'));
    };
    if (isPhone()) ctx.sheet({ title: it.title, build: (body, sheet) => body.append(h('div', { class: 'list tb-menu' }, rows(() => sheet.close()))) });
    else ctx.popover({ anchor, label: t('pl.options', it.title), className: 'tb-pop', build: (el, close) => el.append(rows(close)) });
  }
  function removeItem(it) {
    const key = `it:${id}:${it.id}`;
    deleteLater(key, `/playlists/${id}/items/${it.id}`, {
      onDone: () => { if (p) p.items = p.items.filter((x) => x.id !== it.id); changed(); },
      onError: (e) => { ctx.fail(e); reloadItems(); },
    });
    paintItems();
    ctx.toast(t('pl.removed', it.title), 'info', { ms: 6000, action: { label: t('tb.undo'), run: () => { if (undoDelete(key) && node.isConnected) paintItems(); } } });
  }
  function moveBy(it, step, refocus) {
    const list = items();
    const i = list.findIndex((x) => x.id === it.id);
    const j = i + step;
    if (j < 0 || j >= list.length) return;
    moveTo(it, j, refocus);
  }
  async function moveTo(it, to, refocus = false) {
    await flushDeletes(`it:${id}:`);
    const list = items();
    const from = list.findIndex((x) => x.id === it.id);
    if (from < 0) return;
    list.splice(from, 1);
    list.splice(to, 0, it);
    p.items = list;
    paintItems();
    if (refocus) {
      const r = itemsEl.querySelector(`[data-id="${it.id}"]`);
      const target = r && (r.querySelector(reorder ? `.tb-act button:not([disabled])` : '.pl-grip') || r.querySelector('.pl-grip'));
      if (target) target.focus({ preventScroll: false });
    }
    live.textContent = t('pl.moved', it.title, to + 1);
    try {
      p = await ctx.api(`/playlists/${id}/order`, { method: 'PUT', body: { item_ids: list.map((x) => x.id) } });
      changed();
    } catch (e) { ctx.fail(e); reloadItems(); }
  }

  /* ----- drag to reorder (pointer events: mouse and touch alike, from the handle) ----- */
  function startDrag(e, row, grip) {
    if (e.button !== 0 || dragging) return;
    e.preventDefault();
    const rows = [...itemsEl.querySelectorAll('.pl-it')];
    const from = rows.indexOf(row);
    const sy0 = scrollY;
    const tops = rows.map((r) => { const b = r.getBoundingClientRect(); return { mid: b.top + sy0 + b.height / 2 }; });
    const hgt = row.getBoundingClientRect().height;
    const y0 = e.clientY + sy0;
    let to = from, moved = false, raf = 0, lastY = e.clientY;
    dragging = true;
    grip.setPointerCapture(e.pointerId);
    row.classList.add('dragging');
    itemsEl.classList.add('sorting');
    const step = () => {
      const y = lastY + scrollY;
      const dy = y - y0;
      if (Math.abs(dy) > 4) moved = true;
      row.style.transform = `translateY(${dy}px)`;
      const mid = tops[from].mid + dy;
      to = from;
      for (let i = 0; i < rows.length; i++) {
        if (i < from && mid < tops[i].mid) { to = i; break; }
        if (i > from && mid > tops[i].mid) to = i;
      }
      rows.forEach((r, i) => {
        if (i === from) return;
        const s = from < to && i > from && i <= to ? -hgt : to < from && i >= to && i < from ? hgt : 0;
        r.style.transform = s ? `translateY(${s}px)` : '';
      });
      // keep scrolling while the finger/pointer sits near the top or bottom edge
      const edge = lastY < 90 ? -1 : lastY > innerHeight - 110 ? 1 : 0;
      if (edge) { scrollBy(0, edge * 8); raf = requestAnimationFrame(step); } else raf = 0;
    };
    const onMove = (ev) => { lastY = ev.clientY; if (!raf) raf = requestAnimationFrame(step); };
    const end = () => {
      cancelAnimationFrame(raf);
      grip.removeEventListener('pointermove', onMove);
      grip.removeEventListener('pointerup', end);
      grip.removeEventListener('pointercancel', end);
      rows.forEach((r) => { r.style.transform = ''; });
      row.classList.remove('dragging');
      itemsEl.classList.remove('sorting');
      dragging = false;
      if (moved && to !== from) {
        const it = items()[from];
        moveTo(it, to);
      }
    };
    grip.addEventListener('pointermove', onMove);
    grip.addEventListener('pointerup', end);
    grip.addEventListener('pointercancel', end);
  }

  /* ----- playlist actions ----- */
  function rename() {
    nameSheet(ctx, { title: t('pl.rename'), button: t('pl.saveName'), value: p.name, save: async (name) => {
      p = { ...p, ...(await ctx.api(`/playlists/${id}`, { method: 'PATCH', body: { name } })) };
      build();
      changed();
    } });
  }
  function moreMenu(anchor) {
    const rows = (close) => h('div', { class: 'menu' },
      h('button', { type: 'button', class: 'mi', onclick: () => { close(); rename(); } }, h('span', { class: 'mic' }, bicon('pencil', 'xs')), h('span', {}, t('pl.rename'))),
      h('button', { type: 'button', class: 'mi danger', onclick: () => { close(); remove(); } }, h('span', { class: 'mic' }, bicon('trash', 'xs')), h('span', {}, t('pl.delete'))));
    if (isPhone()) ctx.sheet({ title: p.name, build: (body, sheet) => body.append(h('div', { class: 'list tb-menu' }, rows(() => sheet.close()))) });
    else ctx.popover({ anchor, label: t('pl.more', p.name), className: 'tb-pop', build: (el, close) => el.append(rows(close)) });
  }
  function remove() {
    const key = `pl:${id}`;
    const name = p.name;
    deleteLater(key, `/playlists/${id}`, { onError: (e) => { ctx.fail(e); listeners.forEach((f) => f()); } });
    ctx.toast(t('pl.deleted', name), 'info', { ms: 6000, action: { label: t('tb.undo'), run: () => { if (undoDelete(key)) listeners.forEach((f) => f()); } } });
    onDeleted();
  }

  node.append(spinnerLine(''));
  load();
  return {
    id, node, reload: reloadItems,
    onStatus(s) { status = s.status; if (p && metaEl && !dragging) paintControls(); },
    destroy() { ac.abort(); },
  };
}
