# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Podcast subscriptions: every member (viewers too) follows shows with the Follow button on a show's episodes,
  and finds them under "Following" in Music > Podcasts with a count of episodes published since they last opened
  the show; those episodes are marked New. Subscriptions are personal and go with the member
  (`GET`/`POST /podcasts/subs`, `POST /podcasts/subs/{id}/seen`, `DELETE /podcasts/subs/{id}`; `/podcasts/episodes`
  has the caller's `subscription`). Feeds are read a few at a time and cached for 15 minutes; database schema 7.
- Talkie, a walkie-talkie between members: while This device is the music output, the Announce page (and its nav
  label) is Talkie, with two tabs. Walkie: hold to talk live to everyone who has the Walkie open, one at a time,
  heard once and not kept; the members show as cards (who talks, who listens, who is online but can't hear).
  Voice messages: hold to record a message kept for 24 hours, with "Not played yet" per device, an unread count on
  the tab and the nav item, and delete (with Undo) for your own. Other pages show a small "2 on Walkie · Join" chip
  while others are in the Walkie. 60 seconds at most, the same for every role (to announce on the speaker, switch
  the output back to it). "Hear Talkie on this device" in App settings (`WebSocket /talkie` with a required
  `mode`, `walkie` or `message`; `GET /talkie/clips`, `GET /talkie/clips/{id}.mp3`, `GET /talkie/live/{id}`,
  `DELETE /talkie/clips/{id}`; clips in `TALKIE_DIR`; database schema 8).
- UI design reference in `docs/design/`: one HTML page with screenshots of every screen on each device, theme and
  language, for anyone designing on top of the app.
- About, Privacy and Licenses pages, from Account ("About", with the version; Account & app settings on iPad/desktop) and
  signed out from "Privacy · About" under the sign-in form. About shows the version and build, this server's speaker,
  connection and the owner's contact (signed in only), and links to What's new, the security policy and issue
  reports. Privacy says in plain words what is stored, who can see what, and what goes to other services. Licenses
  lists the app's MIT license, the required notices and every open-source part with its license text
  (`static/licenses.json`, `static/licenses/`).
- `owner_contact` setting (Speaker settings, "Contact for members"): how members reach the owner; About shows it to
  signed-in members and hides the row when it's empty.
- `GET /about` (anyone): `version` and `build`; signed in also `server` (`speaker`, `transport`, `owner_contact`).

### Changed
- The version lives in `version.py` (0.6.0), kept equal to `pyproject.toml` (was 0.2.0) and the newest CHANGELOG
  release by a test; the radio-browser and feed User-Agent says `speaker-service/0.6.0` (was 0.2).
- Android: a short context line under the big page title says what matters on that page: what the speaker (or This
  device) is doing on Now, Announce and Music, the playing playlist or how many there are, what's left on the
  schedule today, members and disabled ones, today's activity, unsaved speaker settings. iOS and desktop don't show it.
- Playlists are sorted into Music and Announcements (playlists of announcements only) inside My playlists, Shared and
  Members' playlists. `GET /playlists` items have `tts_only`; empty and mixed playlists count as music.

### Fixed
- Android: a page left before it finished loading no longer leaves its floating button (FAB) on the next page.
- Android: members' avatars (Members, Account, Talkie) have white initials again; they were dark on the dark
  member colours and hard to read.

## [0.6.0] - 2026-11-05

### Added
- This device plays HLS radio through the server: `GET /local/hls` (signed) rewrites the playlist so variant
  playlists, segments, keys and init sections go through signed relay links. Browsers that can't play HLS say so
  and point to the speaker, Safari or a recent Chrome.
- A live stream on This device that ends or drops (including the relay's 6-hour cut) reconnects by itself with a
  fresh link after 1, 2, 4, 8 and 16 s, at most 5 times in a row; 60 s of playing resets the count.
- Owners unlink a member's Google account and remove their passkeys in Members, for a lost phone or a Google
  account that isn't theirs any more (`GET /users/{id}/passkeys`, `DELETE /users/{id}/passkeys/{pid}`,
  `DELETE /users/{id}/google`). The member is signed out of every device; the API won't take away their only way in.
- Seek on the speaker: operators drag the Now page's progress bar (or use the arrow keys) and one `POST /seek`
  is sent when they let go. `/status` media has `seekable` (false for live streams and for a relay before
  protocol 2).
- Relay firmware 0.2.0 (not tested on hardware): a `seek` command (`POST /api/seek`, `{"cmd":"seek"}`) and
  status `proto` 2.
- Every member can change their own display name with the pencil next to it in Account (`PATCH /me`). Role,
  disabled and password stay with owners and `/auth/password`.

### Fixed
- Leaving Activity while it was still loading could throw a page error (a body read cut short by the page change
  was treated as an empty answer).
- Relay firmware: a play onto a cold speaker runs step by step from the main loop, so MQTT, HTTP and status
  keep running while the speaker starts (it used to block for up to ~40 s).
- On iPad, desktop and iPhone in landscape the scrolled page header is a floating glass bar instead of a flat strip
  that ran into the sidebar, and the sidebar clears the iPhone notch in landscape.
- The relay plays SHOUTcast v1 stations that answer `ICY 200 OK`.
- The relay connects only to the public addresses it checked, so a DNS answer that changes after the check can't
  point it inside the network (DNS rebinding).

### Changed
- One icon set for the whole web app (`js/icons.js`); a few icons on Music, Schedule, Help, Settings and Account are
  redrawn to match the rest. Front-end modules are named for what they do instead of the team that wrote them.

### Docs
- README.en.md (full English guide) and a language switch on both READMEs. The Thai README gains a schedules API
  section, Docker first-run steps and limits it was missing, and corrections where it no longer matched the code.

## [0.5.1] - 2026-11-04

### Added
- Personal playlists and files (schema 6: `owner_id` on `playlists` and `media_files`, deleted with their member,
  files on disk too). Viewers create, edit and delete their own playlists and upload their own files; operators and
  admins make shared ones unless they ask for `personal`. Personal items are seen only by their owner and admins
  (others get 404); everything from before stays shared. Playlists and files carry `owner_id`, `owner_name`, `mine`
  and `can_edit`; files also `uploader_id`/`uploader` (the old `owner` field). A playlist's `file` items must be
  files its owner can see, and `/local/resolve` plays only files the caller can see.
- Viewers may skip, go back and jump in the speaker's queue (`/queue/next`, `/prev`, `/jump`) and search YouTube,
  radio and podcasts (`/youtube/search`, `/radio/search`, `/podcasts/search`, `/podcasts/episodes`).

### Changed
- Viewers on This device may play YouTube tracks the server hasn't saved yet (reverts the cached-only rule).
- Schedules play shared playlists only (a personal one would go with its member).
- The web app follows a viewer's output: on the speaker there is no Music page, shared playlists are read-only and
  previous/next and tapping a queue row work; on This device Music appears, uploads are private and Playlists
  gains "My playlists". Owners see members' personal playlists and files in their own group.

### Fixed
- Saving a new speaker name or address no longer waits (up to ~10 s) for a connect to the offline old speaker.

## [0.5.0] - 2026-11-03

### Added
- "This device" output: the speaker picker offers this phone/tablet/computer to operators. Now playing, Music and
  Playlists then play in the browser (local queue with shuffle/repeat, seek, volume, lock-screen controls via the
  Media Session API), per browser (`spk.output`), without changing what anyone else hears. `POST /local/resolve`
  hands out the same signed media links without contacting the speaker. Announcements, live talk and schedules
  still play on the speaker, and the Announce/Schedule pages say so.
- "This device" for viewers too (it plays only on their own device); `POST /local/played` logs one "Played on
  their device" Activity entry per play someone starts; `GET /local/stream` relays radio the browser can't fetch
  itself (http:// on an https page, unknown types) through a signed, SSRF-checked, size/time-limited stream proxy.
  The quick tour gains a "This device" step; people who finished the old tour see just that step once.
- SponsorBlock (`yt_skip_segments`, default `interaction`, `selfpromo`, `sponsor`): sponsor reads inside YouTube
  videos are cut out after download (needs ffmpeg); cache files carry a tag of the cut categories
  (`<id>.sb-<hash>.<ext>`). Files cached before this play at once and are cut in the background from the local
  copy (hash-prefix SponsorBlock lookup, niced ffmpeg, one job at a time), so nothing is downloaded again.
  `POST /youtube` resolves the video first and plays a cached copy instead of downloading it again.

### Fixed
- Android tablets: Sign-in methods is a row of the "Your account" card on Members, and the display-name label
  sits inside its field on Account.
- The quick tour skipped its This device step on Android phones.
- `/tts.mp3` answers Range requests, so announcements played on This device can be sought.

## [0.4.0] - 2026-11-02

### Added
- Android look for the web app, chosen from the device's OS (no setting), in Material 3 style with the lagoon
  colours in light and dark. Phones get a floating nav pill with slide-to-select and filled active icons;
  tablets get a side rail with Help under the admin items. Page titles stay pinned under the top bar. Also a Now
  Bar, snackbars, blurred-scrim sheets, full-screen dialogs and floating action buttons, and the back button
  closes sheets and dialogs. iPhone, iPad and desktop look the same as before.
- Android layouts for Now playing, Announce, Music, Playlists, Schedule, Members, Activity, Settings, Account,
  Help, sign-in and first-account setup, with two panes from 960 px wide. Members splits into "Your account" and
  "Other people".

### Fixed
- The Now playing queue could show the word "null".

## [0.3.1] - 2026-10-30

### Fixed
- Phones ran hot with Now playing or Sign in open: the 3D speaker's spin, float, LED pulse and sound rings
  redrew the whole model every frame. It now moves for 8 s after it appears, changes state or is touched, then
  rests; the sign-in glow breathes three times instead of forever (about 55% -> 5% CPU on Now playing).

## [0.3.0] - 2026-10-30

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
