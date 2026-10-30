import asyncio
import json
import re

import pytest
from conftest import BASE, path_of

from transport import DEFAULT_MEDIA_RECEIVER


def test_status_reports_speaker(client):
    r = client.get("/status")
    assert r.status_code == 200
    assert r.json()["speaker"] == "Test Speaker"
    assert r.json()["resume_pending"] is None
    assert r.json()["tts_lang"] == "th"  # every role needs it to default the announce language


def test_say_switches_receiver_and_loads_tts(client, fake_speaker, app):
    r = client.post("/say", json={"text": "ทดสอบ"})
    assert r.status_code == 200
    assert fake_speaker.started == [DEFAULT_MEDIA_RECEIVER]
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


def test_tts_concatenates_chunks(anon, app, monkeypatch):
    calls = []

    class Resp:
        status_code = 200
        content = b"MP3"

    async def fake_get(url, params=None):
        calls.append(params["q"])
        return Resp()

    monkeypatch.setattr(app.http, "get", fake_get)
    r = anon.get(path_of(app.media_url("/tts.mp3", text="ก" * 400, lang="th")))
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
    assert load["url"].startswith(f"{BASE}/yt/abc123.m4a?")
    assert load["content_type"] == "audio/mp4"
    assert load["stream_type"] == "BUFFERED"


def test_yt_file_serving_and_traversal(anon, app):
    (app.CACHE_DIR / "ok.m4a").write_bytes(b"data")
    assert anon.get(path_of(app.media_url("/yt/ok.m4a"))).content == b"data"
    assert anon.get(path_of(app.media_url("/yt/missing.m4a"))).status_code == 404
    assert anon.get(path_of(app.media_url("/yt/..%2Fconfig.json"))).status_code in (403, 404)


def test_settings_partial_update_persists(client, app):
    r = client.post("/settings", json={"cache_keep": 7})
    assert r.status_code == 200 and r.json()["restart"] is False
    assert json.loads(app.CONFIG_PATH.read_text())["cache_keep"] == 7


def test_settings_reject_invalid(client):
    assert client.post("/settings", json={"default_volume": 5}).status_code == 422


@pytest.mark.parametrize("ip", ["192.0.2.10", "2001:db8::10", "speaker.local", "speaker", "kitchen-1.example.com.",
                                "  192.0.2.11  "])
def test_speaker_ip_accepts_addresses_and_hostnames(app, ip):
    assert app.Settings(speaker_ip=ip).speaker_ip == ip.strip()


@pytest.mark.parametrize("ip", ["", "   ", "999.1.1.1", "192.0.2", "http://192.0.2.10", "192.0.2.10:8009",
                                "my speaker", "-bad.example.com", "a..b", "speaker_1.local", "x" * 64 + ".com"])
def test_speaker_ip_rejects_garbage(app, ip):
    with pytest.raises(ValueError, match="speaker_ip must be an IP address"):
        app.Settings(speaker_ip=ip)


def test_speaker_name_is_trimmed_and_required(app):
    assert app.Settings(speaker_name="  Living\troom  ").speaker_name == "Living room"
    for bad, why in (("", "can't be empty"), ("  \n ", "can't be empty"), ("x" * 65, "at most 64")):
        with pytest.raises(ValueError, match=why):
            app.Settings(speaker_name=bad)
    assert len(app.Settings(speaker_name="x" * 64).speaker_name) == 64


def test_settings_api_rejects_bad_speaker_without_saving(client, app):
    before = app.CONFIG_PATH.read_text()
    transport = app.transport
    r = client.post("/settings", json={"speaker_ip": "not an ip"})
    assert r.status_code == 422
    assert r.json()["detail"] == "speaker_ip must be an IP address like 192.0.2.10 or a hostname like speaker.local"
    r = client.post("/settings", json={"speaker_name": "   "})
    assert r.status_code == 422 and r.json()["detail"] == "speaker_name can't be empty"
    r = client.post("/settings", json={"speaker_name": "", "speaker_ip": ""})
    assert r.status_code == 422
    assert "speaker_ip must be" in r.json()["detail"] and "; speaker_name can't be empty" in r.json()["detail"]
    assert app.CONFIG_PATH.read_text() == before and app.transport is transport  # nothing saved or restarted


