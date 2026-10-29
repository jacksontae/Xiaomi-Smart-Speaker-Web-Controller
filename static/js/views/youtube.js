// YouTube: search, play now, or add a result to a playlist.
import { h, icon, iconBtn, fmtDur, thumbEl, busy } from '../ui.js';
import { pickPlaylistSheet } from './playlists.js';

const isUrl = (s) => /^https?:\/\//i.test(s.trim());
const ytUrl = (id) => `https://www.youtube.com/watch?v=${encodeURIComponent(id)}`;
const SUGGEST = ['เพลงบรรเลงเปียโน', 'เพลงลูกทุ่งฮิต', 'เพลงสปาผ่อนคลาย', 'lo-fi ทำงาน'];
let memo = { q: '', results: null }; // keep results when switching tabs

export async function playYouTube(ctx, query, btn) {
  const slow = setTimeout(() => ctx.toast('กำลังดึงเสียงจาก YouTube อาจใช้เวลาสักครู่'), 1500);
  try {
    await busy(btn, async () => {
      const r = await ctx.api('/youtube', { body: { query } });
      ctx.toast(`กำลังเล่น “${r.title || 'YouTube'}”`, 'ok');
    });
    ctx.refreshStatus();
    return true;
  } catch (e) { ctx.fail(e); return false; } finally { clearTimeout(slow); }
}

export default function youtubeView(ctx) {
  const input = h('input', { class: 'input', type: 'search', id: 'yt-q', enterKeyHint: 'search', autocomplete: 'off', placeholder: 'ชื่อเพลง ศิลปิน หรือวางลิงก์ YouTube', value: memo.q, 'aria-label': 'ค้นหา YouTube' });
  const go = h('button', { class: 'btn primary', type: 'submit' }, icon('search', 'sm'), 'ค้นหา');
  const results = h('div', { 'aria-live': 'polite' });
  const form = h('form', { role: 'search', style: { display: 'flex', gap: '10px', marginBottom: '16px' }, onsubmit: (e) => { e.preventDefault(); search(); } }, input, go);

  async function search(q = input.value.trim()) {
    if (!q) { input.focus(); return; }
    input.value = q;
    memo.q = q;
    if (isUrl(q)) { showUrl(q); return; }
    results.replaceChildren(h('div', { class: 'panel glass' }, [1, 2, 3, 4].map(() => h('div', { class: 'skeleton' }))));
    try {
      const r = await busy(go, () => ctx.api(`/youtube/search?q=${encodeURIComponent(q)}&limit=8`));
      memo.results = r;
      showResults(r);
    } catch (e) {
      results.replaceChildren();
      ctx.fail(e);
    }
  }

  function showUrl(url) {
    const play = h('button', { class: 'btn primary', type: 'button', onclick: () => playYouTube(ctx, url, play) }, icon('play', 'fill sm'), 'เล่นเลย');
    const add = h('button', { class: 'btn', type: 'button', onclick: () => pickPlaylistSheet(ctx, { kind: 'youtube', source: url, title: 'ลิงก์ YouTube' }) }, icon('plus', 'sm'), 'เพิ่มลงเพลย์ลิสต์');
    results.replaceChildren(h('section', { class: 'panel glass' }, h('div', { class: 'row no-thumb' }, icon('link'), h('div', { class: 'body' }, h('div', { class: 'title' }, 'ลิงก์ YouTube'), h('div', { class: 'sub' }, h('span', {}, url)))),
      h('div', { class: 'idle-actions', style: { marginTop: '10px' } }, play, add)));
  }

  function showResults(list) {
    if (!list || !list.length) {
      results.replaceChildren(h('div', { class: 'panel glass empty' }, icon('search'), h('h2', {}, 'ไม่พบผลลัพธ์'), h('p', {}, 'ลองใช้คำอื่น หรือวางลิงก์ YouTube โดยตรง')));
      return;
    }
    results.replaceChildren(h('section', { class: 'panel glass', 'aria-label': 'ผลการค้นหา' }, h('ul', { class: 'list' }, list.map((v) => {
      const play = iconBtn('play', `เล่น ${v.title}`, () => playYouTube(ctx, ytUrl(v.video_id), play));
      const add = iconBtn('plus', `เพิ่ม ${v.title} ลงเพลย์ลิสต์`, () => pickPlaylistSheet(ctx, { kind: 'youtube', source: v.video_id, title: v.title }));
      return h('li', { class: 'row' }, thumbEl(v.thumbnail, 'note', 'wide'),
        h('div', { class: 'body' }, h('div', { class: 'title' }, v.title), h('div', { class: 'sub' }, h('span', {}, v.channel || ''), v.duration ? h('span', { class: 'num' }, fmtDur(v.duration)) : null)),
        h('div', { class: 'trail' }, add, play));
    }))));
  }

  function showStart() {
    results.replaceChildren(h('section', { class: 'panel glass' },
      h('h2', { style: { fontSize: 'var(--fs-md)', marginBottom: '12px' } }, 'ลองค้นหา'),
      h('div', { class: 'phrases' }, SUGGEST.map((s) => h('button', { type: 'button', class: 'phrase glass', onclick: () => search(s) }, icon('search', 'sm'), s)))));
  }

  if (memo.results) showResults(memo.results); else showStart();
  const node = h('div', {}, h('div', { class: 'page-head' }, h('h1', {}, 'YouTube')), form, results);
  return { node };
}
