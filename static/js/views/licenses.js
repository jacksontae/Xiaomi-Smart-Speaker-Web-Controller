// Licenses (#/licenses): this app's MIT license, the notices other licenses ask for (Anuphan font, FFmpeg, the
// GPL/LGPL parts), then every open-source part grouped by where it runs: the browser, the server, the relay firmware.
// The list is static/licenses.json; each row opens to its license text (static/licenses/*.txt, fetched on first open).
import { h, icon } from '../ui.js';
import { register, t } from '../i18n.js';
import { glyph } from '../icons.js';
import { badge, caption, card, tile } from '../kit.js';
import { policyPage, fine, extLink, extMark } from '../policy-kit.js';

register({
  en: {
    'li.lead': 'Speaker Web Controller is free software. It’s built on the open-source parts below; tap one to see its license.',
    'li.app': 'This app', 'li.mit': 'MIT License', 'li.show': 'Show text',
    'li.notices': 'Notices',
    'li.font': 'Anuphan font', 'li.fontT': 'Copyright 2019 The Anuphan Project Authors. Licensed under the SIL Open Font License 1.1.',
    'li.ffmpegT': 'This software uses FFmpeg (ffmpeg.org) under the LGPL 2.1 or the GPL, depending on how it was built.',
    'li.gpl': 'GPL and LGPL parts',
    'li.gplT': 'mutagen (GPL 2+), zeroconf (LGPL 2.1+) and the Arduino cores (LGPL 2.1, relay firmware) are separate packages used without changes. Their source code is linked below.',
    'li.g.browser': 'In your browser', 'li.g.server': 'Runs on the server', 'li.g.firmware': 'Relay firmware',
    'li.browserNote': 'No other outside code runs in your browser. Google’s sign-in script loads from Google only if you use it.',
    'li.firmwareNote': 'Only used when the speaker is connected through an ESP32 or ESP8266 relay.',
    'li.meta': (l) => `License: ${l}. The text comes with the package.`,
    'li.metaFont': 'SIL Open Font License 1.1. The same text is kept next to the font files.',
    'li.metaProgram': (l) => `License: ${l}. A separate program the server runs, not part of this app; its license is on the project website.`,
    'li.metaCerts': 'Public root certificates built into the relay firmware so it can reach secure brokers. Free to share.',
    'li.public': 'Public',
    'li.web': 'Project website', 'li.loading': 'Loading…', 'li.failed': 'The text didn’t load. Open the project website instead.',
    'li.trademarks': 'YouTube, Google, Google Cast and Xiaomi are trademarks of their owners.',
  },
  th: {
    'li.lead': 'Speaker Web Controller เป็นซอฟต์แวร์เสรี สร้างจากซอฟต์แวร์โอเพนซอร์สด้านล่าง แตะรายการเพื่อดูสัญญาอนุญาต',
    'li.app': 'แอปนี้', 'li.mit': 'สัญญาอนุญาต MIT', 'li.show': 'ดูข้อความ',
    'li.notices': 'ประกาศที่ต้องแสดง',
    'li.font': 'ฟอนต์ Anuphan', 'li.fontT': 'Copyright 2019 The Anuphan Project Authors ใช้ภายใต้ SIL Open Font License 1.1',
    'li.ffmpegT': 'ซอฟต์แวร์นี้ใช้ FFmpeg (ffmpeg.org) ภายใต้ LGPL 2.1 หรือ GPL แล้วแต่วิธีที่คอมไพล์',
    'li.gpl': 'ส่วนที่ใช้ GPL และ LGPL',
    'li.gplT': 'mutagen (GPL 2+) zeroconf (LGPL 2.1+) และ Arduino core (LGPL 2.1 ในเฟิร์มแวร์รีเลย์) เป็นแพ็กเกจแยกที่ใช้โดยไม่แก้ไข ลิงก์ซอร์สโค้ดอยู่ด้านล่าง',
    'li.g.browser': 'ในเบราว์เซอร์ของคุณ', 'li.g.server': 'ทำงานบนเซิร์ฟเวอร์', 'li.g.firmware': 'เฟิร์มแวร์รีเลย์',
    'li.browserNote': 'ไม่มีโค้ดจากภายนอกอื่นทำงานในเบราว์เซอร์ สคริปต์เข้าสู่ระบบของ Google โหลดจาก Google เฉพาะเมื่อคุณใช้',
    'li.firmwareNote': 'ใช้เฉพาะเมื่อลำโพงต่อผ่านรีเลย์ ESP32 หรือ ESP8266',
    'li.meta': (l) => `สัญญาอนุญาต: ${l} ข้อความนี้มากับแพ็กเกจ`,
    'li.metaFont': 'SIL Open Font License 1.1 ข้อความเดียวกันนี้เก็บไว้คู่กับไฟล์ฟอนต์',
    'li.metaProgram': (l) => `สัญญาอนุญาต: ${l} เป็นโปรแกรมแยกที่เซิร์ฟเวอร์เรียกใช้ ไม่ใช่ส่วนหนึ่งของแอปนี้ ดูสัญญาอนุญาตได้ที่เว็บไซต์โปรเจกต์`,
    'li.metaCerts': 'ใบรับรอง Root สาธารณะที่ฝังในเฟิร์มแวร์รีเลย์ เพื่อให้ต่อโบรกเกอร์แบบปลอดภัยได้ แจกจ่ายได้อิสระ',
    'li.public': 'สาธารณะ',
    'li.web': 'เว็บไซต์โปรเจกต์', 'li.loading': 'กำลังโหลด…', 'li.failed': 'โหลดข้อความไม่ได้ เปิดเว็บไซต์โปรเจกต์แทน',
    'li.trademarks': 'YouTube, Google, Google Cast และ Xiaomi เป็นเครื่องหมายการค้าของเจ้าของแต่ละราย',
  },
});

