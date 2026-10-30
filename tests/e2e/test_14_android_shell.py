"""Android look (static/css/android.css, js/boot.js, js/prefs.js 'os', shell.js branches): detection by user agent,
?os= forcing (saved as spk.os), the floating nav pill on phones, the navigation rail on tablets, the Now Bar
(operators+, only while something plays, never on Now; play/pause through /pause and /resume), and the Android back
gesture closing a sheet instead of leaving the page. The speaker is offline in this suite, so /status is mocked."""
import json

import pytest
from playwright.sync_api import expect

from .conftest import NO_TOUR_JS, PREFS_JS
from .e2ekit import BASE, ROLES, App

ANDROID_PHONE = {
    "viewport": {"width": 412, "height": 915}, "is_mobile": True, "has_touch": True,
    "user_agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/130.0.0.0 Mobile Safari/537.36",
}
ANDROID_TABLET = {
    "viewport": {"width": 1280, "height": 800}, "has_touch": True,
    "user_agent": "Mozilla/5.0 (Linux; Android 15; Pixel Tablet) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/130.0.0.0 Safari/537.36",
}
PLAYING = {
    "speaker": "Test speaker", "ip": "192.0.2.10", "app": "Default Media Receiver", "volume": 0.4, "muted": False,
    "media": {"title": "Morning Café Jazz", "state": "PLAYING", "duration": 225, "position": 96, "thumbnail": None},
    "resume_pending": None, "tts_lang": "en", "queue": None, "talking": None,
}


@pytest.fixture
def android_app(browser, server, request):
    """android_app(role, device=ANDROID_PHONE, route='', playing=True, prefs=None) -> App with a mocked /status.
    app.sent lists the speaker commands the page POSTed (/pause, /resume); app.status is the mocked body."""
    made = []

    def factory(role="owner", device=ANDROID_PHONE, route="", playing=True, prefs=None, query=""):
        ctx = browser.new_context(base_url=BASE, locale="en-GB", timezone_id="Asia/Bangkok", **device)
        ctx.add_init_script(PREFS_JS.replace("PREFS", json.dumps({"spk.lang": "en", "spk.theme": "light",
                                                                    "spk.pkOffer": "never", **(prefs or {})})))
        ctx.add_init_script(NO_TOUR_JS)
        status = json.loads(json.dumps(PLAYING))
        sent = []

        def fake_status(r):
            if playing:
                r.fulfill(status=200, content_type="application/json", body=json.dumps(status))
            else:
                r.fulfill(status=503, content_type="application/json", body='{"detail": "speaker unreachable"}')

        def fake_command(r):
            path = "/" + r.request.url.rsplit("/", 1)[1]
            sent.append(path)
            status["media"]["state"] = "PAUSED" if path == "/pause" else "PLAYING"
            r.fulfill(status=200, content_type="application/json", body="{}")

        ctx.route("**/status", fake_status)
        ctx.route("**/pause", fake_command)
        ctx.route("**/resume", fake_command)
        page = ctx.new_page()
        page.set_default_timeout(10_000)
        app = App(ctx, page, f"{request.node.name}-{len(made)}")
        app.sent, app.status = sent, status
        made.append(app)
        if role:
            app.login_api(ROLES[role])
        page.goto(f"{BASE}/{query}#/{route}")
        if role:
            app.header()
        return app

    yield factory
    for a in made:
        a.ctx.close()


def is_android(p):
    return p.evaluate("document.documentElement.dataset.os || null") == "android"


def test_detection_and_forcing(android_app, seeded):
    app = android_app("owner", route="playlists", playing=False)
    p = app.page
    assert is_android(p), "an Android user agent gets the Android look"
    assert p.evaluate("!!document.getElementById('android-css')")
    # forced iOS on an Android phone: saved, the parameter leaves the address, android.css is never fetched
    p.goto(f"{BASE}/?os=ios#/playlists")
    app.header()
    assert not is_android(p)
    assert p.evaluate("location.search") == ""
    assert p.evaluate("localStorage.getItem('spk.os')") == "ios"
    assert not p.evaluate("performance.getEntriesByType('resource').some((e) => e.name.includes('android.css'))")
    # App settings: Look -> Android applies right away (the shell is rebuilt with the avatar in the top bar)
    app.go("prefs")
    p.get_by_role("radiogroup", name="Look").get_by_role("radio", name="Android").click()
    expect(p.locator(".topbar .me-top")).to_be_visible()
    assert is_android(p)
    app.clean("android detection")


