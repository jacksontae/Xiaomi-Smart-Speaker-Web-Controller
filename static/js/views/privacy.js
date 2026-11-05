// Privacy (#/privacy): what this software stores and sends, in plain words, as it works today (keep it in step with
// the code: activity log size, Talkie retention, who can see what). A short summary, jump links, then the sections.
// The owner's contact shows only signed in (GET /about), like on the About page.
import { h, icon } from '../ui.js';
import { register, t, locale } from '../i18n.js';
import { glyph } from '../icons.js';
import { caption, card, linkRow, tile } from '../kit.js';
import { aboutInfo, policyPage, fine, contactEl } from '../policy-kit.js';

const UPDATED = '2026-11-05'; // change with the text below

register({
  en: {
    'pv.lead': 'This app runs on a server that belongs to whoever set it up (the “owner”).',
    'pv.leadMore': 'The people who wrote the software don’t run it and can’t see your data. This page says what the software stores and sends; the owner decides how it’s used.',
    'pv.updated': (d) => `Last updated ${d}`, 'pv.questions': 'Questions: ',
    'pv.short': 'In short',
    'pv.s1': 'No ads, no analytics, no tracking.',
    'pv.s2': 'Your data stays on this server. The app’s authors never get it.',
    'pv.s3': 'Announcement text goes to Google to make the voice. Searches go to YouTube and others.',
    'pv.s4': 'The owner can see everything stored here, including your playlists and files.',
    'pv.index': 'On this page',
    'pv.stored': 'What is stored', 'pv.who': 'Who can see what', 'pv.third': 'Other companies', 'pv.mic': 'Microphone',
    'pv.device': 'Cookies and storage', 'pv.yours': 'See or delete your data', 'pv.contact': 'Contact',
    'pv.account': 'Your account', 'pv.accountT': ': username, display name, role, last sign-in. Your password is kept only as a scrambled hash.',
    'pv.passkeys': 'Passkeys', 'pv.passkeysT': ': the public half only. The private key stays on your device.',
    'pv.google': 'Google sign-in', 'pv.googleT': ' (if linked): your Google account id and email.',
    'pv.sessions': 'Sessions', 'pv.sessionsT': ': one per device. They end after 30 days without use or when you sign out; ended sessions are deleted within an hour.',
    'pv.made': 'What you make', 'pv.madeT': ': playlists, uploaded audio (with file names), followed podcasts, quick phrases, schedules, radio favourites.',
    'pv.talkie': 'Talkie', 'pv.talkieT': ': Walkie talk is not kept. Voice messages are kept for 24 hours, then deleted.',
    'pv.log': 'Activity log', 'pv.logT': ': sign-ins (with the device’s network address), failed sign-ins, the start of each announcement, what was played, volume and settings changes. Entries are deleted after 90 days, and at most the newest 5,000 are kept.',
    'pv.backups': 'Backups', 'pv.backupsT': ' (if the owner turned them on): kept for about 14 days.',
    'pv.live': 'Live talk is not recorded. It’s streamed to the speaker and thrown away.',
    'pv.what': 'What', 'pv.yes': 'yes', 'pv.no': 'no', 'pv.yesNote': 'yes, see note', 'pv.you': 'You',
    'pv.r1': 'Your playlists, files and followed shows',
    'pv.r2': 'Shared playlists, files, phrases, schedules (with who made them)',
    'pv.r3': 'Talkie voice messages (24 h) and who has the app open',
    'pv.r4': 'Member list, activity log, settings',
    'pv.ownerNote': '* Owners can see your playlists and files, but not the shows you follow. The owner also runs the server itself, so in practice they can reach everything stored on it.',
    'pv.thirdLead': 'No ads, no analytics, no tracking. Fonts and icons come from this server. To do its job, the app shares these things:',
    'pv.byServer': 'Sent by this server', 'pv.byBrowser': 'Loaded by your browser',
    'pv.gt': 'The full text of every announcement, to turn it into speech',
    'pv.yt': 'What you search for and play',
    'pv.rb': 'Station searches', 'pv.ap': 'Podcast searches',
    'pv.feeds': 'Podcast websites', 'pv.feedsT': 'Checks for new episodes of followed shows',
    'pv.sb': 'A short code that doesn’t name the video, to skip ads',
    'pv.art': 'Artwork sites', 'pv.artT': 'YouTube thumbnails, radio and podcast artwork. They see your network address, not this page.',
    'pv.src': 'Radio and podcast sources', 'pv.srcT': 'The audio, when you play on “This device”',
    'pv.gsi': 'Google sign-in', 'pv.gsiT': 'Its script, only if the owner turned it on and you use it',
    'pv.tunnel': 'If the owner set up remote access through a tunnel service (for example Cloudflare), that service carries the traffic between you and this server.',
    'pv.micT': 'The app asks for the microphone only while you hold the talk button (Talkie, or Live talk for operators). Your voice goes only to this server. The camera is never used. You can turn the microphone off in your browser’s site settings at any time.',
    'pv.cookie': 'One cookie, “sid”, keeps you signed in. Page scripts can’t read it and it isn’t sent to other sites.',
    'pv.local': 'Your browser keeps your preferences on this device: language, theme, motion, volume, speaker or “This device”, Talkie sound, played Talkie messages, tips you’ve seen. They never leave the device.',
    'pv.y1': 'In Account you can change your name and password, remove passkeys, unlink Google and sign out everywhere.',
    'pv.y2': 'You can delete your own playlists, files and followed shows.',
    'pv.y3': 'You can’t delete your own account or download your data in the app yet: ask the owner. Deleting an account removes your sessions, passkeys, personal playlists and files, followed shows and voice messages. Shared items you made stay; activity entries stay until they are 90 days old or newer ones push them out; backups keep a copy for about 14 days.',
    'pv.askData': 'Questions about your data', 'pv.askOwner': 'Ask the owner of this server.',
    'pv.appProblem': 'Problems with the app itself', 'pv.appProblemSub': 'Report a problem, on the About page',
  },
  th: {
    'pv.lead': 'แอปนี้ทำงานบนเซิร์ฟเวอร์ของคนหรือทีมที่ติดตั้งมันขึ้นมา (เรียกว่า “เจ้าของ”)',
    'pv.leadMore': 'ผู้เขียนซอฟต์แวร์ไม่ได้เปิดใช้และมองไม่เห็นข้อมูลของคุณ หน้านี้อธิบายว่าซอฟต์แวร์เก็บอะไรและส่งอะไรออกไป ส่วนการนำไปใช้ เจ้าของเป็นผู้ตัดสินใจ',
    'pv.updated': (d) => `ปรับปรุงล่าสุด ${d}`, 'pv.questions': 'สอบถาม: ',
    'pv.short': 'สรุปสั้นๆ',
    'pv.s1': 'ไม่มีโฆษณา ไม่มีระบบวิเคราะห์ ไม่มีการติดตาม',
    'pv.s2': 'ข้อมูลของคุณอยู่บนเซิร์ฟเวอร์นี้ ผู้เขียนแอปไม่ได้รับ',
    'pv.s3': 'ข้อความประกาศถูกส่งไป Google เพื่อแปลงเป็นเสียง คำค้นหาส่งไป YouTube และบริการอื่น',
    'pv.s4': 'เจ้าของเห็นทุกอย่างที่เก็บไว้ที่นี่ รวมถึงเพลย์ลิสต์และไฟล์ของคุณ',
    'pv.index': 'ในหน้านี้',
    'pv.stored': 'ข้อมูลที่เก็บ', 'pv.who': 'ใครเห็นอะไร', 'pv.third': 'บริษัทอื่น', 'pv.mic': 'ไมโครโฟน',
    'pv.device': 'คุกกี้และข้อมูลในเครื่อง', 'pv.yours': 'ดูหรือลบข้อมูล', 'pv.contact': 'ติดต่อ',
    'pv.account': 'บัญชีของคุณ', 'pv.accountT': ': ชื่อผู้ใช้ ชื่อที่แสดง บทบาท เวลาเข้าสู่ระบบล่าสุด รหัสผ่านเก็บเป็นค่าแฮชที่ถอดกลับไม่ได้',
    'pv.passkeys': 'พาสคีย์', 'pv.passkeysT': ': เก็บเฉพาะส่วนสาธารณะ กุญแจส่วนตัวอยู่ในอุปกรณ์ของคุณ',
    'pv.google': 'เข้าสู่ระบบด้วย Google', 'pv.googleT': ' (ถ้าเชื่อมไว้): รหัสบัญชี Google และอีเมล',
    'pv.sessions': 'เซสชัน', 'pv.sessionsT': ': หนึ่งรายการต่ออุปกรณ์ หมดอายุเมื่อไม่ได้ใช้ 30 วัน หรือเมื่อออกจากระบบ เซสชันที่หมดอายุจะถูกลบภายในหนึ่งชั่วโมง',
    'pv.made': 'สิ่งที่คุณสร้าง', 'pv.madeT': ': เพลย์ลิสต์ ไฟล์เสียงที่อัปโหลด (รวมชื่อไฟล์) พอดแคสต์ที่ติดตาม ข้อความด่วน ตารางเวลา สถานีวิทยุโปรด',
    'pv.talkie': 'Talkie', 'pv.talkieT': ': เสียงวอล์กกี้ไม่ถูกเก็บ ข้อความเสียงเก็บ 24 ชั่วโมงแล้วลบทิ้ง',
    'pv.log': 'บันทึกกิจกรรม', 'pv.logT': ': การเข้าสู่ระบบ (พร้อมที่อยู่เครือข่ายของอุปกรณ์) การเข้าสู่ระบบที่ไม่สำเร็จ ข้อความช่วงต้นของประกาศ สิ่งที่เปิดเล่น การปรับเสียงและการตั้งค่า ลบเมื่อครบ 90 วัน และเก็บไม่เกิน 5,000 รายการล่าสุด',
    'pv.backups': 'ข้อมูลสำรอง', 'pv.backupsT': ' (ถ้าเจ้าของเปิดไว้): เก็บประมาณ 14 วัน',
    'pv.live': 'การพูดสดไม่ถูกอัดเก็บ เสียงถูกส่งไปเล่นแล้วทิ้งไป',
    'pv.what': 'ข้อมูล', 'pv.yes': 'เห็น', 'pv.no': 'ไม่เห็น', 'pv.yesNote': 'เห็น ดูหมายเหตุ', 'pv.you': 'คุณ',
    'pv.r1': 'เพลย์ลิสต์ ไฟล์ และพอดแคสต์ที่ติดตามของคุณ',
    'pv.r2': 'เพลย์ลิสต์ ไฟล์ ข้อความด่วน ตารางเวลาที่แชร์ (พร้อมชื่อคนสร้าง)',
    'pv.r3': 'ข้อความเสียง Talkie (24 ชม.) และใครเปิดแอปอยู่',
    'pv.r4': 'รายชื่อสมาชิก บันทึกกิจกรรม การตั้งค่า',
    'pv.ownerNote': '* เจ้าของเห็นเพลย์ลิสต์และไฟล์ของคุณ แต่ไม่เห็นพอดแคสต์ที่คุณติดตาม และเจ้าของดูแลตัวเซิร์ฟเวอร์เอง จึงเข้าถึงทุกอย่างที่เก็บไว้บนนั้นได้',
    'pv.thirdLead': 'ไม่มีโฆษณา ไม่มีระบบวิเคราะห์ ไม่มีการติดตาม ฟอนต์และไอคอนโหลดจากเซิร์ฟเวอร์นี้ แอปต้องส่งข้อมูลเหล่านี้เพื่อให้ทำงานได้:',
    'pv.byServer': 'เซิร์ฟเวอร์ส่งไปที่', 'pv.byBrowser': 'เบราว์เซอร์ของคุณโหลดจาก',
    'pv.gt': 'ข้อความประกาศทั้งหมด เพื่อแปลงเป็นเสียงพูด',
    'pv.yt': 'สิ่งที่คุณค้นหาและเปิดเล่น',
    'pv.rb': 'คำค้นหาสถานีวิทยุ', 'pv.ap': 'คำค้นหาพอดแคสต์',
    'pv.feeds': 'เว็บไซต์พอดแคสต์', 'pv.feedsT': 'การตรวจหาตอนใหม่ของรายการที่ติดตาม',
    'pv.sb': 'รหัสสั้นๆ ที่ไม่ระบุว่าเป็นวิดีโอไหน เพื่อข้ามโฆษณา',
    'pv.art': 'เว็บภาพปก', 'pv.artT': 'ภาพปก YouTube ภาพสถานีและพอดแคสต์ เว็บนั้นเห็นที่อยู่เครือข่ายของคุณ แต่ไม่เห็นหน้านี้',
    'pv.src': 'ต้นทางวิทยุและพอดแคสต์', 'pv.srcT': 'ตัวเสียง เมื่อคุณเล่นบน “อุปกรณ์นี้”',
    'pv.gsi': 'เข้าสู่ระบบด้วย Google', 'pv.gsiT': 'สคริปต์ของ Google เฉพาะเมื่อเจ้าของเปิดใช้และคุณกดใช้',
    'pv.tunnel': 'ถ้าเจ้าของตั้งการเข้าถึงจากภายนอกผ่านบริการทันเนล (เช่น Cloudflare) บริการนั้นเป็นทางผ่านข้อมูลระหว่างคุณกับเซิร์ฟเวอร์นี้',
    'pv.micT': 'แอปขอใช้ไมโครโฟนเฉพาะตอนที่คุณกดปุ่มพูดค้างไว้ (Talkie หรือพูดสดสำหรับผู้ควบคุม) เสียงของคุณส่งไปที่เซิร์ฟเวอร์นี้เท่านั้น แอปไม่ใช้กล้องเลย ปิดสิทธิ์ไมโครโฟนได้ทุกเมื่อในการตั้งค่าเว็บไซต์ของเบราว์เซอร์',
    'pv.cookie': 'มีคุกกี้เดียวชื่อ “sid” ใช้คงสถานะการเข้าสู่ระบบ สคริปต์ในหน้าอ่านไม่ได้ และไม่ถูกส่งไปเว็บอื่น',
    'pv.local': 'เบราว์เซอร์เก็บค่าที่คุณเลือกบนเครื่องนี้ เช่น ภาษา ธีม การเคลื่อนไหว ระดับเสียง ลำโพงหรือ “อุปกรณ์นี้” เสียง Talkie ข้อความที่ฟังแล้ว และคำแนะนำที่เคยดู ข้อมูลนี้ไม่ออกจากเครื่อง',
    'pv.y1': 'ในหน้าบัญชี เปลี่ยนชื่อและรหัสผ่าน ลบพาสคีย์ ยกเลิกการเชื่อม Google และออกจากระบบทุกอุปกรณ์ได้',
    'pv.y2': 'ลบเพลย์ลิสต์ ไฟล์ และพอดแคสต์ที่ติดตามของตัวเองได้',
    'pv.y3': 'ตอนนี้ยังลบบัญชีหรือดาวน์โหลดข้อมูลของตัวเองในแอปไม่ได้ ให้ติดต่อเจ้าของ การลบบัญชีจะลบเซสชัน พาสคีย์ เพลย์ลิสต์และไฟล์ส่วนตัว พอดแคสต์ที่ติดตาม และข้อความเสียงของคุณ ของที่แชร์ไว้จะยังอยู่ บันทึกกิจกรรมจะอยู่จนครบ 90 วันหรือจนกว่ารายการใหม่จะดันออกไป และข้อมูลสำรองเก็บสำเนาไว้ประมาณ 14 วัน',
    'pv.askData': 'คำถามเรื่องข้อมูลของคุณ', 'pv.askOwner': 'ติดต่อเจ้าของเซิร์ฟเวอร์นี้',
    'pv.appProblem': 'ปัญหาของตัวแอป', 'pv.appProblemSub': 'แจ้งปัญหา ในหน้าเกี่ยวกับแอป',
  },
});

