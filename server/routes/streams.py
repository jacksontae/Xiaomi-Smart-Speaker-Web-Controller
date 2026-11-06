"""Streams the speaker fetches itself (signed URLs, no header): TTS, cached YouTube audio, files and talks."""
import re
import time
from functools import cache
from pathlib import Path
from typing import Literal

from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from server import config, livetalk, outbound, talk
from server.access import content_type_for, public_api, verify_media
from server.config import CACHE_DIR, FILE_TYPES
from server.speaker import split_text

# --- Streams fetched by the speaker itself (signed URLs, no header) ---

@public_api.get("/tts.mp3", dependencies=[Depends(verify_media)])
async def tts(request: Request, text: str, lang: str = "th"):
    audio = b""
    for chunk in split_text(text):
        r = await outbound.http.get(
            "https://translate.google.com/translate_tts",
            params={"ie": "UTF-8", "client": "tw-ob", "tl": lang, "q": chunk},
        )
        if r.status_code != 200:
            raise HTTPException(502, f"TTS failed: HTTP {r.status_code}")
        audio += r.content  # MP3 frames concatenate cleanly
    # browsers only seek a file that answers Range requests ("This device")
    headers = {"Accept-Ranges": "bytes"}
    wanted = re.fullmatch(r"bytes=(\d+)-(\d*)", request.headers.get("range", ""))
    if not wanted or int(wanted[1]) >= len(audio):
        return Response(audio, media_type="audio/mpeg", headers=headers)
    start, end = int(wanted[1]), min(int(wanted[2] or len(audio) - 1), len(audio) - 1)
    headers["Content-Range"] = f"bytes {start}-{end}/{len(audio)}"
    return Response(audio[start:end + 1], status_code=206, media_type="audio/mpeg", headers=headers)


@public_api.get("/yt/{filename}", dependencies=[Depends(verify_media)])
async def yt_file(filename: str):
    path = CACHE_DIR / Path(filename).name
    if not path.is_file():
        raise HTTPException(404, "not cached")
    return FileResponse(path, media_type=content_type_for(path))


@public_api.get("/media/{filename}", dependencies=[Depends(verify_media)])
async def media_file(filename: str):
    path = config.MEDIA_DIR / Path(filename).name
    if path.name.startswith(".") or not path.is_file():
        raise HTTPException(404, "No such file")
    return FileResponse(path, media_type=FILE_TYPES.get(path.suffix, "application/octet-stream"))


@public_api.get("/talk/chime.wav", dependencies=[Depends(verify_media)])
async def talk_chime(tone: Literal["start", "end"] = "start"):
    return Response(chime_bytes(tone), media_type="audio/wav")


@cache
def chime_bytes(tone):
    return talk.chime_wav(tone)


@public_api.get("/talk/{talk_id}/live", dependencies=[Depends(verify_media)])
async def talk_live(talk_id: str):
    """The talk's MP3 as one endless response; it ends when the talk does."""
    session = livetalk._talk if livetalk._talk is not None and livetalk._talk.id == talk_id else livetalk._talk_last
    recent = session is not None and (session.ended_at is None
                                      or time.monotonic() - session.ended_at < config.TALK_GRACE)
    if not recent or session.id != talk_id:
        raise HTTPException(404, "No such live talk")
    return StreamingResponse(session.stream.follow(), media_type="audio/mpeg",
                             headers={"Cache-Control": "no-store"})
