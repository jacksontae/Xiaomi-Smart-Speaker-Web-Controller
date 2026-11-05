// About (#/about): the app, its version and build, this server (speaker, connection, the owner's contact: signed in
// only), links to Privacy, Licenses, What's new, the security policy and issue reports, credits and the disclaimer.
// Opens from Account (phone), Account & app settings (iPad/desktop) and, signed out, from the sign-in page.
import { h, icon } from '../ui.js';
import { register, t } from '../i18n.js';
import { glyph } from '../icons.js';
import { caption, card, linkRow, tile } from '../kit.js';
import { REPO, REPO_LABEL, aboutInfo, policyPage, signInBack, extRow, kv, fine, contactEl } from '../policy-kit.js';

register({
  en: {
    'ab.desc': 'Control a Google Cast speaker from the browser: announcements, music, radio, podcasts, schedules and Talkie. No Google Assistant needed.',
    'ab.version': (v) => `Version ${v}`, 'ab.build': (b) => `build ${b}`,
    'ab.server': 'This server', 'ab.speaker': 'Speaker', 'ab.conn': 'Connection',
    'ab.cast': 'Speaker on the local network', 'ab.mqtt': 'Through the ESP32 relay',
    'ab.contact': 'Questions about this server or your data',
    'ab.selfHosted': 'This copy is run by its owner, not by the app’s authors. The authors don’t receive any data from it.',
    'ab.ownerHint': 'Only you see this: add a contact in Speaker settings so members know who to ask.',
    'ab.addContact': 'Add contact',
    'ab.more': 'More', 'ab.privacySub': 'What is stored and who can see it', 'ab.licensesSub': 'This app and the software it uses',
    'ab.new': 'What’s new', 'ab.newSub': (v) => `Changes in ${v}`,
    'ab.security': 'Security policy', 'ab.securitySub': 'Report a security problem privately',
    'ab.report': 'Report a problem', 'ab.reportSub': 'Bugs in the app. Problems with accounts or the speaker at your place go to the owner.',
    'ab.open': 'Open source', 'ab.source': 'Source code', 'ab.license': 'License',
    'ab.credits': 'Credits',
    'ab.builtWith': 'Built with FastAPI, Uvicorn, PyChromecast, yt-dlp, paho-mqtt and other open-source software.',
    'ab.thanks': 'Font: Anuphan by Cadson Demak. Audio by FFmpeg. Radio directory by Radio Browser. Podcast search by Apple Podcasts. Ad-segment data by SponsorBlock.',
    'ab.disclaimer': 'An independent project, not affiliated with, endorsed or sponsored by Xiaomi, Google or YouTube. Their names only describe compatibility. YouTube playback uses yt-dlp and is subject to YouTube’s Terms of Service; play only content you’re allowed to. Text-to-speech uses an unofficial Google Translate endpoint that may change or stop working.',
  },
  th: {
    'ab.desc': 'ควบคุมลำโพง Google Cast ผ่านเบราว์เซอร์ ทั้งประกาศ เพลง วิทยุ พอดแคสต์ ตั้งเวลา และ Talkie ไม่ต้องใช้ Google Assistant',
    'ab.version': (v) => `เวอร์ชัน ${v}`, 'ab.build': (b) => `build ${b}`,
    'ab.server': 'เซิร์ฟเวอร์นี้', 'ab.speaker': 'ลำโพง', 'ab.conn': 'การเชื่อมต่อ',
    'ab.cast': 'ลำโพงในวงแลนเดียวกัน', 'ab.mqtt': 'ผ่านตัวรีเลย์ ESP32',
    'ab.contact': 'คำถามเรื่องเซิร์ฟเวอร์นี้หรือข้อมูลของคุณ',
    'ab.selfHosted': 'แอปนี้ติดตั้งและดูแลโดยเจ้าของเซิร์ฟเวอร์นี้ ไม่ใช่ผู้เขียนซอฟต์แวร์ ผู้เขียนไม่ได้รับข้อมูลใดๆ จากเซิร์ฟเวอร์นี้',
    'ab.ownerHint': 'เห็นเฉพาะคุณ: ใส่ช่องทางติดต่อในตั้งค่าลำโพง สมาชิกจะได้รู้ว่าต้องถามใคร',
    'ab.addContact': 'ใส่ช่องทางติดต่อ',
    'ab.more': 'เพิ่มเติม', 'ab.privacySub': 'เก็บอะไรบ้าง และใครเห็นได้', 'ab.licensesSub': 'ของแอปนี้ และซอฟต์แวร์ที่ใช้',
    'ab.new': 'มีอะไรใหม่', 'ab.newSub': (v) => `การเปลี่ยนแปลงใน ${v}`,
    'ab.security': 'นโยบายความปลอดภัย', 'ab.securitySub': 'แจ้งช่องโหว่แบบไม่เปิดเผย',
    'ab.report': 'แจ้งปัญหา', 'ab.reportSub': 'ข้อผิดพลาดของแอป ส่วนปัญหาเรื่องบัญชีหรือลำโพงที่สถานที่ของคุณ ให้แจ้งเจ้าของ',
    'ab.open': 'โอเพนซอร์ส', 'ab.source': 'ซอร์สโค้ด', 'ab.license': 'สัญญาอนุญาต',
    'ab.credits': 'เครดิต',
    'ab.builtWith': 'สร้างด้วย FastAPI, Uvicorn, PyChromecast, yt-dlp, paho-mqtt และซอฟต์แวร์โอเพนซอร์สอื่นๆ',
    'ab.thanks': 'ฟอนต์ Anuphan โดย Cadson Demak เสียงโดย FFmpeg รายชื่อสถานีวิทยุจาก Radio Browser ค้นหาพอดแคสต์ด้วย Apple Podcasts ข้อมูลช่วงโฆษณาจาก SponsorBlock',
    'ab.disclaimer': 'โปรเจกต์อิสระ ไม่มีส่วนเกี่ยวข้อง ไม่ได้รับการรับรองหรือสนับสนุนจาก Xiaomi, Google หรือ YouTube ชื่อเหล่านี้ใช้เพื่อบอกว่าใช้งานร่วมกันได้เท่านั้น การเล่น YouTube ใช้ yt-dlp และอยู่ภายใต้ข้อกำหนดของ YouTube โปรดเล่นเฉพาะเนื้อหาที่คุณมีสิทธิ์ เสียงอ่านข้อความใช้บริการ Google Translate แบบไม่เป็นทางการ ซึ่งอาจเปลี่ยนแปลงหรือหยุดทำงานได้',
  },
});

