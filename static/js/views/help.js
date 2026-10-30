// Help (boards Help / T_Help / D_Help): searchable topics in groups, one accordion. Deep links open and scroll to a
// topic: #/help/passkey, #/help/talk, #/help/offline ... (ctx.params[0]; old prototype ids are accepted too).
// "Try it" goes to the page the topic is about, only when the signed-in role can open it.
import { h, icon } from '../ui.js';
import { register, t, lang } from '../i18n.js';
import { ROUTES, href } from '../routes.js';
import { isPhone } from '../sheet.js';
import { aicon } from '../a-icons.js';

register({
  en: {
    'help.sub': 'Pick what you want to do and follow the steps.',
    'help.search': 'Search help', 'help.searchPh': 'Search, e.g. announce, offline, password', 'help.clear': 'Clear search',
    'help.try': 'Try it', 'help.tryIn': (w) => `Try it in ${w}`,
    'help.noMatch': (q) => `No topics match “${q}”`, 'help.noMatchSub': 'Try a shorter word, or look through all topics.',
    'help.showAll': 'Show all topics',
    'help.found': (n) => (n === 1 ? '1 topic found' : `${n} topics found`),
    'help.g.daily': 'Everyday use', 'help.g.admin': 'For admins', 'help.g.fix': 'Troubleshooting',
    'help.tour': 'Take the quick tour',
  },
  th: {
    'help.sub': 'เลือกสิ่งที่อยากทำ แล้วทำตามขั้นตอน',
    'help.search': 'ค้นหาในคู่มือ', 'help.searchPh': 'ค้นหา เช่น ประกาศ, ออฟไลน์, รหัสผ่าน', 'help.clear': 'ล้างคำค้น',
    'help.try': 'ลองเลย', 'help.tryIn': (w) => `ลองเลย ไปที่${w}`,
    'help.noMatch': (q) => `ไม่มีหัวข้อที่ตรงกับ “${q}”`, 'help.noMatchSub': 'ลองใช้คำที่สั้นลง หรือดูทุกหัวข้อ',
    'help.showAll': 'ดูทุกหัวข้อ',
    'help.found': (n) => `พบ ${n} หัวข้อ`,
    'help.g.daily': 'ใช้งานประจำวัน', 'help.g.admin': 'สำหรับผู้ดูแล', 'help.g.fix': 'แก้ปัญหา',
    'help.tour': 'ดูทัวร์แนะนำ',
  },
});

