// Icons the music / playlists / schedule pages need that the sprite in index.html doesn't have yet.
// Same style as the sprite (24px, stroke 2, round caps). The lead can move these into the sprite later;
// until then bicon('play') returns an inline <svg class="icon">. Unknown names fall back to the sprite.
import { icon } from './ui.js';

const SVG = 'http://www.w3.org/2000/svg';

// name -> [paths (stroked), filled paths]
const PATHS = {
  play: [[], ['M8 5.5v13l10.5-6.5z']],
  stop: [[], ['M7 6h10a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1z']],
  shuffle: [['M4 7h3c4 0 6 10 10 10h3M4 17h3c1.6 0 2.8-1.6 3.9-3.6M13.1 9.6C14.2 8.1 15.4 7 17 7h3', 'M18 4l3 3-3 3M18 14l3 3-3 3'], []],
  repeat: [['M17 3l3 3-3 3', 'M4 11V9a3 3 0 0 1 3-3h13', 'M7 21l-3-3 3-3', 'M20 13v2a3 3 0 0 1-3 3H4'], []],
  'repeat-one': [['M17 3l3 3-3 3', 'M4 11V9a3 3 0 0 1 3-3h13', 'M7 21l-3-3 3-3', 'M20 13v2a3 3 0 0 1-3 3H4', 'M11.5 10.5l1.5-1v5'], []],
  more: [['M5 12h.01M12 12h.01M19 12h.01'], []],
  trash: [['M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3'], []],
  top: [['M5 5h14M12 19V9M7 13l5-5 5 5'], []],
  up: [['M6 15l6-6 6 6'], []],
  down: [['M6 9l6 6 6-6'], []],
  grip: [['M9 6h.01M15 6h.01M9 12h.01M15 12h.01M9 18h.01M15 18h.01'], []],
  yt: [['M3 8a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3v8a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3z'], ['M10.5 9.5v5l4-2.5z']],
  radio: [['M5 8h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2z', 'M7 8l10-4', 'M6.5 12h3M6.5 16h3', 'M16 16.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z'], []],
  mic: [['M12 3a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3z', 'M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21'], []],
  file: [['M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z', 'M14 3v5h5', 'M12.5 16.5v-5l2.5 1', 'M11 18a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z'], []],
  upload: [['M12 16V4M7 9l5-5 5 5', 'M5 16v3a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3'], []],
  link: [['M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1', 'M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1'], []],
  text: [['M4 6h16M4 12h16M4 18h10'], []],
  heart: [['M12 20s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.2a4.3 4.3 0 0 1 7.5 2.6C19.5 15.4 12 20 12 20z'], []],
  'heart-on': [[], ['M12 20s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.2a4.3 4.3 0 0 1 7.5 2.6C19.5 15.4 12 20 12 20z']],
  pencil: [['M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z', 'M13.5 6.5l4 4'], []],
  clock: [['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z', 'M12 7v5l3 2'], []],
  calendar: [['M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z', 'M4 10h16M8 3v4M16 3v4'], []],
};

export function bicon(name, cls = '') {
  const p = PATHS[name];
  if (!p) return icon(name, cls);
  const svg = document.createElementNS(SVG, 'svg');
  svg.setAttribute('class', `icon ${cls}`.trim());
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  for (const d of p[0]) {
    const el = document.createElementNS(SVG, 'path');
    el.setAttribute('d', d);
    if (name === 'more' || name === 'grip') el.setAttribute('stroke-width', '3');
    svg.append(el);
  }
  for (const d of p[1]) {
    const el = document.createElementNS(SVG, 'path');
    el.setAttribute('d', d);
    el.setAttribute('fill', 'currentColor');
    el.setAttribute('stroke', 'none');
    svg.append(el);
  }
  return svg;
}
