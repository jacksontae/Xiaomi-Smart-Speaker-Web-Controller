// 3D speaker model (tier 1, CSS 3D; styles in css/speaker3d.css, design notes in the speaker-3d-motion skill).
// The model is decoration that mirrors real state; the same state is always written in text next to it.
//
//   const spk = speaker3d({ state: 'spk-idle spk-breathe' });   // size: CSS --spk-size on .spk-stage, or { size: '240px' }
//   wrapper.append(spk.el); spk.setState('spk-speaking'); spk.flash('spk-success');
//
// Drag turns it (yaw) and tilts it; tilt springs back on release. Reduced motion: static view, drag still works.
import { h } from './ui.js';

const STATES = ['spk-idle', 'spk-listening', 'spk-speaking', 'spk-success', 'spk-error', 'spk-off', 'spk-breathe'];

export function speaker3d({ size = null, state = 'spk-idle' } = {}) {
  const faces = Array.from({ length: 28 }, (_, i) => h('span', { class: 'spk-face' }));
  faces.forEach((f, i) => f.style.setProperty('--a', `${(i * 360) / 28}deg`));
  const model = h('div', { class: `spk ${state}`, 'aria-hidden': 'true' },
    h('div', { class: 'spk-scene' },
      h('div', { class: 'spk-floor' }, h('span', { class: 'spk-shadow' }), h('span', { class: 'spk-ring r1' }), h('span', { class: 'spk-ring r2' }), h('span', { class: 'spk-ring r3' })),
      h('div', { class: 'spk-body' }, h('div', { class: 'spk-yaw' }, faces, h('div', { class: 'spk-top' }, h('span', { class: 'spk-led' }))))));
  const el = h('div', { class: 'spk-stage', 'aria-hidden': 'true' }, model);
  if (size) el.style.setProperty('--spk-size', size); // else the stylesheet sizes it (responsive clamp())

  let drag = null;
  model.addEventListener('pointerdown', (e) => {
    const cs = getComputedStyle(model);
    drag = { x: e.clientX, y: e.clientY, yaw: parseFloat(cs.getPropertyValue('--spk-drag')) || 0 };
    model.setAttribute('data-drag', '');
    try { model.setPointerCapture(e.pointerId); } catch { /* ignore */ }
  });
  model.addEventListener('pointermove', (e) => {
    if (!drag) return;
    model.style.setProperty('--spk-drag', `${drag.yaw + (e.clientX - drag.x) * 0.7}deg`);
    model.style.setProperty('--spk-tilt', `${Math.max(-42, Math.min(-4, -9 - (e.clientY - drag.y) * 0.3))}deg`);
  });
  const up = () => { if (!drag) return; drag = null; model.removeAttribute('data-drag'); model.style.removeProperty('--spk-tilt'); };
  model.addEventListener('pointerup', up);
  model.addEventListener('pointercancel', up);

  let base = state;
  let flashTimer = 0;
  const apply = (cls) => {
    model.classList.remove(...STATES);
    model.classList.add(...cls.split(/\s+/).filter(Boolean));
  };
  return {
    el,
    /** Steady state: 'spk-idle spk-breathe' | 'spk-listening' | 'spk-speaking' | 'spk-off'. */
    setState(cls) { base = cls; if (!flashTimer) apply(cls); },
    /** One-shot: 'spk-success' (900 ms) or 'spk-error' (1.2 s), then back to the steady state. */
    flash(cls) {
      clearTimeout(flashTimer);
      apply('spk-idle'); void model.offsetWidth; apply(cls);
      flashTimer = setTimeout(() => { flashTimer = 0; apply(base); }, cls === 'spk-error' ? 1200 : 900);
    },
  };
}
