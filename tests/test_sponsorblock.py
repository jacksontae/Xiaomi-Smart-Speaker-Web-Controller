"""SponsorBlock segment removal for YouTube downloads (yt-dlp is faked; nothing reaches the network)."""
import pytest
import yt_dlp
from conftest import REAL_YT_DOWNLOAD
from fastapi import HTTPException

from server import config, media, talk


@pytest.fixture
def ffmpeg(monkeypatch, app):
    """ffmpeg present by default; set `.on = False` to simulate a server without it."""
    state = type("FF", (), {"on": True})()
    monkeypatch.setattr(talk, "ffmpeg_available", lambda: state.on)
    return state


@pytest.fixture
def ydl(monkeypatch, app):
    """Fake YoutubeDL: records its options, resolves metadata, 'downloads' into the outtmpl (counted in
    `downloads`), optionally fails after the download."""
    seen = {"fail": None, "downloads": 0}

    class FakeYDL:
        def __init__(self, opts):
            seen["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, target, download=True, process=True):
            assert not download and not process  # resolve first, download through process_ie_result
            info = {"id": "abcdefghijk", "title": "Song", "duration": 300, "extractor_key": "Youtube"}
            return {"entries": iter([info])} if target.startswith("ytsearch") else info

        def process_ie_result(self, info, download=True):
            seen["downloads"] += 1
            path = seen["opts"]["outtmpl"].replace("%(id)s", info["id"]).replace("%(ext)s", "m4a")
            open(path, "wb").write(b"audio")
            for hook in seen["opts"].get("progress_hooks", []):
                hook({"status": "finished", "filename": path, "info_dict": info})
            if seen["fail"]:
                raise yt_dlp.utils.DownloadError(seen["fail"])
            cut = 270 if seen["opts"].get("postprocessors") else 300
            return {**info, "requested_downloads": [{"filepath": path, "duration": cut}]}

    monkeypatch.setattr(media, "yt_download", REAL_YT_DOWNLOAD)
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    return seen


@pytest.fixture(autouse=True)
def empty_cache(app):
    for p in config.CACHE_DIR.glob("*"):
        p.unlink()


def test_audio_only_format(app):
    """Only the audio stream is downloaded, so YouTube's own inserted ads are never part of the file."""
    assert config.YT_FORMAT.startswith("bestaudio")


def test_settings_default_and_validation(client, app, ffmpeg):
    s = client.get("/settings").json()
    assert s["yt_skip_segments"] == ["interaction", "selfpromo", "sponsor"]
    assert s["yt_skip_available"] is True
    r = client.post("/settings", json={"yt_skip_segments": ["Sponsor", "intro", "sponsor"]})
    assert r.status_code == 200
    assert r.json()["settings"]["yt_skip_segments"] == ["intro", "sponsor"]  # normalised for a stable cache key
    assert client.post("/settings", json={"yt_skip_segments": ["ads"]}).status_code == 422
    assert client.post("/settings", json={"yt_skip_segments": ["chapter"]}).status_code == 422  # can't be cut
    assert client.post("/settings", json={"yt_skip_segments": []}).json()["settings"]["yt_skip_segments"] == []
    ffmpeg.on = False
    assert client.get("/settings").json()["yt_skip_available"] is False


def test_owner_only(as_role):
    assert as_role("operator").post("/settings", json={"yt_skip_segments": []}).status_code == 403


def test_download_adds_sponsorblock_postprocessors(app, ydl, ffmpeg):
    info = media.yt_download("https://www.youtube.com/watch?v=abcdefghijk")
    pps = ydl["opts"]["postprocessors"]
    assert pps[0] == {"key": "SponsorBlock", "categories": ["interaction", "selfpromo", "sponsor"],
                      "when": "post_process"}
    assert pps[1] == {"key": "ModifyChapters", "remove_sponsor_segments": ["interaction", "selfpromo", "sponsor"]}
    assert info["path"].name.startswith("abcdefghijk.sb-") and info["path"].suffix == ".m4a"
    assert info["duration"] == 270  # the cut length
    assert media.cached_track("abcdefghijk") == info["path"]


@pytest.mark.parametrize("segments, has_ffmpeg", [([], True), (["sponsor"], False)])
def test_download_whole_video_when_off_or_no_ffmpeg(app, ydl, ffmpeg, segments, has_ffmpeg):
    config.settings.yt_skip_segments, ffmpeg.on = segments, has_ffmpeg
    info = media.yt_download("words")
    assert "postprocessors" not in ydl["opts"]
    assert info["path"].name == "abcdefghijk.m4a"  # the pre-SponsorBlock cache name


def test_cache_key_includes_categories(app, ffmpeg):
    a = media.yt_cache_stem("abcdefghijk", ["sponsor"])
    b = media.yt_cache_stem("abcdefghijk", ["selfpromo", "sponsor"])
    assert a != b and a.startswith("abcdefghijk.sb-")
    assert media.yt_cache_stem("abcdefghijk", []) == "abcdefghijk"
    (config.CACHE_DIR / f"{a}.m4a").write_bytes(b"x")
    config.settings.yt_skip_segments = ["selfpromo", "sponsor"]
    assert media.cached_track("abcdefghijk") is None  # cut differently: download again
    config.settings.yt_skip_segments = ["sponsor"]
    assert media.cached_track("abcdefghijk").name == f"{a}.m4a"


def test_old_cache_files_keep_playing(app, ffmpeg):
    legacy = config.CACHE_DIR / "abcdefghijk.webm"
    legacy.write_bytes(b"x")
    assert media.cached_track("abcdefghijk") == legacy  # segments on, but the old whole file is used as is
    cut = config.CACHE_DIR / f"{media.yt_cache_stem('abcdefghijk', config.settings.yt_skip_segments)}.m4a"
    cut.write_bytes(b"x")
    assert media.cached_track("abcdefghijk") == cut  # a matching cut copy wins
    config.settings.yt_skip_segments = []
    assert media.cached_track("abcdefghijk") == legacy  # off: never a cut copy


def test_sponsorblock_failure_keeps_whole_download(app, ydl, ffmpeg):
    ydl["fail"] = "ERROR: Postprocessing: Unable to communicate with SponsorBlock API"
    info = media.yt_download("https://www.youtube.com/watch?v=abcdefghijk")
    assert info["path"].name == "abcdefghijk.m4a" and info["path"].is_file()
    assert info["duration"] == 300
    assert not list(config.CACHE_DIR.glob("*.sb-*"))  # no uncut file left under a "cut" name


def test_download_failure_is_502(app, monkeypatch, ffmpeg):
    class Failing:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, target, download=True, process=True):
            raise yt_dlp.utils.DownloadError("Video unavailable")

    monkeypatch.setattr(media, "yt_download", REAL_YT_DOWNLOAD)
    monkeypatch.setattr(yt_dlp, "YoutubeDL", Failing)
    with pytest.raises(HTTPException) as e:
        media.yt_download("https://www.youtube.com/watch?v=abcdefghijk")
    assert e.value.status_code == 502


