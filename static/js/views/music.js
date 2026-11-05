// Music (boards YouTube / T_YouTube / D_YouTube): one page, four sources in a segmented control —
// YouTube search, internet radio (directory + favourites), podcasts (search or RSS link -> episodes, and the
// shows the member follows) and "My files" (upload with progress, rename, delete). Every result plays on the
// speaker or goes into a playlist.
// Spotify is not offered this round and Joox / Apple Music can't be: a Help link explains (no fake buttons).
// The source is part of the hash (#/music/radio) so other pages can link straight to one.
import { h, icon, iconBtn, field, busy, segmented, helpLink, headerSub } from '../ui.js';
import { register, t, fmtDur, lang } from '../i18n.js';
import { errorText, ApiError } from '../api.js';
import {
  thumb, mediaRow, roundBtn, setRound, errBox, note, sectionLabel, spinnerLine, searchForm, sourceError,
  playTracker, trackPlay, pickPlaylist, ibtn, deleteLater, isPending, undoDelete, isUrl, epMeta, fileMeta, size, androidSearch, here,
} from '../media-kit.js';
import { isAndroid } from '../prefs.js';
import { badge, sameDay } from '../kit.js';
import { glyph } from '../icons.js';

register({
  en: {
    // the header's context line (Android): what's playing, else what the page is for
    'music.ctxIdle': 'Pick a source, then play it on the speaker', 'music.ctxIdle.here': 'Pick a source, then play it on this device',
    'music.ctxPlaying': (x) => `Speaker is playing ${x}`, 'music.ctxPlaying.here': (x) => `Playing ${x} on this device`,
    'music.sources': 'Music source',
    'music.src.youtube': 'YouTube', 'music.src.radio': 'Radio', 'music.src.podcasts': 'Podcasts', 'music.src.files': 'My files',
    'music.whyJoox': 'Why isn’t Spotify, Joox or Apple Music here?', 'music.whyJooxShort': 'Where are Spotify, Joox and Apple Music?',
    'music.ytLabel': 'Search YouTube', 'music.ytPh': 'Search or paste a YouTube link',
    'music.ytHint': 'Search for a song, an artist or a mood, or paste a YouTube link.',
    'music.radioLabel': 'Search radio stations', 'music.radioPh': 'Search stations, e.g. jazz',
    'music.favs': 'Favourites', 'music.stations': 'Stations', 'music.popular': 'Popular stations',
    'music.favOn': (x) => `Remove ${x} from favourites`, 'music.favOff': (x) => `Add ${x} to favourites`,
    'music.podLabel': 'Podcast name or RSS link', 'music.podPh': 'Podcast name or RSS link', 'music.podFind': 'Find',
    'music.podHint': 'Search by name, or paste the show’s RSS link to open it straight away.',
    'music.podResults': (q) => `Podcasts matching “${q}”`, 'music.allResults': 'All results',
    'music.episodesOf': (x) => `Episodes: ${x}`, 'music.noEpisodes': 'This feed has no audio episodes.',
    'music.openShow': (x) => `Show episodes of ${x}`,
    'music.following': 'Following', 'music.followOn': 'Following', 'music.followOff': 'Follow',
    'music.newN': (n) => `${n} new`, 'music.newEp': 'New', 'music.latest': (d) => `Latest ${d}`,
    'music.allFollowed': 'All followed shows',
    'music.filesNote': (types, max) => `Audio files up to ${max} MB (${types}). They’re stored on the speaker server.`,
    'music.used': (used, quota) => `${used} of ${quota} used`,
    'music.upload': 'Upload', 'music.filesTitle': 'Uploaded files', 'music.edit': 'Edit', 'music.done': 'Done',
    'music.noFiles': 'No files yet. Tap Upload to add one.',
    'music.upPct': (p) => `Uploading, ${p}%`, 'music.upStart': 'Getting ready…', 'music.uploaded': (x) => `${x} uploaded`,
    'music.upCancelled': 'Upload cancelled', 'music.cancelUp': (x) => `Cancel uploading ${x}`,
    'music.oneAtATime': 'Wait for the current upload to finish.',
    'music.tooBig': (name, max) => `${name} is too big. Files can be up to ${max} MB.`,
    'music.badType': (name, types) => `${name} isn’t an audio file the speaker can play. Use ${types}.`,
    'music.noRoom': 'There isn’t enough space left on the server. Delete some files first.',
    'music.rename': (x) => `Rename ${x}`, 'music.del': (x) => `Delete ${x}`, 'music.deleted': (x) => `${x} deleted`,
    'music.fileName': 'File name', 'music.nameErr': 'Give it a name first.', 'music.byOwner': (n) => `by ${n}`,
    'music.filesMine': 'Your files', 'music.filesShared': 'Shared files', 'music.filesMembers': 'Members’ files',
    'music.filesPrivate': 'Files you upload are private: only you and the owner can see them.',
  },
  th: {
    'music.ctxIdle': 'เลือกแหล่งเพลง แล้วเล่นที่ลำโพงได้ทันที', 'music.ctxIdle.here': 'เลือกแหล่งเพลง แล้วเล่นที่อุปกรณ์นี้ได้ทันที',
    'music.ctxPlaying': (x) => `ลำโพงกำลังเล่น ${x}`, 'music.ctxPlaying.here': (x) => `กำลังเล่น ${x} ที่อุปกรณ์นี้`,
    'music.sources': 'แหล่งเพลง',
    'music.src.youtube': 'YouTube', 'music.src.radio': 'วิทยุ', 'music.src.podcasts': 'พอดแคสต์', 'music.src.files': 'ไฟล์ของฉัน',
    'music.whyJoox': 'ทำไมไม่มี Spotify, Joox หรือ Apple Music', 'music.whyJooxShort': 'Spotify, Joox และ Apple Music อยู่ไหน',
    'music.ytLabel': 'ค้นหา YouTube', 'music.ytPh': 'ค้นหา หรือวางลิงก์ YouTube',
    'music.ytHint': 'ค้นหาชื่อเพลง ศิลปิน หรือแนวเพลง หรือวางลิงก์ YouTube',
    'music.radioLabel': 'ค้นหาสถานีวิทยุ', 'music.radioPh': 'ค้นหาสถานี เช่น jazz',
    'music.favs': 'รายการโปรด', 'music.stations': 'สถานี', 'music.popular': 'สถานียอดนิยม',
    'music.favOn': (x) => `เอา ${x} ออกจากรายการโปรด`, 'music.favOff': (x) => `เพิ่ม ${x} เข้ารายการโปรด`,
    'music.podLabel': 'ชื่อพอดแคสต์ หรือลิงก์ RSS', 'music.podPh': 'ชื่อพอดแคสต์ หรือลิงก์ RSS', 'music.podFind': 'ค้นหา',
    'music.podHint': 'ค้นด้วยชื่อรายการ หรือวางลิงก์ RSS ของรายการเพื่อเปิดทันที',
    'music.podResults': (q) => `พอดแคสต์ที่ตรงกับ “${q}”`, 'music.allResults': 'ผลการค้นหาทั้งหมด',
    'music.episodesOf': (x) => `ตอนของ ${x}`, 'music.noEpisodes': 'ฟีดนี้ไม่มีตอนที่เป็นเสียง',
    'music.openShow': (x) => `ดูตอนของ ${x}`,
    'music.following': 'กำลังติดตาม', 'music.followOn': 'ติดตามอยู่', 'music.followOff': 'ติดตาม',
    'music.newN': (n) => `ใหม่ ${n} ตอน`, 'music.newEp': 'ใหม่', 'music.latest': (d) => `ตอนล่าสุด ${d}`,
    'music.allFollowed': 'ทั้งหมดที่ติดตาม',
    'music.filesNote': (types, max) => `ไฟล์เสียงไม่เกิน ${max} MB (${types}) ไฟล์จะเก็บไว้ที่เซิร์ฟเวอร์ลำโพง`,
    'music.used': (used, quota) => `ใช้ไป ${used} จาก ${quota}`,
    'music.upload': 'อัปโหลด', 'music.filesTitle': 'ไฟล์ที่อัปโหลดไว้', 'music.edit': 'แก้ไข', 'music.done': 'เสร็จ',
    'music.noFiles': 'ยังไม่มีไฟล์ แตะ อัปโหลด เพื่อเพิ่ม',
    'music.upPct': (p) => `กำลังอัปโหลด ${p}%`, 'music.upStart': 'กำลังเตรียม…', 'music.uploaded': (x) => `อัปโหลด ${x} แล้ว`,
    'music.upCancelled': 'ยกเลิกการอัปโหลดแล้ว', 'music.cancelUp': (x) => `ยกเลิกการอัปโหลด ${x}`,
    'music.oneAtATime': 'รอให้ไฟล์ที่กำลังอัปโหลดเสร็จก่อน',
    'music.tooBig': (name, max) => `${name} ใหญ่เกินไป ไฟล์ต้องไม่เกิน ${max} MB`,
    'music.badType': (name, types) => `${name} ไม่ใช่ไฟล์เสียงที่ลำโพงเล่นได้ ใช้ไฟล์ ${types}`,
    'music.noRoom': 'พื้นที่บนเซิร์ฟเวอร์เหลือไม่พอ ลบไฟล์เก่าออกก่อน',
    'music.rename': (x) => `เปลี่ยนชื่อ ${x}`, 'music.del': (x) => `ลบ ${x}`, 'music.deleted': (x) => `ลบ ${x} แล้ว`,
    'music.fileName': 'ชื่อไฟล์', 'music.nameErr': 'ตั้งชื่อก่อน', 'music.byOwner': (n) => `โดย ${n}`,
    'music.filesMine': 'ไฟล์ของคุณ', 'music.filesShared': 'ไฟล์ที่แชร์', 'music.filesMembers': 'ไฟล์ของสมาชิก',
    'music.filesPrivate': 'ไฟล์ที่คุณอัปโหลดเป็นแบบส่วนตัว เห็นได้แค่คุณกับเจ้าของ',
  },
});

