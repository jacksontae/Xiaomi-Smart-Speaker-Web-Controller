"""This device as a speaker: pick it in the speaker picker, play a playlist's TTS item in the browser's own <audio>
element (the server only signs the link), seek, see that announcements still go to the speaker, keep the choice
after a reload, and switch back. Needs Chromium's --autoplay-policy=no-user-gesture-required (conftest)."""
import io
import math
import re
import struct
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
    expect(viewer.page.locator(".topbar [data-spk='chip']")).to_be_visible()
    assert viewer.page.locator(".spi[data-out='device']").count() == 0
    viewer.clean("viewer")
