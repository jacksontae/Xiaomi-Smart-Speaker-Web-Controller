"""First-run quick tour: opens once per user per device after sign-in, never again after Done/Skip/Esc, replays
from App settings and Help, steps follow the role and the screen (phone tab bar vs desktop sidebar), keyboard,
focus trap, taps outside don't close it, reduce motion, no sideways scroll."""
import re
import time

from playwright.sync_api import expect

from .e2ekit import OPERATOR, wait_for

CARD = ".tour-card"


def card(p):
    c = p.locator(CARD)
    expect(c).to_be_visible(timeout=15_000)
    return c


def step(p):
    return p.locator(".tour").get_attribute("data-step")


def steps(p):
    """Walk the tour with Next and return the step ids (stops on the last step without closing)."""
    seen = [step(p)]
    while p.locator(".tour-next").inner_text() not in ("Done", "เสร็จ"):
        p.locator(".tour-next").click()
        wait_for(lambda: step(p) != seen[-1], what="next step")
        seen.append(step(p))
    return seen


def stored(p):
    return p.evaluate("""async () => { const s = await (await fetch('/auth/state')).json();
      return localStorage.getItem('spk.tour.' + s.user.id); }""")


def no_tour_after_wait(p, seconds=3.5):
    time.sleep(seconds)  # the tour waits ~1.2 s of quiet before it opens on its own
    expect(p.locator(".tour")).to_have_count(0)


def in_view(p, sel):
    box = p.locator(sel).bounding_box()
    vw, vh = p.viewport_size["width"], p.viewport_size["height"]
    assert box and box["x"] >= 0 and box["y"] >= 0 and box["x"] + box["width"] <= vw + 1 \
        and box["y"] + box["height"] <= vh + 1, f"{sel} outside the window: {box}"


def test_tour_first_signin_phone_operator(make_app, seeded):
    app = make_app(None, device="phone", tour=True)
    p = app.page
    expect(p.locator(".tour")).to_have_count(0)  # never on the login page
    app.login_ui(OPERATOR)
    c = card(p)
    expect(c).to_have_attribute("role", "dialog")
    expect(c).to_have_attribute("aria-modal", "true")
    expect(p.locator(".tour-text")).to_have_attribute("aria-live", "polite")
    expect(c).to_be_focused()
    expect(p.locator(".tour-count")).to_have_text("1 of 5")
    expect(p.locator(".tour-back")).to_be_hidden()
    assert p.evaluate("document.getElementById('app').inert")
    p.wait_for_timeout(500)  # let the spotlight finish moving
    app.shot("tour-phone-en-light")
    app.no_hscroll("tour open, phone")
    in_view(p, CARD)
    # taps outside the card do nothing
    p.mouse.click(20, 400)
    expect(c).to_be_visible()
    # focus stays in the card
    for _ in range(5):
        p.keyboard.press("Tab")
        assert p.evaluate("document.activeElement.closest('.tour-card') !== null")
    # keyboard: arrows move, Back goes back
    p.keyboard.press("ArrowRight")
    expect(p.locator(".tour-count")).to_have_text("2 of 5")
    p.keyboard.press("ArrowLeft")
    expect(p.locator(".tour-count")).to_have_text("1 of 5")
    p.locator(".tour-next").click()
    p.locator(".tour-back").click()
    expect(p.locator(".tour-count")).to_have_text("1 of 5")
    # operator on a phone: tab bar, Now, Announce, Music, Account
    assert steps(p) == ["tabs", "now", "announce", "music", "account"]
    expect(p.locator(".tour-dot.on")).to_have_count(1)
    expect(p.locator(".tour-dot")).to_have_count(5)
    in_view(p, CARD)
    p.locator(".tour-next", has_text="Done").click()
    expect(p.locator(".tour")).to_have_count(0)
    assert not p.evaluate("document.getElementById('app').inert")
    assert stored(p) == "1"
    # not again on this device
    p.reload()
    app.header()
    no_tour_after_wait(p)
    app.clean("tour phone operator")