const SOURCES = [
  { id: 'youtube', icon: 'yt' },
  { id: 'radio', icon: 'radio' },
  { id: 'podcasts', icon: 'mic' },
  { id: 'files', icon: 'file' },
];
// Kept between visits (module scope): the last search of each source, so coming back shows the same results.
const memo = { source: 'youtube', yt: null, radio: { q: '' }, pod: null, subs: null };
// "Add to playlist": the playlist-add glyph on Android (A_YouTube), the plus elsewhere
const ADD_IC = () => (isAndroid() ? 'playlist-add' : 'plus');

export async function render(ctx) {
  // common.css: the c-badge of the podcast counts
  await Promise.all([ctx.css('views/common.css'), ctx.css('views/media.css'), ctx.css('views/music.css')]);
  const asked = ctx.params[0];
  let source = SOURCES.some((s) => s.id === asked) ? asked : memo.source;
  const tracker = playTracker(ctx);
  const panel = h('div', { class: 'mu-panel' });
  const why = (cls) => h('div', { class: cls }, helpLink('joox', t(cls === 'mu-why-lg' ? 'music.whyJooxShort' : 'music.whyJoox')));

  const seg = segmented({
    label: t('music.sources'), cls: 'mu-src', value: source,
    options: SOURCES.map((s) => ({ value: s.id, label: [glyph(s.icon, 'xs mu-src-ic'), h('span', {}, t(`music.src.${s.id}`))] })),
    onChange: (v) => {
      source = v;
      memo.source = v;
      history.replaceState(null, '', `#/music/${v}`);
      show();
    },
  });

  const head = ctx.header({ title: t('nav.music'), actions: why('mu-why-lg'), sub: here('music.ctxIdle') });
  const node = h('div', { class: 'page mu' },
    head,
    seg, panel, why('mu-why-ph'));

  function show() {
    const build = { youtube: youtubePane, radio: radioPane, podcasts: podcastPane, files: filesPane }[source];
    panel.replaceChildren(build(ctx, tracker));
    if (ctx.motionReduced()) return;
    panel.classList.remove('enter'); void panel.offsetWidth; panel.classList.add('enter');
  }
  show();
  return {
    node,
    onStatus(s) {
      tracker.onStatus(s);
      const m = s.status && !s.error && s.status.media;
      const playing = m && m.title && m.title !== 'Announcement' && (m.state === 'PLAYING' || m.state === 'BUFFERING');
      headerSub(head, playing ? here('music.ctxPlaying', m.title) : here('music.ctxIdle'));
    },
  };
}

