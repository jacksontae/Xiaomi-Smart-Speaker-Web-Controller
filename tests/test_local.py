"""This device: POST /local/resolve gives the browser a playable link and never touches the speaker,
POST /local/played logs what a person started, GET /local/stream relays streams the browser can't fetch itself."""
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


def test_viewers_may_use_it(as_role, anon):
    """It plays only on the member's own device, so viewers get it too (the speaker's endpoints stay operator+)."""
    body = {"kind": "tts", "source": "hello"}
    assert resolve(anon, **body).status_code == 401
    assert resolve(as_role("viewer"), **body).status_code == 200
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
    assert got["proxy_url"] is None  # this server's own links need no relay
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
    assert got["proxy_url"].startswith("/local/stream?") and "sig=" in got["proxy_url"]
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
    hls = resolve(client, kind="url", source="https://cdn.example.com/live.m3u8",
                  content_type="application/vnd.apple.mpegurl").json()
    assert hls["proxy_url"] is None  # relaying the playlist alone would break its segment links
    assert resolve(client, kind="spotify", source="x").status_code == 422


def test_speaker_play_still_gets_absolute_links(client, app, fake_speaker, downloads):  # noqa: F811
    """The refactor keeps the speaker's links absolute (public_base_url)."""
    pl = app.db.create_playlist("Mix")
    app.db.add_item(pl["id"], {"kind": "tts", "source": "hi", "title": "hi", "duration": None, "thumbnail": None,
                               "lang": "en"}, 100)
    assert client.post(f"/playlists/{pl['id']}/play", json={}).status_code == 200
    assert fake_speaker.media_controller.loads[-1]["url"].startswith(f"{BASE}/tts.mp3?")


# --- Activity: POST /local/played ---

def test_played_is_logged_once_per_call(as_role, anon, app, no_speaker):
    viewer = as_role("viewer", "vee")
    assert viewer.post("/local/played", json={"title": "  Morning   mix  "}).status_code == 204
    assert [(e["actor"].lower(), e["action"], e["detail"]) for e in app.db.activity()] == [
        ("vee", "device play", "Morning mix")]
    assert viewer.post("/local/played", json={"title": "   "}).status_code == 400
    assert viewer.post("/local/played", json={}).status_code == 422
    assert anon.post("/local/played", json={"title": "x"}).status_code == 401
    assert len(app.db.activity()) == 1


def test_resolve_alone_logs_nothing(client, app, net, no_speaker):  # noqa: F811
    """The browser resolves ahead (next track) and again (expired link): only /local/played writes the log."""
    resolve(client, kind="radio", source=UUID_A)
    resolve(client, kind="radio", source=UUID_A)
    assert app.db.activity() == []


# --- Stream relay: GET /local/stream ---

@pytest.fixture
def upstream(app, net, monkeypatch):  # noqa: F811
    """Fake radio servers on the mock internet (no real network): the relay uses the same mock client."""
    monkeypatch.setattr(app, "stream_http", app.http)
    return net


def proxy_of(c, source, **body):
    got = resolve(c, kind="radio", source=source, **body).json()
    assert got["proxy_url"], got
    return got["proxy_url"]


def test_stream_relays_audio(client, anon, upstream, no_speaker):
    upstream.routes[("radio.example.com", "/live.mp3")] = httpx.Response(
        200, content=b"ID3" + b"\x01" * 5000, headers={"content-type": "audio/mpeg", "icy-name": "x"})
    url = proxy_of(client, "http://radio.example.com/live.mp3")
    r = fetch(anon, url)  # signed: the <audio> element fetches it without headers
    assert r.status_code == 200 and r.content == b"ID3" + b"\x01" * 5000
    assert r.headers["content-type"] == "audio/mpeg" and r.headers["x-content-type-options"] == "nosniff"
    assert "icy-name" not in r.headers
    sent = upstream.seen[-1]
    assert sent.url == "http://radio.example.com/live.mp3" and "icy-metadata" not in sent.headers
    assert anon.get(url.replace("sig=", "sig=0")).status_code == 403
    assert anon.get(url.replace("live.mp3", "other.mp3")).status_code == 403  # the signature covers the URL


