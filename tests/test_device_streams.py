"""The "This device" relay beyond plain HTTP: SHOUTcast v1 servers ("ICY 200 OK"), connections pinned to the
address checked public, and HLS playlists rewritten to signed relay links. Fake upstreams only (no internet)."""
import asyncio
import socket
import threading
import urllib.parse

import httpx
import pytest
from test_local import no_speaker, proxy_of, resolve, upstream  # noqa: F401 - fixtures
from test_sources import net  # noqa: F401 - fixture

from server import config, outbound
from server.routes import device as device_routes

# --- IcyStream: the status line rewrite on its own ---


class FakeStream:
    def __init__(self, *chunks):
        self.chunks = list(chunks)

    async def read(self, max_bytes, timeout=None):
        return self.chunks.pop(0) if self.chunks else b""


def read_all(app, *chunks):
    async def go():
        stream, out = outbound.IcyStream(FakeStream(*chunks)), b""
        while chunk := await stream.read(65536):
            out += chunk
        return out
    return asyncio.run(go())


def test_icy_status_line_reads_as_http(app):
    assert read_all(app, b"ICY 200 OK\r\nicy-name: x\r\n\r\nAUDIO") == b"HTTP/1.0 200 OK\r\nicy-name: x\r\n\r\nAUDIO"
    # the first bytes split over reads, and "ICY" later in the body left alone
    assert read_all(app, b"I", b"CY", b" 200 OK\r\n\r\n", b"ICY ICY") == b"HTTP/1.0 200 OK\r\n\r\nICY ICY"
    assert read_all(app, b"HTTP/1.1 200 OK\r\n\r\nICY ") == b"HTTP/1.1 200 OK\r\n\r\nICY "
    assert read_all(app, b"IC") == b"IC" and read_all(app) == b""


def test_stream_type_of_hls_parts(app):
    assert device_routes.stream_type("video/MP2T", "", part=True) == "video/mp2t"
    assert device_routes.stream_type("", "", part=True) == "application/octet-stream"  # an AES key, often untyped
    assert device_routes.stream_type("audio/aacp", "", part=True) == "audio/aac"
    assert device_routes.stream_type("text/html", "", part=True) is None
    assert device_routes.stream_type("video/mp2t", "audio/mpeg") is None  # only signed HLS part links take these


# --- Real sockets: a fake radio server on this machine, reached through the relay's own transport ---

class FakeServer:
    """Answers every connection with `answer` (bytes) and closes; records the requests it got."""

    def __init__(self, answer):
        self.answer, self.requests = answer, []
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn:
                request = b""
                while b"\r\n\r\n" not in request:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    request += chunk
                self.requests.append(request)
                conn.sendall(self.answer)

    def close(self):
        self.sock.close()


@pytest.fixture
def local_net(app, monkeypatch):
    """radio.example.com is public to check_public_url, and the relay's connections go to 127.0.0.1."""
    real = outbound.public_addresses
    monkeypatch.setattr(outbound, "resolve_host", lambda host: {"8.8.8.8"})
    monkeypatch.setattr(outbound, "public_addresses", lambda host: ["127.0.0.1"])
    # a fresh client: the module's pool belongs to whichever event loop used it first
    monkeypatch.setattr(outbound, "stream_http", httpx.AsyncClient(transport=outbound.relay_transport(),
                                                              timeout=httpx.Timeout(5), follow_redirects=False))
    servers = []

    def serve(answer):
        servers.append(FakeServer(answer))
        return servers[-1]
    serve.public_addresses = real
    yield serve
    for server in servers:
        server.close()


ICY = b"ICY 200 OK\r\nicy-name: Fake FM\r\ncontent-type: audio/mpeg\r\nicy-br: 128\r\n\r\n" + b"\xff\xfb" * 3000


def test_shoutcast_v1_server_is_relayed(client, anon, local_net, no_speaker):  # noqa: F811
    server = local_net(ICY)
    r = anon.get(proxy_of(client, f"http://radio.example.com:{server.port}/;stream.mp3"))
    assert r.status_code == 200 and r.content == b"\xff\xfb" * 3000
    assert r.headers["content-type"] == "audio/mpeg" and "icy-name" not in r.headers
    assert server.requests[0].startswith(b"GET /;stream.mp3 HTTP/1.1\r\n")
    assert b"\r\nhost: radio.example.com:" in server.requests[0].lower()  # the name, not the pinned address