/* ---------- shared row builders ---------- */
function playButton(ctx, tracker, key, title, run, row, idleSub, live) {
  const btn = roundBtn('play', here('tb.playOn', title), () => {
    if (tracker.state(key) === 'playing') tracker.stop();
    else tracker.play(key, title, run, btn);
  }, 'primary');
  trackPlay(tracker, key, { btn, row, title, idleSub, live });
  return btn;
}

/* ---------- YouTube ---------- */
function youtubePane(ctx, tracker) {
  const out = h('div', { class: 'mu-out', 'aria-live': 'polite' });
  const paint = () => {
    const m = memo.yt;
    if (!m) { out.replaceChildren(note(t('music.ytHint'))); return; }
    if (m.loading) { out.replaceChildren(spinnerLine(t('tb.searching', m.q))); return; }
    if (m.error) { out.replaceChildren(errBox(m.error, () => search(m.q))); return; }
    if (!m.results.length) { out.replaceChildren(note(t('tb.noMatch', m.q))); return; }
    out.replaceChildren(note(t('tb.resultsFor', m.q), 'tb-cap'), h('div', { class: 'list tb-list tb-grid' }, m.results.map((v) => {
      const row = mediaRow({ th: thumb('youtube', { img: v.thumbnail, badge: fmtDur(v.duration), wide: true }), title: v.title, sub: v.channel || '' });
      const play = playButton(ctx, tracker, `yt:${v.video_id}`, v.title,
        () => ctx.api('/youtube', { body: { query: `https://www.youtube.com/watch?v=${v.video_id}`, title: v.title } }), row, v.channel || '');
      const add = roundBtn(ADD_IC(), t('tb.addX', v.title), () => pickPlaylist(ctx, { kind: 'youtube', source: v.video_id, title: v.title }));
      row.querySelector('.tb-act').append(play, add);
      return row;
    })));
  };
  async function search(q, btn) {
    if (!q) { memo.yt = null; out.replaceChildren(note(t('tb.typeFirst'))); return; }
    memo.yt = { q, loading: true };
    paint();
    await busy(btn, async () => {
      try {
        const results = await ctx.api(`/youtube/search?q=${encodeURIComponent(q)}&limit=12`, { signal: ctx.signal });
        memo.yt = { q, results };
      } catch (e) {
        if (e.name === 'AbortError') return;
        memo.yt = { q, error: errorText(e, ctx.user) };
      }
      if (out.isConnected) paint();
    });
  }
  const { form, input } = searchForm({ label: t('music.ytLabel'), placeholder: t('music.ytPh'), value: memo.yt ? memo.yt.q : '', onSearch: search });
  if (memo.yt && memo.yt.loading) search(memo.yt.q);
  paint();
  autofocus(input);
  return h('div', { class: 'mu-pane' }, form, out);
}

