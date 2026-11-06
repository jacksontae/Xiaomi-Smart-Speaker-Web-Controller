"""What plays: resuming after an announcement, the play queue, and the play actions endpoints and schedules share."""
import asyncio
import itertools
import mimetypes
import re
import urllib.parse
from pathlib import Path

from fastapi import HTTPException

from server import config, core, livetalk, media
from server.access import base_url, content_type_for, media_url, record
from server.config import FILE_TYPES, QUEUE_BACKOFF, QUEUE_POLL, RESUME_TIMEOUT
from server.media import cached_track, prune_cache, yt_skip_segments, yt_thumbnail, yt_watch_url
from server.player import Queue
from server.speaker import cast_play, run_cast, split_text

# --- Resume YouTube after an announcement ---

_resume = None  # track interrupted by an announcement: {"url", "content_type", "title", "position", "live"}
_say_gen = 0  # bumped by every play action so stale resume watchers give up
_direct = None  # radio station, podcast episode or file started outside the queue: {"url", "live", "thumbnail"}


def capture_youtube():
    """Snapshot the YouTube track, queue item or other source this service is playing, if any."""
    m = core.transport.media()
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
        "position": None if live else max(0.0, m.adjusted_current_time - config.RESUME_REWIND),
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
        m = await run_cast(core.transport.media)
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


# --- Play queue ---

_queue: Queue | None = None
_queue_gen = 0  # bumped whenever the queue moves or is replaced, so stale loads give up
_downloads = {}  # video id -> download task, so a prefetch and a play never download the same file twice
_watcher = None
_nonce = itertools.count()  # makes every queue load's URL unique, even a repeated track


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
        if path.stem == video_id and (categories := yt_skip_segments()):
            media.queue_cut(video_id, path, categories)  # cached before SponsorBlock: play it now, cut it for next time
        return path
    task = _downloads.get(video_id)
    if task is None:
        task = asyncio.create_task(asyncio.to_thread(media.yt_download, yt_watch_url(video_id)))
        _downloads[video_id] = task
        task.add_done_callback(lambda _: _downloads.pop(video_id, None))
    return (await asyncio.shield(task))["path"]


async def queue_media(item, sign=media_url):
    """(url, content_type) the speaker loads for a queue item. `sign=media_path` gives this server's own links
    relative, for a browser playing on "This device"."""
    nonce = next(_nonce)
    if item["kind"] == "youtube":
        path = await ensure_track(item["source"])
        return sign(f"/yt/{path.name}", n=nonce), content_type_for(path)
    if item["kind"] == "tts":
        lang = item["lang"] or config.settings.tts_lang
        return sign("/tts.mp3", text=item["source"], lang=lang, n=nonce), "audio/mp3"
    if item["kind"] == "file":
        row = core.db.get_file(int(item["source"])) if item["source"].isdigit() else None
        if row is None or not (config.MEDIA_DIR / row["stored_name"]).is_file():
            raise HTTPException(404, "The uploaded file is gone")
        return sign(f"/media/{row['stored_name']}", n=nonce), row["content_type"]
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
        core.spawn(prefetch(item["source"]))


def skip_failed(q, reason):
    """Log and step past the current item. False when the queue should stop."""
    core.db.log("system", "queue skip", f"{q.current['title']}: {reason}")
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
    m = await run_cast(core.transport.media)
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
    elif not (q.after_say and _resume is None and livetalk._talk_on_speaker is None
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
        _watcher = core.spawn(queue_watch())


def queue_after_say(q):
    """Whether the queue should move on once an announcement ends (its track won't be resumed)."""
    m = core.transport.media()
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


# --- Play actions shared by the endpoints and the schedules ---

async def announce(text, lang, volume, who):
    """Speak `text`, then resume the interrupted track or let the queue continue (POST /say and schedules)."""
    global _resume, _say_gen
    tts_prefix = f"{base_url()}/tts.mp3"
    if config.settings.resume_after_say:
        # Keep an already-pending track when announcements are back to back.
        _resume = await run_cast(capture_youtube) or _resume
    q = _queue
    if q is not None:
        q.after_say = _resume is None and await run_cast(queue_after_say, q)
    _say_gen += 1
    gen = _say_gen
    url = media_url("/tts.mp3", text=text, lang=lang or config.settings.tts_lang)
    record(who, "say", text.strip()[:80])
    await run_cast(cast_play, url, "audio/mp3", "Announcement", volume)
    if _resume:
        core.spawn(resume_after_announcement(gen, tts_prefix))
    return {"ok": True, "chunks": len(split_text(text)), "will_resume": _resume and _resume["title"]}


async def stop_everything():
    cancel_resume()
    clear_queue()
    await run_cast(core.transport.stop)


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
            await run_cast(core.transport.set_volume, volume)
        played = await play_queue(q, keep_volume=volume is not None)
    except HTTPException:
        end_queue(q)
        raise
    if not played:
        raise HTTPException(502, "None of the playlist's items could be played")
    ensure_queue_watcher()
    return q.summary()


async def play_source(url, content_type, title, volume, who, action, live=False, thumbnail=None):
    """Play a radio station, podcast episode or uploaded file outside the queue (announcements resume it)."""
    global _direct
    cancel_resume()
    clear_queue()
    _direct = {"url": url, "live": live, "thumbnail": thumbnail}
    record(who, action, title[:200])
    await run_cast(cast_play, url, content_type, title, volume, live=live)
    return {"ok": True, "title": title}