def test_shoutcast_bare_newlines_and_no_type(client, anon, local_net, no_speaker):  # noqa: F811
    server = local_net(b"ICY 200 OK\nicy-name: Old FM\n\n" + b"a" * 100)
    r = anon.get(proxy_of(client, f"http://radio.example.com:{server.port}/", content_type="audio/aac"))
    assert r.status_code == 200 and r.content == b"a" * 100 and r.headers["content-type"] == "audio/aac"


def test_icy_answers_keep_the_type_check(client, anon, local_net, no_speaker):  # noqa: F811
    page = local_net(b"ICY 200 OK\r\ncontent-type: text/html\r\n\r\n<script>alert(1)</script>")
    assert anon.get(proxy_of(client, f"http://radio.example.com:{page.port}/")).status_code == 502
    refused = local_net(b"ICY 401 Unauthorized\r\n\r\n")
    assert anon.get(proxy_of(client, f"http://radio.example.com:{refused.port}/")).status_code == 502
    junk = local_net(b"SOURCE stuff\r\n\r\n")
    assert anon.get(proxy_of(client, f"http://radio.example.com:{junk.port}/")).status_code == 502


def test_plain_http_and_redirects_still_work(client, anon, local_net, no_speaker):  # noqa: F811
    server = local_net(b"HTTP/1.1 200 OK\r\ncontent-type: audio/ogg\r\ncontent-length: 4\r\n\r\nOggS")
    hop = local_net(f"HTTP/1.1 302 Found\r\nlocation: http://radio.example.com:{server.port}/x\r\n"
                    "content-length: 0\r\n\r\n".encode())
    r = anon.get(proxy_of(client, f"http://radio.example.com:{hop.port}/"))
    assert r.status_code == 200 and r.content == b"OggS" and r.headers["content-type"] == "audio/ogg"
    assert r.headers["content-length"] == "4"


def test_size_limit_applies_to_icy_streams(client, anon, app, local_net, monkeypatch, no_speaker):  # noqa: F811
    server = local_net(ICY)
    monkeypatch.setattr(config, "STREAM_MAX_BYTES", 1000)
    r = anon.get(proxy_of(client, f"http://radio.example.com:{server.port}/"))
    assert r.status_code == 200 and len(r.content) <= 1000
    assert device_routes._streams_open == 0


def test_connections_go_only_to_the_address_checked_public(client, anon, app, local_net, monkeypatch,
                                                          no_speaker):  # noqa: F811
    """DNS rebinding: the name is public when checked, then points inside. The relay checks again as it connects
    (public_addresses) and never reaches the inside address."""
    server = local_net(ICY)
    answers = iter([{"8.8.8.8"}, {"127.0.0.1"}])
    monkeypatch.setattr(outbound, "resolve_host", lambda host: next(answers))
    monkeypatch.setattr(outbound, "public_addresses", local_net.public_addresses)  # outbound.py's own, not the stand-in
    # "localhost": a connect by name (not pinned) would reach the fake server
    r = anon.get(proxy_of(client, f"http://localhost:{server.port}/"))
    assert r.status_code == 502 and "ConnectError" in r.json()["detail"]
    assert server.requests == []


def test_public_addresses(app, monkeypatch):
    monkeypatch.setattr(outbound, "resolve_host", lambda host: {"8.8.8.8", "2001:4860:4860::8888"})
    assert outbound.public_addresses("x") == ["8.8.8.8", "2001:4860:4860::8888"]  # IPv4 first
    for inside in ({"8.8.8.8", "10.0.0.1"}, {"::1"}, {"169.254.169.254"}, {"fe80::1%en0"}, set()):
        monkeypatch.setattr(outbound, "resolve_host", lambda host, inside=inside: inside)
        with pytest.raises(ValueError):
            outbound.public_addresses("x")


# --- HLS: playlists rewritten to signed relay links ---

