import asyncio
import random

import pytest
from conftest import BASE, REAL_SCHEDULE_PREFETCH, path_of
from fastapi import HTTPException

from player import Queue

A, B, C = "aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"


def yt(vid):
    return {"kind": "youtube", "source": vid, "title": f"Song {vid[0]}", "duration": 100.0,
            "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg", "lang": None}


@pytest.fixture
def downloads(app, monkeypatch):
    """Fake yt_download writing a file into the cache; ids in `downloads.fail` raise like a real failure."""
    for f in app.CACHE_DIR.glob("*"):
        f.unlink()
    calls = []

    def download(query):
        vid = query.rsplit("v=", 1)[-1]
        calls.append(vid)
        if vid in download.fail:
            raise HTTPException(502, "YouTube download failed: Video unavailable")
        path = app.CACHE_DIR / f"{vid}.m4a"
        path.write_bytes(b"audio")
        return {"id": vid, "title": vid, "duration": 100, "path": path}

    download.fail = set()
    download.calls = calls
    monkeypatch.setattr(app, "yt_download", download)
    return download


def playlist(app, *items, name="Mix"):
    pl = app.db.create_playlist(name)
    for item in items:
        app.db.add_item(pl["id"], item, 100)
    return pl["id"]


def loaded(cast):
    return cast.media_controller.loads[-1]


def tick(app):
    asyncio.run(app.queue_tick())


def start(client, pid, **body):
    r = client.post(f"/playlists/{pid}/play", json=body)
    assert r.status_code == 200, r.text
    return r.json()


# --- Queue model ---

def test_model_repeat_off_all_one():
    q = Queue([1, 2, 3])
    assert q.advance(auto=True) and q.pos == 1
    assert q.advance(auto=True) and q.pos == 2
    assert not q.advance(auto=True) and q.pos == 2
    q.repeat = "all"
    assert q.advance(auto=True) and q.pos == 0
    q.repeat = "one"
    assert q.advance(auto=True) and q.pos == 0  # replays on its own
    assert q.advance(auto=False) and q.pos == 1  # but "next" still moves on


def test_model_back():
    q = Queue([1, 2, 3], start=1)
    q.back()
    assert q.pos == 0
    q.back()
    assert q.pos == 0  # repeat off: restart the first item
    q.repeat = "all"
    q.back()
    assert q.pos == 2


def test_model_shuffle_keeps_current_and_restores_order():
    q = Queue(list(range(10)), start=4, shuffle=True, rng=random.Random(1))
    assert q.current == 4 and q.pos == 0 and sorted(q.order) == list(range(10))
    assert q.summary()["items"][0] == 4
    q.advance(auto=False)
    playing = q.current
    q.set_shuffle(False)
    assert q.current == playing and q.order == list(range(10)) and q.pos == playing


def test_model_reshuffles_each_round_without_repeating_last():
    for seed in range(30):
        q = Queue(list(range(4)), shuffle=True, repeat="all", rng=random.Random(seed))
        for _ in range(3):
            q.advance(auto=True)
        last = q.current
        q.advance(auto=True)
        assert q.pos == 0 and q.current != last and sorted(q.order) == [0, 1, 2, 3]


def test_model_peek_next_and_validation():
    q = Queue(["a", "b"])
    assert q.peek_next() == "b"
    q.advance(auto=True)
    assert q.peek_next() is None
    q.repeat = "all"
    assert q.peek_next() == "a"
    q.repeat = "one"
    assert q.peek_next() == "b"
    with pytest.raises(IndexError):
        q.jump(2)
    with pytest.raises(IndexError):
        Queue(["a"], start=1)
    with pytest.raises(ValueError):
        Queue([])


# --- Playing a playlist ---

def test_play_playlist_starts_first_item(client, app, fake_speaker, downloads, fresh_state):
    pid = playlist(app, yt(A), yt(B))
    summary = start(client, pid)
    assert summary["playlist_id"] == pid and summary["name"] == "Mix" and summary["index"] == 0
    assert summary["length"] == 2 and summary["shuffle"] is False and summary["repeat"] == "off"
    assert [i["source"] for i in summary["items"]] == [A, B]
    load = loaded(fake_speaker)
    assert load["url"].startswith(f"{BASE}/yt/{A}.m4a?") and load["title"] == "Song a"
    assert load["content_type"] == "audio/mp4"
    assert fresh_state.watchers == 1
    assert fresh_state.prefetch[-1]["source"] == B
    assert client.get("/queue").json() == summary
    status = client.get("/status").json()
    assert status["queue"] == summary
    assert status["media"]["thumbnail"] == f"https://i.ytimg.com/vi/{A}/hqdefault.jpg"


