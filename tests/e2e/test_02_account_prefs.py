"""Account page, Account & app settings: display name, password, sign out, language/theme/motion persistence."""
import re

from playwright.sync_api import expect

from .e2ekit import BASE, OWNER, pw


def seg(p, i):
    """The i-th app preference block (0 language, 1 appearance, 2 reduce motion)."""
    return p.locator(".c-seg-wrap").nth(i)


def html(p, attr):
    return p.evaluate(f"document.documentElement.getAttribute('{attr}')")


def test_prefs_language_theme_motion_persist(make_app, seeded):
    app = make_app("operator", device="desktop", route="prefs")
    p = app.page
    app.header("Account & app settings")
    assert html(p, "lang") == "en" and html(p, "data-theme") == "light"
    # language: Thai, survives a reload, and the shell is translated
    seg(p, 0).locator("button[data-value=th]").click()
    expect(p.locator("html")).to_have_attribute("lang", "th")
    app.header("บัญชีและการตั้งค่าแอป")
    expect(p.locator(".sbn a[data-route=announce]")).to_have_text("ประกาศ")
    p.reload()
    app.header("บัญชีและการตั้งค่าแอป")
    assert p.evaluate("localStorage.getItem('spk.lang')") == "th"
    # appearance: dark, survives a reload
    seg(p, 1).locator("button[data-value=dark]").click()
    expect(p.locator("html")).to_have_attribute("data-theme", "dark")
    p.reload()
    app.header()
    expect(p.locator("html")).to_have_attribute("data-theme", "dark")
    expect(seg(p, 1).locator("button[data-value=dark]")).to_have_attribute("aria-checked", "true")
    # reduce motion: on -> CSS durations collapse app-wide, survives a reload
    seg(p, 2).locator("button[data-value=on]").click()
    expect(p.locator("html")).to_have_attribute("data-motion", "reduce")
    expect(seg(p, 2).locator("[role=status]")).to_have_text("ภาพเคลื่อนไหวในแอปปิดอยู่")
    dur = p.evaluate("getComputedStyle(document.querySelector('.nv-thumb')).transitionDuration")
    assert all(float(x.strip().rstrip("s")) <= 0.002 for x in dur.split(",")), dur
    p.reload()
    app.header()
    expect(p.locator("html")).to_have_attribute("data-motion", "reduce")
    # "follow system" with an OS that asks for less motion
    seg(p, 2).locator("button[data-value=off]").click()
    expect(p.locator("html")).to_have_attribute("data-motion", "full")
    p.emulate_media(reduced_motion="reduce")
    seg(p, 2).locator("button[data-value=system]").click()
    expect(p.locator("html")).to_have_attribute("data-motion", "reduce")
    p.emulate_media(reduced_motion="no-preference")
    expect(p.locator("html")).to_have_attribute("data-motion", "full")
    # back to English + system theme; the pre-paint script (boot.js) agrees after reload
    seg(p, 0).locator("button[data-value=en]").click()
    expect(p.locator("html")).to_have_attribute("lang", "en")
    seg(p, 1).locator("button[data-value=system]").click()
    p.emulate_media(color_scheme="dark")
    expect(p.locator("html")).to_have_attribute("data-theme", "dark")
    p.emulate_media(color_scheme="light")
    expect(p.locator("html")).to_have_attribute("data-theme", "light")
    app.clean("prefs")


def test_prefs_phone_and_account_page(make_app, seeded):
    app = make_app("owner", device="phone", route="account")
    p = app.page
    app.header("Account")
    for name in ("Members", "Speaker settings", "Sign-in methods", "Activity", "App settings", "Help"):
        expect(p.locator("#view a.c-row", has_text=name).first).to_be_visible()
    expect(p.locator("#view a.c-row", has_text="Members").locator(".c-val")).to_have_text(re.compile(r"\d+ people"))
    p.locator("#view a.c-row", has_text="App settings").click()
    app.header("App settings")
    expect(p.locator(".c-seg-wrap")).to_have_count(3)
    expect(p.locator("#view a.c-row", has_text="Speaker settings")).to_be_visible()  # owner only
    # back link on the phone header returns to Account
    p.locator("a.phd-back").click()
    app.header("Account")
    app.clean("account phone")
    viewer = make_app("viewer", device="phone", route="prefs")
    viewer.header("App settings")
    expect(viewer.page.locator("#view a.c-row", has_text="Speaker settings")).to_have_count(0)
    viewer.go("account")
    expect(viewer.page.locator("#view a.c-row", has_text="Members")).to_have_count(0)
    viewer.clean("account viewer")


