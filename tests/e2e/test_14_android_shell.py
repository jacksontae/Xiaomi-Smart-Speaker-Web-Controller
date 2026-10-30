"""Android look (static/css/android.css, js/boot.js, shell.js branches): it follows the OS (a Chrome-on-Android user
agent here), the floating nav pill with filled active icons and drag-to-select on phones, the navigation rail with
Help on tablets, the Now Bar
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

    def factory(role="owner", device=ANDROID_PHONE, route="", playing=True, prefs=None):
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
        page.goto(f"{BASE}/#/{route}")
        if role:
            app.header()
        return app

    yield factory
    for a in made:
        a.ctx.close()


FETCHED_ANDROID_CSS = "performance.getEntriesByType('resource').some((e) => e.name.includes('android.css'))"


def is_android(p):
    return p.evaluate("document.documentElement.dataset.os || null") == "android"


def test_follows_the_os(android_app, make_app, seeded):
    app = android_app("owner", route="playlists", playing=False)
    p = app.page
    assert is_android(p), "an Android user agent gets the Android look"
    assert p.evaluate("!!document.getElementById('android-css')")
    assert p.evaluate("localStorage.getItem('spk.os')") is None, "no stored look: it follows the OS"
    # a wide window on Android is still Android (rail); the tablet test covers it
    # iPhone and desktop: the glass look, and android.css is never fetched
    for device in ("phone", "desktop"):
        other = make_app("owner", device=device, route="playlists")
        assert not is_android(other.page)
        assert not other.page.evaluate(FETCHED_ANDROID_CSS)
        # the old ?os= override is gone
        other.page.goto(f"{BASE}/?os=android#/playlists")
        other.header()
        assert not is_android(other.page)
        other.clean(f"{device} keeps the glass look")
    app.clean("android detection")


def drag(p, bar, frm, to, axis="x"):
    """A touch slide along the nav from one item to another (synthetic pointer events, pointerType touch)."""
    a, b = p.locator(frm).bounding_box(), p.locator(to).bounding_box()
    x0, y0 = a["x"] + a["width"] / 2, a["y"] + a["height"] / 2
    x1, y1 = (b["x"] + b["width"] / 2, y0) if axis == "x" else (x0, b["y"] + b["height"] / 2)
    ev = {"pointerId": 7, "pointerType": "touch", "isPrimary": True, "bubbles": True}
    p.locator(frm).dispatch_event("pointerdown", {**ev, "clientX": x0, "clientY": y0})
    for i in range(1, 7):
        f = i / 6
        at = {"clientX": x0 + (x1 - x0) * f, "clientY": y0 + (y1 - y0) * f}
        p.locator(bar).dispatch_event("pointermove", {**ev, **at})
    hot = p.locator(f"{bar} [data-hot]").get_attribute("data-route")
    p.locator(bar).dispatch_event("pointerup", {**ev, "clientX": x1, "clientY": y1})
    return hot


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
    # filled icon on the active destination only
    expect(p.locator(".tab[data-route='playlists'] .ic-f")).to_be_visible()
    expect(p.locator(".tab[data-route='playlists'] .ic-o")).to_be_hidden()
    expect(p.locator(".tab[data-route='music'] .ic-o")).to_be_visible()
    expect(p.locator(".tab[data-route='music'] .ic-f")).to_be_hidden()
    # slide along the pill: the item under the finger lights up, release opens it
    assert drag(p, ".tabbar", ".tab[data-route='playlists']", ".tab[data-route='announce']") == "announce"
    expect(p).to_have_url(f"{BASE}/#/announce")
    p.evaluate("location.hash = '#/playlists'")
    app.header("Playlists")

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
    for rid in ("now", "announce", "music", "playlists", "members", "settings", "activity", "help"):
        expect(p.locator(f".sb .nv[data-route='{rid}']")).to_be_visible()
    expect(p.locator(".sb .nv[data-route='members']")).to_have_attribute("aria-current", "page")
    expect(p.locator(".sb-foot .uchip .avatar")).to_be_visible()
    expect(p.locator("#view .phd .help-btn")).to_be_hidden()  # Help lives in the rail
    expect(p.locator(".sb .nv[data-route='members'] .ic-f")).to_be_visible()
    p.locator(".sb .nv[data-route='help']").click()
    expect(p.locator(".sb .nv[data-route='help']")).to_have_attribute("aria-current", "page")
    p.go_back()
    app.header("Members")
    expect(p.locator(".tabdock")).to_be_hidden()
    nb = p.locator(".nowbar")
    expect(nb).to_be_visible()
    p.wait_for_timeout(500)  # entrance animation
    nbox = nb.bounding_box()
    assert nbox["x"] > 80 and nbox["width"] <= 560 and 800 - (nbox["y"] + nbox["height"]) <= 24, nbox
    app.clean("android tablet rail")