const SECTIONS = ['stored', 'who', 'third', 'mic', 'device', 'yours', 'contact'];

export async function render(ctx) {
  ctx.css('views/common.css');
  await ctx.css('views/policy.css');
  const info = ctx.user ? await aboutInfo(ctx).catch((e) => { if (e.name === 'AbortError') throw e; return {}; }) : {};
  const contact = (info.server && info.server.owner_contact) || '';
  const updated = t('pv.updated', new Date(`${UPDATED}T12:00:00`).toLocaleDateString(locale(), { day: 'numeric', month: 'short', year: 'numeric' }));

  const b = (s) => h('strong', {}, s);
  const ul = (items) => h('ul', { class: 'pv-ul' }, items.map((x) => h('li', {}, x)));
  const text = (...kids) => card(h('div', { class: 'pp-text' }, kids));
  const sec = (id, ...kids) => h('section', { class: 'pv-sec', id: `pv-${id}`, 'aria-labelledby': `pvh-${id}` },
    h('h2', { class: 'pv-h', id: `pvh-${id}`, tabindex: -1 }, t(`pv.${id}`)), kids);

  const lead = h('div', { class: 'pv-lead' }, h('p', {}, b(t('pv.lead')), ' ', t('pv.leadMore')));
  const meta = h('p', { class: 'pv-meta' }, updated, contact ? [' · ', t('pv.questions'), contactEl(contact, '')] : null);
  const shortItem = (ic, txt, warn) => h('li', { class: warn ? 'warn' : null }, h('span', { class: 'pv-sic' }, ic), h('span', {}, txt));
  const short = card(h('div', { class: 'pv-short' }, h('p', { class: 'pv-short-t' }, t('pv.short')), h('ul', {},
    shortItem(icon('check', 'xs'), t('pv.s1')), shortItem(icon('check', 'xs'), t('pv.s2')),
    shortItem(glyph('alert', 'xs'), t('pv.s3'), true), shortItem(glyph('alert', 'xs'), t('pv.s4'), true))));
  // jump links scroll in place: a #pv-... hash would be read as a route by the router
  const jump = (e, id) => {
    e.preventDefault();
    const target = node.querySelector(`#pvh-${id}`);
    target.scrollIntoView({ behavior: ctx.motionReduced() ? 'auto' : 'smooth', block: 'start' });
    target.focus({ preventScroll: true });
  };
  const index = h('nav', { class: 'pv-index', 'aria-label': t('pv.index') }, h('p', { class: 'pv-index-t', 'aria-hidden': 'true' }, t('pv.index')),
    h('div', { class: 'pv-chips' }, SECTIONS.map((id) => h('a', { class: 'pv-chip', href: `#pv-${id}`, onclick: (e) => jump(e, id) }, t(`pv.${id}`)))));

  const stored = sec('stored', text(ul([
    [b(t('pv.account')), t('pv.accountT')], [b(t('pv.passkeys')), t('pv.passkeysT')], [b(t('pv.google')), t('pv.googleT')],
    [b(t('pv.sessions')), t('pv.sessionsT')], [b(t('pv.made')), t('pv.madeT')], [b(t('pv.talkie')), t('pv.talkieT')],
    [b(t('pv.log')), t('pv.logT')], [b(t('pv.backups')), t('pv.backupsT')],
  ]), h('p', { class: 'pv-callout' }, icon('check', 'xs'), h('span', {}, t('pv.live')))));

  const Y = () => h('span', { class: 'pv-y', role: 'img', 'aria-label': t('pv.yes') }, icon('check', 'xs'));
  const N = () => h('span', { class: 'pv-n', role: 'img', 'aria-label': t('pv.no') }, '–');
  const You = () => h('span', { class: 'pv-you' }, t('pv.you'));
  const ownMark = () => h('span', { class: 'pv-y pv-warn', role: 'img', 'aria-label': t('pv.yesNote') }, icon('check', 'xs'), h('sup', { 'aria-hidden': 'true' }, '*'));
  const tr = (what, a, o, w) => h('tr', {}, h('th', { scope: 'row' }, what), h('td', {}, a), h('td', {}, o), h('td', {}, w));
  const table = h('table', { class: 'pv-table' },
    h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, h('span', { class: 'sr-only' }, t('pv.what'))),
      ['viewer', 'operator', 'admin'].map((r) => h('th', { scope: 'col' }, t(`role.${r}`))))),
    h('tbody', {},
      tr(t('pv.r1'), You(), You(), ownMark()),
      tr(t('pv.r2'), Y(), Y(), Y()),
      tr(t('pv.r3'), Y(), Y(), Y()),
      tr(t('pv.r4'), N(), N(), Y())));
  const who = sec('who', card(table), fine(t('pv.ownerNote')));

  const svc = (ic, name, gets) => h('div', { class: 'c-row pv-svc' }, tile(ic, 'plain'),
    h('span', { class: 'c-row-tx' }, h('span', { class: 'c-title' }, name), h('span', { class: 'c-sub' }, gets)));
  const third = sec('third',
    h('p', { class: 'pv-p' }, t('pv.thirdLead')),
    caption(t('pv.byServer')),
    card(
      svc(glyph('text'), 'Google Translate', t('pv.gt')),
      svc(glyph('yt'), 'YouTube', t('pv.yt')),
      svc(glyph('radio'), 'Radio Browser', t('pv.rb')),
      svc(glyph('podcast'), 'Apple Podcasts', t('pv.ap')),
      svc(glyph('podcast'), t('pv.feeds'), t('pv.feedsT')),
      svc(glyph('next'), 'SponsorBlock', t('pv.sb'))),
    caption(t('pv.byBrowser')),
    card(
      svc(glyph('note'), t('pv.art'), t('pv.artT')),
      svc(glyph('radio'), t('pv.src'), t('pv.srcT')),
      svc(icon('key'), t('pv.gsi'), t('pv.gsiT'))),
    fine(t('pv.tunnel')));

  const mic = sec('mic', text(h('p', {}, t('pv.micT'))));
  const device = sec('device', text(ul([t('pv.cookie'), t('pv.local')])));
  const yours = sec('yours', text(ul([t('pv.y1'), t('pv.y2'), t('pv.y3')])));
  const contactSec = sec('contact', card(
    h('div', { class: 'c-row pp-contact' }, tile(glyph('user-plus'), 'accent'), h('span', { class: 'c-row-tx' },
      h('span', { class: 'c-title' }, t('pv.askData')), contact ? contactEl(contact) : h('span', { class: 'c-sub' }, t('pv.askOwner')))),
    linkRow({ href: '#/about', title: t('pv.appProblem'), sub: t('pv.appProblemSub'), lead: tile(glyph('alert'), 'plain') })),
  fine(updated));

  const node = policyPage(ctx, { title: t('nav.privacy'), back: { href: '#/about', label: t('nav.about') } },
    lead, meta, short, index, stored, who, third, mic, device, yours, contactSec);
  return node;
}