def test_forced_on_desktop_browser(make_app, seeded):
    app = make_app("owner", device="desktop", route="playlists")
    p = app.page
    assert not is_android(p), "desktop keeps the glass look"
    p.goto(f"{BASE}/?os=android#/playlists")
    app.header()
    assert is_android(p)
    expect(p.locator(".sb .nv[data-route='playlists']")).to_have_attribute("aria-current", "page")
    assert p.locator(".sb").evaluate("(e) => e.getBoundingClientRect().width") == 80, "navigation rail"
    p.goto(f"{BASE}/?os=auto#/playlists")
    app.header()
    assert not is_android(p)
    app.clean("forced android on desktop")


def test_phone_nav_pill_and_now_bar(android_app, seeded):
    app = android_app("owner", route="playlists")
    p = app.page
    pill = p.locator(".tabbar")
    expect(pill).to_be_visible()
    box = pill.bounding_box()
    assert box["height"] == 68 and abs(box["x"] - 12) <= 1, f"floating pill 12 px from the side: {box}"
    assert 915 - (box["y"] + box["height"]) >= 12
    expect(p.locator(".me-btn")).to_be_hidden()
    expect(p.locator(".topbar .me-top")).to_be_visible()
    expect(p.locator(".tab[data-route='playlists']")).to_have_attribute("aria-current", "page")

    nb = p.locator(".nowbar")
    expect(nb).to_be_visible()
    expect(nb).to_contain_text("Morning Café Jazz")
    p.wait_for_timeout(500)  # entrance animation
    assert nb.bounding_box()["y"] + 48 <= box["y"], "the Now Bar sits above the nav pill"
    nb.get_by_role("button", name="Pause").click()
    expect(nb.get_by_role("button", name="Resume")).to_be_visible()
    assert app.sent == ["/pause"]
    expect(nb).to_have_class("nowbar paused")
    nb.get_by_role("button", name="Resume").click()
    expect(nb.get_by_role("button", name="Pause")).to_be_visible()
    assert app.sent == ["/pause", "/resume"]
    # the capsule opens Now, where it is not shown
    nb.get_by_role("link", name="Open Now playing").click()
    expect(p).to_have_url(f"{BASE}/#/")
    expect(nb).to_be_hidden()
    # nothing playing: gone after the next poll
    app.status["media"]["state"] = "IDLE"
    p.evaluate("location.hash = '#/playlists'")
    app.header("Playlists")
    expect(nb).to_be_hidden(timeout=10_000)
    app.clean("android phone shell")


def test_viewer_has_no_now_bar(android_app, seeded):
    app = android_app("viewer", route="playlists")
    app.page.wait_for_timeout(500)
    expect(app.page.locator(".nowbar")).to_be_hidden()
    app.clean("viewer now bar")


def test_back_closes_sheet(android_app, seeded):
    app = android_app("owner", route="", playing=False)
    p = app.page
    p.evaluate("location.hash = '#/account'")  # a page to go back to inside the app
    app.header("Account")
    p.get_by_role("button", name="Change password").click()
    app.sheet()
    p.go_back()
    app.no_sheet()
    assert app.hash() == "#/account", "back closed the sheet and stayed on the page"
    # closing with X takes its history entry back off: the next back leaves the page as usual
    p.get_by_role("button", name="Change password").click()
    app.sheet().locator(".sheet-close").click()
    app.no_sheet()
    p.wait_for_timeout(300)
    p.go_back()
    expect(p).to_have_url(f"{BASE}/#/")
    app.clean("android back")


def test_tablet_rail(android_app, seeded):
    app = android_app("owner", device=ANDROID_TABLET, route="members")
    p = app.page
    rail = p.locator(".sb")
    expect(rail).to_be_visible()
    assert rail.bounding_box()["width"] == 80
    expect(p.locator(".sb .sb-sep")).to_be_visible()  # admin items under a divider
    for rid in ("now", "announce", "music", "playlists", "members", "settings", "activity"):
        expect(p.locator(f".sb .nv[data-route='{rid}']")).to_be_visible()
    expect(p.locator(".sb .nv[data-route='members']")).to_have_attribute("aria-current", "page")
    expect(p.locator(".sb-foot .uchip .avatar")).to_be_visible()
    expect(p.locator(".tabdock")).to_be_hidden()
    nb = p.locator(".nowbar")
    expect(nb).to_be_visible()
    p.wait_for_timeout(500)  # entrance animation
    nbox = nb.bounding_box()
    assert nbox["x"] > 80 and nbox["width"] <= 560 and 800 - (nbox["y"] + nbox["height"]) <= 24, nbox
    app.clean("android tablet rail")