// files next to the static folder's root, under the same versioned path as this module (see app.py StaticBuild)
const staticUrl = (path) => new URL(`../../${path}`, import.meta.url).href;
const texts = new Map(); // path -> Promise<string>, kept across renders (language changes)
const loadText = (path) => {
  if (!texts.has(path)) {
    texts.set(path, fetch(staticUrl(path)).then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text(); }));
    texts.get(path).catch(() => texts.delete(path)); // try again next time
  }
  return texts.get(path);
};
const shortLicense = (s) => s.replace(/-or-later/g, '+').replace(/ AND /g, '+').replace(/ OR /g, '/');

export async function render(ctx) {
  ctx.css('views/common.css');
  await ctx.css('views/policy.css');
  const data = await fetch(staticUrl('licenses.json'), { signal: ctx.signal }).then((r) => r.json());

  /** Fill a <pre> with a license text the first time it is shown. */
  const fill = (pre, path) => {
    if (pre.dataset.loaded) return;
    pre.dataset.loaded = '1';
    pre.textContent = t('li.loading');
    loadText(path).then((txt) => { pre.textContent = txt; }, () => { pre.textContent = t('li.failed'); delete pre.dataset.loaded; });
  };

  let seq = 0;
  const row = (p) => {
    const id = `li${++seq}`;
    const license = p.kind === 'certs' ? t('li.public') : p.license;
    const btn = h('button', { type: 'button', class: 'c-row c-link li-q', 'aria-expanded': 'false', 'aria-controls': id },
      h('span', { class: 'c-row-tx' }, h('span', { class: 'c-title' }, p.name), p.version ? h('span', { class: 'c-sub li-ver' }, p.version) : null),
      badge(shortLicense(license), p.copyleft ? 'li-copy' : 'li-perm'), icon('chev-down', 'sm li-chev'));
    const meta = p.kind === 'font' ? t('li.metaFont') : p.kind === 'program' ? t('li.metaProgram', license)
      : p.kind === 'certs' ? t('li.metaCerts') : t('li.meta', license);
    const pre = p.text ? h('pre', { class: 'li-text', tabindex: 0 }) : null;
    const panel = h('div', { class: 'li-a', id, role: 'region', 'aria-label': p.name, hidden: true },
      p.copyright ? h('p', { class: 'li-cr' }, p.copyright) : null,
      h('p', { class: 'li-meta' }, meta),
      pre,
      h('div', { class: 'li-acts' }, Object.assign(extLink(p.url, t('li.web'), ' ', extMark()), { className: 'btn tonal li-web' })));
    btn.addEventListener('click', () => {
      const open = btn.getAttribute('aria-expanded') !== 'true';
      btn.setAttribute('aria-expanded', String(open));
      panel.hidden = !open;
      if (open && pre) fill(pre, p.text);
    });
    return h('div', { class: 'li-item' }, btn, panel);
  };

  const ownText = h('pre', { class: 'li-text', tabindex: 0 });
  const own = h('details', { class: 'c-card li-own', ontoggle: (e) => { if (e.currentTarget.open) fill(ownText, data.app.text); } },
    h('summary', { class: 'c-row c-link' }, tile(glyph('file'), 'accent'),
      h('span', { class: 'c-row-tx' }, h('span', { class: 'c-title' }, data.app.name), h('span', { class: 'c-sub' }, t('li.mit'))),
      h('span', { class: 'li-show' }, t('li.show')), icon('chev-down', 'sm li-chev')),
    h('div', { class: 'li-a' }, ownText));

  const notice = (ic, title, txt) => h('div', { class: 'c-row li-n' }, tile(ic, 'lamp'),
    h('span', { class: 'c-row-tx' }, h('span', { class: 'c-title' }, title), h('span', { class: 'c-sub' }, txt)));
  const notices = card(
    notice(glyph('text'), t('li.font'), t('li.fontT')),
    notice(glyph('volume'), 'FFmpeg', t('li.ffmpegT')),
    notice(glyph('wrench'), t('li.gpl'), t('li.gplT')));

  const NOTES = { browser: 'li.browserNote', firmware: 'li.firmwareNote' };
  const groups = data.groups.map((g) => [
    caption(`${t(`li.g.${g.id}`)} · ${g.items.length}`),
    h('div', { class: 'c-card li-list', dataset: { group: g.id } }, g.items.map(row)),
    NOTES[g.id] ? fine(t(NOTES[g.id])) : null]);

  return policyPage(ctx, { title: t('nav.licenses'), back: { href: '#/about', label: t('nav.about') } },
    h('p', { class: 'pv-p li-lead' }, t('li.lead')),
    caption(t('li.app')), own,
    caption(t('li.notices')), notices,
    groups,
    fine(t('li.trademarks')));
}
