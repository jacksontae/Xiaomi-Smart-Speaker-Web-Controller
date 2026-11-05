// Inline icons the sprite in index.html doesn't have. One set for every page, drawn like the sprite (24 px grid,
// 2 px stroke, round caps) with the same .icon classes; filled glyphs (play, pause, stop, prev, next...) set
// fill="currentColor" themselves. glyph() falls back to the sprite, so any sprite name works too:
//   glyph('play', 'lg')  ->  <svg class="icon lg">…</svg>
import { icon } from './ui.js';

const NS = 'http://www.w3.org/2000/svg';

const PATHS = {
  alert: '<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/>',
  'arrow-up': '<path d="M12 19V5M6 11l6-6 6 6"/>',
  calendar: '<path d="M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z"/><path d="M4 10h16M8 3v4M16 3v4"/>',
  clock: '<circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/>',
  down: '<path d="M6 9l6 6 6-6"/>',
  download: '<path d="M12 4v11M7 10l5 5 5-5"/><path d="M5 16v3a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><circle cx="10.5" cy="16" r="1.8"/><path d="M12.3 16v-5l2.7 1"/>',
  gear: '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
  grip: '<path stroke-width="3" d="M9 6h.01M15 6h.01M9 12h.01M15 12h.01M9 18h.01M15 18h.01"/>',
  heart: '<path d="M12 20s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.2a4.3 4.3 0 0 1 7.5 2.6C19.5 15.4 12 20 12 20z"/>',
  'heart-on': '<path fill="currentColor" stroke="none" d="M12 20s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.2a4.3 4.3 0 0 1 7.5 2.6C19.5 15.4 12 20 12 20z"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  list: '<path d="M5 7h14M5 12h14M5 17h9"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  'mic-off': '<path d="M9 9v2a3 3 0 0 0 5.1 2.1M15 10V6a3 3 0 0 0-5.7-1.3"/><path d="M5 11a7 7 0 0 0 11.6 5.3M19 11a7 7 0 0 1-.6 2.8M12 18v3M3 3l18 18"/>',
  more: '<path stroke-width="3" d="M5 12h.01M12 12h.01M19 12h.01"/>',
  next: '<path fill="currentColor" stroke="none" d="M6 6.2v11.6a.8.8 0 0 0 1.2.7l8.2-5.8a.8.8 0 0 0 0-1.4L7.2 5.5A.8.8 0 0 0 6 6.2z"/><rect fill="currentColor" stroke="none" x="16.6" y="5.5" width="2.4" height="13" rx="1"/>',
  note: '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',
  pause: '<rect fill="currentColor" stroke="none" x="6" y="5" width="4" height="14" rx="1.2"/><rect fill="currentColor" stroke="none" x="14" y="5" width="4" height="14" rx="1.2"/>',
  pencil: '<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
  play: '<path fill="currentColor" stroke="none" d="M8 5.2v13.6a1 1 0 0 0 1.5.86l11-6.8a1 1 0 0 0 0-1.72l-11-6.8A1 1 0 0 0 8 5.2z"/>',
  'play-circle': '<circle cx="12" cy="12" r="9"/><path d="M10 8.5v7l5.5-3.5z"/>',
  podcast: '<circle cx="12" cy="11" r="2"/><path d="M12 13v8"/><path d="M8.5 15a5 5 0 1 1 7 0"/><path d="M6 18a8.5 8.5 0 1 1 12 0"/>',
  prev: '<path fill="currentColor" stroke="none" d="M18 6.2v11.6a.8.8 0 0 1-1.2.7L8.6 12.7a.8.8 0 0 1 0-1.4l8.2-5.8a.8.8 0 0 1 1.2.7z"/><rect fill="currentColor" stroke="none" x="5" y="5.5" width="2.4" height="13" rx="1"/>',
  queue: '<path d="M4 6h11M4 12h11M4 18h7"/><path d="M17 15l4 3-4 3z"/>',
  radio: '<rect x="3" y="8" width="18" height="12" rx="2"/><path d="M7 8l10-5"/><circle cx="15.5" cy="14" r="2.5"/><path d="M6.5 12.5h3M6.5 15.5h3"/>',
  repeat: '<path d="M17 2l4 4-4 4"/><path d="M3 11V9a3 3 0 0 1 3-3h15"/><path d="M7 22l-4-4 4-4"/><path d="M21 13v2a3 3 0 0 1-3 3H3"/>',
  'repeat-one': '<path d="M17 2l4 4-4 4"/><path d="M3 11V9a3 3 0 0 1 3-3h15"/><path d="M7 22l-4-4 4-4"/><path d="M21 13v2a3 3 0 0 1-3 3H3"/><path d="M11 10.5l1.5-1V15"/>',
  scan: '<circle cx="12" cy="12" r="2"/><path d="M8.5 8.5a5 5 0 0 0 0 7M15.5 8.5a5 5 0 0 1 0 7M5.6 5.6a9 9 0 0 0 0 12.8M18.4 5.6a9 9 0 0 1 0 12.8"/>',
  shield: '<path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z"/><path d="M9 12l2 2 4-4"/>',
  shuffle: '<path d="M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5"/>',
  stop: '<rect fill="currentColor" stroke="none" x="6" y="6" width="12" height="12" rx="2"/>',
  text: '<path d="M4 6h16M4 12h16M4 18h10"/>',
  top: '<path d="M5 5h14M12 19V9M7 13l5-5 5 5"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
  unlock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 7.5-2"/>',
  up: '<path d="M6 15l6-6 6 6"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M5 16v3a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3"/>',
  'user-plus': '<circle cx="10" cy="8" r="3.5"/><path d="M3.5 20a6.5 6.5 0 0 1 11.5-4.2M18 14v6M15 17h6"/>',
  'vol-low': '<path d="M5 10v4h3l5 4V6L8 10H5z"/><path d="M16.5 9.5a3.5 3.5 0 0 1 0 5"/>',
  'vol-x': '<path d="M3 10v4h4l6 5V5L7 10H3z"/><path d="M16 9l5 6M21 9l-5 6"/>',
  volume: '<path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16.5 8.5a5 5 0 0 1 0 7"/>',
  wifi: '<path d="M2 8.8a15 15 0 0 1 20 0M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0"/><path d="M12 19.5h.01"/>',
  wrench: '<path d="M14.7 6.3a4 4 0 0 0 5 5L21 13l-8 8-3-3 1.4-1.3a4 4 0 0 1-5-5L3 8.4 8.4 3l3.3 3.3"/>',
  yt: '<path d="M3 8a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3v8a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3z"/><path fill="currentColor" stroke="none" d="M10.5 9.5v5l4-2.5z"/>',
};

/** An inline SVG icon from PATHS, or the sprite's icon of that name. */
export function glyph(name, cls = '') {
  if (!(name in PATHS)) return icon(name, cls);
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('class', `icon ${cls}`.trim());
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  svg.innerHTML = PATHS[name];
  return svg;
}