export async function render(ctx) {
  ctx.css('views/common.css');
  await ctx.css('views/policy.css');
  // the page still opens (without the version) when the server can't be asked
  const info = await aboutInfo(ctx).catch((e) => { if (e.name === 'AbortError') throw e; return {}; });
  const version = info.version || '–';
  const server = info.server; // signed in only

  const hero = h('div', { class: 'ab-hero' },
    h('img', { class: 'ab-icon', src: '/static/icon-192.png', alt: '', width: 76, height: 76 }),
    h('h2', { class: 'ab-name' }, 'Speaker Web Controller'),
    h('p', { class: 'ab-desc' }, t('ab.desc')),
    h('p', { class: 'ab-ver' }, h('span', {}, t('ab.version', version)), info.build ? h('span', { class: 'ab-build' }, t('ab.build', info.build)) : null));

  let serverPart = [fine(t('ab.selfHosted'), 'pp-solo')];
  if (server) {
    const contact = server.owner_contact
      ? h('div', { class: 'c-row pp-contact' }, tile(glyph('user-plus'), 'accent'),
        h('span', { class: 'c-row-tx' }, h('span', { class: 'c-title' }, t('ab.contact')), contactEl(server.owner_contact)))
      : null;
    const hint = !server.owner_contact && ctx.can('admin')
      ? h('p', { class: 'c-note pp-owner' }, glyph('shield', 'xs'),
        h('span', {}, t('ab.ownerHint'), ' ', h('a', { href: '#/settings' }, t('ab.addContact'))))
      : null;
    serverPart = [caption(t('ab.server')),
      card(
        kv(tile(icon('speaker'), 'plain'), t('ab.speaker'), server.speaker),
        kv(tile(glyph('wifi'), 'plain'), t('ab.conn'), t(server.transport === 'mqtt' ? 'ab.mqtt' : 'ab.cast')),
        contact),
      fine(t('ab.selfHosted')), hint];
  }

  const links = card(
    linkRow({ href: '#/privacy', title: t('nav.privacy'), sub: t('ab.privacySub'), lead: tile(icon('lock'), 'accent') }),
    linkRow({ href: '#/licenses', title: t('nav.licenses'), sub: t('ab.licensesSub'), lead: tile(glyph('file'), 'accent') }),
    extRow({ href: `${REPO}/blob/main/CHANGELOG.md`, title: t('ab.new'), sub: t('ab.newSub', version), lead: tile(glyph('list'), 'plain') }),
    extRow({ href: `${REPO}/security/policy`, title: t('ab.security'), sub: t('ab.securitySub'), lead: tile(glyph('shield'), 'plain') }),
    extRow({ href: `${REPO}/issues/new/choose`, title: t('ab.report'), sub: t('ab.reportSub'), lead: tile(glyph('alert'), 'plain') }));
  const source = card(
    extRow({ href: REPO, title: t('ab.source'), sub: REPO_LABEL, lead: tile(glyph('link'), 'plain') }),
    kv(tile(glyph('file'), 'plain'), t('ab.license'), 'MIT'));
  const credits = card(h('div', { class: 'pp-text' }, h('p', {}, t('ab.builtWith')), h('p', {}, t('ab.thanks'))));

  // signed in, About is a phone page under Account (iPad/desktop reach it from Account & app settings, no back link)
  const back = ctx.user ? { href: '#/account', label: t('nav.account') } : signInBack();
  return policyPage(ctx, { title: t('nav.about'), back, phoneOnly: !!ctx.user },
    hero, serverPart,
    caption(t('ab.more')), links,
    caption(t('ab.open')), source,
    caption(t('ab.credits')), credits,
    fine(t('ab.disclaimer'), 'pp-disc'),
    fine('© 2026 Jackson Tae · MIT License', 'pp-copy'));
}
