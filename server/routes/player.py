"""Player: status, announcements, direct plays, volume and transport controls."""
import asyncio
from typing import Annotated

from fastapi import HTTPException, Query
from fastapi.responses import JSONResponse

from server import config, core, livetalk, media, playback
from server.access import Who, content_type_for, media_url, operator_api, record, viewer_api
from server.config import VOLUME_COALESCE
from server.media import prune_cache, yt_skip_segments
from server.playback import cancel_resume, clear_queue, stop_everything, thumbnail_for
from server.schemas import PlayBody, SayBody, SeekBody, VolumeBody, YoutubeBody
from server.speaker import cast_play, run_cast, speaker_state

# --- Player ---

@viewer_api.get("/status")
async def status(who: Who):
    relay = core.transport.relay_status() if who.role == "admin" else None  # relay details are admin-only
    try:
        r, m = await speaker_state()
    except HTTPException as e:
        if relay is None:
            raise
        # Admins still get the relay's health while it (or the speaker behind it) is unreachable.
        return JSONResponse({"detail": e.detail, "relay": core.transport.relay_status()}, status_code=e.status_code)
    result = {
        "speaker": r.name or config.settings.speaker_name,
        "ip": r.ip,
        "app": r.app,
        "volume": round(r.volume, 2) if r.volume is not None else None,
        "muted": r.muted,
        "media": {
            "title": m.title,
            "state": m.player_state,
            "duration": m.duration,
            "position": round(m.adjusted_current_time, 1) if m.current_time is not None else None,
            # live streams have no duration; a relay before firmware 0.2.0 can't seek
            "seekable": bool(m.duration) and m.player_state in ("PLAYING", "PAUSED", "BUFFERING")
                        and core.transport.can_seek(),
            "thumbnail": thumbnail_for(m.content_id),
        },
        "resume_pending": playback._resume and playback._resume["title"],
        "tts_lang": config.settings.tts_lang,
        "queue": playback._queue.summary() if playback._queue is not None else None,
        "talking": livetalk._talk.who.actor if livetalk._talk is not None else None,
    }
    if who.role == "admin":
        result["relay"] = relay
    return result


@operator_api.post("/say")
async def say(body: SayBody, who: Who):
    if not body.text.strip():
        raise HTTPException(400, "text is empty")
    return await playback.announce(body.text, body.lang, body.volume, who)


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
    info = await asyncio.to_thread(media.yt_download, body.query)
    path = info["path"]
    if path.stem == info["id"] and (categories := yt_skip_segments()):
        media.queue_cut(info["id"], path, categories)  # a whole file: play it now, cut it locally for next time
    url = media_url(f"/yt/{path.name}")
    record(who, "youtube", info["title"] or info["id"])
    await run_cast(cast_play, url, content_type_for(path), info["title"], body.volume)
    await asyncio.to_thread(prune_cache)
    return {"ok": True, "id": info["id"], "title": info["title"], "duration": info["duration"]}


@viewer_api.get("/youtube/search")
async def youtube_search(q: Annotated[str, Query(min_length=1, max_length=200)], limit: int = Query(8, ge=1, le=20)):
    return await asyncio.to_thread(media.yt_search, q.strip(), limit)


@operator_api.post("/volume")
async def volume(body: VolumeBody, who: Who):
    if not 0 <= body.level <= 1:
        raise HTTPException(400, "level must be between 0 and 1")
    await run_cast(core.transport.set_volume, body.level)
    record(who, "volume", f"{round(body.level * 100)}%", coalesce=VOLUME_COALESCE)
    return {"ok": True, "volume": body.level}


@operator_api.post("/pause")
async def pause():
    await run_cast(core.transport.pause)
    return {"ok": True}


@operator_api.post("/resume")
async def resume():
    await run_cast(core.transport.resume)
    return {"ok": True}


@operator_api.post("/seek")
async def seek(body: SeekBody):
    """Jump to `position` seconds in what the speaker is playing (not live streams)."""
    if not 0 <= body.position < 86400:
        raise HTTPException(400, "position must be between 0 and 86400 seconds")
    if not core.transport.can_seek():
        raise HTTPException(409, "The relay's firmware can't seek; update it to 0.2.0 or later")
    await run_cast(core.transport.seek, body.position)
    return {"ok": True, "position": body.position}


@operator_api.post("/stop")
async def stop(who: Who):
    record(who, "stop")
    await stop_everything()
    return {"ok": True}
