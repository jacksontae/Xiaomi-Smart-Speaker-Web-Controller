"""Settings (config.json plus environment overrides), paths and limits, and the server's time zone."""
import ipaddress
import json
import os
import re
import secrets
import urllib.parse
from datetime import UTC, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator
from yt_dlp.postprocessor.sponsorblock import SponsorBlockPP

from server import talk
from server.version import __version__

ROOT = Path(__file__).resolve().parent.parent  # the checkout: config.json, data.db, static/, cache/
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
HOST_LABEL_RE = re.compile(r"(?!-)[A-Za-z0-9-]{1,63}(?<!-)")  # one DNS label (RFC 1123)
SPEAKER_NAME_MAX = 64  # the settings page's input has the same maxLength
OWNER_CONTACT_MAX = 120  # ... and so does the owner contact's
TIME_RE = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
AUDIO_SUFFIXES = {".m4a", ".webm", ".mp3", ".opus", ".ogg", ".mp4", ".aac"}
# SponsorBlock segment kinds yt-dlp can cut out (highlight/chapter only mark a point, so they aren't offered).
YT_SEGMENT_CATEGORIES = tuple(c for c in SponsorBlockPP.CATEGORIES if c not in SponsorBlockPP.NON_SKIPPABLE_CATEGORIES)
YT_SKIP_DEFAULT = ("interaction", "selfpromo", "sponsor")
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
FEED_CACHE_TTL = 15 * 60  # a followed show's feed is read at most this often for its "N new" count
FEED_FAIL_TTL = 5 * 60  # ... and a feed that failed isn't tried again sooner than this
FEED_CHECKS = 4  # feeds read at once for the Following list
FEED_CHECK_TIMEOUT = 10  # seconds one feed may take there before it just shows no count
USER_AGENT = f"speaker-service/{__version__}"  # radio-browser asks clients to identify themselves
# "This device" stream proxy (/local/stream): for radio a browser can't fetch itself (http:// on an https page)
STREAM_MAX_BYTES = 512 * 1024 * 1024  # one relayed stream ends after this much (about 9 h of 128 kbit/s radio)
STREAM_MAX_SECONDS = 6 * 3600  # ... or after this long; the browser then asks for a fresh link
STREAM_MAX_OPEN = 8  # relayed streams at once (all browsers together)
STREAM_REDIRECTS = 5
HLS_MAX_BYTES = 512 * 1024  # an HLS playlist the relay rewrites (a live radio one is a few kB)
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
TALKIE_DIR = Path(os.environ.get("TALKIE_DIR", DATA_PATH.parent / "talkie"))  # Talkie clips (MP3, kept a day)
TALKIE_MAX_SECONDS = 60  # a Talkie talk (walkie or message) ends after this long
TALKIE_MIN_SECONDS = 0.5  # shorter ones (a tap on the button) are dropped, not kept as a clip
TALKIE_KEEP = timedelta(hours=24)  # clips older than this are deleted
TALKIE_SWEEP = 3600.0  # seconds between sweeps for old clip files


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


def is_ip_or_hostname(value):
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        pass
    host = value.removesuffix(".")
    labels = host.split(".")
    # An all-numeric last label is a mistyped IP address (999.1.1.1), not a hostname.
    return (0 < len(host) <= 253 and all(HOST_LABEL_RE.fullmatch(label) for label in labels)
            and not labels[-1].isdigit())


def readable_errors(errors):
    """Pydantic errors as one line the web UI can show: "speaker_ip: must be ...; port: ..."."""
    messages = []
    for err in errors:
        where = ".".join(str(p) for p in err["loc"] if p not in ("body", "query", "path"))
        msg = err["msg"].removeprefix("Value error, ")
        messages.append(f"{where}: {msg}" if where and not msg.startswith(where) else msg)
    return "; ".join(messages) or "Invalid request"


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
    # SponsorBlock segments cut out of downloaded YouTube audio (needs ffmpeg); [] = keep the whole video.
    yt_skip_segments: list[str] = Field(default_factory=lambda: list(YT_SKIP_DEFAULT))
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
    # How members reach the owner (an email, a LINE id...), shown on the About page to signed-in members only.
    owner_contact: str | None = None
    # The sid cookie's Secure flag. "auto": when the request came over https (uvicorn takes X-Forwarded-Proto
    # only from FORWARDED_ALLOW_IPS, default this machine) or to the host of an https:// public_base_url (a
    # TLS-terminating proxy such as Cloudflare Tunnel). true: always. false: never.
    cookie_secure: Literal["auto"] | bool = "auto"

    @field_validator("speaker_ip")
    @classmethod
    def check_speaker_ip(cls, v):
        """The Cast transport connects to this address and media URLs are routed by it, so it can't be blank."""
        v = v.strip()
        if not is_ip_or_hostname(v):
            raise ValueError("speaker_ip must be an IP address like 192.0.2.10 or a hostname like speaker.local")
        return v

    @field_validator("speaker_name")
    @classmethod
    def check_speaker_name(cls, v):
        v = " ".join(v.split())  # also folds tabs and newlines
        if not v:
            raise ValueError("speaker_name can't be empty")
        if len(v) > SPEAKER_NAME_MAX:
            raise ValueError(f"speaker_name must be at most {SPEAKER_NAME_MAX} characters")
        return v

    @field_validator("owner_contact")
    @classmethod
    def check_owner_contact(cls, v):
        if v is None:
            return None
        v = " ".join(v.split())
        if len(v) > OWNER_CONTACT_MAX:
            raise ValueError(f"owner_contact must be at most {OWNER_CONTACT_MAX} characters")
        return v or None

    @field_validator("yt_skip_segments")
    @classmethod
    def check_skip_segments(cls, v):
        """Lowercased, de-duplicated and sorted, so the same choice always gives the same cache name."""
        cats = {c.strip().lower() for c in v}
        unknown = sorted(cats - set(YT_SEGMENT_CATEGORIES))
        if unknown:
            raise ValueError(f"yt_skip_segments: unknown categories {', '.join(unknown)}; "
                             f"known: {', '.join(YT_SEGMENT_CATEGORIES)}")
        return sorted(cats)

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
    "COOKIE_SECURE": ("cookie_secure",),
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
    data["yt_skip_available"] = talk.ffmpeg_available()  # read-only: cutting segments needs ffmpeg
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


def utc_iso(moment):
    return moment.astimezone(UTC).isoformat(timespec="seconds")


settings = load_settings()
ZONE = local_zone()
