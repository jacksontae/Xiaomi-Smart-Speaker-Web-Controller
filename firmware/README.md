# Speaker Relay firmware (ESP32 / ESP8266)

Turns an ESP32 or ESP8266 into the LAN-side helper for the speaker service: it receives commands over
HTTP or MQTT and drives a Google Cast speaker (e.g. Xiaomi Mi Smart Speaker) with the Cast v2
protocol. The board never handles audio; it tells the speaker which URL to play, and the speaker
fetches it (from the speaker service or the cloud).

```
[server / cloud] --MQTT or HTTP--> [ESP32 relay] --Cast (TLS :8009)--> [speaker] --HTTP--> audio URL
```

> **Status:** builds for `esp32dev`, `esp32-s3` and `esp8266` (D1 mini / NodeMCU); the Cast codec has
> host unit tests. Tested on an ESP32-D0WDQ6 (`esp32dev`) with a Xiaomi Mi Smart Speaker over MQTT:
> status, volume, play, pause/resume/stop, and the speaker service's announcements, YouTube and
> resume-after-announcement, over plain MQTT and over MQTT on WebSocket (Mosquitto `ws://`). ESP32-S3 and ESP8266 are not yet tested on hardware.

## Build and flash

Needs [PlatformIO](https://platformio.org/install/cli).

```bash
cd firmware
pio run -e esp32dev -t upload     # or -e esp32-s3, -e esp8266
pio device monitor                # 115200 baud
pio test -e native                # codec tests on your computer
```

## ESP32 or ESP8266?

| | ESP32 / ESP32-S3 | ESP8266 |
|---|---|---|
| Recommended | Yes | For boards you already have |
| Free heap | ~250 KB | ~46 KB at boot |
| MQTT over TLS (cloud broker) | Yes, with CA verification | **No**: RAM fits only the speaker's TLS session. Use plain MQTT on a trusted LAN or VPN |
| MQTT over WebSocket (`wss://`, e.g. through a Cloudflare Tunnel) | Yes; trusts the built-in public root CAs | No |
| Pick speaker by `speaker_name` | From mDNS TXT records | Asks each speaker over HTTP :8008 (slower) |

On ESP8266 the speaker connection needs a 16 KB TLS buffer unless the speaker accepts smaller
TLS records (probed on each connect). If you see out-of-memory resets, use an ESP32.

## First-time setup

1. Power the board. With no Wi-Fi saved it opens an access point **SpeakerRelay-XXXX**.
2. Join it and open `http://192.168.4.1/`.
3. Enter the 2.4 GHz Wi-Fi name and password (same network as the speaker), optional MQTT broker
   (a host name, or a `wss://host/path` URL for MQTT over WebSocket; the port and TLS fields are then ignored),
   and **copy the API token shown on the page**.
4. Save. The board restarts, joins Wi-Fi, and prints its address on the serial monitor
   (also reachable as `http://<device-name>.local/`).

Hold the **BOOT** button for 3 s while powering on to wipe settings and return to setup.
Once configured, the board never reopens the setup access point on its own: if Wi-Fi is down it keeps
retrying the saved network. To change networks or fix a wrong password, use `POST /api/config` or hold BOOT.

## Commands

The same JSON works over HTTP and MQTT. HTTP bodies must be sent with `Content-Type: application/json`.

| HTTP (Bearer token) | MQTT payload on `<base>/cmd` | Effect |
|---|---|---|
| `GET /api/status` | `{"cmd":"status"}` | Speaker app, volume, media state and position |
| `POST /api/play` `{"url":"…","content_type":"audio/mpeg","title":"…","volume":0.4,"position":12.5}` | `{"cmd":"play",…}` | Launch the Default Media Receiver and play the URL |
| `POST /api/volume` `{"level":0.3}` | `{"cmd":"volume","level":0.3}` | Set volume 0–1 |
| `POST /api/pause` · `/api/resume` · `/api/stop` | `{"cmd":"pause"}` … | Playback control |

```bash
TOKEN=...   # from the setup page
curl -X POST http://speaker-relay.local/api/play -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url":"http://192.0.2.20:8090/yt/abc.m4a?exp=…&sig=…","content_type":"audio/mp4"}'
```

Over MQTT, add an `"id"` to match replies: results go to `<base>/result` (with the firmware `version`),
a retained status is published to `<base>/status` every 30 s and within a second of any change (app,
player state, track, volume) with `proto`, `seq` and `uptime`, and `<base>/online` is `true`/`false`
(last will). `media` includes `content_type` and `duration` when the speaker reports them.
`<base>` defaults to `speaker-relay/<device-name>`.

Settings: `GET/POST /api/config` (secrets are never returned), `POST /api/token/rotate`
(returns the new token once), `POST /api/mqtt-ca` (PEM body; enables server verification for
MQTT over TLS), `POST /api/reboot`.

## Security notes

- Every `/api/*` call needs the Bearer token. HTTP on the board is unencrypted; keep it on the LAN.
- The setup access point is open and its page shows the token, but it only runs on a board with no saved
  Wi-Fi (first boot or after a BOOT-button wipe). Configure it promptly, out of reach of strangers.
- MQTT over TLS without an uploaded CA certificate does not verify the broker (a warning is logged).
  Upload the broker's CA with `POST /api/mqtt-ca` for real deployments.
- The Cast link to the speaker uses TLS without certificate checks: Cast devices use self-signed certificates.
