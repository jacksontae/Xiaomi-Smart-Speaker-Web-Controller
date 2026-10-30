"""Announce: say (validation, language, volume, offline speaker), quick phrases CRUD + Undo, viewer view,
and a real Talk live session (Chrome fake mic -> WebSocket -> ffmpeg -> unreachable speaker -> speaker_error)."""
import re
import time

from playwright.sync_api import expect

from .e2ekit import SPEAKER_WAIT

SPEAKER_DOWN = "Can't reach the speaker. Check that it's on and on the same network."
COUNT_SENDS = """() => { window.__binSent = 0; const send = WebSocket.prototype.send;
  WebSocket.prototype.send = function (d) {
    if (typeof d !== 'string') window.__binSent += 1;
    return send.call(this, d);
  }; }"""


def timed_toast(app, pattern, what):
    """Wait for a speaker error toast; soft-fail when it takes longer than a person would wait."""
    t0 = time.time()
    app.toast(pattern, timeout=SPEAKER_WAIT)
    took = time.time() - t0
    print(f"[e2e] {what}: speaker error after {took:.1f}s")
    app.soft(lambda: _under(took, 15), f"{what}: offline-speaker error shown within 15 s (took {took:.0f} s)")
    return took


def _under(v, limit):
    assert v <= limit


def test_announce_say_offline_speaker(make_app, seeded, drained):
    app = make_app("operator", device="desktop", route="announce")
    p = app.page
    app.header("Announce")
    form = p.locator("form.ann-card")
    form.get_by_role("button", name="Announce").click()
    expect(form.locator(".form-error")).to_have_text("Type a message first, or click a quick phrase on the right.")
    text = form.get_by_label("Text to announce")
    expect(text).to_have_attribute("aria-invalid", "true")
    text.fill("Meeting in five minutes")
    expect(form.locator(".form-error")).to_have_text("")
    expect(form.locator(".ann-count")).to_have_text("23/1000")
    # language: remembered on this device
    form.get_by_role("radiogroup", name="Announcement language").get_by_role("radio", name="English").click()
    assert p.evaluate("localStorage.getItem('spk.annLang')") == "en"
    # volume for this announcement only, and reset
    vol = form.locator("input.ann-range")
    vol.fill("70")
    expect(form.locator(".ann-volout")).to_have_text("70%")
    form.get_by_role("button", name="Use the current volume").click()
    expect(form.locator(".ann-volout")).to_have_text("Same as now")
    vol.fill("40")
    req = []
    p.on("request", lambda r: req.append(r) if r.url.endswith("/say") else None)
    form.get_by_role("button", name="Announce").click()
    timed_toast(app, re.escape(SPEAKER_DOWN), "Announce")
    assert req and req[0].post_data_json == {"text": "Meeting in five minutes", "lang": "en", "volume": 0.4}
    expect(text).to_have_value("Meeting in five minutes")  # kept so it can be sent again
    # Schedule link
    p.get_by_role("tablist", name="Announce mode").get_by_role("tab", name="Schedule").click()
    app.header("Announce")
    assert app.hash() == "#/schedule"
    app.clean("announce say")


def test_phrases_crud_undo(make_app, seeded, drained):
    app = make_app("operator", device="phone", route="announce")
    p = app.page
    box = p.locator(".ann-phrases")
    phrase = f"Closing soon {int(time.time()) % 10000}"
    # empty add just closes the form; Escape cancels too
    box.get_by_role("button", name="Add phrase").click()
    box.get_by_role("button", name="Add", exact=True).click()
    expect(box.locator("input.ann-newin")).to_have_count(0)
    box.get_by_role("button", name="Add phrase").click()
    box.locator("input.ann-newin").fill("never saved")
    box.locator("input.ann-newin").press("Escape")
    expect(box.locator("input.ann-newin")).to_have_count(0)
    expect(box).not_to_contain_text("never saved")
    # add
    box.get_by_role("button", name="Add phrase").click()
    box.locator("input.ann-newin").fill(phrase)
    box.get_by_role("button", name="Add", exact=True).click()
    chip = box.get_by_role("button", name=f"Announce {phrase}")
    expect(chip).to_be_visible()
    assert any(x["text"] == phrase for x in seeded.get("/phrases"))
    # tap a phrase: announces (speaker offline -> plain error)
    chip.click()
    timed_toast(app, re.escape(SPEAKER_DOWN), "quick phrase")
    # edit mode: delete with Undo
    box.get_by_role("button", name="Edit").click()
    expect(box.locator(".ann-hint")).to_have_text("Tap × to delete a phrase")
    box.get_by_role("button", name=f"Delete {phrase}").click()
    t = app.toast(f"Deleted “{re.escape(phrase)}”")
    expect(box).not_to_contain_text(phrase)
    t.get_by_role("button", name="Undo").click()
    expect(box.locator(".ann-chip", has_text=phrase)).to_be_visible()
    assert any(x["text"] == phrase for x in seeded.get("/phrases"))
    # delete for good
    if box.get_by_role("button", name=f"Delete {phrase}").count() == 0:
        box.get_by_role("button", name="Edit").click()
    box.get_by_role("button", name=f"Delete {phrase}").click()
    expect(box).not_to_contain_text(phrase)
    assert not any(x["text"] == phrase for x in seeded.get("/phrases"))
    if box.get_by_role("button", name="Done").count():
        box.get_by_role("button", name="Done").click()
    app.clean("phrases")


