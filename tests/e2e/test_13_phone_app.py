"""Phone behaves like an app: no zoom (viewport meta, 16px+ fields, gesture block), no sideways scrolling under
stress (long unbroken text, toasts, sheets, page-enter animations, 320/390 px), toasts that always go away,
tooltips that only open on tap on touch and never stick, the same Announce mode switch on Announce and Schedule,
and page changes without a blank frame."""
import time

import pytest
from playwright.sync_api import expect

# Records the widest sideways overflow seen on any animation frame, and what stuck out at that moment.
# The html/body overflow-x: clip safety net is switched off first, so this finds root causes, not just symptoms.
SAMPLER = """() => {
  if (window.__ov) return;
  const st = document.createElement('style');
  st.textContent = 'html, body { overflow-x: visible !important; }';
  document.head.append(st);
  window.__ov = { max: 0, where: [] };
  // fixed boxes and boxes inside a clipping/scrolling parent don't widen the page
  const clipped = (e) => {
    if (getComputedStyle(e).position === 'fixed') return true;
    for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) {
      const s = getComputedStyle(a);
      if (s.overflowX !== 'visible' || s.position === 'fixed') return true;
    }
    return false;
  };
  const sample = () => {
    const d = document.documentElement;
    const over = Math.max(d.scrollWidth, document.body.scrollWidth) - d.clientWidth;
    if (over > window.__ov.max) {
      window.__ov.max = over;
      window.__ov.where = [location.hash, ...[...document.querySelectorAll('body *')].filter((e) => {
        const r = e.getBoundingClientRect();
        return r.width && r.right > d.clientWidth + 1 && !clipped(e);
      }).slice(0, 6).map((e) => `${e.tagName.toLowerCase()}.${[...e.classList].join('.')}`
        + ` right=${Math.round(e.getBoundingClientRect().right)}`)];
    }
    requestAnimationFrame(sample);
  };
  requestAnimationFrame(sample);
}"""

LONG_WORD = "ประชาสัมพันธ์" * 6  # a long Thai run with no spaces
LONG_URL = "https://example.com/" + "a-very-long-path-segment-without-breaks" * 4 + ".mp3"
ROUTES = ["", "announce", "music", "playlists", "schedule", "account", "prefs", "settings", "members", "activity",
          "auth", "help"]


def overflow(p):
    return p.evaluate("() => window.__ov")


def test_phone_no_zoom(make_app, seeded):
    app = make_app("owner", device="phone")
    p = app.page
    meta = p.locator("meta[name=viewport]").get_attribute("content")
    for part in ("width=device-width", "initial-scale=1", "maximum-scale=1", "viewport-fit=cover"):
        assert part in meta, f"viewport meta has {part}: {meta}"
    assert p.evaluate("getComputedStyle(document.documentElement).touchAction") == "manipulation"
    assert p.evaluate("getComputedStyle(document.body).touchAction") == "manipulation"
    # iOS pinch: gesturestart is cancelled (the app's listener calls preventDefault)
    assert p.evaluate("""() => { const e = new Event('gesturestart', { cancelable: true });
      document.dispatchEvent(e); return e.defaultPrevented; }""")
    # every text field is 16px or more (iOS zooms into smaller ones on focus), on every page and in a few sheets
    small = []
    find = """() => [...document.querySelectorAll('input, select, textarea')].filter((e) => {
        if (['checkbox', 'radio', 'range', 'file', 'hidden', 'color'].includes(e.type)) return false;
        return e.getClientRects().length && parseFloat(getComputedStyle(e).fontSize) < 16;
      }).map((e) => `${location.hash} ${e.tagName.toLowerCase()}.${[...e.classList].join('.')}`
        + `[${e.name || e.type}] ${getComputedStyle(e).fontSize}`)"""
    for route in ROUTES:
        app.go(route)
        small += p.evaluate(find)
    app.go("account")
    p.get_by_role("button", name="Change password").first.click()
    app.sheet()
    small += p.evaluate(find)
    p.keyboard.press("Escape")
    app.no_sheet()
    app.go("playlists")
    p.locator(".phd button.btn.primary").click()  # "New playlist" ("New" on narrow phones)
    app.sheet()
    small += p.evaluate(find)
    assert not small, f"fields under 16px on phones: {small}"
    # text stays selectable (no app-wide user-select: none)
    assert p.evaluate("getComputedStyle(document.body).userSelect") != "none"
    app.clean("phone zoom")


