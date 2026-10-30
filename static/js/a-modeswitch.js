// The Announce mode switch, one component for #/announce and #/schedule so it looks and behaves the same on both:
// Announce now | Talk live | Schedule, one sliding thumb. Talk live shows only for operators when the server
// offers it (GET /talk/status -> { available: true }); the answer is remembered for the session so moving between
// the two pages never adds, drops, reorders or resizes a tab. Styles: css/views/a-modeswitch.css.
import { h } from './ui.js';
import { register, t } from './i18n.js';

register({
  en: { 'am.aria': 'Announce mode', 'am.say': 'Announce now', 'am.talk': 'Talk live', 'am.schedule': 'Schedule' },
  th: { 'am.aria': 'โหมดประกาศ', 'am.say': 'ประกาศเลย', 'am.talk': 'พูดสด', 'am.schedule': 'ตั้งเวลา' },
});

const wideMq = matchMedia('(min-width: 1280px)');
let talkKnown = null; // null = not asked yet this session, else the last /talk/status body ({} when it failed)

/**
 * modeSwitch(ctx, { current: 'say'|'talk'|'schedule', onPick(mode) -> bool, onTalk(info) })
 * onPick handles a choice in place (return true), otherwise the switch navigates to that mode's page.
 * onTalk(info) runs once the /talk/status answer is in (cached or fresh). Returns
 * { el, slot, headActs, set(mode), talkAvailable() }: put `headActs` in the page header actions and `slot` under the
 * header; the switch moves between them at the desktop breakpoint (like the boards).
 */
export function modeSwitch(ctx, { current, onPick = () => false, onTalk = () => {} }) {
  const op = ctx.can('operator');
  let mode = current;
  // before the first answer assume Talk live is there (the usual case), so the switch doesn't grow a tab later
  let talkAvail = !!(op && (talkKnown ? talkKnown.available : true));
  const thumb = h('span', { class: 'seg-thumb', 'aria-hidden': 'true' });
  const tab = (m, label) => h('button', { type: 'button', role: 'tab', dataset: { mode: m }, onclick: () => pick(m) }, label);
  const tabs = { say: tab('say', t('am.say')), talk: tab('talk', t('am.talk')), schedule: tab('schedule', t('am.schedule')) };
  const el = h('div', { class: 'seg ann-seg', role: 'tablist', 'aria-label': t('am.aria') }, thumb, tabs.say, tabs.talk, tabs.schedule);
  const visible = () => Object.values(tabs).filter((b) => !b.hidden);
  el.addEventListener('keydown', (e) => {
    const list = visible();
    const i = list.indexOf(document.activeElement);
    const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
    if (i < 0 || !step) return;
    e.preventDefault();
    const n = list[(i + step + list.length) % list.length];
    n.focus(); n.click();
  });

  function pick(m) {
    if (m === mode) return;
    if (onPick(m)) return;
    ctx.go({ say: '#/announce', talk: '#/announce/talk', schedule: '#/schedule' }[m]);
  }
  function paintTalk() {
    tabs.talk.hidden = !talkAvail;
    el.classList.toggle('two', !talkAvail);
  }
  function place(animate) {
    const b = tabs[mode] && !tabs[mode].hidden ? tabs[mode] : tabs.say;
    thumb.classList.toggle('no-anim', !animate);
    thumb.style.width = `${b.offsetWidth}px`;
    thumb.style.setProperty('--x', `${b.offsetLeft}px`);
  }
  function set(m, animate = true) {
    mode = m;
    for (const [k, b] of Object.entries(tabs)) {
      b.setAttribute('aria-selected', String(k === m));
      b.tabIndex = k === m ? 0 : -1;
    }
    place(animate);
  }
  new ResizeObserver(() => place(false)).observe(el);

  const headActs = h('div', { class: 'ann-headacts' });
  const slot = h('div', { class: 'ann-segslot' });
  const mount = () => { (wideMq.matches ? headActs : slot).append(el); requestAnimationFrame(() => place(false)); };
  wideMq.addEventListener('change', mount);
  ctx.onCleanup(() => wideMq.removeEventListener('change', mount));
  mount();
  paintTalk();
  set(mode, false);

  if (op) {
    const cached = talkKnown;
    if (cached) queueMicrotask(() => onTalk(cached)); // after the page's render has finished wiring up
    ctx.api('/talk/status', { signal: ctx.signal }).then((r) => r || {}, (e) => { if (e.name === 'AbortError') throw e; return {}; })
      .then((info) => {
        talkKnown = info;
        const was = talkAvail;
        talkAvail = !!info.available;
        if (was !== talkAvail) { paintTalk(); requestAnimationFrame(() => place(false)); }
        onTalk(info);
      }).catch(() => {});
  }
  return { el, slot, headActs, set, talkAvailable: () => talkAvail };
}