// Topic content. `route` = where "Try it" goes (hash route id + params); `ic` = icon on iPad/desktop;
// `kw` = extra search words (both languages, so a Thai word finds the topic in English and the other way round).
const TOPICS = [
  { group: 'daily', id: 'start', ic: ['play-circle'], route: ['now'], kw: 'login sign in online offline status switch speaker เข้าระบบ ล็อกอิน ออนไลน์ ออฟไลน์ สถานะ เปลี่ยนลำโพง',
    en: { title: 'Getting started', where: 'Now playing', steps: [
      'Sign in with the username and password your admin gave you. If the owner turned them on, you can also continue with Google or a passkey.',
      'The speaker you’re controlling is named at the top. If you see just its name, it’s online and ready to use.',
      'If it says Offline after the name, the speaker isn’t getting commands. See Speaker is offline for fixes.',
      'The Now tab always shows what the speaker is playing, or that it’s quiet. The light round the top of the speaker picture moves while it’s making sound.'] },
    th: { title: 'เริ่มต้นใช้งาน', where: 'หน้าเล่นอยู่', steps: [
      'เข้าสู่ระบบด้วยชื่อผู้ใช้และรหัสผ่านที่ผู้ดูแลให้มา ถ้าเจ้าของเปิดไว้ จะใช้ Google หรือพาสคีย์ก็ได้',
      'ด้านบนมีชื่อลำโพงที่กำลังควบคุมอยู่ ถ้าเห็นแค่ชื่อ แปลว่าออนไลน์ สั่งงานได้เลย',
      'ถ้ามีคำว่า ออฟไลน์ ต่อท้ายชื่อ ลำโพงยังไม่ได้รับคำสั่ง ดูวิธีแก้ที่หัวข้อ ลำโพงออฟไลน์',
      'หน้าเล่นอยู่บอกเสมอว่าลำโพงกำลังเล่นอะไร หรือเงียบอยู่ ไฟรอบขอบบนของรูปลำโพงจะวิ่งเมื่อมีเสียงออก'] } },
  { group: 'daily', id: 'announce', alias: ['say'], ic: ['announce', 'sprite'], route: ['announce'], kw: 'announce speak text tts voice message phrase ประกาศ พูด ข้อความ เสียงอ่าน ประโยคด่วน',
    en: { title: 'Announce now', where: 'Announce', steps: [
      'Open Announce.',
      'Type a message, or tap one of your saved quick phrases to announce it straight away.',
      'Pick the language the speaker reads in, then tap Announce.',
      'If music is playing, it pauses and picks up again when the announcement ends.'] },
    th: { title: 'ประกาศทันที', where: 'หน้าประกาศ', steps: [
      'เปิดหน้าประกาศ',
      'พิมพ์ข้อความ หรือแตะประโยคด่วนที่บันทึกไว้เพื่อประกาศทันที',
      'เลือกภาษาที่ลำโพงจะอ่าน แล้วกด ประกาศ',
      'ถ้ามีเพลงเล่นอยู่ เพลงจะพักไว้ แล้วเล่นต่อเมื่อประกาศจบ'] } },
  { group: 'daily', id: 'talk', ic: ['mic'], route: ['announce', 'talk'], min: 'operator', kw: 'talk live microphone mic push to talk space key latency delay permission blocked https two-way พูดสด ไมค์ ไมโครโฟน กด Space ช้า ดีเลย์ อนุญาต ปิดกั้น คุยสองทาง',
    en: { title: 'Talk live through the speaker', where: 'Talk live', steps: [
      'On the Announce page, pick Talk live.',
      'On a phone, press and hold the mic button while you speak, and let go when you’re done. For a longer talk, slide your finger up to lock it. On a computer, click once to start and again to stop, or press Space.',
      'People near the speaker hear you about 2⁠–⁠5 seconds later.',
      'The first time, your browser asks to use the microphone. Tap Allow. If you said no, turn it back on from the aA or lock icon next to the address bar.',
      'The mic only works when the app is open at a secure https:// address. On a plain http LAN address, Talk live is blocked.',
      'The speaker can’t send sound back, so you won’t hear the people next to it.',
      'Music pauses while you talk and picks up again afterwards, the same as after an announcement.'] },
    th: { title: 'พูดสดผ่านลำโพง', where: 'หน้าพูดสด', steps: [
      'ในหน้าประกาศ เลือก พูดสด',
      'บนมือถือ กดปุ่มไมค์ค้างไว้แล้วพูด ปล่อยเมื่อพูดจบ ถ้าจะพูดยาวโดยไม่ต้องกดค้าง ให้เลื่อนนิ้วขึ้นเพื่อล็อก บนคอมพิวเตอร์ คลิกหนึ่งครั้งเพื่อเริ่ม คลิกอีกครั้งเพื่อจบ หรือกด Space',
      'คนที่อยู่ข้างลำโพงจะได้ยินช้ากว่าที่คุณพูดประมาณ 2⁠–⁠5 วินาที',
      'ครั้งแรกเบราว์เซอร์จะขอใช้ไมโครโฟน ให้กด อนุญาต ถ้าเผลอกดไม่อนุญาต เปิดได้ที่ไอคอน aA หรือรูปกุญแจข้างช่องที่อยู่เว็บ',
      'ไมค์ใช้ได้เฉพาะเมื่อเปิดแอปผ่านที่อยู่แบบ https:// ถ้าเปิดผ่านที่อยู่ในวง LAN แบบ http ปุ่มพูดสดจะใช้ไม่ได้',
      'ลำโพงส่งเสียงกลับมาไม่ได้ คุณจะไม่ได้ยินคนที่อยู่ข้างลำโพง',
      'ถ้ามีเพลงเล่นอยู่ เพลงจะพักไว้ระหว่างพูด แล้วเล่นต่อเมื่อพูดจบ เหมือนหลังประกาศ'] } },
  { group: 'daily', id: 'schedule', alias: ['sched'], ic: ['clock'], route: ['schedule'], kw: 'schedule time every day repeat alarm timer ตั้งเวลา ทุกวัน ซ้ำ ปลุก',
    en: { title: 'Scheduled announcements', where: 'Schedule', steps: [
      'On the Announce page, pick Schedule.',
      'Add a schedule: give it a name, then choose whether it announces a message or plays a playlist.',
      'Pick the time and the days it repeats, then save. You can switch a schedule off without deleting it.'] },
    th: { title: 'ตั้งเวลาประกาศ', where: 'หน้าตั้งเวลา', steps: [
      'ในหน้าประกาศ เลือก ตั้งเวลา',
      'เพิ่มรายการตั้งเวลา ตั้งชื่อ แล้วเลือกว่าจะประกาศข้อความหรือเล่นเพลย์ลิสต์',
      'เลือกเวลาและวันที่ให้ทำซ้ำ แล้วบันทึก ปิดรายการไว้ชั่วคราวได้โดยไม่ต้องลบ'] } },
  { group: 'daily', id: 'music', alias: ['youtube', 'yt'], ic: ['search'], route: ['music'], min: 'operator', kw: 'music youtube radio station podcast rss episode upload mp3 m4a file เพลง วิทยุ สถานี พอดแคสต์ อัปโหลด ไฟล์',
    en: { title: 'Play music: YouTube, radio, podcasts, your files', where: 'Music', steps: [
      'Open Music, then pick a source at the top: YouTube, Radio, Podcasts or My files.',
      'YouTube: type a song name or paste a link. Radio: search for a station and play it. Keep the ones you like as favourites.',
      'Podcasts: search for a show, then pick an episode to play. My files: upload an audio file. It’s stored on the speaker server.',
      'Anything you find can be added to a playlist.'] },
    th: { title: 'เปิดเพลง: YouTube, วิทยุ, พอดแคสต์, ไฟล์ของฉัน', where: 'หน้าเพลง', steps: [
      'เปิดหน้าเพลง แล้วเลือกแหล่งเพลงด้านบน: YouTube, วิทยุ, พอดแคสต์ หรือไฟล์ของฉัน',
      'YouTube: พิมพ์ชื่อเพลง หรือวางลิงก์ วิทยุ: ค้นหาสถานีแล้วกดเล่น สถานีที่ชอบเก็บไว้เป็นรายการโปรดได้',
      'พอดแคสต์: ค้นหารายการ แล้วเลือกตอนที่จะเล่น ไฟล์ของฉัน: อัปโหลดไฟล์เสียง ไฟล์จะเก็บไว้ที่เซิร์ฟเวอร์ลำโพง',
      'ทุกอย่างที่หาเจอเพิ่มเข้าเพลย์ลิสต์ได้'] } },
  { group: 'daily', id: 'joox', ic: ['help', 'sprite'], route: ['music'], min: 'operator', kw: 'joox apple music spotify itunes missing not here cast airplay จูกซ์ แอปเปิล ไม่มี หาไม่เจอ แคสต์',
    en: { title: 'Why isn’t Joox or Apple Music here?', where: 'Music', steps: [
      'They don’t offer a way for other apps to play to your speaker.',
      'Use their own app’s cast button instead.'] },
    th: { title: 'ทำไมไม่มี Joox หรือ Apple Music', where: 'หน้าเพลง', steps: [
      'สองบริการนี้ไม่เปิดให้แอปอื่นสั่งเล่นเพลงไปที่ลำโพงของคุณ',
      'ให้ใช้ปุ่มแคสต์ในแอปของบริการนั้นแทน'] } },
  { group: 'daily', id: 'playlists', alias: ['pl'], ic: ['playlists', 'sprite'], route: ['playlists'], kw: 'playlist list order shuffle เพลย์ลิสต์ รายการ เรียง สุ่ม',
    en: { title: 'Playlists', where: 'Playlists', steps: [
      'Open Playlists and make a new one. Pick a name that’s easy to remember, like Morning opening music.',
      'Add items: YouTube songs, radio stations, podcast episodes, your files, audio links, or announcement text between songs.',
      'Open a playlist and tap Play. The speaker plays it in order.'] },
    th: { title: 'เพลย์ลิสต์', where: 'หน้าเพลย์ลิสต์', steps: [
      'เปิดหน้าเพลย์ลิสต์แล้วสร้างใหม่ ตั้งชื่อที่จำง่าย เช่น เพลงเปิดร้านตอนเช้า',
      'เพิ่มรายการ ใส่ได้ทั้งเพลงจาก YouTube สถานีวิทยุ ตอนพอดแคสต์ ไฟล์ของฉัน ลิงก์เสียง หรือข้อความประกาศคั่นระหว่างเพลง',
      'เปิดเพลย์ลิสต์แล้วกด เล่น ลำโพงจะเล่นตามลำดับ'] } },
  { group: 'daily', id: 'queue', ic: ['queue'], route: ['now'], kw: 'queue resume pause announcement repeat shuffle คิว เล่นต่อ พัก ประกาศแทรก วน สุ่ม',
    en: { title: 'Queue and resuming after announcements', where: 'Now playing', steps: [
      'The queue is below the controls on the Now tab.',
      'Tap an item in the queue to play it now.',
      'Shuffle and repeat are next to the playlist name.',
      'When an announcement comes in, music pauses, then continues from the same spot. An admin can turn this off in Speaker settings.'] },
    th: { title: 'คิวและการเล่นต่อหลังประกาศ', where: 'หน้าเล่นอยู่', steps: [
      'คิวอยู่ใต้ปุ่มควบคุมในหน้าเล่นอยู่',
      'แตะรายการในคิวเพื่อเล่นรายการนั้นทันที',
      'ปุ่มสุ่มกับเล่นวนอยู่ข้างชื่อเพลย์ลิสต์',
      'มีประกาศแทรกเมื่อไร เพลงจะพัก แล้วเล่นต่อจากจุดเดิม ผู้ดูแลปิดได้ในตั้งค่าลำโพง'] } },
  { group: 'daily', id: 'prefs', ic: ['user', 'sprite'], route: ['prefs'], kw: 'app settings language english thai appearance dark light mode theme motion ตั้งค่าแอป ภาษา ไทย อังกฤษ ลักษณะ โหมดมืด สว่าง ธีม',
    en: { title: 'App settings: language and appearance', where: 'App settings', steps: [
      'Open Account, then App settings.',
      'Language: English or ไทย. Appearance: System, Light or Dark. You can also reduce motion. Changes show right away.',
      'These only change the app on this device for you. They don’t change the speaker.'] },
    th: { title: 'ตั้งค่าแอป: ภาษาและลักษณะ', where: 'หน้าตั้งค่าแอป', steps: [
      'เปิด บัญชี แล้วแตะ ตั้งค่าแอป',
      'ภาษา: English หรือ ไทย ลักษณะ: ตามระบบ สว่าง หรือมืด ลดการเคลื่อนไหวได้ด้วย เปลี่ยนแล้วเห็นผลทันที',
      'ค่าพวกนี้เปลี่ยนเฉพาะแอปบนเครื่องนี้ของคุณ ไม่ได้เปลี่ยนลำโพง'] } },
  { group: 'daily', id: 'google', ic: ['key', 'sprite'], route: ['account'], kw: 'google gmail sign in login account link unlink กูเกิล เข้าสู่ระบบ ล็อกอิน บัญชี ลิงก์ ยกเลิกลิงก์ client id oauth origin javascript',
    en: { title: 'Sign in with Google', where: 'Account', steps: [
      'Google sign-in only works after you link Google to your account: sign in with your password, open Account and link your Google account.',
      'From then on, tap Continue with Google on the sign-in page and pick that account.',
      'If there’s no Google button on the sign-in page, the owner hasn’t turned it on.',
      'You can unlink Google in Account, as long as you still have another way to sign in.',
      'Owner setup: in Google Cloud console create an OAuth client ID of type Web application. Add the app’s https address (for example https://speaker.example.com) under Authorized JavaScript origins and leave redirect URIs empty. Paste the Client ID in Sign-in methods and switch it on. No client secret is needed.'] },
    th: { title: 'เข้าสู่ระบบด้วย Google', where: 'หน้าบัญชี', steps: [
      'ต้องลิงก์ Google กับบัญชีก่อนถึงจะใช้ได้: เข้าสู่ระบบด้วยรหัสผ่าน เปิด บัญชี แล้วลิงก์บัญชี Google',
      'หลังจากนั้น ที่หน้าเข้าสู่ระบบ กด ดำเนินการต่อด้วย Google แล้วเลือกบัญชีนั้น',
      'ถ้าไม่เห็นปุ่ม Google ที่หน้าเข้าสู่ระบบ แปลว่าเจ้าของยังไม่ได้เปิดใช้',
      'ยกเลิกลิงก์ Google ได้ที่ บัญชี ถ้ายังมีวิธีเข้าสู่ระบบอื่นเหลืออยู่',
      'สำหรับเจ้าของ: ใน Google Cloud console สร้าง OAuth client ID แบบ Web application ใส่ที่อยู่ https ของแอป (เช่น https://speaker.example.com) ใน Authorized JavaScript origins และเว้น redirect URIs ว่างไว้ แล้ววาง Client ID ในหน้าวิธีเข้าสู่ระบบและเปิดใช้ ไม่ต้องใช้ client secret'] } },
  { group: 'daily', id: 'passkey', alias: ['pk'], ic: ['passkey', 'sprite'], route: ['account'], kw: 'passkey webauthn face id touch id windows hello fingerprint pin พาสคีย์ ลายนิ้วมือ ใบหน้า',
    en: { title: 'Sign in with a passkey', where: 'Account', steps: [
      'A passkey lets you sign in with Face ID, your fingerprint or your device PIN instead of a password.',
      'Add one in Account, under Passkeys. Then tap Sign in with a passkey on the sign-in page and confirm on your device.',
      'Passkeys only work at the app’s secure https:// address. If you don’t see the passkey button, this device or browser doesn’t support them, or the app is open on a plain http address.',
      'Rename or remove passkeys in Account. You can’t remove the last one if it’s your only way to sign in.'] },
    th: { title: 'เข้าสู่ระบบด้วยพาสคีย์', where: 'หน้าบัญชี', steps: [
      'พาสคีย์คือการเข้าสู่ระบบด้วย Face ID ลายนิ้วมือ หรือรหัส PIN ของเครื่อง ไม่ต้องจำรหัสผ่าน',
      'เพิ่มพาสคีย์ได้ที่ บัญชี ในหัวข้อ พาสคีย์ จากนั้นที่หน้าเข้าสู่ระบบ กด เข้าสู่ระบบด้วยพาสคีย์ แล้วยืนยันตัวตนบนเครื่อง',
      'พาสคีย์ใช้ได้เฉพาะเมื่อเปิดแอปผ่านที่อยู่แบบ https:// ถ้าไม่เห็นปุ่มพาสคีย์ แปลว่าเครื่องหรือเบราว์เซอร์นี้ไม่รองรับ หรือเปิดผ่านที่อยู่แบบ http',
      'เปลี่ยนชื่อหรือลบพาสคีย์ได้ที่ บัญชี ลบพาสคีย์สุดท้ายไม่ได้ถ้าไม่มีวิธีเข้าสู่ระบบอื่นเหลืออยู่'] } },
  { group: 'admin', id: 'members', alias: ['mem'], ic: ['members', 'sprite'], route: ['members'], kw: 'member user role viewer operator admin owner disable สมาชิก ผู้ใช้ สิทธิ์ ผู้ชม ผู้ควบคุม ผู้ดูแล เจ้าของ ปิดใช้งาน',
    en: { title: 'Members and roles', where: 'Members', steps: [
      'Open Members.',
      'Add a member with a name, a username and a starting password.',
      'Pick a role. Viewers can only look. Operators can announce, talk live, play music and schedule. The owner can do everything, including managing members.',
      'When someone leaves, disable their account. They can’t sign in from then on.'] },
    th: { title: 'สมาชิกและสิทธิ์', where: 'หน้าสมาชิก', steps: [
      'เปิดหน้าสมาชิก',
      'เพิ่มสมาชิก ใส่ชื่อ ชื่อผู้ใช้ และรหัสผ่านเริ่มต้น',
      'เลือกบทบาท ผู้ชมดูได้อย่างเดียว ผู้ควบคุมประกาศ พูดสด เล่นเพลง และตั้งเวลาได้ เจ้าของทำได้ทุกอย่างรวมถึงจัดการสมาชิก',
      'ถ้ามีคนลาออก ให้ปิดใช้งานบัญชีนั้น จะเข้าระบบไม่ได้ทันที'] } },
  { group: 'admin', id: 'settings', alias: ['set'], ic: ['settings', 'sprite'], route: ['settings'], kw: 'settings speaker volume language resume lan relay ตั้งค่า ลำโพง ระดับเสียง ภาษา เล่นต่อ',
    en: { title: 'Speaker settings', where: 'Speaker settings', steps: [
      'Open Speaker settings.',
      'Pick the speaker to control. It must be on the same Wi‑Fi as the machine running the service, unless you use the relay.',
      'Set the volume when playback starts and the default announcement language.',
      'Turn Resume music after announcements on or off here.',
      'App language and light or dark mode aren’t here. They’re in App settings, and each person sets their own.'] },
    th: { title: 'ตั้งค่าลำโพง', where: 'หน้าตั้งค่าลำโพง', steps: [
      'เปิดหน้าตั้งค่าลำโพง',
      'เลือกลำโพงที่จะควบคุม ลำโพงต้องอยู่ Wi‑Fi วงเดียวกับเครื่องที่รัน service ยกเว้นใช้ตัวรีเลย์',
      'ตั้งระดับเสียงตอนเริ่มเล่น และภาษาประกาศเริ่มต้น',
      'เปิดหรือปิด เล่นเพลงต่อหลังประกาศ ได้ที่นี่',
      'ภาษาของแอปกับโหมดสว่างหรือมืดไม่ได้อยู่ที่นี่ แต่อยู่ใน ตั้งค่าแอป และแต่ละคนตั้งเองได้'] } },
  { group: 'admin', id: 'signin', ic: ['lock', 'sprite'], route: ['auth'], kw: 'sign-in methods google passkey password owner require วิธีเข้าสู่ระบบ กูเกิล พาสคีย์ รหัสผ่าน เจ้าของ',
    en: { title: 'Sign-in methods (owner only)', where: 'Sign-in methods', steps: [
      'Open Account, then Sign-in methods. Only the owner can change these.',
      'Turn Google sign-in on or off. Paste the OAuth client ID (Web application) on this page first; the (i) button next to Google shows the Google Cloud steps. Each member links their own Google account.',
      'Turn passkeys on or off, and choose whether admins must use a passkey.',
      'Everyone keeps at least one way to sign in. The app won’t remove the last one.'] },
    th: { title: 'วิธีเข้าสู่ระบบ (เฉพาะเจ้าของ)', where: 'หน้าวิธีเข้าสู่ระบบ', steps: [
      'เปิด บัญชี แล้วแตะ วิธีเข้าสู่ระบบ มีแค่เจ้าของที่แก้ได้',
      'เปิดหรือปิดการเข้าสู่ระบบด้วย Google ต้องวาง OAuth client ID (แบบ Web application) ในหน้านี้ก่อน ปุ่ม (i) ข้าง Google บอกขั้นตอนใน Google Cloud และสมาชิกแต่ละคนต้องลิงก์บัญชี Google ของตัวเอง',
      'เปิดหรือปิดพาสคีย์ และเลือกว่าผู้ดูแลต้องใช้พาสคีย์หรือไม่',
      'ทุกคนต้องเหลือวิธีเข้าสู่ระบบอย่างน้อยหนึ่งวิธีเสมอ แอปจะไม่ยอมลบวิธีสุดท้าย'] } },
  { group: 'fix', id: 'offline', alias: ['fix'], ic: ['wrench'], route: ['settings'], kw: 'offline unreachable disconnected wifi plug light ออฟไลน์ ติดต่อไม่ได้ หลุด ปลั๊ก ไฟ',
    en: { title: 'Speaker is offline', where: 'Speaker settings', steps: [
      'Check that the speaker is plugged in and the light on top is on.',
      'The speaker and the machine running the service must be on the same Wi‑Fi.',
      'Ask an admin to open Speaker settings and pick the speaker again.',
      'Still not showing? Unplug the speaker, wait 10 seconds and plug it back in.'] },
    th: { title: 'ลำโพงออฟไลน์', where: 'หน้าตั้งค่าลำโพง', steps: [
      'เช็กว่าลำโพงเสียบปลั๊กอยู่ และไฟที่ขอบบนติด',
      'ลำโพงกับเครื่องที่รัน service ต้องต่อ Wi‑Fi วงเดียวกัน',
      'ให้ผู้ดูแลเปิด ตั้งค่าลำโพง แล้วเลือกลำโพงอีกครั้ง',
      'ยังไม่ขึ้น ถอดปลั๊กลำโพง รอ 10 วินาที แล้วเสียบใหม่'] } },
  { group: 'fix', id: 'nosound', ic: ['vol-x'], route: ['now'], kw: 'no sound silent quiet volume mute ไม่มีเสียง เงียบ ระดับเสียง',
    en: { title: 'No sound after a command', where: 'Now playing', steps: [
      'Check the speaker name at the top. It shouldn’t say Offline after it.',
      'Raise the volume on the Now tab. At 0% the speaker stays silent.',
      'Try a short announcement. If you hear it, the speaker is fine and the problem is that song.'] },
    th: { title: 'สั่งแล้วไม่มีเสียง', where: 'หน้าเล่นอยู่', steps: [
      'ดูชื่อลำโพงด้านบน ต้องไม่มีคำว่า ออฟไลน์ ต่อท้าย',
      'เพิ่มระดับเสียงในหน้าเล่นอยู่ ถ้าอยู่ที่ 0% ลำโพงจะเงียบ',
      'ลองประกาศข้อความสั้น ๆ ถ้าได้ยิน แปลว่าลำโพงปกติ ปัญหาอยู่ที่เพลงนั้น'] } },
  { group: 'fix', id: 'ytfail', ic: ['link'], route: ['music'], min: 'operator', kw: 'youtube link broken fails private age live ลิงก์ เล่นไม่ได้ ส่วนตัว จำกัดอายุ ไลฟ์',
    en: { title: 'A YouTube link won’t play', where: 'Music', steps: [
      'The link must be a single video, not a channel or a search page.',
      'Private videos, age-restricted videos and live streams that haven’t ended can’t be played.',
      'Try searching by song name instead of pasting the link.'] },
    th: { title: 'ลิงก์ YouTube เล่นไม่ได้', where: 'หน้าเพลง', steps: [
      'ลิงก์ต้องเป็นวิดีโอเดียว ไม่ใช่ลิงก์ช่องหรือหน้าค้นหา',
      'วิดีโอส่วนตัว จำกัดอายุ หรือไลฟ์ที่ยังไม่จบ เล่นไม่ได้',
      'ลองค้นด้วยชื่อเพลงแทนการวางลิงก์'] } },
  { group: 'fix', id: 'forgot', ic: ['key', 'sprite'], route: null, kw: 'forgot password reset ลืมรหัส รหัสผ่าน ตั้งใหม่',
    en: { title: 'Forgot password', steps: [
      'Ask the owner to set a new password for you on the Members page.',
      'Sign in with that password.',
      'Change it to your own in Account, under Change password.'] },
    th: { title: 'ลืมรหัสผ่าน', steps: [
      'บอกเจ้าของให้ตั้งรหัสผ่านใหม่ให้ในหน้าสมาชิก',
      'เข้าสู่ระบบด้วยรหัสนั้น',
      'เปลี่ยนเป็นรหัสของคุณเองที่ บัญชี ในหัวข้อ เปลี่ยนรหัสผ่าน'] } },
];
const GROUPS = ['daily', 'admin', 'fix'];

