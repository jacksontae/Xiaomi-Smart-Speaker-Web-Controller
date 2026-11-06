"""YouTube audio: lookups, downloads into the cache, and SponsorBlock cuts of cached files."""
import asyncio
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

import yt_dlp
from fastapi import HTTPException

from server import config, core, outbound, talk
from server.config import AUDIO_SUFFIXES, CACHE_DIR, YT_FORMAT, YT_ID_RE

# --- YouTube ---

def yt_skip_segments():
    """Categories actually cut right now: none when ffmpeg is missing (yt-dlp would fail the download)."""
    return config.settings.yt_skip_segments if config.settings.yt_skip_segments and talk.ffmpeg_available() else []


def yt_cache_stem(video_id, segments):
    """Cache file stem: the bare id for the whole video (the name used before SponsorBlock), else id + a short
    tag of the cut categories, so changing them downloads a fresh copy instead of reusing a differently cut one."""
    if not segments:
        return video_id
    return f"{video_id}.sb-{hashlib.sha256(','.join(sorted(segments)).encode()).hexdigest()[:8]}"


def yt_sponsorblock_opts(segments):
    """yt-dlp postprocessors that look up SponsorBlock segments after the download and cut them with ffmpeg."""
    return [
        {"key": "SponsorBlock", "categories": segments, "when": "post_process"},
        {"key": "ModifyChapters", "remove_sponsor_segments": segments},
    ]