/* ---------- Radio ---------- */
function radioPane(ctx, tracker) {
  const favBox = h('div', { class: 'mu-block' });
  const out = h('div', { class: 'mu-block', 'aria-live': 'polite' });
  let favs = [];
  let timer = 0;
  const favOf = (s) => favs.find((f) => (s.uuid && f.uuid === s.uuid) || (!s.uuid && f.url === s.url));

  const stationRow = (s, isFav) => {
    const sub = [s.tags && s.tags.split(',').slice(0, 2).join(', '), s.country].filter(Boolean).join(', ');
    const row = mediaRow({ th: thumb('radio', { img: s.favicon }), title: s.name, sub });
    // favourites are shared: viewers play them but don't add or remove
    const heart = ctx.can('operator') ? h('button', { type: 'button', class: 'iconbtn mu-heart' }) : null;
    const paintHeart = () => {
      const f = favOf(s);
      heart.setAttribute('aria-pressed', String(!!f));
      heart.setAttribute('aria-label', t(f ? 'music.favOn' : 'music.favOff', s.name));
      heart.dataset.tip = heart.getAttribute('aria-label');
      heart.replaceChildren(glyph(f ? 'heart-on' : 'heart'));
    };
    if (heart) heart.addEventListener('click', () => busy(heart, async () => {
      try {
        const f = favOf(s);
        if (f) await ctx.api(`/radio/favorites/${f.id}`, { method: 'DELETE' });
        else await ctx.api('/radio/favorites', { body: s.uuid ? { uuid: s.uuid } : { url: s.url, name: s.name, content_type: s.content_type, favicon: s.favicon } });
        await loadFavs();
      } catch (e) { ctx.fail(e); }
      if (heart.isConnected) { paintHeart(); heart.focus({ preventScroll: true }); }
    }));
    if (heart) paintHeart();
    // url/name/favicon ride along for "This device" (local-player.js), which plays the stream without asking the server
    const stream = { url: s.url, name: s.name, content_type: s.content_type, favicon: s.favicon };
    const body = isFav ? { favorite_id: s.id, ...stream } : s.uuid ? { uuid: s.uuid, ...stream } : stream;
    const play = playButton(ctx, tracker, `radio:${s.uuid || s.url}`, s.name, () => ctx.api('/radio/play', { body }), row, sub, true);
    row.querySelector('.tb-act').append(...[heart, play].filter(Boolean));
    return row;
  };

  function paintFavs() {
    favBox.replaceChildren(...(favs.length ? [sectionLabel(t('music.favs')), h('div', { class: 'list tb-list tb-grid' }, favs.map((f) => stationRow(f, true)))] : []));
  }
  function paintResults() {
    const m = memo.radio;
    const label = m.q ? t('music.stations') : t('music.popular');
    if (m.loading) out.replaceChildren(sectionLabel(label), spinnerLine(t('tb.searching', m.q || '…')));
    else if (m.error) out.replaceChildren(sectionLabel(label), errBox(m.error, () => search(m.q)));
    else if (m.results && !m.results.length) out.replaceChildren(note(t('tb.noMatch', m.q)));
    else if (m.results) out.replaceChildren(sectionLabel(label), h('div', { class: 'list tb-list tb-grid' }, m.results.map((s) => stationRow(s, false))));
  }
  async function loadFavs() {
    favs = await ctx.api('/radio/favorites', { signal: ctx.signal });
    if (favBox.isConnected || !out.isConnected) paintFavs();
    // keep hearts in the results in step
    if (memo.radio.results && out.isConnected) paintResults();
  }
  async function search(q) {
    memo.radio = { q, loading: true };
    paintResults();
    try {
      memo.radio = { q, results: await ctx.api(`/radio/search?q=${encodeURIComponent(q)}&limit=24`, { signal: ctx.signal }) };
    } catch (e) {
      if (e.name === 'AbortError') return;
      memo.radio = { q, error: sourceError(e, ctx.user, 'radio') };
    }
    if (out.isConnected) paintResults();
  }
  const input = h('input', {
    class: 'input', type: 'search', placeholder: t('music.radioPh'), 'aria-label': t('music.radioLabel'), value: memo.radio.q || '',
    enterKeyHint: 'search', autocomplete: 'off', spellcheck: false,
    oninput: () => { clearTimeout(timer); timer = setTimeout(() => search(input.value.trim()), 500); },
  });
  ctx.onCleanup(() => clearTimeout(timer));
  const form = h('form', { role: 'search', class: 'tb-search solo', onsubmit: (e) => { e.preventDefault(); clearTimeout(timer); search(input.value.trim()); } }, input);
  androidSearch(form, input, null);
  loadFavs().catch((e) => { if (e.name !== 'AbortError') favBox.replaceChildren(errBox(errorText(e, ctx.user))); });
  if (memo.radio.results && !memo.radio.loading) paintResults(); else search(memo.radio.q || '');
  autofocus(input);
  return h('div', { class: 'mu-pane' }, form, favBox, out);
}

