"""HTTP service that makes a Google Cast speaker announce text and play YouTube audio.

The speaker fetches every stream from this service (TTS and YouTube are proxied),
so it only needs to reach this machine on the LAN.
"""
import asyncio
import json
import os
import socket
import urllib.parse
from pathlib import Path

import httpx
import pychromecast
import pychromecast.discovery
import pychromecast.error
import yt_dlp
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from pychromecast.const import CAST_TYPE_AUDIO
from pychromecast.models import CastInfo, HostServiceInfo
from pydantic import BaseModel, Field

ROOT = Path(__file__).parent
CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", ROOT / "config.json"))
DEFAULT_MEDIA_RECEIVER = "CC1AD845"
TTS_CHUNK = 180  # Google Translate TTS rejects queries longer than ~200 chars
YT_FORMAT = os.environ.get("YT_FORMAT", "bestaudio[ext=m4a]/bestaudio")
CACHE_DIR = Path(os.environ.get("CACHE_DIR", ROOT / "cache"))
CACHE_DIR.mkdir(exist_ok=True)
RESUME_REWIND = 1.0  # seconds replayed before the interruption point
RESUME_TIMEOUT = 300  # give up resuming if an announcement runs longer than this


class Settings(BaseModel):
    speaker_ip: str = "192.168.2.48"
    speaker_name: str = "Air Purifier speaker"
    port: int = Field(8090, ge=1024, le=65535)
    default_volume: float | None = Field(None, ge=0, le=1)  # None = keep the speaker's volume
    tts_lang: str = "th"
    cache_keep: int = Field(20, ge=1)  # most recent YouTube tracks kept on disk
    resume_after_say: bool = True  # continue the interrupted YouTube track after /say
    public_base_url: str | None = None  # override when auto-detected LAN address is wrong


def load_settings():
    if CONFIG_PATH.exists():
        return Settings(**json.loads(CONFIG_PATH.read_text()))
    s = Settings()
    save_settings(s)
    return s


def save_settings(s):
    CONFIG_PATH.write_text(json.dumps(s.model_dump(), indent=2, ensure_ascii=False) + "\n")


settings = load_settings()
app = FastAPI(title="Speaker Service")
http = httpx.AsyncClient(timeout=30, follow_redirects=True)
cast_lock = asyncio.Lock()
_cast = None


def content_type_for(path):
    return {".webm": "audio/webm", ".mp3": "audio/mpeg"}.get(path.suffix, "audio/mp4")


def host_ip():
    """The LAN address the speaker can use to reach this machine."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((settings.speaker_ip, 8009))
        return s.getsockname()[0]


def base_url():
    return settings.public_base_url or f"http://{host_ip()}:{settings.port}"


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


def cast_play(url, content_type, title=None, volume=None, current_time=None):
    cast = get_cast()
    if volume is None:
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
    """Snapshot the YouTube track this service is playing, if any."""
    m = get_cast().media_controller.status
    if not (m.content_id or "").startswith(f"{base_url()}/yt/"):
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


def prune_cache():
    files = sorted(CACHE_DIR.glob("*.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[settings.cache_keep:]:
        old.unlink(missing_ok=True)


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


@app.get("/status")
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
            },
            "resume_pending": _resume and _resume["title"],
        }

    return await run_cast(read)


@app.post("/say")
async def say(body: SayBody):
    if not body.text.strip():
        raise HTTPException(400, "text is empty")
    global _resume, _say_gen
    q = urllib.parse.urlencode({"text": body.text, "lang": body.lang or settings.tts_lang})
    tts_prefix = f"{base_url()}/tts.mp3"
    if settings.resume_after_say:
        # Keep an already-pending track when announcements are back to back.
        _resume = await run_cast(capture_youtube) or _resume
    _say_gen += 1
    gen = _say_gen
    await run_cast(cast_play, f"{tts_prefix}?{q}", "audio/mp3", "Announcement", body.volume)
    if _resume:
        asyncio.create_task(resume_after_announcement(gen, tts_prefix))
    return {"ok": True, "chunks": len(split_text(body.text)), "will_resume": _resume and _resume["title"]}


@app.post("/play")
async def play(body: PlayBody):
    cancel_resume()
    await run_cast(cast_play, body.url, body.content_type, None, body.volume)
    return {"ok": True}


@app.post("/youtube")
async def youtube(body: YoutubeBody):
    cancel_resume()
    info = await asyncio.to_thread(yt_download, body.query)
    path = info["path"]
    await run_cast(cast_play, f"{base_url()}/yt/{path.name}", content_type_for(path), info["title"], body.volume)
    await asyncio.to_thread(prune_cache)
    return {"ok": True, "id": info["id"], "title": info["title"], "duration": info["duration"]}


@app.post("/volume")
async def volume(body: VolumeBody):
    if not 0 <= body.level <= 1:
        raise HTTPException(400, "level must be between 0 and 1")
    await run_cast(lambda: get_cast().set_volume(body.level))
    return {"ok": True, "volume": body.level}


@app.get("/settings")
async def get_settings():
    return settings


@app.post("/settings")
async def update_settings(changes: dict, background: BackgroundTasks):
    """Partial update. Changing the port restarts the process; launchd brings it back up."""
    global settings
    try:
        new = Settings(**{**settings.model_dump(), **changes})
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    old, settings = settings, new
    save_settings(new)
    if new.speaker_ip != old.speaker_ip:
        await run_cast(drop_cast)
    restart = new.port != old.port
    if restart:
        background.add_task(lambda: os._exit(0))
    return {"ok": True, "restart": restart, "settings": new}


@app.get("/speakers")
async def speakers():
    def discover():
        found, browser = pychromecast.discovery.discover_chromecasts(timeout=4)
        browser.stop_discovery()
        return [{"name": c.friendly_name, "ip": c.host, "model": c.model_name} for c in found]

    return await asyncio.to_thread(discover)


@app.post("/pause")
async def pause():
    await run_cast(lambda: get_cast().media_controller.pause())
    return {"ok": True}


@app.post("/resume")
async def resume():
    await run_cast(lambda: get_cast().media_controller.play())
    return {"ok": True}


@app.post("/stop")
async def stop():
    cancel_resume()
    await run_cast(lambda: get_cast().quit_app())
    return {"ok": True}


# --- Streams fetched by the speaker itself ---

@app.get("/tts.mp3")
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


@app.get("/yt/{filename}")
async def yt_file(filename: str):
    path = CACHE_DIR / Path(filename).name
    if not path.is_file():
        raise HTTPException(404, "not cached")
    return FileResponse(path, media_type=content_type_for(path))


@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse(ROOT / "static" / "index.html")




if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.port)