def yt_download(query):
    """Download the audio track into CACHE_DIR (googlevideo rejects proxied Range requests), or return the
    cached file when the video is already there: the cut copy, else the whole one cached before SponsorBlock.

    Only the audio stream is fetched (YT_FORMAT), so YouTube's inserted ads never play; what can remain are
    sponsor reads inside the video itself, which yt_skip_segments cuts out with SponsorBlock after the download.
    """
    target = query if query.startswith(("http://", "https://")) else f"ytsearch1:{query}"
    segments = yt_skip_segments()
    finished = {}  # the downloaded file, kept even when the SponsorBlock step fails afterwards
    opts = {
        "format": YT_FORMAT,
        "outtmpl": str(CACHE_DIR / f"{yt_cache_stem('%(id)s', segments)}.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "js_runtimes": {"node": {}},
        "retries": 5,
        "extractor_retries": 3,
        "progress_hooks": [lambda d: d["status"] == "finished" and finished.update(d)],
    }
    if segments:
        opts["postprocessors"] = yt_sponsorblock_opts(segments)
        opts["ffmpeg_location"] = shutil.which(talk.FFMPEG)  # the same ffmpeg live talk uses ($FFMPEG)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            # Resolve the video first (metadata only) so one already in the cache is never downloaded again.
            info = ydl.extract_info(target, download=False, process=False)
            if "entries" in info:  # search words: the first result
                info = next((e for e in info["entries"] or [] if e), None)
                if info is None:
                    raise HTTPException(404, f"No YouTube result for {query!r}")
            path = cached_track(info["id"]) if YT_ID_RE.fullmatch(info.get("id") or "") else None
            if path:
                path.touch()  # newest mtime keeps it out of prune_cache's way
                return {"id": info["id"], "title": info.get("title"), "duration": info.get("duration"), "path": path}
            info = ydl.process_ie_result(info, download=True)
    except yt_dlp.utils.DownloadError as e:
        uncut = segments and yt_keep_uncut(finished)
        if uncut:
            print(f"SponsorBlock step failed, playing the whole video: {e.msg or e}")
            return uncut
        raise HTTPException(502, f"YouTube download failed: {e.msg or e}") from e
    if "entries" in info:
        if not info["entries"]:
            raise HTTPException(404, f"No YouTube result for {query!r}")
        info = info["entries"][0]
    done = info["requested_downloads"][0]
    duration = done.get("duration") or info.get("duration")  # the cut length when segments were removed
    return {"id": info["id"], "title": info.get("title"), "duration": duration, "path": Path(done["filepath"])}


def yt_keep_uncut(finished):
    """After a failed SponsorBlock step: rename the whole download to the plain cache name and use it as is."""
    path, info = Path(finished.get("filename") or ""), finished.get("info_dict") or {}
    if not finished or not path.is_file() or not YT_ID_RE.fullmatch(info.get("id") or ""):
        return None
    plain = path.with_name(f"{info['id']}{path.suffix}")
    path.replace(plain)
    return {"id": info["id"], "title": info.get("title"), "duration": info.get("duration"), "path": plain}


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
    """The cached file cut with today's categories, else the whole video (every file cached before SponsorBlock
    has the bare-id name, so old caches keep playing without a new download)."""
    stems = list(dict.fromkeys([yt_cache_stem(video_id, yt_skip_segments()), video_id]))
    files = [p for p in CACHE_DIR.glob(f"{video_id}.*") if p.suffix in AUDIO_SUFFIXES]
    for stem in stems:
        for path in files:
            if path.stem == stem:
                return path
    return None


def prune_cache(protect=()):
    # Dot files are cuts still being written (see yt_cut_file).
    files = sorted((p for p in CACHE_DIR.glob("*.*") if not p.name.startswith(".")),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[config.settings.cache_keep:]:
        if old.name not in protect:
            old.unlink(missing_ok=True)


# --- SponsorBlock for files cached before it ---
# A whole-video file (<id>.<ext>) plays at once; a background job then cuts the same local file into the
# <id>.sb-<hash>.<ext> name, so the next play is cut without downloading the video again.

SB_API = os.environ.get("SPONSORBLOCK_API", "https://sponsor.ajay.app")
SB_TIMEOUT = 10  # seconds for the segment lookup
CUT_QUEUE_MAX = 20  # videos waiting to be cut; more are dropped and tried again on a later play
CUT_TIMEOUT = 600  # seconds one ffmpeg run may take
# ffmpeg output format and the re-encode used when a stream copy fails, per cache extension.
CUT_FORMATS = {
    ".m4a": ("mp4", ["-c:a", "aac", "-b:a", "160k"]),
    ".mp4": ("mp4", ["-c:a", "aac", "-b:a", "160k"]),
    ".aac": ("adts", ["-c:a", "aac", "-b:a", "160k"]),
    ".webm": ("webm", ["-c:a", "libopus", "-b:a", "128k"]),
    ".opus": ("ogg", ["-c:a", "libopus", "-b:a", "128k"]),
    ".ogg": ("ogg", ["-c:a", "libopus", "-b:a", "128k"]),
    ".mp3": ("mp3", ["-c:a", "libmp3lame", "-q:a", "2"]),
}
DURATION_RE = re.compile(r"Duration: (\d+):(\d\d):(\d\d(?:\.\d+)?)")
_cuts = {}  # video id -> (whole file, categories): waiting or being cut, oldest first
_cut_worker = None


def queue_cut(video_id, path, categories):
    """Ask for a cut copy of an old whole-video cache file. Never waits; False when already queued or full."""
    global _cut_worker
    if video_id in _cuts or len(_cuts) >= CUT_QUEUE_MAX or path.suffix not in CUT_FORMATS:
        return False
    _cuts[video_id] = (path, list(categories))
    if _cut_worker is None or _cut_worker.done():
        _cut_worker = core.spawn(cut_worker())
    return True


async def cut_worker():
    """Cut the queued files one at a time. A failure is logged and dropped; the next play queues it again."""
    while _cuts:
        video_id, (path, categories) = next(iter(_cuts.items()))
        try:
            await cut_cached(video_id, path, categories)
        except Exception as e:  # noqa: BLE001 - a bad file or lookup must not stop the worker
            print(f"SponsorBlock cut failed for {video_id}: {e!r}")
        finally:
            _cuts.pop(video_id, None)


async def cut_cached(video_id, path, categories):
    target = path.with_name(f"{yt_cache_stem(video_id, categories)}{path.suffix}")
    if target.exists() or not path.is_file() or not talk.ffmpeg_available():
        return
    segments = await sb_segments(video_id, categories)
    removed = await yt_cut_file(path, target, segments)
    print(f"SponsorBlock: {target.name} ready, {removed:.0f}s removed")


async def sb_segments(video_id, categories):
    """Skip segments for one video, asked by the first 4 hex of its SHA-256 so the API never learns which
    video plays (the same lookup yt-dlp makes). Raises on network or server errors."""
    prefix = hashlib.sha256(video_id.encode()).hexdigest()[:4]
    r = await outbound.http.get(f"{SB_API}/api/skipSegments/{prefix}", timeout=SB_TIMEOUT, params={
        "service": "YouTube", "categories": json.dumps(categories), "actionTypes": json.dumps(["skip"])})
    if r.status_code == 404:
        return []  # nothing for any video with this prefix
    r.raise_for_status()
    for entry in r.json():
        if entry.get("videoID") == video_id:
            return entry.get("segments") or []
    return []


def cut_ranges(segments, duration):
    """Merged (start, end) seconds to remove. Like yt-dlp: whole-video labels and segments submitted for a
    different-length version of the video are ignored, and edges within a second snap to the file's ends."""
    ranges = []
    for s in segments:
        start, end = (float(x) for x in s["segment"])
        if end <= start:
            continue  # (0, 0) labels the whole video
        known = s.get("videoDuration") or 0
        if duration and known:
            diff = abs(duration - known)
            if not (diff < 1 or (diff < 5 and diff / (end - start) < 0.05)):
                continue
        start = 0.0 if start <= 1 else start
        end = duration if duration and duration - end <= 1 else end
        ranges.append((start, end))
    merged = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


async def run_niced(args, timeout=CUT_TIMEOUT):
    """Run ffmpeg at the lowest CPU priority; (exit code, stderr). Killed on timeout or cancellation."""
    nice = ["nice", "-n", "19"] if shutil.which("nice") else []
    proc = await asyncio.create_subprocess_exec(
        *nice, shutil.which(talk.FFMPEG) or talk.FFMPEG, "-hide_banner", "-nostdin", *args,
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout)
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
    return proc.returncode, err.decode(errors="replace")


async def media_duration(path):
    """Length in seconds from ffmpeg's header read (ffprobe isn't always installed), or None."""
    _, err = await run_niced(["-i", str(path)], timeout=30)  # no output given: exits 1 after the header
    m = DURATION_RE.search(err)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else None


async def yt_cut_file(path, target, segments):
    """Write `path` minus the segments to `target` (temp file, then rename); returns seconds removed.
    No segments: `target` becomes a hard link to the same file, which records "already checked"."""
    duration = await media_duration(path)
    ranges = cut_ranges(segments, duration)
    if not ranges:
        try:
            os.link(path, target)
        except OSError:
            shutil.copy2(path, target)
        return 0.0
    keep, at = [], 0.0
    for start, end in ranges:
        if start > at:
            keep.append((at, start))
        at = end
    if duration is None or duration - at > 0.05:
        keep.append((at, None))  # to the end
    fmt, encode = CUT_FORMATS[path.suffix]
    tmp = target.with_name(f".{target.name}.part")
    spec = tmp.with_name(f".{target.name}.ffconcat")
    quoted = str(path).replace("'", r"'\''")
    lines = ["ffconcat version 1.0"]
    for start, end in keep:  # the concat demuxer reads only the kept parts of the same file
        lines += [f"file '{quoted}'", f"inpoint {start:.3f}"] + ([f"outpoint {end:.3f}"] if end else [])
    spec.write_text("\n".join(lines) + "\n")
    try:
        base = ["-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(spec), "-map", "0:a", "-vn"]
        out = (["-movflags", "+faststart"] if fmt == "mp4" else []) + ["-f", fmt, "-y", str(tmp)]
        code, err = await run_niced([*base, "-c", "copy", *out])
        if code != 0:  # stream copy refused (odd packet layout): re-encode in the same codec family
            code, err = await run_niced([*base, *encode, *out])
        if code != 0:
            raise RuntimeError(f"ffmpeg exited {code}: {err.strip()[-300:]}")
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)
        spec.unlink(missing_ok=True)
    return sum(end - start for start, end in ranges)
