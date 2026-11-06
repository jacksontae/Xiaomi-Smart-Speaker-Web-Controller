"""This device: play in the browser instead of on the speaker, with a relay for streams it can't fetch."""
import asyncio
import re
import time
import urllib.parse
from pathlib import Path

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from server import config, core, outbound
from server.access import Who, media_path, public_api, record, verify_media, viewer_api
from server.accounts import can_see
from server.config import (
    HLS_MAX_BYTES,
    STATION_UUID_RE,
    STREAM_MAX_OPEN,
    STREAM_REDIRECTS,
    TTS_TEXT_MAX,
    USER_AGENT,
    YT_ID_RE,
)
from server.media import prune_cache, yt_info, yt_thumbnail
from server.outbound import check_public_url
from server.playback import _nonce, queue_media
from server.schemas import ItemBody, clean_text
from server.sources import audio_type, http_url, optional_http_url, radio_station

# --- This device: play in the browser instead of on the speaker ---

async def local_item(body, who):
    """A playlist-style item (kind, source, title, lang, thumbnail, duration, content_type) checked like
    build_item, but without the metadata lookups a browser already has; YouTube words or URLs are looked up."""
    title = body.title.strip()[:200] if body.title and body.title.strip() else None
    item = {"kind": body.kind, "title": title, "duration": body.duration, "lang": None,
            "thumbnail": optional_http_url(body.thumbnail), "content_type": audio_type(body.content_type)}
    if body.kind == "youtube":
        source = clean_text(body.source, "source", 500)
        if not YT_ID_RE.fullmatch(source):
            meta = await asyncio.to_thread(yt_info, source)
            source, title = meta["video_id"], title or meta["title"]
            item["duration"] = item["duration"] or meta["duration"]
        return {**item, "source": source, "title": title, "thumbnail": yt_thumbnail(source)}
    if body.kind == "tts":
        text = clean_text(body.source, "source", TTS_TEXT_MAX)
        return {**item, "source": text, "title": title or text[:60],
                "lang": (body.lang or config.settings.tts_lang)[:16]}
    if body.kind == "file":
        row = core.db.get_file(int(body.source)) if body.source.strip().isdigit() else None
        if row is None or not can_see(row, who):
            raise HTTPException(404, "No such file")
        return {**item, "source": str(row["id"]), "title": title or row["title"],
                "duration": item["duration"] or row["duration"]}
    if body.kind == "radio" and STATION_UUID_RE.fullmatch(body.source.strip()):
        station = await radio_station(body.source.strip())
        return {**item, "source": station["url"], "title": title or station["name"],
                "thumbnail": item["thumbnail"] or station["favicon"], "content_type": station["content_type"]}
    return {**item, "source": http_url(body.source, "source")}  # url, podcast, radio stream URL


def local_proxy_path(item, url, content_type):
    """A signed link relaying `url` through this server, for streams a browser can't fetch itself (http:// on an
    https page, a type it doesn't know): /local/stream, or /local/hls for an HLS playlist. None for this server's
    own links."""
    if url.startswith("/"):
        return None
    if "mpegurl" in (content_type or "") or is_hls_url(url):
        return media_path("/local/hls", u=url, n=next(_nonce))
    return media_path("/local/stream", u=url, t=content_type or "", n=next(_nonce))


def is_hls_url(url):
    return urllib.parse.urlsplit(url).path.lower().endswith(".m3u8")


@viewer_api.post("/local/resolve")
async def local_resolve(body: ItemBody, who: Who):
    """A link this browser can play itself when "This device" is its output: the same signed media links the
    speaker gets (relative to this server), or the item's own stream URL plus a relayed one (`proxy_url`).
    The speaker is never contacted. Open to viewers: it plays only on their own device. Not logged here, since
    a browser also asks ahead for the next track and again when a long pause outlived a link: POST /local/played.
    A `file` must be one the caller may see."""
    item = await local_item(body, who)
    url, content_type = await queue_media(item, sign=media_path)
    if item["kind"] == "youtube":
        await asyncio.to_thread(prune_cache, {Path(urllib.parse.urlsplit(url).path).name})
    return {"kind": item["kind"], "url": url, "content_type": content_type,
            "proxy_url": local_proxy_path(item, url, content_type),
            "title": item["title"], "duration": item["duration"], "thumbnail": item["thumbnail"],
            "live": item["kind"] == "radio"}


