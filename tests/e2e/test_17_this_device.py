"""This device as a speaker: pick it in the speaker picker, play a playlist's TTS item in the browser's own <audio>
element (the server only signs the link), seek, see that announcements still go to the speaker, keep the choice
after a reload, and switch back. Needs Chromium's --autoplay-policy=no-user-gesture-required (conftest)."""
import io
import math
import re
import struct
import time
import wave
from urllib.parse import urlsplit

from playwright.sync_api import expect

TEXT = "Hello from this device"


def tone_wav(seconds=4, rate=8000):
    """A short 440 Hz WAV, served in place of /tts.mp3 so the run needs no internet (Google TTS)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate)))
                               for i in range(seconds * rate)))
    return buf.getvalue()


def tts_playlist(api, name="Device check"):
    for p in api.get("/playlists"):
        if p["name"] == name:
            api.delete(f"/playlists/{p['id']}")
    pid = api.post("/playlists", {"name": name}).json()["id"]
    api.post(f"/playlists/{pid}/items", {"kind": "tts", "source": TEXT, "lang": "en"})
    return pid


def watch(app):
    """Serve the tone for signed TTS links and record the API calls the page makes."""
    seen = {"tts": [], "calls": []}
    wav = tone_wav()

    def tts(route):
        seen["tts"].append(route.request.url)
        route.fulfill(status=200, content_type="audio/wav", body=wav)

    app.page.route(re.compile(r".*/tts\.mp3\?.*"), tts)
    app.page.on("request", lambda r: seen["calls"].append((r.method, urlsplit(r.url).path)))
    return seen


def pick(app, which):
    """Choose an output in the speaker picker (desktop: the sidebar's speaker block opens a popover)."""
    p = app.page
    p.locator("[data-spk='side']").click()
    row = p.locator(f".spi[data-out='{which}']")
    expect(row).to_be_visible()
    row.click()


def test_play_tts_on_this_device(make_app, seeded, api):
    pid = tts_playlist(api)
    app = make_app("operator", "desktop")
    seen = watch(app)
    p = app.page

    pick(app, "device")
    app.toast(re.compile(r"plays on this device", re.I))
    assert p.evaluate("localStorage.getItem('spk.output')") == "device"
    expect(p.locator("[data-spk='side']")).to_contain_text("This device")

    app.go(f"playlists/{pid}")
    play = p.locator("#view .pl-play")
    expect(play).to_be_visible()
    play.click()
    p.wait_for_function("() => { const a = document.getElementById('local-audio');"
                        " return a && !a.paused && a.currentTime > 0.3; }", timeout=15_000)
    assert seen["tts"], "the TTS link was never fetched"
    assert "sig=" in seen["tts"][0] and "exp=" in seen["tts"][0], "the browser plays the server-signed link"
    assert ("POST", f"/playlists/{pid}/play") not in seen["calls"], "the speaker's play endpoint must not be called"
    assert ("POST", "/local/resolve") in seen["calls"]

    # Now playing follows this device: title, the queue, the note, and a seek slider
    app.go("")
    expect(p.locator(".np-title")).to_have_text(TEXT)
    expect(p.locator(".np-local")).to_contain_text("Announcements")
    bar = p.locator(".np-bar")
    expect(bar).to_have_attribute("role", "slider")
    bar.focus()
    p.keyboard.press("Home")
    p.wait_for_function("() => document.getElementById('local-audio').currentTime < 1.5")
    expect(p.locator(".np-queue")).to_contain_text("Device check")

    # announcements still go to the speaker, and the page says so
    app.go("announce")
    expect(p.locator(".out-note")).to_contain_text("always play on the speaker")

    # the choice survives a reload; switching back stops this device and touches nothing on the speaker
    p.reload()
    app.header()
    expect(p.locator("[data-spk='side']")).to_contain_text("This device")
    pick(app, "main")
    assert p.evaluate("localStorage.getItem('spk.output')") == "speaker"
    expect(p.locator(".out-note")).to_have_count(0)
    app.clean("this device")


def test_phone_picker_and_viewer(make_app, seeded):
    app = make_app("operator", "phone")
    p = app.page
    p.locator(".topbar [data-spk='chip']").click()
    sheet = app.sheet()
    expect(sheet.locator(".spi[data-out='device']")).to_contain_text("This device")
    expect(sheet.locator(".spi[data-out='main']")).to_be_visible()
    p.keyboard.press("Escape")
    app.clean("phone picker")

    viewer = make_app("viewer", "phone")
    viewer.page.locator(".topbar [data-spk='chip']").click()
    sheet = viewer.sheet()
    expect(sheet.locator(".spi[data-out='device']")).to_contain_text("This device")  # viewers may play here too
    viewer.page.keyboard.press("Escape")
    viewer.clean("viewer")


def device_plays(p):
    p.wait_for_function("() => { const a = document.getElementById('local-audio');"
                        " return a && !a.paused && a.currentTime > 0.3; }", timeout=15_000)


def test_viewer_plays_on_this_device_and_it_is_logged_once(make_app, seeded, api):
    """A viewer can't touch the speaker, but may play a playlist on their own device; the owner's Activity
    gets one entry for it (not one per track, seek or resolve)."""
    pid = tts_playlist(api, "Viewer device")
    before = {e["id"] for e in api.get("/activity")}
    app = make_app("viewer", "desktop")
    seen = watch(app)
    p = app.page
    pick(app, "device")
    app.go(f"playlists/{pid}")
    play = p.locator("#view .pl-play")
    expect(play).to_be_visible()
    expect(p.locator("#view .pl-links")).to_have_count(0)  # still no editing for viewers
    play.click()
    device_plays(p)
    assert ("POST", f"/playlists/{pid}/play") not in seen["calls"]
    app.go("")
    bar = p.locator(".np-bar")
    bar.focus()
    p.keyboard.press("Home")  # a seek is not a new play
    p.wait_for_function("() => document.getElementById('local-audio').currentTime < 1.5")
    p.wait_for_timeout(500)
    new = [e for e in api.get("/activity") if e["id"] not in before and e["action"] != "login ok"]
    assert [(e["action"], e["detail"]) for e in new] == [("device play", "Viewer device")], new
    assert seen["calls"].count(("POST", "/local/played")) == 1
    app.clean("viewer device")


def test_stream_the_browser_cant_play_goes_through_the_relay(make_app, seeded):
    """A type this browser reports it can't play: the player asks the server's relay (/local/stream) instead of
    the station's own link. The relay itself is covered by tests/test_local.py (no internet here)."""
    app = make_app("operator", "desktop")
    p = app.page
    wav = tone_wav()
    relayed, direct = [], []
    p.route(re.compile(r".*/local/stream\?.*"), lambda r: (relayed.append(r.request.url),
                                                         r.fulfill(status=200, content_type="audio/wav", body=wav)))
    p.route("https://radio.example.com/**", lambda r: (direct.append(r.request.url), r.abort()))
    pick(app, "device")
    p.evaluate("""async () => {
      const src = document.querySelector('script[src*="app.js"]').src;
      const m = await import(src.replace('app.js', 'local-player.js'));
      await m.playItem({ kind: 'radio', source: 'https://radio.example.com/live', title: 'Test FM',
                         content_type: 'audio/x-not-a-real-codec' });
    }""")
    device_plays(p)
    assert relayed and "sig=" in relayed[0] and not direct
    app.clean("relay")


PLAY_RADIO = """async ([url, type]) => {
  const src = document.querySelector('script[src*="app.js"]').src;
  const m = await import(src.replace('app.js', 'local-player.js'));
  window.__lp = m;
  try { await m.playItem({ kind: 'radio', source: url, title: 'Test FM', content_type: type }); return null; }
  catch (e) { return e.message; }
}"""


def test_live_stream_reconnects_when_it_ends(make_app, seeded):
    """The relay ends a live stream after 6 h (or it drops): the player fetches a fresh link and goes on by
    itself, with a backoff (1 s, 2 s, ...). Here each relayed "stream" is a 1 s clip, so it ends at once."""
    app = make_app("operator", "desktop")
    p = app.page
    wav = tone_wav(seconds=1)
    relayed = []
    p.route(re.compile(r".*/local/stream\?.*"), lambda r: (relayed.append(r.request.url),
                                                         r.fulfill(status=200, content_type="audio/wav", body=wav)))
    pick(app, "device")
    assert p.evaluate(PLAY_RADIO, ["https://radio.example.com/live", "audio/x-not-a-real-codec"]) is None
    p.wait_for_function("() => window.__lp.status(null).media.state === 'PLAYING'", timeout=15_000)
    deadline = time.time() + 15
    while len({urlsplit(u).query for u in relayed}) < 3 and time.time() < deadline:
        p.wait_for_timeout(250)
    links = {urlsplit(u).query for u in relayed}
    assert len(links) >= 3, relayed  # two reconnects, each with a fresh signed link
    assert p.evaluate("() => window.__lp.status(null).media.state") in ("PLAYING", "BUFFERING")
    # stopping ends it for good: no reconnect after
    p.evaluate("() => window.__lp.stop()")
    count = len(relayed)
    p.wait_for_timeout(5000)
    assert len(relayed) == count and p.evaluate("() => window.__lp.status(null).media.state") == "IDLE"
    app.clean("reconnect")


def test_hls_station_on_this_device(make_app, seeded):
    """HLS (.m3u8): a browser that plays it itself (Safari, recent Chrome) tries the station's link, then the
    server's playlist relay (/local/hls). One that doesn't (stubbed here) is told so plainly, without trying."""
    app = make_app("operator", "desktop")
    p = app.page
    fetched = []
    p.route(re.compile(r".*(/local/hls\?|radio\.example\.com).*"), lambda r: (fetched.append(r.request.url), r.abort()))
    pick(app, "device")
    hls = ["https://radio.example.com/live.m3u8", "application/vnd.apple.mpegurl"]
    if p.evaluate("() => document.createElement('audio').canPlayType('application/vnd.apple.mpegurl')"):
        assert "HLS" not in (p.evaluate(PLAY_RADIO, hls) or "")
        assert any("radio.example.com/live.m3u8" in u for u in fetched), fetched
        assert any("/local/hls?" in u and "sig=" in u for u in fetched), fetched
        fetched.clear()
    p.evaluate("""() => {
      const own = HTMLMediaElement.prototype.canPlayType;
      HTMLMediaElement.prototype.canPlayType = function (type) {
        return /mpegurl/i.test(type) ? '' : own.call(this, type);
      };
    }""")
    message = p.evaluate(PLAY_RADIO, hls)
    assert message and "HLS" in message and not fetched
    app.clean("hls")