const norm = (s) => s.toLowerCase().normalize('NFC');
let query = ''; // survives language re-render

export async function render(ctx) {
  await ctx.css('views/help.css');
  const L = lang();
  const wanted = ctx.params[0] ? TOPICS.find((x) => x.id === ctx.params[0] || (x.alias || []).includes(ctx.params[0])) : null;
  const open = new Set([wanted ? wanted.id : 'start']);

  const canRoute = (tp) => {
    if (!tp.route) return false;
    const r = ROUTES.find((x) => x.id === tp.route[0]);
    // routes not in the table yet (e.g. schedule, built by another page) still link: the router is the judge
    return r ? ctx.can(r.min) : ctx.can(tp.min || 'viewer');
  };

  const input = h('input', { class: 'input hp-input', type: 'search', placeholder: t('help.searchPh'), 'aria-label': t('help.search'), value: query, autocomplete: 'off', spellcheck: false });
  const clear = h('button', { type: 'button', class: 'iconbtn hp-clear', 'aria-label': t('help.clear'), hidden: !query, onclick: () => { input.value = ''; onSearch(); input.focus(); } }, icon('close', 'sm'));
  const count = h('p', { class: 'sr-only', role: 'status', 'aria-live': 'polite' });
  const search = h('div', { class: 'hp-search', role: 'search' }, aicon('search', 'sm hp-sic'), input, clear);
  const groupsBox = h('div', { class: 'hp-groups' });

  const sub = h('p', { class: 'hp-sub' }, t('help.sub'));
  // replays the first-run quick tour on the Now page (js/tour.js); hidden while searching
  const tour = h('div', { class: 'hp-list hp-tourbox', hidden: !!query },
    h('button', { type: 'button', class: 'hp-q hp-tour', onclick: () => import('../tour.js').then((m) => m.replay({ user: ctx.user })) },
      h('span', { class: 'hp-tic', 'aria-hidden': 'true' }, aicon('play', 'sm')), h('span', { class: 'hp-qt' }, t('help.tour')), icon('chev-right', 'sm hp-chev')));
  const node = h('div', { class: 'page narrow help-page' },
    ctx.header({ title: t('nav.help'), back: isPhone() ? { href: '#/account', label: t('nav.account') } : null }),
    sub, search, count, tour, groupsBox);

  function topicEl(tp, matchAll) {
    const c = tp[L] || tp.en;
    const isOpen = matchAll || open.has(tp.id);
    const ic = tp.ic[1] === 'sprite' ? icon(tp.ic[0], 'sm') : aicon(tp.ic[0], 'sm');
    const btn = h('button', { type: 'button', class: 'hp-q', id: `hq-${tp.id}`, 'aria-expanded': String(isOpen), 'aria-controls': `hp-${tp.id}` },
      h('span', { class: 'hp-ic', 'aria-hidden': 'true' }, ic), h('span', { class: 'hp-qt' }, c.title), icon('chev-down', 'sm hp-chev'));
    const tryIt = canRoute(tp) ? h('a', { class: 'btn tonal hp-try', href: href(...tp.route), 'aria-label': t('help.tryIn', c.where) }, t('help.try'), icon('chev-right', 'xs')) : null;
    const panel = h('div', { class: 'hp-a', id: `hp-${tp.id}`, role: 'region', 'aria-labelledby': `hq-${tp.id}`, hidden: !isOpen },
      h('ol', { class: 'hp-steps' }, c.steps.map((s) => h('li', {}, s))), tryIt);
    btn.addEventListener('click', () => {
      const now = btn.getAttribute('aria-expanded') !== 'true';
      btn.setAttribute('aria-expanded', String(now));
      panel.hidden = !now;
      if (now) open.add(tp.id); else open.delete(tp.id);
      history.replaceState(null, '', now ? `#/help/${tp.id}` : '#/help');
    });
    return h('section', { class: 'hp-topic', id: `topic-${tp.id}` }, btn, panel);
  }

  function draw() {
    const q = norm(input.value.trim());
    const hits = TOPICS.filter((tp) => {
      if (!q) return true;
      const c = tp[L] || tp.en;
      return norm([c.title, ...c.steps, tp.kw, tp.en.title, tp.th.title].join(' ')).includes(q);
    });
    if (!hits.length) {
      groupsBox.replaceChildren(h('div', { class: 'hp-none' }, h('p', { class: 'hp-none-t' }, t('help.noMatch', input.value.trim())),
        h('p', { class: 'small' }, t('help.noMatchSub')),
        h('button', { type: 'button', class: 'btn tonal', onclick: () => { input.value = ''; onSearch(); input.focus(); } }, t('help.showAll'))));
      count.textContent = t('help.noMatch', input.value.trim());
      return;
    }
    count.textContent = q ? t('help.found', hits.length) : '';
    groupsBox.replaceChildren(...GROUPS.map((g) => {
      const items = hits.filter((tp) => tp.group === g);
      if (!items.length) return null;
      return h('div', { class: 'hp-group' }, h('h2', { class: 'hp-gt' }, t(`help.g.${g}`)),
        h('div', { class: 'hp-list' }, items.map((tp) => topicEl(tp, !!q && hits.length <= 3))));
    }));
  }
  function onSearch() {
    query = input.value;
    clear.hidden = !query;
    tour.hidden = !!query;
    draw();
  }
  input.addEventListener('input', onSearch);
  input.addEventListener('keydown', (e) => { if (e.key === 'Escape' && input.value) { e.preventDefault(); input.value = ''; onSearch(); } });
  draw();

  if (wanted) {
    if (query && !groupsBox.querySelector(`#topic-${wanted.id}`)) { input.value = ''; onSearch(); }
    // the router may swap pages inside a view transition (a frame or two later): wait until the page is shown
    let tries = 0;
    requestAnimationFrame(function open() {
      if (!node.isConnected) { if (++tries < 30) requestAnimationFrame(open); return; }
      const el = node.querySelector(`#topic-${wanted.id}`);
      if (!el) return;
      el.scrollIntoView({ block: 'start', behavior: ctx.motionReduced() ? 'auto' : 'smooth' });
      el.querySelector('.hp-q').focus({ preventScroll: true });
    });
  }
  return { node };
}
