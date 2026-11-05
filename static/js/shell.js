// App chrome around the views: phone top bar + tab bar, iPad/desktop sidebar, speaker control, account menu,
// change-password sheet, page header helper. Built once per sign-in / language / look change by app.js.
// Android look (<html data-os="android">, css/android.css): the same markup restyled as a floating navigation pill
// (phone) and a navigation rail (tablet), plus three small branches here: the account avatar in the phone top bar,
// the Now Bar (a playing capsule above the nav on every page but Now) and short rail labels.
import { h, icon, avatar, field, passwordInput, busy, tip, toast } from './ui.js';
import { t, roleLabel } from './i18n.js';
import { ROUTES, RANK, href } from './routes.js';
import { openSheet, popover, isPhone, closePopover } from './sheet.js';
import { errorText } from './api.js';
import { isAndroid } from './prefs.js';
import { glyph } from './icons.js';

/**
 * Android nav pill and rail: press and slide along it (touch or pen), the destination under the finger lights up
 * (data-hot) and releasing there opens it (prototype snippets/seg-drag.html). Taps and mouse clicks are untouched;
 * the pill keeps vertical page panning (touch-action pan-y), the rail horizontal (pan-x). Listeners only.
 */
function dragToSelect(bar, axis) {
  let g = null;           // { pid, x0, y0, on, hot }
  let swallowUntil = 0;   // the click that follows a drag release must not also fire on the start item
  const items = () => [...bar.querySelectorAll('a[data-route]')].filter((a) => a.offsetParent);
  const setHot = (a) => {
    if (g.hot === a) return;
    if (g.hot) g.hot.removeAttribute('data-hot');
    g.hot = a;
    if (a) a.setAttribute('data-hot', '');
  };
  const end = (go) => {
    if (!g) return;
    const { on, hot } = g;
    if (hot) hot.removeAttribute('data-hot');
    bar.removeAttribute('data-dragging');
    g = null;
    if (!on) return;
    swallowUntil = Date.now() + 500;
    if (go && hot && !hot.hasAttribute('aria-current')) location.hash = hot.getAttribute('href');
  };
  bar.addEventListener('pointerdown', (e) => {
    if (e.pointerType === 'mouse' || g) return;
    g = { pid: e.pointerId, x0: e.clientX, y0: e.clientY, on: false, hot: null };
  });
  bar.addEventListener('pointermove', (e) => {
    if (!g || e.pointerId !== g.pid) return;
    const along = axis === 'x' ? e.clientX - g.x0 : e.clientY - g.y0;
    const across = axis === 'x' ? e.clientY - g.y0 : e.clientX - g.x0;
    if (!g.on) {
      if (Math.abs(along) < 8) { if (Math.abs(across) > 10) g = null; return; }
      if (Math.abs(across) > Math.abs(along)) { g = null; return; }
      g.on = true;
      bar.setAttribute('data-dragging', '');
      try { bar.setPointerCapture(e.pointerId); } catch { /* still tracks while over the bar */ }
    }
    const pos = axis === 'x' ? e.clientX : e.clientY;
    let best = null, bd = Infinity;
    for (const a of items()) {
      const r = a.getBoundingClientRect();
      const lo = axis === 'x' ? r.left : r.top, hi = axis === 'x' ? r.right : r.bottom;
      const d = pos < lo ? lo - pos : pos > hi ? pos - hi : 0;
      if (d < bd) { bd = d; best = a; }
    }
    setHot(best);
  });
  bar.addEventListener('pointerup', (e) => { if (g && e.pointerId === g.pid) end(true); });
  bar.addEventListener('pointercancel', () => end(false));
  bar.addEventListener('click', (e) => { if (Date.now() < swallowUntil) { e.preventDefault(); e.stopPropagation(); } }, true);
}

// Android rail: labels that fit an 80 px column (the phone tab label, else a short form, else the full name)
const RAIL_LABEL = { settings: 'rail.settings', activity: 'rail.activity', help: 'rail.help' };

