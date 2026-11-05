# Xiaomi-Smart-Speaker-Web-Controller

English | [ภาษาไทย](README.md)

[![CI](https://github.com/jacksontae/Xiaomi-Smart-Speaker-Web-Controller/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/jacksontae/Xiaomi-Smart-Speaker-Web-Controller/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

An HTTP API and web UI for a Google Cast speaker such as the **Xiaomi Mi Smart Speaker**, without Google Assistant:
text-to-speech announcements, YouTube audio, internet radio, podcasts, uploaded files, playlists, schedules and live
talk from a browser microphone. The service talks to the speaker over the local network with the Cast protocol, and
the speaker fetches all audio from the service.

> **Status:** the Python service runs on macOS (LaunchAgent) and in Docker on a Linux VM. The relay firmware
> (see [firmware/](firmware/README.md)) is tested on an ESP32 (`esp32dev`); ESP32-S3 and ESP8266 build but are not
> yet tested on hardware.

## Install (macOS)

You need Python 3.11+ and Node.js (yt-dlp uses it to solve YouTube's JavaScript challenges), e.g.
`brew install python node`. Live talk also needs ffmpeg: `brew install ffmpeg` (or point the `FFMPEG` environment
variable at it). Without ffmpeg everything else still works.

```bash
git clone git@github.com:jacksontae/Xiaomi-Smart-Speaker-Web-Controller.git
cd Xiaomi-Smart-Speaker-Web-Controller
./speakerctl install     # creates .venv, installs dependencies, copies config.json, starts at login
```

Then set `speaker_ip` in `config.json`, or press "Find" in the web UI to pick a speaker on the LAN. To run it
without the LaunchAgent: `./.venv/bin/python app.py`.

## Run

The service starts every time you log in to the Mac (LaunchAgent `~/Library/LaunchAgents/local.speaker-service.plist`)
and is restarted if the process dies. Output goes to `service.log` in the repository folder.

```bash
./speakerctl status      # service state and the speaker's /status
./speakerctl restart
./speakerctl stop | start
./speakerctl logs [n]    # follow the log (last n lines first, default 50)
./speakerctl config      # edit config.json, then restart
./speakerctl token       # print the API token; --rotate issues a new one (the old token and old media links stop working)
./speakerctl uninstall   # remove auto-start
```

Web UI: `http://<this machine's IP>:8090/` · API docs (OpenAPI): `http://<IP>:8090/docs`

On first open, the web UI asks for the API token to create the first admin account (see [API](#api)).

## Install (Docker on a VM)

For a service that runs away from the speaker's LAN, use `deploy/remote/` (Docker Compose: the service, a Mosquitto
broker, `cloudflared` and a nightly backup). The speaker is then driven through an ESP32 relay over MQTT. The steps
are in [Remote deployment](#remote-deployment-esp32-relay--self-hosted-mqtt--cloudflare-tunnel).

In the container, `config.json`, `data.db`, uploads (`media/`) and the YouTube cache live on the `speaker-data`
volume under `/data`. The API token is generated on first start; to read it for the first-admin setup:

```bash
docker compose -f deploy/remote/docker-compose.yml exec speaker-service \
  python -c "import json; print(json.load(open('/data/config.json'))['api_token'])"
```

## Settings

Three ways to change them: the web UI ("Settings"), `POST /settings`, or edit `config.json` and run
`./speakerctl restart`.

| key | default | meaning |
|---|---|---|
| `speaker_ip` | `192.0.2.10` | Speaker IP address or hostname (press "Find" in the web UI to choose from speakers on the LAN) |
| `speaker_name` | `Air Purifier speaker` | Display name (1–64 characters) |
| `port` | `8090` | Service port, 1024–65535 (changing it restarts the service) |
| `default_volume` | `null` | Volume set before an announcement or playback, 0–1; `null` = leave it |
| `tts_lang` | `th` | Default language of `/say` |
| `cache_keep` | `20` | Number of YouTube tracks kept in `cache/` |
| `yt_skip_segments` | `["interaction", "selfpromo", "sponsor"]` | SponsorBlock categories cut out of downloaded YouTube audio (needs ffmpeg); `[]` = off. See [YouTube ads](#notes) |
| `resume_after_say` | `true` | After an announcement, continue the interrupted track from where it stopped (1 s earlier) |
| `talk_max_seconds` | `120` | Longest live talk in seconds (10–600) |
| `transport` | `cast` | `cast` = talk to the speaker directly on the LAN · `mqtt` = through the ESP32 relay (see Remote deployment) |
| `mqtt` | see `config.example.json` | Relay broker: `host`, `port`, `tls`, `ca_file`, `username`, `password`, `base_topic`, `client_id`, plus timing (`keepalive`, `offline_after`, `status_refresh`, `command_timeout`, `play_timeout`, `reconnect_min`, `reconnect_max`) |
| `public_base_url` | `null` | Base of the media links the speaker gets, for when the auto-detected LAN address is wrong or the speaker is remote, e.g. `http://192.0.2.20:8090` or `https://speaker.example.com`. Its host is the passkey RP ID |
| `google_client_id` | `null` | OAuth client ID for "Sign in with Google", e.g. `1234-abc.apps.googleusercontent.com` (not a secret) |
| `google_signin` | `false` | Owner (admin) switch for Google sign-in; needs `google_client_id` |
| `passkey_signin` | `true` | Allow passkey sign-in (works only when `public_base_url` is `https://` or `http://localhost`) |
| `passkey_required_for_admins` | `false` | Admins who have a passkey must sign in with it (can be turned on only once every admin has one) |
| `owner_contact` | `null` | How members reach the owner, e.g. `it@example.com` or a LINE id (up to 120 characters); shown on the About page to signed-in members only |

`api_token` is also stored in `config.json` but is never returned by `GET /settings` and can't be changed through
the API.

```bash
TOKEN=$(./speakerctl token)
curl -X POST localhost:8090/settings -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"default_volume":0.4}'
curl -H "Authorization: Bearer $TOKEN" localhost:8090/speakers    # find Cast speakers on the LAN
```

Environment variables used by the service:

| variable | default | meaning |
|---|---|---|
| `CONFIG_PATH` | `./config.json` | Settings file |
| `DATA_PATH` | `./data.db` | SQLite database |
| `CACHE_DIR` | `./cache` | YouTube cache |
| `MEDIA_DIR` | `media/` next to `data.db` | Uploaded files |
| `TALKIE_DIR` | `talkie/` next to `data.db` | Talkie clips (kept 24 hours) |
| `UPLOAD_MAX_MB` · `UPLOAD_QUOTA_MB` | `50` · `2000` | Size limit per upload · for all uploads together |
| `YT_FORMAT` | `bestaudio[ext=m4a]/bestaudio` | yt-dlp format |
| `FFMPEG` | `ffmpeg` | ffmpeg binary (live talk, SponsorBlock cuts) |
| `SPONSORBLOCK_API` | `https://sponsor.ajay.app` | SponsorBlock server |
| `RADIO_BROWSER_URL` | `https://all.api.radio-browser.info` | Radio directory |
| `PODCAST_SEARCH_URL` | `https://itunes.apple.com/search` | Podcast search |
| `TZ` | system zone | Time zone for schedules |
| `SPEAKER_TRANSPORT`, `PUBLIC_BASE_URL`, `MQTT_*` | – | Override `config.json`; see Remote deployment |

## API

Two ways to call the API. Without authentication you get `401`, without enough rights `403`. Error bodies are
always `{"detail": "..."}`.

- **API token:** send `Authorization: Bearer <token>`. It has the `admin` role. Use it for curl, integrations and
  scripts.
  - The token is generated on first start and stored in `config.json` (file mode 600). Print it with
    `./speakerctl token`.
  - `GET /settings` doesn't return it and the API can't change it; use `./speakerctl token --rotate`.
- **User accounts (web UI):** signing in sets the `sid` cookie (`HttpOnly`, `SameSite=Strict`, valid 30 days from
  last use).
  - Requests that change data (POST/PUT/PATCH/DELETE) with the cookie must send `X-Requested-With: speaker-web`,
    or they get `403`.
  - While there are no users, the web UI asks for the API token to create the first admin (`POST /auth/setup`).
  - Passwords are 8–256 characters, stored with scrypt. 5 failed sign-ins in 5 minutes (per IP and username) give
    `429` with `Retry-After`.
- The audio files the speaker fetches (`/tts.mp3`, `/yt/...`, `/media/...`, `/talk/...`) can't use a header,
  because the speaker can't send one. They use links signed with an HMAC of the API token that expire after 6 hours.
- Users, playlists, quick phrases, schedules, radio favourites, file records and the activity log are stored in
  SQLite at `data.db` (change with `DATA_PATH`).

### Roles

| role | can do |
|---|---|
| `viewer` | See status, queue, shared playlists and quick phrases · skip/back/pick a track in the speaker's queue · search music and play on "This device" · upload files and make their own (personal) playlists · Talkie |
| `operator` | viewer + announce, play, set volume, pause/resume/stop, control the queue, edit shared playlists, quick phrases and schedules, radio and podcasts, upload shared files, live talk |
| `admin` | operator + manage members, settings, speaker discovery, activity log, rename or delete any uploaded file |

The web UI calls `admin` "Owner".

### Accounts

| Method | Path | Role | Body | Does |
|---|---|---|---|---|
| GET | `/auth/state` | anyone | – | `{"needs_setup", "user", "methods": {"password", "google", "passkey"}}`, plus `google_client_id` when Google is on (and `passkey_required` when an admin must add a passkey) |
| GET | `/about` | anyone | – | `{"version", "build"}` (app version, static build id), plus `server: {"speaker", "transport", "owner_contact"}` when signed in |
| POST | `/auth/setup` | anyone (only while there are no users) | `{"api_token", "username", "display_name", "password"}` | Create the first admin and sign in (wrong token `401`, users already exist `409`) |
| POST | `/auth/login` | anyone | `{"username", "password"}` | Sign in, set the cookie |
| POST | `/auth/logout` · `/auth/logout-all` | signed in | – | Sign out this device · all devices |
| POST | `/auth/password` | signed in | `{"current", "new"}` | Change password (other devices are signed out) |
| POST | `/auth/google` | anyone | `{"credential"}` | Sign in with a Google ID token (linked accounts only: not linked `401`, Google off `409`) |
| POST · DELETE | `/me/google` | signed in | `{"credential"}` · – | Link · unlink a Google account to your own account (linked to someone else `409`) |
| POST | `/auth/passkey/options` | anyone | – | `{"publicKey"}` for `navigator.credentials.get()` |
| POST | `/auth/passkey/verify` | anyone | `{"credential"}` | Sign in with a passkey, set the cookie (failure `401`) |
| POST | `/me/passkeys/options` | signed in | – | `{"publicKey"}` for `navigator.credentials.create()` |
| GET · POST | `/me/passkeys` | signed in | `{"credential", "name"}` | List · add your own passkeys |
| PATCH · DELETE | `/me/passkeys/{id}` | signed in | `{"name"}` · – | Rename · delete a passkey |
| GET · POST | `/users` | admin | `{"username", "display_name", "password", "role"}` | List · add members |
| PATCH · DELETE | `/users/{id}` | admin | `{"display_name", "role", "password", "disabled"}` (only the fields to change) | Edit · delete a member |

Usernames are 3–32 characters of `a-z 0-9 . _ -`. You can't delete, disable or demote yourself, and at least one
enabled admin must remain (`409`). Disabling an account or changing its password signs that member out everywhere.
The `/me/*`, `/auth/password` and `/auth/logout-all` endpoints need a user account; the API token gets `400`.

#### Sign in with Google

1. Create an OAuth client ID of type "Web application" in the Google Cloud console and add the web UI's origin
   (e.g. `https://speaker.example.com`) under "Authorized JavaScript origins".
2. Set `google_client_id` and turn on `google_signin` in Settings (or `POST /settings`).
3. Members sign in with their password first, then press "Link Google account" on the Account page. After that they
   can sign in with Google. There is no self sign-up.

The service checks the ID token's signature against Google's keys (cached for 1 hour), plus `aud`, `iss`, `exp`
and `email_verified`, and stores the Google subject id (`sub`), not just the email. A token works once. 5 failures
in 5 minutes (per IP) give `429`. You can't unlink Google if it is your only remaining sign-in method (`409`).

#### Passkeys

Passkeys work when the web UI is opened through a `public_base_url` that is `https://` (or `http://localhost` for
development), because browsers don't allow passkeys on plain http or on an IP address. The RP ID is the host of
`public_base_url`; if the domain changes, existing passkeys stop working.
`credential` is the `PublicKeyCredential` as JSON (binary fields base64url-encoded, as `credential.toJSON()` gives).
A challenge works once and expires after 5 minutes. The sign counter is checked (a counter that doesn't increase
means a copied key and is refused). 5 failures in 5 minutes (per IP) give `429`.
You can't delete your last passkey if it is your only sign-in method, or if you are an admin while
`passkey_required_for_admins` is on (`409`).
With `passkey_required_for_admins` on, an admin who has a passkey can't sign in with a password or Google (`403`).
A new admin without a passkey can still sign in with a password, but `/auth/state` then contains
`"passkey_required": true` so the web UI can ask them to add one. The API token always works (recovery path).

### Speaker

| Method | Path | Role | Body | Does |
|---|---|---|---|---|
| GET | `/status` | viewer | – | App, track (with `media.thumbnail`), volume, queue (`queue`), `talking`; admins also get `relay` |
| POST | `/say` | operator | `{"text": "...", "lang": "th", "volume": 0.4}` | Announce text (TTS) |
| POST | `/youtube` | operator | `{"query": "search words or URL", "volume": 0.3}` | Play YouTube audio (clears the queue) |
| GET | `/youtube/search?q=...&limit=8` | operator | – | Search YouTube without downloading (`limit` 1–20) |
| POST | `/play` | operator | `{"url": "...", "content_type": "audio/mp3", "volume": 0.4}` | Play an audio URL (clears the queue) |
| POST | `/volume` | operator | `{"level": 0.3}` | Set volume 0–1 |
| POST | `/pause` · `/resume` · `/stop` | operator | – | Playback control (`stop` also clears the queue) |
| GET · POST | `/settings` | admin | `{"default_volume": 0.4}` | Read · change settings (partial update) |
| GET | `/speakers` | admin | – | Find Cast speakers on the LAN |
| GET | `/activity?limit=50&before_id=` | admin | – | Activity log, newest first (`limit` up to 500; the newest 5000 entries are kept) |

### Playlists and queue

| Method | Path | Role | Body | Does |
|---|---|---|---|---|
| GET · POST | `/playlists` | viewer | `{"name", "personal": false}` | List the playlists you can see · create one |
| GET · PATCH · DELETE | `/playlists/{id}` | viewer | `{"name"}` | Get with items · rename · delete |
| POST | `/playlists/{id}/items` | viewer | `{"kind": "youtube"\|"url"\|"tts"\|"radio"\|"podcast"\|"file", "source", "title", "lang", "thumbnail", "duration", "content_type"}` | Add an item (at most 500 per playlist) |
| DELETE | `/playlists/{id}/items/{item_id}` | viewer | – | Remove an item |
| PUT | `/playlists/{id}/order` | viewer | `{"item_ids": [...]}` | Reorder (must list every id exactly, else `409`) |
| POST | `/playlists/{id}/play` | operator | `{"start_index": 0, "shuffle": false, "repeat": "off"\|"all"\|"one"}` | Play the whole playlist as the queue |
| GET · PATCH | `/queue` | viewer · operator | `{"shuffle", "repeat"}` | Get the queue (`null` if none) · change shuffle/repeat |
| POST | `/queue/next` · `/queue/prev` · `/queue/jump` | viewer | `{"index"}` (jump only) | Skip |
| POST | `/queue/clear` | operator | – | Clear the queue and stop |
| GET · POST | `/phrases` | viewer · operator | `{"text", "lang"}` | Quick phrases (the web UI sends them to `/say`) |
| DELETE | `/phrases/{id}` | operator | – | Delete a quick phrase |

- Personal playlists: `owner_id` is the owner's id (`null` = shared; every playlist from before schema 6 is shared).
  Results carry `owner_id`, `owner_name`, `mine` and `can_edit` (whether the caller may edit it).
  - Viewers can only create personal playlists. Operators and admins create shared ones unless they send
    `"personal": true` (the API token can't create personal ones, `400`).
  - Who sees them: shared ones everyone; personal ones only their owner and admins (operators don't see other
    people's). Anything you can't see answers `404`.
  - Editing (rename, delete, add/remove/reorder items): shared ones need operator or above (viewers get `403`);
    personal ones need their owner or an admin.
  - `/playlists/{id}/play` (plays on the speaker) is still operator and needs a playlist you can see. Schedules only
    play shared playlists.
  - A `file` item must be a file the playlist's owner can see (a shared playlist takes shared files only; a personal
    one takes shared files or the owner's own), else `400`.
  - Deleting a member deletes their personal playlists and files (files on disk too) and turns off schedules that
    played those playlists.
- Viewers drive the speaker's queue only with next/prev/jump (logged like an operator's). Shuffle/repeat, clearing,
  stop and volume still need operator.
- A `youtube` item takes a URL, a video id or search words (first result). A `url` item must be an http(s) link and
  needs a `title`. A `tts` item is at most 1000 characters.
- A `radio` item takes a radio-browser station uuid or a stream URL (stream URLs need a `title`). A `podcast` item
  takes an episode's audio URL (needs a `title`). A `file` item takes the id of an uploaded file; deleting the file
  also removes it from playlists.
- A radio station in the queue plays live and never ends; the queue stays on it until you press next.
- The queue moves to the next track when one ends (announcements don't count). The next YouTube track is downloaded
  ahead of time. Items that fail to load are skipped and logged.
- `say` during a queue: the announcement plays, the interrupted track continues, then the queue carries on.
- The queue lives in memory: a restart loses it, and editing a playlist doesn't change a queue that is playing.

```bash
TOKEN=$(./speakerctl token)
curl -X POST localhost:8090/say -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"text":"Air quality is poor, please close the windows","lang":"en"}'
curl -X POST localhost:8090/youtube -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"query":"piano instrumental"}'
curl -X POST localhost:8090/playlists/1/play -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"shuffle":true,"repeat":"all"}'
```

### Schedules

| Method | Path | Role | Body | Does |
|---|---|---|---|---|
| GET | `/schedules` | viewer | – | `{"timezone", "now", "items"}` |
| POST | `/schedules` | operator | `{"name", "enabled", "action", "text", "lang", "playlist_id", "shuffle", "volume", "time", "days", "date"}` | Create a schedule |
| PATCH · DELETE | `/schedules/{id}` | operator | any subset of the fields above · – | Edit · delete |
| POST | `/schedules/{id}/run` | operator | – | Run it now as a test (ignores time and `enabled`; `next_run` is unchanged) |

- `action` is `say` (needs `text`, optional `lang`) or `playlist` (needs `playlist_id`, optional `shuffle`).
  `volume` is optional, 0–1. `name` is at most 80 characters.
- `time` is `HH:MM` (24-hour) in the server's time zone (`TZ`, else the system zone, else UTC).
- `days` is a list of weekdays, `0` (Monday) to `6` (Sunday), for a repeating schedule. With `days` empty it is a
  one-off on `date` (`YYYY-MM-DD`), which must not be in the past; it turns itself off after it runs.
- The service checks for due schedules every 15 seconds. A run more than 5 minutes late (e.g. the service was down)
  is skipped and recorded as `missed`. Each item has `next_run`, `last_run` and `last_result` (`ok`, `missed` or
  the error).
- A playlist schedule replaces the queue and plays with repeat off; with `shuffle` it starts at a random item.

### Music sources: radio, podcasts, my files

| Method | Path | Role | Body / query | Does |
|---|---|---|---|---|
| GET | `/radio/search?q=&country=TH&tag=&limit=20` | viewer | – | Search stations on [radio-browser.info](https://www.radio-browser.info) (most listened first, `limit` up to 50) |
| GET · POST | `/radio/favorites` | viewer · operator | `{"uuid"}` or `{"url", "name"}` | Favourite stations · add one (same radio-browser station twice `409`) |
| DELETE | `/radio/favorites/{id}` | operator | – | Remove a favourite |
| POST | `/radio/play` | operator | `{"favorite_id"}` or `{"uuid"}` or `{"url", "name"}`, plus `"volume"` | Play radio live (clears the queue) |
| GET | `/podcasts/search?q=&country=TH&limit=20` | viewer | – | Search shows with the iTunes Search API; results include `feed_url` |
| GET | `/podcasts/episodes?feed=<feed_url>&limit=50` | viewer | – | Read the RSS feed: show details and latest episodes (`limit` up to 200), plus the caller's `subscription` (or `null`) |
| GET · POST | `/podcasts/subs` | viewer | `{"feed_url", "title", "author", "artwork"}` | Your followed shows (personal) with `new_count` · follow one (again is fine: same row; without `title` the feed is read) |
| POST | `/podcasts/subs/{id}/seen` | viewer | – | You opened the show: its episodes so far stop counting as new |
| DELETE | `/podcasts/subs/{id}` | viewer | – | Unfollow |
| POST | `/podcasts/play` | operator | `{"url", "title", "thumbnail", "content_type", "volume"}` | Play one episode (clears the queue) |
| GET | `/files` | viewer | – | `{"items", "used", "quota", "max_size", "types"}` (files you can see) |
| POST | `/files?name=<file name>&duration=<seconds>&personal=1` | viewer | The audio file itself as the body (not a form) | Upload |
| PATCH · DELETE | `/files/{id}` | viewer (by the file's rights) | `{"title"}` · – | Rename · delete |
| POST | `/files/{id}/play` | operator | `{"volume"}` | Play a file (clears the queue) |

- Personal files follow the playlist rules: a viewer's upload is always personal; operators and admins upload shared
  files unless `personal=1`. You see shared files and your own (admins see all); others answer `404`. Each file has
  `owner_id`, `owner_name`, `mine`, `can_edit`, `uploader_id` and `uploader`.
- Renaming or deleting: a personal file by its owner or an admin; a shared file by the operator who uploaded it or an
  admin (viewers get `403`). The storage quota is still shared by everyone.
- Uploads are recognised from their content (mp3, aac, m4a, ogg/opus, wav, flac, webm), not from the name. Other
  types get `415`, too large `413`, quota full `507`.
- Files are stored in `media/` next to `data.db` (`MEDIA_DIR`), up to 50 MB each (`UPLOAD_MAX_MB`) and 2000 MB in
  total (`UPLOAD_QUOTA_MB`). The speaker fetches them through signed `/media/...` links, like `/yt/...`.
- The speaker fetches radio and podcast audio from the source directly. The server fetches podcast feeds itself, so
  it only accepts hosts on the public internet (no LAN addresses) and reads at most 10 MB.
- `say` during radio, a podcast or a file: the announcement plays, then playback continues (radio goes back to the
  live signal).
- The relay firmware currently plays everything as BUFFERED (it ignores the `stream_type` field); most radio
  stations still play.

### Play on this device

| Method | Path | Role | Body | Returns |
|---|---|---|---|---|
| POST | `/local/resolve` | viewer | `{"kind", "source", "title", "lang", "thumbnail", "duration", "content_type"}` (same as a playlist item) | `{"kind", "url", "proxy_url", "content_type", "title", "duration", "thumbnail", "live"}` |
| POST | `/local/played` | viewer | `{"title"}` | `204`, logs a `device play` activity entry |
| GET | `/local/stream?u=&t=&exp=&sig=` | signed link (from `proxy_url`) | – | Relays the source as a stream |
| GET | `/local/hls?u=&exp=&sig=` | signed link (from `proxy_url`) | – | An HLS playlist with its links turned into signed relay links |

- In the web UI, choose "This device" from the speaker name button. Now Playing, Music and Playlists then play in
  that browser's `<audio>` element instead of on the speaker (queue, shuffle, repeat, seeking, volume and lock-screen
  controls via Media Session run in the browser). The choice is stored per browser in `localStorage`
  (`spk.output`) and doesn't change what anyone else hears.
- Viewers can use it, including YouTube tracks the server hasn't downloaded yet, since it only plays on their own
  device. Endpoints that drive the speaker still need operator. A `file` item must be a file the caller can see, else
  `404`.
- `/local/resolve` doesn't contact the speaker and doesn't log (the browser calls it ahead for the next track and
  again when a link expires). The browser calls `/local/played` once per play request (a playlist is logged by its
  name, not per track, and seeking isn't logged). YouTube is downloaded into the same cache and returned as a signed
  `/yt/...` link (a path relative to this server); text returns `/tts.mp3?...`; files return `/media/...`; radio,
  podcasts and links return the source URL.
- `proxy_url` (radio, podcasts and external links) is a signed `/local/stream` link (`/local/hls` for HLS): the server fetches
  the source and passes the bytes on as they arrive, without storing them. The browser uses it only when needed: an
  `http://` stream on an `https://` page (mixed content, iPhone Safari), a type `canPlayType` says it can't play, or
  when the direct link fails. The relay accepts only http(s) to public hosts (private, loopback and link-local
  addresses are refused, on every redirect), passes content-type and Range on, refuses non-audio responses, cuts a
  stream after 30 seconds of silence, ends each relay at 512 MB or 6 hours, and allows 8 streams at once (`503`
  beyond that). It reads SHOUTcast v1 stations that answer `ICY 200 OK`, and connects only to the public addresses
  it checked (no DNS rebinding).
- HLS: `/local/hls` fetches the playlist (at most 512 KB) and turns every URI into a signed link (variant playlists
  through `/local/hls`; segments, keys and init sections through `/local/stream`). It plays in Safari and recent
  Chrome; a browser that can't play HLS shows a message to play it on the speaker instead.
- A live stream that ends or drops (including the relay's 6-hour cut) reconnects by itself with a fresh link after
  1, 2, 4, 8 and 16 seconds, at most 5 times in a row; 60 seconds of playing resets the count.
- Announcements, live talk and schedules always play on the speaker. On iOS you have to tap before any sound, and background playback lasts only while the page keeps
  playing.

### Live talk

The web UI records the microphone with MediaRecorder and sends chunks over `WebSocket /talk`. The server converts
them to MP3 with ffmpeg and has the speaker play the link `/talk/<id>/live` as a live stream. The delay is about
2–5 seconds, and the speaker can't talk back (its microphone isn't available).

- Authentication: the `sid` cookie (operator or higher), and `Origin` must be the same site (the request's host or
  the host of `public_base_url`). Scripts can send `Authorization: Bearer <token>` instead.
- One talker at a time; a second one gets `{"type": "error", "code": "busy"}`. Music stops during the talk and
  continues afterwards, as after an announcement.
- `GET /talk/status` (operator) returns `available` (ffmpeg present), `max_seconds` and `active` (who is talking).
  `/status` has `talking`.

| Direction | Message | Meaning |
|---|---|---|
| → | `{"type": "start", "mime": "audio/webm;codecs=opus", "chime": true, "volume": 0.6}` | First message (within 10 seconds). `mime` accepts `audio/webm`, `video/webm`, `audio/ogg`, `audio/mp4` (Safari), `audio/x-m4a` |
| ← | `{"type": "ready", "id", "max_seconds", "format"}` | Start sending audio (MediaRecorder binary frames) |
| ← | `{"type": "live"}` | The speaker has started the stream (after the chime, if on) |
| → | `{"type": "ping"}` · `{"type": "stop"}` | Answered with `{"type": "pong"}` · end the talk |
| ← | `{"type": "ended", "reason", "seconds", "detail"?}` | Finished, closed with code 1000. `reason`: `stopped`, `disconnected`, `max_length`, `idle` (no audio for 10 seconds), `interrupted` (something else was played), `too_large`, `speaker_error`, `transcoder_error` |
| ← | `{"type": "error", "code", "detail"}` | Not started, closed with `4400` bad_request · `4401` unauthorized · `4403` forbidden · `4409` busy · `4503` unavailable (no ffmpeg) |

To test by hand: `python tests/manual/talk_stream.py --url ws://127.0.0.1:8090/talk --token $TOKEN --file clip.webm`

### Talkie

A walkie-talkie between the members of this server. While "This device" is the music output, the Announce page is
the Talkie (operators and owners switch between Talkie and Speaker at the top; viewers only get Talkie). Hold the
button to talk: everyone with the app open hears it live (about 1–2 seconds behind), and the talk is kept as a clip
for 24 hours for those who weren't listening. One room, one talker at a time (separate from live talk on the speaker).
Each device can turn the sound off in App settings ("Hear Talkie on this device").

- `WebSocket /talkie`: the web app keeps it open on every page while signed in. Authentication: the `sid` cookie
  (any role) and a same-site `Origin`, as for `/talk`; the API token is refused (`4403`). The server re-checks the
  session on every `ping` and `start`.
- Recordings go through ffmpeg like live talk; clips are MP3 files in `talkie/` next to `data.db` (`TALKIE_DIR`).
  Talks shorter than 0.5 seconds keep no clip, a talk ends after 60 seconds, clips older than 24 hours are deleted,
  and deleting a member deletes their clips. Nothing goes to the activity log.

| Method | Path | Role | Body | Does |
|---|---|---|---|---|
| GET | `/talkie/clips` | viewer | – | The last 24 hours' clips, newest first: `id`, `user_id`, `name`, `seconds`, `created_at`, `url` |
| GET | `/talkie/clips/{id}.mp3` | viewer | – | A clip's MP3 (Range requests work) |
| GET | `/talkie/live/{id}` | viewer | – | The talk going on as one MP3 response from its start, ending when the talk does (a plain `<audio>` plays it) |

| Direction | Message | Meaning |
|---|---|---|
| ← | `{"type": "hello", "me", "online": [{"id", "name"}], "live": {"id", "user_id", "name", "url"} \| null, "clips"}` | On connect |
| ← | `{"type": "online", "online"}` | Someone opened or closed the app (several tabs count once) |
| → | `{"type": "start", "mime"}` | Talk (same `mime` values as `/talk`) |
| ← | `{"type": "ready", "id", "max_seconds"}` | Send MediaRecorder binary frames, then `{"type": "stop"}` |
| ← | `{"type": "error", "code", "detail"}` | Not started; the socket stays open. `code`: `busy`, `bad_request`, `unavailable` (no ffmpeg), `transcoder_error` |
| ← | `{"type": "live", "id", "user_id", "name", "url"}` | To everyone else: a talk started; play `url` |
| ← | `{"type": "ended", "id", "user_id", "reason", "clip"}` | To everyone: the talk ended (`stopped`, `disconnected`, `max_length`, `idle`, `too_large`, `transcoder_error`); `clip` is `null` when nothing was kept |
| → | `{"type": "ping"}` | Answered with `{"type": "pong"}` |

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
   These names only resolve inside the compose network, so run `cloudflared` from the compose file; a `cloudflared`
   installed on the host answers 502.
3. **Service.** `cp deploy/remote/.env.example deploy/remote/.env` (then `chmod 600`), fill it in
   (`PUBLIC_BASE_URL` = `https://speaker.example.com`, `MQTT_PASSWORD` = the `speaker-service` password,
   `CLOUDFLARE_TUNNEL_TOKEN`), then `docker compose -f deploy/remote/docker-compose.yml up -d --build`.
4. **Relay.** Flash `firmware/` to an ESP32 next to the speaker (see below) and set the broker to
   `wss://mqtt.example.com` with the `relay-1` login. The firmware trusts the public root CAs Cloudflare uses; no CA
   upload is needed. ESP8266 can't do MQTT over WebSocket.

The service's port is bound to the VM's loopback (`127.0.0.1:8090`) only. To reach the web UI other than through
the tunnel, use an SSH tunnel (`ssh -L 8090:127.0.0.1:8090 <vm>`).

A managed broker (HiveMQ Cloud, EMQX Cloud, ...) also works: point `MQTT_HOST`/`MQTT_PORT`/`MQTT_TLS` at it
instead of the `mosquitto` service, and give the relay its host, port 8883 and TLS.

Settings can also live in `config.json` (`"transport": "mqtt"`, an `mqtt` block, `public_base_url`).
The environment variables `SPEAKER_TRANSPORT`, `PUBLIC_BASE_URL`, `MQTT_HOST`, `MQTT_PORT`, `MQTT_TLS`,
`MQTT_CA_FILE`, `MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_BASE_TOPIC` and `MQTT_CLIENT_ID` override it and
are never written back to the file. The MQTT password is never returned by `/settings` (only `password_set`) or
written to the activity log.

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
- Without `public_base_url` the service falls back to its LAN address, which a remote speaker can't reach
  (a warning is printed at start-up).

### Backups and restore

The `backup` service in the same compose file saves the database and settings every night at
`BACKUP_TIME` (default `03:30`, UTC) and keeps the newest `BACKUP_KEEP` (default 14). It also takes one at
start-up when the newest is more than a day old (a VM that was off at night). Each backup is one file,
`speaker-YYYYMMDD-HHMMSS.tar.gz`, with `data.db` and `config.json`. The database is copied with SQLite's
online backup API while the service runs (it includes changes still in the WAL file; a plain file copy
can miss them or come out torn), and the copy must pass `PRAGMA integrity_check`. Backups live in the
`speaker-backups` volume, owner-only (files `0600`, folder `0700`): they hold password hashes, sessions
and the API token. The YouTube cache isn't backed up; it fills again by itself.

Why a compose service rather than a host cron job or systemd timer: it ships with the deployment, needs
nothing installed or configured on the VM, runs as the same user as the service (so it can read the
database and its WAL without root), and uses Python's `sqlite3` backup API from the same image. It
sleeps between runs.

```bash
C="docker compose -f deploy/remote/docker-compose.yml"
$C logs backup                                      # "[backup] wrote speaker-....tar.gz" each night
$C exec backup python backup.py --list
$C exec backup python backup.py --now               # e.g. before an upgrade (counts toward BACKUP_KEEP)

# Copy them off the VM as well (a backup on the same disk doesn't survive losing the VM)
$C cp backup:/backups ./speaker-backups && chmod -R go-rwx ./speaker-backups
```

**Restore** (the service must be stopped, so nothing writes while the files are swapped):

```bash
$C stop speaker-service backup
$C run --rm --no-deps backup python backup.py --list
$C run --rm --no-deps backup python backup.py --restore speaker-20261030-033000.tar.gz
$C up -d speaker-service backup
```

`--restore` checks the backup's database first, then puts `data.db` and `config.json` back. The files it
replaces (and a leftover `data.db-wal`/`-shm`, which must not be replayed onto the restored database) are
kept next to them as `*.before-restore-<time>`; delete them once the service looks right. To restore from a
copy kept elsewhere (e.g. on a new VM), first put it into the volume, then restore as above:

```bash
$C build
$C run --rm --no-deps -T backup sh -c 'umask 077; cat > /backups/speaker-20261030-033000.tar.gz' \
  < speaker-20261030-033000.tar.gz
```

`deploy/remote/.env` and the broker's `mosquitto/passwd` and `acl` are files on the VM, not in a volume;
keep your own copy of them (they hold secrets, so not in git).

## ESP32 relay firmware

`firmware/` turns an ESP32 or ESP8266 into the LAN-side helper: it receives commands over HTTP or MQTT and drives
the Cast speaker. The board never handles audio; it tells the speaker which URL to play. Full details are in
[firmware/README.md](firmware/README.md). In short:

- Build and flash with [PlatformIO](https://platformio.org/install/cli): `cd firmware && pio run -e esp32dev -t upload`
  (or `-e esp32-s3`, `-e esp8266`); `pio test -e native` runs the codec tests on your computer.
- Use an ESP32 for anything over the internet. ESP8266 has no RAM for MQTT over TLS and can't do MQTT over
  WebSocket; use it only with plain MQTT on a trusted LAN or VPN.
- First boot opens an access point **SpeakerRelay-XXXX**. Join it, open the setup page, enter the 2.4 GHz Wi-Fi
  (same network as the speaker) and, optionally, the broker (a host name, or a `wss://host/path` URL), and copy the
  API token shown on the page. Hold **BOOT** for 3 s while powering on to wipe settings.
- The same JSON commands work over HTTP (`/api/status`, `/api/play`, `/api/volume`, `/api/pause`, `/api/resume`,
  `/api/stop`, with the board's Bearer token) and MQTT (`{"cmd": ...}` on `<base>/cmd`; results on `<base>/result`,
  retained status on `<base>/status`, last will on `<base>/online`). `<base>` defaults to
  `speaker-relay/<device-name>`; set the service's `mqtt.base_topic` to match.

## Notes

- **The service speaks plain HTTP (no TLS).** The token travels unencrypted on the LAN. To use it from outside
  your home, go through a VPN or an HTTPS tunnel. Don't expose port 8090 to the internet directly.
- If the speaker can't be reached (different network, speaker off, IP changed), the API answers `503` within
  about 10 seconds.
- `volume` in request bodies is always optional.
- `say` interrupts YouTube the service is playing and resumes it afterwards (several announcements in a row are
  fine). If `stop`, `youtube` or `play` is called in between, the old track doesn't come back.
- Other apps playing on the speaker (e.g. Spotify) stop and don't resume.
- YouTube audio is downloaded into `cache/` (the newest `cache_keep`, default 20, are kept), because YouTube doesn't
  allow proxying the stream directly.
- **YouTube ads:** the service downloads only the audio stream (`YT_FORMAT`) with yt-dlp, so ads YouTube inserts are
  never played. What can remain are sponsor segments the creator speaks inside the video. Set `yt_skip_segments`
  (owner-only speaker settings page) and yt-dlp fetches the segments from SponsorBlock (sponsor.ajay.app, a public
  database), then cuts them with ffmpeg after the download. The cache file name carries a tag of the cut categories
  (`<id>.sb-<hash>.m4a`), so changing the categories downloads tracks again. Without ffmpeg, or when SponsorBlock
  can't be reached, tracks play at full length as before.
- **Tracks cached before SponsorBlock** (`<id>.m4a`) aren't downloaded again (for the queue and playlists, and for
  `POST /youtube` when the video can be identified before downloading). The old file plays at once, then a
  background job (one track at a time, `nice`) asks SponsorBlock using the first 4 characters of the SHA-256 of
  the id (as yt-dlp does, so the API doesn't learn which track is played) and cuts the local file with ffmpeg
  (stream copy, re-encoding only when needed) into `<id>.sb-<hash>.m4a`. The next play uses the cut file. When
  there is nothing to cut, a hard link with the new name is made so it isn't asked again. A failure is retried on
  the next play. The old file isn't deleted right away (the speaker may still be playing it) but ages out with
  `cache_keep`. The API can be changed with `SPONSORBLOCK_API`.
- yt-dlp needs Node.js for YouTube's JavaScript challenges. If playback stops working one day, update it:
  `./.venv/bin/pip install -U "yt-dlp[default]"`
- TTS uses an undocumented Google Translate endpoint, which may change or be rate-limited.

## Troubleshooting

| Symptom | Check |
|---|---|
| `503` from speaker endpoints | Speaker is off, on another network, or its IP changed. Use "Find" in Settings or `GET /speakers`. With `transport: mqtt`, check the relay (`relay` in `/status` as admin) |
| Speaker gets the command but plays nothing | The speaker can't fetch the media link. Set `public_base_url` to an address the speaker can reach |
| YouTube fails | Update yt-dlp (`./.venv/bin/pip install -U "yt-dlp[default]"`) and check Node.js is installed |
| Live talk unavailable (`4503`) | Install ffmpeg or set `FFMPEG` |
| Passkeys missing from the sign-in page | `public_base_url` must be `https://` (or `http://localhost`) and the page must be opened through it |
| `403 Missing header X-Requested-With` | Cookie requests that change data must send `X-Requested-With: speaker-web` |
| Lost access to every account | The API token always has admin rights: `./speakerctl token` |
| Tunnel answers 502 (VM) | `cloudflared` must run from the compose file, not on the host |
| Logs | macOS: `./speakerctl logs` · Docker: `docker compose -f deploy/remote/docker-compose.yml logs speaker-service` |

## Project layout

```
app.py                 FastAPI service: TTS, YouTube cache, queue, schedules, settings, the whole API
talk.py                Live talk: ffmpeg converts the microphone to an MP3 stream; chime sounds
transport.py           How the speaker is driven: Cast directly (pychromecast) or the ESP32 relay over MQTT
auth.py                Passwords (scrypt), session tokens, failed sign-in throttling
google_signin.py       Checks "Sign in with Google" ID tokens (signature, aud, iss, exp)
passkeys.py            Passkeys (WebAuthn): RP from public_base_url, single-use challenges, response checks
store.py               SQLite: users, sessions, playlists, quick phrases, schedules, radio favourites, uploads, activity log
player.py              Queue (play order, shuffle, repeat)
static/                Web UI
speakerctl             Manages the macOS LaunchAgent
deploy/                LaunchAgent template · deploy/remote/ = Docker Compose for a VM (service + Mosquitto + cloudflared + nightly backup)
tests/                 pytest with a fake speaker (no real speaker needed)
firmware/              ESP32 / ESP8266 firmware (PlatformIO), the LAN-side relay to the speaker
config.example.json    Example settings (copied to config.json)
```

## Contributing

Issues and pull requests are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) first (PRs go to the `dev` branch).
Report security problems as described in [SECURITY.md](SECURITY.md). Everyone follows the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Disclaimer

This is an independent project. It is not affiliated with, endorsed by, or sponsored by Xiaomi, Google or YouTube;
their names are used only to describe compatibility. YouTube playback uses yt-dlp and is subject to YouTube's Terms of Service;
use it for content you are allowed to play. The TTS endpoint is an unofficial Google Translate endpoint and may change or stop working.

## License

[MIT](LICENSE) © 2026 Jackson Tae
