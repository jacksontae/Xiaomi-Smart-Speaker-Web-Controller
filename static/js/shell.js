// App chrome around the views: phone top bar + tab bar, iPad/desktop sidebar, speaker control, account menu,
// change-password sheet, page header helper. Built once per sign-in / language change by app.js.
import { h, icon, avatar, field, passwordInput, busy, tip, toast } from './ui.js';
import { t, roleLabel } from './i18n.js';
import { ROUTES, RANK, href } from './routes.js';
import { openSheet, popover, isPhone, closePopover } from './sheet.js';
import { errorText } from './api.js';

/**
 * buildShell({ user, api, onSignOut, onPickSpeaker }) -> shell
 * shell.el, shell.content (the <main>), shell.markRoute(route), shell.setSpeakers(list), shell.header(opts),
 * shell.accountItems(close) (menu rows reused by the phone Account page), shell.destroy()
 */
export function buildShell({ user, api, onSignOut, onPickSpeaker }) {
  const can = (role) => RANK[user.role] >= RANK[role];
  const routes = ROUTES.filter((r) => can(r.min));
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
  const tabbar = h('div', { class: 'tabbar glass' }, tabThumb,
    main.map((r) => h('a', { class: 'tab', href: href(r.id), dataset: { route: r.id } }, icon(r.icon), h('span', {}, t(r.tab)))));
  const meBtn = h('a', { class: 'me-btn glass', href: href('account'), dataset: { route: 'account' }, 'aria-label': t('acct.aria', user.display_name, roleLabel(user.role)) }, avatar(user));
  const tabdock = h('nav', { class: 'tabdock', 'aria-label': t('nav.main') }, tabbar, meBtn);

  /* ----- iPad / desktop: sidebar ----- */
  const navThumb = h('span', { class: 'nv-thumb', 'aria-hidden': 'true' });
  const link = (r) => h('a', { class: 'nv', href: href(r.id), dataset: { route: r.id } }, icon(r.icon), h('span', {}, t(r.label)));
  const sbn = h('nav', { class: 'sbn', 'aria-label': t('nav.main') }, navThumb, main.map(link),
    admin.length ? [h('span', { class: 'sb-sep', 'aria-hidden': 'true' }), admin.map(link)] : null);
  const sideSpeaker = h('div', { class: 'sb-spk' });
  const uchip = h('button', {
    type: 'button', class: 'uchip', 'aria-haspopup': 'dialog', 'aria-expanded': 'false',
    'aria-label': t('acct.aria', user.display_name, roleLabel(user.role)),
    onclick: () => popover({ anchor: uchip, place: 'above', label: t('acct.my'), className: 'acct', build: (el, close) => el.append(h('div', { class: 'menu' }, accountItems(close))) }),
  }, avatar(user), h('span', { class: 'uchip-tx' }, h('span', { class: 'uchip-n' }, user.display_name), h('span', { class: 'uchip-r' }, roleLabel(user.role))), icon('chev-up', 'sm chev'));
  const sidebar = h('aside', { class: 'sb' }, sideSpeaker, sbn, h('div', { class: 'sb-foot' }, uchip));

  const content = h('main', { class: 'main', id: 'view', tabindex: '-1' });
  const el = h('div', { class: 'shell' }, sidebar, topbar, content, tabdock);

  /* ----- account menu (desktop/iPad popover, phone Account page) ----- */
  function accountItems(close = () => {}) {
    const item = (ic, label, props, cls = '') => h(props.href ? 'a' : 'button', { class: `mi ${cls}`.trim(), type: props.href ? null : 'button', ...props },
      h('span', { class: 'mic' }, icon(ic, 'xs')), h('span', {}, label));
    const items = [
      isPhone() ? null : item('user', t('nav.prefs'), { href: href('prefs'), onclick: () => close() }),
      item('key', t('acct.changePw'), { onclick: () => { close(); changePassword(); } }),
      item('devices', t('acct.signOutAll'), { onclick: (e) => { close(); confirmSignOutAll(e.currentTarget); } }),
      item('help', t('nav.help'), { href: href('help'), onclick: () => close() }),
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
        h('span', { class: 'splogo', 'aria-hidden': 'true' }, icon('now')),
        h('span', { class: 'spsidetx' }, h('span', { class: 'spbrand' }, t('spk.label')), h('span', { class: 'spname' }, nameEls)),
        many ? icon('chev-down', 'sm spchev') : null);
    } else {
      node = h(many ? 'button' : 'div', { class: 'spchip', ...props }, icon('speaker', 'sm'), nameEls, many ? icon('chev-down', 'sm spchev') : null);
    }
    if (many) node.addEventListener('click', () => openPicker(node, kind === 'side' ? 'right' : 'below'));
    node.dataset.spk = kind;
    return node;
  }
  function pickerRows(close) {
    return h('div', { role: 'listbox', 'aria-label': t('spk.pick'), class: 'menu' }, speakers.map((s) => {
      const row = h('button', {
        type: 'button', class: 'spi', role: 'option', 'aria-selected': String(!!s.current), 'aria-disabled': String(!s.online),
        onclick: () => {
          if (!s.online) { row.querySelector('.spis').textContent = t('spk.why'); return; }
          close();
          if (!s.current && onPickSpeaker) onPickSpeaker(s);
        },
      }, h('span', { class: 'spic', 'aria-hidden': 'true' }, icon('speaker', 'sm')),
      h('span', { class: 'spitx' }, h('span', { class: 'spit' }, s.name), h('span', { class: 'spis' }, s.sub || '')),
      s.current ? icon('check', 'sm ck') : h('span', { class: 'spst', style: s.online ? null : { color: 'var(--danger)' } }, t(s.online ? 'spk.online' : 'spk.offline')));
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
  function header({ title, back, actions } = {}) {
    barTitle.textContent = title || '';
    const helpBtn = h('a', { class: 'iconbtn glassy help-btn', href: href('help'), 'aria-label': t('nav.help') }, icon('help'));
    tip(helpBtn, t('nav.help'));
    return h('header', { class: 'phd' },
      h('div', { style: { minWidth: 0 } },
        back ? h('a', { class: 'phd-back', href: back.href }, icon('back', 'sm'), back.label || t('nav.back')) : null,
        h('h1', { class: 'pt' }, title)),
      h('div', { class: 'phd-r' }, actions || null, chip(), helpBtn));
  }

  /* ----- current route marking + sliding thumbs ----- */
  let current = null;
  function markRoute(route, animate = true) {
    current = route;
    for (const a of el.querySelectorAll('[data-route]')) {
      if (a.dataset.route === route.id) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    }
    barLeft.replaceChildren();
    barRight.replaceChildren();
    barTitle.textContent = '';
    if (route.chip) {
      barLeft.append(chip());
      const hb = h('a', { class: 'iconbtn glassy', href: href('help'), 'aria-label': t('nav.help') }, icon('help'));
      barRight.append(tip(hb, t('nav.help')));
    }
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
  const onScroll = () => {
    const y = window.scrollY;
    document.documentElement.toggleAttribute('data-scrolled', y > 8);
    topbar.dataset.under = String(y > 4);
    topbar.dataset.title = String(y > 44 && !!barTitle.textContent);
  };
  window.addEventListener('scroll', onScroll, { passive: true });

  return {
    el, content, markRoute, setSpeakers, header, accountItems, changePassword, onScroll,
    destroy() { ro.disconnect(); window.removeEventListener('scroll', onScroll); closePopover(); document.documentElement.removeAttribute('data-scrolled'); },
  };
}
