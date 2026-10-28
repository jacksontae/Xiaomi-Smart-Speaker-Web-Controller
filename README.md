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
| `speaker_ip` | `192.168.2.48` | IP ลำโพง (กด "ค้นหา" ในหน้าเว็บเพื่อเลือกจากลำโพงในวง LAN) |
| `speaker_name` | `Air Purifier speaker` | ชื่อที่แสดง |
| `port` | `8090` | พอร์ตของ service (เปลี่ยนแล้วรีสตาร์ทเอง) |
| `default_volume` | `null` | ระดับเสียงที่ตั้งก่อนประกาศหรือเล่น 0–1, `null` = ไม่เปลี่ยน |
| `tts_lang` | `th` | ภาษาเริ่มต้นของ `/say` |
| `cache_keep` | `20` | จำนวนเพลง YouTube ที่เก็บใน `cache/` |
| `resume_after_say` | `true` | ประกาศเสร็จแล้วเล่นเพลง YouTube ที่ค้างอยู่ต่อจากจุดเดิม (ย้อน 1 วินาที) |
| `public_base_url` | `null` | ใส่เมื่อ IP ของ Mac ที่ตรวจเองผิด เช่น `http://192.168.2.45:8090` |

```bash
TOKEN=$(./speakerctl token)
curl -X POST localhost:8090/settings -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"default_volume":0.4}'
curl -H "Authorization: Bearer $TOKEN" localhost:8090/speakers    # ค้นหาลำโพง Cast ในวง LAN
```

## API

ทุก endpoint ในตารางต้องส่ง header `Authorization: Bearer <token>` ถ้าไม่ส่งหรือ token ผิดจะได้ `401`

- token สร้างให้อัตโนมัติตอนเปิด service ครั้งแรก เก็บใน `config.json` (สิทธิ์ไฟล์ 600) ดูด้วย `./speakerctl token`
- `GET /settings` ไม่ส่ง token กลับไป และเปลี่ยน token ผ่าน API ไม่ได้ ใช้ `./speakerctl token --rotate`
- หน้าเว็บจะขอ token ครั้งแรก แล้วจำไว้ในเบราว์เซอร์นั้น
- ไฟล์เสียงที่ลำโพงดึง (`/tts.mp3`, `/yt/...`) ไม่ใช้ header เพราะลำโพงส่งไม่ได้ แต่ใช้ลิงก์ที่เซ็นด้วย HMAC ของ token และหมดอายุใน 6 ชั่วโมงแทน

| Method | Path | Body | หน้าที่ |
|---|---|---|---|
| GET | `/status` | – | แอป เพลง และระดับเสียงปัจจุบัน |
| POST | `/say` | `{"text": "...", "lang": "th", "volume": 0.4}` | ประกาศข้อความ (TTS) |
| POST | `/youtube` | `{"query": "คำค้น หรือ URL", "volume": 0.3}` | เล่นเสียงจาก YouTube |
| POST | `/play` | `{"url": "...", "content_type": "audio/mp3"}` | เล่นไฟล์เสียงจาก URL |
| POST | `/volume` | `{"level": 0.3}` | ปรับเสียง 0–1 |
| POST | `/pause` · `/resume` · `/stop` | – | ควบคุมการเล่น |

```bash
TOKEN=$(./speakerctl token)
curl -X POST localhost:8090/say -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"text":"ค่าฝุ่นสูง กรุณาปิดหน้าต่าง"}'
curl -X POST localhost:8090/youtube -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"query":"เพลงบรรเลงเปียโน"}'
```

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
app.py                 FastAPI service: Cast control, TTS, YouTube cache, settings
static/index.html      หน้าเว็บควบคุม
speakerctl             จัดการ LaunchAgent บน macOS
deploy/                template ของ LaunchAgent
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