/**
 * buildShell({ user, api, allowed, onSignOut, onPickSpeaker, onCommand }) -> shell
 * allowed(route): may this member open it now (app.js: role, and the output for Music); the nav lists those.
 * shell.el, shell.content (the <main>), shell.markRoute(route), shell.setSpeakers(list), shell.setStatus(status, err),
 * shell.header(opts), shell.accountItems(close) (menu rows reused by the phone Account page), shell.destroy()
 * onCommand(path): POST a speaker command (Now Bar play/pause) and refresh /status; resolves when done.
 */
export function buildShell({ user, api, allowed, onSignOut, onPickSpeaker, onCommand }) {
  const android = isAndroid();
  const can = (role) => RANK[user.role] >= RANK[role];
  const routes = ROUTES.filter((r) => (allowed ? allowed(r) : can(r.min)));
  const main = routes.filter((r) => r.section === 'main');
  const admin = routes.filter((r) => r.section === 'admin');
  let speakers = [];
  let chips = []; // every rendered speaker control, refreshed on setSpeakers

  /* ----- phone: top bar + tab bar ----- */
  const barLeft = h('div', { class: 'topbar-l' });
  const barTitle = h('span', { class: 'topbar-t', 'aria-hidden': 'true' });
  const barRight = h('div', { class: 'topbar-r' });
  const topbar = h('div', { class: 'topbar', 'data-under': 'false', 'data-title': 'false' }, barLeft, barTitle, barRight);

  const tabThumb = h('span', { class: 'tab-thumb', 'aria-hidden': 'true' });
  // Android: the active destination shows a filled icon (sprite i-<name>-fill), the others the outlined one
  const navIcon = (r) => (android ? [icon(r.icon, 'ic-o'), icon(`${r.icon}-fill`, 'ic-f')] : icon(r.icon));
  const tabbar = h('div', { class: 'tabbar glass' }, tabThumb,
    main.map((r) => h('a', { class: 'tab', href: href(r.id), dataset: { route: r.id } }, navIcon(r), h('span', {}, t(r.tab)))));
  const meBtn = h('a', { class: 'me-btn glass', href: href('account'), dataset: { route: 'account' }, 'aria-label': t('acct.aria', user.display_name, roleLabel(user.role)) }, avatar(user));
  const tabdock = h('nav', { class: 'tabdock', 'aria-label': t('nav.main') }, tabbar, meBtn);

  /* ----- iPad / desktop: sidebar ----- */
  const navThumb = h('span', { class: 'nv-thumb', 'aria-hidden': 'true' });
  const link = (r) => h('a', { class: 'nv', href: href(r.id), dataset: { route: r.id } }, navIcon(r),
    h('span', {}, t(android ? r.tab || RAIL_LABEL[r.id] || r.label : r.label)));
  // Android rail (AT_ boards): Help joins the lower group; the page header then has no Help button
  const lower = android ? [...admin, ROUTES.find((r) => r.id === 'help')] : admin;
  const sbn = h('nav', { class: 'sbn', 'aria-label': t('nav.main') }, navThumb, main.map(link),
    lower.length ? [h('span', { class: 'sb-sep', 'aria-hidden': 'true' }), lower.map(link)] : null);
  if (android) { dragToSelect(tabbar, 'x'); dragToSelect(sbn, 'y'); }
  const sideSpeaker = h('div', { class: 'sb-spk' });
  const uchip = h('button', {
    type: 'button', class: 'uchip', 'aria-haspopup': 'dialog', 'aria-expanded': 'false',
    'aria-label': t('acct.aria', user.display_name, roleLabel(user.role)),
    onclick: () => popover({ anchor: uchip, place: android ? 'right' : 'above', label: t('acct.my'), className: 'acct', build: (el, close) => el.append(h('div', { class: 'menu' }, accountItems(close))) }),
  }, avatar(user), h('span', { class: 'uchip-tx' }, h('span', { class: 'uchip-n' }, user.display_name), h('span', { class: 'uchip-r' }, roleLabel(user.role))), icon('chev-up', 'sm chev'));
  const sidebar = h('aside', { class: 'sb' }, sideSpeaker, sbn, h('div', { class: 'sb-foot' }, uchip));

  const content = h('main', { class: 'main', id: 'view', tabindex: '-1' });
  const nowbar = android ? buildNowBar() : null;
  const el = h('div', { class: 'shell' }, sidebar, topbar, content, nowbar && nowbar.el, tabdock);

  /* ----- account menu (desktop/iPad popover, phone Account page) ----- */
  function accountItems(close = () => {}) {
    const item = (ic, label, props, cls = '') => h(props.href ? 'a' : 'button', { class: `mi ${cls}`.trim(), type: props.href ? null : 'button', ...props },
      h('span', { class: 'mic' }, icon(ic, 'xs')), h('span', {}, label));
    // a link row: closing removes the popover (and the <a>) before the browser follows it, so navigate ourselves
    const go = (to) => (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button) return; // new tab/window: let the browser handle it
      e.preventDefault();
      close();
      location.hash = to;
    };
    const items = [
      isPhone() ? null : item('user', t('nav.prefs'), { href: href('prefs'), onclick: go(href('prefs')) }),
      item('key', t('acct.changePw'), { onclick: () => { close(); changePassword(); } }),
      item('devices', t('acct.signOutAll'), { onclick: (e) => { close(); confirmSignOutAll(e.currentTarget); } }),
      item('help', t('nav.help'), { href: href('help'), onclick: go(href('help')) }),
      item('logout', t('acct.signOut'), { onclick: (e) => busy(e.currentTarget, () => onSignOut('/auth/logout')).catch(() => {}) }, 'danger'),
    ];
    return items;
  }
  function confirmSignOutAll() {
    openSheet({
      title: t('acct.signOutAll'),
      build(body, sheet) {
        const go = h('button', { type: 'button', class: 'btn danger big wide', onclick: () => busy(go, () => onSignOut('/auth/logout-all')).then(() => sheet.close(), () => {}) }, t('acct.signOutAll'));
        body.append(h('p', { class: 'muted' }, t('acct.signOutAllText')), go,
          h('button', { type: 'button', class: 'btn big wide', onclick: () => sheet.close() }, t('common.cancel')));
      },
    });
  }
  function changePassword() {
    openSheet({
      title: t('acct.changePw'),
      build(body, sheet) {
        const cur = passwordInput({ autocomplete: 'current-password', required: true });
        const nw = passwordInput({ autocomplete: 'new-password', minLength: 8, required: true });
        const again = passwordInput({ autocomplete: 'new-password', required: true });
        const err = h('p', { class: 'form-error', role: 'alert' });
        const save = h('button', { class: 'btn primary big wide', type: 'submit' }, t('pw.save'));
        const form = h('form', {
          novalidate: true, style: { display: 'flex', flexDirection: 'column', gap: '14px' },
          onsubmit: async (e) => {
            e.preventDefault();
            const bad = !cur.input.value ? [cur.input, 'pw.errCur'] : nw.input.value.length < 8 ? [nw.input, 'pw.errLen']
              : nw.input.value !== again.input.value ? [again.input, 'pw.errMatch'] : null;
            [cur, nw, again].forEach((x) => x.input.removeAttribute('aria-invalid'));
            if (bad) { err.textContent = t(bad[1]); bad[0].setAttribute('aria-invalid', 'true'); bad[0].focus(); return; }
            err.textContent = '';
            await busy(save, async () => {
              try {
                await api('/auth/password', { body: { current: cur.input.value, new: nw.input.value }, allow401: true });
                sheet.close();
                toast(t('pw.changed'), 'ok');
              } catch (e2) {
                err.textContent = errorText(e2, user, { 401: t('pw.wrongCur') });
                if (e2.status === 401) cur.input.setAttribute('aria-invalid', 'true');
              }
            });
          },
        }, field(t('pw.current'), cur.wrap), field(t('pw.new'), nw.wrap, t('pw.rule')), field(t('pw.confirm'), again.wrap), err, save);
        body.append(form);
      },
    });
  }

  /* ----- speaker control (DEVICE.md): name only when online, "Offline" text when not, no dot.
           One speaker = plain label (no chevron, no picker). Several = button + picker. ----- */
  function speakerChip(kind) {
    const cur = speakers.find((s) => s.current) || speakers[0] || { name: '', online: false, checking: true };
    const many = speakers.length > 1;
    const state = cur.online ? null : cur.checking ? h('span', { class: 'spis' }, t('spk.connecting')) : h('span', { class: 'spoff' }, t('spk.offline'));
    // never seen a name (fresh install, speaker offline): the side block already says "Speaker", so show only the state
    const nameEls = [cur.name || kind !== 'side' ? h('span', { class: 'spnm' }, cur.name || t('spk.unknown')) : null, state];
    const props = many ? { type: 'button', 'aria-haspopup': 'dialog', 'aria-expanded': 'false' } : { role: 'group', 'aria-label': `${t('spk.label')}: ${cur.name || t('spk.unknown')}${cur.online ? '' : `, ${t(cur.checking ? 'spk.connecting' : 'spk.offline')}`}` };
    let node;
    if (kind === 'side') {
      node = h(many ? 'button' : 'div', { class: 'spside', ...props },
        h('span', { class: 'splogo', 'aria-hidden': 'true' }, icon(cur.icon || 'now')),
        h('span', { class: 'spsidetx' }, h('span', { class: 'spbrand' }, t('spk.label')), h('span', { class: 'spname' }, nameEls)),
        many ? icon('chev-down', 'sm spchev') : null);
    } else {
      node = h(many ? 'button' : 'div', { class: 'spchip', ...props }, icon(cur.icon || 'speaker', 'sm'), nameEls, many ? icon('chev-down', 'sm spchev') : null);
    }
    if (many) node.addEventListener('click', () => openPicker(node, kind === 'side' ? 'right' : 'below'));
    node.dataset.spk = kind;
    return node;
  }
  function pickerRows(close) {
    return h('div', { role: 'listbox', 'aria-label': t('spk.pick'), class: 'menu' }, speakers.map((s) => {
      const row = h('button', {
        type: 'button', class: 'spi', role: 'option', 'aria-selected': String(!!s.current), 'aria-disabled': String(!s.online && !s.selectable),
        dataset: { out: s.id || '' },
        onclick: () => {
          // offline speakers can't be picked, except to switch this browser back from "This device"
          if (!s.online && !s.selectable) { row.querySelector('.spis').textContent = t('spk.why'); return; }
          close();
          if (!s.current && onPickSpeaker) onPickSpeaker(s);
        },
      }, h('span', { class: 'spic', 'aria-hidden': 'true' }, icon(s.icon || 'speaker', 'sm')),
      h('span', { class: 'spitx' }, h('span', { class: 'spit' }, s.name || t('spk.unknown')), h('span', { class: 'spis' }, s.sub || '')),
      s.current ? icon('check', 'sm ck') : s.id === 'device' ? null // this device is always there: no Online/Offline
        : h('span', { class: 'spst', style: s.online ? null : { color: 'var(--danger)' } }, t(s.online ? 'spk.online' : 'spk.offline')));
      return row;
    }));
  }
  function openPicker(anchor, place) {
    if (isPhone()) {
      openSheet({ title: t('spk.pick'), build: (body, sheet) => body.append(pickerRows(() => sheet.close())) });
    } else {
      popover({ anchor, place, label: t('spk.pick'), build: (el, close) => el.append(h('p', { class: 'sp-h', 'aria-hidden': 'true' }, t('spk.pick')), pickerRows(close)) });
    }
  }
  function setSpeakers(list) {
    const sig = JSON.stringify(list);
    if (sig === setSpeakers.last) return;
    setSpeakers.last = sig;
    speakers = list;
    sideSpeaker.replaceChildren(speakerChip('side'));
    chips = chips.filter((c) => c.isConnected);
    chips.forEach((c) => c.replaceWith(speakerChip(c.dataset.spk)));
    chips = [...el.querySelectorAll('[data-spk="chip"]')];
  }
  const chip = () => { const c = speakerChip('chip'); chips.push(c); return c; };

  /* ----- page header helper (ctx.header) ----- */
  // sub: optional one-line context under the title (the Android big header's "Speaker is playing …" line)
  function header({ title, back, actions, sub } = {}) {
    barTitle.textContent = title || '';
    // Android phone: back is an arrow icon button at the left of the top bar, so it stays reachable after scrolling
    if (android && back && isPhone()) {
      const label = back.label || t('nav.back');
      barLeft.replaceChildren(tip(h('a', { class: 'iconbtn bar-back', href: back.href, 'aria-label': label }, icon('arrow-back')), label));
    }
    const helpBtn = h('a', { class: 'iconbtn glassy help-btn', href: href('help'), 'aria-label': t('nav.help') }, icon('help'));
    tip(helpBtn, t('nav.help'));
    return h('header', { class: 'phd' },
      h('div', { class: 'phd-l', style: { minWidth: 0 } },
        back ? h('a', { class: 'phd-back', href: back.href }, icon(android ? 'arrow-back' : 'back', 'sm'), h('span', { class: 'phd-back-tx' }, back.label || t('nav.back'))) : null,
        h('h1', { class: 'pt' }, title),
        sub ? h('p', { class: 'phd-sub' }, sub) : null),
      h('div', { class: 'phd-r' }, actions || null, chip(), helpBtn));
  }

  /* ----- Android: account avatar in the phone top bar (the boards put it top-right, level with the title) ----- */
  const meTop = () => h('a', { class: 'me-top', href: href('account'), dataset: { route: 'account' }, 'aria-label': t('acct.aria', user.display_name, roleLabel(user.role)) }, avatar(user));

  /* ----- Android Now Bar: what's playing, above the nav pill (phone) or bottom-centre (tablet), on every page but
           Now. Operators+ only (it carries play/pause); hidden while nothing plays or the speaker is unreachable.
           Tap the capsule -> Now; the button -> POST /pause or /resume. The equalizer moves only while playing. ----- */
  function buildNowBar() {
    const title = h('span', { class: 'nb-t' });
    const eq = h('span', { class: 'nb-eq', 'aria-hidden': 'true' }, h('i'), h('i'), h('i'));
    const openA = h('a', { class: 'nb-open', href: href('now'), 'aria-label': t('nb.open') }, eq, title);
    const btn = h('button', { type: 'button', class: 'nb-btn' });
    let playing = false;
    btn.addEventListener('click', () => {
      if (btn.disabled || !onCommand) return;
      const path = playing ? '/pause' : '/resume';
      paint(!playing); // answer the tap now; the next poll confirms
      busy(btn, () => onCommand(path)).catch(() => {});
    });
    const bar = h('div', { class: 'nowbar', role: 'region', 'aria-label': t('nav.now'), hidden: true }, openA, btn);
    function paint(on) {
      playing = on;
      bar.classList.toggle('paused', !on);
      const label = t(on ? 'nb.pause' : 'nb.resume');
      btn.replaceChildren(glyph(on ? 'pause' : 'play', 'sm'));
      btn.setAttribute('aria-label', label);
      tip(btn, label);
    }
    let visible = false;
    function update(status, err) {
      const m = (!err && status && status.media) || {};
      const active = ['PLAYING', 'BUFFERING', 'PAUSED'].includes(m.state);
      const announcing = active && m.title === 'Announcement';
      const q = status && status.queue;
      const cur = q && q.items && q.items[q.index];
      const show = active && can('operator') && !!current && current.id !== 'now';
      if (show) {
        title.textContent = announcing ? t('nb.announcing') : (m.title || (cur && cur.title) || t('spk.label'));
        btn.hidden = announcing;
        if (!btn.disabled) paint(m.state !== 'PAUSED');
      }
      if (show !== visible) {
        visible = show;
        bar.hidden = !show;
        document.documentElement.toggleAttribute('data-nowbar', show);
      }
    }
    return { el: bar, update };
  }
  let lastStatus = null, lastErr = null;
  function setStatus(status, err) {
    lastStatus = status; lastErr = err;
    if (nowbar) nowbar.update(status, err);
  }

  /* ----- current route marking + sliding thumbs ----- */
  let current = null;
  function markRoute(route, animate = true) {
    current = route;
    for (const a of el.querySelectorAll('[data-route]')) {
      if (a.dataset.route === (route.parent || route.id)) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    }
    barLeft.replaceChildren();
    barRight.replaceChildren();
    barTitle.textContent = '';
    if (route.chip) {
      // Android: Now shows the chip under its big title (now.css), so the bar keeps just the title. The top bar
      // only shows on phones, so no width check is needed.
      if (!android) barLeft.append(chip());
      const hb = h('a', { class: 'iconbtn glassy', href: href('help'), 'aria-label': t('nav.help') }, icon('help'));
      barRight.append(tip(hb, t('nav.help')));
    }
    if (android) {
      const me = meTop();
      if ((route.parent || route.id) === 'account') me.setAttribute('aria-current', 'page');
      barRight.append(me);
    }
    if (nowbar) nowbar.update(lastStatus, lastErr);
    placeThumbs(animate);
    closePopover();
  }
  function placeThumbs(animate) {
    if (!current) return;
    const tab = tabbar.querySelector(`[data-route="${current.id}"]`);
    tabThumb.classList.toggle('no-anim', !animate);
    tabThumb.style.opacity = tab ? '1' : '0';
    if (tab) { tabThumb.style.width = `${tab.offsetWidth}px`; tabThumb.style.setProperty('--x', `${tab.offsetLeft}px`); }
    const nv = sbn.querySelector(`[data-route="${current.id}"]`);
    navThumb.classList.toggle('no-anim', !animate);
    navThumb.style.opacity = nv ? '1' : '0';
    if (nv) { navThumb.style.height = `${nv.offsetHeight}px`; navThumb.style.setProperty('--y', `${nv.offsetTop}px`); }
  }
  const ro = new ResizeObserver(() => placeThumbs(false));
  ro.observe(tabbar);
  ro.observe(sbn);

  /* ----- scroll: phone top bar background/title, large-screen sticky header ----- */
  // Android phone (A_ boards): the big title sits right under the bar and hands over to the bar's title once it is
  // half under it; data-bar-title on <html> fades the big one out meanwhile
  const bigTitleUnder = () => {
    const pt = content.querySelector('.phd .pt');
    if (!pt) return true;
    const r = pt.getBoundingClientRect();
    return (r.top + r.bottom) / 2 < topbar.offsetHeight;
  };
  const onScroll = () => {
    const y = window.scrollY;
    document.documentElement.toggleAttribute('data-scrolled', y > 8);
    topbar.dataset.under = String(y > 4);
    const barTitleOn = !!barTitle.textContent && (android && isPhone() ? y > 8 && bigTitleUnder() : y > 44);
    topbar.dataset.title = String(barTitleOn);
    if (android) document.documentElement.toggleAttribute('data-bar-title', barTitleOn);
  };
  window.addEventListener('scroll', onScroll, { passive: true });

  return {
    el, content, markRoute, setSpeakers, setStatus, header, accountItems, changePassword, onScroll,
    destroy() {
      ro.disconnect(); window.removeEventListener('scroll', onScroll); closePopover();
      ['data-scrolled', 'data-nowbar', 'data-bar-title'].forEach((n) => document.documentElement.removeAttribute(n));
    },
  };
}
