"""HTTP service that makes a Google Cast speaker announce text and play YouTube audio, internet radio,
podcast episodes and uploaded audio files.

The speaker fetches every stream from this service (TTS and YouTube are proxied). The service
drives the speaker directly over Cast on the LAN, or through the ESP32 relay (firmware/) over MQTT
when it runs elsewhere; see transport.py. Media URLs then go out under `public_base_url`.

Operators can also talk through the speaker live from the browser's microphone (WebSocket /talk, see talk.py).

Callers authenticate with either `Authorization: Bearer <api_token>` (acts as admin) or the
`sid` session cookie of a web account (admin, operator or viewer). The speaker cannot send
headers, so the media URLs handed to it are signed with an HMAC of the token instead.
"""
import asyncio
import email.utils
import hashlib
import hmac
import html
import ipaddress
import itertools
import json
import mimetypes
import os
import random
import re
import secrets
import socket
import time
import urllib.parse
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Annotated, Literal
from xml.etree import ElementTree
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
import pychromecast.discovery
import yt_dlp
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator

import talk
from auth import (
    DUMMY_HASH,
    PASSWORD_MAX,
    PASSWORD_MIN,
    ROLE_RANK,
    Throttle,
    hash_password,
    new_session_token,
    normalize_username,
    token_hash,
    verify_password,
)
from google_signin import GoogleVerifier, InvalidToken, KeysUnavailable
from passkeys import (
    Challenges,
    PasskeyError,
    authentication_options,
    b64url_decode,
    challenge_of,
    new_user_handle,
    registration_options,
    relying_party,
    verify_authentication,
    verify_registration,
)
from player import Queue
from store import SESSION_TTL, Conflict, Store
from transport import SPEAKER_ERRORS, TransportError, make_transport

ROOT = Path(__file__).parent
CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", ROOT / "config.json"))
DATA_PATH = Path(os.environ.get("DATA_PATH", ROOT / "data.db"))
STATIC_DIR = ROOT / "static"
TTS_CHUNK = 180  # Google Translate TTS rejects queries longer than ~200 chars
YT_FORMAT = os.environ.get("YT_FORMAT", "bestaudio[ext=m4a]/bestaudio")
CACHE_DIR = Path(os.environ.get("CACHE_DIR", ROOT / "cache"))
CACHE_DIR.mkdir(exist_ok=True)
RESUME_REWIND = 1.0  # seconds replayed before the interruption point
RESUME_TIMEOUT = 300  # give up resuming if an announcement runs longer than this
MEDIA_URL_TTL = 6 * 3600  # signed media links stay valid long enough to resume a track
SESSION_COOKIE = "sid"
SESSION_REFRESH = 3600  # extend a session (and re-send the cookie) at most once an hour
QUEUE_POLL = 1.0  # seconds between checks for the end of a queue track
QUEUE_BACKOFF = 10.0  # wait after the speaker failed to answer a poll
MAX_PLAYLIST_ITEMS = 500
TTS_TEXT_MAX = 1000
VOLUME_COALESCE = 10  # at most one volume entry per actor in this many seconds
SCHEDULE_POLL = 15.0  # seconds between checks for due schedules
SCHEDULE_GRACE = timedelta(minutes=5)  # a schedule overdue by more than this (service was down) is skipped
SCHEDULE_NAME_MAX = 80
YT_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")
GOOGLE_CLIENT_ID_RE = re.compile(r"[A-Za-z0-9.-]+\.apps\.googleusercontent\.com")
TIME_RE = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
AUDIO_SUFFIXES = {".m4a", ".webm", ".mp3", ".opus", ".ogg", ".mp4", ".aac"}
MEDIA_DIR = Path(os.environ.get("MEDIA_DIR", DATA_PATH.parent / "media"))  # uploaded audio ("My files")
UPLOAD_MAX = int(os.environ.get("UPLOAD_MAX_MB", "50")) * 1024 * 1024  # per file
UPLOAD_QUOTA = int(os.environ.get("UPLOAD_QUOTA_MB", "2000")) * 1024 * 1024  # all uploads together
UPLOAD_TITLE_MAX = 200
# Uploads are recognised by their first bytes (name and Content-Type aren't trusted) and stored with
# this extension; the value is the content type the speaker is told.
FILE_TYPES = {
    ".mp3": "audio/mpeg", ".aac": "audio/aac", ".m4a": "audio/mp4", ".ogg": "audio/ogg", ".wav": "audio/wav",
    ".flac": "audio/flac", ".webm": "audio/webm",
}
RADIO_API = os.environ.get("RADIO_BROWSER_URL", "https://all.api.radio-browser.info").rstrip("/")
RADIO_CODECS = {"MP3": "audio/mpeg", "AAC": "audio/aac", "AAC+": "audio/aac", "OGG": "audio/ogg",
                "OPUS": "audio/ogg", "FLAC": "audio/flac"}
PODCAST_SEARCH = os.environ.get("PODCAST_SEARCH_URL", "https://itunes.apple.com/search")
FEED_MAX = 10 * 1024 * 1024  # bytes of RSS we read at most
FEED_REDIRECTS = 5
EPISODES_MAX = 200
USER_AGENT = "speaker-service/0.2"  # radio-browser asks clients to identify themselves
STATION_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
ITUNES_NS = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
TALK_START_TIMEOUT = 10.0  # seconds a new /talk connection has to send its start message
TALK_IDLE_TIMEOUT = 10.0  # end a talk when no audio arrives for this long
TALK_TICK = 0.5  # how often the talk loop checks its timers while waiting for the next message
TALK_DRAIN = 3.0  # seconds ffmpeg gets to flush after the talk ends before it is killed
TALK_SPEAKER_WAIT = 15.0  # at the end, wait this long for a speaker command still in flight
TALK_CHIME_WAIT = 5.0  # longest wait for the opening chime to finish
TALK_END_WAIT = 20.0  # longest wait for the speaker to play out the stream before the closing chime
TALK_POLL = 0.3
TALK_GRACE = 60.0  # an ended talk's stream stays fetchable this long (a slow speaker still gets it all)
TALK_MAX_RATE = 64 * 1024  # bytes/s of recorder input accepted on average (Opus/AAC use a fraction)


class MqttSettings(BaseModel):
    """Broker the ESP32 relay listens on (transport "mqtt"). Secrets may come from the environment instead."""
    host: str | None = None
    port: int = Field(8883, ge=1, le=65535)
    tls: bool = True
    ca_file: str | None = None  # PEM bundle to trust; None = the system's CAs (fine for managed brokers)
    username: str | None = None
    password: str | None = Field(None, repr=False)
    base_topic: str = "speaker-relay/speaker-relay"  # the relay's <base>; its default is speaker-relay/<device-name>
    client_id: str | None = None  # None = random; must differ from the relay's own id (its device name)
    keepalive: int = Field(60, ge=10, le=600)
    offline_after: float = Field(90, ge=5)  # relay counts as offline after this long without a message
    status_refresh: float = Field(2.0, ge=0.5)  # ask the relay for fresh state when ours is older than this
    command_timeout: float = Field(10, gt=0)
    play_timeout: float = Field(45, gt=0)  # a cold start on the speaker can take ~40 s
    reconnect_min: float = Field(1, gt=0)
    reconnect_max: float = Field(60, gt=0)

    @field_validator("host", "username", "ca_file", "client_id")
    @classmethod
    def blank_is_none(cls, v):
        return (v.strip() or None) if isinstance(v, str) else v

    @field_validator("password")
    @classmethod
    def empty_password_is_none(cls, v):
        return v or None  # spaces are legal in passwords, so no strip

    @field_validator("base_topic")
    @classmethod
    def check_topic(cls, v):
        v = v.strip().strip("/")
        if not v or any(c in v for c in "+#\0"):
            raise ValueError("base_topic must be a non-empty topic without wildcards (+ #)")
        return v

    @model_validator(mode="after")
    def check_backoff(self):
        if self.reconnect_max < self.reconnect_min:
            raise ValueError("reconnect_max must be at least reconnect_min")
        return self


class Settings(BaseModel):
    transport: Literal["cast", "mqtt"] = "cast"  # cast: speaker on this LAN; mqtt: through the ESP32 relay
    speaker_ip: str = "192.0.2.10"
    speaker_name: str = "Air Purifier speaker"
    port: int = Field(8090, ge=1024, le=65535)
    default_volume: float | None = Field(None, ge=0, le=1)  # None = keep the speaker's volume
    tts_lang: str = "th"
    cache_keep: int = Field(20, ge=1)  # most recent YouTube tracks kept on disk
    resume_after_say: bool = True  # continue the interrupted YouTube track after /say
    talk_max_seconds: int = Field(120, ge=10, le=600)  # a live talk ends after this long
    # Base of the signed media URLs given to the speaker, e.g. a Cloudflare Tunnel hostname.
    # None = this machine's LAN address (only works when the speaker is on the same LAN).
    public_base_url: str | None = None
    api_token: str | None = None  # Bearer token for the control API; generated on first run, never served
    mqtt: MqttSettings = Field(default_factory=MqttSettings)
    # OAuth client id (Google Cloud console, type "Web application") for Sign in with Google. Not a secret.
    google_client_id: str | None = None
    google_signin: bool = False  # the owner's switch; members still have to link their Google account first
    # Passkeys work only when public_base_url is https:// (or http://localhost); its host is the RP ID.
    passkey_signin: bool = True
    passkey_required_for_admins: bool = False  # admins who have a passkey can't sign in any other way

    @field_validator("public_base_url")
    @classmethod
    def check_base_url(cls, v):
        if v is None or not v.strip():
            return None
        v = v.strip().rstrip("/")
        parts = urllib.parse.urlsplit(v)
        if parts.scheme not in ("http", "https") or not parts.netloc or parts.query or parts.fragment:
            raise ValueError("public_base_url must be an http(s) URL like https://speaker.example.com")
        return v

    @field_validator("google_client_id")
    @classmethod
    def check_google_client_id(cls, v):
        if v is None or not v.strip():
            return None
        v = v.strip()
        if not GOOGLE_CLIENT_ID_RE.fullmatch(v):
            raise ValueError("google_client_id must look like 1234-abc.apps.googleusercontent.com")
        return v

    @model_validator(mode="after")
    def check_transport(self):
        if self.transport == "mqtt" and not self.mqtt.host:
            raise ValueError("transport \"mqtt\" needs mqtt.host (config or MQTT_HOST)")
        return self

    @model_validator(mode="after")
    def check_google(self):
        if self.google_signin and not self.google_client_id:
            raise ValueError("google_signin needs google_client_id")
        return self


# Environment variables that override config.json (handy for secrets in Docker). Never written back to disk.
ENV_OVERRIDES = {
    "SPEAKER_TRANSPORT": ("transport",),
    "PUBLIC_BASE_URL": ("public_base_url",),
    "MQTT_HOST": ("mqtt", "host"),
    "MQTT_PORT": ("mqtt", "port"),
    "MQTT_TLS": ("mqtt", "tls"),
    "MQTT_CA_FILE": ("mqtt", "ca_file"),
    "MQTT_USERNAME": ("mqtt", "username"),
    "MQTT_PASSWORD": ("mqtt", "password"),
    "MQTT_BASE_TOPIC": ("mqtt", "base_topic"),
    "MQTT_CLIENT_ID": ("mqtt", "client_id"),
}


def _env_overrides(environ=None):
    environ = os.environ if environ is None else environ
    return {path: environ[name] for name, path in ENV_OVERRIDES.items() if environ.get(name, "") != ""}


def _with_overrides(data, overrides):
    data = json.loads(json.dumps(data))  # deep copy
    for path, value in overrides.items():
        node = data
        for key in path[:-1]:
            node = node.setdefault(key, {})
        node[path[-1]] = value
    return data


def load_settings(environ=None):
    data = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    s = Settings(**_with_overrides(data, _env_overrides(environ)))
    if not s.api_token:
        s.api_token = secrets.token_urlsafe(32)
        save_settings(s, environ)
    if s.transport == "mqtt" and not s.public_base_url:
        print("warning: transport is mqtt but public_base_url is unset; the speaker gets LAN media URLs")
    if s.mqtt.username and not s.mqtt.tls:
        print("warning: MQTT credentials are sent without TLS (mqtt.tls is false)")
    return s


def save_settings(s, environ=None):
    """Write config.json, keeping what the file had for values that came from the environment."""
    on_disk = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    data = s.model_dump()
    for path in _env_overrides(environ):
        node, disk = data, on_disk
        for key in path[:-1]:
            node, disk = node[key], disk.get(key) if isinstance(disk.get(key), dict) else {}
        if path[-1] in disk:
            node[path[-1]] = disk[path[-1]]
        else:
            node.pop(path[-1], None)
    CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    CONFIG_PATH.chmod(0o600)  # holds the API token (and maybe the MQTT password)


def public_settings(s):
    data = s.model_dump(exclude={"api_token"})
    data["mqtt"]["password_set"] = bool(data["mqtt"].pop("password"))
    return data


