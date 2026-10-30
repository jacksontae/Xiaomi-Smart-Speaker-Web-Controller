"""Cutting SponsorBlock segments out of files cached before SponsorBlock (fake API; real ffmpeg when installed)."""
import asyncio
import hashlib
import json
import shutil
import subprocess

import httpx
import pytest
from conftest import REAL_QUEUE_CUT

VID = "abcdefghijk"
HAS_FFMPEG = shutil.which("ffmpeg") is not None


@pytest.fixture(autouse=True)
def clean(app, monkeypatch):
    for p in app.CACHE_DIR.glob("*"):
        p.unlink()
    app._cuts.clear()
    monkeypatch.setattr(app, "_cut_worker", None)
    monkeypatch.setattr(app, "queue_cut", REAL_QUEUE_CUT)  # conftest only records cuts elsewhere
    monkeypatch.setattr(app.talk, "ffmpeg_available", lambda: True)


@pytest.fixture
def sponsorblock(app, monkeypatch):
    """Fake SponsorBlock API: `segments` answers for VID; `status` forces an error; `calls` records requests."""
    api = {"segments": [], "status": 200, "calls": []}

    def handler(request):
        api["calls"].append(request.url)
        if api["status"] != 200:
            return httpx.Response(api["status"])
        other = {"videoID": "zzzzzzzzzzz", "segments": [{"segment": [0, 50], "category": "sponsor"}]}
        return httpx.Response(200, json=[other, {"videoID": VID, "segments": api["segments"]}])

    monkeypatch.setattr(app, "http", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return api


def cut_name(app, suffix=".m4a"):
    return app.CACHE_DIR / f"{app.yt_cache_stem(VID, app.settings.yt_skip_segments)}{suffix}"


async def drain(app):
    while app._cut_worker is not None and not app._cut_worker.done():
        await asyncio.sleep(0.01)


def test_play_is_not_blocked_and_cut_is_deduplicated(app, monkeypatch):
    legacy = app.CACHE_DIR / f"{VID}.m4a"
    legacy.write_bytes(b"x")
    started = []

    async def slow_cut(video_id, path, categories):
        started.append(video_id)
        await asyncio.sleep(3600)

    monkeypatch.setattr(app, "cut_cached", slow_cut)

    async def scenario():
        first = await asyncio.wait_for(app.ensure_track(VID), 1)
        second = await asyncio.wait_for(app.ensure_track(VID), 1)
        await asyncio.sleep(0.05)
        waiting = list(app._cuts)
        app._cut_worker.cancel()
        return first, second, waiting

    first, second, waiting = asyncio.run(scenario())
    assert first == second == legacy  # the whole file plays right away
    assert started == [VID] and waiting == [VID]  # one job however often it is played


def test_not_queued_when_off_or_already_cut(app):
    legacy = app.CACHE_DIR / f"{VID}.m4a"
    legacy.write_bytes(b"x")
    app.settings.yt_skip_segments = []
    asyncio.run(app.ensure_track(VID))
    assert not app._cuts
    app.settings.yt_skip_segments = ["sponsor"]
    cut_name(app).write_bytes(b"x")
    assert asyncio.run(app.ensure_track(VID)) == cut_name(app)
    assert not app._cuts


def test_queue_is_bounded(app):
    for i in range(app.CUT_QUEUE_MAX):
        app._cuts[f"v{i:010d}"] = (None, [])
    assert app.queue_cut(VID, app.CACHE_DIR / f"{VID}.m4a", ["sponsor"]) is False


def test_lookup_uses_hash_prefix(app, sponsorblock):
    sponsorblock["segments"] = [{"segment": [10, 20], "category": "sponsor", "actionType": "skip"}]
    got = asyncio.run(app.sb_segments(VID, ["selfpromo", "sponsor"]))
    assert got == sponsorblock["segments"]  # the other video sharing the prefix is ignored
    url = sponsorblock["calls"][0]
    assert url.path == f"/api/skipSegments/{hashlib.sha256(VID.encode()).hexdigest()[:4]}"
    assert VID not in str(url)
    assert json.loads(url.params["categories"]) == ["selfpromo", "sponsor"]


def test_cut_ranges(app):
    segs = [
        {"segment": [0.5, 10], "videoDuration": 100},  # snaps to the start
        {"segment": [8, 15], "videoDuration": 100},  # overlaps: merged
        {"segment": [0, 0], "videoDuration": 0},  # whole-video label: ignored
        {"segment": [40, 50], "videoDuration": 160},  # another version of the video: ignored
        {"segment": [95, 99.5], "videoDuration": 100.2},  # snaps to the end
    ]
    assert app.cut_ranges(segs, 100.0) == [(0.0, 15.0), (95.0, 100.0)]


def test_no_segments_records_the_check(app, sponsorblock, monkeypatch):
    legacy = app.CACHE_DIR / f"{VID}.m4a"
    legacy.write_bytes(b"whole")

    async def duration(path):
        return 300.0

    monkeypatch.setattr(app, "media_duration", duration)

    async def scenario():
        app.queue_cut(VID, legacy, app.settings.yt_skip_segments)
        await drain(app)

    asyncio.run(scenario())
    assert cut_name(app).read_bytes() == b"whole" and legacy.exists()
    assert app.cached_track(VID) == cut_name(app)  # the next play doesn't ask again
    assert not app._cuts


def test_failure_is_logged_and_retried_on_a_later_play(app, sponsorblock, capsys):
    legacy = app.CACHE_DIR / f"{VID}.m4a"
    legacy.write_bytes(b"x")
    sponsorblock["status"] = 503

    async def play_and_wait():
        path = await app.ensure_track(VID)
        await drain(app)
        return path

    assert asyncio.run(play_and_wait()) == legacy
    assert "SponsorBlock cut failed" in capsys.readouterr().out
    assert len(sponsorblock["calls"]) == 1  # no retry loop
    assert not app._cuts and not list(app.CACHE_DIR.glob("*.sb-*"))
    sponsorblock["status"], sponsorblock["segments"] = 200, []
    asyncio.run(play_and_wait())
    assert len(sponsorblock["calls"]) == 2  # the later play tried again
    assert legacy.exists()  # the whole file stays until prune_cache ages it out


def test_skipped_without_ffmpeg(app, sponsorblock, monkeypatch):
    legacy = app.CACHE_DIR / f"{VID}.m4a"
    legacy.write_bytes(b"x")
    monkeypatch.setattr(app.talk, "ffmpeg_available", lambda: False)
    asyncio.run(app.ensure_track(VID))
    assert not app._cuts and not sponsorblock["calls"]


def test_prune_ignores_cuts_in_progress(app):
    app.settings.cache_keep = 1
    part = app.CACHE_DIR / f".{VID}.sb-12345678.m4a.part"
    part.write_bytes(b"x")
    (app.CACHE_DIR / "bbbbbbbbbbb.m4a").write_bytes(b"x")
    app.prune_cache()
    assert part.exists()


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
def test_real_cut_with_ffmpeg(app, sponsorblock):
    legacy = app.CACHE_DIR / f"{VID}.m4a"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=8", "-c:a", "aac", "-b:a", "64k", str(legacy)], check=True)
    sponsorblock["segments"] = [{"segment": [2, 5], "category": "sponsor", "actionType": "skip", "videoDuration": 8}]

    async def scenario():
        before = await app.media_duration(legacy)
        app.queue_cut(VID, legacy, app.settings.yt_skip_segments)
        await drain(app)
        return before, await app.media_duration(cut_name(app))

    before, after = asyncio.run(scenario())
    assert before == pytest.approx(8, abs=0.1)
    assert after == pytest.approx(5, abs=0.2)  # 3 s removed
    assert app.content_type_for(cut_name(app)) == "audio/mp4"  # same container the speaker already plays
    assert not list(app.CACHE_DIR.glob(".*"))  # temp files gone


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
def test_reencodes_when_stream_copy_fails(app, sponsorblock, monkeypatch):
    legacy = app.CACHE_DIR / f"{VID}.m4a"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=6", "-c:a", "aac", "-b:a", "64k", str(legacy)], check=True)
    sponsorblock["segments"] = [{"segment": [1.5, 3], "category": "sponsor", "actionType": "skip"}]
    real = app.run_niced

    async def no_copy(args, timeout=app.CUT_TIMEOUT):
        return (1, "copy refused") if "copy" in args else await real(args, timeout)

    monkeypatch.setattr(app, "run_niced", no_copy)

    async def scenario():
        app.queue_cut(VID, legacy, app.settings.yt_skip_segments)
        await drain(app)
        return await app.media_duration(cut_name(app))

    assert asyncio.run(scenario()) == pytest.approx(4.5, abs=0.2)