@pytest.mark.parametrize("width", [320, 390])
def test_phone_no_sideways_scroll_under_stress(make_app, seeded, width):
    stamp = int(time.time()) % 100000
    pl = seeded.post("/playlists", {"name": f"{LONG_WORD}{stamp}"}).json()
    seeded.post(f"/playlists/{pl['id']}/items", {"kind": "url", "source": LONG_URL, "title": LONG_URL})
    seeded.post(f"/playlists/{pl['id']}/items", {"kind": "tts", "source": LONG_WORD * 2, "lang": "th"})
    phrase = seeded.post("/phrases", {"text": LONG_URL + LONG_WORD, "lang": "th"}).json()
    try:
        app = make_app("owner", device="phone")
        p = app.page
        p.set_viewport_size({"width": width, "height": 740})
        for lang in ("en", "th"):
            p.evaluate(f"localStorage.setItem('spk.lang', '{lang}')")
            p.reload()
            app.header()
            p.evaluate(SAMPLER)
            for route in ROUTES:
                app.go(route)
                p.evaluate(SAMPLER)  # a hash navigation keeps the sampler; a reload would need it again
                p.wait_for_timeout(350)  # let the page-enter animation run under the sampler
            # sheet open/close, playlist detail with the long name, toasts with long text
            app.go(f"playlists/{pl['id']}")
            p.evaluate(SAMPLER)
            p.wait_for_timeout(300)
            p.locator(".pl-links button.linkbtn").first.click()  # Add item (either language)
            app.sheet()
            p.wait_for_timeout(400)
            p.locator(".sheet-close").click()
            app.no_sheet()
            p.evaluate(f"""() => import(document.querySelector('script[type=module]').src.replace(/[^/]+$/, 'ui.js'))
              .then((m) => {{ m.toast({LONG_URL!r} + ' ' + {LONG_WORD!r}, 'err'); m.toast('Saved', 'ok'); }})""")
            p.wait_for_timeout(600)
            # the speaker chip and the help button in the top bar, the tab bar
            app.go("")
            p.evaluate(SAMPLER)
            p.wait_for_timeout(400)
        ov = overflow(p)
        assert ov["max"] <= 1, f"sideways overflow of {ov['max']}px at {width}px: {ov['where']}"
        # and with the safety net on, nothing can be scrolled sideways
        p.reload()
        app.header()
        assert p.evaluate("() => { scrollTo(400, scrollY); const x = scrollX; scrollTo(0, scrollY); return x; }") == 0
        app.clean(f"phone stress {width}")
    finally:
        seeded.delete(f"/playlists/{pl['id']}")
        seeded.delete(f"/phrases/{phrase['id']}")


def test_toasts_always_go_away(make_app, seeded):
    app = make_app("owner", device="phone", motion="reduce")
    p = app.page
    toast = """(args) => import(document.querySelector('script[type=module]').src.replace(/[^/]+$/, 'ui.js'))
      .then((m) => { for (const [msg, kind, opts] of args) m.toast(msg, kind, opts || {}); })"""
    # capped: only the newest few stay on screen
    p.evaluate(toast, [[f"Toast {i}", "info", None] for i in range(6)])
    expect(p.locator("#toasts .toast")).to_have_count(3)
    # a tap on the toast dismisses it
    p.locator("#toasts .toast", has_text="Toast 5").click()
    expect(p.locator("#toasts .toast", has_text="Toast 5")).to_have_count(0)
    # every toast times out, even one with an action or a huge ms
    p.evaluate(toast, [["Forever?", "info", {"ms": 10 ** 9, "action": {"label": "Undo", "run": None}}]])
    expect(p.locator("#toasts .toast")).to_have_count(0, timeout=15_000)
    # while a sheet is open the toast sits on top of it (inside the modal's top layer) and can still be tapped
    app.go("account")
    p.get_by_role("button", name="Change password").first.click()
    app.sheet()
    p.evaluate(toast, [["Over the sheet", "ok", None]])
    t = p.locator(".toast", has_text="Over the sheet")
    expect(t).to_be_visible()
    box = t.bounding_box()
    assert 0 <= box["x"] and box["x"] + box["width"] <= 390 and 0 <= box["y"] <= 844, f"toast on screen: {box}"
    t.click()
    expect(t).to_have_count(0)
    p.keyboard.press("Escape")
    app.no_sheet()
    # the toast host survives the sheet closing: toasts still show afterwards
    p.evaluate(toast, [["After the sheet", "ok", None]])
    expect(p.locator("#toasts .toast", has_text="After the sheet")).to_be_visible()
    # a touch tooltip never sticks: any tap elsewhere hides it, and it hides itself
    p.evaluate("""() => { const b = document.querySelector('[data-tip]'); if (!b) return;
      b.dispatchEvent(new PointerEvent('pointerdown', { pointerType: 'touch', bubbles: true }));
      b.dispatchEvent(new PointerEvent('pointercancel', { pointerType: 'touch', bubbles: true })); }""")
    p.wait_for_timeout(900)
    expect(p.locator(".tip")).to_have_count(0)
    app.clean("toasts")