def merge_settings(current, changes):
    """Partial update; `mqtt` merges field by field so a change doesn't wipe the stored password."""
    data = current.model_dump()
    for key, value in changes.items():
        if key == "mqtt" and isinstance(value, dict):
            data["mqtt"] = {**data["mqtt"], **value}
        else:
            data[key] = value
    return Settings(**data)


def describe_changes(changes):
    """Settings changes for the activity log, with secrets masked."""
    parts = []
    for key, value in changes.items():
        if key == "mqtt" and isinstance(value, dict):
            parts += [f"mqtt.{k}={'***' if k == 'password' else v}" for k, v in value.items()]
        else:
            parts.append(f"{key}={value}")
    return ", ".join(parts)[:500]


def local_zone():
    """The server's zone: $TZ, else the system zone (/etc/localtime), else UTC."""
    name = os.environ.get("TZ", "").lstrip(":")
    if not name:
        match = re.search(r"zoneinfo[^/]*/(.+)$", os.path.realpath("/etc/localtime"))
        name = match[1] if match else "UTC"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        print(f"unknown time zone {name!r}; schedules use UTC")
        return ZoneInfo("UTC")


settings = load_settings()
transport = make_transport(settings)
db = Store(DATA_PATH)
login_throttle = Throttle(limit=5, window=300)
google_verifier = GoogleVerifier()
passkey_challenges = Challenges()
ZONE = local_zone()


@asynccontextmanager
async def lifespan(_app):
    transport.start()  # the mqtt transport connects to the broker here; cast connects on first use
    runner = asyncio.create_task(schedule_loop())
    try:
        yield
    finally:
        runner.cancel()
        if _talk is not None:
            _talk.transcoder.kill()  # never leave an ffmpeg behind
        transport.close()


app = FastAPI(title="Speaker Service", lifespan=lifespan)
http = httpx.AsyncClient(timeout=30, follow_redirects=True)
# For URLs users type in (podcast feeds): redirects are followed by hand so each hop is checked first.
feed_http = httpx.AsyncClient(timeout=20, follow_redirects=False)
cast_lock = asyncio.Lock()
bearer = HTTPBearer(auto_error=False, description="The api_token from config.json (`./speakerctl token`)")


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    """Keep `detail` a readable string, like every other error."""
    messages = []
    for err in exc.errors():
        where = ".".join(str(p) for p in err["loc"] if p not in ("body", "query", "path"))
        messages.append(f"{where}: {err['msg']}" if where else err["msg"])
    return JSONResponse({"detail": "; ".join(messages) or "Invalid request"}, status_code=422)


# --- Who is calling ---

@dataclass
class Principal:
    role: str
    actor: str  # name recorded in the activity log
    user: dict | None = None  # None for the API token
    session: str | None = None  # sha256 of the sid cookie


def unauthorized(detail):
    return HTTPException(401, detail, headers={"WWW-Authenticate": "Bearer"})


def set_session_cookie(request, response, sid):
    response.set_cookie(
        SESSION_COOKIE, sid, max_age=SESSION_TTL, path="/", httponly=True, samesite="strict",
        secure=request.url.scheme == "https",
    )


def clear_session_cookie(request, response):
    response.delete_cookie(
        SESSION_COOKIE, path="/", httponly=True, samesite="strict", secure=request.url.scheme == "https"
    )


def authenticate(
    request: Request, response: Response, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
):
    """The API token (admin), a web session, or None."""
    if creds is not None:
        if not secrets.compare_digest(creds.credentials.encode(), settings.api_token.encode()):
            raise unauthorized("Missing or invalid API token")
        return Principal("admin", "api-token")
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid:
        return None
    digest = token_hash(sid)
    user, expires_at = db.session_user(digest)
    if user is None:
        return None
    # SameSite=Strict plus a header a cross-site form can't send.
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-requested-with") != "speaker-web":
        raise HTTPException(403, "Missing header X-Requested-With: speaker-web")
    if expires_at - time.time() < SESSION_TTL - SESSION_REFRESH:
        db.touch_session(digest)
        set_session_cookie(request, response, sid)
    return Principal(user["role"], user["display_name"], user, digest)


Caller = Annotated[Principal | None, Depends(authenticate)]


def require(role):
    def check(who: Caller):
        if who is None:
            raise unauthorized("Not signed in")
        if ROLE_RANK[who.role] < ROLE_RANK[role]:
            raise HTTPException(403, f"This needs the {role} role")
        return who

    check.role = role  # read by the role-matrix test
    return check


require_viewer, require_operator, require_admin = require("viewer"), require("operator"), require("admin")
SignedIn = Annotated[Principal, Depends(require_viewer)]
Who = Annotated[Principal, Depends(authenticate)]  # inside a role-guarded router, never None

viewer_api = APIRouter(dependencies=[Depends(require_viewer)])
operator_api = APIRouter(dependencies=[Depends(require_operator)])
admin_api = APIRouter(dependencies=[Depends(require_admin)])


def record(who, action, detail=None, coalesce=0):
    db.log(who.actor if who else "system", action, detail, coalesce)


# --- Signed media links ---

def _media_sig(path, params):
    payload = path + "?" + urllib.parse.urlencode(sorted(params.items()))
    return hmac.new(settings.api_token.encode(), payload.encode(), hashlib.sha256).hexdigest()


def media_url(path, **params):
    """A URL the speaker can fetch without a header: signed with the API token and time-limited."""
    params = {k: str(v) for k, v in params.items()}
    params["exp"] = str(int(time.time()) + MEDIA_URL_TTL)
    params["sig"] = _media_sig(path, params)
    return f"{base_url()}{path}?{urllib.parse.urlencode(params)}"


def verify_media(request: Request):
    params = dict(request.query_params)
    sig, exp = params.pop("sig", ""), params.get("exp", "")
    expired = not exp.isdigit() or int(exp) < time.time()
    if expired or not hmac.compare_digest(sig, _media_sig(request.url.path, params)):
        raise HTTPException(403, "Invalid or expired media link")


def content_type_for(path):
    return {".webm": "audio/webm", ".mp3": "audio/mpeg"}.get(path.suffix, "audio/mp4")


def host_ip():
    """The LAN address the speaker can use to reach this machine."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((settings.speaker_ip, 8009))
        return s.getsockname()[0]


def base_url():
    return settings.public_base_url or f"http://{host_ip()}:{settings.port}"


# --- Speaker ---

def cast_play(url, content_type, title=None, volume=None, current_time=None, keep_volume=False, live=False):
    if volume is None and not keep_volume:
        volume = settings.default_volume
    transport.play(url, content_type, title, volume, current_time, live=live)


# --- Resume YouTube after an announcement ---

_resume = None  # track interrupted by an announcement: {"url", "content_type", "title", "position", "live"}
_say_gen = 0  # bumped by every play action so stale resume watchers give up
_direct = None  # radio station, podcast episode or file started outside the queue: {"url", "live", "thumbnail"}


def capture_youtube():
    """Snapshot the YouTube track, queue item or other source this service is playing, if any."""
    m = transport.media()
    content_id = m.content_id or ""
    from_queue = _queue is not None and content_id == _queue.current_url
    from_direct = _direct is not None and content_id == _direct["url"]
    if not (content_id.startswith(f"{base_url()}/yt/") or from_queue or from_direct):
        return None
    if m.player_state not in ("PLAYING", "BUFFERING"):
        return None
    live = (from_queue and _queue.current["kind"] == "radio") or (from_direct and _direct["live"])
    return {
        "url": m.content_id,
        "content_type": m.content_type,
        "title": m.title,
        "position": None if live else max(0.0, m.adjusted_current_time - RESUME_REWIND),
        "live": live,
    }


def cancel_resume():
    global _resume, _say_gen
    _resume = None
    _say_gen += 1


async def resume_after_announcement(gen, tts_prefix):
    global _resume
    try:
        await _watch_and_resume(gen, tts_prefix)
    except HTTPException as e:  # speaker went away mid-announcement; drop the resume
        _resume = None
        print(f"resume skipped: {e.detail}")


async def _watch_and_resume(gen, tts_prefix):
    global _resume
    loop = asyncio.get_running_loop()
    deadline = loop.time() + RESUME_TIMEOUT
    while loop.time() < deadline:
        await asyncio.sleep(0.5)
        if gen != _say_gen:
            return  # a newer action took over
        m = await run_cast(transport.media)
        content_id = m.content_id or ""
        if _resume and content_id == _resume["url"]:
            continue  # status hasn't switched to the announcement yet
        if not content_id.startswith(tts_prefix):
            _resume = None  # something else was cast meanwhile; don't override it
            return
        if m.player_state == "IDLE":
            break
    track, _resume = _resume, None
    if track and gen == _say_gen:
        await run_cast(cast_play, track["url"], track["content_type"], track["title"], None, track["position"],
                       live=track.get("live", False))


async def run_cast(fn, *args, **kwargs):
    async with cast_lock:
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except TransportError as e:
            raise HTTPException(503, str(e)) from e
        except SPEAKER_ERRORS as e:
            detail = f"Speaker {settings.speaker_ip} is not responding ({type(e).__name__}); is it on the same network?"
            raise HTTPException(503, detail) from e


def split_text(text, size=TTS_CHUNK):
    chunks, current = [], ""
    for word in text.split():
        while len(word) > size:  # Thai has no spaces, so long runs need a hard cut
            if current:
                chunks.append(current)
                current = ""
            chunks.append(word[:size])
            word = word[size:]
        if len(current) + len(word) + 1 > size:
            chunks.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        chunks.append(current)
    return chunks


# --- YouTube ---

def yt_download(query):
    """Download the audio track into CACHE_DIR; googlevideo rejects proxied Range requests."""
    target = query if query.startswith(("http://", "https://")) else f"ytsearch1:{query}"
    opts = {
        "format": YT_FORMAT,
        "outtmpl": str(CACHE_DIR / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "js_runtimes": {"node": {}},
        "retries": 5,
        "extractor_retries": 3,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(target, download=True)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(502, f"YouTube download failed: {e.msg or e}") from e
    if "entries" in info:
        if not info["entries"]:
            raise HTTPException(404, f"No YouTube result for {query!r}")
        info = info["entries"][0]
    path = Path(info["requested_downloads"][0]["filepath"])
    return {"id": info["id"], "title": info.get("title"), "duration": info.get("duration"), "path": path}


def yt_thumbnail(video_id):
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def yt_watch_url(video_id):
    return f"https://www.youtube.com/watch?v={video_id}"


def yt_extract(target):
    """yt-dlp metadata only (no download); search results stay flat so they come back fast."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "js_runtimes": {"node": {}},
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(target, download=False)


def yt_entry(entry):
    duration = entry.get("duration")
    return {
        "video_id": entry["id"],
        "title": entry.get("title") or entry["id"],
        "duration": float(duration) if duration else None,
        "channel": entry.get("channel") or entry.get("uploader"),
        "thumbnail": yt_thumbnail(entry["id"]),
    }


def yt_search(query, limit=8):
    try:
        info = yt_extract(f"ytsearch{limit}:{query}")
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(502, f"YouTube search failed: {e.msg or e}") from e
    return [yt_entry(e) for e in info.get("entries") or [] if e and YT_ID_RE.fullmatch(e.get("id") or "")]


def yt_info(query):
    """Metadata for one video from a YouTube URL, a video id, or search words (first result)."""
    query = query.strip()
    if YT_ID_RE.fullmatch(query):
        try:
            return yt_entry(yt_extract(yt_watch_url(query)))
        except (yt_dlp.utils.DownloadError, KeyError):
            pass  # eleven characters but not a video id: search for the words instead
    target = query if query.startswith(("http://", "https://")) else f"ytsearch1:{query}"
    try:
        info = yt_extract(target)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(502, f"YouTube lookup failed: {e.msg or e}") from e
    if "entries" in info:
        entries = [e for e in info["entries"] or [] if e]
        if not entries:
            raise HTTPException(404, f"No YouTube result for {query!r}")
        info = entries[0]
    if not YT_ID_RE.fullmatch(info.get("id") or ""):
        raise HTTPException(400, "Not a YouTube video")
    return yt_entry(info)


def cached_track(video_id):
    for path in CACHE_DIR.glob(f"{video_id}.*"):
        if path.stem == video_id and path.suffix in AUDIO_SUFFIXES:
            return path
    return None


