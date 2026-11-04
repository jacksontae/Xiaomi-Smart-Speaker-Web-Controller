"""Seeking on the speaker from Now: the progress bar is a slider only when /status says the media is seekable, a drag
sends one POST /seek, and viewers keep the display-only bar. /status is stubbed (the test speaker is offline)."""
import json

from playwright.sync_api import expect


def status(seekable=True):
    return {
        "speaker": "Test speaker", "ip": "192.0.2.10", "app": "Default Media Receiver", "volume": 0.4, "muted": False,
        "media": {"title": "Song", "state": "PAUSED", "duration": 200, "position": 20, "thumbnail": None,
                  "seekable": seekable},
        "resume_pending": None, "tts_lang": "en", "queue": None, "talking": None,
    }


def stub(page, body, seeks):
    page.route("**/status", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(body)))

    def on_seek(r):
        seeks.append(r.request.post_data_json["position"])
        r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))
    page.route("**/seek", on_seek)


def test_operator_drags_to_seek(make_app, seeded):
    app = make_app("operator", device="desktop", go=False)
    seeks = []
    stub(app.page, status(), seeks)
    app.go("")
    p = app.page
    bar = p.locator(".np-bar")
    expect(bar).to_have_attribute("role", "slider")
    box = bar.bounding_box()
    y = box["y"] + box["height"] / 2
    p.mouse.move(box["x"] + box["width"] * 0.2, y)
    p.mouse.down()
    p.mouse.move(box["x"] + box["width"] * 0.35, y, steps=5)
    p.mouse.move(box["x"] + box["width"] * 0.5, y, steps=5)
    expect(p.locator(".np-times span").first).to_have_text("1:40")  # previewed while dragging
    assert seeks == []
    p.mouse.up()
    p.wait_for_timeout(300)
    assert len(seeks) == 1 and 95 <= seeks[0] <= 105
    # arrow keys: several presses settle into one request
    bar.focus()
    for _ in range(3):
        p.keyboard.press("ArrowRight")
    p.wait_for_timeout(900)
    assert len(seeks) == 2 and 125 <= seeks[1] <= 135
    app.clean("speaker seek")


def test_not_seekable_or_viewer_is_display_only(make_app, seeded):
    for role, body in (("operator", status(seekable=False)), ("viewer", status())):
        app = make_app(role, device="desktop", go=False)
        seeks = []
        stub(app.page, body, seeks)
        app.go("")
        bar = app.page.locator(".np-bar")
        expect(bar).to_have_attribute("role", "progressbar")
        bar.click()
        app.page.wait_for_timeout(300)
        assert seeks == []