def test_stream_type_names_and_ranges(client, anon, upstream, no_speaker):
    def ranged(request):
        assert request.headers["range"] == "bytes=10-"
        return httpx.Response(206, content=b"x" * 5, headers={
            "content-type": "audio/aacp", "content-range": "bytes 10-14/15", "accept-ranges": "bytes"})
    upstream.routes[("radio.example.com", "/aac")] = ranged
    r = anon.get(proxy_of(client, "https://radio.example.com/aac"), headers={"Range": "bytes=10-"})
    assert r.status_code == 206 and r.headers["content-type"] == "audio/aac"  # an odd name some servers use
    assert r.headers["content-range"] == "bytes 10-14/15" and r.headers["accept-ranges"] == "bytes"
    # no type from the server: the one the station directory gave
    upstream.routes[("radio.example.com", "/bare")] = httpx.Response(200, content=b"ogg")
    r = anon.get(proxy_of(client, "https://radio.example.com/bare", content_type="audio/ogg"))
    assert r.status_code == 200 and r.headers["content-type"] == "audio/ogg"


def test_stream_refuses_what_isnt_audio(client, anon, upstream, no_speaker):
    upstream.routes[("radio.example.com", "/page")] = httpx.Response(
        200, content=b"<script>alert(1)</script>", headers={"content-type": "text/html"})
    upstream.routes[("radio.example.com", "/gone")] = httpx.Response(404)
    assert anon.get(proxy_of(client, "https://radio.example.com/page")).status_code == 502
    assert anon.get(proxy_of(client, "https://radio.example.com/gone")).status_code == 502


def test_stream_blocks_private_targets(client, anon, app, upstream, monkeypatch, no_speaker):
    """No SSRF: hosts that resolve into private, loopback or link-local networks are refused, redirects too."""
    addresses = {"lan.example.com": "172.16.0.5", "loop.example.com": "127.0.0.1",
                 "meta.example.com": "169.254.169.254", "v6.example.com": "::1"}
    monkeypatch.setattr(app, "resolve_host", lambda host: {addresses.get(host, "8.8.8.8")})
    for host in addresses:
        assert anon.get(proxy_of(client, f"http://{host}/live")).status_code == 400, host
    upstream.routes[("radio.example.com", "/hop")] = httpx.Response(
        302, headers={"location": "http://meta.example.com/latest/meta-data"})
    assert anon.get(proxy_of(client, "http://radio.example.com/hop")).status_code == 400
    assert not [r for r in upstream.seen if r.url.host in addresses]
    # a public redirect is followed
    upstream.routes[("radio.example.com", "/moved")] = httpx.Response(302, headers={"location": "/live.mp3"})
    upstream.routes[("radio.example.com", "/live.mp3")] = httpx.Response(200, content=b"ok",
                                                                        headers={"content-type": "audio/mpeg"})
    assert anon.get(proxy_of(client, "http://radio.example.com/moved")).content == b"ok"


def test_stream_only_http_upstreams(client, anon, app, no_speaker):
    url = app.media_path("/local/stream", u="file:///etc/passwd", t="")
    assert anon.get(url).status_code == 400


def test_stream_stops_at_the_size_limit_and_frees_its_slot(client, anon, app, upstream, monkeypatch, no_speaker):
    async def endless():
        for _ in range(1000):
            yield b"z" * 1000
    upstream.routes[("radio.example.com", "/endless")] = lambda r: httpx.Response(
        200, content=endless(), headers={"content-type": "audio/mpeg"})
    monkeypatch.setattr(app, "STREAM_MAX_BYTES", 10_000)
    r = anon.get(proxy_of(client, "https://radio.example.com/endless"))
    assert r.status_code == 200 and len(r.content) == 10_000
    assert app._streams_open == 0


def test_stream_time_limit_and_open_cap(client, anon, app, upstream, monkeypatch, no_speaker):
    upstream.routes[("radio.example.com", "/live.mp3")] = httpx.Response(200, content=b"a" * 100,
                                                                        headers={"content-type": "audio/mpeg"})
    url = proxy_of(client, "https://radio.example.com/live.mp3")
    monkeypatch.setattr(app, "STREAM_MAX_SECONDS", -1)
    assert anon.get(url).content == b""  # over time: the relay ends and the browser asks for a fresh link
    monkeypatch.setattr(app, "STREAM_MAX_SECONDS", 3600)
    monkeypatch.setattr(app, "_streams_open", app.STREAM_MAX_OPEN)
    assert anon.get(url).status_code == 503


def test_stream_stalled_upstream_ends_the_relay(client, anon, upstream, no_speaker):
    async def stalls():
        yield b"first"
        raise httpx.ReadTimeout("no bytes for 30 s")
    upstream.routes[("radio.example.com", "/stall")] = lambda r: httpx.Response(
        200, content=stalls(), headers={"content-type": "audio/mpeg"})
    r = anon.get(proxy_of(client, "https://radio.example.com/stall"))
    assert r.status_code == 200 and r.content == b"first"
