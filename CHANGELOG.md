# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions will follow
[Semantic Versioning](https://semver.org/) once releases begin.

## [Unreleased]

### Added
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
