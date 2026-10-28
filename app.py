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
import yt_dlp
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
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


def get_cast():
    global _cast
    if _cast is None or not _cast.socket_client.is_connected:
        drop_cast()
        _cast = pychromecast.get_chromecast_from_host((settings.speaker_ip, 8009, None, None, None))
        _cast.wait(timeout=10)
    return _cast


def drop_cast():
    global _cast
    if _cast is not None:
        _cast.disconnect(blocking=False)
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
    loop = asyncio.get_running_loop()
    deadline = loop.time() + RESUME_TIMEOUT
    while loop.time() < deadline:
        await asyncio.sleep(0.5)
        if gen != _say_gen:
            return  # a newer action took over
        m = get_cast().media_controller.status
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


async def run_cast(fn, *args, **kwargs):
    async with cast_lock:
        return await asyncio.to_thread(fn, *args, **kwargs)


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
        raise HTTPException(422, str(e))
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
    return INDEX_HTML


INDEX_HTML = """<!doctype html>
<html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Speaker Control</title>
<style>
:root{--bg:#f6f6f4;--card:#fff;--fg:#1d1d1f;--muted:#6b6b70;--accent:#2f6fde;--line:#e2e2e0}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--card:#1f1f22;--fg:#f2f2f2;--muted:#9a9aa0;--accent:#6b9bf0;--line:#323236}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
main{max-width:520px;margin:0 auto;padding:24px 16px}
h1{font-size:20px;margin:0 0 4px}#st{color:var(--muted);font-size:14px;margin-bottom:20px}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:14px}
label{display:block;font-weight:600;margin-bottom:8px}
textarea,input[type=text]{width:100%;box-sizing:border-box;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg);font:inherit}
button{margin-top:10px;padding:9px 16px;border:0;border-radius:8px;background:var(--accent);color:#fff;font:inherit;cursor:pointer}
button.alt{background:transparent;color:var(--fg);border:1px solid var(--line)}
.row{display:flex;gap:8px;flex-wrap:wrap}input[type=range]{width:100%}
#msg{color:var(--muted);font-size:14px;min-height:1.5em}
</style></head><body><main>
<h1>Speaker Control</h1><div id="st">กำลังโหลด…</div>
<section><label for="t">ประกาศข้อความ</label><textarea id="t" rows="3">สวัสดีครับ</textarea>
<button onclick="call('/say',{text:t.value})">ประกาศ</button></section>
<section><label for="q">YouTube (คำค้นหรือลิงก์)</label><input id="q" type="text" placeholder="เช่น เพลงบรรเลงเปียโน">
<button onclick="call('/youtube',{query:q.value})">เล่นในลำโพง</button></section>
<section><label for="v">ระดับเสียง <span id="vl"></span></label>
<input id="v" type="range" min="0" max="1" step="0.05" onchange="call('/volume',{level:+v.value})">
<div class="row"><button class="alt" onclick="call('/pause')">พัก</button><button class="alt" onclick="call('/resume')">เล่นต่อ</button><button class="alt" onclick="call('/stop')">หยุด</button></div></section>
<details><summary>ตั้งค่า</summary><section style="margin-top:10px">
<label for="sp">ลำโพง</label><div class="row"><select id="sp" style="flex:1;padding:9px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--fg);font:inherit"></select><button class="alt" style="margin-top:0" onclick="scan()">ค้นหา</button></div>
<label for="dv" style="margin-top:12px">ระดับเสียงเริ่มต้นตอนประกาศ/เล่น <span id="dvl"></span></label>
<div class="row" style="align-items:center"><input id="dv" type="range" min="0" max="1" step="0.05" style="flex:1" oninput="dvl.textContent=Math.round(dv.value*100)+'%'"><label style="font-weight:400;margin:0"><input id="keep" type="checkbox" onchange="dv.disabled=keep.checked;dvl.textContent=keep.checked?'(ไม่เปลี่ยน)':Math.round(dv.value*100)+'%'"> ใช้ค่าเดิมของลำโพง</label></div>
<label for="lg" style="margin-top:12px">ภาษา TTS</label><select id="lg" style="width:100%;padding:9px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--fg);font:inherit"><option value="th">ไทย</option><option value="en">English</option><option value="zh-CN">中文</option><option value="ja">日本語</option></select>
<label for="pt" style="margin-top:12px">พอร์ต (เปลี่ยนแล้ว service จะรีสตาร์ท)</label><input id="pt" type="text" inputmode="numeric">
<label for="ck" style="margin-top:12px">จำนวนเพลง YouTube ที่เก็บ cache</label><input id="ck" type="text" inputmode="numeric">
<label style="margin-top:12px;font-weight:400"><input id="rs" type="checkbox"> ประกาศเสร็จแล้วเล่นเพลง YouTube ต่อ</label>
<button onclick="saveSettings()">บันทึก</button></section></details>
<div id="msg"></div>
<script>
async function call(p,b){msg.textContent='กำลังส่ง…';try{const r=await fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});const j=await r.json();msg.textContent=r.ok?('สำเร็จ'+(j.title?': '+j.title:'')):('ผิดพลาด: '+(j.detail||r.status))}catch(e){msg.textContent='ผิดพลาด: '+e}setTimeout(load,800)}
async function load(){try{const s=await(await fetch('/status')).json();st.textContent=`${s.speaker} · ${s.app||'ว่าง'}${s.media.title?' · '+s.media.title:''} · ${s.media.state||''}`;v.value=s.volume;vl.textContent=Math.round(s.volume*100)+'%'}catch(e){st.textContent='เชื่อมต่อลำโพงไม่ได้'}}
let cfg={};
function opt(ip,name){const o=document.createElement('option');o.value=ip;o.textContent=`${name} (${ip})`;o.dataset.name=name;return o}
async function loadSettings(){cfg=await(await fetch('/settings')).json();sp.replaceChildren(opt(cfg.speaker_ip,cfg.speaker_name));keep.checked=cfg.default_volume===null;dv.value=cfg.default_volume??0.3;keep.onchange();lg.value=cfg.tts_lang;pt.value=cfg.port;ck.value=cfg.cache_keep;rs.checked=cfg.resume_after_say}
async function scan(){msg.textContent='กำลังค้นหาลำโพง…';const l=await(await fetch('/speakers')).json();sp.replaceChildren(...l.map(s=>opt(s.ip,s.name)));if(!l.some(s=>s.ip===cfg.speaker_ip))sp.prepend(opt(cfg.speaker_ip,cfg.speaker_name));sp.value=cfg.speaker_ip;msg.textContent=`พบ ${l.length} เครื่อง`}
async function saveSettings(){const o=sp.selectedOptions[0];const b={speaker_ip:sp.value,speaker_name:o.dataset.name,default_volume:keep.checked?null:+dv.value,tts_lang:lg.value,port:+pt.value,cache_keep:+ck.value,resume_after_say:rs.checked};
const r=await fetch('/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});const j=await r.json();
if(!r.ok){msg.textContent='ผิดพลาด: '+j.detail;return}
if(j.restart){msg.textContent='บันทึกแล้ว กำลังย้ายไปพอร์ต '+b.port+'…';setTimeout(()=>location.port=b.port,4000);return}
cfg=j.settings;msg.textContent='บันทึกการตั้งค่าแล้ว';load()}
load();loadSettings();setInterval(load,5000);
</script></main></body></html>"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.port)