def test_play_playlist_validation(client, app, downloads):
    empty = playlist(app)
    assert client.post(f"/playlists/{empty}/play", json={}).status_code == 400
    pid = playlist(app, yt(A))
    assert client.post(f"/playlists/{pid}/play", json={"start_index": 1}).status_code == 400
    assert client.post(f"/playlists/{pid}/play", json={"repeat": "forever"}).status_code == 422
    assert client.post("/playlists/999/play", json={}).status_code == 404
    assert client.get("/queue").json() is None


def test_start_index_with_shuffle_plays_that_item_first(client, app, fake_speaker, downloads):
    pid = playlist(app, yt(A), yt(B), yt(C))
    summary = start(client, pid, start_index=2, shuffle=True)
    assert summary["index"] == 0 and summary["items"][0]["source"] == C and summary["shuffle"]
    assert f"/yt/{C}.m4a?" in loaded(fake_speaker)["url"]


def test_track_end_advances(client, app, fake_speaker, downloads):
    pid = playlist(app, yt(A), yt(B))
    start(client, pid)
    fake_speaker.media_controller.finish()
    tick(app)
    assert f"/yt/{B}.m4a?" in loaded(fake_speaker)["url"]
    assert client.get("/queue").json()["index"] == 1
    fake_speaker.media_controller.finish()
    tick(app)
    assert client.get("/queue").json() is None  # ran out with repeat off
    assert len(fake_speaker.media_controller.loads) == 2


def test_no_advance_while_playing_paused_or_cancelled(client, app, fake_speaker, downloads):
    pid = playlist(app, yt(A), yt(B))
    start(client, pid)
    tick(app)
    fake_speaker.media_controller.status.player_state = "PAUSED"
    tick(app)
    fake_speaker.media_controller.finish("CANCELLED")  # stopped from the Google Home app
    tick(app)
    fake_speaker.media_controller.finish("INTERRUPTED")
    tick(app)
    assert len(fake_speaker.media_controller.loads) == 1


def test_other_media_finishing_does_not_advance(client, app, fake_speaker, downloads):
    pid = playlist(app, yt(A), yt(B))
    start(client, pid)
    status = fake_speaker.media_controller.status
    status.content_id = "https://someone-else/track.mp3"
    fake_speaker.media_controller.finish()
    tick(app)
    assert len(fake_speaker.media_controller.loads) == 1


def test_announcement_ending_does_not_advance_and_queue_continues_after_resume(
    client, app, fake_speaker, downloads
):
    pid = playlist(app, yt(A), yt(B))
    start(client, pid)
    track_url = loaded(fake_speaker)["url"]
    fake_speaker.media_controller.status.adjusted_current_time = 42.0

    r = client.post("/say", json={"text": "ประกาศ"})
    assert r.json()["will_resume"] == "Song a"
    assert loaded(fake_speaker)["url"].startswith(f"{BASE}/tts.mp3?")
    fake_speaker.media_controller.finish()  # the announcement ends
    tick(app)
    assert loaded(fake_speaker)["url"].startswith(f"{BASE}/tts.mp3?")  # no advance on the announcement's end

    asyncio.run(app.resume_after_announcement(app._say_gen, f"{BASE}/tts.mp3"))
    resumed = loaded(fake_speaker)
    assert resumed["url"] == track_url and resumed["current_time"] == 42.0 - app.RESUME_REWIND
    assert client.get("/queue").json()["index"] == 0

    fake_speaker.media_controller.finish()  # the resumed track ends
    tick(app)
    assert f"/yt/{B}.m4a?" in loaded(fake_speaker)["url"]


def test_announcement_after_track_finished_continues_queue(client, app, fake_speaker, downloads):
    pid = playlist(app, yt(A), yt(B))
    start(client, pid)
    fake_speaker.media_controller.finish()  # track ended; the watcher hasn't noticed yet
    r = client.post("/say", json={"text": "hello"})
    assert r.json()["will_resume"] is None
    tick(app)
    assert loaded(fake_speaker)["url"].startswith(f"{BASE}/tts.mp3?")  # announcement still playing
    fake_speaker.media_controller.finish()
    tick(app)
    assert f"/yt/{B}.m4a?" in loaded(fake_speaker)["url"]


