"""Music sources: internet radio, podcasts and uploaded files, played directly or from playlists."""
import asyncio
import sqlite3
import threading
from collections import OrderedDict
from types import SimpleNamespace

import httpx
import pytest
from conftest import BASE, make_user, path_of, session_client

import store
import transport as transport_module

UUID_A = "11111111-2222-3333-4444-555555555555"
UUID_B = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
STATIONS = [
    {"stationuuid": UUID_A, "name": "Jazz FM", "url": "http://radio.example.com/jazz.pls",
     "url_resolved": "https://radio.example.com/jazz", "codec": "AAC", "bitrate": 128, "countrycode": "TH",
     "tags": "jazz,smooth", "favicon": "https://radio.example.com/jazz.png", "hls": 0},
    {"stationuuid": UUID_B, "name": "News HLS", "url": "https://radio.example.com/news.m3u8", "url_resolved": "",
     "codec": "UNKNOWN", "bitrate": 0, "favicon": "javascript:alert(1)", "hls": 1},
    {"stationuuid": "not-a-uuid", "name": "Broken", "url_resolved": "https://radio.example.com/x"},
    {"stationuuid": "99999999-2222-3333-4444-555555555555", "name": "No URL", "url_resolved": "ftp://x"},
]
MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 200
FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
<channel>
  <title>Morning Show</title>
  <itunes:author>Host Person</itunes:author>
  <itunes:image href="https://cdn.example.com/show.jpg"/>
  <description>&lt;p&gt;Daily &amp;amp; fun&lt;/p&gt;</description>
  <item>
    <title>Episode 2</title>
    <guid>ep-2</guid>
    <pubDate>Mon, 26 Oct 2026 06:00:00 +0700</pubDate>
    <itunes:duration>1:02:03</itunes:duration>
    <itunes:image href="https://cdn.example.com/ep2.jpg"/>
    <description><![CDATA[<b>Big</b> news]]></description>
    <enclosure url="https://cdn.example.com/ep2.mp3" type="audio/mpeg" length="1"/>
  </item>
  <item>
    <title>Video only</title>
    <enclosure url="https://cdn.example.com/v.mp4" type="video/mp4" length="1"/>
  </item>
  <item>
    <title>Episode 1</title>
    <pubDate>not a date</pubDate>
    <itunes:duration>754</itunes:duration>
    <enclosure url="https://cdn.example.com/ep1.m4a" length="1"/>
  </item>
  <item><title>No audio</title></item>