/* ---------- Podcasts ---------- */
// "Following": the member's own subscriptions (personal, like their playlists) with a count of episodes
// published since they last opened the show; opening one marks it seen.
function dayLabel(iso) {
  const d = new Date(iso), now = new Date();
  const y = new Date(now); y.setDate(now.getDate() - 1);
  if (sameDay(d, now)) return t('c.today');
  if (sameDay(d, y)) return t('c.yesterday');
  return d.toLocaleDateString(lang() === 'th' ? 'th-TH-u-ca-gregory' : 'en-GB', { day: 'numeric', month: 'short' });
}
function podcastPane(ctx, tracker) {
  const out = h('div', { class: 'mu-out', 'aria-live': 'polite' });
  const subsBox = h('div', { class: 'mu-block mu-subs' });
  const hint = note(t('music.podHint'), 'mu-hint');
  const m = () => memo.pod;

  function paintSubs() {
    const subs = memo.subs || [];
    const inShow = !!(m() && m().show && !m().error);
    subsBox.hidden = inShow || !subs.length;
    hint.hidden = inShow;
    subsBox.replaceChildren(...(subs.length ? [sectionLabel(t('music.following')), h('div', { class: 'list tb-list tb-grid' }, subs.map((s) => {
      const n = s.new_count;
      const label = n ? `${t('music.openShow', s.title)}, ${t('music.newN', n)}` : t('music.openShow', s.title);
      const open = h('button', { type: 'button', class: 'mu-rowbtn', 'aria-label': label, onclick: () => openFeed(s, true) });
      const sub = [s.author, s.latest_at && t('music.latest', dayLabel(s.latest_at))].filter(Boolean).join(' · ');
      const row = mediaRow({
        th: thumb('podcast', { img: s.artwork }), title: s.title, sub, cls: 'tb-tap mu-sub', props: { 'data-feed': s.feed_url },
        actions: [n ? badge(t('music.newN', n), 'mu-count') : null, icon('chev-right', 'sm tb-chev')].filter(Boolean),
      });
      row.prepend(open);
      return row;
    }))] : []));
  }
  async function loadSubs() {
    try {
      memo.subs = await ctx.api('/podcasts/subs', { signal: ctx.signal });
    } catch (e) {
      if (e.name !== 'AbortError') ctx.fail(e);
      return;
    }
    if (subsBox.isConnected) paintSubs();
  }

  function paint() {
    const p = m();
    paintSubs();
    if (!p) { out.replaceChildren(); return; }
    if (p.loading) { out.replaceChildren(spinnerLine(t('tb.searching', p.loading))); return; }
    if (p.error) { out.replaceChildren(errBox(p.error, p.retry)); return; }
    if (p.feed) { out.replaceChildren(episodesView(p)); return; }
    if (!p.shows.length) { out.replaceChildren(note(t('tb.noMatch', p.q))); return; }
    out.replaceChildren(sectionLabel(t('music.podResults', p.q)), h('div', { class: 'list tb-list tb-grid' }, p.shows.map((s) => {
      const open = h('button', { type: 'button', class: 'mu-rowbtn', 'aria-label': t('music.openShow', s.title), onclick: () => openFeed(s) });
      const row = mediaRow({ th: thumb('podcast', { img: s.artwork }), title: s.title, sub: [s.author, s.genre].filter(Boolean).join(', '), actions: [icon('chev-right', 'sm tb-chev')], cls: 'tb-tap' });
      row.prepend(open);
      return row;
    })));
  }
  function followButton(p, title) {
    const btn = h('button', { type: 'button', class: 'btn mu-follow' });
    const draw = () => {
      btn.setAttribute('aria-pressed', String(!!p.sub));
      btn.replaceChildren(...(p.sub ? [icon('check', 'xs'), t('music.followOn')] : [t('music.followOff')]));
    };
    btn.addEventListener('click', () => busy(btn, async () => {
      try {
        if (p.sub) {
          await ctx.api(`/podcasts/subs/${p.sub.id}`, { method: 'DELETE' });
          p.sub = null;
        } else {
          const f = p.feed;
          p.sub = await ctx.api('/podcasts/subs', { body: { feed_url: p.show.feed_url, title: title.slice(0, 200) || p.show.feed_url.slice(0, 200), author: f.author || p.show.author || null, artwork: f.artwork || p.show.artwork || null } });
        }
        loadSubs();
      } catch (e) { ctx.fail(e); }
      if (btn.isConnected) { draw(); btn.focus({ preventScroll: true }); }
    }));
    draw();
    return btn;
  }
  function episodesView(p) {
    const f = p.feed;
    const title = f.title || p.show.title || '';
    const back = p.fromSubs
      ? h('button', { type: 'button', class: 'linkbtn', onclick: () => { memo.pod = p.shows ? { q: p.q, shows: p.shows } : null; paint(); } }, icon('back', 'xs'), t('music.allFollowed'))
      : p.shows ? h('button', { type: 'button', class: 'linkbtn', onclick: () => { memo.pod = { q: p.q, shows: p.shows }; paint(); } }, icon('back', 'xs'), t('music.allResults')) : null;
    // new = published after the member's previous visit (seen_at as it was before this one)
    const isNew = (ep) => p.seenAt && ep.published && new Date(ep.published) > new Date(p.seenAt);
    const rows = f.episodes.map((ep) => {
      const meta = epMeta(ep);
      const sub = isNew(ep) ? [badge(t('music.newEp'), 'mu-new'), meta] : meta;
      const row = mediaRow({ th: thumb('podcast', { img: ep.thumbnail }), title: ep.title, sub: '' });
      row.sub.replaceChildren(...[].concat(sub));
      const play = playButton(ctx, tracker, `pod:${ep.url}`, ep.title,
        () => ctx.api('/podcasts/play', { body: { url: ep.url, title: ep.title.slice(0, 200), thumbnail: ep.thumbnail, content_type: ep.content_type } }), row, sub);
      const add = roundBtn(ADD_IC(), t('tb.addX', ep.title), () => pickPlaylist(ctx, {
        kind: 'podcast', source: ep.url, title: ep.title.slice(0, 200), duration: ep.duration, thumbnail: ep.thumbnail, content_type: ep.content_type,
      }));
      row.querySelector('.tb-act').append(play, add);
      return row;
    });
    return h('div', { class: 'mu-block' }, back,
      h('div', { class: 'mu-show' }, thumb('podcast', { img: f.artwork }),
        h('div', { class: 'mu-show-tx' }, h('h2', { class: 'mu-show-t' }, title), f.author ? h('p', { class: 'small' }, f.author) : null),
        followButton(p, title)),
      sectionLabel(t('music.episodesOf', title)),
      rows.length ? h('div', { class: 'list tb-list tb-grid' }, rows) : note(t('music.noEpisodes')));
  }
  async function openFeed(show, fromSubs = false) {
    const prev = m();
    const shows = prev && prev.shows, q = prev && prev.q;
    memo.pod = { q, shows, show, fromSubs, loading: show.title || show.feed_url };
    paint();
    try {
      const feed = await ctx.api(`/podcasts/episodes?feed=${encodeURIComponent(show.feed_url)}&limit=40`, { signal: ctx.signal });
      const sub = feed.subscription;
      memo.pod = { q, shows, show, fromSubs, feed, sub, seenAt: sub && sub.seen_at };
      if (sub) {
        // opened: its episodes so far stop counting as new (the badges stay for this visit)
        ctx.api(`/podcasts/subs/${sub.id}/seen`, { method: 'POST' })
          .then(() => { const s = (memo.subs || []).find((x) => x.id === sub.id); if (s) s.new_count = 0; })
          .catch(() => {});
      }
    } catch (e) {
      if (e.name === 'AbortError') return;
      memo.pod = { q, shows, show, fromSubs, error: sourceError(e, ctx.user, 'feed'), retry: () => openFeed(show, fromSubs) };
    }
    if (out.isConnected) { paint(); out.scrollIntoView({ block: 'nearest', behavior: ctx.motionReduced() ? 'auto' : 'smooth' }); }
  }
  async function search(q, btn) {
    if (!q) { memo.pod = null; paintSubs(); out.replaceChildren(note(t('tb.typeFirst'))); return; }
    if (isUrl(q)) { memo.pod = null; openFeed({ feed_url: q, title: '' }); return; }
    memo.pod = { q, loading: q };
    paint();
    await busy(btn, async () => {
      try {
        memo.pod = { q, shows: await ctx.api(`/podcasts/search?q=${encodeURIComponent(q)}&limit=20`, { signal: ctx.signal }) };
      } catch (e) {
        if (e.name === 'AbortError') return;
        memo.pod = { q, error: sourceError(e, ctx.user, 'podcast'), retry: () => search(q) };
      }
      if (out.isConnected) paint();
    });
  }
  const { form, input } = searchForm({ label: t('music.podLabel'), placeholder: t('music.podPh'), button: t('music.podFind'), value: (m() && m().q) || '', onSearch: search });
  paint();
  loadSubs();
  autofocus(input);
  return h('div', { class: 'mu-pane' }, form, subsBox, hint, out);
}