def test_owner_display_name(make_app, seeded):
    app = make_app("owner", device="desktop", route="prefs")
    p = app.page
    field = p.locator(".ca-namefield input")
    field.fill("")
    p.locator(".ca-namefield button", has_text="Save").click()
    expect(p.locator(".ca-namefield .hint.err")).to_have_text("Enter a display name first")
    field.fill("Olivia Renamed")
    p.locator(".ca-namefield button", has_text="Save").click()
    app.toast("Name saved")
    expect(p.locator(".uchip-n")).to_have_text("Olivia Renamed")
    p.locator(".ca-namefield input").fill(OWNER["display_name"])
    p.locator(".ca-namefield button", has_text="Save").click()
    expect(p.locator(".uchip-n")).to_have_text(OWNER["display_name"])
    # operators have no name field (no self-service endpoint)
    op = make_app("operator", device="desktop", route="prefs")
    expect(op.page.locator(".ca-namefield")).to_have_count(0)
    app.clean("display name")
    op.clean("operator prefs")


def test_change_password_flow(make_app, seeded):
    spec = {"username": "pat", "display_name": "Pat Password", "password": pw("pat-pass-123"), "role": "operator"}
    seeded.ensure_user(spec)
    u = seeded.user("pat")
    seeded.patch(f"/users/{u['id']}", {"password": spec["password"]})
    app = make_app(None, device="ipad", go=False)
    app.login_api(spec)
    app.go("prefs")
    p = app.page
    p.locator("#view button", has_text="Change password").click()
    sheet = app.sheet()
    save = sheet.locator("button[type=submit]")
    save.click()
    expect(sheet.locator(".form-error")).to_have_text("Enter your current password first")
    fields = sheet.locator(".pw input")
    fields.nth(0).fill("wrong-current")
    fields.nth(1).fill("short")
    save.click()
    expect(sheet.locator(".form-error")).to_have_text("New password needs at least 8 characters")
    fields.nth(1).fill(pw("pat-new-pass-1"))
    fields.nth(2).fill(pw("pat-new-pass-2"))
    save.click()
    expect(sheet.locator(".form-error")).to_have_text("The new passwords don't match")
    fields.nth(2).fill(pw("pat-new-pass-1"))
    save.click()
    expect(sheet.locator(".form-error")).to_have_text("Current password is wrong")
    # the eye button shows the password
    sheet.locator("button.eye").first.click()
    expect(fields.nth(0)).to_have_attribute("type", "text")
    sheet.locator("input").nth(0).fill(spec["password"])
    save.click()
    app.toast("Password changed")
    expect(p.locator("dialog.ov[open]")).to_have_count(0)
    # still signed in here; the new password works
    app.go("announce")
    r = app.ctx.request.post(f"{BASE}/auth/login", headers={"X-Requested-With": "speaker-web"},
                             data={"username": "pat", "password": pw("pat-new-pass-1")})
    assert r.ok
    app.clean("change password")


def test_sign_out_all_devices(make_app, seeded):
    spec = {"username": "sam", "display_name": "Sam Signout", "password": pw("sam-pass-123"), "role": "viewer"}
    seeded.ensure_user(spec)
    other = make_app(None, device="desktop", go=False)
    other.login_api(spec)
    other.go("")
    app = make_app(None, device="desktop", go=False)
    app.login_api(spec)
    app.go("")
    p = app.page
    p.locator("button.uchip").click()
    p.locator(".popover .mi", has_text="Sign out of all devices").click()
    sheet = app.sheet()
    sheet.locator("button.danger").click()
    expect(p.locator("input[name=username]")).to_be_visible(timeout=10_000)
    app.toast("Signed out")
    # the other device is signed out on its next call
    other.page.evaluate("location.hash = '#/playlists'")
    expect(other.page.locator("input[name=username]")).to_be_visible(timeout=20_000)
    app.clean("sign out all")


def test_account_menu_desktop(make_app, seeded):
    app = make_app("owner", device="desktop")
    p = app.page
    p.locator("button.uchip").click()
    menu = p.locator(".popover.acct")
    expect(menu).to_be_visible()
    for label in ("Account & app settings", "Change password", "Sign out of all devices", "Help", "Sign out"):
        expect(menu.locator(".mi", has_text=label).first).to_be_visible()
    p.keyboard.press("Escape")
    expect(menu).to_have_count(0)
    for label, title in (("Help", "Help"), ("Account & app settings", "Account & app settings")):
        app.go("")
        p.locator("button.uchip").click()
        p.locator(".popover .mi", has_text=label).click()
        app.soft(lambda title=title: app.header(title), f"account menu link '{label}' navigates")
    app.clean("account menu")