def test_settings_api_422_names_the_field(client):
    r = client.post("/settings", json={"default_volume": 5})
    assert r.json()["detail"] == "default_volume: Input should be less than or equal to 1"
    r = client.post("/settings", json={"mqtt": {"base_topic": "a/#"}})
    assert r.json()["detail"].startswith("mqtt.base_topic: base_topic must be")


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


def test_unreachable_speaker_returns_503(client, app, monkeypatch):
    import pychromecast.error

    def unreachable():
        raise pychromecast.error.RequestTimeout("wait", 10)

    monkeypatch.setattr(app.transport, "get_cast", unreachable)
    r = client.get("/status")
    assert r.status_code == 503
    assert "not responding" in r.json()["detail"]


def test_resume_dropped_when_speaker_disappears(app, monkeypatch):
    import pychromecast.error

    def unreachable():
        raise pychromecast.error.RequestTimeout("wait", 10)

    app._resume = {"url": f"{BASE}/yt/abc.m4a", "content_type": "audio/mp4", "title": "Song", "position": 1}
    app._say_gen = 2
    monkeypatch.setattr(app.transport, "get_cast", unreachable)
    asyncio.run(app.resume_after_announcement(2, f"{BASE}/tts.mp3"))
    assert app._resume is None


# --- Authentication ---

PROTECTED = [
    ("get", "/status", None), ("post", "/say", {"text": "x"}), ("post", "/play", {"url": "http://x/a.mp3"}),
    ("post", "/youtube", {"query": "x"}), ("post", "/volume", {"level": 0.5}), ("get", "/settings", None),
    ("post", "/settings", {"cache_keep": 3}), ("get", "/speakers", None), ("post", "/pause", None),
    ("post", "/resume", None), ("post", "/stop", None),
]


def test_control_endpoints_require_token(anon, fake_speaker):
    for method, path, body in PROTECTED:
        r = getattr(anon, method)(path, json=body) if body else getattr(anon, method)(path)
        assert r.status_code == 401, path
        assert r.headers["www-authenticate"] == "Bearer"
    assert fake_speaker.media_controller.loads == [] and not fake_speaker.quit


def test_wrong_token_is_rejected(anon):
    assert anon.get("/status", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_web_ui_and_docs_stay_public(anon):
    assert anon.get("/").status_code == 200
    assert anon.get("/openapi.json").status_code == 200


def test_settings_never_expose_token(client):
    assert "api_token" not in client.get("/settings").json()
    r = client.post("/settings", json={"cache_keep": 4})
    assert "api_token" not in r.json()["settings"]


def test_token_cannot_be_changed_over_api(client, app):
    r = client.post("/settings", json={"api_token": "mine"})
    assert r.status_code == 400
    assert app.settings.api_token == "test-token"


def test_first_run_generates_and_persists_token(app, monkeypatch, tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"speaker_ip": "10.0.0.5"}))
    monkeypatch.setattr(app, "CONFIG_PATH", cfg)
    s = app.load_settings()
    assert s.api_token and len(s.api_token) >= 40
    assert json.loads(cfg.read_text())["api_token"] == s.api_token
    assert cfg.stat().st_mode & 0o077 == 0
    assert app.load_settings().api_token == s.api_token


def test_media_links_must_be_signed(anon, app):
    (app.CACHE_DIR / "song.m4a").write_bytes(b"data")
    assert anon.get("/yt/song.m4a").status_code == 403
    assert anon.get("/tts.mp3", params={"text": "x"}).status_code == 403
    signed = path_of(app.media_url("/yt/song.m4a"))
    assert anon.get(signed).status_code == 200
    assert anon.get(signed.replace("song.m4a", "other.m4a")).status_code == 403


def test_tampered_or_expired_media_link_rejected(anon, app, monkeypatch):
    signed = path_of(app.media_url("/tts.mp3", text="hello", lang="th"))
    assert anon.get(signed.replace("hello", "evil")).status_code == 403
    monkeypatch.setattr(app.time, "time", lambda: 10**12)
    assert anon.get(signed).status_code == 403