def test_tour_viewer_desktop_th_dark_skip(make_app, seeded):
    app = make_app("viewer", device="desktop", lang="th", theme="dark", tour=True)
    p = app.page
    card(p)
    expect(p.locator(".tour-count")).to_have_text("1 จาก 4")
    expect(p.locator(".tour-skip")).to_have_text("ข้าม")
    # viewers can't announce: sidebar, speaker, Now, Help
    assert steps(p) == ["nav", "speaker", "now", "help"]
    p.locator(".tour-back").click()
    p.locator(".tour-back").click()
    expect(p.locator(".tour")).to_have_attribute("data-step", "speaker")
    p.wait_for_timeout(500)  # let the spotlight finish moving
    app.shot("tour-desktop-th-dark")
    app.no_hscroll("tour open, desktop")
    p.locator(".tour-skip").click()
    expect(p.locator(".tour")).to_have_count(0)
    assert stored(p) == "1"
    p.reload()
    app.header()
    no_tour_after_wait(p)
    app.clean("tour viewer desktop th")


def test_tour_owner_desktop_esc_and_replay(make_app, seeded):
    app = make_app("owner", device="desktop", tour=True)
    p = app.page
    card(p)
    assert steps(p) == ["nav", "speaker", "now", "announce", "help"]
    for _ in range(4):
        p.keyboard.press("ArrowLeft")
    expect(p.locator(".tour-count")).to_have_text("1 of 5")
    p.wait_for_timeout(500)  # let the spotlight finish moving
    app.shot("tour-desktop-en-light")
    # resize while open: the card follows and stays inside the window
    p.set_viewport_size({"width": 1024, "height": 700})
    p.keyboard.press("ArrowRight")
    time.sleep(0.6)
    in_view(p, CARD)
    app.no_hscroll("tour after resize")
    p.set_viewport_size({"width": 1440, "height": 900})
    p.keyboard.press("Escape")
    expect(p.locator(".tour")).to_have_count(0)
    assert stored(p) == "1"
    # replay from Account & app settings: goes to Now, starts at step 1
    app.go("prefs")
    p.get_by_role("button", name=re.compile("Show quick tour again")).click()
    card(p)
    assert app.hash() in ("#/", "")
    expect(p.locator(".tour-count")).to_have_text("1 of 5")
    p.locator(".tour-skip").click()
    expect(p.locator(".tour")).to_have_count(0)
    # replay from Help; the row hides while searching
    app.go("help")
    tour_row = p.get_by_role("button", name="Take the quick tour")
    p.get_by_label("Search help").fill("passkey")
    expect(tour_row).to_be_hidden()
    p.get_by_label("Search help").fill("")
    tour_row.click()
    card(p)
    expect(p.locator(".tour")).to_have_attribute("data-step", "nav")
    for _ in range(5):
        p.keyboard.press("ArrowRight")  # the last ArrowRight is Done
    expect(p.locator(".tour")).to_have_count(0)
    app.clean("tour owner desktop")


def test_tour_replay_phone_th_dark_reduced_motion(make_app, seeded):
    # tour=False: the first-run tour counts as seen, so only the replay opens it
    app = make_app("viewer", device="phone", lang="th", theme="dark", motion="on", route="prefs")
    p = app.page
    no_tour_after_wait(p, 2)
    p.get_by_role("button", name=re.compile("ดูทัวร์แนะนำอีกครั้ง")).click()
    card(p)
    # viewer on a phone: no Announce or Music steps
    expect(p.locator(".tour-count")).to_have_text("1 จาก 3")
    dur = p.evaluate("getComputedStyle(document.querySelector('.tour-ring')).transitionDuration")
    assert all(float(x.strip().rstrip("s")) <= 0.002 for x in dur.split(",")), dur
    p.locator(".tour-next").click()
    expect(p.locator(".tour")).to_have_attribute("data-step", "now")
    p.wait_for_timeout(500)  # let the spotlight finish moving
    app.shot("tour-phone-th-dark")
    app.no_hscroll("tour phone th")
    in_view(p, CARD)
    # replay from Help too
    p.keyboard.press("Escape")
    expect(p.locator(".tour")).to_have_count(0)
    app.go("help")
    p.get_by_role("button", name="ดูทัวร์แนะนำ").click()
    card(p)
    assert steps(p) == ["tabs", "now", "account"]
    p.locator(".tour-next").click()
    expect(p.locator(".tour")).to_have_count(0)
    app.clean("tour phone viewer th")
