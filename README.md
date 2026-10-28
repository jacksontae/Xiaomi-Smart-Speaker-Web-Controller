# Xiaomi-Smart-Speaker-Web-Controller
Custom web controller with support for ESP32, ESP8266, macOS, and Linux.

HTTP API และหน้าเว็บสำหรับสั่ง Google Cast speaker (เช่น Xiaomi Mi Smart Speaker) ให้ประกาศข้อความและเล่นเสียงจาก YouTube
ผ่านโปรโตคอล Cast ในวง LAN โดยไม่ต้องพึ่ง Google Assistant ลำโพงดึงไฟล์เสียงทั้งหมดจาก service นี้

> สถานะ: ตอนนี้มีตัว service บน macOS (Python) · ESP32/ESP8266 และ Linux อยู่ระหว่างพัฒนา

## ติดตั้ง (macOS)

ต้องมี Python 3.10+ และ Node.js (yt-dlp ใช้แก้ JS challenge ของ YouTube) เช่น `brew install python node`

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
curl -X POST localhost:8090/settings -H 'Content-Type: application/json' -d '{"default_volume":0.4}'
curl localhost:8090/speakers    # ค้นหาลำโพง Cast ในวง LAN
```

## API

| Method | Path | Body | หน้าที่ |
|---|---|---|---|
| GET | `/status` | – | แอป เพลง และระดับเสียงปัจจุบัน |
| POST | `/say` | `{"text": "...", "lang": "th", "volume": 0.4}` | ประกาศข้อความ (TTS) |
| POST | `/youtube` | `{"query": "คำค้น หรือ URL", "volume": 0.3}` | เล่นเสียงจาก YouTube |
| POST | `/play` | `{"url": "...", "content_type": "audio/mp3"}` | เล่นไฟล์เสียงจาก URL |
| POST | `/volume` | `{"level": 0.3}` | ปรับเสียง 0–1 |
| POST | `/pause` · `/resume` · `/stop` | – | ควบคุมการเล่น |

```bash
curl -X POST localhost:8090/say -H 'Content-Type: application/json' -d '{"text":"ค่าฝุ่นสูง กรุณาปิดหน้าต่าง"}'
curl -X POST localhost:8090/youtube -H 'Content-Type: application/json' -d '{"query":"เพลงบรรเลงเปียโน"}'
```

## หมายเหตุ

- `volume` ใน body เป็นค่าที่ไม่ต้องใส่ก็ได้
- `say` ขัดเพลง YouTube ที่ service เล่นอยู่แล้วกลับมาเล่นต่อให้เอง (ประกาศติดกันหลายครั้งก็ได้) ถ้าระหว่างนั้นสั่ง `stop`, `youtube` หรือ `play` จะไม่กลับไปเล่นเพลงเดิม
- แอปอื่นที่ลำโพงเล่นอยู่ (เช่น Spotify) จะหยุดและไม่กลับมาเล่นต่อ
- YouTube ถูกดาวน์โหลดเก็บไว้ใน `cache/` (เก็บ 20 ไฟล์ล่าสุด) เพราะ YouTube ไม่ยอมให้ proxy stream ตรง
- yt-dlp ต้องใช้ Node.js แก้ JS challenge ของ YouTube ถ้าวันไหนเล่นไม่ได้ให้อัปเดต: `./.venv/bin/pip install -U "yt-dlp[default]"`
- TTS ใช้ endpoint ของ Google Translate ซึ่งไม่มีเอกสารทางการ อาจเปลี่ยนหรือถูกจำกัดได้
