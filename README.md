# Xiaomi-Smart-Speaker-Web-Controller

[![CI](https://github.com/jacksontae/Xiaomi-Smart-Speaker-Web-Controller/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/jacksontae/Xiaomi-Smart-Speaker-Web-Controller/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Custom web controller with support for ESP32, ESP8266, macOS, and Linux.

Control a Google Cast speaker such as the **Xiaomi Mi Smart Speaker** from your own code, with no Google Assistant:
text-to-speech announcements, YouTube audio, volume and playback control, through an HTTP API and a small web UI.
The service talks to the speaker over the local network with the Cast protocol, and the speaker fetches audio from the service.

> **Status:** the macOS service (Python) works today. Relay firmware for ESP32 and ESP8266 builds (see [firmware/](firmware/README.md)) but is not yet hardware-tested; Linux is in progress.
> English docs are short for now; the detailed guide below is in Thai.

HTTP API และหน้าเว็บสำหรับสั่ง Google Cast speaker (เช่น Xiaomi Mi Smart Speaker) ให้ประกาศข้อความและเล่นเสียงจาก YouTube
ผ่านโปรโตคอล Cast ในวง LAN โดยไม่ต้องพึ่ง Google Assistant ลำโพงดึงไฟล์เสียงทั้งหมดจาก service นี้

## ติดตั้ง (macOS)

ต้องมี Python 3.11+ และ Node.js (yt-dlp ใช้แก้ JS challenge ของ YouTube) เช่น `brew install python node`

```bash
git clone git@github.com:jacksontae/Xiaomi-Smart-Speaker-Web-Controller.git
cd Xiaomi-Smart-Speaker-Web-Controller
./speakerctl install     # สร้าง venv, ติดตั้ง dependency, สร้าง config.json, ตั้งให้เปิดเองตอนล็อกอิน
```

แล้วตั้ง `speaker_ip` ใน `config.json` หรือกด "ค้นหา" ในหน้าเว็บ ไม่อยากเปิดอัตโนมัติก็รันตรงได้: `./.venv/bin/python app.py`

## รัน

service เปิดเองทุกครั้งที่ล็อกอินเข้า Mac (LaunchAgent `~/Library/LaunchAgents/local.speaker-service.plist`)
ถ้า process ตายจะถูกเปิดใหม่ให้อัตโนมัติ

```bash
./speakerctl status      # สถานะ service และลำโพง
./speakerctl restart
./speakerctl stop | start
./speakerctl logs        # ดู log แบบ follow
./speakerctl config      # แก้ config.json แล้วรีสตาร์ท
./speakerctl token       # แสดง API token · --rotate เพื่อออก token ใหม่ (ของเดิมใช้ไม่ได้ทันที)
./speakerctl uninstall   # เลิกเปิดอัตโนมัติ
```

หน้าควบคุม: http://<ip เครื่องนี้>:8090/ · เอกสาร API: http://<ip>:8090/docs

## ตั้งค่า

แก้ได้ 3 ทาง: หน้าเว็บ (หัวข้อ "ตั้งค่า"), `POST /settings`, หรือแก้ `config.json` ตรงแล้ว `./speakerctl restart`

| key | ค่าเริ่มต้น | ความหมาย |
|---|---|---|
| `speaker_ip` | `192.0.2.10` | IP ลำโพง (กด "ค้นหา" ในหน้าเว็บเพื่อเลือกจากลำโพงในวง LAN) |
| `speaker_name` | `Air Purifier speaker` | ชื่อที่แสดง |
| `port` | `8090` | พอร์ตของ service (เปลี่ยนแล้วรีสตาร์ทเอง) |
| `default_volume` | `null` | ระดับเสียงที่ตั้งก่อนประกาศหรือเล่น 0–1, `null` = ไม่เปลี่ยน |
| `tts_lang` | `th` | ภาษาเริ่มต้นของ `/say` |
| `cache_keep` | `20` | จำนวนเพลง YouTube ที่เก็บใน `cache/` |
| `resume_after_say` | `true` | ประกาศเสร็จแล้วเล่นเพลง YouTube ที่ค้างอยู่ต่อจากจุดเดิม (ย้อน 1 วินาที) |
| `transport` | `cast` | `cast` = สั่งลำโพงตรงในวง LAN · `mqtt` = สั่งผ่าน ESP32 relay (ดู Remote deployment) |
| `mqtt` | ดู `config.example.json` | broker ของ relay: `host`, `port`, `tls`, `username`, `password`, `base_topic`, `client_id` |
| `public_base_url` | `null` | ใส่เมื่อ IP ของ Mac ที่ตรวจเองผิด เช่น `http://192.0.2.20:8090` · host ของ URL นี้คือ RP ID ของ passkey |
| `passkey_signin` | `true` | เปิดการล็อกอินด้วย passkey (ใช้ได้จริงเมื่อ `public_base_url` เป็น `https://` หรือ `http://localhost`) |
| `passkey_required_for_admins` | `false` | admin ที่มี passkey ต้องล็อกอินด้วย passkey เท่านั้น (เปิดได้เมื่อ admin ทุกคนมี passkey แล้ว) |

```bash
TOKEN=$(./speakerctl token)
curl -X POST localhost:8090/settings -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"default_volume":0.4}'
curl -H "Authorization: Bearer $TOKEN" localhost:8090/speakers    # ค้นหาลำโพง Cast ในวง LAN
```

## API

เรียก API ได้ 2 แบบ ถ้าไม่ได้ยืนยันตัวตนจะได้ `401` ถ้าสิทธิ์ไม่พอจะได้ `403` (body เป็น `{"detail": "..."}` เสมอ)

- **API token** ส่ง header `Authorization: Bearer <token>` ได้สิทธิ์ `admin` ใช้กับ curl, integration และ firmware relay
  - token สร้างให้อัตโนมัติตอนเปิด service ครั้งแรก เก็บใน `config.json` (สิทธิ์ไฟล์ 600) ดูด้วย `./speakerctl token`
  - `GET /settings` ไม่ส่ง token กลับไป และเปลี่ยน token ผ่าน API ไม่ได้ ใช้ `./speakerctl token --rotate`
- **บัญชีผู้ใช้ (หน้าเว็บ)** ล็อกอินแล้วได้ cookie `sid` (`HttpOnly`, `SameSite=Strict`, อายุ 30 วันนับจากใช้งานล่าสุด)
  - คำขอที่เปลี่ยนข้อมูล (POST/PUT/PATCH/DELETE) ด้วย cookie ต้องส่ง header `X-Requested-With: speaker-web` ไม่งั้นได้ `403`
  - ครั้งแรกที่ยังไม่มีผู้ใช้ หน้าเว็บจะให้ใส่ API token เพื่อสร้างบัญชี admin คนแรก (`POST /auth/setup`)
  - รหัสผ่านอย่างน้อย 8 ตัว เก็บแบบ scrypt · ล็อกอินผิด 5 ครั้งใน 5 นาที (ต่อ IP + ชื่อผู้ใช้) จะได้ `429` พร้อม `Retry-After`
- ไฟล์เสียงที่ลำโพงดึง (`/tts.mp3`, `/yt/...`) ไม่ใช้ header เพราะลำโพงส่งไม่ได้ แต่ใช้ลิงก์ที่เซ็นด้วย HMAC ของ token และหมดอายุใน 6 ชั่วโมงแทน
- ข้อมูลผู้ใช้ เพลย์ลิสต์ ข้อความด่วน และบันทึกกิจกรรม เก็บใน SQLite ที่ `data.db` (เปลี่ยนที่ได้ด้วย env `DATA_PATH`)

### สิทธิ์ (role)

| role | ทำอะไรได้ |
|---|---|
| `viewer` | ดูสถานะ คิว เพลย์ลิสต์ และข้อความด่วน |
| `operator` | viewer + ประกาศ เล่น ปรับเสียง หยุด/เล่นต่อ คุมคิว แก้เพลย์ลิสต์และข้อความด่วน |
| `admin` | operator + จัดการสมาชิก ตั้งค่า ค้นหาลำโพง ดูบันทึกกิจกรรม |

### บัญชี

| Method | Path | สิทธิ์ | Body | หน้าที่ |
|---|---|---|---|---|
| GET | `/auth/state` | ทุกคน | – | `{"needs_setup", "user", "methods": {"password", "passkey"}}` (+ `passkey_required` เมื่อ admin ต้องเพิ่ม passkey) |
| POST | `/auth/setup` | ทุกคน (ตอนยังไม่มีผู้ใช้) | `{"api_token", "username", "display_name", "password"}` | สร้าง admin คนแรกแล้วล็อกอิน (token ผิด `401`, มีผู้ใช้แล้ว `409`) |
| POST | `/auth/login` | ทุกคน | `{"username", "password"}` | ล็อกอิน ตั้ง cookie |
| POST | `/auth/logout` · `/auth/logout-all` | ล็อกอินแล้ว | – | ออกจากระบบเครื่องนี้ · ทุกเครื่อง |
| POST | `/auth/password` | ล็อกอินแล้ว | `{"current", "new"}` | เปลี่ยนรหัสผ่าน (เครื่องอื่นถูกออกจากระบบ) |
| POST | `/auth/passkey/options` | ทุกคน | – | `{"publicKey"}` สำหรับ `navigator.credentials.get()` |
| POST | `/auth/passkey/verify` | ทุกคน | `{"credential"}` | ล็อกอินด้วย passkey ตั้ง cookie (ไม่ผ่าน `401`) |
| POST | `/me/passkeys/options` | ล็อกอินแล้ว | – | `{"publicKey"}` สำหรับ `navigator.credentials.create()` |
| GET · POST | `/me/passkeys` | ล็อกอินแล้ว | `{"credential", "name"}` | ดู · เพิ่ม passkey ของตัวเอง |
| PATCH · DELETE | `/me/passkeys/{id}` | ล็อกอินแล้ว | `{"name"}` · – | เปลี่ยนชื่อ · ลบ passkey |
| GET · POST | `/users` | admin | `{"username", "display_name", "password", "role"}` | ดู · เพิ่มสมาชิก |
| PATCH · DELETE | `/users/{id}` | admin | `{"display_name", "role", "password", "disabled"}` (ใส่เฉพาะที่จะแก้) | แก้ · ลบสมาชิก |

ชื่อผู้ใช้ 3–32 ตัว `a-z 0-9 . _ -` · ลบ ปิด หรือลดสิทธิ์ตัวเองไม่ได้ และต้องเหลือ admin ที่เปิดใช้อย่างน้อย 1 คน (`409`)
ปิดบัญชีหรือเปลี่ยนรหัสผ่านจะออกจากระบบทุกเครื่องของคนนั้น

#### Passkeys

ใช้ได้เมื่อเปิดหน้าเว็บผ่าน `public_base_url` ที่เป็น `https://` (หรือ `http://localhost` ตอนพัฒนา) เพราะเบราว์เซอร์ไม่ให้ใช้ passkey
บน http หรือ IP · RP ID = host ของ `public_base_url` ถ้าเปลี่ยนโดเมน passkey เดิมจะใช้ไม่ได้
`credential` คือ `PublicKeyCredential` ที่แปลงเป็น JSON (ฟิลด์ binary เป็น base64url เหมือน `credential.toJSON()`)
challenge ใช้ได้ครั้งเดียวและหมดอายุใน 5 นาที · ตรวจ sign counter (ค่าไม่เพิ่ม = key ถูกคัดลอก ปฏิเสธ) · ผิด 5 ครั้งใน 5 นาที (ต่อ IP) ได้ `429`
ลบ passkey สุดท้ายไม่ได้ถ้าเป็นวิธีล็อกอินเดียวที่เหลือ หรือเป็น admin ขณะเปิด `passkey_required_for_admins` (`409`)
เมื่อเปิด `passkey_required_for_admins` admin ที่มี passkey ล็อกอินด้วยรหัสผ่านไม่ได้ (`403`) · admin ใหม่ที่ยังไม่มี passkey
ยังล็อกอินด้วยรหัสผ่านได้ แต่ `/auth/state` จะมี `"passkey_required": true` ให้หน้าเว็บพาไปเพิ่ม · API token ใช้ได้เสมอ (ทางกู้คืน)

### ลำโพง

| Method | Path | สิทธิ์ | Body | หน้าที่ |
|---|---|---|---|---|
| GET | `/status` | viewer | – | แอป เพลง (มี `media.thumbnail`) ระดับเสียง และคิว (`queue`) |
| POST | `/say` | operator | `{"text": "...", "lang": "th", "volume": 0.4}` | ประกาศข้อความ (TTS) |
| POST | `/youtube` | operator | `{"query": "คำค้น หรือ URL", "volume": 0.3}` | เล่นเสียงจาก YouTube (ล้างคิว) |
| GET | `/youtube/search?q=...&limit=8` | operator | – | ค้นหา YouTube (ไม่ดาวน์โหลด) |
| POST | `/play` | operator | `{"url": "...", "content_type": "audio/mp3"}` | เล่นไฟล์เสียงจาก URL (ล้างคิว) |
| POST | `/volume` | operator | `{"level": 0.3}` | ปรับเสียง 0–1 |
| POST | `/pause` · `/resume` · `/stop` | operator | – | ควบคุมการเล่น (`stop` ล้างคิวด้วย) |
| GET · POST | `/settings` | admin | `{"default_volume": 0.4}` | ดู · แก้ตั้งค่า |
| GET | `/speakers` | admin | – | ค้นหาลำโพง Cast ในวง LAN |
| GET | `/activity?limit=50&before_id=` | admin | – | บันทึกกิจกรรม ใหม่สุดก่อน (เก็บ 5000 รายการล่าสุด) |

### เพลย์ลิสต์และคิว

| Method | Path | สิทธิ์ | Body | หน้าที่ |
|---|---|---|---|---|
| GET · POST | `/playlists` | viewer · operator | `{"name"}` | รายการเพลย์ลิสต์ · สร้างใหม่ |
| GET · PATCH · DELETE | `/playlists/{id}` | viewer · operator | `{"name"}` | ดูพร้อมรายการ · เปลี่ยนชื่อ · ลบ |
| POST | `/playlists/{id}/items` | operator | `{"kind": "youtube"\|"url"\|"tts", "source", "title", "lang"}` | เพิ่มรายการ |
| DELETE | `/playlists/{id}/items/{item_id}` | operator | – | ลบรายการ |
| PUT | `/playlists/{id}/order` | operator | `{"item_ids": [...]}` | เรียงใหม่ (ต้องครบทุก id พอดี ไม่งั้น `409`) |
| POST | `/playlists/{id}/play` | operator | `{"start_index": 0, "shuffle": false, "repeat": "off"\|"all"\|"one"}` | เล่นทั้งเพลย์ลิสต์เป็นคิว |
| GET · PATCH | `/queue` | viewer · operator | `{"shuffle", "repeat"}` | ดูคิว (`null` ถ้าไม่มี) · สลับ shuffle/repeat |
| POST | `/queue/next` · `/queue/prev` · `/queue/jump` | operator | `{"index"}` (เฉพาะ jump) | ข้ามเพลง |
| POST | `/queue/clear` | operator | – | ล้างคิวและหยุดเล่น |
| GET · POST | `/phrases` | viewer · operator | `{"text", "lang"}` | ข้อความด่วน (กดแล้วหน้าเว็บเรียก `/say`) |
| DELETE | `/phrases/{id}` | operator | – | ลบข้อความด่วน |

- รายการ `youtube` ใส่ได้ทั้ง URL, video id หรือคำค้น (เอาผลแรก) · `url` ต้องเป็นลิงก์ http(s) และต้องมี `title` · `tts` ยาวไม่เกิน 1000 ตัวอักษร
- คิวเลื่อนไปเพลงถัดไปเองเมื่อเพลงจบ (ประกาศจบไม่นับ) โหลดเพลง YouTube ถัดไปไว้ล่วงหน้า รายการที่โหลดไม่ได้จะถูกข้ามและบันทึกไว้
- `say` ระหว่างเล่นคิว: ประกาศจบแล้วเล่นเพลงเดิมต่อ แล้วคิวก็เดินต่อตามปกติ
- คิวอยู่ในหน่วยความจำ รีสตาร์ท service แล้วหาย และแก้เพลย์ลิสต์ระหว่างเล่นจะไม่กระทบคิวที่เล่นอยู่

```bash
TOKEN=$(./speakerctl token)
curl -X POST localhost:8090/say -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"text":"ค่าฝุ่นสูง กรุณาปิดหน้าต่าง"}'
curl -X POST localhost:8090/youtube -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"query":"เพลงบรรเลงเปียโน"}'
curl -X POST localhost:8090/playlists/1/play -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"shuffle":true,"repeat":"all"}'
```

## Remote deployment (ESP32 relay + self-hosted MQTT + Cloudflare Tunnel)

Use this when the service runs somewhere other than the speaker's LAN (e.g. a VM without a fixed IP).
Everything runs on the VM: the service, a Mosquitto broker and `cloudflared`. Nothing is published on
the VM's own ports; the relay reaches the broker over `wss://` through the tunnel.

```
[ESP32 relay] --wss://mqtt.example.com--> [Cloudflare Tunnel] --> [mosquitto :9001 (WebSocket)]
      |                                                                   ^ :1883 (compose network)
      +--Cast--> [speaker] --HTTPS (signed media URLs)--> [tunnel] --> [speaker-service]
```

1. **Broker logins.** `cp deploy/remote/mosquitto/acl.example deploy/remote/mosquitto/acl`, then
   `sh deploy/remote/mosquitto/add-user.sh speaker-service` and `sh deploy/remote/mosquitto/add-user.sh relay-1`
   (one login per relay; the ACL limits each relay to its own base topic). Anonymous clients are refused.
2. **Tunnel.** Create a Cloudflare Tunnel with two public hostnames:
   `speaker.example.com` → `http://speaker-service:8090` (web UI and the signed media paths) and
   `mqtt.example.com` → `http://mosquitto:9001` (Cloudflare carries WebSockets; it terminates TLS).
3. **Service.** `cp deploy/remote/.env.example deploy/remote/.env`, fill it in (`PUBLIC_BASE_URL` =
   `https://speaker.example.com`, `MQTT_PASSWORD` = the `speaker-service` password), then
   `docker compose -f deploy/remote/docker-compose.yml up -d --build`.
4. **Relay.** Flash `firmware/` to an ESP32 next to the speaker (see `firmware/README.md`) and set the
   broker to `wss://mqtt.example.com` with the `relay-1` login. The firmware trusts the public root CAs
   Cloudflare uses; no CA upload is needed. ESP8266 can't do MQTT over WebSocket.

A managed broker (HiveMQ Cloud, EMQX Cloud, ...) still works: point `MQTT_HOST`/`MQTT_PORT`/`MQTT_TLS` at it
instead of the `mosquitto` service, and give the relay its host, port 8883 and TLS.

Settings can also live in `config.json` (`"transport": "mqtt"`, an `mqtt` block, `public_base_url`).
The environment variables `SPEAKER_TRANSPORT`, `PUBLIC_BASE_URL`, `MQTT_HOST`, `MQTT_PORT`, `MQTT_TLS`,
`MQTT_CA_FILE`, `MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_BASE_TOPIC` and `MQTT_CLIENT_ID` override it and
are never written back to the file. The MQTT password is never returned by `/settings` or written to the
activity log.

How it behaves:

- Commands go to `<base>/cmd`; the relay answers on `<base>/result`. The service refreshes the speaker
  state with a `status` command when it is older than `mqtt.status_refresh` seconds (only while
  something asks: the queue watcher, a resume after an announcement, or `/status`).
- The relay counts as **offline** when its last will (`<base>/online` = `false`) fires or nothing has
  arrived from it for `mqtt.offline_after` seconds (it publishes status every 30 s). Commands then
  fail fast with `503`.
- Admins see `relay` in `GET /status`: `online`, `broker_connected`, `last_seen`, `firmware_version`,
  `relay_ip`, `rssi`. While the relay is down, admins still get it in the `503` body.
- The broker connection reconnects on its own with exponential backoff (`mqtt.reconnect_min`..`reconnect_max`).
- Without `public_base_url` the service falls back to its LAN address, which a remote speaker can't reach.

## หมายเหตุ

- **service ยังเป็น HTTP ธรรมดา (ไม่มี TLS)** token จึงวิ่งแบบไม่เข้ารหัสในวง LAN ถ้าจะเรียกจากนอกบ้าน ให้ผ่าน Tailscale หรือ tunnel ที่เป็น HTTPS อย่าเปิดพอร์ต 8090 ออกอินเทอร์เน็ตตรงๆ
- ถ้าต่อลำโพงไม่ได้ (คนละวงเน็ต ลำโพงปิด หรือ IP เปลี่ยน) API จะตอบ `503` ภายในประมาณ 10 วินาที
- `volume` ใน body เป็นค่าที่ไม่ต้องใส่ก็ได้
- `say` ขัดเพลง YouTube ที่ service เล่นอยู่แล้วกลับมาเล่นต่อให้เอง (ประกาศติดกันหลายครั้งก็ได้) ถ้าระหว่างนั้นสั่ง `stop`, `youtube` หรือ `play` จะไม่กลับไปเล่นเพลงเดิม
- แอปอื่นที่ลำโพงเล่นอยู่ (เช่น Spotify) จะหยุดและไม่กลับมาเล่นต่อ
- YouTube ถูกดาวน์โหลดเก็บไว้ใน `cache/` (เก็บ 20 ไฟล์ล่าสุด) เพราะ YouTube ไม่ยอมให้ proxy stream ตรง
- yt-dlp ต้องใช้ Node.js แก้ JS challenge ของ YouTube ถ้าวันไหนเล่นไม่ได้ให้อัปเดต: `./.venv/bin/pip install -U "yt-dlp[default]"`
- TTS ใช้ endpoint ของ Google Translate ซึ่งไม่มีเอกสารทางการ อาจเปลี่ยนหรือถูกจำกัดได้

## โครงสร้างโปรเจกต์

```
app.py                 FastAPI service: TTS, YouTube cache, คิว, settings, API ทั้งหมด
transport.py           ช่องทางสั่งลำโพง: Cast ตรง (pychromecast) หรือผ่าน ESP32 relay ทาง MQTT
auth.py                รหัสผ่าน (scrypt), session token, จำกัดการล็อกอินผิด
passkeys.py            passkey (WebAuthn): RP จาก public_base_url, challenge ใช้ครั้งเดียว, ตรวจ response
store.py               SQLite: ผู้ใช้ session เพลย์ลิสต์ ข้อความด่วน บันทึกกิจกรรม
player.py              คิวเพลง (ลำดับเล่น shuffle repeat)
static/                หน้าเว็บควบคุม
speakerctl             จัดการ LaunchAgent บน macOS
deploy/                template ของ LaunchAgent · deploy/remote/ = Docker Compose สำหรับ VM (service + Mosquitto + cloudflared)
tests/                 pytest + ลำโพงจำลอง (ไม่ต้องมีลำโพงจริง)
firmware/              firmware ESP32 / ESP8266 (PlatformIO) ตัวกลางสั่งลำโพงในวง LAN
config.example.json    ตัวอย่างไฟล์ตั้งค่า (คัดลอกเป็น config.json)
```

## Contributing

ยินดีรับ issue และ pull request ครับ อ่าน [CONTRIBUTING.md](CONTRIBUTING.md) ก่อน (PR ส่งเข้า branch `dev`)
รายงานช่องโหว่ด้านความปลอดภัยตาม [SECURITY.md](SECURITY.md) · ทุกคนต้องปฏิบัติตาม [Code of Conduct](CODE_OF_CONDUCT.md)

## Disclaimer

This is an independent project. It is not affiliated with, endorsed by, or sponsored by Xiaomi, Google or YouTube;
their names are used only to describe compatibility. YouTube playback uses yt-dlp and is subject to YouTube's Terms of Service;
use it for content you are allowed to play. The TTS endpoint is an unofficial Google Translate endpoint and may change or stop working.

## License

[MIT](LICENSE) © 2026 Jackson Tae