def test_announcement_without_resume_setting_moves_on(client, app, fake_speaker, downloads):
    app.settings.resume_after_say = False
    pid = playlist(app, yt(A), yt(B))
    start(client, pid)
    client.post("/say", json={"text": "hello"})
    fake_speaker.media_controller.finish()
    tick(app)
    assert f"/yt/{B}.m4a?" in loaded(fake_speaker)["url"]


def test_announcement_while_paused_does_not_start_next(client, app, fake_speaker, downloads):
    pid = playlist(app, yt(A), yt(B))
    start(client, pid)
    fake_speaker.media_controller.status.player_state = "PAUSED"
    client.post("/say", json={"text": "hello"})
    fake_speaker.media_controller.finish()
    tick(app)
    assert loaded(fake_speaker)["url"].startswith(f"{BASE}/tts.mp3?")


def test_repeat_one_replays_and_repeat_all_wraps(client, app, fake_speaker, downloads):
    pid = playlist(app, yt(A), yt(B))
    start(client, pid, repeat="one")
    first = loaded(fake_speaker)["url"]
    fake_speaker.media_controller.finish()
    tick(app)
    again = loaded(fake_speaker)["url"]
    assert f"/yt/{A}.m4a?" in again and again != first  # unique URL so the next end is recognised
    client.patch("/queue", json={"repeat": "all"})
    fake_speaker.media_controller.finish()
    tick(app)
    fake_speaker.media_controller.finish()
    tick(app)
    assert f"/yt/{A}.m4a?" in loaded(fake_speaker)["url"]
    assert client.get("/queue").json()["index"] == 0


def test_next_prev_jump(client, app, fake_speaker, downloads):
    pid = playlist(app, yt(A), yt(B), yt(C))
    start(client, pid)
    assert client.post("/queue/next").json()["index"] == 1
    assert f"/yt/{B}.m4a?" in loaded(fake_speaker)["url"]
    assert client.post("/queue/jump", json={"index": 2}).json()["index"] == 2
    assert f"/yt/{C}.m4a?" in loaded(fake_speaker)["url"]
    assert client.post("/queue/next").status_code == 409
    assert client.post("/queue/jump", json={"index": 3}).status_code == 400
    assert client.post("/queue/prev").json()["index"] == 1
    assert client.post("/queue/prev").json()["index"] == 0
    assert client.post("/queue/prev").json()["index"] == 0  # restarts the first item
    assert f"/yt/{A}.m4a?" in loaded(fake_speaker)["url"]


def test_queue_controls_need_a_queue(client):
    assert client.get("/queue").json() is None
    for path in ("/queue/next", "/queue/prev"):
        assert client.post(path).status_code == 404
    assert client.post("/queue/jump", json={"index": 0}).status_code == 404
    assert client.patch("/queue", json={"shuffle": True}).status_code == 404


def test_patch_queue_shuffle_keeps_current_item(client, app, fake_speaker, downloads):
    pid = playlist(app, *(yt(c * 11) for c in "abcdefgh"))
    start(client, pid, start_index=3)
    loads = len(fake_speaker.media_controller.loads)
    s = client.patch("/queue", json={"shuffle": True}).json()
    assert s["shuffle"] and s["index"] == 0 and s["items"][0]["source"] == "d" * 11
    s = client.patch("/queue", json={"shuffle": False, "repeat": "all"}).json()
    assert s["index"] == 3 and [i["source"][0] for i in s["items"]] == list("abcdefgh") and s["repeat"] == "all"
    assert len(fake_speaker.media_controller.loads) == loads  # no interruption


def test_failed_download_is_skipped_and_logged(client, app, fake_speaker, downloads):
    downloads.fail = {A}
    pid = playlist(app, yt(A), yt(B))
    summary = start(client, pid)
    assert summary["index"] == 1
    assert f"/yt/{B}.m4a?" in loaded(fake_speaker)["url"]
    skip = [e for e in client.get("/activity").json() if e["action"] == "queue skip"]
    assert skip[0]["actor"] == "system" and "Song a" in skip[0]["detail"] and "unavailable" in skip[0]["detail"]


def test_all_items_failing_ends_queue(client, app, fake_speaker, downloads):
    downloads.fail = {A, B}
    pid = playlist(app, yt(A), yt(B))
    r = client.post(f"/playlists/{pid}/play", json={"repeat": "all"})
    assert r.status_code == 502
    assert client.get("/queue").json() is None
    assert fake_speaker.media_controller.loads == []


