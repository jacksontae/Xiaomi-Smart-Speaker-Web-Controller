"""HTTP service that makes a Google Cast speaker announce text and play YouTube audio.

The speaker fetches every stream from this service (TTS and YouTube are proxied),
so it only needs to reach this machine on the LAN.

Callers authenticate with either `Authorization: Bearer <api_token>` (acts as admin) or the
`sid` session cookie of a web account (admin, operator or viewer). The speaker cannot send
headers, so the media URLs handed to it are signed with an HMAC of the token instead.
"""
import asyncio
import hashlib
import hmac
import itertools
import json
import mimetypes
import os
import re
import secrets
import socket
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

import httpx
import pychromecast
import pychromecast.discovery
import pychromecast.error
import yt_dlp
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pychromecast.const import CAST_TYPE_AUDIO
from pychromecast.models import CastInfo, HostServiceInfo
from pydantic import BaseModel, Field

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
from player import Queue
from store import SESSION_TTL, Conflict, Store

ROOT = Path(__file__).parent
CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", ROOT / "config.json"))
DATA_PATH = Path(os.environ.get("DATA_PATH", ROOT / "data.db"))
STATIC_DIR = ROOT / "static"
DEFAULT_MEDIA_RECEIVER = "CC1AD845"
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
YT_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")
AUDIO_SUFFIXES = {".m4a", ".webm", ".mp3", ".opus", ".ogg", ".mp4", ".aac"}


class Settings(BaseModel):
    speaker_ip: str = "192.0.2.10"
    speaker_name: str = "Air Purifier speaker"
    port: int = Field(8090, ge=1024, le=65535)
    default_volume: float | None = Field(None, ge=0, le=1)  # None = keep the speaker's volume
    tts_lang: str = "th"
    cache_keep: int = Field(20, ge=1)  # most recent YouTube tracks kept on disk
    resume_after_say: bool = True  # continue the interrupted YouTube track after /say
    public_base_url: str | None = None  # override when auto-detected LAN address is wrong
    api_token: str | None = None  # Bearer token for the control API; generated on first run, never served


def load_settings():
    s = Settings(**json.loads(CONFIG_PATH.read_text())) if CONFIG_PATH.exists() else Settings()
    if not s.api_token:
        s.api_token = secrets.token_urlsafe(32)
        save_settings(s)
    return s


def save_settings(s):
    CONFIG_PATH.write_text(json.dumps(s.model_dump(), indent=2, ensure_ascii=False) + "\n")
    CONFIG_PATH.chmod(0o600)  # holds the API token


def public_settings(s):
    return s.model_dump(exclude={"api_token"})


settings = load_settings()
db = Store(DATA_PATH)
login_throttle = Throttle(limit=5, window=300)
app = FastAPI(title="Speaker Service")
http = httpx.AsyncClient(timeout=30, follow_redirects=True)
cast_lock = asyncio.Lock()
_cast = None
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


# --- Cast ---

def connect_speaker(ip):
    """Connect without pychromecast's blocking 30 s HTTP probe for the cast type.

    Bounded retries make an unreachable speaker fail in ~10 s instead of hanging;
    when the worker later gives up, get_cast() sees a dead thread and reconnects.
    """
    info = CastInfo({HostServiceInfo(ip, 8009)}, None, None, None, ip, 8009, CAST_TYPE_AUDIO, None)
    return pychromecast.Chromecast(info, tries=2, retry_wait=1, timeout=4)


def get_cast():
    global _cast
    if _cast is not None and not _cast.socket_client.is_alive():
        drop_cast()  # worker thread is gone; pychromecast won't reconnect it
    if _cast is None:
        _cast = connect_speaker(settings.speaker_ip)
        _cast.wait(timeout=10)
    elif not _cast.socket_client.is_connected:
        _cast.wait(timeout=10)  # pychromecast is already reconnecting; let it finish
    return _cast


def drop_cast():
    global _cast
    if _cast is not None:
        # Signal the worker to stop without joining: Chromecast.disconnect(timeout=0) raises if it's still alive.
        _cast.socket_client.disconnect()
        _cast = None


def cast_play(url, content_type, title=None, volume=None, current_time=None, keep_volume=False):
    cast = get_cast()
    if volume is None and not keep_volume:
        volume = settings.default_volume
    if volume is not None:
        cast.set_volume(volume)
    # Other apps (e.g. Spotify) ignore LOAD for arbitrary URLs, so switch receivers first.
    if cast.app_id != DEFAULT_MEDIA_RECEIVER:
        cast.start_app(DEFAULT_MEDIA_RECEIVER)
        cast.wait(timeout=10)
    mc = cast.media_controller
    # BUFFERED (not the LIVE default) so the receiver honours current_time and allows seeking.
    mc.play_media(url, content_type, title=title, current_time=current_time, stream_type="BUFFERED")
    mc.block_until_active(timeout=10)


# --- Resume YouTube after an announcement ---

_resume = None  # track interrupted by an announcement: {"url", "content_type", "title", "position"}
_say_gen = 0  # bumped by every play action so stale resume watchers give up