def prune_cache(protect=()):
    files = sorted(CACHE_DIR.glob("*.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[settings.cache_keep:]:
        if old.name not in protect:
            old.unlink(missing_ok=True)


# --- Play queue ---

_queue: Queue | None = None
_queue_gen = 0  # bumped whenever the queue moves or is replaced, so stale loads give up
_downloads = {}  # video id -> download task, so a prefetch and a play never download the same file twice
_background = set()
_watcher = None
_nonce = itertools.count()  # makes every queue load's URL unique, even a repeated track


def spawn(coro):
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task


def clear_queue():
    """Forget the queue (and a direct radio/podcast/file play): something else is about to play."""
    global _queue, _queue_gen, _direct
    _queue = None
    _queue_gen += 1
    _direct = None


def end_queue(q):
    if _queue is q:
        clear_queue()


async def ensure_track(video_id):
    """Path of the cached audio for a video, downloading it at most once at a time."""
    path = cached_track(video_id)
    if path:
        path.touch()  # newest mtime keeps it out of prune_cache's way
        return path
    task = _downloads.get(video_id)
    if task is None:
        task = asyncio.create_task(asyncio.to_thread(yt_download, yt_watch_url(video_id)))
        _downloads[video_id] = task
        task.add_done_callback(lambda _: _downloads.pop(video_id, None))
    return (await asyncio.shield(task))["path"]


async def queue_media(item):
    """(url, content_type) the speaker loads for a queue item."""
    nonce = next(_nonce)
    if item["kind"] == "youtube":
        path = await ensure_track(item["source"])
        return media_url(f"/yt/{path.name}", n=nonce), content_type_for(path)
    if item["kind"] == "tts":
        lang = item["lang"] or settings.tts_lang
        return media_url("/tts.mp3", text=item["source"], lang=lang, n=nonce), "audio/mp3"
    if item["kind"] == "file":
        row = db.get_file(int(item["source"])) if item["source"].isdigit() else None
        if row is None or not (MEDIA_DIR / row["stored_name"]).is_file():
            raise HTTPException(404, "The uploaded file is gone")
        return media_url(f"/media/{row['stored_name']}", n=nonce), row["content_type"]
    # url, radio and podcast items are fetched by the speaker straight from their source.
    return item["source"], item.get("content_type") or guess_audio_type(item["source"])


def guess_audio_type(url):
    """Content type from the URL's extension; the speaker copes with audio/mpeg for unknown streams."""
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    known = FILE_TYPES | {".mp4": "audio/mp4", ".opus": "audio/ogg", ".m3u8": "application/x-mpegurl"}
    guessed = known.get(suffix) or mimetypes.guess_type(urllib.parse.urlparse(url).path)[0]
    return guessed if guessed and guessed.startswith(("audio/", "application/x-mpegurl")) else "audio/mpeg"


async def prefetch(video_id):
    try:
        await ensure_track(video_id)
    except HTTPException as e:
        print(f"prefetch failed for {video_id}: {e.detail}")


def schedule_prefetch(q):
    item = q.peek_next()
    if item and item["kind"] == "youtube" and not cached_track(item["source"]):
        spawn(prefetch(item["source"]))


def skip_failed(q, reason):
    """Log and step past the current item. False when the queue should stop."""
    db.log("system", "queue skip", f"{q.current['title']}: {reason}")
    q.failures += 1
    return q.failures < len(q) and q.advance(auto=False)


def load_if_current(gen, url, content_type, title, keep_volume, live=False):
    if gen != _queue_gen:
        return False  # something else was cast while this load waited for the speaker
    cast_play(url, content_type, title, keep_volume=keep_volume, live=live)
    return True


async def play_queue(q, keep_volume=True):
    """Load the queue's current item, skipping ones that fail. False if the queue ran out instead."""
    global _queue_gen
    _queue_gen += 1
    gen = _queue_gen
    cancel_resume()
    while True:
        item = q.current
        try:
            url, content_type = await queue_media(item)
        except HTTPException as e:
            if gen != _queue_gen:
                return True  # superseded while downloading
            if skip_failed(q, e.detail):
                continue
            end_queue(q)
            return False
        live = item["kind"] == "radio"  # a station never ends; the queue stays on it until skipped
        if await run_cast(load_if_current, gen, url, content_type, item["title"], keep_volume, live):
            q.current_url, q.after_say = url, False
            schedule_prefetch(q)
            keep = {p.name for i in (q.current, q.peek_next()) if i and i["kind"] == "youtube"
                    for p in [cached_track(i["source"])] if p}
            await asyncio.to_thread(prune_cache, keep)
        return True


async def queue_tick():
    """One check of the speaker: advance when the queue's own track has finished."""
    q, gen = _queue, _queue_gen
    if q is None:
        return
    m = await run_cast(transport.media)
    if q is not _queue or gen != _queue_gen or m.player_state != "IDLE":
        return
    content_id, reason = m.content_id or "", m.idle_reason
    if q.current_url and content_id == q.current_url:
        if reason == "ERROR":
            if not skip_failed(q, "the speaker could not play it"):
                end_queue(q)
                return
            await play_queue(q)
            return
        if reason != "FINISHED":
            return  # stopped or replaced from elsewhere: leave it alone
        q.failures = 0
    elif not (q.after_say and _resume is None and _talk_on_speaker is None
              and content_id.startswith((f"{base_url()}/tts.mp3", f"{base_url()}/talk/"))):
        return  # an announcement, a live talk (or something else) is playing; never advance on its end
    if q.advance(auto=True):
        await play_queue(q)
    else:
        end_queue(q)


async def queue_watch():
    while _queue is not None:
        await asyncio.sleep(QUEUE_POLL)
        try:
            await queue_tick()
        except HTTPException as e:
            print(f"queue: {e.detail}")
            await asyncio.sleep(QUEUE_BACKOFF)
        except Exception as e:  # keep the queue alive; one bad poll shouldn't stop auto-advance for good
            print(f"queue watcher error: {type(e).__name__}: {e}")
            await asyncio.sleep(QUEUE_BACKOFF)


def ensure_queue_watcher():
    global _watcher
    if _watcher is None or _watcher.done():
        _watcher = spawn(queue_watch())


def queue_after_say(q):
    """Whether the queue should move on once an announcement ends (its track won't be resumed)."""
    m = transport.media()
    if (m.content_id or "") != q.current_url:
        return q.after_say  # back-to-back announcements keep the earlier decision
    if m.player_state in ("PLAYING", "BUFFERING"):
        return True  # replaced without a resume (resume_after_say is off)
    return m.player_state == "IDLE" and m.idle_reason == "FINISHED"


def thumbnail_for(content_id):
    if _queue is not None and content_id and content_id == _queue.current_url:
        return _queue.current.get("thumbnail")
    if _direct is not None and content_id and content_id == _direct["url"]:
        return _direct["thumbnail"]
    match = re.match(re.escape(f"{base_url()}/yt/") + r"([A-Za-z0-9_-]{11})\.", content_id or "")
    return yt_thumbnail(match[1]) if match else None


# --- Request bodies ---

Role = Literal["admin", "operator", "viewer"]
Repeat = Literal["off", "all", "one"]


class SayBody(BaseModel):
    text: str
    lang: str | None = None  # defaults to settings.tts_lang
    volume: float | None = None


class PlayBody(BaseModel):
    url: str
    content_type: str = "audio/mp3"
    volume: float | None = None


class YoutubeBody(BaseModel):
    query: str  # search words or a YouTube URL
    volume: float | None = None


class VolumeBody(BaseModel):
    level: float


class SetupBody(BaseModel):
    api_token: str
    username: str
    display_name: str = ""
    password: str


class LoginBody(BaseModel):
    username: str
    password: str


class GoogleBody(BaseModel):
    credential: str = Field(max_length=8192)  # the ID token from Google Identity Services


class PasskeyBody(BaseModel):
    credential: dict  # the PublicKeyCredential from the browser, as JSON (base64url fields)
    name: str | None = None  # registration only; defaults to "Passkey"


class PasskeyName(BaseModel):
    name: str


class PasswordBody(BaseModel):
    current: str
    new: str


class NewUserBody(BaseModel):
    username: str
    display_name: str = ""
    password: str
    role: Role


class UserPatch(BaseModel):
    display_name: str | None = None
    role: Role | None = None
    password: str | None = None
    disabled: bool | None = None


class PlaylistBody(BaseModel):
    name: str


class ItemBody(BaseModel):
    """`source` per kind: youtube = URL/id/words, url/podcast = audio URL, tts = text,
    radio = radio-browser station uuid or stream URL, file = id of an uploaded file."""
    kind: Literal["youtube", "url", "tts", "radio", "podcast", "file"]
    source: str
    title: str | None = None
    lang: str | None = None
    thumbnail: str | None = None  # radio (stream URL) and podcast items
    duration: float | None = Field(None, ge=0)  # podcast items
    content_type: str | None = None  # radio (stream URL) and podcast items


class StationBody(BaseModel):
    """A radio-browser station (uuid) or a stream URL of your own (url + name)."""
    uuid: str | None = None
    url: str | None = None
    name: str | None = None
    content_type: str | None = None
    favicon: str | None = None


class RadioPlayBody(StationBody):
    favorite_id: int | None = None
    volume: float | None = Field(None, ge=0, le=1)


class EpisodePlayBody(BaseModel):
    url: str  # the episode's enclosure URL
    title: str
    thumbnail: str | None = None
    content_type: str | None = None
    volume: float | None = Field(None, ge=0, le=1)


class FilePatch(BaseModel):
    title: str


class FilePlayBody(BaseModel):
    volume: float | None = Field(None, ge=0, le=1)


class OrderBody(BaseModel):
    item_ids: list[int]


class PlayPlaylistBody(BaseModel):
    start_index: int = 0
    shuffle: bool = False
    repeat: Repeat = "off"


class JumpBody(BaseModel):
    index: int


class QueuePatch(BaseModel):
    shuffle: bool | None = None
    repeat: Repeat | None = None


class PhraseBody(BaseModel):
    text: str
    lang: str | None = None


class ScheduleBody(BaseModel):
    """POST takes the whole schedule, PATCH any subset; either way the result is validated as a whole."""
    name: str | None = None
    enabled: bool | None = None
    action: str | None = None
    text: str | None = None
    lang: str | None = None
    playlist_id: int | None = None
    shuffle: bool | None = None
    volume: float | None = None
    time: str | None = None
    days: list[int] | None = None
    date: str | None = None


def clean_text(value, field, max_len):
    value = value.strip()
    if not value:
        raise HTTPException(400, f"{field} is empty")
    if len(value) > max_len:
        raise HTTPException(400, f"{field} is longer than {max_len} characters")
    return value


def check_password(password):
    if not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        raise HTTPException(400, f"Password must be {PASSWORD_MIN}-{PASSWORD_MAX} characters")


def check_username(username):
    name = normalize_username(username)
    if name is None:
        raise HTTPException(400, "Username must be 3-32 characters of a-z, 0-9, '.', '_' or '-'")
    return name


def client_ip(request):
    return request.client.host if request.client else "unknown"


def throttled(key):
    wait = login_throttle.retry_after(key)
    if wait:
        raise HTTPException(429, f"Too many failed attempts; try again in {wait} s", headers={"Retry-After": str(wait)})
    login_throttle.fail(key)  # reserved before the slow hash check; cleared on success


def start_session(request, response, user_id):
    old = request.cookies.get(SESSION_COOKIE)
    if old:
        db.delete_session(token_hash(old))
    sid = new_session_token()
    db.create_session(token_hash(sid), user_id)
    db.mark_login(user_id)
    set_session_cookie(request, response, sid)
    return db.get_user(user_id)


def google_enabled():
    return settings.google_signin and bool(settings.google_client_id)


async def google_claims(credential, ip):
    """Verified claims of a Google ID token; failed attempts count against the IP like wrong passwords."""
    if not google_enabled():
        raise HTTPException(409, "Sign in with Google is turned off")
    key = (ip, "#google")
    throttled(key)
    try:
        claims = await asyncio.to_thread(google_verifier.verify, credential, settings.google_client_id)
    except KeysUnavailable as e:
        login_throttle.clear(key)  # not the caller's fault
        raise HTTPException(503, "Couldn't reach Google to check the sign-in; try again") from e
    except InvalidToken as e:
        db.log("system", "login failed", f"Google: {e} from {ip}"[:300], coalesce=VOLUME_COALESCE)
        raise HTTPException(401, "Google sign-in failed; try again") from e
    login_throttle.clear(key)
    return claims


def current_rp():
    """The passkey relying party, or None while passkeys are switched off or the origin can't use them."""
    return relying_party(settings.public_base_url, settings.speaker_name) if settings.passkey_signin else None


def passkey_rp():
    rp = current_rp()
    if rp is None:
        raise HTTPException(409, "Passkeys are off; they need passkey_signin and an https:// public_base_url")
    return rp


def passkey_policy_applies(user):
    return settings.passkey_required_for_admins and user["role"] == "admin" and current_rp() is not None


def refuse_without_passkey(user, ip, how):
    """Sign-ins other than a passkey call this: an admin with a passkey must use it while the owner requires it."""
    if passkey_policy_applies(user) and user["has_passkey"]:
        db.log("system", "login failed", f"{user['username']} ({how}) needs a passkey, from {ip}")
        raise HTTPException(403, "Owners sign in with a passkey")


def sign_in_methods(user):
    """The ways this member can sign in right now."""
    methods = set()
    if db.password_hash(user["id"]):
        methods.add("password")
    if user["google_email"] and google_enabled():
        methods.add("google")
    if user["has_passkey"] and current_rp() is not None:
        methods.add("passkey")
    return methods


# --- Accounts ---

@app.get("/auth/state")
async def auth_state(who: Caller):
    user = who.user if who else None
    state = {
        "needs_setup": db.user_count() == 0, "user": user,
        "methods": {"password": True, "google": google_enabled(), "passkey": current_rp() is not None},
    }
    if google_enabled():
        state["google_client_id"] = settings.google_client_id
    if user and passkey_policy_applies(user) and not user["has_passkey"]:
        state["passkey_required"] = True  # signed in with a password; the UI should ask for a passkey now
    return state


@app.post("/auth/setup")
async def auth_setup(body: SetupBody, request: Request, response: Response):
    if db.user_count():
        raise HTTPException(409, "Setup is already done; sign in instead")
    key = (client_ip(request), "#setup")
    throttled(key)
    if not secrets.compare_digest(body.api_token.encode(), settings.api_token.encode()):
        raise HTTPException(401, "Wrong API token")
    login_throttle.clear(key)
    username = check_username(body.username)
    display_name = clean_text(body.display_name or username, "display_name", 64)
    check_password(body.password)
    user = db.create_first_admin(username, display_name, await asyncio.to_thread(hash_password, body.password))
    if user is None:
        raise HTTPException(409, "Setup is already done; sign in instead")
    user = start_session(request, response, user["id"])
    db.log(user["display_name"], "login ok", "first-run setup")
    return {"user": user}


@app.post("/auth/login")
async def login(body: LoginBody, request: Request, response: Response):
    username, ip = body.username.strip().lower()[:64], client_ip(request)
    key = (ip, username)
    throttled(key)
    user, stored = db.credentials(username)
    ok = await asyncio.to_thread(verify_password, body.password, stored or DUMMY_HASH)
    if user is None:
        # Unknown names are coalesced so a flood of guesses can't push real history out of the log.
        db.log("system", "login failed", f"{username} from {ip}", coalesce=VOLUME_COALESCE)
        raise HTTPException(401, "Wrong username or password")
    if not ok or user["disabled"]:
        db.log("system", "login failed", f"{username} from {ip}")
        raise HTTPException(401, "This account is disabled" if ok else "Wrong username or password")
    login_throttle.clear(key)
    refuse_without_passkey(user, ip, "password")
    user = start_session(request, response, user["id"])
    db.log(user["display_name"], "login ok", f"from {ip}")
    return {"user": user}


@app.post("/auth/google")
async def login_google(body: GoogleBody, request: Request, response: Response):
    """Sign in with a linked Google account; there is no sign-up, so an unknown account is refused."""
    ip = client_ip(request)
    claims = await google_claims(body.credential, ip)
    user = db.user_by_google(claims["sub"])
    if user is None:
        db.log("system", "login failed", f"Google account {claims['email']} is not linked, from {ip}"[:300])
        raise HTTPException(401, "This Google account isn't linked to a member; sign in with your password and "
                                 "link it under Account first")
    if user["disabled"]:
        db.log("system", "login failed", f"{user['username']} (Google) from {ip}")
        raise HTTPException(401, "This account is disabled")
    refuse_without_passkey(user, ip, "Google")
    db.link_google(user["id"], claims["sub"], claims["email"])  # keep the shown email current
    user = start_session(request, response, user["id"])
    db.log(user["display_name"], "login ok", f"with Google from {ip}")
    return {"user": user}


@app.post("/auth/passkey/options")
async def passkey_login_options():
    """Options for navigator.credentials.get(); any passkey registered here may answer."""
    rp = passkey_rp()
    return {"publicKey": authentication_options(rp, passkey_challenges.issue("login"))}


@app.post("/auth/passkey/verify")
async def passkey_login(body: PasskeyBody, request: Request, response: Response):
    rp, ip = passkey_rp(), client_ip(request)
    key = (ip, "#passkey")
    throttled(key)
    credential = body.credential
    try:
        challenge = challenge_of(credential)
        passkey_challenges.take(challenge, "login")
        passkey = db.passkey_by_credential(str(credential.get("id", "")))
        if passkey is None:
            raise PasskeyError("This passkey isn't registered here")
        handle = (credential.get("response") or {}).get("userHandle")
        if handle and b64url_decode(str(handle)) != b64url_decode(passkey["user_handle"]):
            raise PasskeyError("This passkey belongs to another account")
        sign_count = await asyncio.to_thread(verify_authentication, rp, credential, challenge, passkey)
    except (PasskeyError, ValueError) as e:  # ValueError: a userHandle that isn't base64url
        db.log("system", "login failed", f"passkey: {e} from {ip}"[:300], coalesce=VOLUME_COALESCE)
        raise HTTPException(401, str(e)[:200]) from e
    user = db.get_user(passkey["user_id"])
    if user["disabled"]:
        db.log("system", "login failed", f"{user['username']} (passkey) from {ip}")
        raise HTTPException(401, "This account is disabled")
    login_throttle.clear(key)
    db.use_passkey(passkey["id"], sign_count)
    user = start_session(request, response, user["id"])
    db.log(user["display_name"], "login ok", f"with a passkey from {ip}")
    return {"user": user}


@app.post("/auth/logout")
async def logout(who: SignedIn, request: Request, response: Response):
    if who.session:
        db.delete_session(who.session)
    clear_session_cookie(request, response)
    record(who, "logout")
    return {"ok": True}


def account_of(who):
    if who.user is None:
        raise HTTPException(400, "The API token is not a user account")
    return who.user


@app.post("/auth/logout-all")
async def logout_all(who: SignedIn, request: Request, response: Response):
    db.delete_sessions(account_of(who)["id"])
    clear_session_cookie(request, response)
    record(who, "logout", "all sessions")
    return {"ok": True}


@app.post("/auth/password")
async def change_password(body: PasswordBody, who: SignedIn, request: Request):
    user = account_of(who)
    key = (client_ip(request), user["username"])
    throttled(key)
    if not await asyncio.to_thread(verify_password, body.current, db.password_hash(user["id"]) or DUMMY_HASH):
        raise HTTPException(401, "Current password is wrong")
    login_throttle.clear(key)
    check_password(body.new)
    db.update_user(user["id"], {"password_hash": await asyncio.to_thread(hash_password, body.new)})
    db.delete_sessions(user["id"], keep=who.session)
    record(who, "password change")
    return {"ok": True}


@app.post("/me/google")
async def link_google(body: GoogleBody, who: SignedIn, request: Request):
    user = account_of(who)
    claims = await google_claims(body.credential, client_ip(request))
    try:
        user = db.link_google(user["id"], claims["sub"], claims["email"])
    except Conflict as e:
        raise HTTPException(409, str(e)) from e
    record(who, "google link", claims["email"])
    return user


@app.delete("/me/google")
async def unlink_google(who: SignedIn):
    user = account_of(who)
    if not user["google_email"]:
        raise HTTPException(404, "No Google account is linked")
    if not sign_in_methods(user) - {"google"}:
        raise HTTPException(409, "This is your only way to sign in; set a password or add another method first")
    email = user["google_email"]
    user = db.unlink_google(user["id"])
    record(who, "google unlink", email)
    return user


@app.post("/me/passkeys/options")
async def passkey_register_options(who: SignedIn):
    """Options for navigator.credentials.create(); the member's existing passkeys are excluded."""
    user, rp = account_of(who), passkey_rp()
    handle, existing = db.passkey_handles(user["id"])
    handle = handle or new_user_handle()
    challenge = passkey_challenges.issue("register", user["id"], handle)
    return {"publicKey": registration_options(rp, challenge, handle, user["username"], user["display_name"], existing)}


@app.post("/me/passkeys")
async def add_passkey(body: PasskeyBody, who: SignedIn):
    user, rp = account_of(who), passkey_rp()
    name = clean_text(body.name or "Passkey", "name", 64)
    try:
        challenge = challenge_of(body.credential)
        handle = passkey_challenges.take(challenge, "register", user["id"])
        cred = await asyncio.to_thread(verify_registration, rp, body.credential, challenge)
    except PasskeyError as e:
        raise HTTPException(400, str(e)[:200]) from e
    try:
        passkey = db.add_passkey(user["id"], handle, name, cred)
    except Conflict as e:
        raise HTTPException(409, str(e)) from e
    record(who, "passkey add", name)
    return passkey


@app.get("/me/passkeys")
async def list_passkeys(who: SignedIn):
    return db.list_passkeys(account_of(who)["id"])


@app.patch("/me/passkeys/{passkey_id}")
async def rename_passkey(passkey_id: int, body: PasskeyName, who: SignedIn):
    name = clean_text(body.name, "name", 64)
    passkey = db.rename_passkey(account_of(who)["id"], passkey_id, name)
    if passkey is None:
        raise HTTPException(404, "No such passkey")
    record(who, "passkey rename", name)
    return passkey


@app.delete("/me/passkeys/{passkey_id}", status_code=204)
async def delete_passkey(passkey_id: int, who: SignedIn):
    user = account_of(who)
    names = {p["id"]: p["name"] for p in db.list_passkeys(user["id"])}
    if passkey_policy_applies(user):
        reason = "Owners must keep at least one passkey"
    elif not sign_in_methods(user) - {"passkey"}:
        reason = "This is your only way to sign in; set a password or add another method first"
    else:
        reason = None
    try:
        gone = db.delete_passkey(user["id"], passkey_id, keep_one=reason is not None)
    except Conflict as e:
        raise HTTPException(409, reason) from e
    if not gone:
        raise HTTPException(404, "No such passkey")
    record(who, "passkey remove", names.get(passkey_id))


# --- Members ---

@admin_api.get("/users")
async def list_users():
    return db.list_users()


@admin_api.post("/users")
async def create_user(body: NewUserBody, who: Who):
    username = check_username(body.username)
    display_name = clean_text(body.display_name or username, "display_name", 64)
    check_password(body.password)
    try:
        user = db.create_user(username, display_name, body.role, await asyncio.to_thread(hash_password, body.password))
    except Conflict as e:
        raise HTTPException(409, str(e)) from e
    record(who, "member create", f"{username} ({body.role})")
    return user


@admin_api.patch("/users/{user_id}")
async def update_user(user_id: int, body: UserPatch, who: Who):
    changes = body.model_dump(exclude_none=True)
    target = db.get_user(user_id)
    if target is None:
        raise HTTPException(404, "No such member")
    myself = who.user is not None and who.user["id"] == user_id
    if myself and (changes.get("disabled") or changes.get("role", who.user["role"]) != who.user["role"]):
        raise HTTPException(409, "You can't disable or demote yourself")
    if "display_name" in changes:
        changes["display_name"] = clean_text(changes["display_name"], "display_name", 64)
    if "password" in changes:
        check_password(changes["password"])
        changes["password_hash"] = await asyncio.to_thread(hash_password, changes.pop("password"))
    try:
        user = db.update_user(user_id, changes)
    except Conflict as e:
        raise HTTPException(409, str(e)) from e
    if "password_hash" in changes or changes.get("disabled"):
        db.delete_sessions(user_id, keep=who.session if myself else None)
    fields = [f"{k}={changes[k]}" for k in ("display_name", "role", "disabled") if k in changes]
    if "password_hash" in changes:
        fields.append("password")
    record(who, "member update", f"{target['username']}: {', '.join(fields) or 'no changes'}")
    return user


@admin_api.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: int, who: Who):
    if who.user is not None and who.user["id"] == user_id:
        raise HTTPException(409, "You can't delete yourself")
    target = db.get_user(user_id)
    try:
        if target is None or not db.delete_user(user_id):
            raise HTTPException(404, "No such member")
    except Conflict as e:
        raise HTTPException(409, str(e)) from e
    record(who, "member delete", target["username"])


# --- Player ---

@viewer_api.get("/status")
async def status(who: Who):
    relay = transport.relay_status() if who.role == "admin" else None  # relay details are admin-only

    def read():
        r, m = transport.receiver(), transport.media()
        return {
            "speaker": r.name or settings.speaker_name,
            "ip": r.ip,
            "app": r.app,
            "volume": round(r.volume, 2) if r.volume is not None else None,
            "muted": r.muted,
            "media": {
                "title": m.title,
                "state": m.player_state,
                "duration": m.duration,
                "position": round(m.adjusted_current_time, 1) if m.current_time is not None else None,
                "thumbnail": thumbnail_for(m.content_id),
            },
            "resume_pending": _resume and _resume["title"],
            "tts_lang": settings.tts_lang,
            "queue": _queue.summary() if _queue is not None else None,
            "talking": _talk.who.actor if _talk is not None else None,
        }

    try:
        result = await run_cast(read)
    except HTTPException as e:
        if relay is None:
            raise
        # Admins still get the relay's health while it (or the speaker behind it) is unreachable.
        return JSONResponse({"detail": e.detail, "relay": transport.relay_status()}, status_code=e.status_code)
    if who.role == "admin":
        result["relay"] = relay
    return result


@operator_api.post("/say")
async def say(body: SayBody, who: Who):
    if not body.text.strip():
        raise HTTPException(400, "text is empty")
    return await announce(body.text, body.lang, body.volume, who)


async def announce(text, lang, volume, who):
    """Speak `text`, then resume the interrupted track or let the queue continue (POST /say and schedules)."""
    global _resume, _say_gen
    tts_prefix = f"{base_url()}/tts.mp3"
    if settings.resume_after_say:
        # Keep an already-pending track when announcements are back to back.
        _resume = await run_cast(capture_youtube) or _resume
    q = _queue
    if q is not None:
        q.after_say = _resume is None and await run_cast(queue_after_say, q)
    _say_gen += 1
    gen = _say_gen
    url = media_url("/tts.mp3", text=text, lang=lang or settings.tts_lang)
    record(who, "say", text.strip()[:80])
    await run_cast(cast_play, url, "audio/mp3", "Announcement", volume)
    if _resume:
        spawn(resume_after_announcement(gen, tts_prefix))
    return {"ok": True, "chunks": len(split_text(text)), "will_resume": _resume and _resume["title"]}


@operator_api.post("/play")
async def play(body: PlayBody, who: Who):
    cancel_resume()
    clear_queue()
    record(who, "play", body.url[:200])
    await run_cast(cast_play, body.url, body.content_type, None, body.volume)
    return {"ok": True}


@operator_api.post("/youtube")
async def youtube(body: YoutubeBody, who: Who):
    cancel_resume()
    clear_queue()
    info = await asyncio.to_thread(yt_download, body.query)
    path = info["path"]
    url = media_url(f"/yt/{path.name}")
    record(who, "youtube", info["title"] or info["id"])
    await run_cast(cast_play, url, content_type_for(path), info["title"], body.volume)
    await asyncio.to_thread(prune_cache)
    return {"ok": True, "id": info["id"], "title": info["title"], "duration": info["duration"]}


@operator_api.get("/youtube/search")
async def youtube_search(q: Annotated[str, Query(min_length=1, max_length=200)], limit: int = Query(8, ge=1, le=20)):
    return await asyncio.to_thread(yt_search, q.strip(), limit)


@operator_api.post("/volume")
async def volume(body: VolumeBody, who: Who):
    if not 0 <= body.level <= 1:
        raise HTTPException(400, "level must be between 0 and 1")
    await run_cast(transport.set_volume, body.level)
    record(who, "volume", f"{round(body.level * 100)}%", coalesce=VOLUME_COALESCE)
    return {"ok": True, "volume": body.level}


@operator_api.post("/pause")
async def pause():
    await run_cast(transport.pause)
    return {"ok": True}


@operator_api.post("/resume")
async def resume():
    await run_cast(transport.resume)
    return {"ok": True}


async def stop_everything():
    cancel_resume()
    clear_queue()
    await run_cast(transport.stop)


@operator_api.post("/stop")
async def stop(who: Who):
    record(who, "stop")
    await stop_everything()
    return {"ok": True}


# --- Settings / speakers ---

@admin_api.get("/settings")
async def get_settings():
    return public_settings(settings)


@admin_api.post("/settings")
async def update_settings(changes: dict, background: BackgroundTasks, who: Who):
    """Partial update. Changing the port restarts the process; launchd brings it back up."""
    global settings, transport
    if "api_token" in changes:
        raise HTTPException(400, "api_token can't be changed over the API; rotate it with ./speakerctl token --rotate")
    try:
        new = merge_settings(settings, changes)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    if new.passkey_required_for_admins and not settings.passkey_required_for_admins:
        if not new.passkey_signin or relying_party(new.public_base_url, new.speaker_name) is None:
            raise HTTPException(409, "Passkeys aren't available; they need passkey_signin and an https:// "
                                     "public_base_url")
        missing = db.admins_without_passkey()
        if missing:
            raise HTTPException(409, f"Every admin needs a passkey first; missing: {', '.join(missing)}")
    old, settings = settings, new
    save_settings(new)
    record(who, "settings change", describe_changes(changes))
    if (new.transport, new.speaker_ip, new.speaker_name, new.mqtt) != (
        old.transport, old.speaker_ip, old.speaker_name, old.mqtt
    ):
        old_transport, transport = transport, make_transport(new)
        await run_cast(old_transport.close)
        transport.start()
    restart = new.port != old.port
    if restart:
        background.add_task(lambda: os._exit(0))
    return {"ok": True, "restart": restart, "settings": public_settings(new)}


@admin_api.get("/speakers")
async def speakers():
    def discover():
        found, browser = pychromecast.discovery.discover_chromecasts(timeout=4)
        browser.stop_discovery()
        return [{"name": c.friendly_name, "ip": c.host, "model": c.model_name} for c in found]

    return await asyncio.to_thread(discover)


@admin_api.get("/activity")
async def activity(limit: int = Query(50, ge=1, le=500), before_id: int | None = Query(None, ge=1)):
    return db.activity(limit, before_id)


# --- Playlists ---

def playlist_or_404(playlist):
    if playlist is None:
        raise HTTPException(404, "No such playlist")
    return playlist


@viewer_api.get("/playlists")
async def list_playlists():
    return db.list_playlists()


@operator_api.post("/playlists")
async def create_playlist(body: PlaylistBody):
    return db.create_playlist(clean_text(body.name, "name", 100))


@viewer_api.get("/playlists/{playlist_id}")
async def get_playlist(playlist_id: int):
    return playlist_or_404(db.get_playlist(playlist_id))


@operator_api.patch("/playlists/{playlist_id}")
async def rename_playlist(playlist_id: int, body: PlaylistBody):
    return playlist_or_404(db.rename_playlist(playlist_id, clean_text(body.name, "name", 100)))


@operator_api.delete("/playlists/{playlist_id}", status_code=204)
async def delete_playlist(playlist_id: int):
    if not db.delete_playlist(playlist_id):
        raise HTTPException(404, "No such playlist")


async def build_item(body):
    title = body.title.strip()[:200] if body.title and body.title.strip() else None
    if body.kind == "youtube":
        meta = await asyncio.to_thread(yt_info, clean_text(body.source, "source", 500))
        return {"kind": "youtube", "source": meta["video_id"], "title": title or meta["title"],
                "duration": meta["duration"], "thumbnail": meta["thumbnail"], "lang": None}
    if body.kind == "url":
        source = http_url(body.source, "source")
        if not title:
            raise HTTPException(400, "title is required for a url item")
        return {"kind": "url", "source": source, "title": title, "duration": None, "thumbnail": None, "lang": None}
    if body.kind == "radio":
        source = body.source.strip()
        station = await radio_station(source) if STATION_UUID_RE.fullmatch(source) else custom_station(
            StationBody(url=source, name=title, content_type=body.content_type, favicon=body.thumbnail))
        return {"kind": "radio", "source": station["url"], "title": title or station["name"], "duration": None,
                "thumbnail": station["favicon"], "lang": None, "content_type": station["content_type"]}
    if body.kind == "podcast":
        source = http_url(body.source, "source")
        if not title:
            raise HTTPException(400, "title is required for a podcast item")
        return {"kind": "podcast", "source": source, "title": title, "duration": body.duration,
                "thumbnail": optional_http_url(body.thumbnail), "lang": None,
                "content_type": audio_type(body.content_type) or guess_audio_type(source)}
    if body.kind == "file":
        row = db.get_file(int(body.source)) if body.source.strip().isdigit() else None
        if row is None:
            raise HTTPException(400, "source must be the id of an uploaded file")
        return {"kind": "file", "source": str(row["id"]), "title": title or row["title"], "duration": row["duration"],
                "thumbnail": None, "lang": None, "content_type": row["content_type"]}
    text = clean_text(body.source, "source", TTS_TEXT_MAX)
    lang = (body.lang or settings.tts_lang).strip()[:16]
    return {"kind": "tts", "source": text, "title": title or text[:60], "duration": None, "thumbnail": None,
            "lang": lang}


@operator_api.post("/playlists/{playlist_id}/items")
async def add_item(playlist_id: int, body: ItemBody):
    playlist_or_404(db.get_playlist(playlist_id))
    item = await build_item(body)
    try:
        return playlist_or_404(db.add_item(playlist_id, item, MAX_PLAYLIST_ITEMS))
    except Conflict as e:
        raise HTTPException(409, str(e)) from e


@operator_api.delete("/playlists/{playlist_id}/items/{item_id}", status_code=204)
async def delete_item(playlist_id: int, item_id: int):
    if not db.delete_item(playlist_id, item_id):
        raise HTTPException(404, "No such item in this playlist")


@operator_api.put("/playlists/{playlist_id}/order")
async def reorder_playlist(playlist_id: int, body: OrderBody):
    try:
        return playlist_or_404(db.reorder(playlist_id, body.item_ids))
    except Conflict as e:
        raise HTTPException(409, str(e)) from e


@operator_api.post("/playlists/{playlist_id}/play")
async def play_playlist(playlist_id: int, body: PlayPlaylistBody, who: Who):
    return await start_playlist(playlist_or_404(db.get_playlist(playlist_id)), body.start_index, body.shuffle,
                                body.repeat, who)


async def start_playlist(playlist, start_index, shuffle, repeat, who, volume=None):
    """Replace the queue with `playlist` and start it (POST /playlists/{id}/play and schedules)."""
    global _queue
    if not playlist["items"]:
        raise HTTPException(400, "The playlist is empty")
    if not 0 <= start_index < len(playlist["items"]):
        raise HTTPException(400, "start_index is out of range")
    q = Queue(playlist["items"], playlist["id"], playlist["name"], start_index, shuffle, repeat)
    clear_queue()
    _queue = q
    record(who, "playlist play", playlist["name"])
    try:
        if volume is not None:
            await run_cast(transport.set_volume, volume)
        played = await play_queue(q, keep_volume=volume is not None)
    except HTTPException:
        end_queue(q)
        raise
    if not played:
        raise HTTPException(502, "None of the playlist's items could be played")
    ensure_queue_watcher()
    return q.summary()


# --- Queue ---

def active_queue():
    if _queue is None:
        raise HTTPException(404, "Nothing is queued")
    return _queue


async def play_moved(q, who, how):
    record(who, "queue skip", f"{how}: {q.current['title']}")
    if not await play_queue(q):
        raise HTTPException(502, "No playable items left in the queue")
    ensure_queue_watcher()
    return q.summary()


@viewer_api.get("/queue")
async def get_queue():
    return _queue.summary() if _queue is not None else None


@operator_api.post("/queue/next")
async def queue_next(who: Who):
    q = active_queue()
    if not q.advance(auto=False):
        raise HTTPException(409, "Already at the last item")
    return await play_moved(q, who, "next")


@operator_api.post("/queue/prev")
async def queue_prev(who: Who):
    q = active_queue()
    q.back()
    return await play_moved(q, who, "previous")


@operator_api.post("/queue/jump")
async def queue_jump(body: JumpBody, who: Who):
    q = active_queue()
    try:
        q.jump(body.index)
    except IndexError as e:
        raise HTTPException(400, "index is out of range") from e
    return await play_moved(q, who, "jump")


@operator_api.patch("/queue")
async def update_queue(body: QueuePatch):
    q = active_queue()
    if body.shuffle is not None and body.shuffle != q.shuffle:
        q.set_shuffle(body.shuffle)
    if body.repeat is not None:
        q.repeat = body.repeat
    schedule_prefetch(q)
    return q.summary()


@operator_api.post("/queue/clear", status_code=204)
async def queue_clear(who: Who):
    record(who, "stop", "queue cleared")
    await stop_everything()


# --- Music sources: shared helpers ---

def http_url(value, field):
    value = (value or "").strip()
    if urllib.parse.urlsplit(value).scheme not in ("http", "https") or len(value) > 2000:
        raise HTTPException(400, f"{field} must be an http(s) URL")
    return value


def optional_http_url(value):
    """A picture URL from a directory or a feed: kept when it is http(s), dropped otherwise."""
    value = (value or "").strip()
    return value if urllib.parse.urlsplit(value).scheme in ("http", "https") and len(value) <= 2000 else None


def audio_type(value):
    value = (value or "").strip().lower()[:100]
    return value if value.startswith("audio/") or value in ("application/x-mpegurl", "application/vnd.apple.mpegurl") \
        else None


async def get_json(url, params, what):
    """GET a JSON API we trust (radio-browser, iTunes); 502 with a readable reason on any failure."""
    try:
        r = await http.get(url, params=params, headers={"User-Agent": USER_AGENT})
    except httpx.HTTPError as e:
        raise HTTPException(502, f"{what} is unreachable ({type(e).__name__})") from e
    if r.status_code != 200:
        raise HTTPException(502, f"{what} failed: HTTP {r.status_code}")
    try:
        return r.json()
    except ValueError as e:
        raise HTTPException(502, f"{what} sent an unreadable answer") from e


async def play_source(url, content_type, title, volume, who, action, live=False, thumbnail=None):
    """Play a radio station, podcast episode or uploaded file outside the queue (announcements resume it)."""
    global _direct
    cancel_resume()
    clear_queue()
    _direct = {"url": url, "live": live, "thumbnail": thumbnail}
    record(who, action, title[:200])
    await run_cast(cast_play, url, content_type, title, volume, live=live)
    return {"ok": True, "title": title}


# --- Internet radio (radio-browser.info) ---

def station_from_api(s):
    url = optional_http_url(s.get("url_resolved")) or optional_http_url(s.get("url"))
    if not url or not STATION_UUID_RE.fullmatch(s.get("stationuuid") or ""):
        return None
    codec = (s.get("codec") or "").upper()
    return {
        "uuid": s["stationuuid"],
        "name": (s.get("name") or "").strip()[:200] or "Radio",
        "url": url,
        "content_type": "application/x-mpegurl" if s.get("hls") else RADIO_CODECS.get(codec, "audio/mpeg"),
        "favicon": optional_http_url(s.get("favicon")),
        "country": (s.get("countrycode") or s.get("country") or "")[:64] or None,
        "tags": (s.get("tags") or "")[:200] or None,
        "bitrate": s.get("bitrate") if isinstance(s.get("bitrate"), int) and s["bitrate"] > 0 else None,
    }


async def radio_search(name, country, tag, limit):
    params = {"limit": limit, "hidebroken": "true", "order": "clickcount", "reverse": "true"}
    if name:
        params["name"] = name
    if country:
        params["countrycode"] = country
    if tag:
        params["tag"] = tag
    found = await get_json(f"{RADIO_API}/json/stations/search", params, "Radio directory")
    stations = [station_from_api(s) for s in found if isinstance(s, dict)] if isinstance(found, list) else []
    return [s for s in stations if s]


async def radio_station(uuid):
    found = await get_json(f"{RADIO_API}/json/stations/byuuid", {"uuids": uuid}, "Radio directory")
    stations = [station_from_api(s) for s in found if isinstance(s, dict)] if isinstance(found, list) else []
    if not any(stations):
        raise HTTPException(404, "No such radio station")
    return next(s for s in stations if s)


def custom_station(body):
    """A stream URL the user typed in, instead of a directory station."""
    url = http_url(body.url, "url")
    name = clean_text(body.name or "", "name", 200)
    return {"uuid": None, "name": name, "url": url,
            "content_type": audio_type(body.content_type) or guess_audio_type(url),
            "favicon": optional_http_url(body.favicon), "country": None, "tags": None, "bitrate": None}


async def resolve_station(body):
    if getattr(body, "favorite_id", None) is not None:
        favorite = db.get_favorite(body.favorite_id)
        if favorite is None:
            raise HTTPException(404, "No such favourite")
        return favorite
    if body.uuid:
        if not STATION_UUID_RE.fullmatch(body.uuid.strip()):
            raise HTTPException(400, "uuid is not a radio-browser station id")
        return await radio_station(body.uuid.strip())
    if body.url:
        return custom_station(body)
    raise HTTPException(400, "Give a station uuid, a favorite_id, or a url and name")


@operator_api.get("/radio/search")
async def search_radio(
    q: Annotated[str, Query(max_length=100)] = "",
    country: Annotated[str, Query(pattern=r"^([A-Za-z]{2})?$")] = "",
    tag: Annotated[str, Query(max_length=50)] = "",
    limit: int = Query(20, ge=1, le=50),
):
    """Most-listened stations matching a name, a two-letter country code and/or a tag (all optional)."""
    return await radio_search(q.strip(), country.upper(), tag.strip(), limit)


@viewer_api.get("/radio/favorites")
async def list_favorites():
    return db.list_favorites()


@operator_api.post("/radio/favorites")
async def add_favorite(body: StationBody, who: Who):
    station = await resolve_station(body)
    try:
        favorite = db.add_favorite(station, who.user and who.user["id"])
    except Conflict as e:
        raise HTTPException(409, str(e)) from e
    record(who, "radio favourite", station["name"])
    return favorite


@operator_api.delete("/radio/favorites/{favorite_id}", status_code=204)
async def delete_favorite(favorite_id: int, who: Who):
    favorite = db.get_favorite(favorite_id)
    if favorite is None or not db.delete_favorite(favorite_id):
        raise HTTPException(404, "No such favourite")
    record(who, "radio unfavourite", favorite["name"])


@operator_api.post("/radio/play")
async def play_radio(body: RadioPlayBody, who: Who):
    station = await resolve_station(body)
    return await play_source(station["url"], station["content_type"], station["name"], body.volume, who, "radio",
                             live=True, thumbnail=station["favicon"])


# --- Podcasts (iTunes Search API + the show's RSS feed) ---

def resolve_host(host):
    return {info[4][0] for info in socket.getaddrinfo(host, None)}


def check_public_url(url):
    """Refuse feed URLs that point into this machine's networks (the server fetches them, not the speaker)."""
    host = urllib.parse.urlsplit(url).hostname
    if not host:
        raise HTTPException(400, "feed must be an http(s) URL")
    try:
        addresses = resolve_host(host)
    except OSError as e:
        raise HTTPException(502, f"Can't resolve {host}") from e
    for address in addresses:
        if not ipaddress.ip_address(address.split("%")[0]).is_global:
            raise HTTPException(400, "feed must be on the public internet")


async def fetch_feed(url):
    """The feed's bytes, following redirects by hand (each hop checked) and reading at most FEED_MAX."""
    for _ in range(FEED_REDIRECTS + 1):
        url = http_url(url, "feed")
        await asyncio.to_thread(check_public_url, url)
        try:
            async with feed_http.stream("GET", url, headers={"User-Agent": USER_AGENT}) as r:
                if r.is_redirect and r.headers.get("location"):
                    url = urllib.parse.urljoin(url, r.headers["location"])
                    continue
                if r.status_code != 200:
                    raise HTTPException(502, f"Podcast feed failed: HTTP {r.status_code}")
                body = bytearray()
                async for chunk in r.aiter_bytes():
                    body += chunk
                    if len(body) > FEED_MAX:
                        raise HTTPException(502, "Podcast feed is too large")
                return bytes(body)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Podcast feed is unreachable ({type(e).__name__})") from e
    raise HTTPException(502, "Podcast feed redirects too many times")


def parse_duration(value):
    """itunes:duration is seconds, MM:SS or HH:MM:SS."""
    try:
        seconds = 0.0
        for part in (value or "").strip().split(":"):
            seconds = seconds * 60 + float(part)
        return seconds or None
    except ValueError:
        return None


def parse_date(value):
    try:
        return utc_iso(email.utils.parsedate_to_datetime(value))
    except (TypeError, ValueError):
        return None


def plain_text(value, limit):
    text = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return " ".join(text.split())[:limit] or None


def parse_feed(data, limit):
    """Show details and the newest `limit` audio episodes of an RSS podcast feed."""
    if b"<!ENTITY" in data:
        raise HTTPException(502, "Podcast feed declares XML entities; refusing to parse it")
    try:
        channel = ElementTree.fromstring(data).find("channel")
    except ElementTree.ParseError as e:
        raise HTTPException(502, "Not a podcast feed (invalid XML)") from e
    if channel is None:
        raise HTTPException(502, "Not a podcast feed (no RSS channel)")
    image = channel.find(f"{ITUNES_NS}image")
    artwork = optional_http_url(image.get("href") if image is not None else channel.findtext("image/url"))
    episodes = []
    for item in channel.iter("item"):
        enclosure = item.find("enclosure")
        url = optional_http_url(enclosure.get("url") if enclosure is not None else None)
        kind = (enclosure.get("type") or "").lower() if enclosure is not None else ""
        if not url or (kind and not audio_type(kind)):
            continue  # no audio (video episodes too: the speaker can't show them)
        picture = item.find(f"{ITUNES_NS}image")
        episodes.append({
            "guid": (item.findtext("guid") or url).strip()[:500],
            "title": (item.findtext("title") or "").strip()[:200] or "Untitled episode",
            "published": parse_date(item.findtext("pubDate")),
            "duration": parse_duration(item.findtext(f"{ITUNES_NS}duration")),
            "url": url,
            "content_type": audio_type(kind) or guess_audio_type(url),
            "thumbnail": optional_http_url(picture.get("href") if picture is not None else None) or artwork,
            "description": plain_text(item.findtext(f"{ITUNES_NS}summary") or item.findtext("description"), 300),
        })
        if len(episodes) >= limit:
            break
    return {
        "title": (channel.findtext("title") or "").strip()[:200] or None,
        "author": (channel.findtext(f"{ITUNES_NS}author") or "").strip()[:200] or None,
        "artwork": artwork,
        "description": plain_text(channel.findtext("description"), 500),
        "episodes": episodes,
    }


@operator_api.get("/podcasts/search")
async def search_podcasts(
    q: Annotated[str, Query(min_length=1, max_length=100)],
    country: Annotated[str, Query(pattern=r"^([A-Za-z]{2})?$")] = "",
    limit: int = Query(20, ge=1, le=50),
):
    """Shows matching the words, from Apple's podcast directory; `country` picks its store (e.g. TH)."""
    params = {"media": "podcast", "entity": "podcast", "term": q.strip(), "limit": limit}
    if country:
        params["country"] = country.upper()
    found = await get_json(PODCAST_SEARCH, params, "Podcast search")
    shows = []
    for r in found.get("results") or [] if isinstance(found, dict) else []:
        feed = optional_http_url(r.get("feedUrl")) if isinstance(r, dict) else None
        if feed:
            shows.append({
                "id": r.get("collectionId"),
                "title": (r.get("collectionName") or "").strip()[:200] or "Untitled show",
                "author": (r.get("artistName") or "").strip()[:200] or None,
                "feed_url": feed,
                "artwork": optional_http_url(r.get("artworkUrl600") or r.get("artworkUrl100")),
                "genre": r.get("primaryGenreName"),
                "episode_count": r.get("trackCount"),
            })
    return shows


@operator_api.get("/podcasts/episodes")
async def podcast_episodes(
    feed: Annotated[str, Query(min_length=1, max_length=2000)], limit: int = Query(50, ge=1, le=EPISODES_MAX)
):
    return parse_feed(await fetch_feed(feed), limit)


@operator_api.post("/podcasts/play")
async def play_episode(body: EpisodePlayBody, who: Who):
    url = http_url(body.url, "url")
    title = clean_text(body.title, "title", 200)
    content_type = audio_type(body.content_type) or guess_audio_type(url)
    return await play_source(url, content_type, title, body.volume, who, "podcast",
                             thumbnail=optional_http_url(body.thumbnail))


# --- My files (uploaded audio) ---

def sniff_audio(head):
    """FILE_TYPES extension for the audio format these first bytes start, or None."""
    if head.startswith(b"ID3"):
        return ".mp3"
    if len(head) >= 2 and head[0] == 0xFF and head[1] & 0xF6 == 0xF0:
        return ".aac"  # ADTS frame (layer bits 00)
    if len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0 and head[1] & 0x06:
        return ".mp3"  # MPEG audio frame without an ID3 tag
    if head[4:8] == b"ftyp":
        return ".m4a"
    if head.startswith(b"OggS"):
        return ".ogg"
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return ".wav"
    if head.startswith(b"fLaC"):
        return ".flac"
    if head.startswith(b"\x1aE\xdf\xa3"):
        return ".webm"
    return None


def public_file(row):
    return {k: v for k, v in row.items() if k != "stored_name"}


def file_or_404(file_id):
    row = db.get_file(file_id)
    if row is None:
        raise HTTPException(404, "No such file")
    return row


def check_file_owner(row, who):
    if who.role != "admin" and (who.user is None or row["owner_id"] != who.user["id"]):
        raise HTTPException(403, "Only the member who uploaded this file or an admin can change it")


@viewer_api.get("/files")
async def list_files():
    return {
        "items": [public_file(r) for r in db.list_files()],
        "used": db.files_size(),
        "quota": UPLOAD_QUOTA,
        "max_size": UPLOAD_MAX,
        "types": sorted(FILE_TYPES),
    }


@operator_api.post("/files")
async def upload_file(
    request: Request,
    who: Who,
    name: Annotated[str, Query(min_length=1, max_length=255)],
    duration: Annotated[float | None, Query(ge=0, le=24 * 3600)] = None,
):
    """The request body is the audio file itself (not a form); `name` is its original file name and
    `duration` (seconds, optional) what the browser measured. The format is checked from the content."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > UPLOAD_MAX:
        raise HTTPException(413, f"Files can be at most {UPLOAD_MAX // (1024 * 1024)} MB")
    room = UPLOAD_QUOTA - db.files_size()
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    part = MEDIA_DIR / f".upload-{secrets.token_hex(8)}.part"
    size, head = 0, b""
    try:
        with part.open("wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                if size > UPLOAD_MAX:
                    raise HTTPException(413, f"Files can be at most {UPLOAD_MAX // (1024 * 1024)} MB")
                if size > room:
                    raise HTTPException(507, "Not enough upload space left; delete some files first")
                if len(head) < 64:
                    head = (head + chunk)[:64]
                f.write(chunk)  # small chunks to the local disk; not worth a thread hop each
        if not size:
            raise HTTPException(400, "The file is empty")
        ext = sniff_audio(head)
        if ext is None:
            raise HTTPException(415, f"Not a supported audio file (use {', '.join(sorted(FILE_TYPES))})")
        stored = f"{secrets.token_urlsafe(12)}{ext}"
        part.rename(MEDIA_DIR / stored)
    finally:
        part.unlink(missing_ok=True)
    original = Path(name.replace("\\", "/")).name.strip()[:255] or "upload"
    title = Path(original).stem.strip()[:UPLOAD_TITLE_MAX] or "Untitled"
    row = db.add_file(stored, title, original, FILE_TYPES[ext], size, duration, who.user and who.user["id"])
    record(who, "file upload", f"{title} ({size // 1024} KB)")
    return public_file(row)


@operator_api.patch("/files/{file_id}")
async def rename_file(file_id: int, body: FilePatch, who: Who):
    row = file_or_404(file_id)
    check_file_owner(row, who)
    title = clean_text(body.title, "title", UPLOAD_TITLE_MAX)
    record(who, "file rename", f"{row['title']} -> {title}"[:200])
    return public_file(db.rename_file(file_id, title))


@operator_api.delete("/files/{file_id}", status_code=204)
async def delete_file(file_id: int, who: Who):
    row = file_or_404(file_id)
    check_file_owner(row, who)
    if db.delete_file(file_id) is None:
        raise HTTPException(404, "No such file")
    (MEDIA_DIR / row["stored_name"]).unlink(missing_ok=True)
    record(who, "file delete", row["title"])


@operator_api.post("/files/{file_id}/play")
async def play_file(file_id: int, body: FilePlayBody, who: Who):
    row = file_or_404(file_id)
    if not (MEDIA_DIR / row["stored_name"]).is_file():
        raise HTTPException(410, "The file is missing from the server's disk")
    url = media_url(f"/media/{row['stored_name']}")
    return await play_source(url, row["content_type"], row["title"], body.volume, who, "file play")


# --- Quick phrases ---

@viewer_api.get("/phrases")
async def list_phrases():
    return db.list_phrases()


@operator_api.post("/phrases")
async def add_phrase(body: PhraseBody, who: Who):
    text = clean_text(body.text, "text", TTS_TEXT_MAX)
    return db.add_phrase(text, (body.lang or settings.tts_lang).strip()[:16], who.user and who.user["id"])


@operator_api.delete("/phrases/{phrase_id}", status_code=204)
async def delete_phrase(phrase_id: int):
    if not db.delete_phrase(phrase_id):
        raise HTTPException(404, "No such phrase")


# --- Scheduled announcements ---

def utc_iso(moment):
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def next_run_after(schedule, after):
    """The first run strictly after `after` (aware), from the local wall time; None once a one-off has passed."""
    hour, minute = map(int, schedule["time"].split(":"))
    if not schedule["days"]:
        day = date.fromisoformat(schedule["date"])
        candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZONE)
        return candidate if candidate > after else None
    today = after.astimezone(ZONE).date()
    for offset in range(8):
        day = today + timedelta(days=offset)
        if day.weekday() in schedule["days"]:
            candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZONE)
            if candidate > after:
                return candidate
    return None  # unreachable with at least one day


def validate_schedule(fields, now):
    """Normalize a whole schedule (after merging a PATCH) and work out next_run. 400 on anything invalid."""
    out = {"name": clean_text(fields.get("name") or "", "name", SCHEDULE_NAME_MAX)}
    out["enabled"] = True if fields.get("enabled") is None else fields["enabled"]
    action = fields.get("action")
    if action not in ("say", "playlist"):
        raise HTTPException(400, "action must be 'say' or 'playlist'")
    out["action"] = action
    if action == "say":
        out["text"] = clean_text(fields.get("text") or "", "text", TTS_TEXT_MAX)
        out["lang"] = (fields.get("lang") or settings.tts_lang).strip()[:16] or settings.tts_lang
        out["playlist_id"], out["shuffle"] = None, False
    else:
        if fields.get("playlist_id") is None:
            raise HTTPException(400, "playlist_id is required for a playlist schedule")
        if db.get_playlist(fields["playlist_id"]) is None:
            raise HTTPException(400, "Unknown playlist")
        out["playlist_id"], out["shuffle"] = fields["playlist_id"], bool(fields.get("shuffle"))
        out["text"] = out["lang"] = None
    volume = fields.get("volume")
    if volume is not None and not 0 <= volume <= 1:
        raise HTTPException(400, "volume must be between 0 and 1")
    out["volume"] = volume
    if not TIME_RE.fullmatch(fields.get("time") or ""):
        raise HTTPException(400, "time must be HH:MM (24-hour)")
    out["time"] = fields["time"]
    days = fields.get("days") or []
    if any(not 0 <= d <= 6 for d in days):
        raise HTTPException(400, "days must be numbers 0 (Monday) to 6 (Sunday)")
    out["days"] = sorted(set(days))
    out["date"] = None
    if not days:
        raw = fields.get("date") or ""
        try:
            if not DATE_RE.fullmatch(raw):
                raise ValueError
            date.fromisoformat(raw)
        except ValueError:
            raise HTTPException(400, "date must be YYYY-MM-DD when days is empty (one-off)") from None
        out["date"] = raw
    following = next_run_after(out, now) if out["enabled"] else None
    if out["enabled"] and following is None:
        raise HTTPException(400, "The date and time of a one-off schedule must not be in the past")
    out["next_run"] = following and utc_iso(following)
    return out


def schedule_or_404(schedule):
    if schedule is None:
        raise HTTPException(404, "No such schedule")
    return schedule


async def fire_schedule(schedule, who):
    """Play a schedule now through the same path as POST /say or /playlists/{id}/play; raises HTTPException."""
    if schedule["action"] == "say":
        await announce(schedule["text"], schedule["lang"], schedule["volume"], who)
        return
    playlist = db.get_playlist(schedule["playlist_id"]) if schedule["playlist_id"] is not None else None
    if playlist is None:
        raise HTTPException(400, "The schedule's playlist no longer exists")
    count = len(playlist["items"])
    start = random.randrange(count) if schedule["shuffle"] and count else 0  # shuffle keeps the start item first
    await start_playlist(playlist, start, schedule["shuffle"], "off", who, schedule["volume"])


async def run_schedule(schedule, who):
    """Fire and record the outcome ("ok" or the error) in last_result and the activity log.

    Returns the HTTPException it failed with, or None.
    """
    error = None
    try:
        await fire_schedule(schedule, who)
        result = "ok"
    except HTTPException as e:
        error, result = e, str(e.detail)
    except Exception as e:  # one broken schedule mustn't stop the runner
        result = f"{type(e).__name__}: {e}"
        error = HTTPException(500, result)
    db.update_schedule(schedule["id"], {"last_result": result})
    record(who, "schedule run", f"{schedule['name']}: {result}"[:200])
    return error


async def run_due_schedules(now):
    """Fire every enabled schedule whose next_run <= now (aware datetime); skip ones overdue past the grace."""
    for schedule in db.due_schedules(utc_iso(now)):
        due = datetime.fromisoformat(schedule["next_run"])
        following = next_run_after(schedule, now) if schedule["days"] else None
        moved = {"next_run": following and utc_iso(following)}
        if not schedule["days"]:
            moved["enabled"] = False  # one-off: done either way
        if now - due > SCHEDULE_GRACE:
            db.update_schedule(schedule["id"], moved | {"last_result": "missed"})
            db.log("system", "schedule missed", f"{schedule['name']} (due {due.astimezone(ZONE):%Y-%m-%d %H:%M})")
            continue
        # Move next_run on before playing, so a slow download can't make the next poll fire it again.
        db.update_schedule(schedule["id"], moved | {"last_run": utc_iso(now)})
        await run_schedule(schedule, None)


async def schedule_loop():
    while True:
        try:
            await run_due_schedules(datetime.now(UTC))
        except Exception as e:  # keep the runner alive
            print(f"schedule runner error: {type(e).__name__}: {e}")
        await asyncio.sleep(SCHEDULE_POLL)


@viewer_api.get("/schedules")
async def list_schedules():
    return {"timezone": ZONE.key, "now": utc_iso(datetime.now(UTC)), "items": db.list_schedules()}


@operator_api.post("/schedules")
async def create_schedule(body: ScheduleBody, who: Who):
    fields = validate_schedule(body.model_dump(), datetime.now(UTC))
    schedule = db.create_schedule(fields, who.user and who.user["id"])
    record(who, "schedule create", schedule["name"])
    return schedule


@operator_api.patch("/schedules/{schedule_id}")
async def update_schedule(schedule_id: int, body: ScheduleBody, who: Who):
    current = schedule_or_404(db.get_schedule(schedule_id))
    fields = validate_schedule(current | body.model_dump(exclude_unset=True), datetime.now(UTC))
    schedule = schedule_or_404(db.update_schedule(schedule_id, fields))
    record(who, "schedule update", schedule["name"])
    return schedule


@operator_api.delete("/schedules/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: int, who: Who):
    schedule = schedule_or_404(db.get_schedule(schedule_id))
    db.delete_schedule(schedule_id)
    record(who, "schedule delete", schedule["name"])


@operator_api.post("/schedules/{schedule_id}/run")
async def run_schedule_now(schedule_id: int, who: Who):
    """Test-play regardless of time or enabled; next_run stays as it is."""
    schedule = schedule_or_404(db.get_schedule(schedule_id))
    db.update_schedule(schedule_id, {"last_run": utc_iso(datetime.now(UTC))})
    error = await run_schedule(schedule, who)
    if error is not None:
        raise error
    return {"ok": True}


# --- Live talk (WebSocket /talk) ---
#
# Protocol (JSON text frames unless noted):
#   client -> {"type": "start", "mime": MediaRecorder.mimeType, "chime": bool, "volume": 0-1 | null}
#   server -> {"type": "ready", "id", "max_seconds", "format"}   then the client sends binary recorder chunks
#   server -> {"type": "live"}                                    the speaker has loaded the live stream
#   client -> {"type": "stop"} | {"type": "ping"}  (server answers a ping with {"type": "pong"})
#   server -> {"type": "ended", "reason", "seconds", "detail"?}  and closes (1000)
#   server -> {"type": "error", "code", "detail"}                 and closes (44xx / 4503) instead of starting
# One talker at a time. Music pauses for the talk and resumes after it, as after an announcement.

TALK_CLOSE = {"bad_request": 4400, "unauthorized": 4401, "forbidden": 4403, "busy": 4409, "unavailable": 4503}

talk_transcoder = talk.FfmpegTranscoder  # replaced by a fake in tests
talk_available = talk.ffmpeg_available


@dataclass
class TalkSession:
    id: str
    who: Principal
    chime: bool
    volume: float | None
    transcoder: object
    live_url: str
    stream: talk.LiveStream = field(default_factory=talk.LiveStream)
    gen: int | None = None  # _say_gen once the talk has taken over the speaker
    end_reason: str | None = None  # set by a helper task that wants the talk to end
    detail: str | None = None
    first_chunk: float | None = None
    last_chunk: float | None = None
    received: int = 0
    ended_at: float | None = None

    @property
    def seconds(self):
        return self.last_chunk - self.first_chunk if self.first_chunk is not None else 0.0


_talk: TalkSession | None = None  # the talk in progress
_talk_last: TalkSession | None = None  # the previous one, whose stream the speaker may still be reading
_talk_on_speaker: TalkSession | None = None  # owns the speaker from its start until the music is back


class TalkSender:
    """Sends from the talk loop and its helper tasks one at a time; a closed socket is ignored."""

    def __init__(self, ws):
        self.ws, self.lock = ws, asyncio.Lock()

    async def __call__(self, message):
        async with self.lock:
            try:
                await self.ws.send_json(message)
            except Exception:  # the client is gone (the exception type depends on the server)
                pass


async def talk_refuse(ws, code, detail):
    try:
        await ws.send_json({"type": "error", "code": code, "detail": detail})
        await ws.close(TALK_CLOSE[code], reason=code)
    except Exception:  # the client is gone
        pass


def talk_caller(ws):
    """(Principal, None), or (None, (error code, detail)) for a connection that may not talk.

    Browsers can't set headers on a WebSocket, so the session cookie authenticates and the Origin
    check stands in for the X-Requested-With header; scripts may send the API token instead.
    """
    origin = ws.headers.get("origin")
    if origin:
        allowed = {ws.headers.get("host", "")}
        if settings.public_base_url:
            allowed.add(urllib.parse.urlsplit(settings.public_base_url).netloc)
        if urllib.parse.urlsplit(origin).netloc not in allowed:
            return None, ("forbidden", "Cross-site connection refused")
    auth = ws.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        if not secrets.compare_digest(auth[7:].strip().encode(), settings.api_token.encode()):
            return None, ("unauthorized", "Missing or invalid API token")
        who = Principal("admin", "api-token")
    else:
        sid = ws.cookies.get(SESSION_COOKIE)
        user = db.session_user(token_hash(sid))[0] if sid else None
        if user is None:
            return None, ("unauthorized", "Not signed in")
        who = Principal(user["role"], user["display_name"], user, token_hash(sid))
    if ROLE_RANK[who.role] < ROLE_RANK["operator"]:
        return None, ("forbidden", "Live talk needs the operator role")
    return who, None


def parse_talk_start(message):
    """(input format, chime, volume) from the start message; ValueError with a readable reason."""
    if message.get("type") != "websocket.receive" or message.get("text") is None:
        raise ValueError("Send a start message (JSON text) first")
    try:
        start = json.loads(message["text"])
    except ValueError:
        raise ValueError("The start message is not JSON") from None
    if not isinstance(start, dict) or start.get("type") != "start":
        raise ValueError('The first message must be {"type": "start", ...}')
    fmt = talk.input_format(start.get("mime") if isinstance(start.get("mime"), str) else "")
    if fmt is None:
        raise ValueError(f"Unsupported recording format; use one of {', '.join(sorted(talk.INPUT_FORMATS))}")
    volume = start.get("volume")
    if volume is not None and (isinstance(volume, bool) or not isinstance(volume, (int, float))
                               or not 0 <= volume <= 1):
        raise ValueError("volume must be between 0 and 1")
    return fmt, bool(start.get("chime")), volume


@app.websocket("/talk")
async def talk_socket(ws: WebSocket):
    global _talk
    await ws.accept()  # accept first: a refused handshake hides the reason from the browser
    who, problem = talk_caller(ws)
    if problem:
        await talk_refuse(ws, *problem)
        return
    try:
        message = await asyncio.wait_for(ws.receive(), TALK_START_TIMEOUT)
    except TimeoutError:
        await talk_refuse(ws, "bad_request", "No start message within 10 seconds")
        return
    if message["type"] == "websocket.disconnect":
        return
    try:
        fmt, chime, volume = parse_talk_start(message)
    except ValueError as e:
        await talk_refuse(ws, "bad_request", str(e))
        return
    if not talk_available():
        await talk_refuse(ws, "unavailable", "Live talk needs ffmpeg on the server, and it isn't installed")
        return
    if _talk is not None:
        await talk_refuse(ws, "busy", f"{_talk.who.actor} is talking right now")
        return
    talk_id = secrets.token_urlsafe(9)
    _talk = TalkSession(talk_id, who, chime, volume, talk_transcoder(fmt), media_url(f"/talk/{talk_id}/live"))
    await run_talk(ws, _talk, TalkSender(ws))


async def run_talk(ws, session, send):
    """Run one talk from ffmpeg start to clean-up; every path ends with ffmpeg gone and the stream closed."""
    global _talk, _talk_last, _talk_on_speaker
    pump = speaker = None
    started = False
    try:
        await session.transcoder.start()
        started = True
        pump = asyncio.create_task(talk_pump(session))
        await send({"type": "ready", "id": session.id, "max_seconds": settings.talk_max_seconds,
                    "format": "audio/mpeg"})
        _talk_on_speaker = session
        speaker = asyncio.create_task(talk_start_speaker(session, send))
        session.end_reason = await talk_receive(ws, session, send)
    except talk.TranscoderError as e:
        session.end_reason, session.detail = "transcoder_error", str(e)
    finally:
        _talk, _talk_last = None, session  # the next talker may start while this one winds down
        try:
            await end_talk(ws, session, send, speaker, pump, started)
        except asyncio.CancelledError:  # server shutting down mid clean-up: at least stop ffmpeg
            session.transcoder.kill()
            if _talk_on_speaker is session:
                _talk_on_speaker = None
            raise


async def end_talk(ws, session, send, speaker, pump, started):
    """Stop ffmpeg, close the stream, log, hand the speaker back and tell the client how it ended."""
    global _talk_on_speaker
    if speaker is not None:
        await asyncio.wait({speaker}, timeout=TALK_SPEAKER_WAIT)
        speaker.cancel()
    await session.transcoder.finish(TALK_DRAIN)
    if pump is not None:
        await asyncio.wait({pump}, timeout=TALK_DRAIN)
        pump.cancel()
    await session.stream.close()
    session.ended_at = time.monotonic()
    reason = session.end_reason or "disconnected"
    if started:
        suffix = "" if reason in ("stopped", "disconnected") else f" ({reason.replace('_', ' ')})"
        record(session.who, "talk", f"Talked live for {talk.format_seconds(session.seconds)}{suffix}")
    if session.gen is not None and session.gen == _say_gen:
        spawn(talk_finish_on_speaker(session))
    elif _talk_on_speaker is session:
        _talk_on_speaker = None
    ended = {"type": "ended", "reason": reason, "seconds": round(session.seconds, 1)}
    await send(ended | ({"detail": session.detail} if session.detail else {}))
    try:
        await ws.close(1000)
    except Exception:  # already closed by the client
        pass


async def talk_receive(ws, session, send):
    """Feed recorder chunks to ffmpeg until the talk should end; returns the reason."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + settings.talk_max_seconds
    last_audio = loop.time()
    pending = None
    try:
        while True:
            if session.end_reason:
                return session.end_reason
            if session.gen is not None and session.gen != _say_gen:
                return "interrupted"  # something else was played or announced
            now = loop.time()
            if now >= deadline:
                return "max_length"
            if now - last_audio >= TALK_IDLE_TIMEOUT:
                return "idle"
            if pending is None:
                pending = asyncio.ensure_future(ws.receive())
            done, _ = await asyncio.wait({pending}, timeout=min(TALK_TICK, deadline - now))
            if not done:
                continue
            message, pending = pending.result(), None
            if message["type"] == "websocket.disconnect":
                return "disconnected"
            if message.get("bytes"):
                chunk = message["bytes"]
                last_audio = loop.time()
                if session.first_chunk is None:
                    session.first_chunk = last_audio
                session.last_chunk = last_audio
                session.received += len(chunk)
                if session.received > TALK_MAX_RATE * settings.talk_max_seconds:
                    return "too_large"
                await session.transcoder.write(chunk)
            elif message.get("text"):
                try:
                    kind = json.loads(message["text"]).get("type")
                except (ValueError, AttributeError):
                    kind = None
                if kind == "stop":
                    return "stopped"
                if kind == "ping":
                    await send({"type": "pong"})
    finally:
        if pending is not None:
            pending.cancel()


async def talk_pump(session):
    """Move ffmpeg's MP3 output into the live stream until ffmpeg exits."""
    while chunk := await session.transcoder.read():
        await session.stream.append(chunk)


async def wait_until_idle(gen, url, timeout):
    """Poll until the speaker has finished `url`, moved on to something else, or `timeout` has passed."""
    loop = asyncio.get_running_loop()
    deadline, seen = loop.time() + timeout, False
    while loop.time() < deadline and gen == _say_gen:
        m = await run_cast(transport.media)
        if m.content_id == url:
            seen = True
            if m.player_state == "IDLE":
                return
        elif seen:
            return
        await asyncio.sleep(TALK_POLL)


async def talk_start_speaker(session, send):
    """Take over the speaker like an announcement: remember the music, optional chime, then the live stream."""
    global _resume, _say_gen
    try:
        if settings.resume_after_say:
            _resume = await run_cast(capture_youtube) or _resume
        q = _queue
        if q is not None:
            q.after_say = _resume is None and await run_cast(queue_after_say, q)
        _say_gen += 1
        session.gen = gen = _say_gen
        if session.chime:
            chime = media_url("/talk/chime.wav", tone="start")
            await run_cast(cast_play, chime, "audio/wav", "Chime", session.volume)
            await wait_until_idle(gen, chime, TALK_CHIME_WAIT)
            if gen != _say_gen:
                return
        await run_cast(cast_play, session.live_url, "audio/mpeg", f"Live: {session.who.actor}", session.volume,
                       live=True)
        await send({"type": "live"})
    except HTTPException as e:
        session.end_reason, session.detail = "speaker_error", str(e.detail)


async def talk_finish_on_speaker(session):
    """After a talk: let the speaker play out the stream, closing chime, then resume the interrupted music."""
    global _talk_on_speaker
    gen = session.gen
    try:
        if session.chime:
            await wait_until_idle(gen, session.live_url, TALK_END_WAIT)
            if gen != _say_gen:
                return
            await run_cast(cast_play, media_url("/talk/chime.wav", tone="end"), "audio/wav", "Chime",
                           session.volume)
        if _resume and gen == _say_gen:
            await resume_after_announcement(gen, f"{base_url()}/talk/")
        elif _queue is not None and _queue.after_say and gen == _say_gen:
            await wait_until_idle(gen, session.live_url, TALK_END_WAIT)  # then queue_tick moves the queue on
    except HTTPException as e:
        print(f"talk: {e.detail}")
    finally:
        if _talk_on_speaker is session:
            _talk_on_speaker = None


@operator_api.get("/talk/status")
async def talk_status():
    """Whether live talk works on this server (ffmpeg installed) and who is talking."""
    active = _talk and {"by": _talk.who.actor, "id": _talk.id}
    return {"available": talk_available(), "max_seconds": settings.talk_max_seconds, "active": active}


# --- Streams fetched by the speaker itself (signed URLs, no header) ---

@app.get("/tts.mp3", dependencies=[Depends(verify_media)])
async def tts(text: str, lang: str = "th"):
    audio = b""
    for chunk in split_text(text):
        r = await http.get(
            "https://translate.google.com/translate_tts",
            params={"ie": "UTF-8", "client": "tw-ob", "tl": lang, "q": chunk},
        )
        if r.status_code != 200:
            raise HTTPException(502, f"TTS failed: HTTP {r.status_code}")
        audio += r.content  # MP3 frames concatenate cleanly
    return Response(audio, media_type="audio/mpeg")


@app.get("/yt/{filename}", dependencies=[Depends(verify_media)])
async def yt_file(filename: str):
    path = CACHE_DIR / Path(filename).name
    if not path.is_file():
        raise HTTPException(404, "not cached")
    return FileResponse(path, media_type=content_type_for(path))


@app.get("/media/{filename}", dependencies=[Depends(verify_media)])
async def media_file(filename: str):
    path = MEDIA_DIR / Path(filename).name
    if path.name.startswith(".") or not path.is_file():
        raise HTTPException(404, "No such file")
    return FileResponse(path, media_type=FILE_TYPES.get(path.suffix, "application/octet-stream"))


@app.get("/talk/chime.wav", dependencies=[Depends(verify_media)])
async def talk_chime(tone: Literal["start", "end"] = "start"):
    return Response(chime_bytes(tone), media_type="audio/wav")


@cache
def chime_bytes(tone):
    return talk.chime_wav(tone)


@app.get("/talk/{talk_id}/live", dependencies=[Depends(verify_media)])
async def talk_live(talk_id: str):
    """The talk's MP3 as one endless response; it ends when the talk does."""
    session = _talk if _talk is not None and _talk.id == talk_id else _talk_last
    recent = session is not None and (session.ended_at is None or time.monotonic() - session.ended_at < TALK_GRACE)
    if not recent or session.id != talk_id:
        raise HTTPException(404, "No such live talk")
    return StreamingResponse(session.stream.follow(), media_type="audio/mpeg",
                             headers={"Cache-Control": "no-store"})


# --- Web UI (public) ---

# The web app is ES modules under fixed names, so browsers (and proxies such as Cloudflare, which add a long
# max-age when none is set) must check back on every load; otherwise an update mixes old and new modules.
NO_CACHE = {"Cache-Control": "no-cache"}


class RevalidatedStatic(StaticFiles):
    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers.update(NO_CACHE)
        return response


@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse(STATIC_DIR / "index.html", headers=NO_CACHE)


def static_root_file(name, media_type):
    async def serve():
        path = STATIC_DIR / name
        if not path.is_file():
            raise HTTPException(404, "Not found")
        return FileResponse(path, media_type=media_type)

    return serve


# iOS looks for these at the site root.
app.get("/manifest.webmanifest", include_in_schema=False)(
    static_root_file("manifest.webmanifest", "application/manifest+json")
)
app.get("/apple-touch-icon.png", include_in_schema=False)(static_root_file("apple-touch-icon.png", "image/png"))
app.mount("/static", RevalidatedStatic(directory=STATIC_DIR), name="static")

for router in (viewer_api, operator_api, admin_api):
    app.include_router(router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.port)