</channel>
</rss>"""


@pytest.fixture
def net(app, monkeypatch):
    """Mock internet: routes[(host, path)] = httpx.Response or callable(request). Records requests."""
    routes, seen = {}, []

    def handle(request):
        seen.append(request)
        route = routes.get((request.url.host, request.url.path))
        if route is None:
            return httpx.Response(404)
        return route(request) if callable(route) else route

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(app, "http", client)
    monkeypatch.setattr(app, "feed_http", client)
    monkeypatch.setattr(app, "resolve_host", lambda host: {"192.0.2.1" if host == "lan.example.com" else "8.8.8.8"})
    routes[("all.api.radio-browser.info", "/json/stations/search")] = httpx.Response(200, json=STATIONS)
    routes[("all.api.radio-browser.info", "/json/stations/byuuid")] = lambda r: httpx.Response(
        200, json=[s for s in STATIONS if s["stationuuid"] == r.url.params["uuids"]])
    routes[("feeds.example.com", "/show.xml")] = httpx.Response(200, content=FEED)
    net = type("Net", (), {"routes": routes, "seen": seen})
    return net


def loads(cast):
    return cast.media_controller.loads


def actions(client):
    return [(e["actor"], e["action"], e["detail"]) for e in client.get("/activity").json()]


def upload(c, data=MP3, name="My Song.mp3", **params):
    return c.post("/files", content=data, params={"name": name, **params})


# --- Storage ---

def test_migrates_version_2_playlist_items(tmp_path):
    path = tmp_path / "v2.db"
    db = sqlite3.connect(path)
    for statement in store.SCHEMA.split(";"):
        if statement.strip():
            db.execute(statement)
    for statement in store.MIGRATIONS[2]:
        db.execute(statement)
    db.execute("INSERT INTO playlists (id, name, created_at, updated_at) VALUES (1, 'Old', 'x', 'x')")
    db.execute("INSERT INTO playlist_items (id, playlist_id, position, kind, title, source) VALUES"
               " (7, 1, 0, 'youtube', 'Song', 'aaaaaaaaaaa')")
    db.execute("PRAGMA user_version = 2")
    db.commit()
    db.close()

    upgraded = store.Store(path)
    assert upgraded.schema_version() == store.SCHEMA_VERSION
    items = upgraded.get_playlist(1)["items"]
    assert items == [{"id": 7, "kind": "youtube", "title": "Song", "source": "aaaaaaaaaaa", "duration": None,
                      "thumbnail": None, "lang": None, "content_type": None}]
    radio = upgraded.add_item(1, {"kind": "radio", "title": "R", "source": "https://r.example.com/s",
                                  "content_type": "audio/aac"}, 10)
    assert radio["kind"] == "radio" and radio["content_type"] == "audio/aac"
    with pytest.raises(sqlite3.IntegrityError):
        upgraded.add_item(1, {"kind": "spotify", "title": "x", "source": "x"}, 10)
    assert store.Store(path).get_playlist(1)["items"][0]["id"] == 7  # reopening changes nothing


# --- Transport ---

def test_cast_live_has_no_position(app, fake_speaker):
    app.transport.play("https://r.example.com/s", "audio/aac", "R", None, 30, live=True)
    load = loads(fake_speaker)[-1]
    assert load["stream_type"] == "LIVE" and "current_time" not in load


def test_relay_live_field(app, monkeypatch):
    sent = []

    class Relay(transport_module.MqttRelayTransport):
        def __init__(self):
            self._cond, self._loaded, self.cfg = threading.Condition(), OrderedDict(), SimpleNamespace(play_timeout=1)

        def command(self, cmd, timeout=None, **fields):
            sent.append(fields)

    Relay().play("https://r.example.com/s", "audio/aac", "R", None, 30, live=True)
    Relay().play("https://x.example.com/a.mp3", "audio/mpeg", "A", None, 30)
    assert sent[0] == {"url": "https://r.example.com/s", "content_type": "audio/aac", "title": "R",
                       "stream_type": "LIVE"}
    assert sent[1]["position"] == 30 and "stream_type" not in sent[1]


# --- Radio ---

def test_radio_search_maps_stations(client, net):
    r = client.get("/radio/search", params={"q": "jazz", "country": "th", "limit": 5})
    assert r.status_code == 200
    stations = r.json()
    assert [s["name"] for s in stations] == ["Jazz FM", "News HLS"]
    jazz, news = stations
    assert jazz == {"uuid": UUID_A, "name": "Jazz FM", "url": "https://radio.example.com/jazz",
                    "content_type": "audio/aac", "favicon": "https://radio.example.com/jazz.png", "country": "TH",
                    "tags": "jazz,smooth", "bitrate": 128}
    assert news["content_type"] == "application/x-mpegurl" and news["favicon"] is None and news["bitrate"] is None
    params = net.seen[-1].url.params
    assert params["name"] == "jazz" and params["countrycode"] == "TH" and params["limit"] == "5"
    assert params["hidebroken"] == "true" and net.seen[-1].headers["user-agent"].startswith("speaker-service")
    assert client.get("/radio/search", params={"country": "Thailand"}).status_code == 422


def test_radio_directory_down_is_502(client, net):
    net.routes[("all.api.radio-browser.info", "/json/stations/search")] = httpx.Response(503)
    r = client.get("/radio/search", params={"q": "x"})
    assert r.status_code == 502 and "HTTP 503" in r.json()["detail"]

    def boom(request):
        raise httpx.ConnectError("down")

    net.routes[("all.api.radio-browser.info", "/json/stations/search")] = boom
    assert "unreachable" in client.get("/radio/search").json()["detail"]


def test_favorites_crud_and_roles(client, net, as_role):
    operator = as_role("operator")
    r = operator.post("/radio/favorites", json={"uuid": UUID_A})
    assert r.status_code == 200, r.text
    fav = r.json()
    assert fav["uuid"] == UUID_A and fav["name"] == "Jazz FM" and fav["created_by"] == "Operator-User"
    assert operator.post("/radio/favorites", json={"uuid": UUID_A}).status_code == 409
    assert operator.post("/radio/favorites", json={"uuid": "99999999-0000-0000-0000-000000000000"}).status_code == 404
    custom = operator.post("/radio/favorites", json={"url": "https://my.example.com/live.mp3", "name": "Mine"}).json()
    assert custom["uuid"] is None and custom["content_type"] == "audio/mpeg"
    assert operator.post("/radio/favorites", json={"url": "ftp://x", "name": "x"}).status_code == 400
    assert operator.post("/radio/favorites", json={}).status_code == 400
    viewer = as_role("viewer")
    assert [f["name"] for f in viewer.get("/radio/favorites").json()] == ["Jazz FM", "Mine"]
    assert viewer.delete(f"/radio/favorites/{fav['id']}").status_code == 403
    assert operator.delete(f"/radio/favorites/{fav['id']}").status_code == 204
    assert operator.delete(f"/radio/favorites/{fav['id']}").status_code == 404
    assert ("Operator-User", "radio favourite", "Jazz FM") in actions(client)


def test_radio_play_is_live_and_clears_queue(client, net, app, fake_speaker):
    fav = client.post("/radio/favorites", json={"uuid": UUID_A}).json()
    pl = app.db.create_playlist("Q")
    app.db.add_item(pl["id"], {"kind": "url", "title": "U", "source": "https://x.example.com/a.mp3"}, 10)
    client.post(f"/playlists/{pl['id']}/play", json={})
    assert app._queue is not None

    r = client.post("/radio/play", json={"favorite_id": fav["id"], "volume": 0.3})
    assert r.status_code == 200 and r.json()["title"] == "Jazz FM"
    load = loads(fake_speaker)[-1]
    assert load["url"] == "https://radio.example.com/jazz" and load["stream_type"] == "LIVE"
    assert load["content_type"] == "audio/aac" and fake_speaker.volume == 0.3
    assert app._queue is None
    assert client.get("/status").json()["media"]["thumbnail"] == "https://radio.example.com/jazz.png"
    assert actions(client)[0] == ("api-token", "radio", "Jazz FM")
    assert client.post("/radio/play", json={"uuid": UUID_B}).status_code == 200
    assert loads(fake_speaker)[-1]["content_type"] == "application/x-mpegurl"
    assert client.post("/radio/play", json={"favorite_id": 999}).status_code == 404
    assert client.post("/radio/play", json={"uuid": "nope"}).status_code == 400
    assert client.post("/radio/play", json={"favorite_id": fav["id"], "volume": 3}).status_code == 422


def test_announcement_resumes_radio_live(client, net, app, fake_speaker):
    client.post("/radio/play", json={"uuid": UUID_A})
    fake_speaker.media_controller.status.adjusted_current_time = 500.0
    r = client.post("/say", json={"text": "hello"})
    assert r.json()["will_resume"] == "Jazz FM"
    assert app._resume["live"] is True and app._resume["position"] is None
    status = fake_speaker.media_controller.status
    status.player_state = "IDLE"
    asyncio.run(app.resume_after_announcement(app._say_gen, f"{BASE}/tts.mp3"))
    load = loads(fake_speaker)[-1]
    assert load["url"] == "https://radio.example.com/jazz" and load["stream_type"] == "LIVE"


# --- Podcasts ---

def test_podcast_search(client, net):
    net.routes[("itunes.apple.com", "/search")] = httpx.Response(200, json={"results": [
        {"collectionId": 42, "collectionName": "Morning Show", "artistName": "Host", "trackCount": 9,
         "feedUrl": "https://feeds.example.com/show.xml", "artworkUrl600": "https://cdn.example.com/a.jpg",
         "primaryGenreName": "News"},
        {"collectionId": 43, "collectionName": "No feed"},
    ]})
    r = client.get("/podcasts/search", params={"q": "morning", "country": "th"})
    assert r.status_code == 200
    assert r.json() == [{"id": 42, "title": "Morning Show", "author": "Host", "feed_url":
                         "https://feeds.example.com/show.xml", "artwork": "https://cdn.example.com/a.jpg",
                         "genre": "News", "episode_count": 9}]
    params = net.seen[-1].url.params
    assert params["term"] == "morning" and params["media"] == "podcast" and params["country"] == "TH"
    assert client.get("/podcasts/search", params={"q": ""}).status_code == 422


def test_podcast_episodes_parsed(client, net):
    r = client.get("/podcasts/episodes", params={"feed": "https://feeds.example.com/show.xml"})
    assert r.status_code == 200, r.text
    show = r.json()
    assert show["title"] == "Morning Show" and show["author"] == "Host Person"
    assert show["artwork"] == "https://cdn.example.com/show.jpg" and show["description"] == "Daily & fun"
    ep2, ep1 = show["episodes"]
    assert ep2 == {"guid": "ep-2", "title": "Episode 2", "published": "2026-10-25T23:00:00+00:00",
                   "duration": 3723.0, "url": "https://cdn.example.com/ep2.mp3", "content_type": "audio/mpeg",
                   "thumbnail": "https://cdn.example.com/ep2.jpg", "description": "Big news"}
    assert ep1["duration"] == 754 and ep1["published"] is None and ep1["content_type"] == "audio/mp4"
    assert ep1["thumbnail"] == "https://cdn.example.com/show.jpg" and ep1["guid"] == ep1["url"]
    limited = client.get("/podcasts/episodes", params={"feed": "https://feeds.example.com/show.xml", "limit": 1})
    assert len(limited.json()["episodes"]) == 1


def test_feed_must_be_public_and_redirects_are_checked(client, net):
    r = client.get("/podcasts/episodes", params={"feed": "http://lan.example.com/feed"})
    assert r.status_code == 400 and "public internet" in r.json()["detail"]
    assert client.get("/podcasts/episodes", params={"feed": "file:///etc/passwd"}).status_code == 400
    net.routes[("feeds.example.com", "/moved")] = httpx.Response(302, headers={"location": "/show.xml"})
    assert client.get("/podcasts/episodes", params={"feed": "https://feeds.example.com/moved"}).status_code == 200
    net.routes[("feeds.example.com", "/sneaky")] = httpx.Response(
        301, headers={"location": "http://lan.example.com/admin"})
    r = client.get("/podcasts/episodes", params={"feed": "https://feeds.example.com/sneaky"})
    assert r.status_code == 400 and not any(req.url.host == "lan.example.com" for req in net.seen)
    net.routes[("feeds.example.com", "/loop")] = httpx.Response(302, headers={"location": "/loop"})
    assert "too many" in client.get("/podcasts/episodes", params={"feed": "https://feeds.example.com/loop"}).text


def test_bad_feeds_are_502(client, net, app, monkeypatch):
    feeds = {"/html": b"<html><body>hi</body></html>", "/junk": b"not xml <<<",
             "/bomb": b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa">]><rss><channel/></rss>'}
    for path, body in feeds.items():
        net.routes[("feeds.example.com", path)] = httpx.Response(200, content=body)
        r = client.get("/podcasts/episodes", params={"feed": f"https://feeds.example.com{path}"})
        assert r.status_code == 502, path
    monkeypatch.setattr(app, "FEED_MAX", 100)
    r = client.get("/podcasts/episodes", params={"feed": "https://feeds.example.com/show.xml"})
    assert r.status_code == 502 and "too large" in r.json()["detail"]


def test_podcast_play(client, app, fake_speaker):
    r = client.post("/podcasts/play", json={"url": "https://cdn.example.com/ep2.mp3", "title": "Episode 2",
                                             "thumbnail": "https://cdn.example.com/ep2.jpg"})
    assert r.status_code == 200
    load = loads(fake_speaker)[-1]
    assert load["url"] == "https://cdn.example.com/ep2.mp3" and load["stream_type"] == "BUFFERED"
    assert load["content_type"] == "audio/mpeg" and load["title"] == "Episode 2"
    fake_speaker.media_controller.status.adjusted_current_time = 90.0
    assert app.capture_youtube()["position"] == 90 - app.RESUME_REWIND  # resumable after an announcement
    assert actions(client)[0] == ("api-token", "podcast", "Episode 2")
    assert client.post("/podcasts/play", json={"url": "nope", "title": "x"}).status_code == 400
    assert client.post("/podcasts/play", json={"url": "https://x.example.com/a", "title": " "}).status_code == 400


# --- My files ---

def test_upload_list_and_serve(as_role, app, anon):
    operator = as_role("operator")
    r = upload(operator, duration=61.5)
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["title"] == "My Song" and f["original_name"] == "My Song.mp3" and f["content_type"] == "audio/mpeg"
    assert f["size"] == len(MP3) and f["duration"] == 61.5 and f["owner"] == "Operator-User"
    assert "stored_name" not in f
    listing = as_role("viewer").get("/files").json()
    assert [i["id"] for i in listing["items"]] == [f["id"]] and listing["used"] == len(MP3)
    assert listing["max_size"] == app.UPLOAD_MAX and ".mp3" in listing["types"]
    stored = app.db.get_file(f["id"])["stored_name"]
    assert (app.MEDIA_DIR / stored).read_bytes() == MP3 and stored.endswith(".mp3")
    assert [p.name for p in app.MEDIA_DIR.iterdir()] == [stored]  # no .part left behind
    served = anon.get(path_of(app.media_url(f"/media/{stored}")))
    assert served.content == MP3 and served.headers["content-type"] == "audio/mpeg"
    ranged = anon.get(path_of(app.media_url(f"/media/{stored}")), headers={"Range": "bytes=0-2"})
    assert ranged.status_code == 206 and ranged.content == b"ID3"
    assert anon.get(f"/media/{stored}").status_code == 403
    assert anon.get(path_of(app.media_url("/media/..%2Fdata.db"))).status_code in (403, 404)
    assert anon.get(path_of(app.media_url("/media/missing.mp3"))).status_code == 404


@pytest.mark.parametrize(("head", "ext", "ctype"), [
    (b"\xff\xfb\x90\x00", ".mp3", "audio/mpeg"),
    (b"\xff\xf1\x50\x80", ".aac", "audio/aac"),
    (b"\x00\x00\x00\x20ftypM4A ", ".m4a", "audio/mp4"),
    (b"OggS\x00\x02", ".ogg", "audio/ogg"),
    (b"RIFF\x24\x00\x00\x00WAVEfmt ", ".wav", "audio/wav"),
    (b"fLaC\x00\x00", ".flac", "audio/flac"),
    (b"\x1aE\xdf\xa3\x01", ".webm", "audio/webm"),
])
def test_upload_formats_are_sniffed(client, app, head, ext, ctype):
    f = upload(client, head + b"\x00" * 100, name="clip.bin").json()  # the name's extension doesn't matter
    assert f["content_type"] == ctype and app.db.get_file(f["id"])["stored_name"].endswith(ext)


def test_upload_rejections(client, app, monkeypatch):
    r = upload(client, b"MZ\x90\x00 not audio", name="evil.mp3")
    assert r.status_code == 415
    assert upload(client, b"").status_code == 400
    assert client.post("/files", content=MP3).status_code == 422  # name is required
    monkeypatch.setattr(app, "UPLOAD_MAX", 100)
    assert upload(client).status_code == 413
    monkeypatch.setattr(app, "UPLOAD_MAX", 10_000)
    monkeypatch.setattr(app, "UPLOAD_QUOTA", len(MP3) + 50)
    assert upload(client).status_code == 200
    r = upload(client)
    assert r.status_code == 507
    assert len(app.db.list_files()) == 1 and len(list(app.MEDIA_DIR.iterdir())) == 1


def test_rename_and_delete_permissions(app, client):
    alice = session_client(make_user("alice", "operator", "Alice"))
    bob = session_client(make_user("bob", "operator", "Bob"))
    admin = session_client(make_user("root", "admin", "Root"))
    viewer = session_client(make_user("vic", "viewer", "Vic"))
    f = upload(alice).json()
    assert alice.patch(f"/files/{f['id']}", json={"title": "  Better  "}).json()["title"] == "Better"
    assert bob.patch(f"/files/{f['id']}", json={"title": "Mine now"}).status_code == 403
    assert viewer.patch(f"/files/{f['id']}", json={"title": "x"}).status_code == 403
    assert alice.patch(f"/files/{f['id']}", json={"title": " "}).status_code == 400
    assert bob.delete(f"/files/{f['id']}").status_code == 403
    assert admin.patch(f"/files/{f['id']}", json={"title": "Admin's"}).status_code == 200
    stored = app.db.get_file(f["id"])["stored_name"]
    assert admin.delete(f"/files/{f['id']}").status_code == 204
    assert not (app.MEDIA_DIR / stored).exists() and admin.delete(f"/files/{f['id']}").status_code == 404
    own = upload(bob).json()
    assert bob.delete(f"/files/{own['id']}").status_code == 204
    log = actions(client)
    assert ("Root", "file delete", "Admin's") in log and ("Alice", "file rename", "My Song -> Better") in log


def test_file_play(client, app, fake_speaker):
    f = upload(client).json()
    r = client.post(f"/files/{f['id']}/play", json={})
    assert r.status_code == 200
    load = loads(fake_speaker)[-1]
    stored = app.db.get_file(f["id"])["stored_name"]
    assert load["url"].startswith(f"{BASE}/media/{stored}?") and load["content_type"] == "audio/mpeg"
    assert load["title"] == "My Song" and load["stream_type"] == "BUFFERED"
    assert client.post("/files/999/play", json={}).status_code == 404
    (app.MEDIA_DIR / stored).unlink()
    assert client.post(f"/files/{f['id']}/play", json={}).status_code == 410


# --- Playlists and schedules ---

def test_playlist_items_of_new_kinds(client, net, app):
    pid = client.post("/playlists", json={"name": "Mix"}).json()["id"]
    f = upload(client).json()

    def add(**body):
        return client.post(f"/playlists/{pid}/items", json=body)

    radio = add(kind="radio", source=UUID_A).json()
    assert radio["source"] == "https://radio.example.com/jazz" and radio["title"] == "Jazz FM"
    assert radio["thumbnail"] == "https://radio.example.com/jazz.png" and radio["content_type"] == "audio/aac"
    own = add(kind="radio", source="https://my.example.com/live.aac", title="Mine").json()
    assert own["content_type"] == "audio/aac"
    assert add(kind="radio", source="https://my.example.com/live").status_code == 400  # needs a title
    pod = add(kind="podcast", source="https://cdn.example.com/ep2.mp3", title="Episode 2", duration=3723,
              thumbnail="https://cdn.example.com/ep2.jpg", content_type="audio/mpeg").json()
    assert pod["duration"] == 3723 and pod["thumbnail"] == "https://cdn.example.com/ep2.jpg"
    assert add(kind="podcast", source="https://cdn.example.com/x.mp3").status_code == 400
    item = add(kind="file", source=str(f["id"])).json()
    assert item["source"] == str(f["id"]) and item["title"] == "My Song" and item["content_type"] == "audio/mpeg"
    assert add(kind="file", source="999").status_code == 400
    assert add(kind="spotify", source="x").status_code == 422

    client.patch(f"/files/{f['id']}", json={"title": "Renamed"})
    assert client.get(f"/playlists/{pid}").json()["items"][-1]["title"] == "Renamed"
    client.delete(f"/files/{f['id']}")
    assert [i["kind"] for i in client.get(f"/playlists/{pid}").json()["items"]] == ["radio", "radio", "podcast"]


def test_queue_plays_new_kinds(client, app, fake_speaker):
    f = upload(client).json()
    pl = app.db.create_playlist("Mix")
    app.db.add_item(pl["id"], {"kind": "file", "title": "My Song", "source": str(f["id"]),
                               "content_type": "audio/mpeg"}, 10)
    app.db.add_item(pl["id"], {"kind": "podcast", "title": "Ep", "source": "https://cdn.example.com/ep.m4a"}, 10)
    app.db.add_item(pl["id"], {"kind": "radio", "title": "Jazz", "source": "https://radio.example.com/jazz",
                               "content_type": "audio/aac"}, 10)
    assert client.post(f"/playlists/{pl['id']}/play", json={}).status_code == 200
    first = loads(fake_speaker)[-1]
    assert first["url"].startswith(f"{BASE}/media/") and first["stream_type"] == "BUFFERED"
    client.post("/queue/next")
    second = loads(fake_speaker)[-1]
    assert second["url"] == "https://cdn.example.com/ep.m4a" and second["content_type"] == "audio/mp4"
    client.post("/queue/next")
    third = loads(fake_speaker)[-1]
    assert third["url"] == "https://radio.example.com/jazz" and third["stream_type"] == "LIVE"
    assert app.capture_youtube()["live"] is True


def test_queue_skips_a_file_deleted_from_disk(client, app, fake_speaker):
    f = upload(client).json()
    (app.MEDIA_DIR / app.db.get_file(f["id"])["stored_name"]).unlink()
    pl = app.db.create_playlist("Mix")
    app.db.add_item(pl["id"], {"kind": "file", "title": "Gone", "source": str(f["id"])}, 10)
    app.db.add_item(pl["id"], {"kind": "url", "title": "U", "source": "https://x.example.com/a.mp3"}, 10)
    assert client.post(f"/playlists/{pl['id']}/play", json={}).status_code == 200
    assert loads(fake_speaker)[-1]["url"] == "https://x.example.com/a.mp3"
    assert ("system", "queue skip", "Gone: The uploaded file is gone") in actions(client)


def test_schedule_plays_playlist_with_radio(client, app, fake_speaker):
    pl = app.db.create_playlist("Morning radio")
    app.db.add_item(pl["id"], {"kind": "radio", "title": "Jazz", "source": "https://radio.example.com/jazz",
                               "content_type": "audio/aac"}, 10)
    s = client.post("/schedules", json={"name": "Wake", "action": "playlist", "playlist_id": pl["id"],
                                         "time": "07:00", "days": [0, 1, 2, 3, 4, 5, 6]}).json()
    r = client.post(f"/schedules/{s['id']}/run")
    assert r.status_code == 200, r.text
    load = loads(fake_speaker)[-1]
    assert load["url"] == "https://radio.example.com/jazz" and load["stream_type"] == "LIVE"