class LocalPlayedBody(BaseModel):
    title: str = Field(min_length=1, max_length=500)


@viewer_api.post("/local/played", status_code=204)
async def local_played(body: LocalPlayedBody, who: Who):
    """Activity entry for something a person started on "This device" (one per tap, not per track: the browser
    calls this when a play it was asked for starts, never when its queue moves on by itself)."""
    title = " ".join(body.title.split())[:200]
    if not title:
        raise HTTPException(400, "title is empty")
    record(who, "device play", title)


# Stream types the relay passes on (anything else, like an HTML error page, is refused: it would be served from
# this origin) and the odd names some radio servers use for common ones.
STREAM_TYPES = ("audio/", "application/ogg", "video/mp4", "video/webm")
STREAM_TYPE_ALIASES = {"audio/aacp": "audio/aac", "audio/x-aac": "audio/aac", "audio/mp3": "audio/mpeg",
                       "audio/x-mp3": "audio/mpeg", "audio/x-mpeg": "audio/mpeg", "audio/mpeg3": "audio/mpeg"}
# ... and what the parts of an HLS stream may also be: MPEG-TS segments, fMP4 init sections, AES keys
HLS_PART_TYPES = ("video/mp2t", "application/mp4", "application/octet-stream", "binary/octet-stream")
# Tags whose URI="..." names another playlist (the others name a segment, a key or an init section).
HLS_PLAYLIST_TAGS = ("#EXT-X-MEDIA:", "#EXT-X-I-FRAME-STREAM-INF:", "#EXT-X-RENDITION-REPORT:")
HLS_URI_RE = re.compile(r'URI="([^"]*)"')
_streams_open = 0


def stream_type(upstream, expected, part=False):
    """The content type to send for a relayed stream (or HLS part), or None when it isn't audio."""
    value = (upstream or "").split(";")[0].strip().lower()
    if part:
        value = value or "application/octet-stream"
    elif value in ("", "application/octet-stream"):
        value = (expected or "").strip().lower() or "audio/mpeg"
    value = STREAM_TYPE_ALIASES.get(value, value)
    return value if value.startswith(STREAM_TYPES + (HLS_PART_TYPES if part else ())) else None


async def open_stream(url, range_header):
    """The upstream response (streaming, not read yet), following redirects by hand so each hop is checked."""
    headers = {"User-Agent": USER_AGENT, "Accept": "audio/*, */*;q=0.5"}
    if range_header:
        headers["Range"] = range_header
    for _ in range(STREAM_REDIRECTS + 1):
        url = http_url(url, "stream")
        await asyncio.to_thread(check_public_url, url, "stream")
        try:
            client = outbound.stream_http
            r = await client.send(client.build_request("GET", url, headers=headers), stream=True)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"The stream is unreachable ({type(e).__name__})") from e
        if not (r.is_redirect and r.headers.get("location")):
            return r
        await r.aclose()
        url = urllib.parse.urljoin(url, r.headers["location"])
    raise HTTPException(502, "The stream redirects too many times")