def test_rotating_token_invalidates_media_links(anon, app):
    (app.CACHE_DIR / "song.m4a").write_bytes(b"data")
    signed = path_of(app.media_url("/yt/song.m4a"))
    app.settings.api_token = "rotated"
    assert anon.get(signed).status_code == 403


def test_signed_link_survives_url_encoding(anon, app, monkeypatch):
    class Resp:
        status_code, content = 200, b"MP3"

    async def fake_get(url, params=None):
        return Resp()

    monkeypatch.setattr(app.http, "get", fake_get)
    text = "a b&c=d+e/ไทย 100% ?#"
    assert anon.get(path_of(app.media_url("/tts.mp3", text=text, lang="th"))).status_code == 200


def test_web_app_files_are_revalidated(anon):
    """Unversioned paths (manifest icons, anything referenced absolutely) and the page itself are checked back."""
    for path in ("/", "/static/js/app.js", "/static/css/base.css", "/static/icon-192.png"):
        r = anon.get(path)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-cache", path
    etag = anon.get("/static/js/app.js").headers["etag"]
    assert anon.get("/static/js/app.js", headers={"If-None-Match": etag}).status_code == 304


def build_prefix(anon):
    m = re.search(r'src="/static/([0-9a-f]{12})/js/app\.js"', anon.get("/").text)
    assert m, "index.html must load the app from the versioned path"
    return f"/static/{m.group(1)}"


def test_index_points_at_versioned_immutable_files(anon, app):
    html = anon.get("/").text
    prefix = build_prefix(anon)
    assert prefix[len("/static/"):] == app.static_build.id
    # every app file comes from this build; the root-level icons stay where iOS and the manifest expect them
    assert re.findall(r'"/static/(?![0-9a-f]{12}/)', html) == []
    assert 'href="/manifest.webmanifest"' in html and 'href="/apple-touch-icon.png"' in html
    for path in ("js/app.js", "js/views/now.js", "css/base.css", "fonts/anuphan-latin-wght-normal.woff2"):
        r = anon.get(f"{prefix}/{path}")
        assert r.status_code == 200, path
        assert r.headers["cache-control"] == "public, max-age=31536000, immutable", path
        assert r.content == anon.get(f"/static/{path}").content
    etag = anon.get(f"{prefix}/js/app.js").headers["etag"]
    r = anon.get(f"{prefix}/js/app.js", headers={"If-None-Match": etag})
    assert r.status_code == 304 and r.headers["cache-control"].endswith("immutable")


def test_versioned_static_refuses_other_builds_and_escapes(anon):
    prefix = build_prefix(anon)
    for path in ("/static/0123456789ab/js/app.js", f"{prefix}/js/nope.js", f"{prefix}/../../config.json", prefix):
        r = anon.get(path)
        assert r.status_code == 404, path
        assert "immutable" not in r.headers.get("cache-control", ""), path
    # a tab from an older build must not get a cached 404 either: the next index.html names the new build
    assert anon.get("/static/0123456789ab/js/app.js").headers["cache-control"] == "no-store"


def test_build_id_follows_static_content(app, tmp_path):
    (tmp_path / "index.html").write_text('<script type="module" src="/static/js/app.js"></script>')
    (tmp_path / "js").mkdir()
    (tmp_path / "js" / "app.js").write_text("export const a = 1;")
    build = app.StaticBuild(tmp_path).refresh()
    first = build.id
    assert app.BUILD_ID.fullmatch(first)
    assert build.index == f'<script type="module" src="/static/{first}/js/app.js"></script>'
    assert build.refresh().id == first  # unchanged files: same id
    (tmp_path / "js" / "app.js").write_text("export const a = 22;")
    assert build.refresh().id != first
    (tmp_path / "js" / "app.js").write_text("export const a = 1;")
    assert build.refresh().id == first  # content, not timestamps
    (tmp_path / "js" / "new.js").write_text("")
    assert build.refresh().id != first
