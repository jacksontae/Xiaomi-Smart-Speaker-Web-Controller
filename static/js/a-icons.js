// Team A icons (Now playing, Announce, Help) that the sprite in index.html doesn't have yet. Same drawing rules as
// the sprite (24 px grid, 2 px stroke, round caps) and the same .icon classes, so they can move into the sprite later:
//   aicon('play', 'lg')  ->  <svg class="icon lg">…</svg>
// Filled glyphs (play/pause/stop/prev/next) set fill="currentColor" themselves.

const NS = 'http://www.w3.org/2000/svg';

const PATHS = {
  play: '<path fill="currentColor" stroke="none" d="M8 5.2v13.6a1 1 0 0 0 1.5.86l11-6.8a1 1 0 0 0 0-1.72l-11-6.8A1 1 0 0 0 8 5.2z"/>',
  pause: '<rect fill="currentColor" stroke="none" x="6" y="5" width="4" height="14" rx="1.2"/><rect fill="currentColor" stroke="none" x="14" y="5" width="4" height="14" rx="1.2"/>',
  stop: '<rect fill="currentColor" stroke="none" x="6" y="6" width="12" height="12" rx="2"/>',
  prev: '<path fill="currentColor" stroke="none" d="M18 6.2v11.6a.8.8 0 0 1-1.2.7L8.6 12.7a.8.8 0 0 1 0-1.4l8.2-5.8a.8.8 0 0 1 1.2.7z"/><rect fill="currentColor" stroke="none" x="5" y="5.5" width="2.4" height="13" rx="1"/>',
  next: '<path fill="currentColor" stroke="none" d="M6 6.2v11.6a.8.8 0 0 0 1.2.7l8.2-5.8a.8.8 0 0 0 0-1.4L7.2 5.5A.8.8 0 0 0 6 6.2z"/><rect fill="currentColor" stroke="none" x="16.6" y="5.5" width="2.4" height="13" rx="1"/>',
  shuffle: '<path d="M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5"/>',
  repeat: '<path d="M17 2l4 4-4 4"/><path d="M3 11V9a3 3 0 0 1 3-3h15"/><path d="M7 22l-4-4 4-4"/><path d="M21 13v2a3 3 0 0 1-3 3H3"/>',
  'repeat-one': '<path d="M17 2l4 4-4 4"/><path d="M3 11V9a3 3 0 0 1 3-3h15"/><path d="M7 22l-4-4 4-4"/><path d="M21 13v2a3 3 0 0 1-3 3H3"/><path d="M11 10.5l1.5-1V15"/>',
  'vol-low': '<path d="M5 10v4h3l5 4V6L8 10H5z"/><path d="M16.5 9.5a3.5 3.5 0 0 1 0 5"/>',
  'vol-x': '<path d="M3 10v4h4l6 5V5L7 10H3z"/><path d="M16 9l5 6M21 9l-5 6"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  'mic-off': '<path d="M9 9v2a3 3 0 0 0 5.1 2.1M15 10V6a3 3 0 0 0-5.7-1.3"/><path d="M5 11a7 7 0 0 0 11.6 5.3M19 11a7 7 0 0 1-.6 2.8M12 18v3M3 3l18 18"/>',
  unlock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 7.5-2"/>',
  'arrow-up': '<path d="M12 19V5M6 11l6-6 6 6"/>',
  note: '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',
  radio: '<rect x="3" y="8" width="18" height="12" rx="2"/><path d="M7 8l10-5"/><circle cx="15.5" cy="14" r="2.5"/><path d="M6.5 12.5h3M6.5 15.5h3"/>',
  podcast: '<circle cx="12" cy="11" r="2"/><path d="M12 13v8"/><path d="M8.5 15a5 5 0 1 1 7 0"/><path d="M6 18a8.5 8.5 0 1 1 12 0"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><circle cx="10.5" cy="16" r="1.8"/><path d="M12.3 16v-5l2.7 1"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  clock: '<circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/>',
  'play-circle': '<circle cx="12" cy="12" r="9"/><path d="M10 8.5v7l5.5-3.5z"/>',
  queue: '<path d="M4 6h11M4 12h11M4 18h7"/><path d="M17 15l4 3-4 3z"/>',
  wrench: '<path d="M14.7 6.3a4 4 0 0 0 5 5L21 13l-8 8-3-3 1.4-1.3a4 4 0 0 1-5-5L3 8.4 8.4 3l3.3 3.3"/>',
  wifi: '<path d="M2 8.8a15 15 0 0 1 20 0M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0"/><path d="M12 19.5h.01"/>',
  search: '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
};

/** Inline SVG icon from PATHS; unknown names render an empty box (easy to spot). */
export function aicon(name, cls = '') {
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('class', `icon ${cls}`.trim());
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  svg.innerHTML = PATHS[name] || '';
  return svg;
}
