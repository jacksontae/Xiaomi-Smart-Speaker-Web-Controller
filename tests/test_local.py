"""This device: POST /local/resolve gives the browser a playable link and never touches the speaker."""
import httpx
import pytest
from conftest import BASE
from test_queue import downloads  # noqa: F401 - fixture
from test_sources import MP3, STATIONS, UUID_A, net, upload  # noqa: F401 - fixtures

VID = "aaaaaaaaaaa"


class NoSpeaker:
    def __getattr__(self, name):
        raise AssertionError(f"/local/resolve must not touch the speaker (transport.{name})")


@pytest.fixture
def no_speaker(app, monkeypatch, fake_speaker):
    """Any speaker call (or working out the speaker-facing base URL) fails the test."""
    monkeypatch.setattr(app, "transport", NoSpeaker())
    monkeypatch.setattr(app, "host_ip", lambda: (_ for _ in ()).throw(AssertionError("host_ip used")))
    return fake_speaker


def resolve(c, **body):
    return c.post("/local/resolve", json=body)


def fetch(c, url):
    assert url.startswith("/"), "this server's own links are relative, for the browser's origin"
    return c.get(url)


def test_needs_operator(as_role, anon):
    body = {"kind": "tts", "source": "hello"}
    assert resolve(anon, **body).status_code == 401
    assert resolve(as_role("viewer"), **body).status_code == 403
    assert resolve(as_role("operator"), **body).status_code == 200
    assert resolve(as_role("admin"), **body).status_code == 200


def test_tts(client, anon, app, net, no_speaker):  # noqa: F811
    net.routes[("translate.google.com", "/translate_tts")] = lambda r: httpx.Response(200, content=b"mp3")
    r = resolve(client, kind="tts", source="  Shop opens at nine  ", lang="en")
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["kind"] == "tts" and got["title"] == "Shop opens at nine" and got["live"] is False
    assert got["url"].startswith("/tts.mp3?") and "sig=" in got["url"] and got["content_type"] == "audio/mp3"
    assert fetch(anon, got["url"]).content == b"mp3"  # signed: plays without a session
    assert resolve(client, kind="tts", source="  ").status_code == 400
    assert no_speaker.media_controller.loads == [] and app.db.activity() == []


def test_youtube_by_id_uses_the_cache(client, anon, app, downloads, no_speaker):  # noqa: F811
    r = resolve(client, kind="youtube", source=VID, title="Song A", duration=100)
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["url"].startswith(f"/yt/{VID}.m4a?") and got["content_type"] == "audio/mp4"
    assert got["title"] == "Song A" and got["duration"] == 100
    assert got["thumbnail"] == f"https://i.ytimg.com/vi/{VID}/hqdefault.jpg"
    assert fetch(anon, got["url"]).content == b"audio"
    resolve(client, kind="youtube", source=VID)
    assert downloads.calls == [VID]  # the second play is served from the cache


def test_youtube_words_are_looked_up(client, app, downloads, monkeypatch, no_speaker):  # noqa: F811
    found = {"entries": [{"id": VID, "title": "Found it", "duration": 61}]}
    monkeypatch.setattr(app, "yt_extract", lambda target: found)
    got = resolve(client, kind="youtube", source="some song").json()
    assert got["title"] == "Found it" and got["duration"] == 61 and got["url"].startswith(f"/yt/{VID}.")


def test_youtube_download_failure_is_502(client, downloads, no_speaker):  # noqa: F811
    downloads.fail.add(VID)
    assert resolve(client, kind="youtube", source=VID).status_code == 502


def test_file(client, anon, app, no_speaker):
    f = upload(client).json()
    got = resolve(client, kind="file", source=str(f["id"])).json()
    stored = app.db.get_file(f["id"])["stored_name"]
    assert got["url"].startswith(f"/media/{stored}?") and got["content_type"] == "audio/mpeg"
    assert got["title"] == "My Song"
    assert fetch(anon, got["url"]).content == MP3
    assert resolve(client, kind="file", source="999").status_code == 404
    (app.MEDIA_DIR / stored).unlink()
    assert resolve(client, kind="file", source=str(f["id"])).status_code == 404


def test_radio_station_and_stream_url(client, net, no_speaker):  # noqa: F811
    got = resolve(client, kind="radio", source=UUID_A).json()
    assert got["url"] == STATIONS[0]["url_resolved"] and got["content_type"] == "audio/aac"
    assert got["title"] == "Jazz FM" and got["thumbnail"] == STATIONS[0]["favicon"] and got["live"] is True
    got = resolve(client, kind="radio", source="https://radio.example.com/live.mp3", title="My FM").json()
    assert got["url"] == "https://radio.example.com/live.mp3" and got["content_type"] == "audio/mpeg"
    assert got["title"] == "My FM" and got["live"] is True


def test_podcast_and_url(client, no_speaker):
    got = resolve(client, kind="podcast", source="https://cdn.example.com/ep2.m4a", title="Episode 2",
                  thumbnail="javascript:alert(1)", duration=754).json()
    assert got["url"] == "https://cdn.example.com/ep2.m4a" and got["content_type"] == "audio/mp4"
    assert got["thumbnail"] is None and got["duration"] == 754 and got["live"] is False
    got = resolve(client, kind="url", source="https://cdn.example.com/a.mp3", content_type="audio/ogg").json()
    assert got["content_type"] == "audio/ogg"
    assert resolve(client, kind="url", source="file:///etc/passwd").status_code == 400
    assert resolve(client, kind="spotify", source="x").status_code == 422


def test_speaker_play_still_gets_absolute_links(client, app, fake_speaker, downloads):  # noqa: F811
    """The refactor keeps the speaker's links absolute (public_base_url)."""
    pl = app.db.create_playlist("Mix")
    app.db.add_item(pl["id"], {"kind": "tts", "source": "hi", "title": "hi", "duration": None, "thumbnail": None,
                               "lang": "en"}, 100)
    assert client.post(f"/playlists/{pl['id']}/play", json={}).status_code == 200
    assert fake_speaker.media_controller.loads[-1]["url"].startswith(f"{BASE}/tts.mp3?")