/* ---------- My files ---------- */
let upload = null; // { name, pct, xhr } while one is running (module scope: survives switching sources)
function filesPane(ctx, tracker) {
  const info = h('p', { class: 'tb-note mu-fnote' });
  const used = h('p', { class: 'small mu-used' });
  const err = h('div', { class: 'mu-uperr' });
  const progress = h('div', { class: 'mu-progress' });
  const listBox = h('div', { class: 'mu-block' });
  const picker = h('input', { type: 'file', class: 'sr-only', tabindex: '-1', 'aria-hidden': 'true', multiple: false });
  const upBtn = h('button', { type: 'button', class: 'btn primary', onclick: () => { if (upload) { err.replaceChildren(errBox(t('music.oneAtATime'))); return; } picker.click(); } }, glyph('upload', 'sm'), t('music.upload'));
  let data = null, editing = false;
  const me = ctx.user;
  const canEdit = (f) => f.can_edit;
  // personal files: the member's own first, then shared ones; owners also see other members' in their own group
  const groupOf = (f) => (f.owner_id == null ? 'shared' : f.mine ? 'mine' : 'members');
  const typeList = () => (data ? data.types.map((x) => x.replace('.', '')).join(', ') : 'mp3, m4a');

  async function load() {
    try {
      data = await ctx.api('/files', { signal: ctx.signal });
    } catch (e) {
      if (e.name !== 'AbortError') listBox.replaceChildren(errBox(errorText(e, ctx.user), load));
      return;
    }
    picker.accept = [...data.types, 'audio/*'].join(',');
    if (listBox.isConnected || !info.isConnected) paint();
  }
  function paint() {
    if (!data) return;
    info.textContent = t('music.filesNote', typeList(), Math.round(data.max_size / 1048576));
    used.textContent = t('music.used', size(data.used), size(data.quota));
    const items = data.items.filter((f) => !isPending(`file:${f.id}`));
    const editable = items.some(canEdit);
    if (!editable) editing = false;
    const editBtn = editable ? h('button', { type: 'button', class: 'btn quiet', 'aria-pressed': String(editing), onclick: () => { editing = !editing; paint(); listBox.querySelector('.mu-edit')?.focus(); } }, t(editing ? 'music.done' : 'music.edit')) : null;
    if (editBtn) editBtn.classList.add('mu-edit');
    if (!items.length) { listBox.replaceChildren(note(t('music.noFiles'))); return; }
    const groups = ['mine', 'shared', 'members'].map((g) => [g, items.filter((f) => groupOf(f) === g)]).filter(([, l]) => l.length);
    const label = (g) => (groups.length > 1 || g !== 'shared' ? t(`music.files${g[0].toUpperCase()}${g.slice(1)}`) : t('music.filesTitle'));
    listBox.replaceChildren(...groups.flatMap(([g, list], i) => [sectionLabel(label(g), i ? null : editBtn), fileList(list)]));
  }
  function fileList(list) {
    return h('div', { class: 'list tb-list tb-grid' }, list.map((f) => {
      const by = f.owner_id != null ? (f.mine ? null : f.owner_name) : f.uploader_id !== (me && me.id) ? f.uploader : null;
      const sub = [fileMeta(f), by ? t('music.byOwner', by) : null].filter(Boolean).join(lang() === 'th' ? ' ' : ', ');
      const row = mediaRow({ th: thumb('file'), title: f.title, sub });
      const act = row.querySelector('.tb-act');
      if (editing) {
        if (canEdit(f)) act.append(ibtn('pencil', t('music.rename', f.title), () => rename(f)), ibtn('trash', t('music.del', f.title), () => remove(f), 'mu-del'));
      } else {
        const play = playButton(ctx, tracker, `file:${f.id}`, f.title, () => ctx.api(`/files/${f.id}/play`, { body: {} }), row, sub);
        act.append(play, roundBtn(ADD_IC(), t('tb.addX', f.title), () => pickPlaylist(ctx, { kind: 'file', source: String(f.id) })));
      }
      return row;
    }));
  }
  function rename(f) {
    ctx.sheet({
      title: t('music.rename', f.title),
      build(body, sheet) {
        const input = h('input', { class: 'input', value: f.title, maxLength: 200 });
        const e2 = h('p', { class: 'form-error', role: 'alert' });
        const save = h('button', { type: 'submit', class: 'btn primary big wide' }, t('common.save'));
        body.append(h('form', {
          class: 'tb-form', novalidate: true,
          onsubmit: (e) => {
            e.preventDefault();
            const v = input.value.trim();
            if (!v) { input.setAttribute('aria-invalid', 'true'); e2.textContent = t('music.nameErr'); input.focus(); return; }
            busy(save, async () => {
              try {
                const r = await ctx.api(`/files/${f.id}`, { method: 'PATCH', body: { title: v } });
                Object.assign(f, r);
                sheet.close();
                paint();
              } catch (x) { e2.textContent = errorText(x, ctx.user); }
            });
          },
        }, field(t('music.fileName'), input), e2, save));
      },
    });
  }
  function remove(f) {
    const key = `file:${f.id}`;
    deleteLater(key, `/files/${f.id}`, {
      onDone: () => { data.items = data.items.filter((x) => x.id !== f.id); },
      onError: (e) => { ctx.fail(e); load(); },
    });
    paint();
    ctx.toast(t('music.deleted', f.title), 'info', { ms: 6000, action: { label: t('tb.undo'), run: () => { if (undoDelete(key)) paint(); } } });
  }

  function paintProgress() {
    if (!upload) { progress.replaceChildren(); return; }
    const pct = upload.pct;
    progress.replaceChildren(h('div', { class: 'list tb-list' }, mediaRow({
      th: thumb('file'), title: upload.name,
      sub: h('span', { class: 'mu-bar-wrap' },
        h('span', { class: 'mu-bar', role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': '100', 'aria-valuenow': String(pct ?? 0), 'aria-label': upload.name }, h('span', { style: { width: `${pct ?? 0}%` } })),
        h('span', {}, pct == null ? t('music.upStart') : t('music.upPct', pct))),
      actions: [iconBtn('close', t('music.cancelUp', upload.name), () => upload && upload.cancel && upload.cancel())],
    })));
  }
  picker.addEventListener('change', async () => {
    const file = picker.files && picker.files[0];
    picker.value = '';
    if (!file) return;
    err.replaceChildren();
    const ext = (file.name.match(/\.[^.]+$/) || [''])[0].toLowerCase();
    if (data && file.size > data.max_size) { err.replaceChildren(errBox(t('music.tooBig', file.name, Math.round(data.max_size / 1048576)))); return; }
    if (data && !data.types.includes(ext) && !(file.type || '').startsWith('audio/')) { err.replaceChildren(errBox(t('music.badType', file.name, typeList()))); return; }
    upload = { name: file.name, pct: null };
    paintProgress();
    try {
      const duration = await measure(file);
      const row = await send(file, duration, (pct) => { if (upload) { upload.pct = pct; if (progress.isConnected) paintProgress(); } });
      upload = null;
      ctx.toast(t('music.uploaded', row.title), 'ok');
      await load();
    } catch (e) {
      upload = null;
      if (e.cancelled) ctx.toast(t('music.upCancelled'), 'info');
      else {
        const msg = e.status === 413 ? t('music.tooBig', file.name, data ? Math.round(data.max_size / 1048576) : 50)
          : e.status === 415 ? t('music.badType', file.name, typeList())
            : e.status === 507 ? t('music.noRoom') : errorText(e, ctx.user);
        if (err.isConnected) err.replaceChildren(errBox(msg)); else ctx.toast(msg, 'err');
      }
    }
    if (progress.isConnected) paintProgress();
  });

  load();
  paintProgress();
  return h('div', { class: 'mu-pane' },
    h('div', { class: 'mu-fhead' }, h('div', {}, info, ctx.can('operator') ? null : h('p', { class: 'tb-note mu-fnote' }, t('music.filesPrivate')), used), upBtn),
    picker, err, progress, listBox);
}

/** Length of an audio file as the browser reads it (seconds), or null. Never blocks the upload for long. */
function measure(file) {
  return new Promise((resolve) => {
    let done = false;
    const url = URL.createObjectURL(file);
    const a = new Audio();
    const finish = (v) => { if (done) return; done = true; URL.revokeObjectURL(url); resolve(v); };
    a.preload = 'metadata';
    a.addEventListener('loadedmetadata', () => finish(Number.isFinite(a.duration) && a.duration > 0 ? Math.min(a.duration, 86400) : null));
    a.addEventListener('error', () => finish(null));
    setTimeout(() => finish(null), 4000);
    a.src = url;
  });
}

/** POST /files with the raw file as the body; progress(pct) from XHR upload events. Rejects with { status, detail }. */
function send(file, duration, progress) {
  const qs = `name=${encodeURIComponent(file.name.slice(0, 255))}${duration ? `&duration=${duration.toFixed(1)}` : ''}`;
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `/files?${qs}`);
    xhr.setRequestHeader('X-Requested-With', 'speaker-web');
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
    xhr.responseType = 'json';
    if (xhr.upload) xhr.upload.addEventListener('progress', (e) => { if (e.lengthComputable) progress(Math.min(99, Math.round((e.loaded / e.total) * 100))); });
    xhr.addEventListener('load', () => {
      const body = xhr.response;
      if (xhr.status >= 200 && xhr.status < 300) { progress(100); resolve(body); return; }
      reject(Object.assign(new Error('upload'), { status: xhr.status, detail: (body && typeof body.detail === 'string' && body.detail) || '' }));
    });
    xhr.addEventListener('error', () => reject(Object.assign(new Error('network'), { status: 0 })));
    xhr.addEventListener('abort', () => reject(Object.assign(new Error('cancelled'), { cancelled: true })));
    if (upload) upload.cancel = () => xhr.abort();
    xhr.send(file);
  }).catch((e) => {
    if (e.cancelled) throw e;
    throw new ApiError(e.status, e.detail); // errorText() reads status/detail off an ApiError
  });
}

function autofocus(input) {
  // focus the search once the page is shown (the router may swap it in a frame or two later, in a view transition)
  const focusIn = (n = 0) => { if (input.isConnected) input.focus({ preventScroll: true }); else if (n < 30) requestAnimationFrame(() => focusIn(n + 1)); };
  if (!matchMedia('(pointer: coarse)').matches && !input.value) setTimeout(focusIn, 60);
}
