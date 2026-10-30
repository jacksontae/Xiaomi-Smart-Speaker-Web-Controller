# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Web app v3, rebuilt from the approved prototype for iPhone, iPad and desktop: English by default with Thai,
  light/dark/system theme, app-wide reduce motion, self-hosted Anuphan font, 3D speaker art. Pages: sign-in and
  first-account setup, Now playing (queue, volume, relay health), Announce (quick phrases, live talk), Music
  (YouTube, radio, podcasts, my files), Playlists, Schedule, Members, Activity, Speaker settings, App settings,
  Account (Google link, passkeys), Sign-in methods and searchable Help. Offers a passkey after sign-in.
- Scheduled announcements and playlists (`/schedules`), now working with both transports.
- Nightly SQLite + config backups for the remote deployment (`backup` service), with restore.
- Sign in with Google: members link their Google account (`POST/DELETE /me/google`) and then sign in with it
  (`POST /auth/google`); no self-sign-up. ID tokens are checked against Google's keys (`aud`, `iss`, `exp`,
  `email_verified`, single use). The owner switches it on with `google_client_id` + `google_signin`;
  `GET /auth/state` reports `methods` and `google_client_id`.
- Passkeys (WebAuthn): register, rename and remove passkeys under `/me/passkeys`, sign in with
  `/auth/passkey/options` + `/auth/passkey/verify`. The RP ID is the host of `public_base_url` (HTTPS, or
  localhost); single-use challenges, sign-counter checks. Owner settings `passkey_signin` and
  `passkey_required_for_admins`; members carry `has_passkey`. Schema version 4 adds the `passkeys` table.
- Music sources: internet radio (radio-browser.info search, favourites, played as a LIVE stream), podcasts
  (iTunes Search API + RSS episodes) and "My files" (audio uploads with size/type/quota limits, served through
  signed `/media/...` links). All three play directly, resume after an announcement, and can be playlist items
  (`radio`, `podcast`, `file`). Database schema version 5 (version 3 adds the Google account columns).
- Live talk: operators speak through the speaker from the browser's microphone (`WebSocket /talk`).
  MediaRecorder chunks (WebM/Opus, Ogg/Opus or Safari's MP4/AAC) are transcoded by ffmpeg into a live MP3
  stream at a signed `/talk/<id>/live` URL; music pauses and resumes afterwards, with an optional chime,
  a `talk_max_seconds` limit (default 120) and an activity entry "Talked live for m:ss". Needs ffmpeg
  (added to the Docker image).

## [0.2.0] - 2026-10-30

### Added
- ESP32 relay transport: the service can drive the speaker through an ESP32/ESP8266 board over MQTT
  (`transport: "mqtt"`, `<base>/cmd`, `/result`, `/status`, `/online`), with offline detection and
  `public_base_url` for media links served through a tunnel. The firmware is now tested on an ESP32 with a
  Mi Smart Speaker.
- The relay publishes its status within a second of a change and reports media duration and content type;
  the service only safety-polls relays that push changes.
- MQTT over WebSocket on the ESP32 (`ws://` / `wss://` broker URL, verified against public root CAs or an
  uploaded CA).
- Self-hosted broker for remote deployments: `deploy/remote` runs Mosquitto (no anonymous clients, per-user
  passwords and ACL) next to the service, published through the Cloudflare Tunnel.

### Fixed
- The relay no longer reports the last track's title and position after the speaker app stops.

## [0.1.0] - 2026-10-29

### Added
- Web v2 backend: user accounts with roles (`admin`, `operator`, `viewer`) and first-run setup guarded by the API token;
  session cookie (`HttpOnly`, `SameSite=Strict`, 30-day sliding expiry), `X-Requested-With: speaker-web` required for
  cookie-authenticated changes, scrypt password hashes, login throttling (5 failures per IP and username per 5 minutes).
  The API token keeps working and acts as `admin`. Every endpoint now checks the caller's role.
- Members management (`/users`) with guards against removing, disabling or demoting yourself or the last admin.
- Playlists of YouTube, direct-URL and TTS items with reordering, and `GET /youtube/search`.
- Play queue (`/playlists/{id}/play`, `/queue`): shuffle, repeat off/all/one, next/previous/jump, auto-advance when a
  track ends (not when an announcement ends), prefetch of the next YouTube track, failed items skipped.
  `/status` now includes `queue` and `media.thumbnail`.
- Quick phrases (`/phrases`) and an activity log (`/activity`, newest 5000 entries, volume changes coalesced).
- SQLite storage at `DATA_PATH` (default `data.db`) with a schema version for later migrations.
- `/static/...`, `/manifest.webmanifest` and `/apple-touch-icon.png` are served for the web UI.
- API token: control endpoints require `Authorization: Bearer <token>`; the token is generated on first run,
  stored in `config.json` (mode 600), never returned by `/settings`, and rotated with `speakerctl token --rotate`.
- Media links handed to the speaker are HMAC-signed and expire after 6 hours.
- Web UI asks for the token once and keeps it in that browser.
- Relay firmware (`firmware/`, PlatformIO) for ESP32, ESP32-S3 and ESP8266 (plain MQTT only on ESP8266): Cast v2 client, HTTP API with Bearer
  token, MQTT commands and status, Wi-Fi setup access point, mDNS speaker discovery. Not yet tested on hardware.
- HTTP service and web UI for a Google Cast speaker: Thai TTS announcements, YouTube audio, volume, pause/resume/stop.
- Resume the interrupted YouTube track after an announcement (`resume_after_say`).
- Editable settings (web UI, `POST /settings`, `config.json`) and speaker discovery (`GET /speakers`).
- macOS LaunchAgent with `speakerctl install|start|stop|restart|status|logs|config|uninstall`.
- Test suite with a fake speaker, and GitHub Actions CI (ruff, pytest on Python 3.11–3.14).
- Contributing guide, code of conduct, security policy, issue and pull request templates.

### Fixed
- Minimum Python is 3.11: PyChromecast 14 and current yt-dlp no longer install on 3.10.
- A dropped speaker connection no longer breaks every request until restart.
- An unreachable speaker now returns HTTP 503 within ~10 s instead of hanging and failing with 500.