@pytest.mark.parametrize("query", ["https://www.youtube.com/watch?v=abcdefghijk", "song words"])
def test_direct_play_reuses_whole_file_and_queues_cut(client, app, ydl, ffmpeg, fresh_state, fake_speaker, query):
    legacy = config.CACHE_DIR / "abcdefghijk.m4a"
    legacy.write_bytes(b"x")
    r = client.post("/youtube", json={"query": query})
    assert r.status_code == 200 and r.json()["title"] == "Song"
    assert ydl["downloads"] == 0  # already cached: never downloaded again
    assert "/yt/abcdefghijk.m4a?" in fake_speaker.media_controller.loads[-1]["url"]
    assert fresh_state.cuts == ["abcdefghijk"]  # cut locally in the background for next time


def test_direct_play_uses_cut_copy(client, app, ydl, ffmpeg, fresh_state, fake_speaker):
    (config.CACHE_DIR / "abcdefghijk.m4a").write_bytes(b"x")
    cut = config.CACHE_DIR / f"{media.yt_cache_stem('abcdefghijk', config.settings.yt_skip_segments)}.m4a"
    cut.write_bytes(b"x")
    assert client.post("/youtube", json={"query": "song words"}).status_code == 200
    assert ydl["downloads"] == 0 and fresh_state.cuts == []
    assert f"/yt/{cut.name}?" in fake_speaker.media_controller.loads[-1]["url"]


def test_direct_play_downloads_on_a_miss(client, app, ydl, ffmpeg, fresh_state, fake_speaker):
    assert client.post("/youtube", json={"query": "song words"}).status_code == 200
    assert ydl["downloads"] == 1 and fresh_state.cuts == []  # downloaded already cut
    assert ".sb-" in fake_speaker.media_controller.loads[-1]["url"]