@public_api.get("/local/stream", dependencies=[Depends(verify_media)])
async def local_stream(request: Request, u: str, t: str = "", h: str = ""):
    """Relay a radio stream or audio link for "This device" (signed link from POST /local/resolve, so only a
    signed-in member gets one). Bytes are passed on as they arrive, never stored; only public http(s) hosts.
    `h=1` (signed links in a playlist from GET /local/hls): an HLS segment, key or init section."""
    global _streams_open
    if _streams_open >= STREAM_MAX_OPEN:
        raise HTTPException(503, "Too many streams are being relayed right now")
    _streams_open += 1
    try:
        r = await open_stream(u, request.headers.get("range"))
    except BaseException:
        _streams_open -= 1
        raise
    content_type = stream_type(r.headers.get("content-type"), t, part=h == "1")
    if r.status_code not in (200, 206) or content_type is None:
        await r.aclose()
        _streams_open -= 1
        if content_type is None and r.status_code in (200, 206):
            raise HTTPException(502, "The link didn't send audio")
        raise HTTPException(502, f"The stream failed: HTTP {r.status_code}")
    headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
               "Content-Security-Policy": "sandbox"}
    # passing the encoded length on would be wrong once httpx has decoded a compressed body
    keep = ("content-range", "accept-ranges") if r.headers.get("content-encoding") else \
        ("content-length", "content-range", "accept-ranges")
    headers.update({k: r.headers[k] for k in keep if k in r.headers})

    closed = False

    async def close():
        """Once, from the relay's end or after the response (a client gone before the first byte)."""
        global _streams_open
        nonlocal closed
        if not closed:
            closed = True
            _streams_open -= 1
            await r.aclose()

    async def relay():
        sent, ends = 0, time.monotonic() + config.STREAM_MAX_SECONDS
        try:
            async for chunk in r.aiter_bytes():
                sent += len(chunk)
                if sent > config.STREAM_MAX_BYTES or time.monotonic() > ends:
                    break  # the browser sees the stream end and asks for a fresh link
                yield chunk
        except httpx.HTTPError:
            pass  # the upstream stalled or dropped: end the relay
        finally:
            await close()

    return StreamingResponse(relay(), status_code=r.status_code, media_type=content_type, headers=headers,
                             background=BackgroundTask(close))


def hls_link(uri, base, playlist):
    """A signed relay link for a URI in an HLS playlist fetched from `base`: /local/hls for another playlist,
    /local/stream for a segment, key or init section. Non-http URIs (skd://) stay as they are."""
    url = urllib.parse.urljoin(base, uri.strip())
    if urllib.parse.urlsplit(url).scheme not in ("http", "https") or len(url) > 2000:
        return uri
    return media_path("/local/hls", u=url) if playlist else media_path("/local/stream", u=url, h="1")


def hls_rewrite(text, base):
    """The playlist with every link in it pointing at this server's relay."""
    master = "#EXT-X-STREAM-INF" in text  # its URI lines are variant playlists, not segments
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXT-X-SERVER-CONTROL"):
            continue  # blocking reloads add query parameters, which the signed links refuse
        if line.startswith("#"):
            playlist = line.startswith(HLS_PLAYLIST_TAGS)
            line = HLS_URI_RE.sub(lambda m, p=playlist: f'URI="{hls_link(m.group(1), base, p)}"', line)
        elif line:
            line = hls_link(line, base, master)
        lines.append(line)
    return "\n".join(lines) + "\n"


@public_api.get("/local/hls", dependencies=[Depends(verify_media)])
async def local_hls(u: str):
    """An HLS playlist for "This device" with its links turned into signed relay links (segments, keys and init
    sections through /local/stream, variant playlists through here again), so a browser that plays HLS can play
    an http:// station on an https:// page. Signed links only; public http(s) hosts only, each hop checked."""
    r = await open_stream(u, None)
    try:
        if r.status_code != 200:
            raise HTTPException(502, f"The playlist failed: HTTP {r.status_code}")
        body = bytearray()
        async for chunk in r.aiter_bytes():
            body += chunk
            if len(body) > HLS_MAX_BYTES:
                raise HTTPException(502, "The playlist is too large")
    except httpx.HTTPError as e:
        raise HTTPException(502, f"The playlist is unreachable ({type(e).__name__})") from e
    finally:
        await r.aclose()
    text = body.decode("utf-8", "replace").lstrip("\ufeff \t\r\n")
    if not text.startswith("#EXTM3U"):
        raise HTTPException(502, "The link isn't an HLS playlist")
    return Response(hls_rewrite(text, str(r.url)), media_type="application/vnd.apple.mpegurl",
                    headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                             "Content-Security-Policy": "sandbox"})