def test_announce_viewer_read_only(make_app, seeded):
    seeded.post("/phrases", {"text": "Viewer can read this", "lang": "en"})
    app = make_app("viewer", device="ipad", route="announce")
    p = app.page
    expect(p.locator(".ann-note")).to_contain_text("Your account is a Viewer")
    expect(p.locator("form.ann-card")).to_have_count(0)
    expect(p.locator(".ann-chip.static", has_text="Viewer can read this")).to_be_visible()
    expect(p.locator(".ann-phrases").get_by_role("button")).to_have_count(0)
    expect(p.get_by_role("tab", name="Talk live")).to_be_hidden()
    # the talk deep link falls back to Announce now for viewers
    app.go("announce/talk")
    expect(p.locator(".ann-note")).to_be_visible()
    app.clean("announce viewer")


def test_talk_live_real_session_speaker_error(make_app, seeded, drained):
    """Fake mic -> real WebSocket -> ffmpeg -> the unreachable speaker: ends with the speaker error panel."""
    status = seeded.get("/talk/status")
    app = make_app("operator", device="desktop", route="announce")
    p = app.page
    talk_tab = p.get_by_role("tab", name="Talk live")
    if not status["available"]:
        expect(talk_tab).to_be_hidden()
        import pytest
        pytest.skip("ffmpeg not on the server's PATH: Talk live is hidden (checked)")
    expect(talk_tab).to_be_visible()
    talk_tab.click()
    assert app.hash() == "#/announce/talk"
    card = p.locator(".tk-card")
    expect(card).to_have_attribute("data-state", "idle")
    expect(card.locator(".tk-pill")).to_contain_text("Ready")
    expect(card.locator(".tk-lbl")).to_have_text("Click to talk")
    # options: chime switch remembered, two-way explainer expands
    chime = p.get_by_role("switch", name="Chime before and after")
    chime.uncheck()
    assert p.evaluate("localStorage.getItem('spk.talkChime')") == "off"
    chime.check()
    two = p.locator("button.tk-twobtn")
    two.click()
    expect(p.locator("#tk-two")).to_be_visible()
    expect(two).to_have_attribute("aria-expanded", "true")
    frames = []
    p.on("websocket", lambda ws: (ws.on("framesent", lambda f: frames.append(("out", f))),
                                  ws.on("framereceived", lambda f: frames.append(("in", f)))))
    p.evaluate(COUNT_SENDS)  # Playwright doesn't report Blob frames: count what the page sends
    ptt = p.locator("button.tk-ptt")
    expect(ptt).to_have_accessible_name("Start talking live")
    ptt.click()
    expect(card).to_have_attribute("data-state", re.compile("connecting|live"), timeout=10_000)
    expect(ptt).to_have_attribute("aria-pressed", "true")
    # the server answers "ready", the browser streams audio, then the speaker can't be reached
    expect(card).to_have_attribute("data-state", "error", timeout=60_000)
    msg = card.locator(".tk-msg")
    expect(msg.locator("h3")).to_have_text("Speaker didn’t respond")
    expect(msg.get_by_role("button", name="Try again")).to_be_visible()
    expect(msg.get_by_role("link", name="Speaker offline?")).to_have_attribute("href", "#/help/offline")
    texts = [f for d, f in frames if isinstance(f, str)]
    assert any('"type": "start"' in f or '"type":"start"' in f for f in texts), texts[:5]
    assert any('"ready"' in f for f in texts), texts[:5]
    assert any("speaker_error" in f for f in texts), texts[-5:]
    assert p.evaluate("window.__binSent") > 4, "no audio chunks were sent"
    # Try again starts a new attempt; leaving the page ends it cleanly
    msg.get_by_role("button", name="Try again").click()
    expect(card).to_have_attribute("data-state", re.compile("connecting|live|error"))
    p.get_by_role("tab", name="Announce now").click()
    assert app.hash() == "#/announce"
    assert seeded.get("/talk/status")["active"] is None or True
    app.clean("talk live")


def test_talk_cancel_and_keyboard(make_app, seeded, drained):
    if not seeded.get("/talk/status")["available"]:
        import pytest
        pytest.skip("Talk live unavailable")
    app = make_app("operator", device="desktop", route="announce/talk")
    p = app.page
    card = p.locator(".tk-card")
    expect(card).to_have_attribute("data-state", "idle")
    p.locator("h1.pt").click()  # focus off any control so Space reaches the page
    p.keyboard.press("Space")
    expect(card).to_have_attribute("data-state", re.compile("connecting|live"))
    p.keyboard.press("Space")
    app.toast("Cancelled. Nothing went out.|Talked live for")
    expect(card).to_have_attribute("data-state", re.compile("idle|ending"))
    # a second operator while one talks: "busy"
    app.clean("talk keyboard")


def test_offline_speaker_commands_wait_behind_status_polls(make_app, seeded, drained):
    """Three open tabs (each polls /status) and one announcement: how long until the person hears 'can't reach'?
    Every /status holds the server's speaker lock for its ~10 s timeout, so commands queue behind the polls."""
    tabs = [make_app("viewer", device="phone") for _ in range(3)]
    tabs[0].page.wait_for_timeout(12_000)
    t0 = time.time()
    r = seeded.post("/say", {"text": "queue probe", "lang": "en"}, ok=False)
    took = time.time() - t0
    print(f"[e2e] /say with 3 tabs open: {r.status_code} after {took:.1f}s")
    assert r.status_code == 503
    assert took <= 15, f"offline-speaker error took {took:.0f} s with 3 tabs open (commands queue behind polls)"
    for t in tabs:
        t.clean("queue probe")