def capture_youtube():
    """Snapshot the YouTube track (or current queue item) this service is playing, if any."""
    m = get_cast().media_controller.status
    content_id = m.content_id or ""
    from_queue = _queue is not None and content_id == _queue.current_url
    if not (content_id.startswith(f"{base_url()}/yt/") or from_queue):
        return None
    if m.player_state not in ("PLAYING", "BUFFERING"):
        return None
    return {
        "url": m.content_id,
        "content_type": m.content_type,
        "title": m.title,
        "position": max(0.0, m.adjusted_current_time - RESUME_REWIND),
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
        m = await run_cast(lambda: get_cast().media_controller.status)
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
        await run_cast(cast_play, track["url"], track["content_type"], track["title"], None, track["position"])


SPEAKER_ERRORS = (pychromecast.error.PyChromecastError, OSError)


async def run_cast(fn, *args, **kwargs):
    async with cast_lock:
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
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
    global _queue, _queue_gen
    _queue = None
    _queue_gen += 1


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
    guessed = mimetypes.guess_type(urllib.parse.urlparse(item["source"]).path)[0]
    return item["source"], guessed if guessed and guessed.startswith("audio/") else "audio/mpeg"


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


def load_if_current(gen, url, content_type, title, keep_volume):
    if gen != _queue_gen:
        return False  # something else was cast while this load waited for the speaker
    cast_play(url, content_type, title, keep_volume=keep_volume)
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
        if await run_cast(load_if_current, gen, url, content_type, item["title"], keep_volume):
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
    m = await run_cast(lambda: get_cast().media_controller.status)
    if q is not _queue or gen != _queue_gen or m.player_state != "IDLE":
        return
    content_id, reason = m.content_id or "", getattr(m, "idle_reason", None)
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
    elif not (q.after_say and _resume is None and content_id.startswith(f"{base_url()}/tts.mp3")):
        return  # an announcement (or something else) is playing; never advance on its end
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
    m = get_cast().media_controller.status
    if (m.content_id or "") != q.current_url:
        return q.after_say  # back-to-back announcements keep the earlier decision
    if m.player_state in ("PLAYING", "BUFFERING"):
        return True  # replaced without a resume (resume_after_say is off)
    return m.player_state == "IDLE" and getattr(m, "idle_reason", None) == "FINISHED"


def thumbnail_for(content_id):
    if _queue is not None and content_id and content_id == _queue.current_url:
        return _queue.current.get("thumbnail")
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
    kind: Literal["youtube", "url", "tts"]
    source: str
    title: str | None = None
    lang: str | None = None


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


# --- Accounts ---

@app.get("/auth/state")
async def auth_state(who: Caller):
    return {"needs_setup": db.user_count() == 0, "user": who.user if who else None}


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
    user = start_session(request, response, user["id"])
    db.log(user["display_name"], "login ok", f"from {ip}")
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
async def status():
    def read():
        cast = get_cast()
        s, m = cast.status, cast.media_controller.status
        return {
            "speaker": cast.cast_info.friendly_name or settings.speaker_name,
            "ip": settings.speaker_ip,
            "app": s.display_name,
            "volume": round(s.volume_level, 2),
            "muted": s.volume_muted,
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
        }

    return await run_cast(read)


@operator_api.post("/say")
async def say(body: SayBody, who: Who):
    if not body.text.strip():
        raise HTTPException(400, "text is empty")
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
    url = media_url("/tts.mp3", text=body.text, lang=body.lang or settings.tts_lang)
    record(who, "say", body.text.strip()[:80])
    await run_cast(cast_play, url, "audio/mp3", "Announcement", body.volume)
    if _resume:
        spawn(resume_after_announcement(gen, tts_prefix))
    return {"ok": True, "chunks": len(split_text(body.text)), "will_resume": _resume and _resume["title"]}


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
    await run_cast(lambda: get_cast().set_volume(body.level))
    record(who, "volume", f"{round(body.level * 100)}%", coalesce=VOLUME_COALESCE)
    return {"ok": True, "volume": body.level}


@operator_api.post("/pause")
async def pause():
    await run_cast(lambda: get_cast().media_controller.pause())
    return {"ok": True}


@operator_api.post("/resume")
async def resume():
    await run_cast(lambda: get_cast().media_controller.play())
    return {"ok": True}


async def stop_everything():
    cancel_resume()
    clear_queue()
    await run_cast(lambda: get_cast().quit_app())


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
    global settings
    if "api_token" in changes:
        raise HTTPException(400, "api_token can't be changed over the API; rotate it with ./speakerctl token --rotate")
    try:
        new = Settings(**{**settings.model_dump(), **changes})
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    old, settings = settings, new
    save_settings(new)
    record(who, "settings change", ", ".join(f"{k}={v}" for k, v in changes.items())[:500])
    if new.speaker_ip != old.speaker_ip:
        await run_cast(drop_cast)
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
        source = body.source.strip()
        if urllib.parse.urlparse(source).scheme not in ("http", "https") or len(source) > 2000:
            raise HTTPException(400, "source must be an http(s) URL")
        if not title:
            raise HTTPException(400, "title is required for a url item")
        return {"kind": "url", "source": source, "title": title, "duration": None, "thumbnail": None, "lang": None}
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
    global _queue
    playlist = playlist_or_404(db.get_playlist(playlist_id))
    if not playlist["items"]:
        raise HTTPException(400, "The playlist is empty")
    if not 0 <= body.start_index < len(playlist["items"]):
        raise HTTPException(400, "start_index is out of range")
    q = Queue(playlist["items"], playlist["id"], playlist["name"], body.start_index, body.shuffle, body.repeat)
    clear_queue()
    _queue = q
    record(who, "playlist play", playlist["name"])
    try:
        played = await play_queue(q, keep_volume=False)
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


# --- Web UI (public) ---

@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


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
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

for router in (viewer_api, operator_api, admin_api):
    app.include_router(router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.port)
