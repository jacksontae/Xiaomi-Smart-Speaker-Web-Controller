# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions will follow
[Semantic Versioning](https://semver.org/) once releases begin.

## [Unreleased]

### Added
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