MASTER = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=64000,CODECS="mp4a.40.5"
low/index.m3u8
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="a",NAME="en",URI="alt/en.m3u8"
#EXT-X-STREAM-INF:BANDWIDTH=128000
http://other.example.com/hi.m3u8
"""
MEDIA = """﻿#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:10
#EXT-X-SERVER-CONTROL:CAN-BLOCK-RELOAD=YES
#EXT-X-MEDIA-SEQUENCE:7
#EXT-X-KEY:METHOD=AES-128,URI="/keys/k1",IV=0x1
#EXT-X-MAP:URI="init.mp4"
#EXT-X-SESSION-KEY:METHOD=SAMPLE-AES,URI="skd://drm"
#EXTINF:10.0,
seg7.ts
#EXTINF:10.0,
https://cdn2.example.com/abs/seg8.ts?token=1
"""


def query(link):
    assert link.startswith("/local/"), link
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(link).query))


def hls_of(c, source):
    got = resolve(c, kind="url", source=source).json()
    assert got["content_type"] == "application/x-mpegurl" and got["proxy_url"].startswith("/local/hls?"), got
    return got["proxy_url"]


def test_hls_master_playlist(client, anon, upstream, no_speaker):  # noqa: F811
    upstream.routes[("radio.example.com", "/live.m3u8")] = httpx.Response(
        200, text=MASTER, headers={"content-type": "application/vnd.apple.mpegurl"})
    r = anon.get(hls_of(client, "http://radio.example.com/live.m3u8"))
    assert r.status_code == 200 and r.headers["content-type"] == "application/vnd.apple.mpegurl"
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-store"
    lines = r.text.splitlines()
    assert lines[0] == "#EXTM3U" and lines[1] == '#EXT-X-STREAM-INF:BANDWIDTH=64000,CODECS="mp4a.40.5"'
    assert lines[2].startswith("/local/hls?")  # a variant: another playlist
    assert query(lines[2])["u"] == "http://radio.example.com/low/index.m3u8"
    alt = lines[3].split('URI="')[1].rstrip('"')
    assert alt.startswith("/local/hls?") and query(alt)["u"] == "http://radio.example.com/alt/en.m3u8"
    assert query(lines[5])["u"] == "http://other.example.com/hi.m3u8"
    assert "radio.example.com" not in r.text.replace("radio.example.com%2F", "")  # no bare upstream link left
    # the rewritten variant link works in turn
    upstream.routes[("radio.example.com", "/low/index.m3u8")] = httpx.Response(200, text=MEDIA)
    assert anon.get(lines[2]).text.startswith("#EXTM3U\n#EXT-X-VERSION:3")


def test_hls_media_playlist_and_its_parts(client, anon, upstream, no_speaker):  # noqa: F811
    upstream.routes[("radio.example.com", "/moved.m3u8")] = httpx.Response(
        302, headers={"location": "https://cdn.example.com/radio/live.m3u8"})
    upstream.routes[("cdn.example.com", "/radio/live.m3u8")] = httpx.Response(
        200, text=MEDIA, headers={"content-type": "audio/mpegurl"})
    r = anon.get(hls_of(client, "http://radio.example.com/moved.m3u8"))
    assert r.status_code == 200
    text = r.text
    assert "SERVER-CONTROL" not in text and "#EXT-X-MEDIA-SEQUENCE:7" in text
    assert 'URI="skd://drm"' in text  # not http: left for the player
    lines = text.splitlines()
    key = next(x for x in lines if x.startswith("#EXT-X-KEY")).split('URI="')[1].split('"')[0]
    init = next(x for x in lines if x.startswith("#EXT-X-MAP")).split('URI="')[1].split('"')[0]
    segs = [x for x in lines if x and not x.startswith("#")]
    # relative links resolve against where the playlist really came from (after the redirect)
    assert query(key)["u"] == "https://cdn.example.com/keys/k1"
    assert query(init)["u"] == "https://cdn.example.com/radio/init.mp4"
    assert [query(s)["u"] for s in segs] == ["https://cdn.example.com/radio/seg7.ts",
                                             "https://cdn2.example.com/abs/seg8.ts?token=1"]
    assert all(s.startswith("/local/stream?") and query(s)["h"] == "1" for s in segs + [key, init])

    upstream.routes[("cdn.example.com", "/radio/seg7.ts")] = httpx.Response(
        200, content=b"G" * 188, headers={"content-type": "video/MP2T"})
    upstream.routes[("cdn.example.com", "/keys/k1")] = httpx.Response(200, content=b"k" * 16)
    upstream.routes[("cdn2.example.com", "/abs/seg8.ts")] = httpx.Response(
        200, content=b"<html>", headers={"content-type": "text/html"})
    r = anon.get(segs[0])
    assert r.status_code == 200 and r.content == b"G" * 188 and r.headers["content-type"] == "video/mp2t"
    r = anon.get(key)
    assert r.status_code == 200 and r.headers["content-type"] == "application/octet-stream"
    assert r.headers["content-security-policy"] == "sandbox"
    assert anon.get(segs[1]).status_code == 502  # a page is never served from this origin


def test_hls_links_are_signed(client, anon, upstream, no_speaker):  # noqa: F811
    upstream.routes[("radio.example.com", "/live.m3u8")] = httpx.Response(200, text=MEDIA)
    link = hls_of(client, "http://radio.example.com/live.m3u8")
    assert anon.get(link.replace("live.m3u8", "other.m3u8")).status_code == 403
    assert anon.get("/local/hls?u=http%3A%2F%2Fradio.example.com%2Flive.m3u8").status_code == 403
    seg = [x for x in anon.get(link).text.splitlines() if x.startswith("/local/stream")][0]
    assert anon.get(seg.replace("h=1", "h=0")).status_code == 403
    # a plain stream link can't be turned into a part link (which takes more types)
    plain = proxy_of(client, "http://radio.example.com/live.mp3")
    assert anon.get(plain + "&h=1").status_code == 403


def test_hls_refuses_what_isnt_a_playlist(client, anon, app, upstream, monkeypatch, no_speaker):  # noqa: F811
    upstream.routes[("radio.example.com", "/page.m3u8")] = httpx.Response(
        200, text="<html><script>alert(1)</script>", headers={"content-type": "text/html"})
    upstream.routes[("radio.example.com", "/gone.m3u8")] = httpx.Response(404)
    upstream.routes[("radio.example.com", "/big.m3u8")] = httpx.Response(
        200, text="#EXTM3U\n" + "#EXTINF:1,\nseg.ts\n" * 40_000)
    for path in ("/page.m3u8", "/gone.m3u8", "/big.m3u8"):
        assert anon.get(hls_of(client, f"http://radio.example.com{path}")).status_code == 502, path


def test_hls_blocks_private_targets(client, anon, app, upstream, monkeypatch, no_speaker):  # noqa: F811
    monkeypatch.setattr(outbound, "resolve_host", lambda host: {"10.0.0.2" if host == "lan.example.com" else "8.8.8.8"})
    assert anon.get(hls_of(client, "http://lan.example.com/live.m3u8")).status_code == 400
    upstream.routes[("radio.example.com", "/hop.m3u8")] = httpx.Response(
        302, headers={"location": "http://lan.example.com/live.m3u8"})
    assert anon.get(hls_of(client, "http://radio.example.com/hop.m3u8")).status_code == 400
    # a playlist naming an inside segment: rewritten, but the relay refuses it when fetched
    upstream.routes[("radio.example.com", "/in.m3u8")] = httpx.Response(
        200, text="#EXTM3U\n#EXTINF:10,\nhttp://lan.example.com/seg.ts\n")
    seg = anon.get(hls_of(client, "http://radio.example.com/in.m3u8")).text.splitlines()[-1]
    assert anon.get(seg).status_code == 400
    assert not [r for r in upstream.seen if r.url.host == "lan.example.com"]


def test_radio_station_with_hls_gets_the_playlist_relay(client, app, net, no_speaker):  # noqa: F811
    assert device_routes.local_proxy_path({}, "https://x.example.com/a.m3u8?x=1", "")
    assert device_routes.local_proxy_path({}, "https://x.example.com/a.m3u8", "audio/mpeg").startswith("/local/hls?")
    path = device_routes.local_proxy_path({}, "http://x.example.com/a.mp3", "application/x-mpegurl")
    assert path.startswith("/local/hls?")
    assert device_routes.local_proxy_path({}, "/yt/a.m4a?sig=1", "audio/mp4") is None