def test_touch_tooltips_open_on_tap_only(make_app, seeded):
    app = make_app("operator", device="phone", route="playlists")
    p = app.page
    pl = seeded.post("/playlists", {"name": f"Tips {int(time.time()) % 10000}"}).json()
    seeded.post(f"/playlists/{pl['id']}/items", {"kind": "tts", "source": "Tip test", "lang": "en"})
    try:
        app.go(f"playlists/{pl['id']}")
        rep = p.locator(".pl-rep")
        # a finger passing over (pointerenter/long press without a tap) opens nothing
        rep.dispatch_event("pointerenter", {"pointerType": "touch"})
        rep.dispatch_event("pointerdown", {"pointerType": "touch"})
        p.wait_for_timeout(900)
        rep.dispatch_event("pointercancel", {"pointerType": "touch"})
        expect(p.locator(".tip")).to_have_count(0)
        # a tap on the trigger shows it; a tap elsewhere hides it
        rep.tap()
        expect(p.locator(".tip")).to_be_visible()
        p.locator(".pl-hero").tap()
        expect(p.locator(".tip")).to_have_count(0)
        # it also hides by itself, and on a route change
        rep.tap()
        expect(p.locator(".tip")).to_be_visible()
        expect(p.locator(".tip")).to_have_count(0, timeout=6000)
        rep.tap()
        app.go("playlists")
        expect(p.locator(".tip")).to_have_count(0)
        # the per-announcement volume hint is page text now, not a hover label
        app.go("announce")
        p.locator(".ann-range").fill("60")
        expect(p.locator(".ann-volhint")).to_be_visible()
        expect(p.locator(".tip")).to_have_count(0)
    finally:
        seeded.delete(f"/playlists/{pl['id']}")
    app.clean("touch tooltips")


def test_mouse_tooltips_still_hover(make_app, seeded):
    app = make_app("operator", device="desktop", route="playlists")
    p = app.page
    p.locator(".tb-rb, .pl-rep, [data-tip]").first.hover()
    expect(p.locator(".tip")).to_be_visible(timeout=3000)
    p.mouse.move(5, 5)
    expect(p.locator(".tip")).to_have_count(0)
    app.clean("mouse tooltips")


@pytest.mark.parametrize("device", ["phone", "desktop"])
def test_mode_switch_same_on_announce_and_schedule(make_app, seeded, device):
    app = make_app("operator", device=device, route="announce")
    p = app.page
    talk = p.request.get("/talk/status")
    available = talk.ok and talk.json().get("available")
    expected = ["Announce now", "Talk live", "Schedule"] if available else ["Announce now", "Schedule"]

    def tabs():
        sw = p.get_by_role("tablist", name="Announce mode")
        expect(sw).to_be_visible()
        p.wait_for_timeout(300)  # the thumb settles
        return [b.inner_text().strip() for b in sw.get_by_role("tab").all() if b.is_visible()], sw.bounding_box()

    names_a, box_a = tabs()
    assert names_a == expected, names_a
    p.get_by_role("tablist", name="Announce mode").get_by_role("tab", name="Schedule").click()
    app.header("Announce")
    assert app.hash() == "#/schedule"
    names_s, box_s = tabs()
    assert names_s == expected, f"schedule page switch {names_s} != {expected}"
    assert abs(box_a["width"] - box_s["width"]) <= 1 and abs(box_a["x"] - box_s["x"]) <= 1, (box_a, box_s)
    sel = p.get_by_role("tablist", name="Announce mode").get_by_role("tab", selected=True)
    expect(sel).to_have_text("Schedule")
    if available:
        p.get_by_role("tablist", name="Announce mode").get_by_role("tab", name="Talk live").click()
        app.header("Announce")
        assert app.hash() == "#/announce/talk"
    app.clean(f"mode switch {device}")


FRAMES = """() => {
  window.__frames = [];
  const v = document.getElementById('view');
  const tick = () => {
    const pg = v.firstElementChild;
    window.__frames.push({ kids: v.childElementCount, op: pg ? +getComputedStyle(pg).opacity : 0,
      vt: !!document.documentElement.matches(':active-view-transition') });
    if (window.__frames.length < 600) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}"""


@pytest.mark.parametrize("device", ["phone", "desktop"])
def test_page_change_has_no_blank_frame(make_app, seeded, device):
    """Every animation frame during route changes shows a page (never an empty view or a page faded below 50%)."""
    app = make_app("owner", device=device)
    p = app.page
    p.evaluate(FRAMES)
    for route in ("announce", "playlists", "account" if device == "phone" else "members", "help", ""):
        p.evaluate(f"location.hash = '#/{route}'")
        p.wait_for_timeout(450)
    frames = p.evaluate("window.__frames")
    blank = [f for f in frames if f["kids"] == 0 or f["op"] < 0.5]
    assert frames and not blank, f"{len(blank)} blank/faded frames of {len(frames)}: {blank[:5]}"
    app.clean(f"no blank frame {device}")
