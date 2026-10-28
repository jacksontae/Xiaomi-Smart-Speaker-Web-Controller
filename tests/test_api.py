import asyncio
import json

from conftest import BASE


def test_status_reports_speaker(client):
    r = client.get("/status")
    assert r.status_code == 200
    assert r.json()["speaker"] == "Test Speaker"
    assert r.json()["resume_pending"] is None


def test_say_switches_receiver_and_loads_tts(client, fake_speaker, app):
    r = client.post("/say", json={"text": "ทดสอบ"})
    assert r.status_code == 200
    assert fake_speaker.started == [app.DEFAULT_MEDIA_RECEIVER]
    load = fake_speaker.media_controller.loads[-1]
    assert load["url"].startswith(f"{BASE}/tts.mp3?")
    assert load["title"] == "Announcement"


def test_say_rejects_empty_text(client):
    assert client.post("/say", json={"text": "  "}).status_code == 400


def test_say_applies_default_volume(client, fake_speaker, app):
    app.settings.default_volume = 0.6
    client.post("/say", json={"text": "hello", "lang": "en"})
    assert fake_speaker.volume == 0.6


def test_volume_validates_range(client, fake_speaker):
    assert client.post("/volume", json={"level": 2}).status_code == 400
    assert client.post("/volume", json={"level": 0.4}).status_code == 200
    assert fake_speaker.volume == 0.4


def test_tts_concatenates_chunks(client, app, monkeypatch):
    calls = []

    class Resp:
        status_code = 200
        content = b"MP3"

    async def fake_get(url, params=None):
        calls.append(params["q"])
        return Resp()

    monkeypatch.setattr(app.http, "get", fake_get)
    r = client.get("/tts.mp3", params={"text": "ก" * 400})
    assert r.status_code == 200
    assert r.content == b"MP3" * len(calls)
    assert len(calls) == 3


def test_youtube_plays_cached_file(client, fake_speaker, app, monkeypatch):
    path = app.CACHE_DIR / "abc123.m4a"
    path.write_bytes(b"audio")
    monkeypatch.setattr(app, "yt_download", lambda q: {"id": "abc123", "title": "Song", "duration": 60, "path": path})
    r = client.post("/youtube", json={"query": "song"})
    assert r.status_code == 200 and r.json()["title"] == "Song"
    load = fake_speaker.media_controller.loads[-1]
    assert load["url"] == f"{BASE}/yt/abc123.m4a"
    assert load["content_type"] == "audio/mp4"
    assert load["stream_type"] == "BUFFERED"


def test_yt_file_serving_and_traversal(client, app):
    (app.CACHE_DIR / "ok.m4a").write_bytes(b"data")
    assert client.get("/yt/ok.m4a").content == b"data"
    assert client.get("/yt/missing.m4a").status_code == 404
    assert client.get("/yt/..%2Fconfig.json").status_code == 404


def test_settings_partial_update_persists(client, app):
    r = client.post("/settings", json={"cache_keep": 7})
    assert r.status_code == 200 and r.json()["restart"] is False
    assert json.loads(app.CONFIG_PATH.read_text())["cache_keep"] == 7


def test_settings_reject_invalid(client):
    assert client.post("/settings", json={"default_volume": 5}).status_code == 422


def test_settings_port_change_requests_restart(client, app, monkeypatch):
    exits = []
    monkeypatch.setattr(app.os, "_exit", exits.append)
    r = client.post("/settings", json={"port": 8095})
    assert r.json()["restart"] is True
    assert exits == [0]


def test_stop_cancels_pending_resume(client, app, fake_speaker):
    app._resume = {"url": "x", "content_type": "audio/mp4", "title": "Song", "position": 3}
    client.post("/stop")
    assert app._resume is None and fake_speaker.quit


def test_capture_youtube_only_for_own_tracks(app, fake_speaker):
    status = fake_speaker.media_controller.status
    status.content_id, status.player_state, status.adjusted_current_time = "https://other/x.mp3", "PLAYING", 30
    assert app.capture_youtube() is None
    status.content_id = f"{BASE}/yt/abc.m4a"
    track = app.capture_youtube()
    assert track["position"] == 30 - app.RESUME_REWIND


def test_resume_after_announcement_replays_track(app, fake_speaker):
    tts = f"{BASE}/tts.mp3"
    track = {"url": f"{BASE}/yt/abc.m4a", "content_type": "audio/mp4", "title": "Song", "position": 12.5}
    app._resume, app._say_gen = track, 4
    status = fake_speaker.media_controller.status
    status.content_id, status.player_state = tts + "?text=x", "IDLE"
    asyncio.run(app.resume_after_announcement(4, tts))
    load = fake_speaker.media_controller.loads[-1]
    assert load["url"] == track["url"] and load["current_time"] == 12.5
    assert app._resume is None


def test_resume_gives_up_when_something_else_is_cast(app, fake_speaker):
    tts = f"{BASE}/tts.mp3"
    app._resume = {"url": f"{BASE}/yt/abc.m4a", "content_type": "audio/mp4", "title": "Song", "position": 1}
    app._say_gen = 1
    fake_speaker.media_controller.status.content_id = "https://other/stream.mp3"
    asyncio.run(app.resume_after_announcement(1, tts))
    assert fake_speaker.media_controller.loads == []
    assert app._resume is None