def test_speaker_error_skips_item(client, app, fake_speaker, downloads):
    pid = playlist(app, yt(A), yt(B))
    start(client, pid, repeat="one")
    fake_speaker.media_controller.finish("ERROR")
    tick(app)
    assert f"/yt/{B}.m4a?" in loaded(fake_speaker)["url"]  # skipped even with repeat one


def test_play_youtube_and_stop_replace_the_queue(client, app, fake_speaker, downloads):
    pid = playlist(app, yt(A), yt(B))
    start(client, pid)
    assert client.post("/play", json={"url": "http://x/a.mp3"}).status_code == 200
    assert client.get("/queue").json() is None
    start(client, pid)
    client.post("/youtube", json={"query": f"https://www.youtube.com/watch?v={C}"})
    assert client.get("/queue").json() is None
    assert client.get("/status").json()["media"]["thumbnail"] == f"https://i.ytimg.com/vi/{C}/hqdefault.jpg"
    start(client, pid)
    client.post("/stop")
    assert client.get("/queue").json() is None and fake_speaker.quit


def test_queue_clear_stops(client, app, fake_speaker, downloads):
    pid = playlist(app, yt(A), yt(B))
    start(client, pid)
    r = client.post("/queue/clear")
    assert r.status_code == 204 and r.content == b""
    assert fake_speaker.quit and client.get("/queue").json() is None
    assert client.get("/status").json()["queue"] is None
    assert client.post("/queue/clear").status_code == 204


def test_stale_load_is_dropped(app, fake_speaker):
    app.clear_queue()
    gen = app._queue_gen
    app.clear_queue()  # something else happened meanwhile
    assert app.load_if_current(gen, "http://x/a.mp3", "audio/mpeg", "x", True) is False
    assert fake_speaker.media_controller.loads == []


def test_tts_and_url_items(client, app, fake_speaker, anon, monkeypatch):
    tts = {"kind": "tts", "source": "สวัสดี", "title": "สวัสดี", "duration": None, "thumbnail": None, "lang": "th"}
    url = {"kind": "url", "source": "https://radio.example/stream.ogg", "title": "Radio", "duration": None,
           "thumbnail": None, "lang": None}
    pid = playlist(app, tts, url)
    start(client, pid)
    load = loaded(fake_speaker)
    assert load["url"].startswith(f"{BASE}/tts.mp3?") and load["content_type"] == "audio/mp3"

    class Resp:
        status_code, content = 200, b"MP3"

    async def fake_get(u, params=None):
        assert params["q"] == "สวัสดี"
        return Resp()

    monkeypatch.setattr(app.http, "get", fake_get)
    assert anon.get(path_of(load["url"])).content == b"MP3"  # signed like any announcement
    assert client.get("/status").json()["media"]["thumbnail"] is None

    fake_speaker.media_controller.finish()
    tick(app)
    load = loaded(fake_speaker)
    assert load["url"] == url["source"] and load["content_type"] == "audio/ogg"


def test_default_volume_on_start_but_not_between_tracks(client, app, fake_speaker, downloads):
    app.settings.default_volume = 0.6
    pid = playlist(app, yt(A), yt(B))
    start(client, pid)
    assert fake_speaker.volume == 0.6
    client.post("/volume", json={"level": 0.3})
    fake_speaker.media_controller.finish()
    tick(app)
    assert fake_speaker.volume == 0.3


def test_prefetch_downloads_next_once(app, downloads, monkeypatch):
    monkeypatch.setattr(app, "schedule_prefetch", REAL_SCHEDULE_PREFETCH)

    async def scenario():
        q = Queue([yt(A), yt(B)])
        app.schedule_prefetch(q)
        await asyncio.gather(*app._background)
        assert downloads.calls == [B]
        path = await app.ensure_track(B)  # now cached: no second download
        assert path.name == f"{B}.m4a" and downloads.calls == [B]
        q.advance(auto=True)
        app.schedule_prefetch(q)  # nothing after the last item
        assert not app._background

    asyncio.run(scenario())


def test_concurrent_requests_share_one_download(app, downloads):
    async def scenario():
        return await asyncio.gather(app.ensure_track(C), app.ensure_track(C))

    first, second = asyncio.run(scenario())
    assert first == second and downloads.calls == [C]


def test_prune_keeps_queue_tracks(app, downloads, client, fake_speaker):
    app.settings.cache_keep = 1
    pid = playlist(app, yt(A), yt(B))
    (app.CACHE_DIR / f"{B}.m4a").write_bytes(b"prefetched")
    start(client, pid)
    assert (app.CACHE_DIR / f"{A}.m4a").exists() and (app.CACHE_DIR / f"{B}.m4a").exists()
