// Wavy progress (Android look, M3 Expressive; board A_Now): a sine line for the played part, a flat track for the
// rest, a stop dot at the end. Display only (there is no seek endpoint). The caller keeps the role="progressbar"
// element and sets --np-pos on it; styles live in css/views/now.css.
// Heat: the wave's phase drifts with a CSS transform on one small SVG (compositor only) and only while the page
// marks itself playing; it is static otherwise and under reduced motion.

const NS = 'http://www.w3.org/2000/svg';
const WL = 28;      // wavelength, px (the CSS keyframes move the wave by exactly this)
const AMP = 3;      // amplitude, px
const H = 16;       // track height, px
const LEN = 2400;   // drawn length: wider than any player column

let pathD = '';
const wavePath = () => {
  if (!pathD) {
    pathD = `M2 ${H / 2}`;
    for (let x = 0; x < LEN + WL; x += WL) pathD += ` q${WL / 4} ${-AMP * 2} ${WL / 2} 0 t${WL / 2} 0`;
  }
  return pathD;
};

export function wavyTrack() {
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('class', 'aw-wave');
  svg.setAttribute('width', String(LEN + WL + 4));
  svg.setAttribute('height', String(H));
  svg.setAttribute('viewBox', `0 0 ${LEN + WL + 4} ${H}`);
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  const path = document.createElementNS(NS, 'path');
  path.setAttribute('d', wavePath());
  svg.append(path);

  const on = document.createElement('span');
  on.className = 'aw-on';
  on.append(svg);
  const off = document.createElement('span');
  off.className = 'aw-off';
  const el = document.createElement('span');
  el.className = 'aw';
  el.setAttribute('aria-hidden', 'true');
  el.append(on, off);
  return el;
}
